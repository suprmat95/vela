"""App FastAPI di Vela: un solo processo per REST e MCP (RNF-02).

La superficie MCP (M3) è innestata su ``/mcp`` in ogni modalità; il suo session manager gira nel
lifespan.

``create_app`` è la factory usata dai test; ``app`` è l'istanza per ``uvicorn vela.app:app``.
In replay il dominio è costruito su Postgres con gli adapter finti e il lifespan riallinea il
catalogo alle fixture dell'host (M7); in live il catalogo viene dal sync multi-brand (M10), avviato
in un thread dopo la lettura della quota. Poi il lifespan riaccoda le prenotazioni pendenti
(RF-27) e avvia il worker (RF-50).
La superficie REST (``/v1``) è sempre montata; gli errori sotto ``/v1`` sono RFC 7807.
Nessun webhook Stripe: il pagamento si chiude con ``POST /v1/bookings`` di HofJ e Vela lo scopre
interrogando la Checkout Session (job di M5).
Il pagamento è Stripe se ``STRIPE_SECRET_KEY`` è impostata, altrimenti finto.
In ``loadtest`` (M13a) HofJ è il finto di ``loadtest/fake_hofj`` via HTTP, come in live, ma solo su
localhost o ``fake-hofj``; il catalogo parte dalle fixture dei brand, il pagamento è sempre finto e
il checkout di replay è montato.
Gli SMS al viaggiatore sono Twilio se le tre variabili ``TWILIO_*`` sono impostate, altrimenti finti
(sempre finti in ``loadtest``).
"""
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple
from urllib.parse import urlparse

from fastapi import FastAPI
from sqlalchemy.engine import Engine

from vela.adapters.db import make_engine
from vela.adapters.hofj_http import HofJHttp
from vela.adapters.hofj_replay import FIXTURE_PATH, ReplayHofJ
from vela.adapters.hofj_router import BrandRouter, SingleClientRouter
from vela.adapters.repo_postgres import PostgresRepositories
from vela.adapters.sms_fake import FakeSms
from vela.adapters.sms_twilio import TwilioSms
from vela.adapters.stripe_fake import FakePayments
from vela.adapters.stripe_links import StripePayments, build_stripe_client
from vela.adapters.worker import Worker
from vela.config import DEFAULT_TRAVELER, Settings, live_brands
from vela.domain.booking import BookingJob
from vela.domain.catalog import fixture_meta, load_fixture, select_fixtures
from vela.domain.jobs import JobProcessor
from vela.domain.models import JobKind, Product
from vela.domain.payment_check import PaymentCheckJob
from vela.domain.purchase import PurchaseJob
from vela.domain.sms import SmsJob
from vela.domain.usecases import Vela
from vela.ports.catalog import CatalogSource
from vela.ports.hofj import HofJRouter
from vela.ports.notifier import Notifier
from vela.ports.payments import PaymentsPort
from vela.surfaces.checkout_pages import router as checkout_router
from vela.surfaces.health import router as health_router
from vela.surfaces.mcp import build_mcp, mcp_routes
from vela.surfaces.problems import install_problem_handlers
from vela.surfaces.replay import router as replay_router
from vela.surfaces.rest import router as rest_router
from vela.sync import CatalogSync, SyncScheduler

REPLAY = "replay"
LIVE = "live"
LOADTEST = "loadtest"
LOADTEST_HOSTS = ("localhost", "127.0.0.1", "fake-hofj")   # mai HofJ vero sotto carico (M13a)
CatalogLoader = Callable[[], List[Product]]
FIXTURES_DIR = os.path.dirname(FIXTURE_PATH)   # fixture per (host, brand) (decisioni M7 e M10)


def build_payments(settings: Settings) -> PaymentsPort:
    """Stripe se `STRIPE_SECRET_KEY` è impostata (indipendente dall'upstream HofJ), altrimenti
    il pagamento finto. Senza `VELA_PUBLIC_URL` l'avvio si blocca: servono i ritorni del Checkout.
    In `loadtest` sempre finto: il load test non tocca Stripe (M13a)."""
    if not settings.stripe_secret_key or settings.vela_upstream_mode == LOADTEST:
        return FakePayments(settings.vela_public_url)
    if not settings.vela_public_url:
        raise RuntimeError("STRIPE_SECRET_KEY richiede VELA_PUBLIC_URL per le pagine di ritorno "
                           "del Checkout")
    return StripePayments(build_stripe_client(settings.stripe_secret_key), settings.vela_public_url)


TWILIO_VARS = (("TWILIO_ACCOUNT_SID", "twilio_account_sid"), ("TWILIO_AUTH_TOKEN", "twilio_auth_token"),
               ("TWILIO_FROM", "twilio_from"))


def build_notifier(settings: Settings) -> Notifier:
    """SMS Twilio con tutte e tre le variabili, finti con nessuna (indipendente dall'upstream).
    Una configurazione a metà blocca l'avvio: meglio che scoprire in produzione SMS mai partiti.
    In `loadtest` sempre finti, come il pagamento: il load test non manda SMS veri (M13a)."""
    if settings.vela_upstream_mode == LOADTEST:
        return FakeSms()
    missing = [name for name, attr in TWILIO_VARS if not getattr(settings, attr)]
    if len(missing) == len(TWILIO_VARS):
        return FakeSms()
    if missing:
        raise RuntimeError("SMS Twilio: mancano %s" % ", ".join(missing))
    return TwilioSms(settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_from)


@dataclass(frozen=True)
class Upstream:
    """Cosa serve del mondo HofJ: il router del carrello e, in replay, il catalogo delle
    fixture da riallineare al boot; in live la sorgente e la mappa dei brand del sync (M10)."""
    router: HofJRouter
    catalog_loader: Optional[CatalogLoader] = None
    catalog_source: Optional[CatalogSource] = None
    brands: Optional[dict] = None


def build_hofj(settings: Settings) -> Upstream:
    """Replay (RNF-08) oppure HofJ vero con `VELA_UPSTREAM_MODE=live` (M5). In live servono
    chiave, host, `HOFJ_BRANDS` e un pagamento vero: il checkout finto non è montato in live.
    Un `HofJHttp` per brand, stessa chiave e stesso host; il locale è quello delle fixture
    registrate sull'host (`it` in produzione, `en` su staging).
    `loadtest` (M13a): come live ma verso il finto HofJ, solo su `LOADTEST_HOSTS`, senza Stripe;
    il locale di ogni brand è quello della sua fixture, perché il finto non è un host registrato.
    Il catalogo parte dalle fixture dei brand (le stesse che serve il finto), così ogni giro non
    rifà il sync completo; lo scheduler resta e trova il catalogo fresco."""
    if settings.vela_upstream_mode == REPLAY:
        hofj = ReplayHofJ(latency=settings.replay_latency, limit=settings.replay_limit)
        return Upstream(SingleClientRouter(hofj), catalog_loader=hofj.load_catalog)
    mode = settings.vela_upstream_mode
    if mode not in (LIVE, LOADTEST):
        raise RuntimeError("VELA_UPSTREAM_MODE=%s sconosciuto: usare replay, live o loadtest" % mode)
    missing = [name for name, value in (("HOFJ_API_KEY", settings.hofj_api_key),
                                        ("HOFJ_BASE_URL", settings.hofj_base_url)) if not value]
    if missing:
        raise RuntimeError("VELA_UPSTREAM_MODE=%s richiede %s" % (mode, ", ".join(missing)))
    try:
        brands = live_brands(settings)
    except ValueError as exc:
        raise RuntimeError("VELA_UPSTREAM_MODE=%s: %s" % (mode, exc)) from None
    if mode == LOADTEST:
        host = urlparse(settings.hofj_base_url).hostname
        if host not in LOADTEST_HOSTS:
            raise RuntimeError("VELA_UPSTREAM_MODE=loadtest: HOFJ_BASE_URL deve puntare al finto HofJ "
                               "(%s), non a %s" % (", ".join(LOADTEST_HOSTS), host))
        locales = brand_locales(FIXTURES_DIR)
        clients = {brand: HofJHttp(settings.hofj_base_url, settings.hofj_api_key, brand,
                                   locale=locales.get(brand, "it"))
                   for brand in brands.values()}
        paths = brand_fixtures(FIXTURES_DIR, brands.values())
        def loader():
            return [p for path in paths for p in load_fixture(path)]
        return Upstream(BrandRouter(clients, brands), catalog_loader=loader,
                        catalog_source=next(iter(clients.values())), brands=brands)
    if not settings.stripe_secret_key:
        raise RuntimeError("VELA_UPSTREAM_MODE=live richiede STRIPE_SECRET_KEY: il pagamento finto "
                           "non esiste contro HofJ vero")
    locale = fixture_meta(select_fixtures(FIXTURES_DIR, settings.hofj_base_url)[0])["locale"]
    clients = {brand: HofJHttp(settings.hofj_base_url, settings.hofj_api_key, brand, locale=locale)
               for brand in brands.values()}
    return Upstream(BrandRouter(clients, brands), catalog_source=next(iter(clients.values())),
                    brands=brands)


def _fixtures_by_brand(fixtures_dir: str) -> dict:
    """{brand: (percorso, meta)} delle fixture `catalog*.json` di qualunque host (modo `loadtest`)."""
    found = {}
    for name in sorted(os.listdir(fixtures_dir)):
        if name.startswith("catalog") and name.endswith(".json"):
            path = os.path.join(fixtures_dir, name)
            meta = fixture_meta(path)
            found[meta["brand"]] = (path, meta)
    return found


def brand_locales(fixtures_dir: str) -> dict:
    return {brand: meta["locale"] for brand, (_, meta) in _fixtures_by_brand(fixtures_dir).items()}


def brand_fixtures(fixtures_dir: str, brands) -> List[str]:
    """Le fixture dei brand configurati; un brand senza fixture ferma l'avvio."""
    found = _fixtures_by_brand(fixtures_dir)
    missing = [b for b in brands if b not in found]
    if missing:
        raise RuntimeError("VELA_UPSTREAM_MODE=loadtest: nessuna fixture per %s" % ", ".join(missing))
    return [found[b][0] for b in brands]


def build_vela(settings: Settings, engine: Engine,
               notifier: Optional[Notifier] = None) -> Tuple[Vela, Upstream]:
    """Le frasi e le istruzioni MCP promettono gli SMS solo se il notificatore è Twilio: con
    quello finto nessun SMS parte davvero (RF-19, RF-57)."""
    notifier = notifier or build_notifier(settings)
    upstream = build_hofj(settings)
    extractor = None
    if settings.anthropic_api_key:   # RF-03: senza chiave il fallback è spento, senza errori
        from vela.adapters.haiku import HaikuExtractor
        extractor = HaikuExtractor.from_api_key(settings.anthropic_api_key)
    repos = PostgresRepositories(engine, quota_margin=settings.quota_margin,
                                 booking_reserve=settings.booking_reserve,
                                 quota_burst=settings.quota_burst, quota_floor=settings.quota_floor)
    # Sotto carico nessuna attesa dentro la richiesta: i viaggiatori finti interrogano lo stato
    wait = 0 if settings.vela_upstream_mode == LOADTEST else settings.accept_wait_seconds
    vela = Vela(repos, upstream.router, build_payments(settings), DEFAULT_TRAVELER, extractor=extractor,
                sms_enabled=isinstance(notifier, TwilioSms), accept_wait_seconds=wait,
                accept_poll_seconds=settings.accept_poll_seconds)
    return vela, upstream


def build_scheduler(vela: Vela, upstream: Upstream) -> Optional[SyncScheduler]:
    """Il sync del catalogo esiste in live (M10) e in loadtest (dove parte dalle fixture e trova il
    catalogo fresco); in replay il catalogo sono le fixture."""
    if upstream.catalog_source is None:
        return None
    sync = CatalogSync(upstream.catalog_source, vela.repos, upstream.brands, now=vela.now)
    return SyncScheduler(sync, vela.repos, now=vela.now)


def build_worker(vela: Vela, settings: Settings, router: Optional[HofJRouter] = None,
                 notifier: Optional[Notifier] = None) -> Worker:
    """Job d'acquisto, prenotazione, verifica del pagamento e SMS sotto un solo processore (RF-50).
    Senza `router` (test con un client finto) tutti i brand usano `vela.hofj`."""
    router = router or SingleClientRouter(vela.hofj)
    notifier = notifier or build_notifier(settings)
    purchase = PurchaseJob(vela.repos, router, vela.payments, vela._propose, vela.defaults,
                           now=vela.now, max_attempts=settings.purchase_max_attempts,
                           new_id=vela.new_id, poll_seconds=settings.payment_poll_seconds)
    booking = BookingJob(vela.repos, router, now=vela.now,
                         max_attempts=settings.booking_max_attempts, backoff=settings.booking_backoff,
                         new_id=vela.new_id)
    check = PaymentCheckJob(vela.repos, vela.payments, vela.orders, now=vela.now,
                            poll_seconds=settings.payment_poll_seconds)
    sms = SmsJob(vela.repos, notifier, now=vela.now)
    processor = JobProcessor(vela.repos, router, {JobKind.PURCHASE: purchase,
                                                     JobKind.BOOKING: booking,
                                                     JobKind.PAYMENT_CHECK: check,
                                                     JobKind.SMS_LINK: sms,
                                                     JobKind.SMS_CONFIRMED: sms},
                             now=vela.now, lease_seconds=settings.job_lease_seconds)
    return Worker(processor, settings.worker_concurrency)


def realign_catalog(vela: Vela, catalog_loader: CatalogLoader) -> Tuple[int, int]:
    """Decisione M7: se i prodotti attivi del DB non sono quelli della fixture (DB vuoto o cambio
    di ambiente), upsert della fixture e archiviazione degli assenti, mai DELETE. Con lo stesso
    catalogo non tocca nulla: i flag `bookable` di RF-33 sopravvivono ai riavvii.
    Restituisce (caricati, archiviati)."""
    products = catalog_loader()
    wanted = {p.id for p in products if not p.archived}
    stored = {p.id for p in vela.repos.products.list_all() if not p.archived}
    if stored == wanted:
        return 0, 0
    vela.repos.products.upsert_many(products)
    return len(products), vela.repos.products.archive_missing(p.id for p in products)


def bootstrap(vela: Vela, worker: Worker, catalog_loader: Optional[CatalogLoader],
              scheduler: Optional[SyncScheduler] = None) -> dict:
    loaded = archived = 0
    if catalog_loader is not None:                     # replay (M7) e loadtest (M13a): fixture
        loaded, archived = realign_catalog(vela, catalog_loader)
    synced = worker.processor.refresh_quota()          # RF-36: al boot, prima del sync
    if scheduler is not None:                          # live: sync multi-brand (M10, RF-30)
        scheduler.start()
    resumed = vela.orders.resume_bookings()            # RF-27
    worker.start()
    return {"catalog_loaded": loaded, "catalog_archived": archived, "quota_synced": synced,
            "catalog_sync": "scheduled" if scheduler is not None else None, "resumed": resumed}


def create_app(settings: Optional[Settings] = None, vela: Optional[Vela] = None,
               worker: Optional[Worker] = None,
               catalog_loader: Optional[CatalogLoader] = None,
               scheduler: Optional[SyncScheduler] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url) if settings.database_url else None
    router = notifier = None
    if vela is None and engine is not None:
        notifier = build_notifier(settings)            # uno solo: per il worker e per `sms_enabled`
        vela, upstream = build_vela(settings, engine, notifier)
        catalog_loader, router = upstream.catalog_loader, upstream.router
        scheduler = build_scheduler(vela, upstream)
    if vela is not None and worker is None:
        worker = build_worker(vela, settings, router, notifier=notifier)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with app.state.mcp.session_manager.run():
            if app.state.vela is not None:
                app.state.bootstrap = bootstrap(app.state.vela, app.state.worker,
                                                app.state.catalog_loader, app.state.scheduler)
            yield
            if app.state.scheduler is not None:
                app.state.scheduler.stop()
            if app.state.worker is not None:
                app.state.worker.stop(wait=False)

    app = FastAPI(title="Vela", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.vela = vela
    app.state.worker = worker
    app.state.catalog_loader = catalog_loader
    app.state.scheduler = scheduler
    app.state.bootstrap = None
    app.state.mcp = build_mcp(lambda: app.state.vela)
    app.include_router(health_router)
    install_problem_handlers(app)
    app.include_router(rest_router)
    app.include_router(checkout_router)
    if settings.vela_upstream_mode in (REPLAY, LOADTEST):
        app.include_router(replay_router)
    app.router.routes.extend(mcp_routes(app.state.mcp, settings.vela_public_url))
    return app


app = create_app()
