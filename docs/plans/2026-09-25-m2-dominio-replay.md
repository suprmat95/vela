# M2 — Dominio, casi d'uso e modalità replay: piano di esecuzione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Data: 2026-09-25. Branch: `task/m2`. Destinazione di questo file: `docs/plans/2026-09-25-m2-dominio-replay.md`.

**Goal:** i cinque casi d'uso di RF-39 (`create_intent`, `get_proposal`, `reject_proposal`, `accept_proposal`, `get_order_status`) funzionano in Python puro con porte finte e repository in memoria, e con `VELA_UPSTREAM_MODE=replay` contro Postgres: catalogo caricato da `fixtures/catalog.json`, itinerario simulato, pagamento simulato visitando `GET /replay/checkout/{order_id}`, prenotazione finta completata in background con ripresa all'avvio.

**Architecture:** esagonale. `vela/domain` (modelli, parser, chooser, frasi `say`, macchina a stati degli ordini, orchestratore `Vela`) importa solo `vela/ports` e stdlib. `vela/ports` definisce `HofJPort`, `PaymentsPort` e i repository come `Protocol`. `vela/adapters` implementa i repository (in memoria e Postgres con SQLAlchemy Core), gli adapter replay (`ReplayHofJ`, `FakePayments`) e il `BookingRunner` a thread. `vela/surfaces/replay.py` è l'unica superficie HTTP nuova. `vela/app.py` collega tutto e nel lifespan carica la fixture se `products` è vuota e riprende gli ordini `paid_pending_booking`. Orologio e generatore di id sono iniettati: i test sono deterministici.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy Core 2 + psycopg 3, Alembic, `unittest`. Nessuna dipendenza nuova.

**Spec:** `docs/spec.md` (§2, §4.1-4.5, RF-39, RF-42, §5), `docs/roadmap.md` sezione M2, `docs/fixtures.md` (formato della fixture), `docs/api/internal-checkout.md` (forma di itinerario, customer, pax, booking, che le porte imitano). Il design approvato nell'intervista è la sezione "Design" qui sotto.

## Contesto

- Esiste già: `vela/config.py` (`Settings.from_env`, nessuna lettura di `.env`), `vela/adapters/db.py` (`make_engine`, `check_db`, `metadata` condiviso), `vela/surfaces/health.py`, `vela/app.py` (`create_app(settings)`), Alembic con la sola migrazione vuota `0001`, `fixtures/catalog.json` (110 prodotti in lista, 77 dettagli non archiviati, formato in `docs/fixtures.md`).
- La fixture non ha un campo "sport": le categorie sono Vacanze/Accademie/Tornei. 71 dettagli su 77 contengono "padel" in titolo o slug, 6 non contengono né "padel" né "tennis". `minPax`/`maxPax` sono quasi sempre `null` (un prodotto ha `maxPax: 0`). Due prodotti (`323`, `326`) non hanno destinazione né venue. 34 prodotti non hanno hotel nella proiezione `hotels`. Tutte le finestre di `availabilities` hanno `status: "Bookable"`.
- I test Postgres girano solo con `DATABASE_URL` nell'ambiente. L'URL è nel `.env` del repo: il comando è `set -a; . ./.env; set +a; python3 -m unittest ...` in una sola riga di shell, senza mai stampare la variabile o aprire il file con altri strumenti.
- `tests/test_migrations.py` esegue `alembic upgrade head` anche su SQLite: le nuove tabelle usano solo tipi neutri (`JSON`, `Numeric`, `String`, `Date`, `DateTime`, `Boolean`, `Integer`).

## Decisioni prese nell'intervista (da riportare in `docs/decisions.md`, Task 0)

| Decisione | Scelta | Motivo |
|---|---|---|
| Sport del prodotto | Parole chiave `padel`/`tennis` cercate in ordine in titolo, slug, shortDescription, description; nessun segnale = `padel` | La fixture non ha un campo sport; il brand Weebora è padel; nessun prodotto perso |
| Chooser v1 | Esclusioni: archiviati, non prenotabili, rifiutati, sport diverso, date, pax. Ordinamento: area coincidente (città > paese), totale entro budget, prezzo crescente, id | "Solo prezzo" proporrebbe l'Italia a chi chiede la Spagna nella demo M3. Versione semplificata di RF-07; M11 raffina con geohierarchy |
| Date proposte | Il periodo dell'intento diventa un intervallo; il prodotto passa se l'intervallo interseca `[minDate, maxDate]` e ha una finestra di `availabilities` con inizio nel periodo e non nel passato: quella finestra è la data proposta. Senza periodo: prima finestra futura | RF-06 richiede date proposte; senza finestra non c'è data da dire |
| Rifiuto (RF-08 base) | `reject_proposal` salva prodotto e motivo in `rejections`; i criteri non cambiano | L'interpretazione dei motivi è M9. Con l'ordinamento scelto "troppo caro" produce la successiva per prezzo |
| Catalogo in replay | All'avvio, se `products` è vuota, la fixture viene caricata in Postgres (upsert idempotente). Il chooser legge sempre dal repository | Stesso codice in live; M10 sostituisce solo il caricatore |
| Test repository | Solo Postgres, con `DATABASE_URL` dall'ambiente; saltati senza. Un contratto di test condiviso gira sempre sul repository in memoria | RNF-09; l'URL è disponibile nel `.env` |
| Prenotazione post-pagamento | `BookingRunner` con `ThreadPoolExecutor` nel processo; `resume()` nel lifespan per gli ordini `paid_pending_booking`; `InlineRunner` nei test | RF-27 esercitata davvero; M6 riusa il runner dal webhook |
| Default RF-13 | `TravelerDefaults` costante in `vela/config.py` | L'elenco di variabili di spec §6 resta chiuso |
| Lingua di `say` | Solo italiano in M2; il parser riconosce comunque intenti in inglese e salva `language` | Semplifica; i template inglesi arrivano con M9 |
| Dati viaggiatore mancanti | `accept_proposal` risponde con l'elenco dei campi mancanti e una `say`; nessun ordine finché i dati non sono completi | Nessuno stato aggiuntivo oltre RF-25 |
| Proposta "aperta" | `get_proposal` restituisce l'ultima proposta dell'intento non rifiutata, anche se già accettata; una nuova scelta avviene solo dopo un rifiuto | Idempotenza: due `get_proposal` o un `get_proposal` dopo `accept` non producono un secondo prodotto né un secondo ordine |
| Modalità `live` | `create_app` fallisce all'avvio con `RuntimeError("VELA_UPSTREAM_MODE=live non disponibile prima di M5")` | Niente porte finte spacciate per reali |
| Denaro e id | `Decimal` per prezzi e totali (stringa con due decimali in `to_dict`), uuid4 come stringhe per id; codice prenotazione replay `R-` + 6 cifre | Coerente con `Money.amount` stringa di HofJ |

## Global Constraints

- Nessuna dipendenza nuova in `pyproject.toml`; nessuna modifica a `uv.lock`.
- `python3 -m unittest discover -s tests` verde senza servizi esterni e senza `DATABASE_URL`; i test Postgres usano `@unittest.skipUnless(os.environ.get("DATABASE_URL"), "serve DATABASE_URL")`.
- Mai aprire, stampare o loggare `.env`, chiavi o token. Il caricamento dell'ambiente avviene solo con `set -a; . ./.env; set +a` nella stessa riga del comando di test.
- Nessuna superficie HTTP oltre `GET /replay/checkout/{order_id}`, montata solo con `VELA_UPSTREAM_MODE=replay`.
- Nessuna risposta contiene più di un prodotto (RF-10): ogni dict prodotto da `to_dict()` ha al massimo un dizionario con chiave `product_id`.
- `say` senza markdown e senza URL (RF-42): l'URL sta solo in `payment_url`.
- `vela/domain` importa solo `vela.ports`, `vela.domain.*` e stdlib. Mai `fastapi`, `sqlalchemy`, `httpx`.
- Le variabili d'ambiente restano quelle di spec §6: nessuna nuova.
- Commit piccoli, uno per task, messaggio imperativo in inglese come nella storia del repo, con `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Nessun force push.

## Review Focus

1. Intento con sport e mese ma senza numero di persone e senza profilo: una sola domanda ("In quante persone siete?") e nessun intento persistito. Test in Task 4 (`test_missing_pax_asks_one_question`) e Task 8 (`test_question_persists_nothing`).
2. Prodotto con `maxPax: 0` o `minPax: null` (presenti nella fixture): il filtro pax non deve escluderlo. Test in Task 5 (`test_zero_or_null_pax_bounds_do_not_exclude`).
3. `get_proposal` dopo `accept_proposal` sullo stesso intento: stessa proposta, nessun secondo ordine possibile. Test in Task 10 (`test_get_proposal_after_accept_returns_same_proposal`).
4. `GET /replay/checkout/{order_id}` su un ordine sconosciuto → 404; su un ordine già `confirmed` → stessa risposta, nessuna seconda prenotazione, stesso codice. Test in Task 12 (`test_unknown_order_is_404`, `test_second_visit_has_no_effect`).
5. Budget scritto "1.000 euro" o "1,000 euros" deve valere 1000, non 1; "weekend" detto di sabato è il weekend corrente; un mese già passato è dell'anno prossimo. Test in Task 4 (`test_budget_thousands_separator`, `test_weekend_on_saturday_is_today`, `test_past_month_is_next_year`).

---

## Design

### Struttura dei file

```
vela/config.py                  + TravelerDefaults, DEFAULT_TRAVELER
vela/domain/models.py           dataclass del dominio e le risposte dei casi d'uso (con say e to_dict)
vela/domain/catalog.py          Product da una voce della fixture; detect_sport; load_fixture
vela/domain/geo.py              dizionario statico it/en di paesi, regioni, città → Area
vela/domain/intent.py           parse_intent(text, profile, today) → ParseResult(criteria, question)
vela/domain/chooser.py          choose(products, criteria, rejected_ids, today) → Choice | NoChoice
vela/domain/say.py              frasi italiane (RF-42)
vela/domain/orders.py           OrderService: mark_paid, complete_booking, pending_booking_ids
vela/domain/usecases.py         Vela: i 5 casi d'uso; NotFound
vela/ports/hofj.py              HofJPort (Protocol), Itinerary, Customer, Pax, PaymentProof, errori
vela/ports/payments.py          PaymentsPort (Protocol), PaymentLink
vela/ports/repositories.py      i 5 repository (Protocol), Repositories, DuplicateOrder
vela/adapters/repo_memory.py    MemoryRepositories
vela/adapters/schema.py         5 Table sul metadata condiviso
vela/adapters/repo_postgres.py  PostgresRepositories (SQLAlchemy Core)
vela/adapters/hofj_replay.py    ReplayHofJ, FIXTURE_PATH
vela/adapters/stripe_fake.py    FakePayments
vela/adapters/background.py     InlineRunner, BookingRunner
vela/surfaces/replay.py         GET /replay/checkout/{order_id}
vela/app.py                     create_app(settings, vela, runner, catalog_loader), build_vela, bootstrap
alembic/versions/0002_domain_tables.py
alembic/env.py                  + import vela.adapters.schema
tests/support.py                helper condivisi: make_product, FakeHofJ, assert_single_product
tests/test_models.py test_catalog.py test_geo.py test_intent.py test_chooser.py test_say.py
tests/repo_contract.py test_repo_memory.py test_repo_postgres.py
tests/test_usecases.py test_replay_adapters.py test_orders.py test_app_replay.py
tests/test_migrations.py (aggiornato a 0002)
README.md docs/decisions.md
```

### Flusso dei dati

1. `create_intent(text, profile)` → `parse_intent` → domanda (nulla persistito) oppure `Intent` in `intents`.
2. `get_proposal(intent_id)` → ultima proposta non rifiutata se esiste; altrimenti `choose(products.list_all(), criteria, rejections.product_ids_for_intent, today)` → `Proposal` in `proposals`, oppure `NoMatch`.
3. `reject_proposal(proposal_id, reason)` → `Rejection` in `rejections` → punto 2.
4. `accept_proposal(proposal_id, traveler)` → ordine esistente per la proposta? risposta identica. Profilo = profilo dell'intento fuso con `traveler`; mancanti → `MissingTravelerData`. Altrimenti `hofj.create_itinerary` → `set_customer` (dati + `DEFAULT_TRAVELER`) → `get_pax`/`set_pax` preservando `ref_id` → `Order(awaiting_payment)` in `orders` (`DuplicateOrder` → rilettura) → `payments.create_payment_link(order)` → `orders.save` con `payment_url`, `payment_ref` → `AcceptResponse` (`total_differs` se totale ≠ prezzo × pax).
5. `GET /replay/checkout/{order_id}` → `orders_service.mark_paid` (`awaiting_payment` → `paid_pending_booking`, altrimenti no-op) → `runner.submit(order_id)` → `complete_booking` → `hofj.create_booking` → `confirmed` + codice, o `booking_failed` con motivo.
6. Lifespan: `catalog_loader()` in `products` se vuota; `runner.resume()` per ogni `paid_pending_booking`.
7. `get_order_status(order_id)` → stato, codice, `say`.

### Contratto di `to_dict()` (consumato da M3 e M4)

| Risposta | Chiavi |
|---|---|
| `IntentCreated` | `intent_id`, `criteria` (`sport`, `area{kind,name,country_code}`, `period{start,end,label}`, `pax`, `budget`, `language`), `say` |
| `IntentQuestion` | `question`, `say` (uguale a `question`) |
| `ProposalMade` | `proposal_id`, `intent_id`, `product{product_id,title,destination,hotel}`, `start_date`, `end_date`, `pax`, `price_from`, `total_from`, `currency`, `reason`, `replaced`, `say` |
| `NoMatch` | `intent_id`, `failed_criterion`, `say` |
| `AcceptResponse` | `order_id`, `status`, `total`, `currency`, `price_from_total`, `total_differs`, `payment_url`, `say` |
| `MissingTravelerData` | `proposal_id`, `missing` (lista di nomi campo, es. `email`, `participants[1].last_name`), `say` |
| `OrderStatusResponse` | `order_id`, `status`, `booking_code`, `say` |

Importi come stringhe con due decimali (`"800.00"`), date ISO `YYYY-MM-DD`.

---

### Task 0: Piano e decisioni nel repo

**Files:**
- Create: `docs/plans/2026-09-25-m2-dominio-replay.md` (questo file)
- Modify: `docs/decisions.md` (in coda)

- [ ] **Step 1: Aggiungere in coda a `docs/decisions.md`** una sezione `## 2026-09-25 — M2: dominio, casi d'uso e replay` con la frase di origine (`Origine: intervista sulla macro task M2, piano in docs/plans/2026-09-25-m2-dominio-replay.md.`) e la tabella "Decisioni prese nell'intervista" di questo piano, copiata integralmente.

- [ ] **Step 2: Commit**

```bash
git add docs/plans/2026-09-25-m2-dominio-replay.md docs/decisions.md
git commit -m "Add the M2 execution plan and record the interview decisions

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 1: Modelli del dominio, risposte e invariante RF-10

**Files:**
- Create: `vela/domain/models.py`
- Create: `tests/support.py`
- Create: `tests/test_models.py`

**Interfaces:**
- Produces: tutte le dataclass elencate nel codice qui sotto; `money_str(Decimal) -> str`; `criteria_to_dict/criteria_from_dict`; `profile_to_dict/profile_from_dict`; `TravelerProfile.merged_with(other)`; `TravelerProfile.missing_fields(pax) -> list[str]`; `Proposal.total_from`; `count_products(obj) -> int` in `tests/support.py`; `assert_single_product(testcase, d)`.

- [ ] **Step 1: Scrivere i test** in `tests/test_models.py`:

```python
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from vela.domain.models import (Area, Criteria, Order, OrderStatus, Participant, Period,
                                Proposal, TravelerProfile, criteria_from_dict, criteria_to_dict,
                                money_str, profile_from_dict, profile_to_dict)

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)


class MoneyTest(unittest.TestCase):
    def test_two_decimals(self):
        self.assertEqual(money_str(Decimal("800")), "800.00")
        self.assertEqual(money_str(Decimal("812.5")), "812.50")


class CriteriaRoundTripTest(unittest.TestCase):
    def test_round_trip(self):
        c = Criteria(sport="padel", area=Area("country", "Spagna", "ES"),
                     period=Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre"),
                     pax=2, budget=Decimal("800"), language="it")
        self.assertEqual(criteria_from_dict(criteria_to_dict(c)), c)

    def test_empty_round_trip(self):
        c = Criteria()
        d = criteria_to_dict(c)
        self.assertEqual(d, {"sport": None, "area": None, "period": None, "pax": None,
                             "budget": None, "language": "it"})
        self.assertEqual(criteria_from_dict(d), c)


class ProfileTest(unittest.TestCase):
    def test_merge_keeps_known_values_and_takes_new_ones(self):
        base = TravelerProfile(first_name="Anna", email="a@x.it")
        merged = base.merged_with(TravelerProfile(last_name="Rossi", email=None,
                                                  participants=(Participant("Bo", "Bi"),)))
        self.assertEqual(merged.first_name, "Anna")
        self.assertEqual(merged.last_name, "Rossi")
        self.assertEqual(merged.email, "a@x.it")
        self.assertEqual(merged.participants, (Participant("Bo", "Bi"),))

    def test_missing_fields_for_two_pax(self):
        p = TravelerProfile(first_name="Anna", last_name="Rossi", participants=(Participant("Bo"),))
        self.assertEqual(p.missing_fields(2), ["email", "phone", "participants[0].last_name"])

    def test_missing_fields_complete(self):
        p = TravelerProfile("Anna", "Rossi", "a@x.it", "+39", participants=(Participant("Bo", "Bi"),))
        self.assertEqual(p.missing_fields(2), [])
        self.assertEqual(p.missing_fields(1), [])

    def test_round_trip(self):
        p = TravelerProfile("Anna", "Rossi", "a@x.it", "+39", pax=2,
                            participants=(Participant("Bo", "Bi"),))
        self.assertEqual(profile_from_dict(profile_to_dict(p)), p)


class ProposalTest(unittest.TestCase):
    def test_total_from(self):
        p = Proposal("p1", "i1", "181", date(2026, 10, 1), date(2026, 10, 4), 2,
                     Decimal("578"), "EUR", "motivo", NOW)
        self.assertEqual(p.total_from, Decimal("1156"))


class OrderStatusTest(unittest.TestCase):
    def test_values_are_rf25(self):
        self.assertEqual([s.value for s in OrderStatus],
                         ["awaiting_payment", "paid_pending_booking", "confirmed",
                          "booking_failed", "expired"])

    def test_order_is_frozen(self):
        o = Order("o1", "p1", "i1", "181", OrderStatus.AWAITING_PAYMENT, 2, Decimal("578"),
                  Decimal("1156"), "EUR", TravelerProfile(), NOW, NOW)
        with self.assertRaises(Exception):
            o.status = OrderStatus.CONFIRMED
```

E `tests/support.py`:

```python
"""Helper condivisi dai test di M2: prodotti sintetici, porta HofJ finta, invariante RF-10."""
from datetime import date, datetime, timezone
from decimal import Decimal

from vela.domain.models import Availability, Product

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
TODAY = date(2026, 9, 25)


def make_product(pid, price=500, sport="padel", country="ES", destination="Lanzarote",
                 windows=(("2026-10-01", "2026-10-04"),), min_date="2026-09-25",
                 max_date="2026-12-31", min_pax=None, max_pax=None, archived=False,
                 bookable=True, hotel="Hotel Sole", title=None):
    return Product(
        id=str(pid), title=title or "Padel a %s %s" % (destination, pid), slug="p-%s" % pid,
        short_description="", sport=sport, category="Vacanze", destination=destination,
        country=country, venue="Club %s" % pid, hotel=hotel, price=Decimal(str(price)),
        currency="EUR", min_pax=min_pax, max_pax=max_pax,
        min_date=date.fromisoformat(min_date) if min_date else None,
        max_date=date.fromisoformat(max_date) if max_date else None,
        availabilities=tuple(Availability(date.fromisoformat(a), date.fromisoformat(b))
                             for a, b in windows),
        duration_days=4, hofj_updated_at="2026-09-25T10:44:12.537Z", raw={},
        fetched_at=NOW, bookable=bookable, bookable_checked_at=None, archived=archived,
        provider_id="t%s" % pid)


def count_products(obj):
    """Numero di dizionari con chiave `product_id` a qualunque profondità (invariante RF-10)."""
    if isinstance(obj, dict):
        own = 1 if "product_id" in obj else 0
        return own + sum(count_products(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return sum(count_products(v) for v in obj)
    return 0


def assert_single_product(testcase, d):
    testcase.assertLessEqual(count_products(d), 1, "RF-10 violato: %r" % (d,))
    testcase.assertIn("say", d)
    testcase.assertNotIn("http", d["say"])
    testcase.assertNotIn("**", d["say"])
```

- [ ] **Step 2: Eseguire** `python3 -m unittest tests.test_models -v` → `ModuleNotFoundError: vela.domain.models`.

- [ ] **Step 3: Scrivere `vela/domain/models.py`**:

```python
"""Modelli del dominio di Vela (spec §2, RF-05, RF-06, RF-25) e risposte dei casi d'uso (RF-39, RF-42).

Tutto è dataclass immutabile e senza dipendenze esterne. Le risposte espongono `to_dict()`:
il contratto che le superfici REST (M4) e MCP (M3) serializzano. Nessuna risposta contiene
mai più di un prodotto (RF-10).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


def money_str(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


# --- intento -----------------------------------------------------------------

@dataclass(frozen=True)
class Area:
    kind: str           # "country" | "region" | "city"
    name: str           # nome canonico italiano, es. "Spagna", "Lanzarote"
    country_code: str   # ISO 3166-1 alpha-2


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    label: str          # testo che lo ha generato, es. "ottobre", "weekend"


@dataclass(frozen=True)
class Criteria:
    sport: Optional[str] = None
    area: Optional[Area] = None
    period: Optional[Period] = None
    pax: Optional[int] = None
    budget: Optional[Decimal] = None
    language: str = "it"


def criteria_to_dict(c: Criteria) -> dict:
    return {
        "sport": c.sport,
        "area": None if c.area is None else {"kind": c.area.kind, "name": c.area.name,
                                             "country_code": c.area.country_code},
        "period": None if c.period is None else {"start": c.period.start.isoformat(),
                                                 "end": c.period.end.isoformat(),
                                                 "label": c.period.label},
        "pax": c.pax,
        "budget": None if c.budget is None else money_str(c.budget),
        "language": c.language,
    }


def criteria_from_dict(d: dict) -> Criteria:
    area = d.get("area")
    period = d.get("period")
    budget = d.get("budget")
    return Criteria(
        sport=d.get("sport"),
        area=None if area is None else Area(area["kind"], area["name"], area["country_code"]),
        period=None if period is None else Period(date.fromisoformat(period["start"]),
                                                  date.fromisoformat(period["end"]),
                                                  period["label"]),
        pax=d.get("pax"),
        budget=None if budget is None else Decimal(budget),
        language=d.get("language") or "it",
    )


@dataclass(frozen=True)
class Participant:
    first_name: Optional[str] = None
    last_name: Optional[str] = None


@dataclass(frozen=True)
class TravelerProfile:
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    pax: Optional[int] = None
    participants: tuple = ()   # tuple[Participant, ...]

    def merged_with(self, other: "TravelerProfile") -> "TravelerProfile":
        """I valori non nulli di `other` vincono; i partecipanti di `other` se non vuoti."""
        return TravelerProfile(
            first_name=other.first_name or self.first_name,
            last_name=other.last_name or self.last_name,
            email=other.email or self.email,
            phone=other.phone or self.phone,
            pax=other.pax or self.pax,
            participants=other.participants or self.participants,
        )

    def missing_fields(self, pax: int) -> list:
        """Campi di RF-12 ancora mancanti per `pax` persone: viaggiatore principale completo,
        nome e cognome di ogni altro partecipante."""
        missing = [name for name in ("first_name", "last_name", "email", "phone")
                   if not getattr(self, name)]
        for i in range(max(pax - 1, 0)):
            p = self.participants[i] if i < len(self.participants) else Participant()
            if not p.first_name:
                missing.append("participants[%d].first_name" % i)
            if not p.last_name:
                missing.append("participants[%d].last_name" % i)
        return missing


def profile_to_dict(p: TravelerProfile) -> dict:
    return {"first_name": p.first_name, "last_name": p.last_name, "email": p.email,
            "phone": p.phone, "pax": p.pax,
            "participants": [{"first_name": x.first_name, "last_name": x.last_name}
                             for x in p.participants]}


def profile_from_dict(d: Optional[dict]) -> TravelerProfile:
    d = d or {}
    return TravelerProfile(
        first_name=d.get("first_name"), last_name=d.get("last_name"), email=d.get("email"),
        phone=d.get("phone"), pax=d.get("pax"),
        participants=tuple(Participant(x.get("first_name"), x.get("last_name"))
                           for x in d.get("participants") or []))


@dataclass(frozen=True)
class Intent:
    id: str
    text: str
    criteria: Criteria
    profile: TravelerProfile
    created_at: datetime


# --- catalogo ----------------------------------------------------------------

@dataclass(frozen=True)
class Availability:
    start: date
    end: date


@dataclass(frozen=True)
class Product:
    id: str
    title: str
    slug: str
    short_description: str
    sport: str
    category: Optional[str]
    destination: Optional[str]
    country: Optional[str]
    venue: Optional[str]
    hotel: Optional[str]
    price: Decimal
    currency: str
    min_pax: Optional[int]
    max_pax: Optional[int]
    min_date: Optional[date]
    max_date: Optional[date]
    availabilities: tuple      # tuple[Availability, ...] ordinate per inizio
    duration_days: Optional[int]
    hofj_updated_at: Optional[str]
    raw: dict
    fetched_at: datetime
    bookable: bool = True
    bookable_checked_at: Optional[datetime] = None
    archived: bool = False
    provider_id: Optional[str] = None


# --- proposta, ordine, rifiuto -------------------------------------------------

@dataclass(frozen=True)
class Proposal:
    id: str
    intent_id: str
    product_id: str
    start_date: date
    end_date: date
    pax: int
    price_from: Decimal        # per persona
    currency: str
    reason: str
    created_at: datetime

    @property
    def total_from(self) -> Decimal:
        return self.price_from * self.pax


class OrderStatus(str, Enum):
    AWAITING_PAYMENT = "awaiting_payment"
    PAID_PENDING_BOOKING = "paid_pending_booking"
    CONFIRMED = "confirmed"
    BOOKING_FAILED = "booking_failed"
    EXPIRED = "expired"


@dataclass(frozen=True)
class Order:
    id: str
    proposal_id: str
    intent_id: str
    product_id: str
    status: OrderStatus
    pax: int
    price_from: Decimal        # per persona, dalla proposta
    total: Decimal             # totale reale dell'itinerario
    currency: str
    traveler: TravelerProfile
    created_at: datetime
    updated_at: datetime
    itinerary_id: Optional[str] = None
    payment_url: Optional[str] = None
    payment_ref: Optional[str] = None
    booking_code: Optional[str] = None
    failure_reason: Optional[str] = None
    paid_at: Optional[datetime] = None


@dataclass(frozen=True)
class Rejection:
    intent_id: str
    proposal_id: str
    product_id: str
    reason: str
    created_at: datetime


# --- risposte dei casi d'uso (RF-39, RF-42) -----------------------------------

@dataclass(frozen=True)
class ProductSummary:
    product_id: str
    title: str
    destination: Optional[str]
    hotel: Optional[str]

    def to_dict(self) -> dict:
        return {"product_id": self.product_id, "title": self.title,
                "destination": self.destination, "hotel": self.hotel}


@dataclass(frozen=True)
class IntentCreated:
    intent_id: str
    criteria: Criteria
    say: str

    def to_dict(self) -> dict:
        return {"intent_id": self.intent_id, "criteria": criteria_to_dict(self.criteria),
                "say": self.say}


@dataclass(frozen=True)
class IntentQuestion:
    question: str
    say: str

    def to_dict(self) -> dict:
        return {"question": self.question, "say": self.say}


@dataclass(frozen=True)
class ProposalMade:
    proposal: Proposal
    product: ProductSummary
    say: str
    replaced: bool = False

    def to_dict(self) -> dict:
        p = self.proposal
        return {"proposal_id": p.id, "intent_id": p.intent_id, "product": self.product.to_dict(),
                "start_date": p.start_date.isoformat(), "end_date": p.end_date.isoformat(),
                "pax": p.pax, "price_from": money_str(p.price_from),
                "total_from": money_str(p.total_from), "currency": p.currency,
                "reason": p.reason, "replaced": self.replaced, "say": self.say}


@dataclass(frozen=True)
class NoMatch:
    intent_id: str
    failed_criterion: str
    say: str

    def to_dict(self) -> dict:
        return {"intent_id": self.intent_id, "failed_criterion": self.failed_criterion,
                "say": self.say}


@dataclass(frozen=True)
class AcceptResponse:
    order_id: str
    status: OrderStatus
    total: Decimal
    currency: str
    price_from_total: Decimal
    total_differs: bool
    payment_url: str
    say: str

    def to_dict(self) -> dict:
        return {"order_id": self.order_id, "status": self.status.value,
                "total": money_str(self.total), "currency": self.currency,
                "price_from_total": money_str(self.price_from_total),
                "total_differs": self.total_differs, "payment_url": self.payment_url,
                "say": self.say}


@dataclass(frozen=True)
class MissingTravelerData:
    proposal_id: str
    missing: tuple
    say: str

    def to_dict(self) -> dict:
        return {"proposal_id": self.proposal_id, "missing": list(self.missing), "say": self.say}


@dataclass(frozen=True)
class OrderStatusResponse:
    order_id: str
    status: OrderStatus
    booking_code: Optional[str]
    say: str

    def to_dict(self) -> dict:
        return {"order_id": self.order_id, "status": self.status.value,
                "booking_code": self.booking_code, "say": self.say}

```

- [ ] **Step 4: Eseguire** `python3 -m unittest tests.test_models -v` → tutti PASS.

- [ ] **Step 5: Commit**

```bash
git add vela/domain/models.py tests/support.py tests/test_models.py
git commit -m "Add the domain models and use case responses

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Catalogo: `Product` dalla fixture e rilevamento dello sport

**Files:**
- Create: `vela/domain/catalog.py`
- Create: `tests/test_catalog.py`

**Interfaces:**
- Consumes: `Product`, `Availability` (Task 1); formato di `fixtures/catalog.json` (`docs/fixtures.md`).
- Produces: `detect_sport(*texts) -> str`; `product_from_entry(entry: dict, archived: bool, raw: dict, fetched_at: datetime) -> Product`; `load_fixture(path, fetched_at=None) -> list[Product]` (110 prodotti: 77 dai dettagli, 33 archiviati dalla lista).

- [ ] **Step 1: Scrivere i test** in `tests/test_catalog.py`:

```python
import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from vela.domain.catalog import detect_sport, load_fixture, product_from_entry

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "catalog.json")
NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)

ENTRY = {
    "id": "181", "title": "Magnifico Padel a Lanzarote ", "slug": "magnifico-padel-a-lanzarote",
    "shortDescription": "Weekend di lusso", "price": 578, "currency": "EUR",
    "minPax": None, "maxPax": None, "minDate": "2026-09-25", "maxDate": "2026-12-29",
    "availabilities": [{"status": "Bookable", "startDate": "2026-10-08", "endDate": "2026-10-11"},
                       {"status": "Bookable", "startDate": "2026-10-01", "endDate": "2026-10-04"}],
    "defaultDurationInDays": 4, "updatedAt": "2026-09-25T10:44:12.537Z",
    "category": {"id": "8", "name": "Vacanze", "slug": "vacanze"},
    "venue": {"id": "492", "title": "TocaHub Lanzarote"},
    "destination": {"id": "284", "title": "Lanzarote", "country": "ES"},
    "hotels": {"data": [{"id": 204, "attributes": {"name": "THB Lanzarote Beach "}}]},
}


class DetectSportTest(unittest.TestCase):
    def test_padel_in_title(self):
        self.assertEqual(detect_sport("Magnifico Padel a Lanzarote", "slug"), "padel")

    def test_tennis_in_description_only(self):
        self.assertEqual(detect_sport("TODA Sinalunga", "toda-sinalunga", "", "Tre giorni di tennis"),
                         "tennis")

    def test_first_text_wins(self):
        self.assertEqual(detect_sport("Padel camp", "", "", "vicino ai campi da tennis"), "padel")

    def test_unknown_is_padel(self):
        self.assertEqual(detect_sport("Champagne weekend", "rcr-premium", None, None), "padel")


class ProductFromEntryTest(unittest.TestCase):
    def test_maps_fields(self):
        p = product_from_entry(ENTRY, archived=False, raw={"k": 1}, fetched_at=NOW)
        self.assertEqual(p.id, "181")
        self.assertEqual(p.title, "Magnifico Padel a Lanzarote")
        self.assertEqual(p.sport, "padel")
        self.assertEqual(p.category, "Vacanze")
        self.assertEqual((p.destination, p.country, p.venue), ("Lanzarote", "ES", "TocaHub Lanzarote"))
        self.assertEqual(p.hotel, "THB Lanzarote Beach")
        self.assertEqual(p.price, Decimal("578"))
        self.assertEqual((p.min_date, p.max_date), (date(2026, 9, 25), date(2026, 12, 29)))
        self.assertEqual([a.start for a in p.availabilities], [date(2026, 10, 1), date(2026, 10, 8)])
        self.assertEqual(p.duration_days, 4)
        self.assertEqual(p.raw, {"k": 1})
        self.assertTrue(p.bookable)
        self.assertFalse(p.archived)

    def test_missing_destination_venue_hotel(self):
        entry = dict(ENTRY, destination=None, venue=None, hotels={"data": []}, minPax=2, maxPax=0)
        p = product_from_entry(entry, archived=True, raw={}, fetched_at=NOW)
        self.assertIsNone(p.destination)
        self.assertIsNone(p.country)
        self.assertIsNone(p.venue)
        self.assertIsNone(p.hotel)
        self.assertEqual((p.min_pax, p.max_pax), (2, 0))
        self.assertTrue(p.archived)

    def test_list_item_without_detail_fields(self):
        entry = {k: v for k, v in ENTRY.items() if k not in ("category", "venue", "destination", "hotels")}
        p = product_from_entry(entry, archived=True, raw=entry, fetched_at=NOW)
        self.assertIsNone(p.category)
        self.assertEqual(p.sport, "padel")


@unittest.skipUnless(os.path.exists(FIXTURE), "fixture assente")
class LoadFixtureTest(unittest.TestCase):
    def test_loads_all_products_with_archived_flag(self):
        products = load_fixture(FIXTURE, fetched_at=NOW)
        self.assertEqual(len(products), 110)
        active = [p for p in products if not p.archived]
        self.assertEqual(len(active), 77)
        self.assertTrue(all(p.raw for p in active))
        self.assertTrue(all(p.sport in ("padel", "tennis") for p in products))
        self.assertTrue(all(p.fetched_at == NOW for p in products))
        by_id = {p.id: p for p in products}
        self.assertEqual(by_id["181"].hotel, "THB Lanzarote Beach")
```

- [ ] **Step 2: Eseguire** `python3 -m unittest tests.test_catalog -v` → `ModuleNotFoundError`.

- [ ] **Step 3: Scrivere `vela/domain/catalog.py`**:

```python
"""Dal formato della fixture (`docs/fixtures.md`) ai `Product` del dominio (RF-28).

Lo sport non è un campo dell'API: si cerca `padel`/`tennis` in titolo, slug, descrizione breve
e descrizione, in quest'ordine; senza segnale il prodotto è padel (decisione M2).
"""
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional

from vela.domain.models import Availability, Product

SPORTS = ("padel", "tennis")


def detect_sport(*texts: Optional[str]) -> str:
    for text in texts:
        low = (text or "").lower()
        for sport in SPORTS:
            if sport in low:
                return sport
    return "padel"


def _date(value: Optional[str]) -> Optional[date]:
    return date.fromisoformat(value[:10]) if value else None


def _hotel_name(entry: dict) -> Optional[str]:
    hotels = entry.get("hotels") or {}
    data = hotels.get("data") or []
    if not data:
        return None
    name = (data[0].get("attributes") or {}).get("name")
    return name.strip() if name else None


def product_from_entry(entry: dict, archived: bool, raw: dict, fetched_at: datetime) -> Product:
    category = entry.get("category") or {}
    venue = entry.get("venue") or {}
    destination = entry.get("destination") or {}
    windows = sorted(
        (Availability(_date(a["startDate"]), _date(a["endDate"])) for a in entry.get("availabilities") or []),
        key=lambda a: (a.start, a.end))
    return Product(
        id=str(entry["id"]),
        title=(entry.get("title") or "").strip(),
        slug=entry.get("slug") or "",
        short_description=(entry.get("shortDescription") or "").strip(),
        sport=detect_sport(entry.get("title"), entry.get("slug"), entry.get("shortDescription"),
                           entry.get("description")),
        category=category.get("name") or None,
        destination=(destination.get("title") or "").strip() or None,
        country=destination.get("country") or None,
        venue=(venue.get("title") or "").strip() or None,
        hotel=_hotel_name(entry),
        price=Decimal(str(entry["price"])),
        currency=entry.get("currency") or "EUR",
        min_pax=entry.get("minPax"),
        max_pax=entry.get("maxPax"),
        min_date=_date(entry.get("minDate")),
        max_date=_date(entry.get("maxDate")),
        availabilities=tuple(windows),
        duration_days=entry.get("defaultDurationInDays"),
        hofj_updated_at=entry.get("updatedAt"),
        raw=raw,
        fetched_at=fetched_at,
        bookable=True,
        bookable_checked_at=None,
        archived=archived,
        provider_id=entry.get("providerID"),
    )


def load_fixture(path, fetched_at: Optional[datetime] = None) -> list:
    """Tutti i prodotti della fixture: i non archiviati dal dettaglio `details[id].catalog`
    (con `raw`), gli archiviati dall'item di lista (senza dettaglio)."""
    fetched_at = fetched_at or datetime.now(timezone.utc)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    details = data.get("details") or {}
    products = []
    for item in data.get("products") or []:
        pid = str(item["id"])
        detail = details.get(pid)
        if detail and not item.get("archived"):
            products.append(product_from_entry(detail["catalog"], archived=False,
                                               raw=detail.get("raw") or {}, fetched_at=fetched_at))
        else:
            products.append(product_from_entry(item, archived=bool(item.get("archived")),
                                               raw=item, fetched_at=fetched_at))
    return products
```

- [ ] **Step 4: Eseguire** `python3 -m unittest tests.test_catalog -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add vela/domain/catalog.py tests/test_catalog.py
git commit -m "Build domain products from the catalog fixture

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Dizionario geografico it/en

**Files:**
- Create: `vela/domain/geo.py`
- Create: `tests/test_geo.py`

**Interfaces:**
- Consumes: `Area` (Task 1).
- Produces: `COUNTRIES: dict[str, str]` (codice → nome italiano); `find_area(text: str) -> Area | None` (alias più lungo vince, confini di parola, senza distinzione di maiuscole); `area_of_destination(title, country_code) -> Area | None`.

- [ ] **Step 1: Scrivere i test** in `tests/test_geo.py`:

```python
import json
import os
import unittest

from vela.domain.geo import COUNTRIES, area_of_destination, find_area
from vela.domain.models import Area

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "catalog.json")


class FindAreaTest(unittest.TestCase):
    def test_country_it_and_en(self):
        self.assertEqual(find_area("un weekend di padel in Spagna"), Area("country", "Spagna", "ES"))
        self.assertEqual(find_area("a padel weekend in Spain"), Area("country", "Spagna", "ES"))

    def test_city_alias(self):
        self.assertEqual(find_area("padel a Barcelona"), Area("city", "Barcellona", "ES"))
        self.assertEqual(find_area("tennis in Tuscany"), Area("region", "Toscana", "IT"))

    def test_longest_alias_wins(self):
        self.assertEqual(find_area("Palma de Mallorca in ottobre").name, "Palma de Mallorca")

    def test_place_beats_country(self):
        self.assertEqual(find_area("Lanzarote, Spagna").name, "Lanzarote")

    def test_word_boundaries(self):
        self.assertIsNone(find_area("baliamo tutta la notte"))
        self.assertIsNone(find_area("nessun posto"))

    def test_case_insensitive(self):
        self.assertEqual(find_area("SPAGNA").country_code, "ES")


class AreaOfDestinationTest(unittest.TestCase):
    def test_known_title(self):
        self.assertEqual(area_of_destination("Maiorca", "ES"), Area("region", "Maiorca", "ES"))

    def test_unknown_title_falls_back_to_country(self):
        self.assertEqual(area_of_destination("Weebora", "IT"), Area("country", "Italia", "IT"))

    def test_nothing(self):
        self.assertIsNone(area_of_destination(None, None))


@unittest.skipUnless(os.path.exists(FIXTURE), "fixture assente")
class FixtureCoverageTest(unittest.TestCase):
    SKIP = {"Weebora"}   # destinazione fittizia del brand, senza luogo

    def test_every_fixture_destination_resolves(self):
        with open(FIXTURE, encoding="utf-8") as fh:
            data = json.load(fh)
        for detail in data["details"].values():
            dest = detail["catalog"].get("destination") or {}
            title, country = dest.get("title"), dest.get("country")
            if not title or title in self.SKIP:
                continue
            area = find_area(title)
            self.assertIsNotNone(area, "destinazione non in geo.py: %r" % title)
            self.assertEqual(area.country_code, country, title)
            self.assertIn(country, COUNTRIES)
```

- [ ] **Step 2: Eseguire** `python3 -m unittest tests.test_geo -v` → `ModuleNotFoundError`.

- [ ] **Step 3: Scrivere `vela/domain/geo.py`**:

```python
"""Dizionario geografico statico it/en (RF-02, parser minimo M2).

Contiene i paesi e le destinazioni presenti in `fixtures/catalog.json` con alias in italiano e
inglese. `tests/test_geo.py` verifica che ogni destinazione della fixture sia coperta: quando
la fixture cambia, il test dice quali voci aggiungere. M9 estende con `geohierarchy`.
"""
import re
from typing import Optional

from vela.domain.models import Area

COUNTRIES = {
    "ES": "Spagna", "IT": "Italia", "FR": "Francia", "GR": "Grecia", "MA": "Marocco",
    "EG": "Egitto", "CY": "Cipro", "TN": "Tunisia", "ID": "Indonesia", "TH": "Thailandia",
    "TZ": "Tanzania", "AR": "Argentina",
}

# alias → codice paese
COUNTRY_ALIASES = {
    "spagna": "ES", "spain": "ES", "italia": "IT", "italy": "IT", "francia": "FR", "france": "FR",
    "grecia": "GR", "greece": "GR", "marocco": "MA", "morocco": "MA", "egitto": "EG", "egypt": "EG",
    "cipro": "CY", "cyprus": "CY", "tunisia": "TN", "indonesia": "ID", "thailandia": "TH",
    "thailand": "TH", "tanzania": "TZ", "argentina": "AR",
}

# (nome canonico, tipo, paese, alias aggiuntivi...)
PLACES = [
    ("Lanzarote", "city", "ES"), ("Alicante", "city", "ES"), ("Bali", "region", "ID"),
    ("Barcellona", "city", "ES", "barcelona"), ("Buenos Aires", "city", "AR"),
    ("Dénia", "city", "ES", "denia"), ("Essaouira", "city", "MA"), ("Estepona", "city", "ES"),
    ("Firenze", "city", "IT", "florence"), ("Fuerteventura", "region", "ES"),
    ("Ibiza", "region", "ES"), ("Lloret de Mar", "city", "ES", "costa brava"),
    ("Lombok", "region", "ID"), ("Madrid", "city", "ES"),
    ("Maiorca", "region", "ES", "mallorca", "majorca"), ("Malaga", "city", "ES", "málaga"),
    ("Marrakech", "city", "MA", "marrakesh"), ("Marsa Alam", "city", "EG"),
    ("Milano", "city", "IT", "milan"), ("Minorca", "region", "ES", "menorca"),
    ("Mykonos", "region", "GR"), ("Nicosia", "city", "CY"),
    ("Palma de Mallorca", "city", "ES", "palma"), ("Phuket", "region", "TH"),
    ("Pietrasanta", "city", "IT"), ("Reims", "city", "FR"), ("Riccione", "city", "IT"),
    ("Sardegna", "region", "IT", "sardinia"), ("Siviglia", "city", "ES", "seville", "sevilla"),
    ("Sousse", "city", "TN"), ("Tarragona", "city", "ES"), ("Tenerife", "region", "ES"),
    ("Torre del Mar", "city", "ES"), ("Toscana", "region", "IT", "tuscany"),
    ("Valencia", "city", "ES"), ("Venezia", "city", "IT", "venice"),
    ("Cap d'Agde", "city", "FR", "cap d agde"), ("Zante", "region", "GR", "zakynthos"),
    ("Zanzibar", "region", "TZ"), ("Canarie", "region", "ES", "canary islands", "canaries"),
    ("Baleari", "region", "ES", "balearic islands", "baleares"),
]

_WORD = "a-zà-ÿ'"


def _build_index():
    index = []   # (alias, Area)
    for place in PLACES:
        name, kind, country = place[0], place[1], place[2]
        area = Area(kind, name, country)
        for alias in (name.lower(),) + tuple(a.lower() for a in place[3:]):
            index.append((alias, area))
    for alias, code in COUNTRY_ALIASES.items():
        index.append((alias, Area("country", COUNTRIES[code], code)))
    # gli alias più lunghi prima: "palma de mallorca" batte "mallorca"; luoghi prima dei paesi a pari lunghezza
    index.sort(key=lambda pair: (-len(pair[0]), pair[1].kind == "country"))
    return [(re.compile(r"(?<![%s])%s(?![%s])" % (_WORD, re.escape(alias), _WORD)), area)
            for alias, area in index]


_INDEX = _build_index()


def find_area(text: Optional[str]) -> Optional[Area]:
    low = (text or "").lower()
    for pattern, area in _INDEX:
        if pattern.search(low):
            return area
    return None


def area_of_destination(title: Optional[str], country_code: Optional[str]) -> Optional[Area]:
    found = find_area(title)
    if found is not None:
        return found
    if country_code in COUNTRIES:
        return Area("country", COUNTRIES[country_code], country_code)
    return None
```

- [ ] **Step 4: Eseguire** `python3 -m unittest tests.test_geo -v` → PASS. Se `FixtureCoverageTest` segnala una destinazione mancante, aggiungerla a `PLACES` con il paese indicato dalla fixture.

- [ ] **Step 5: Commit**

```bash
git add vela/domain/geo.py tests/test_geo.py
git commit -m "Add the static it/en gazetteer built from the fixture destinations

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Parser minimo it/en (RF-02, RF-04)

**Files:**
- Create: `vela/domain/intent.py`
- Create: `tests/test_intent.py`

**Interfaces:**
- Consumes: `Criteria`, `Period`, `TravelerProfile` (Task 1); `geo.find_area` (Task 3).
- Produces: `ParseResult(criteria: Criteria, question: str | None)`; `parse_intent(text, profile=None, today=None) -> ParseResult`; `parse_sport`, `parse_period(text, today)`, `parse_pax`, `parse_budget`, `detect_language`; costanti `QUESTION_SPORT_OR_PERIOD`, `QUESTION_PAX`.

- [ ] **Step 1: Scrivere i test** in `tests/test_intent.py`:

```python
import unittest
from datetime import date
from decimal import Decimal

from vela.domain.intent import (QUESTION_PAX, QUESTION_SPORT_OR_PERIOD, detect_language,
                                parse_budget, parse_intent, parse_pax, parse_period)
from vela.domain.models import Area, Period, TravelerProfile

TODAY = date(2026, 9, 25)   # venerdì

# testo → (sport, codice paese, (start, end), pax, budget, lingua)
TABLE = [
    ("un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro",
     ("padel", "ES", (date(2026, 10, 1), date(2026, 10, 31)), 2, Decimal("800"), "it")),
    ("a padel weekend in Spain in October, we are two, max 800 euros",
     ("padel", "ES", (date(2026, 10, 1), date(2026, 10, 31)), 2, Decimal("800"), "en")),
    ("vorrei fare tennis in Toscana a novembre per 4 persone",
     ("tennis", "IT", (date(2026, 11, 1), date(2026, 11, 30)), 4, None, "it")),
    ("padel a Lanzarote il 10 ottobre, siamo in 3, budget 1.000 euro",
     ("padel", "ES", (date(2026, 10, 10), date(2026, 10, 10)), 3, Decimal("1000"), "it")),
    ("tennis camp in Mallorca next weekend for 2 people under 1,000 euros",
     ("tennis", "ES", (date(2026, 9, 26), date(2026, 9, 27)), 2, Decimal("1000"), "en")),
    ("padel in estate a Ibiza, 2 persone",
     ("padel", "ES", (date(2027, 6, 1), date(2027, 8, 31)), 2, None, "it")),
    ("un viaggio di padel a marzo, siamo in quattro",
     ("padel", None, (date(2027, 3, 1), date(2027, 3, 31)), 4, None, "it")),
    ("tennis in Italia il 2026-12-05 per due",
     ("tennis", "IT", (date(2026, 12, 5), date(2026, 12, 5)), 2, None, "it")),
    ("padel weekend, x2, 600€",
     ("padel", None, (date(2026, 9, 26), date(2026, 9, 27)), 2, Decimal("600"), "it")),
    ("we want a tennis holiday in winter, three of us, no more than 2000 euros",
     ("tennis", None, (date(2026, 12, 1), date(2027, 2, 28)), 3, Decimal("2000"), "en")),
]


class TableTest(unittest.TestCase):
    def test_table(self):
        for text, (sport, country, period, pax, budget, lang) in TABLE:
            with self.subTest(text=text):
                r = parse_intent(text, today=TODAY)
                c = r.criteria
                self.assertEqual(c.sport, sport)
                self.assertEqual(c.area.country_code if c.area else None, country)
                self.assertEqual((c.period.start, c.period.end) if c.period else None, period)
                self.assertEqual(c.pax, pax)
                self.assertEqual(c.budget, budget)
                self.assertEqual(c.language, lang)
                self.assertIsNone(r.question)


class PeriodTest(unittest.TestCase):
    def test_current_month_is_this_year(self):
        p = parse_period("a settembre", TODAY)
        self.assertEqual((p.start, p.end, p.label), (date(2026, 9, 1), date(2026, 9, 30), "settembre"))

    def test_past_month_is_next_year(self):
        p = parse_period("ad agosto", TODAY)
        self.assertEqual(p.start, date(2027, 8, 1))

    def test_weekend_on_saturday_is_today(self):
        p = parse_period("questo weekend", date(2026, 9, 26))
        self.assertEqual((p.start, p.end), (date(2026, 9, 26), date(2026, 9, 27)))

    def test_weekend_on_sunday_is_next(self):
        p = parse_period("fine settimana", date(2026, 9, 27))
        self.assertEqual((p.start, p.end), (date(2026, 10, 3), date(2026, 10, 4)))

    def test_month_beats_weekend(self):
        p = parse_period("un weekend a ottobre", TODAY)
        self.assertEqual(p.label, "ottobre")

    def test_day_month_slash(self):
        self.assertEqual(parse_period("il 12/10", TODAY).start, date(2026, 10, 12))
        self.assertEqual(parse_period("il 12/03", TODAY).start, date(2027, 3, 12))

    def test_winter_in_january(self):
        p = parse_period("in inverno", date(2027, 1, 10))
        self.assertEqual((p.start, p.end), (date(2026, 12, 1), date(2027, 2, 28)))

    def test_none(self):
        self.assertIsNone(parse_period("padel in Spagna", TODAY))


class PaxTest(unittest.TestCase):
    def test_forms(self):
        for text, pax in [("siamo in due", 2), ("we are 3", 3), ("per due", 2), ("for four", 4),
                          ("2 persone", 2), ("three people", 3), ("x4", 4), ("in 2", 2),
                          ("siamo in tre amici", 3), ("we're 5", 5)]:
            with self.subTest(text=text):
                self.assertEqual(parse_pax(text), pax)

    def test_not_a_pax(self):
        self.assertIsNone(parse_pax("for 800 euro"))
        self.assertIsNone(parse_pax("per ottobre"))
        self.assertIsNone(parse_pax("padel in Spagna"))


class BudgetTest(unittest.TestCase):
    def test_forms(self):
        for text, budget in [("massimo 800 euro", 800), ("max 800", 800), ("budget di 950 euro", 950),
                             ("under 1000", 1000), ("up to 700 euros", 700), ("€ 650", 650),
                             ("650€", 650), ("fino a 1.200 euro", 1200), ("812,50 euro", Decimal("812.50")),
                             ("not more than 1,500 euros", 1500), ("meno di 900 euro", 900)]:
            with self.subTest(text=text):
                self.assertEqual(parse_budget(text), Decimal(budget))

    def test_budget_thousands_separator(self):
        self.assertEqual(parse_budget("1.000 euro"), Decimal("1000"))
        self.assertEqual(parse_budget("1,000 euros"), Decimal("1000"))

    def test_none(self):
        self.assertIsNone(parse_budget("siamo in 2 a ottobre"))


class LanguageTest(unittest.TestCase):
    def test_detect(self):
        self.assertEqual(detect_language("un weekend di padel, siamo in due"), "it")
        self.assertEqual(detect_language("a weekend of padel for the two of us"), "en")
        self.assertEqual(detect_language("padel"), "it")


class QuestionTest(unittest.TestCase):
    def test_missing_sport_and_period_asks_sport_or_period(self):
        r = parse_intent("un viaggio in Spagna per due", today=TODAY)
        self.assertEqual(r.question, QUESTION_SPORT_OR_PERIOD)

    def test_missing_pax_asks_one_question(self):
        r = parse_intent("padel a ottobre", today=TODAY)
        self.assertEqual(r.question, QUESTION_PAX)
        self.assertEqual(r.criteria.sport, "padel")

    def test_pax_from_profile(self):
        r = parse_intent("padel a ottobre", profile=TravelerProfile(pax=2), today=TODAY)
        self.assertIsNone(r.question)
        self.assertEqual(r.criteria.pax, 2)

    def test_text_pax_beats_profile(self):
        r = parse_intent("padel a ottobre, siamo in 3", profile=TravelerProfile(pax=2), today=TODAY)
        self.assertEqual(r.criteria.pax, 3)

    def test_only_period_is_enough(self):
        r = parse_intent("qualcosa a ottobre per due", today=TODAY)
        self.assertIsNone(r.question)
        self.assertIsNone(r.criteria.sport)

    def test_area_and_period_objects(self):
        c = parse_intent("padel in Spagna a ottobre per due", today=TODAY).criteria
        self.assertEqual(c.area, Area("country", "Spagna", "ES"))
        self.assertEqual(c.period, Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre"))
```

- [ ] **Step 2: Eseguire** `python3 -m unittest tests.test_intent -v` → `ModuleNotFoundError`.

- [ ] **Step 3: Scrivere `vela/domain/intent.py`**:

```python
"""Parser deterministico minimo degli intenti, italiano e inglese (RF-02, RF-04; completo in M9).

Estrae sport, area (dizionario `geo`), periodo, numero di persone, budget e lingua. Se manca
sia lo sport che il periodo, oppure il numero di persone (e il profilo non lo dà), produce una
sola domanda per l'agente. `today` è iniettato per rendere i periodi deterministici.
"""
import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from vela.domain import geo
from vela.domain.models import Criteria, Period, TravelerProfile

QUESTION_SPORT_OR_PERIOD = "Che sport ti interessa, padel o tennis, e in che periodo vuoi partire?"
QUESTION_PAX = "In quante persone siete?"

MONTHS = {
    "gennaio": 1, "january": 1, "febbraio": 2, "february": 2, "marzo": 3, "march": 3,
    "aprile": 4, "april": 4, "maggio": 5, "may": 5, "giugno": 6, "june": 6, "luglio": 7,
    "july": 7, "agosto": 8, "august": 8, "settembre": 9, "september": 9, "ottobre": 10,
    "october": 10, "novembre": 11, "november": 11, "dicembre": 12, "december": 12,
}
SEASONS = {
    "primavera": (3, 5), "spring": (3, 5), "estate": (6, 8), "summer": (6, 8),
    "autunno": (9, 11), "autumn": (9, 11), "fall": (9, 11), "inverno": (12, 2), "winter": (12, 2),
}
NUMBER_WORDS = {
    "uno": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7,
    "otto": 8, "nove": 9, "dieci": 10, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
MAX_PAX = 20

IT_MARKERS = {"un", "una", "di", "del", "della", "per", "siamo", "con", "massimo", "vorrei",
              "voglio", "noi", "persone", "giorni", "il", "la", "viaggio", "vacanza", "due",
              "tre", "quattro", "fine", "settimana", "euro", "e"}
EN_MARKERS = {"the", "of", "for", "we", "are", "with", "max", "want", "would", "like", "people",
              "under", "and", "two", "three", "four", "our", "my", "trip", "holiday", "us",
              "euros", "next", "camp"}

_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))
_SEASON_RE = "|".join(sorted(SEASONS, key=len, reverse=True))
_WEEKEND_RE = re.compile(r"\bweek-?end\b|\bfine settimana\b")
_PAX_PATTERNS = [
    re.compile(r"\bsiamo in (\w+)"),
    re.compile(r"\bwe are (\w+)"),
    re.compile(r"\bwe're (\w+)"),
    re.compile(r"\b(\w+)\s+(?:persone|adulti|giocatori|amici|people|adults|players|friends|pax)\b"),
    re.compile(r"\b(\w+)\s+of us\b"),
    re.compile(r"\b(?:per|for)\s+(\w+)\b"),
    re.compile(r"\bx\s?(\d+)\b"),
    re.compile(r"\bin\s+(\d+)\b"),
]
_BUDGET_PATTERNS = [
    re.compile(r"(?:al massimo|massimo|max|budget|under|up to|fino a|entro|non più di|"
               r"no more than|not more than|less than|meno di)\s*(?:di\s+)?(?:€|eur|euro|euros)?"
               r"\s*(\d[\d.,]*)"),
    re.compile(r"(\d[\d.,]*)\s*(?:€|euros?\b|eur\b)"),
    re.compile(r"€\s*(\d[\d.,]*)"),
]


@dataclass(frozen=True)
class ParseResult:
    criteria: Criteria
    question: Optional[str] = None


def _words(text: str) -> list:
    return re.findall(r"[a-zà-ÿ']+", text.lower())


def detect_language(text: str) -> str:
    words = _words(text)
    it = sum(w in IT_MARKERS for w in words)
    en = sum(w in EN_MARKERS for w in words)
    return "en" if en > it else "it"


def parse_sport(text: str) -> Optional[str]:
    m = re.search(r"\b(padel|tennis)\b", text.lower())
    return m.group(1) if m else None


def _month_period(month: int, today: date, label: str) -> Period:
    year = today.year if month >= today.month else today.year + 1
    return Period(date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1]), label)


def _day_period(day: int, month: int, year: Optional[int], today: date, label: str) -> Optional[Period]:
    try:
        d = date(year or today.year, month, day)
    except ValueError:
        return None
    if year is None and d < today:
        d = date(today.year + 1, month, day)
    return Period(d, d, label)


def parse_period(text: str, today: date) -> Optional[Period]:
    low = text.lower()
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", low)
    if m:
        return _day_period(int(m.group(3)), int(m.group(2)), int(m.group(1)), today, m.group(0))
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b", low)
    if m:
        year = int(m.group(3)) if m.group(3) else None
        return _day_period(int(m.group(1)), int(m.group(2)), year, today, m.group(0))
    m = re.search(r"\b(\d{1,2})\s+(%s)\b" % _MONTH_RE, low)
    if m:
        return _day_period(int(m.group(1)), MONTHS[m.group(2)], None, today, m.group(0))
    m = re.search(r"\b(%s)\b" % _MONTH_RE, low)
    if m:
        return _month_period(MONTHS[m.group(1)], today, m.group(1))
    m = re.search(r"\b(%s)\b" % _SEASON_RE, low)
    if m:
        first, last = SEASONS[m.group(1)]
        if first == 12:   # inverno: dicembre → febbraio
            year = today.year if today.month >= 3 else today.year - 1
            return Period(date(year, 12, 1), date(year + 1, 3, 1) - timedelta(days=1), m.group(1))
        year = today.year if last >= today.month else today.year + 1
        return Period(date(year, first, 1), date(year, last, calendar.monthrange(year, last)[1]),
                      m.group(1))
    m = _WEEKEND_RE.search(low)
    if m:
        start = today + timedelta(days=(5 - today.weekday()) % 7)
        return Period(start, start + timedelta(days=1), m.group(0))
    return None


def _to_int(token: str) -> Optional[int]:
    if token.isdigit():
        return int(token)
    return NUMBER_WORDS.get(token)


def parse_pax(text: str) -> Optional[int]:
    low = text.lower()
    for pattern in _PAX_PATTERNS:
        for m in pattern.finditer(low):
            value = _to_int(m.group(1))
            if value is not None and 1 <= value <= MAX_PAX:
                return value
    return None


def _to_money(token: str) -> Optional[Decimal]:
    token = re.sub(r"[.,](?=\d{3}\b)", "", token)   # separatori delle migliaia
    token = token.replace(",", ".").rstrip(".")
    try:
        return Decimal(token)
    except ArithmeticError:
        return None


def parse_budget(text: str) -> Optional[Decimal]:
    low = text.lower()
    for pattern in _BUDGET_PATTERNS:
        m = pattern.search(low)
        if m:
            value = _to_money(m.group(1))
            if value is not None and value > 0:
                return value
    return None


def parse_intent(text: str, profile: Optional[TravelerProfile] = None,
                 today: Optional[date] = None) -> ParseResult:
    today = today or date.today()
    profile = profile or TravelerProfile()
    criteria = Criteria(
        sport=parse_sport(text),
        area=geo.find_area(text),
        period=parse_period(text, today),
        pax=parse_pax(text) or profile.pax,
        budget=parse_budget(text),
        language=detect_language(text),
    )
    question = None
    if criteria.sport is None and criteria.period is None:
        question = QUESTION_SPORT_OR_PERIOD
    elif criteria.pax is None:
        question = QUESTION_PAX
    return ParseResult(criteria, question)
```

- [ ] **Step 4: Eseguire** `python3 -m unittest tests.test_intent -v` → PASS. Se un caso della tabella fallisce per un alias o un marcatore di lingua, correggere il dizionario, non il caso di test.

- [ ] **Step 5: Commit**

```bash
git add vela/domain/intent.py tests/test_intent.py
git commit -m "Add the minimal it/en intent parser with the single missing-info question

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Chooser v1 (RF-06, RF-07, RF-09)

**Files:**
- Create: `vela/domain/chooser.py`
- Create: `tests/test_chooser.py`

**Interfaces:**
- Consumes: `Product`, `Criteria`, `Availability` (Task 1); `geo.find_area` (Task 3); `make_product` (`tests/support.py`).
- Produces: `Choice(product, start_date, end_date, reason)`; `NoChoice(failed_criterion)`; `choose(products, criteria, rejected_ids, today) -> Choice | NoChoice`; `window_for(product, period, today) -> Availability | None`; `area_score(product, area) -> int`; `FILTERS` (nomi dei criteri: `archived`, `bookable`, `rejected`, `sport`, `dates`, `pax`).

- [ ] **Step 1: Scrivere i test** in `tests/test_chooser.py`:

```python
import unittest
from datetime import date
from decimal import Decimal

from support import TODAY, make_product
from vela.domain.chooser import Choice, NoChoice, area_score, choose, window_for
from vela.domain.models import Area, Criteria, Period

OCTOBER = Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre")
SPAIN = Area("country", "Spagna", "ES")


def crit(**kw):
    base = dict(sport="padel", area=SPAIN, period=OCTOBER, pax=2, budget=Decimal("800"))
    base.update(kw)
    return Criteria(**base)


class ExclusionTest(unittest.TestCase):
    def test_archived_bookable_rejected_are_never_chosen(self):
        products = [make_product(1, archived=True), make_product(2, bookable=False),
                    make_product(3), make_product(4, price=900)]
        r = choose(products, crit(), rejected_ids={"3"}, today=TODAY)
        self.assertIsInstance(r, Choice)
        self.assertEqual(r.product.id, "4")

    def test_sport_mismatch(self):
        r = choose([make_product(1, sport="tennis")], crit(sport="padel"), set(), TODAY)
        self.assertEqual(r, NoChoice("sport"))

    def test_no_sport_in_intent_accepts_any_sport(self):
        r = choose([make_product(1, sport="tennis")], crit(sport=None), set(), TODAY)
        self.assertIsInstance(r, Choice)

    def test_dates_outside_min_max(self):
        p = make_product(1, min_date="2026-11-01", max_date="2026-12-31",
                         windows=(("2026-11-05", "2026-11-08"),))
        self.assertEqual(choose([p], crit(), set(), TODAY), NoChoice("dates"))

    def test_dates_no_window_in_period(self):
        p = make_product(1, windows=(("2026-11-05", "2026-11-08"),))
        self.assertEqual(choose([p], crit(), set(), TODAY), NoChoice("dates"))

    def test_past_window_is_skipped(self):
        p = make_product(1, windows=(("2026-09-20", "2026-09-22"), ("2026-10-15", "2026-10-18")))
        r = choose([p], crit(), set(), TODAY)
        self.assertEqual((r.start_date, r.end_date), (date(2026, 10, 15), date(2026, 10, 18)))

    def test_no_period_takes_first_future_window(self):
        p = make_product(1, windows=(("2026-09-20", "2026-09-22"), ("2026-12-01", "2026-12-04")))
        r = choose([p], crit(period=None), set(), TODAY)
        self.assertEqual(r.start_date, date(2026, 12, 1))

    def test_pax_bounds(self):
        self.assertEqual(choose([make_product(1, min_pax=3)], crit(pax=2), set(), TODAY), NoChoice("pax"))
        self.assertEqual(choose([make_product(1, max_pax=1)], crit(pax=2), set(), TODAY), NoChoice("pax"))

    def test_zero_or_null_pax_bounds_do_not_exclude(self):
        self.assertIsInstance(choose([make_product(1, min_pax=None, max_pax=0)], crit(pax=6), set(), TODAY), Choice)
        self.assertIsInstance(choose([make_product(1, min_pax=0, max_pax=None)], crit(pax=1), set(), TODAY), Choice)

    def test_failed_criterion_is_the_first_emptying_filter(self):
        products = [make_product(1, archived=True), make_product(2, sport="tennis")]
        self.assertEqual(choose(products, crit(), set(), TODAY), NoChoice("sport"))
        self.assertEqual(choose([make_product(1)], crit(), {"1"}, TODAY), NoChoice("rejected"))
        self.assertEqual(choose([], crit(), set(), TODAY), NoChoice("archived"))


class OrderingTest(unittest.TestCase):
    def test_area_then_budget_then_price(self):
        products = [make_product(1, price=300, country="IT", destination="Riccione"),
                    make_product(2, price=450, country="ES", destination="Madrid"),
                    make_product(3, price=350, country="ES", destination="Valencia"),
                    make_product(4, price=390, country="ES", destination="Lanzarote")]
        r = choose(products, crit(area=Area("city", "Lanzarote", "ES")), set(), TODAY)
        self.assertEqual(r.product.id, "4")           # città coincidente batte il prezzo
        r = choose(products, crit(), set(), TODAY)
        self.assertEqual(r.product.id, "3")           # paese: 350×2 = 700 ≤ 800, il più economico
        r = choose(products, crit(budget=Decimal("720")), set(), TODAY)
        self.assertEqual(r.product.id, "3")           # 700 entro budget, 900 no
        r = choose(products, crit(budget=Decimal("100")), set(), TODAY)
        self.assertEqual(r.product.id, "3")           # nessuno entro budget: prezzo crescente in area

    def test_without_area_and_budget_is_price_then_id(self):
        products = [make_product(2, price=300), make_product(1, price=300), make_product(3, price=200)]
        r = choose(products, crit(area=None, budget=None), set(), TODAY)
        self.assertEqual(r.product.id, "3")
        r = choose(products, crit(area=None, budget=None), {"3"}, TODAY)
        self.assertEqual(r.product.id, "1")

    def test_area_score(self):
        p = make_product(1, country="ES", destination="Palma de Mallorca")
        self.assertEqual(area_score(p, None), 0)
        self.assertEqual(area_score(p, Area("city", "Palma de Mallorca", "ES")), 2)
        self.assertEqual(area_score(p, Area("region", "Maiorca", "ES")), 1)
        self.assertEqual(area_score(p, Area("country", "Italia", "IT")), 0)
        self.assertEqual(area_score(make_product(2, country=None, destination=None), SPAIN), 0)


class ReasonAndWindowTest(unittest.TestCase):
    def test_reason_mentions_area_dates_and_budget(self):
        r = choose([make_product(1, price=300)], crit(), set(), TODAY)
        self.assertIn("Spagna", r.reason)
        self.assertIn("1 ottobre", r.reason)
        self.assertIn("800", r.reason)
        self.assertTrue(r.reason.endswith("."))

    def test_reason_over_budget_says_cheapest(self):
        r = choose([make_product(1, price=900)], crit(area=None), set(), TODAY)
        self.assertIn("più economic", r.reason)

    def test_window_for(self):
        p = make_product(1, windows=(("2026-10-01", "2026-10-04"), ("2026-10-08", "2026-10-11")))
        self.assertEqual(window_for(p, OCTOBER, TODAY).start, date(2026, 10, 1))
        self.assertEqual(window_for(p, OCTOBER, date(2026, 10, 2)).start, date(2026, 10, 8))
        self.assertIsNone(window_for(p, OCTOBER, date(2026, 10, 9)))
```

- [ ] **Step 2: Eseguire** `python3 -m unittest tests.test_chooser -v` → `ModuleNotFoundError`.

- [ ] **Step 3: Scrivere `vela/domain/chooser.py`**:

```python
"""Chooser v1 (RF-06, RF-07 semplificato, RF-09): una sola scelta deterministica.

Esclusioni in sequenza (archiviati, non prenotabili, rifiutati, sport, date, pax); tra i
restanti ordina per area coincidente (città > paese), totale entro budget, prezzo crescente,
id. Se un filtro azzera i candidati, `NoChoice` porta il nome di quel filtro (RF-09). M11
aggiunge geohierarchy, durata e intersezioni parziali.
"""
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional, Set, Union

from vela.domain import geo
from vela.domain.models import Area, Availability, Criteria, Period, Product
from vela.domain.say import fmt_date, fmt_money

FILTERS = ("archived", "bookable", "rejected", "sport", "dates", "pax")


@dataclass(frozen=True)
class Choice:
    product: Product
    start_date: date
    end_date: date
    reason: str


@dataclass(frozen=True)
class NoChoice:
    failed_criterion: str


def window_for(product: Product, period: Optional[Period], today: date) -> Optional[Availability]:
    for window in product.availabilities:
        if window.start < today:
            continue
        if period is None or period.start <= window.start <= period.end:
            return window
    return None


def _dates_ok(product: Product, period: Optional[Period], today: date) -> bool:
    if period is not None:
        if product.min_date and period.end < product.min_date:
            return False
        if product.max_date and period.start > product.max_date:
            return False
    return window_for(product, period, today) is not None


def _pax_ok(product: Product, pax: Optional[int]) -> bool:
    if pax is None:
        return True
    if product.min_pax and pax < product.min_pax:
        return False
    if product.max_pax and pax > product.max_pax:
        return False
    return True


def area_score(product: Product, area: Optional[Area]) -> int:
    if area is None:
        return 0
    if area.kind != "country":
        found = geo.find_area(product.destination)
        if found is not None and found.name == area.name:
            return 2
    return 1 if product.country == area.country_code else 0


def _within_budget(product: Product, criteria: Criteria) -> bool:
    if criteria.budget is None:
        return True
    return product.price * (criteria.pax or 1) <= criteria.budget


def _reason(product: Product, criteria: Criteria, window: Availability) -> str:
    parts = []
    if area_score(product, criteria.area) > 0:
        where = criteria.area.name if area_score(product, criteria.area) == 1 else product.destination
        parts.append("è in %s" % where if criteria.area.kind == "country" else "è a %s" % where)
    elif product.destination:
        parts.append("è a %s" % product.destination)
    parts.append("parte il %s" % fmt_date(window.start))
    if criteria.budget is not None and _within_budget(product, criteria):
        parts.append("resta nel tuo budget di %s" % fmt_money(criteria.budget))
    else:
        parts.append("è la proposta più economica tra quelle compatibili")
    sentence = ", ".join(parts[:-1]) + " e " + parts[-1] if len(parts) > 1 else parts[0]
    return sentence[0].upper() + sentence[1:] + "."


def choose(products: Iterable[Product], criteria: Criteria, rejected_ids: Set[str],
           today: date) -> Union[Choice, NoChoice]:
    candidates = list(products)
    steps = (
        ("archived", lambda p: not p.archived),
        ("bookable", lambda p: p.bookable),
        ("rejected", lambda p: p.id not in rejected_ids),
        ("sport", lambda p: criteria.sport is None or p.sport == criteria.sport),
        ("dates", lambda p: _dates_ok(p, criteria.period, today)),
        ("pax", lambda p: _pax_ok(p, criteria.pax)),
    )
    for name, keep in steps:
        candidates = [p for p in candidates if keep(p)]
        if not candidates:
            return NoChoice(name)
    candidates.sort(key=lambda p: (-area_score(p, criteria.area), not _within_budget(p, criteria),
                                   p.price, p.id))
    best = candidates[0]
    window = window_for(best, criteria.period, today)
    return Choice(best, window.start, window.end, _reason(best, criteria, window))
```

Nota: `chooser.py` importa `fmt_date` e `fmt_money` da `vela/domain/say.py`, che nasce nel Task 6. Per far passare questo task, creare subito `vela/domain/say.py` con le sole due funzioni (il Task 6 aggiunge il resto):

```python
"""Frasi italiane pronte da leggere (RF-42): nessun markdown, nessun URL."""
from datetime import date
from decimal import Decimal

MONTHS_IT = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
             "settembre", "ottobre", "novembre", "dicembre"]


def fmt_date(d: date) -> str:
    return "%d %s %d" % (d.day, MONTHS_IT[d.month - 1], d.year)


def fmt_money(value: Decimal) -> str:
    q = value.quantize(Decimal("0.01"))
    if q == q.to_integral_value():
        return "%d euro" % int(q)
    return format(q, "f").replace(".", ",") + " euro"
```

- [ ] **Step 4: Eseguire** `python3 -m unittest tests.test_chooser -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add vela/domain/chooser.py vela/domain/say.py tests/test_chooser.py
git commit -m "Add chooser v1 with ordered exclusions and area, budget, price ranking

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Frasi `say` in italiano (RF-42)

**Files:**
- Modify: `vela/domain/say.py` (creato nel Task 5 con `fmt_date`, `fmt_money`)
- Create: `tests/test_say.py`

**Interfaces:**
- Consumes: `Criteria`, `Proposal`, `ProductSummary`, `OrderStatus` (Task 1).
- Produces: `say_intent_created(criteria)`, `say_proposal(product: ProductSummary, proposal: Proposal)`, `say_no_match(criterion)`, `say_missing(missing: list[str])`, `say_accept(total, price_from_total, total_differs)`, `say_status(status, booking_code, failure_reason)`, `say_paid()`. Tutte restituiscono `str` senza markdown né URL.

- [ ] **Step 1: Scrivere i test** in `tests/test_say.py`:

```python
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from vela.domain import say
from vela.domain.models import Area, Criteria, OrderStatus, Period, ProductSummary, Proposal

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
PRODUCT = ProductSummary("181", "Magnifico Padel a Lanzarote", "Lanzarote", "THB Lanzarote Beach")
PROPOSAL = Proposal("p1", "i1", "181", date(2026, 10, 1), date(2026, 10, 4), 2, Decimal("578"),
                    "EUR", "È in Spagna, parte il 1 ottobre 2026 e resta nel tuo budget di 800 euro.", NOW)


class FormatTest(unittest.TestCase):
    def test_date_and_money(self):
        self.assertEqual(say.fmt_date(date(2026, 10, 1)), "1 ottobre 2026")
        self.assertEqual(say.fmt_money(Decimal("800")), "800 euro")
        self.assertEqual(say.fmt_money(Decimal("812.5")), "812,50 euro")


class SayTest(unittest.TestCase):
    def test_intent_created(self):
        c = Criteria("padel", Area("country", "Spagna", "ES"),
                     Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre"), 2, Decimal("800"))
        s = say.say_intent_created(c)
        for piece in ("padel", "Spagna", "1 ottobre 2026", "31 ottobre 2026", "2 persone", "800 euro"):
            self.assertIn(piece, s)
        self.assertIn("1 persona", say.say_intent_created(Criteria(pax=1)))

    def test_proposal(self):
        s = say.say_proposal(PRODUCT, PROPOSAL)
        for piece in ("Magnifico Padel a Lanzarote", "Lanzarote", "THB Lanzarote Beach",
                      "1 ottobre 2026", "4 ottobre 2026", "2 persone", "578 euro", PROPOSAL.reason):
            self.assertIn(piece, s)
        self.assertNotIn("http", s)
        self.assertNotIn("*", s)

    def test_proposal_without_hotel_and_single_day(self):
        p = ProductSummary("1", "Titolo", None, None)
        s = say.say_proposal(p, Proposal("p", "i", "1", date(2026, 10, 1), date(2026, 10, 1), 1,
                                         Decimal("50"), "EUR", "Motivo.", NOW))
        self.assertIn("il 1 ottobre 2026", s)
        self.assertNotIn("hotel", s.lower())

    def test_no_match_covers_every_criterion(self):
        from vela.domain.chooser import FILTERS
        texts = {c: say.say_no_match(c) for c in FILTERS}
        self.assertEqual(len(set(texts.values())), 5)   # archived e bookable condividono la frase
        self.assertIn("scartato", texts["rejected"])
        self.assertIn("periodo", texts["dates"])

    def test_missing(self):
        s = say.say_missing(["email", "phone", "participants[0].last_name"])
        self.assertIn("l'email", s)
        self.assertIn("il telefono", s)
        self.assertIn("cognome del secondo partecipante", s)

    def test_accept(self):
        same = say.say_accept(Decimal("1156"), Decimal("1156"), False)
        self.assertIn("1156 euro", same)
        self.assertNotIn("non i", same)
        differs = say.say_accept(Decimal("1200"), Decimal("1156"), True)
        self.assertLess(differs.index("1200 euro"), differs.index("link"))
        self.assertIn("1156 euro", differs)

    def test_status(self):
        self.assertIn("R-123456", say.say_status(OrderStatus.CONFIRMED, "R-123456", None))
        self.assertIn("attesa", say.say_status(OrderStatus.AWAITING_PAYMENT, None, None))
        self.assertIn("completando", say.say_status(OrderStatus.PAID_PENDING_BOOKING, None, None))
        self.assertIn("non è riuscita", say.say_status(OrderStatus.BOOKING_FAILED, None, "timeout"))
        self.assertIn("scaduto", say.say_status(OrderStatus.EXPIRED, None, None))

    def test_paid(self):
        self.assertIn("Pagamento", say.say_paid())
```

- [ ] **Step 2: Eseguire** `python3 -m unittest tests.test_say -v` → `AttributeError: say_intent_created`.

- [ ] **Step 3: Completare `vela/domain/say.py`**: gli `import` vanno in testa al file, le funzioni dopo `fmt_money`:

```python
from typing import Optional

from vela.domain.models import Criteria, OrderStatus, ProductSummary, Proposal


def _people(n: Optional[int]) -> str:
    if n is None:
        return ""
    return "1 persona" if n == 1 else "%d persone" % n


def _join(parts: list) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " e " + parts[-1]


def say_intent_created(c: Criteria) -> str:
    parts = ["un viaggio di %s" % c.sport if c.sport else "un viaggio"]
    if c.area:
        parts.append(("in %s" if c.area.kind == "country" else "a %s") % c.area.name)
    if c.period:
        if c.period.start == c.period.end:
            parts.append("il %s" % fmt_date(c.period.start))
        else:
            parts.append("tra il %s e il %s" % (fmt_date(c.period.start), fmt_date(c.period.end)))
    if c.pax:
        parts.append("per %s" % _people(c.pax))
    if c.budget is not None:
        parts.append("con un budget massimo di %s" % fmt_money(c.budget))
    return "Ho capito: %s. Cerco la proposta giusta." % " ".join(parts)


def say_proposal(product: ProductSummary, p: Proposal) -> str:
    where = " a %s" % product.destination if product.destination else ""
    hotel = ", hotel %s" % product.hotel if product.hotel else ""
    if p.start_date == p.end_date:
        when = "il %s" % fmt_date(p.start_date)
    else:
        when = "dal %s al %s" % (fmt_date(p.start_date), fmt_date(p.end_date))
    return ("Ti propongo %s%s%s, %s per %s, a partire da %s a persona. %s Ti va?"
            % (product.title, where, hotel, when, _people(p.pax), fmt_money(p.price_from), p.reason))


_NO_MATCH = {
    "archived": "Al momento non ho nessun viaggio prenotabile: riprova più tardi.",
    "bookable": "Al momento non ho nessun viaggio prenotabile: riprova più tardi.",
    "rejected": "Hai già scartato tutte le proposte compatibili con la tua richiesta: prova a riformularla.",
    "sport": "Non trovo nessun viaggio per lo sport che hai chiesto: prova con l'altro sport o riformula la richiesta.",
    "dates": "Non trovo partenze nel periodo che hai chiesto: prova con un altro periodo.",
    "pax": "Non trovo viaggi per il numero di persone indicato: prova a cambiare il numero di persone.",
}


def say_no_match(criterion: str) -> str:
    return _NO_MATCH.get(criterion, "Non trovo nessun viaggio compatibile: prova a riformulare la richiesta.")


_ORDINALS = ["secondo", "terzo", "quarto", "quinto", "sesto", "settimo", "ottavo", "nono", "decimo"]
_FIELD_LABELS = {"first_name": "il nome", "last_name": "il cognome", "email": "l'email", "phone": "il telefono"}


def _label(field: str) -> str:
    if field.startswith("participants["):
        index = int(field[len("participants["):field.index("]")])
        leaf = field.split(".")[-1]
        ordinal = _ORDINALS[index] if index < len(_ORDINALS) else "numero %d" % (index + 2)
        return "%s del %s partecipante" % (_FIELD_LABELS[leaf], ordinal)
    return _FIELD_LABELS.get(field, field)


def say_missing(missing: list) -> str:
    return "Per prenotare mi servono ancora: %s." % _join([_label(f) for f in missing])


def say_accept(total, price_from_total, total_differs: bool) -> str:
    head = ""
    if total_differs:
        head = "Il totale reale è %s, non i %s stimati. " % (fmt_money(total), fmt_money(price_from_total))
    return (head + "Il totale è %s. Ti mando il link di pagamento per testo: appena il pagamento "
            "arriva, prenoto e ti do il codice." % fmt_money(total))


def say_status(status: OrderStatus, booking_code: Optional[str], failure_reason: Optional[str]) -> str:
    if status == OrderStatus.CONFIRMED:
        return "La tua prenotazione è confermata, codice %s." % booking_code
    if status == OrderStatus.AWAITING_PAYMENT:
        return "L'ordine è in attesa del pagamento: usa il link che ti ho mandato."
    if status == OrderStatus.PAID_PENDING_BOOKING:
        return "Pagamento ricevuto, sto completando la prenotazione: richiedi lo stato tra qualche secondo."
    if status == OrderStatus.BOOKING_FAILED:
        return ("Il pagamento è arrivato ma la prenotazione non è riuscita: riprovo io, "
                "e se non ci riesco ti avviso.")
    return "Il link di pagamento è scaduto: dimmi se vuoi che prepari una nuova proposta."


def say_paid() -> str:
    return "Pagamento simulato registrato: la prenotazione è in corso."
```

- [ ] **Step 4: Eseguire** `python3 -m unittest tests.test_say tests.test_chooser -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add vela/domain/say.py tests/test_say.py
git commit -m "Add the Italian spoken phrases for every use case response

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Porte e repository in memoria

**Files:**
- Create: `vela/ports/hofj.py`, `vela/ports/payments.py`, `vela/ports/repositories.py`
- Create: `vela/adapters/repo_memory.py`
- Create: `tests/repo_contract.py`, `tests/test_repo_memory.py`

**Interfaces:**
- Consumes: modelli del Task 1.
- Produces (esatte, usate da Task 8-12):
  - `vela.ports.hofj`: `HofJError(Exception)`, `ProductError(HofJError)`, `QuotaError(HofJError)`, `UpstreamError(HofJError)`; `Itinerary(id, total: Decimal, currency)`; `Customer(first_name, last_name, email, phone, street1, postal_code, city, region, country_code)`; `Pax(ref_id, first_name=None, last_name=None)`; `PaymentProof(payment_intent_id, payment_status, payment_type="full")`; `HofJPort` con `create_itinerary(product, start_date, adults, rooms, currency) -> Itinerary`, `set_customer(itinerary_id, customer) -> None`, `get_pax(itinerary_id) -> list[Pax]`, `set_pax(itinerary_id, pax: list[Pax]) -> None`, `create_booking(itinerary_id, proof) -> str`.
  - `vela.ports.payments`: `PaymentLink(url, expires_at, reference)`; `PaymentsPort.create_payment_link(order) -> PaymentLink`.
  - `vela.ports.repositories`: `DuplicateOrder(Exception)`; `ProductRepository` (`upsert_many(products)`, `count() -> int`, `list_all() -> list[Product]`, `get(id) -> Product | None`); `IntentRepository` (`add`, `get`); `ProposalRepository` (`add`, `get`, `list_for_intent(intent_id) -> list` ordinata per `created_at`); `OrderRepository` (`add(order)` → `DuplicateOrder` se `proposal_id` esiste, `get`, `get_by_proposal`, `save(order)`, `ids_with_status(status) -> list[str]`); `RejectionRepository` (`add(rejection)` idempotente per `proposal_id`, `product_ids_for_intent(intent_id) -> set`, `proposal_ids_for_intent(intent_id) -> set`); `Repositories` con attributi `products, intents, proposals, orders, rejections`.
  - `vela.adapters.repo_memory.MemoryRepositories()` con `clear()`.

- [ ] **Step 1: Scrivere il contratto** in `tests/repo_contract.py`:

```python
"""Contratto dei repository: eseguito su MemoryRepositories (sempre) e PostgresRepositories (con DATABASE_URL)."""
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from support import NOW, make_product
from vela.domain.models import (Criteria, Intent, Order, OrderStatus, Participant, Period,
                                Proposal, Rejection, TravelerProfile)
from vela.ports.repositories import DuplicateOrder

CRITERIA = Criteria(sport="padel", period=Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre"),
                    pax=2, budget=Decimal("800"))
PROFILE = TravelerProfile("Anna", "Rossi", "a@x.it", "+39", 2, (Participant("Bo", "Bi"),))


def intent(iid="i1"):
    return Intent(iid, "padel a ottobre per due", CRITERIA, PROFILE, NOW)


def proposal(pid="p1", iid="i1", product_id="1", created_at=NOW):
    return Proposal(pid, iid, product_id, date(2026, 10, 1), date(2026, 10, 4), 2, Decimal("500"),
                    "EUR", "Motivo.", created_at)


def order(oid="o1", pid="p1"):
    return Order(oid, pid, "i1", "1", OrderStatus.AWAITING_PAYMENT, 2, Decimal("500"),
                 Decimal("1000"), "EUR", PROFILE, NOW, NOW, itinerary_id="it-1")


class RepositoryContract:
    def make_repos(self):
        raise NotImplementedError

    def setUp(self):
        self.repos = self.make_repos()

    # prodotti
    def test_products_upsert_is_idempotent_and_updates(self):
        self.repos.products.upsert_many([make_product(1, price=500), make_product(2, archived=True)])
        self.repos.products.upsert_many([make_product(1, price=550)])
        self.assertEqual(self.repos.products.count(), 2)
        self.assertEqual(self.repos.products.get("1").price, Decimal("550"))
        self.assertEqual(sorted(p.id for p in self.repos.products.list_all()), ["1", "2"])
        self.assertTrue(self.repos.products.get("2").archived)
        self.assertIsNone(self.repos.products.get("999"))

    def test_products_fields_round_trip(self):
        p = make_product(7, min_pax=2, max_pax=0, hotel=None, windows=(("2026-10-01", "2026-10-04"),
                                                                        ("2026-11-05", "2026-11-08")))
        p = replace(p, raw={"rawAttributes": {"k": [1, 2]}}, bookable=False, bookable_checked_at=NOW)
        self.repos.products.upsert_many([p])
        got = self.repos.products.get("7")
        self.assertEqual(got, p)

    def test_products_empty(self):
        self.assertEqual(self.repos.products.count(), 0)
        self.assertEqual(self.repos.products.list_all(), [])
        self.repos.products.upsert_many([])

    # intenti
    def test_intents_round_trip(self):
        self.repos.intents.add(intent())
        self.assertEqual(self.repos.intents.get("i1"), intent())
        self.assertIsNone(self.repos.intents.get("nope"))

    def seed(self):
        """Prodotti e intento a cui proposte, ordini e rifiuti fanno riferimento (foreign key su Postgres)."""
        self.repos.products.upsert_many([make_product(1), make_product(2)])
        self.repos.intents.add(intent())

    # proposte
    def test_proposals_ordered_by_created_at(self):
        self.seed()
        self.repos.proposals.add(proposal("p2", created_at=NOW + timedelta(seconds=5)))
        self.repos.proposals.add(proposal("p1"))
        self.assertEqual([p.id for p in self.repos.proposals.list_for_intent("i1")], ["p1", "p2"])
        self.assertEqual(self.repos.proposals.get("p2"), proposal("p2", created_at=NOW + timedelta(seconds=5)))
        self.assertIsNone(self.repos.proposals.get("nope"))
        self.assertEqual(self.repos.proposals.list_for_intent("other"), [])

    # ordini
    def test_orders_add_get_save_and_duplicate(self):
        self.seed()
        self.repos.proposals.add(proposal())
        self.repos.orders.add(order())
        self.assertEqual(self.repos.orders.get("o1"), order())
        self.assertEqual(self.repos.orders.get_by_proposal("p1").id, "o1")
        with self.assertRaises(DuplicateOrder):
            self.repos.orders.add(order("o2", "p1"))
        self.assertIsNone(self.repos.orders.get("o2"))
        updated = replace(order(), status=OrderStatus.CONFIRMED, booking_code="R-1",
                          payment_url="http://x", payment_ref="pi", paid_at=NOW,
                          updated_at=NOW + timedelta(seconds=1))
        self.repos.orders.save(updated)
        self.assertEqual(self.repos.orders.get("o1"), updated)
        self.assertEqual(self.repos.orders.ids_with_status(OrderStatus.CONFIRMED), ["o1"])
        self.assertEqual(self.repos.orders.ids_with_status(OrderStatus.AWAITING_PAYMENT), [])
        self.assertIsNone(self.repos.orders.get_by_proposal("nope"))

    # rifiuti
    def test_rejections(self):
        self.seed()
        self.repos.proposals.add(proposal("p1", product_id="1"))
        self.repos.proposals.add(proposal("p2", product_id="2"))
        self.repos.rejections.add(Rejection("i1", "p1", "1", "troppo caro", NOW))
        self.repos.rejections.add(Rejection("i1", "p1", "1", "di nuovo", NOW))
        self.repos.rejections.add(Rejection("i1", "p2", "2", "", NOW))
        self.assertEqual(self.repos.rejections.product_ids_for_intent("i1"), {"1", "2"})
        self.assertEqual(self.repos.rejections.proposal_ids_for_intent("i1"), {"p1", "p2"})
        self.assertEqual(self.repos.rejections.product_ids_for_intent("other"), set())
```

E `tests/test_repo_memory.py`:

```python
import unittest

from repo_contract import RepositoryContract
from vela.adapters.repo_memory import MemoryRepositories


class MemoryRepositoriesTest(RepositoryContract, unittest.TestCase):
    def make_repos(self):
        return MemoryRepositories()

    def test_clear(self):
        from support import make_product
        self.repos.products.upsert_many([make_product(1)])
        self.repos.clear()
        self.assertEqual(self.repos.products.count(), 0)
```

- [ ] **Step 2: Eseguire** `python3 -m unittest tests.test_repo_memory -v` → `ModuleNotFoundError`.

- [ ] **Step 3: Scrivere le porte.** `vela/ports/hofj.py`:

```python
"""Porta verso House of Journeys (spec §2 "Porta", RF-14, RF-23). Implementazioni: replay (M2), HTTP (M5)."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional, Protocol

from vela.domain.models import Product


class HofJError(Exception):
    """Base degli errori della porta."""


class ProductError(HofJError):
    """Errore riconducibile al prodotto (RF-17): il chooser lo marcherà non prenotabile (M5)."""


class QuotaError(HofJError):
    """Quota esaurita (RF-37)."""


class UpstreamError(HofJError):
    """Rete, timeout, 5xx non riconducibili al prodotto."""


@dataclass(frozen=True)
class Itinerary:
    id: str
    total: Decimal
    currency: str


@dataclass(frozen=True)
class Customer:
    first_name: str
    last_name: str
    email: str
    phone: str
    street1: str
    postal_code: str
    city: str
    region: str
    country_code: str


@dataclass(frozen=True)
class Pax:
    ref_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


@dataclass(frozen=True)
class PaymentProof:
    payment_intent_id: str
    payment_status: str
    payment_type: str = "full"


class HofJPort(Protocol):
    def create_itinerary(self, product: Product, start_date: date, adults: int, rooms: int,
                         currency: str) -> Itinerary: ...
    def set_customer(self, itinerary_id: str, customer: Customer) -> None: ...
    def get_pax(self, itinerary_id: str) -> List[Pax]: ...
    def set_pax(self, itinerary_id: str, pax: List[Pax]) -> None: ...
    def create_booking(self, itinerary_id: str, proof: PaymentProof) -> str: ...
```

`vela/ports/payments.py`:

```python
"""Porta verso il pagamento (RF-18, RF-19). Implementazioni: finta (M2), Stripe (M6)."""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from vela.domain.models import Order


@dataclass(frozen=True)
class PaymentLink:
    url: str
    expires_at: datetime
    reference: str      # id del pagamento presso il fornitore (payment intent)


class PaymentsPort(Protocol):
    def create_payment_link(self, order: Order) -> PaymentLink: ...
```

`vela/ports/repositories.py`:

```python
"""Repository del dominio (RNF-01): intenti, proposte, ordini, rifiuti e catalogo stanno fuori dal processo."""
from typing import Iterable, List, Optional, Protocol, Set

from vela.domain.models import Intent, Order, OrderStatus, Product, Proposal, Rejection


class DuplicateOrder(Exception):
    """Esiste già un ordine per la proposta (RNF-03)."""


class ProductRepository(Protocol):
    def upsert_many(self, products: Iterable[Product]) -> None: ...
    def count(self) -> int: ...
    def list_all(self) -> List[Product]: ...
    def get(self, product_id: str) -> Optional[Product]: ...


class IntentRepository(Protocol):
    def add(self, intent: Intent) -> None: ...
    def get(self, intent_id: str) -> Optional[Intent]: ...


class ProposalRepository(Protocol):
    def add(self, proposal: Proposal) -> None: ...
    def get(self, proposal_id: str) -> Optional[Proposal]: ...
    def list_for_intent(self, intent_id: str) -> List[Proposal]: ...


class OrderRepository(Protocol):
    def add(self, order: Order) -> None: ...
    def get(self, order_id: str) -> Optional[Order]: ...
    def get_by_proposal(self, proposal_id: str) -> Optional[Order]: ...
    def save(self, order: Order) -> None: ...
    def ids_with_status(self, status: OrderStatus) -> List[str]: ...


class RejectionRepository(Protocol):
    def add(self, rejection: Rejection) -> None: ...
    def product_ids_for_intent(self, intent_id: str) -> Set[str]: ...
    def proposal_ids_for_intent(self, intent_id: str) -> Set[str]: ...


class Repositories(Protocol):
    products: ProductRepository
    intents: IntentRepository
    proposals: ProposalRepository
    orders: OrderRepository
    rejections: RejectionRepository
```

- [ ] **Step 4: Scrivere `vela/adapters/repo_memory.py`**:

```python
"""Repository in memoria: test del dominio (RNF-09) e app nei test delle superfici."""
import threading
from typing import Dict, Iterable, List, Optional, Set

from vela.domain.models import Intent, Order, OrderStatus, Product, Proposal, Rejection
from vela.ports.repositories import DuplicateOrder


class MemoryProducts:
    def __init__(self):
        self._items: Dict[str, Product] = {}

    def upsert_many(self, products: Iterable[Product]) -> None:
        for p in products:
            self._items[p.id] = p

    def count(self) -> int:
        return len(self._items)

    def list_all(self) -> List[Product]:
        return list(self._items.values())

    def get(self, product_id: str) -> Optional[Product]:
        return self._items.get(product_id)


class MemoryIntents:
    def __init__(self):
        self._items: Dict[str, Intent] = {}

    def add(self, intent: Intent) -> None:
        self._items[intent.id] = intent

    def get(self, intent_id: str) -> Optional[Intent]:
        return self._items.get(intent_id)


class MemoryProposals:
    def __init__(self):
        self._items: Dict[str, Proposal] = {}

    def add(self, proposal: Proposal) -> None:
        self._items[proposal.id] = proposal

    def get(self, proposal_id: str) -> Optional[Proposal]:
        return self._items.get(proposal_id)

    def list_for_intent(self, intent_id: str) -> List[Proposal]:
        return sorted((p for p in self._items.values() if p.intent_id == intent_id),
                      key=lambda p: (p.created_at, p.id))


class MemoryOrders:
    def __init__(self):
        self._items: Dict[str, Order] = {}
        self._lock = threading.Lock()

    def add(self, order: Order) -> None:
        with self._lock:
            if any(o.proposal_id == order.proposal_id for o in self._items.values()):
                raise DuplicateOrder(order.proposal_id)
            self._items[order.id] = order

    def get(self, order_id: str) -> Optional[Order]:
        return self._items.get(order_id)

    def get_by_proposal(self, proposal_id: str) -> Optional[Order]:
        for o in self._items.values():
            if o.proposal_id == proposal_id:
                return o
        return None

    def save(self, order: Order) -> None:
        with self._lock:
            self._items[order.id] = order

    def ids_with_status(self, status: OrderStatus) -> List[str]:
        return sorted(o.id for o in self._items.values() if o.status == status)


class MemoryRejections:
    def __init__(self):
        self._items: Dict[str, Rejection] = {}   # per proposal_id

    def add(self, rejection: Rejection) -> None:
        self._items.setdefault(rejection.proposal_id, rejection)

    def product_ids_for_intent(self, intent_id: str) -> Set[str]:
        return {r.product_id for r in self._items.values() if r.intent_id == intent_id}

    def proposal_ids_for_intent(self, intent_id: str) -> Set[str]:
        return {r.proposal_id for r in self._items.values() if r.intent_id == intent_id}


class MemoryRepositories:
    def __init__(self):
        self.clear()

    def clear(self) -> None:
        self.products = MemoryProducts()
        self.intents = MemoryIntents()
        self.proposals = MemoryProposals()
        self.orders = MemoryOrders()
        self.rejections = MemoryRejections()
```

- [ ] **Step 5: Eseguire** `python3 -m unittest tests.test_repo_memory -v` → PASS.

- [ ] **Step 6: Commit**

```bash
git add vela/ports tests/repo_contract.py tests/test_repo_memory.py vela/adapters/repo_memory.py
git commit -m "Define the HofJ, payments and repository ports with an in-memory implementation

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Orchestratore: `create_intent`, `get_proposal`, `reject_proposal`

**Files:**
- Create: `vela/domain/usecases.py`
- Modify: `tests/support.py` (aggiungere `FakeHofJ`, `StubPayments`)
- Create: `tests/test_usecases.py`

**Interfaces:**
- Consumes: Task 1-7.
- Produces: `NotFound(Exception)` con attributi `kind`, `id`; `class Vela(repos, hofj, payments, defaults=None, now=None, new_id=None)` con attributi pubblici `repos`, `hofj`, `payments`, `defaults`, `now`, `new_id` e metodi `create_intent(text, profile=None) -> IntentCreated | IntentQuestion`, `get_proposal(intent_id) -> ProposalMade | NoMatch`, `reject_proposal(proposal_id, reason) -> ProposalMade | NoMatch`. `utcnow()` e `random_id()` di default. `defaults` è `TravelerDefaults` (Task 10); qui è solo conservato.
- `tests/support.py`: `FakeHofJ(total=None, fail_itinerary=None, fail_booking=None, code="R-000001")` che registra `calls` (lista di tuple `(metodo, args)`) e `StubPayments(base="http://pay.test")`.

- [ ] **Step 1: Aggiungere a `tests/support.py`** in coda:

```python
from decimal import Decimal as _Decimal
from datetime import timedelta as _timedelta

from vela.ports.hofj import Itinerary, Pax
from vela.ports.payments import PaymentLink


class FakeHofJ:
    """Porta HofJ finta e ispezionabile: totale configurabile, errori a comando."""

    def __init__(self, total=None, fail_itinerary=None, fail_booking=None, code="R-000001"):
        self.total = total
        self.fail_itinerary = fail_itinerary
        self.fail_booking = fail_booking
        self.code = code
        self.calls = []
        self.customers = {}
        self.pax = {}
        self.bookings = 0

    def create_itinerary(self, product, start_date, adults, rooms, currency):
        self.calls.append(("create_itinerary", product.id, start_date, adults, rooms, currency))
        if self.fail_itinerary:
            raise self.fail_itinerary
        iid = "it-%s" % product.id
        self.pax[iid] = [Pax("ref-%d" % i) for i in range(adults)]
        total = self.total if self.total is not None else product.price * adults
        return Itinerary(iid, _Decimal(total), currency)

    def set_customer(self, itinerary_id, customer):
        self.calls.append(("set_customer", itinerary_id, customer))
        self.customers[itinerary_id] = customer

    def get_pax(self, itinerary_id):
        self.calls.append(("get_pax", itinerary_id))
        return list(self.pax[itinerary_id])

    def set_pax(self, itinerary_id, pax):
        self.calls.append(("set_pax", itinerary_id, pax))
        self.pax[itinerary_id] = list(pax)

    def create_booking(self, itinerary_id, proof):
        self.calls.append(("create_booking", itinerary_id, proof))
        if self.fail_booking:
            raise self.fail_booking
        self.bookings += 1
        return self.code


class StubPayments:
    def __init__(self, base="http://pay.test"):
        self.base = base
        self.links = []

    def create_payment_link(self, order):
        link = PaymentLink("%s/%s" % (self.base, order.id), NOW + _timedelta(hours=24),
                           "pi_%s" % order.id)
        self.links.append(link)
        return link
```

- [ ] **Step 2: Scrivere i test** in `tests/test_usecases.py`:

```python
import unittest
from datetime import date, timedelta
from decimal import Decimal

from support import NOW, FakeHofJ, StubPayments, assert_single_product, make_product
from vela.adapters.repo_memory import MemoryRepositories
from vela.domain.intent import QUESTION_PAX
from vela.domain.models import (IntentCreated, IntentQuestion, NoMatch, ProposalMade,
                                TravelerProfile)
from vela.domain.usecases import NotFound, Vela

INTENT = "un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro"


class Clock:
    def __init__(self, at=NOW):
        self.at = at

    def __call__(self):
        self.at += timedelta(seconds=1)
        return self.at


def make_vela(products=None, hofj=None, payments=None):
    repos = MemoryRepositories()
    repos.products.upsert_many(products if products is not None else [
        make_product(1, price=300, country="IT", destination="Riccione"),
        make_product(2, price=450, country="ES", destination="Madrid"),
        make_product(3, price=350, country="ES", destination="Valencia"),
        make_product(4, price=390, country="ES", destination="Lanzarote"),
    ])
    ids = iter("id%d" % i for i in range(1, 100))
    return Vela(repos, hofj or FakeHofJ(), payments or StubPayments(), now=Clock(),
                new_id=lambda: next(ids))


class CreateIntentTest(unittest.TestCase):
    def test_creates_and_persists(self):
        vela = make_vela()
        r = vela.create_intent(INTENT)
        self.assertIsInstance(r, IntentCreated)
        self.assertEqual(r.intent_id, "id1")
        self.assertEqual(r.criteria.pax, 2)
        self.assertEqual(vela.repos.intents.get("id1").text, INTENT)
        assert_single_product(self, r.to_dict())

    def test_question_persists_nothing(self):
        vela = make_vela()
        r = vela.create_intent("padel a ottobre")
        self.assertIsInstance(r, IntentQuestion)
        self.assertEqual(r.question, QUESTION_PAX)
        self.assertEqual(r.say, QUESTION_PAX)
        self.assertIsNone(vela.repos.intents.get("id1"))
        assert_single_product(self, r.to_dict())

    def test_profile_is_stored_and_provides_pax(self):
        vela = make_vela()
        r = vela.create_intent("padel a ottobre", TravelerProfile(first_name="Anna", pax=2))
        self.assertIsInstance(r, IntentCreated)
        self.assertEqual(vela.repos.intents.get(r.intent_id).profile.first_name, "Anna")


class GetProposalTest(unittest.TestCase):
    def test_single_proposal_best_match(self):
        vela = make_vela()
        iid = vela.create_intent(INTENT).intent_id
        r = vela.get_proposal(iid)
        self.assertIsInstance(r, ProposalMade)
        self.assertEqual(r.product.product_id, "3")
        self.assertEqual(r.proposal.pax, 2)
        self.assertEqual(r.proposal.start_date, date(2026, 10, 1))
        self.assertFalse(r.replaced)
        assert_single_product(self, r.to_dict())
        self.assertEqual(vela.repos.proposals.get(r.proposal.id).product_id, "3")

    def test_get_twice_returns_same_proposal(self):
        vela = make_vela()
        iid = vela.create_intent(INTENT).intent_id
        first = vela.get_proposal(iid)
        second = vela.get_proposal(iid)
        self.assertEqual(first.proposal.id, second.proposal.id)
        self.assertEqual(len(vela.repos.proposals.list_for_intent(iid)), 1)

    def test_no_match_names_criterion(self):
        vela = make_vela(products=[make_product(1, sport="tennis")])
        iid = vela.create_intent(INTENT).intent_id
        r = vela.get_proposal(iid)
        self.assertIsInstance(r, NoMatch)
        self.assertEqual(r.failed_criterion, "sport")
        self.assertEqual(vela.repos.proposals.list_for_intent(iid), [])
        assert_single_product(self, r.to_dict())

    def test_unknown_intent(self):
        with self.assertRaises(NotFound) as ctx:
            make_vela().get_proposal("nope")
        self.assertEqual((ctx.exception.kind, ctx.exception.id), ("intent", "nope"))


class RejectProposalTest(unittest.TestCase):
    def test_reject_gives_a_different_product(self):
        vela = make_vela()
        iid = vela.create_intent(INTENT).intent_id
        first = vela.get_proposal(iid)
        second = vela.reject_proposal(first.proposal.id, "troppo caro")
        self.assertIsInstance(second, ProposalMade)
        self.assertNotEqual(second.product.product_id, first.product.product_id)
        self.assertEqual(second.product.product_id, "4")
        self.assertEqual(vela.repos.rejections.product_ids_for_intent(iid), {"3"})
        assert_single_product(self, second.to_dict())

    def test_never_proposes_a_rejected_product_again(self):
        vela = make_vela()
        iid = vela.create_intent(INTENT).intent_id
        seen = []
        r = vela.get_proposal(iid)
        while isinstance(r, ProposalMade):
            self.assertNotIn(r.product.product_id, seen)
            seen.append(r.product.product_id)
            r = vela.reject_proposal(r.proposal.id, "no")
        self.assertEqual(seen, ["3", "4", "2", "1"])
        self.assertEqual(r.failed_criterion, "rejected")

    def test_reject_twice_same_proposal_is_idempotent(self):
        vela = make_vela()
        iid = vela.create_intent(INTENT).intent_id
        first = vela.get_proposal(iid)
        a = vela.reject_proposal(first.proposal.id, "no")
        b = vela.reject_proposal(first.proposal.id, "no")
        self.assertEqual(a.proposal.id, b.proposal.id)
        self.assertEqual(len(vela.repos.proposals.list_for_intent(iid)), 2)

    def test_unknown_proposal(self):
        with self.assertRaises(NotFound):
            make_vela().reject_proposal("nope", "x")
```

- [ ] **Step 3: Eseguire** `python3 -m unittest tests.test_usecases -v` → `ModuleNotFoundError`.

- [ ] **Step 4: Scrivere `vela/domain/usecases.py`**:

```python
"""Orchestratore dei cinque casi d'uso di RF-39, identici su ogni superficie.

Dipende solo dalle porte: repository, HofJ e pagamenti sono iniettati. `now` e `new_id` sono
iniettabili per i test. Ogni risposta porta `say` (RF-42) e mai più di un prodotto (RF-10).
"""
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional, Union

from vela.domain import say
from vela.domain.chooser import Choice, choose
from vela.domain.intent import parse_intent
from vela.domain.models import (Intent, IntentCreated, IntentQuestion, NoMatch, Product,
                                ProductSummary, Proposal, ProposalMade, Rejection, TravelerProfile)
from vela.ports.hofj import HofJPort
from vela.ports.payments import PaymentsPort
from vela.ports.repositories import Repositories


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def random_id() -> str:
    return str(uuid.uuid4())


class NotFound(Exception):
    def __init__(self, kind: str, id: str):
        super().__init__("%s %s non trovato" % (kind, id))
        self.kind = kind
        self.id = id


def summary_of(product: Product) -> ProductSummary:
    return ProductSummary(product.id, product.title, product.destination, product.hotel)


class Vela:
    def __init__(self, repos: Repositories, hofj: HofJPort, payments: PaymentsPort,
                 defaults=None, now: Optional[Callable[[], datetime]] = None,
                 new_id: Optional[Callable[[], str]] = None):
        self.repos = repos
        self.hofj = hofj
        self.payments = payments
        self.defaults = defaults
        self.now = now or utcnow
        self.new_id = new_id or random_id

    # --- RF-01..05 -----------------------------------------------------------

    def create_intent(self, text: str, profile: Optional[TravelerProfile] = None
                      ) -> Union[IntentCreated, IntentQuestion]:
        profile = profile or TravelerProfile()
        result = parse_intent(text, profile, today=self.now().date())
        if result.question:
            return IntentQuestion(result.question, result.question)
        intent = Intent(self.new_id(), text, result.criteria, profile, self.now())
        self.repos.intents.add(intent)
        return IntentCreated(intent.id, intent.criteria, say.say_intent_created(intent.criteria))

    # --- RF-06..11 -----------------------------------------------------------

    def get_proposal(self, intent_id: str) -> Union[ProposalMade, NoMatch]:
        intent = self.repos.intents.get(intent_id)
        if intent is None:
            raise NotFound("intent", intent_id)
        return self._propose(intent)

    def reject_proposal(self, proposal_id: str, reason: str) -> Union[ProposalMade, NoMatch]:
        proposal = self.repos.proposals.get(proposal_id)
        if proposal is None:
            raise NotFound("proposal", proposal_id)
        intent = self.repos.intents.get(proposal.intent_id)
        self.repos.rejections.add(Rejection(intent.id, proposal.id, proposal.product_id,
                                            reason or "", self.now()))
        return self._propose(intent)

    def _propose(self, intent: Intent) -> Union[ProposalMade, NoMatch]:
        rejected_proposals = self.repos.rejections.proposal_ids_for_intent(intent.id)
        open_proposals = [p for p in self.repos.proposals.list_for_intent(intent.id)
                          if p.id not in rejected_proposals]
        if open_proposals:
            return self._made(open_proposals[-1])
        rejected_products = self.repos.rejections.product_ids_for_intent(intent.id)
        result = choose(self.repos.products.list_all(), intent.criteria, rejected_products,
                        today=self.now().date())
        if not isinstance(result, Choice):
            return NoMatch(intent.id, result.failed_criterion, say.say_no_match(result.failed_criterion))
        proposal = Proposal(self.new_id(), intent.id, result.product.id, result.start_date,
                            result.end_date, intent.criteria.pax or 1, result.product.price,
                            result.product.currency, result.reason, self.now())
        self.repos.proposals.add(proposal)
        return self._made(proposal, result.product)

    def _made(self, proposal: Proposal, product: Optional[Product] = None) -> ProposalMade:
        product = product or self.repos.products.get(proposal.product_id)
        summary = summary_of(product)
        return ProposalMade(proposal, summary, say.say_proposal(summary, proposal))
```

- [ ] **Step 5: Eseguire** `python3 -m unittest tests.test_usecases -v` → PASS.

- [ ] **Step 6: Commit**

```bash
git add vela/domain/usecases.py tests/support.py tests/test_usecases.py
git commit -m "Add the Vela orchestrator for intents, proposals and rejections

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Adapter replay: `ReplayHofJ` e `FakePayments`

**Files:**
- Create: `vela/adapters/hofj_replay.py`, `vela/adapters/stripe_fake.py`
- Create: `tests/test_replay_adapters.py`

**Interfaces:**
- Consumes: `load_fixture` (Task 2); porte del Task 7.
- Produces: `FIXTURE_PATH` (percorso assoluto di `fixtures/catalog.json`); `ITINERARY_PREFIX = "it-replay-"`; `ReplayHofJ(catalog_path=FIXTURE_PATH, rng=None)` che implementa `HofJPort` più `load_catalog() -> list[Product]`; `FakePayments(public_url=None, now=None)` che implementa `PaymentsPort` con url `{public_url}/replay/checkout/{order_id}`, `reference = "pi_replay_" + order_id`, scadenza a 24 h.

- [ ] **Step 1: Scrivere i test** in `tests/test_replay_adapters.py`:

```python
import random
import unittest
from datetime import date, timedelta
from decimal import Decimal

from support import NOW, make_product
from vela.adapters.hofj_replay import FIXTURE_PATH, ITINERARY_PREFIX, ReplayHofJ
from vela.adapters.stripe_fake import FakePayments
from vela.domain.models import Order, OrderStatus, TravelerProfile
from vela.ports.hofj import Customer, Pax, PaymentProof, UpstreamError

CUSTOMER = Customer("Anna", "Rossi", "a@x.it", "+39", "Via 1", "20100", "Milano", "MI", "IT")


class ReplayHofJTest(unittest.TestCase):
    def setUp(self):
        self.hofj = ReplayHofJ(rng=random.Random(42))

    def test_load_catalog_reads_the_fixture(self):
        products = self.hofj.load_catalog()
        self.assertEqual(len(products), 110)
        self.assertEqual(len([p for p in products if not p.archived]), 77)

    def test_itinerary_total_is_price_times_adults(self):
        it = self.hofj.create_itinerary(make_product(1, price=578), date(2026, 10, 1), 2, 1, "EUR")
        self.assertTrue(it.id.startswith(ITINERARY_PREFIX))
        self.assertEqual((it.total, it.currency), (Decimal("1156"), "EUR"))

    def test_customer_and_pax_round_trip_preserving_ref_ids(self):
        it = self.hofj.create_itinerary(make_product(1), date(2026, 10, 1), 2, 1, "EUR")
        self.hofj.set_customer(it.id, CUSTOMER)
        slots = self.hofj.get_pax(it.id)
        self.assertEqual([s.ref_id for s in slots], ["pax-1", "pax-2"])
        self.assertTrue(all(s.first_name is None for s in slots))
        self.hofj.set_pax(it.id, [Pax("pax-1", "Anna", "Rossi"), Pax("pax-2", "Bo", "Bi")])
        self.assertEqual(self.hofj.get_pax(it.id)[1], Pax("pax-2", "Bo", "Bi"))

    def test_unknown_itinerary_is_upstream_error(self):
        with self.assertRaises(UpstreamError):
            self.hofj.get_pax("it-replay-nope")
        with self.assertRaises(UpstreamError):
            self.hofj.set_customer("it-replay-nope", CUSTOMER)

    def test_booking_code_format_and_idempotence(self):
        it = self.hofj.create_itinerary(make_product(1), date(2026, 10, 1), 2, 1, "EUR")
        proof = PaymentProof("pi_1", "succeeded")
        code = self.hofj.create_booking(it.id, proof)
        self.assertRegex(code, r"^R-\d{6}$")
        self.assertEqual(self.hofj.create_booking(it.id, proof), code)

    def test_booking_survives_a_restart(self):
        # dopo un riavvio l'itinerario non è più in memoria: in replay la prenotazione riesce comunque (RF-27)
        code = ReplayHofJ(rng=random.Random(1)).create_booking("it-replay-abc", PaymentProof("pi", "succeeded"))
        self.assertRegex(code, r"^R-\d{6}$")

    def test_booking_rejects_foreign_itinerary(self):
        with self.assertRaises(UpstreamError):
            self.hofj.create_booking("real-123", PaymentProof("pi", "succeeded"))


class FakePaymentsTest(unittest.TestCase):
    def order(self):
        return Order("o1", "p1", "i1", "1", OrderStatus.AWAITING_PAYMENT, 2, Decimal("500"),
                     Decimal("1000"), "EUR", TravelerProfile(), NOW, NOW)

    def test_link_points_to_replay_checkout(self):
        link = FakePayments("https://vela.test/", now=lambda: NOW).create_payment_link(self.order())
        self.assertEqual(link.url, "https://vela.test/replay/checkout/o1")
        self.assertEqual(link.reference, "pi_replay_o1")
        self.assertEqual(link.expires_at, NOW + timedelta(hours=24))

    def test_default_public_url(self):
        link = FakePayments(None).create_payment_link(self.order())
        self.assertEqual(link.url, "http://localhost:8000/replay/checkout/o1")


class FixturePathTest(unittest.TestCase):
    def test_path_is_absolute_and_exists(self):
        import os
        self.assertTrue(os.path.isabs(FIXTURE_PATH))
        self.assertTrue(FIXTURE_PATH.endswith(os.path.join("fixtures", "catalog.json")))
```

- [ ] **Step 2: Eseguire** `python3 -m unittest tests.test_replay_adapters -v` → `ModuleNotFoundError`.

- [ ] **Step 3: Scrivere `vela/adapters/hofj_replay.py`**:

```python
"""Adapter replay di House of Journeys (RNF-08): nessuna chiamata esterna.

Catalogo da `fixtures/catalog.json`; itinerario sintetico con totale = prezzo × adulti;
customer e pax tenuti in memoria del processo (servono solo dentro `accept_proposal`);
prenotazione con codice `R-<6 cifre>`. `create_booking` accetta qualunque id di itinerario
replay, anche dopo un riavvio, così la ripresa di RF-27 funziona in replay.
"""
import os
import random
import uuid
from datetime import date
from typing import Dict, List, Optional

from vela.domain.catalog import load_fixture
from vela.domain.models import Product
from vela.ports.hofj import Customer, Itinerary, Pax, PaymentProof, UpstreamError

FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "fixtures", "catalog.json")
ITINERARY_PREFIX = "it-replay-"


class ReplayHofJ:
    def __init__(self, catalog_path: str = FIXTURE_PATH, rng: Optional[random.Random] = None):
        self.catalog_path = catalog_path
        self.rng = rng or random.Random()
        self._itineraries: Dict[str, dict] = {}
        self._codes: Dict[str, str] = {}

    def load_catalog(self) -> List[Product]:
        return load_fixture(self.catalog_path)

    def create_itinerary(self, product: Product, start_date: date, adults: int, rooms: int,
                         currency: str) -> Itinerary:
        iid = ITINERARY_PREFIX + uuid.uuid4().hex
        self._itineraries[iid] = {
            "product_id": product.id, "start_date": start_date, "adults": adults, "rooms": rooms,
            "customer": None, "pax": [Pax("pax-%d" % (i + 1)) for i in range(adults)],
        }
        return Itinerary(iid, product.price * adults, currency)

    def _get(self, itinerary_id: str) -> dict:
        try:
            return self._itineraries[itinerary_id]
        except KeyError:
            raise UpstreamError("itinerario sconosciuto: %s" % itinerary_id)

    def set_customer(self, itinerary_id: str, customer: Customer) -> None:
        self._get(itinerary_id)["customer"] = customer

    def get_pax(self, itinerary_id: str) -> List[Pax]:
        return list(self._get(itinerary_id)["pax"])

    def set_pax(self, itinerary_id: str, pax: List[Pax]) -> None:
        self._get(itinerary_id)["pax"] = list(pax)

    def create_booking(self, itinerary_id: str, proof: PaymentProof) -> str:
        if not itinerary_id.startswith(ITINERARY_PREFIX):
            raise UpstreamError("itinerario non replay: %s" % itinerary_id)
        if itinerary_id not in self._codes:
            self._codes[itinerary_id] = "R-%06d" % self.rng.randrange(1_000_000)
        return self._codes[itinerary_id]
```

E `vela/adapters/stripe_fake.py`:

```python
"""Pagamento finto per la modalità replay (RNF-08): il link porta a `GET /replay/checkout/{order_id}`."""
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from vela.domain.models import Order
from vela.ports.payments import PaymentLink

DEFAULT_PUBLIC_URL = "http://localhost:8000"
LINK_TTL = timedelta(hours=24)   # RF-21


class FakePayments:
    def __init__(self, public_url: Optional[str] = None,
                 now: Optional[Callable[[], datetime]] = None):
        self.base = (public_url or DEFAULT_PUBLIC_URL).rstrip("/")
        self.now = now or (lambda: datetime.now(timezone.utc))

    def create_payment_link(self, order: Order) -> PaymentLink:
        return PaymentLink("%s/replay/checkout/%s" % (self.base, order.id), self.now() + LINK_TTL,
                           "pi_replay_%s" % order.id)
```

- [ ] **Step 4: Eseguire** `python3 -m unittest tests.test_replay_adapters -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add vela/adapters/hofj_replay.py vela/adapters/stripe_fake.py tests/test_replay_adapters.py
git commit -m "Add the replay HofJ adapter and the fake payment link

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Accettazione, ordini, prenotazione in background e ripresa

**Files:**
- Modify: `vela/domain/models.py` (aggiungere `TravelerDefaults`)
- Modify: `vela/config.py` (aggiungere `DEFAULT_TRAVELER`)
- Create: `vela/domain/orders.py`, `vela/adapters/background.py`
- Modify: `vela/domain/usecases.py` (`NotFound` spostato in `orders.py`; `accept_proposal`, `get_order_status`, `self.orders`)
- Create: `tests/test_orders.py`
- Modify: `tests/test_usecases.py`

**Interfaces:**
- Produces:
  - `models.TravelerDefaults(street1, postal_code, city, region, country_code)` con i valori di default del prototipo (RF-13); `config.DEFAULT_TRAVELER = TravelerDefaults()`.
  - `orders.NotFound(kind, id)` (importato e riesportato da `usecases`); `orders.OrderService(repos, hofj, now)` con `get(order_id) -> Order`, `mark_paid(order_id, payment_ref) -> Order`, `complete_booking(order_id) -> Order`, `pending_booking_ids() -> list[str]`.
  - `background.InlineRunner(orders)` e `background.BookingRunner(orders, max_workers=2)` con `submit(order_id)`, `resume() -> list[str]` (id sottomessi), `shutdown(wait=True)`.
  - `Vela.orders: OrderService`; `Vela.accept_proposal(proposal_id, traveler=None) -> AcceptResponse | MissingTravelerData`; `Vela.get_order_status(order_id) -> OrderStatusResponse`.

- [ ] **Step 1: Aggiungere a `vela/domain/models.py`**, prima della sezione "risposte":

```python
@dataclass(frozen=True)
class TravelerDefaults:
    """Campi richiesti da HofJ ma non chiesti al viaggiatore (RF-13): vincolo del prototipo,
    documentato in ARCHITECTURE.md (M15)."""
    street1: str = "Via del Prototipo 1"
    postal_code: str = "20100"
    city: str = "Milano"
    region: str = "MI"
    country_code: str = "IT"
```

E a `vela/config.py`, in coda:

```python
from vela.domain.models import TravelerDefaults  # noqa: E402

# RF-13: default dichiarati nella configurazione, non chiesti al viaggiatore.
DEFAULT_TRAVELER = TravelerDefaults()
```

- [ ] **Step 2: Scrivere i test** in `tests/test_orders.py`:

```python
import unittest
from datetime import timedelta
from decimal import Decimal

from support import NOW, FakeHofJ
from vela.adapters.background import BookingRunner, InlineRunner
from vela.adapters.repo_memory import MemoryRepositories
from vela.domain.models import Order, OrderStatus, TravelerProfile
from vela.domain.orders import NotFound, OrderService
from vela.ports.hofj import UpstreamError


def order(oid="o1", status=OrderStatus.AWAITING_PAYMENT):
    return Order(oid, "p-" + oid, "i1", "1", status, 2, Decimal("500"), Decimal("1000"), "EUR",
                 TravelerProfile(), NOW, NOW, itinerary_id="it-1", payment_url="http://x/" + oid,
                 payment_ref="pi_replay_" + oid)


def service(*orders, hofj=None):
    repos = MemoryRepositories()
    for o in orders:
        repos.orders.add(o)
    return OrderService(repos, hofj or FakeHofJ(code="R-123456"), now=lambda: NOW + timedelta(minutes=1))


class MarkPaidTest(unittest.TestCase):
    def test_awaiting_becomes_paid_pending_booking(self):
        s = service(order())
        o = s.mark_paid("o1", "pi_real")
        self.assertEqual(o.status, OrderStatus.PAID_PENDING_BOOKING)
        self.assertEqual(o.payment_ref, "pi_real")
        self.assertEqual(o.paid_at, NOW + timedelta(minutes=1))
        self.assertEqual(s.repos.orders.get("o1"), o)

    def test_second_call_is_noop(self):
        s = service(order())
        first = s.mark_paid("o1", "pi_1")
        self.assertEqual(s.mark_paid("o1", "pi_2"), first)

    def test_other_states_untouched(self):
        s = service(order(status=OrderStatus.CONFIRMED))
        self.assertEqual(s.mark_paid("o1", "pi").status, OrderStatus.CONFIRMED)

    def test_unknown(self):
        with self.assertRaises(NotFound):
            service().mark_paid("nope", "pi")


class CompleteBookingTest(unittest.TestCase):
    def test_confirms_with_code(self):
        hofj = FakeHofJ(code="R-654321")
        s = service(order(status=OrderStatus.PAID_PENDING_BOOKING), hofj=hofj)
        o = s.complete_booking("o1")
        self.assertEqual((o.status, o.booking_code), (OrderStatus.CONFIRMED, "R-654321"))
        self.assertEqual(hofj.calls[-1][1], "it-1")
        self.assertEqual(hofj.calls[-1][2].payment_intent_id, "pi_replay_o1")
        self.assertEqual(hofj.calls[-1][2].payment_type, "full")

    def test_not_paid_is_untouched_and_no_call(self):
        hofj = FakeHofJ()
        s = service(order(), hofj=hofj)
        self.assertEqual(s.complete_booking("o1").status, OrderStatus.AWAITING_PAYMENT)
        self.assertEqual(hofj.calls, [])

    def test_confirmed_is_not_booked_twice(self):
        hofj = FakeHofJ()
        s = service(order(status=OrderStatus.PAID_PENDING_BOOKING), hofj=hofj)
        s.complete_booking("o1")
        s.complete_booking("o1")
        self.assertEqual(hofj.bookings, 1)

    def test_failure_is_recorded(self):
        s = service(order(status=OrderStatus.PAID_PENDING_BOOKING),
                    hofj=FakeHofJ(fail_booking=UpstreamError("timeout")))
        o = s.complete_booking("o1")
        self.assertEqual((o.status, o.failure_reason), (OrderStatus.BOOKING_FAILED, "timeout"))

    def test_pending_ids(self):
        s = service(order("a", OrderStatus.PAID_PENDING_BOOKING), order("b"),
                    order("c", OrderStatus.PAID_PENDING_BOOKING))
        self.assertEqual(s.pending_booking_ids(), ["a", "c"])


class RunnerTest(unittest.TestCase):
    def test_inline_runner_resume(self):
        s = service(order("a", OrderStatus.PAID_PENDING_BOOKING), order("b"))
        self.assertEqual(InlineRunner(s).resume(), ["a"])
        self.assertEqual(s.get("a").status, OrderStatus.CONFIRMED)
        self.assertEqual(s.get("b").status, OrderStatus.AWAITING_PAYMENT)

    def test_thread_runner_submit_and_resume(self):
        s = service(order("a", OrderStatus.PAID_PENDING_BOOKING),
                    order("b", OrderStatus.PAID_PENDING_BOOKING), order("c"))
        runner = BookingRunner(s)
        self.assertEqual(runner.resume(), ["a", "b"])
        runner.submit("c")
        runner.shutdown(wait=True)
        self.assertEqual([s.get(i).status for i in "abc"],
                         [OrderStatus.CONFIRMED, OrderStatus.CONFIRMED, OrderStatus.AWAITING_PAYMENT])

    def test_thread_runner_swallows_unexpected_errors(self):
        s = service(order("a", OrderStatus.PAID_PENDING_BOOKING), hofj=FakeHofJ(fail_booking=RuntimeError("boom")))
        runner = BookingRunner(s)
        runner.submit("a")
        runner.shutdown(wait=True)
        self.assertEqual(s.get("a").status, OrderStatus.PAID_PENDING_BOOKING)   # riprovato al prossimo avvio
```

- [ ] **Step 3: Eseguire** `python3 -m unittest tests.test_orders -v` → `ModuleNotFoundError`.

- [ ] **Step 4: Scrivere `vela/domain/orders.py`**:

```python
"""Macchina a stati dell'ordine (RF-20, RF-23, RF-25, RF-27, RNF-03).

`awaiting_payment` → `paid_pending_booking` (mark_paid) → `confirmed` | `booking_failed`
(complete_booking); `awaiting_payment` → `expired` (M6). Ogni transizione è idempotente: uno
stato diverso da quello atteso lascia l'ordine com'è. Retry con backoff: M5.
"""
from dataclasses import replace
from datetime import datetime
from typing import Callable, List

from vela.domain.models import Order, OrderStatus
from vela.ports.hofj import HofJError, HofJPort, PaymentProof
from vela.ports.repositories import Repositories


class NotFound(Exception):
    def __init__(self, kind: str, id: str):
        super().__init__("%s %s non trovato" % (kind, id))
        self.kind = kind
        self.id = id


class OrderService:
    def __init__(self, repos: Repositories, hofj: HofJPort, now: Callable[[], datetime]):
        self.repos = repos
        self.hofj = hofj
        self.now = now

    def get(self, order_id: str) -> Order:
        order = self.repos.orders.get(order_id)
        if order is None:
            raise NotFound("order", order_id)
        return order

    def mark_paid(self, order_id: str, payment_ref: str) -> Order:
        order = self.get(order_id)
        if order.status != OrderStatus.AWAITING_PAYMENT:
            return order
        now = self.now()
        order = replace(order, status=OrderStatus.PAID_PENDING_BOOKING, payment_ref=payment_ref,
                        paid_at=now, updated_at=now)
        self.repos.orders.save(order)
        return order

    def complete_booking(self, order_id: str) -> Order:
        order = self.get(order_id)
        if order.status != OrderStatus.PAID_PENDING_BOOKING:
            return order
        proof = PaymentProof(order.payment_ref or "", "succeeded")
        try:
            code = self.hofj.create_booking(order.itinerary_id, proof)
            order = replace(order, status=OrderStatus.CONFIRMED, booking_code=code,
                            updated_at=self.now())
        except HofJError as exc:
            order = replace(order, status=OrderStatus.BOOKING_FAILED, failure_reason=str(exc),
                            updated_at=self.now())
        self.repos.orders.save(order)
        return order

    def pending_booking_ids(self) -> List[str]:
        return self.repos.orders.ids_with_status(OrderStatus.PAID_PENDING_BOOKING)
```

- [ ] **Step 5: Scrivere `vela/adapters/background.py`**:

```python
"""Esecuzione della prenotazione dopo il pagamento (RF-27, RNF-02): thread nel processo.

`BookingRunner` sottomette `complete_booking` a un pool di thread; `resume()` riprende gli
ordini `paid_pending_booking` all'avvio. `InlineRunner` esegue subito, per i test.
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List

from vela.domain.orders import OrderService

log = logging.getLogger("vela.booking")


class InlineRunner:
    def __init__(self, orders: OrderService):
        self.orders = orders

    def submit(self, order_id: str) -> None:
        self.orders.complete_booking(order_id)

    def resume(self) -> List[str]:
        ids = self.orders.pending_booking_ids()
        for order_id in ids:
            self.submit(order_id)
        return ids

    def shutdown(self, wait: bool = True) -> None:
        pass


class BookingRunner:
    def __init__(self, orders: OrderService, max_workers: int = 2):
        self.orders = orders
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="booking")

    def _run(self, order_id: str) -> None:
        try:
            self.orders.complete_booking(order_id)
        except Exception:   # noqa: BLE001 - un thread non deve morire in silenzio
            log.exception("prenotazione dell'ordine %s non completata", order_id)

    def submit(self, order_id: str) -> None:
        self._executor.submit(self._run, order_id)

    def resume(self) -> List[str]:
        ids = self.orders.pending_booking_ids()
        for order_id in ids:
            self.submit(order_id)
        return ids

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)
```

- [ ] **Step 6: Eseguire** `python3 -m unittest tests.test_orders -v` → PASS.

- [ ] **Step 7: Aggiungere i test di accettazione** in coda a `tests/test_usecases.py`:

```python
from vela.adapters.background import InlineRunner
from vela.adapters.hofj_replay import ReplayHofJ
from vela.adapters.stripe_fake import FakePayments
from vela.config import DEFAULT_TRAVELER
from vela.domain.models import (AcceptResponse, MissingTravelerData, OrderStatus,
                                OrderStatusResponse, Participant)

FULL = TravelerProfile("Anna", "Rossi", "anna@x.it", "+390000", participants=(Participant("Bo", "Bi"),))


def accepted_vela(hofj=None):
    vela = make_vela(hofj=hofj)
    iid = vela.create_intent(INTENT).intent_id
    proposal = vela.get_proposal(iid)
    return vela, iid, proposal


class AcceptProposalTest(unittest.TestCase):
    def test_missing_data_creates_nothing(self):
        vela, _, proposal = accepted_vela()
        r = vela.accept_proposal(proposal.proposal.id, TravelerProfile(first_name="Anna"))
        self.assertIsInstance(r, MissingTravelerData)
        self.assertEqual(r.missing, ("last_name", "email", "phone",
                                     "participants[0].first_name", "participants[0].last_name"))
        self.assertIn("cognome", r.say)
        self.assertEqual(vela.hofj.calls, [])
        self.assertIsNone(vela.repos.orders.get_by_proposal(proposal.proposal.id))
        assert_single_product(self, r.to_dict())

    def test_accept_creates_itinerary_customer_pax_and_order(self):
        vela, iid, proposal = accepted_vela()
        r = vela.accept_proposal(proposal.proposal.id, FULL)
        self.assertIsInstance(r, AcceptResponse)
        self.assertEqual(r.status, OrderStatus.AWAITING_PAYMENT)
        self.assertEqual(r.total, Decimal("700"))
        self.assertFalse(r.total_differs)
        self.assertEqual(r.payment_url, "http://pay.test/" + r.order_id)
        self.assertNotIn("http", r.say)
        assert_single_product(self, r.to_dict())
        calls = [c[0] for c in vela.hofj.calls]
        self.assertEqual(calls, ["create_itinerary", "set_customer", "get_pax", "set_pax"])
        self.assertEqual(vela.hofj.calls[0][1:], ("3", date(2026, 10, 1), 2, 1, "EUR"))
        customer = vela.hofj.calls[1][2]
        self.assertEqual((customer.first_name, customer.email), ("Anna", "anna@x.it"))
        self.assertEqual((customer.city, customer.country_code), (DEFAULT_TRAVELER.city, DEFAULT_TRAVELER.country_code))
        pax = vela.hofj.calls[3][2]
        self.assertEqual([(p.ref_id, p.first_name, p.last_name) for p in pax],
                         [("ref-0", "Anna", "Rossi"), ("ref-1", "Bo", "Bi")])
        order = vela.repos.orders.get(r.order_id)
        self.assertEqual((order.itinerary_id, order.payment_ref), ("it-3", "pi_" + r.order_id))
        self.assertEqual(order.traveler.email, "anna@x.it")

    def test_real_total_is_declared_when_different(self):
        vela, _, proposal = accepted_vela(hofj=FakeHofJ(total=750))
        r = vela.accept_proposal(proposal.proposal.id, FULL)
        self.assertTrue(r.total_differs)
        self.assertEqual((r.total, r.price_from_total), (Decimal("750"), Decimal("700")))
        self.assertLess(r.say.index("750 euro"), r.say.index("link"))

    def test_double_accept_returns_same_order(self):
        vela, _, proposal = accepted_vela()
        a = vela.accept_proposal(proposal.proposal.id, FULL)
        b = vela.accept_proposal(proposal.proposal.id)
        self.assertEqual(a.to_dict(), b.to_dict())
        self.assertEqual(len([c for c in vela.hofj.calls if c[0] == "create_itinerary"]), 1)
        self.assertEqual(len(vela.payments.links), 1)

    def test_profile_from_intent_is_enough(self):
        vela = make_vela()
        iid = vela.create_intent(INTENT, FULL).intent_id
        proposal = vela.get_proposal(iid)
        self.assertIsInstance(vela.accept_proposal(proposal.proposal.id), AcceptResponse)

    def test_get_proposal_after_accept_returns_same_proposal(self):
        vela, iid, proposal = accepted_vela()
        vela.accept_proposal(proposal.proposal.id, FULL)
        again = vela.get_proposal(iid)
        self.assertEqual(again.proposal.id, proposal.proposal.id)
        self.assertEqual(len(vela.repos.proposals.list_for_intent(iid)), 1)

    def test_unknown_proposal(self):
        with self.assertRaises(NotFound):
            make_vela().accept_proposal("nope", FULL)


class OrderStatusTest(unittest.TestCase):
    def test_awaiting_payment(self):
        vela, _, proposal = accepted_vela()
        oid = vela.accept_proposal(proposal.proposal.id, FULL).order_id
        r = vela.get_order_status(oid)
        self.assertIsInstance(r, OrderStatusResponse)
        self.assertEqual((r.status, r.booking_code), (OrderStatus.AWAITING_PAYMENT, None))
        self.assertIn("attesa", r.say)
        assert_single_product(self, r.to_dict())

    def test_unknown(self):
        with self.assertRaises(NotFound):
            make_vela().get_order_status("nope")


class FullReplayFlowTest(unittest.TestCase):
    """Il flusso della roadmap M2 con gli adapter replay veri e il catalogo della fixture."""

    def make(self, repos=None):
        repos = repos or MemoryRepositories()
        hofj = ReplayHofJ()
        if repos.products.count() == 0:
            repos.products.upsert_many(hofj.load_catalog())
        return Vela(repos, hofj, FakePayments("https://vela.test"), DEFAULT_TRAVELER, now=Clock())

    def test_intent_to_confirmed(self):
        vela = self.make()
        responses = []
        created = vela.create_intent(INTENT)
        responses.append(created)
        first = vela.get_proposal(created.intent_id)
        responses.append(first)
        self.assertIsInstance(first, ProposalMade)
        second = vela.reject_proposal(first.proposal.id, "troppo caro")
        responses.append(second)
        self.assertIsInstance(second, ProposalMade)
        self.assertNotEqual(second.product.product_id, first.product.product_id)
        accepted = vela.accept_proposal(second.proposal.id, FULL)
        responses.append(accepted)
        self.assertIsInstance(accepted, AcceptResponse)
        self.assertEqual(accepted.payment_url, "https://vela.test/replay/checkout/" + accepted.order_id)
        # pagamento simulato: ciò che fa GET /replay/checkout/{order_id}
        vela.orders.mark_paid(accepted.order_id, "pi_replay_" + accepted.order_id)
        InlineRunner(vela.orders).submit(accepted.order_id)
        status = vela.get_order_status(accepted.order_id)
        responses.append(status)
        self.assertEqual(status.status, OrderStatus.CONFIRMED)
        self.assertRegex(status.booking_code, r"^R-\d{6}$")
        self.assertIn(status.booking_code, status.say)
        again = vela.accept_proposal(second.proposal.id, FULL)
        self.assertEqual(again.order_id, accepted.order_id)
        for r in responses:
            assert_single_product(self, r.to_dict())

    def test_resume_at_boot_completes_pending_booking(self):
        repos = MemoryRepositories()
        vela = self.make(repos)
        iid = vela.create_intent(INTENT, FULL).intent_id
        proposal = vela.get_proposal(iid)
        oid = vela.accept_proposal(proposal.proposal.id).order_id
        vela.orders.mark_paid(oid, "pi")   # pagato, ma il processo "muore" prima della prenotazione
        restarted = self.make(repos)       # nuovo processo: stessi repository, nuovo ReplayHofJ
        self.assertEqual(InlineRunner(restarted.orders).resume(), [oid])
        self.assertEqual(restarted.get_order_status(oid).status, OrderStatus.CONFIRMED)
```

- [ ] **Step 8: Eseguire** `python3 -m unittest tests.test_usecases -v` → i nuovi test falliscono con `AttributeError: accept_proposal`.

- [ ] **Step 9: Completare `vela/domain/usecases.py`.** Rimuovere la classe `NotFound` dal file e sostituire gli import con:

```python
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable, Optional, Union

from vela.domain import say
from vela.domain.chooser import Choice, choose
from vela.domain.intent import parse_intent
from vela.domain.models import (AcceptResponse, Intent, IntentCreated, IntentQuestion,
                                MissingTravelerData, NoMatch, Order, OrderStatus,
                                OrderStatusResponse, Product, ProductSummary, Proposal,
                                ProposalMade, Rejection, TravelerDefaults, TravelerProfile)
from vela.domain.orders import NotFound, OrderService
from vela.ports.hofj import Customer, HofJPort
from vela.ports.payments import PaymentsPort
from vela.ports.repositories import DuplicateOrder, Repositories

__all__ = ["Vela", "NotFound", "utcnow", "random_id", "summary_of"]
```

In `__init__` aggiungere dopo `self.new_id = ...`:

```python
        self.defaults = defaults or TravelerDefaults()
        self.orders = OrderService(repos, hofj, self.now)
```

(e togliere la riga `self.defaults = defaults` precedente). Aggiungere in coda alla classe:

```python
    # --- RF-12..16, RNF-03 ---------------------------------------------------

    def accept_proposal(self, proposal_id: str, traveler: Optional[TravelerProfile] = None
                        ) -> Union[AcceptResponse, MissingTravelerData]:
        proposal = self.repos.proposals.get(proposal_id)
        if proposal is None:
            raise NotFound("proposal", proposal_id)
        existing = self.repos.orders.get_by_proposal(proposal_id)
        if existing is not None:
            return self._accepted(existing)
        intent = self.repos.intents.get(proposal.intent_id)
        profile = intent.profile.merged_with(traveler or TravelerProfile())
        missing = profile.missing_fields(proposal.pax)
        if missing:
            return MissingTravelerData(proposal_id, tuple(missing), say.say_missing(missing))
        product = self.repos.products.get(proposal.product_id)
        itinerary = self.hofj.create_itinerary(product, proposal.start_date, proposal.pax, 1,
                                               proposal.currency)
        d = self.defaults
        self.hofj.set_customer(itinerary.id, Customer(
            profile.first_name, profile.last_name, profile.email, profile.phone,
            d.street1, d.postal_code, d.city, d.region, d.country_code))
        names = [(profile.first_name, profile.last_name)] + [
            (p.first_name, p.last_name) for p in profile.participants]
        slots = self.hofj.get_pax(itinerary.id)
        filled = [replace(slot, first_name=names[i][0], last_name=names[i][1])
                  if i < len(names) else slot for i, slot in enumerate(slots)]
        self.hofj.set_pax(itinerary.id, filled)
        now = self.now()
        order = Order(self.new_id(), proposal.id, intent.id, product.id,
                      OrderStatus.AWAITING_PAYMENT, proposal.pax, proposal.price_from,
                      itinerary.total, itinerary.currency, profile, now, now,
                      itinerary_id=itinerary.id)
        try:
            self.repos.orders.add(order)
        except DuplicateOrder:
            return self._accepted(self.repos.orders.get_by_proposal(proposal_id))
        link = self.payments.create_payment_link(order)
        order = replace(order, payment_url=link.url, payment_ref=link.reference,
                        updated_at=self.now())
        self.repos.orders.save(order)
        return self._accepted(order)

    def _accepted(self, order: Order) -> AcceptResponse:
        estimate = order.price_from * order.pax
        differs = order.total != estimate
        return AcceptResponse(order.id, order.status, order.total, order.currency, estimate,
                              differs, order.payment_url or "",
                              say.say_accept(order.total, estimate, differs))

    # --- RF-25, RF-26 --------------------------------------------------------

    def get_order_status(self, order_id: str) -> OrderStatusResponse:
        order = self.orders.get(order_id)
        return OrderStatusResponse(order.id, order.status, order.booking_code,
                                   say.say_status(order.status, order.booking_code,
                                                  order.failure_reason))
```

- [ ] **Step 10: Eseguire** `python3 -m unittest discover -s tests` → tutto PASS (i test Postgres saltati).

- [ ] **Step 11: Commit**

```bash
git add vela/domain/models.py vela/config.py vela/domain/orders.py vela/adapters/background.py vela/domain/usecases.py tests/test_orders.py tests/test_usecases.py
git commit -m "Add acceptance, order state machine, background booking and resume

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11: Tabelle, migrazione `0002` e repository Postgres

**Files:**
- Create: `vela/adapters/schema.py`, `vela/adapters/repo_postgres.py`
- Create: `alembic/versions/0002_domain_tables.py`
- Modify: `alembic/env.py` (importare `vela.adapters.schema` così `metadata` conosce le tabelle)
- Modify: `tests/test_migrations.py` (head `0002`)
- Create: `tests/test_repo_postgres.py`

**Interfaces:**
- Consumes: `metadata` di `vela/adapters/db.py`; contratto di `tests/repo_contract.py` (Task 7).
- Produces: `schema.products_t, intents_t, proposals_t, orders_t, rejections_t`; `PostgresRepositories(engine)` con gli stessi cinque attributi di `MemoryRepositories`. `list_all()` restituisce i prodotti **senza** `raw` (`raw == {}`); `get()` lo include.
- I test Postgres usano lo schema `vela_test` (creato se manca) tramite `options=-csearch_path=vela_test` nell'URL: non toccano le tabelle dello schema `public` usate dall'app su Render.

- [ ] **Step 1: Scrivere `vela/adapters/schema.py`**:

```python
"""Tabelle del dominio (RF-05, RF-25, RF-28) sul `metadata` condiviso di `db.py`.

Tipi neutri (JSON, Numeric, String, Date, DateTime): `tests/test_migrations.py` applica le
migrazioni anche su SQLite. Postgres è l'unico backend di produzione (RNF-01).
"""
from sqlalchemy import (JSON, Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric,
                        String, Table, Text, UniqueConstraint)

from vela.adapters.db import metadata

products_t = Table(
    "products", metadata,
    Column("id", String(32), primary_key=True),
    Column("title", Text, nullable=False),
    Column("slug", Text, nullable=False),
    Column("short_description", Text, nullable=False, default=""),
    Column("sport", String(16), nullable=False),
    Column("category", Text),
    Column("destination", Text),
    Column("country", String(2)),
    Column("venue", Text),
    Column("hotel", Text),
    Column("price", Numeric(12, 2), nullable=False),
    Column("currency", String(3), nullable=False),
    Column("min_pax", Integer),
    Column("max_pax", Integer),
    Column("min_date", Date),
    Column("max_date", Date),
    Column("availabilities", JSON, nullable=False),
    Column("duration_days", Integer),
    Column("hofj_updated_at", String(40)),
    Column("raw", JSON, nullable=False),
    Column("fetched_at", DateTime(timezone=True), nullable=False),
    Column("bookable", Boolean, nullable=False, default=True),
    Column("bookable_checked_at", DateTime(timezone=True)),
    Column("archived", Boolean, nullable=False, default=False),
    Column("provider_id", String(32)),
)

intents_t = Table(
    "intents", metadata,
    Column("id", String(36), primary_key=True),
    Column("text", Text, nullable=False),
    Column("criteria", JSON, nullable=False),
    Column("profile", JSON, nullable=False),
    Column("language", String(2), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

proposals_t = Table(
    "proposals", metadata,
    Column("id", String(36), primary_key=True),
    Column("intent_id", String(36), ForeignKey("intents.id"), nullable=False, index=True),
    Column("product_id", String(32), ForeignKey("products.id"), nullable=False),
    Column("start_date", Date, nullable=False),
    Column("end_date", Date, nullable=False),
    Column("pax", Integer, nullable=False),
    Column("price_from", Numeric(12, 2), nullable=False),
    Column("currency", String(3), nullable=False),
    Column("reason", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

orders_t = Table(
    "orders", metadata,
    Column("id", String(36), primary_key=True),
    Column("proposal_id", String(36), ForeignKey("proposals.id"), nullable=False),
    Column("intent_id", String(36), ForeignKey("intents.id"), nullable=False),
    Column("product_id", String(32), ForeignKey("products.id"), nullable=False),
    Column("status", String(24), nullable=False, index=True),
    Column("pax", Integer, nullable=False),
    Column("price_from", Numeric(12, 2), nullable=False),
    Column("total", Numeric(12, 2), nullable=False),
    Column("currency", String(3), nullable=False),
    Column("traveler", JSON, nullable=False),
    Column("itinerary_id", Text),
    Column("payment_url", Text),
    Column("payment_ref", Text),
    Column("booking_code", Text),
    Column("failure_reason", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("paid_at", DateTime(timezone=True)),
    UniqueConstraint("proposal_id", name="uq_orders_proposal_id"),   # RNF-03: un ordine per proposta
)

rejections_t = Table(
    "rejections", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("intent_id", String(36), ForeignKey("intents.id"), nullable=False, index=True),
    Column("proposal_id", String(36), ForeignKey("proposals.id"), nullable=False),
    Column("product_id", String(32), ForeignKey("products.id"), nullable=False),
    Column("reason", Text, nullable=False, default=""),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("proposal_id", name="uq_rejections_proposal_id"),
)
```

- [ ] **Step 2: Scrivere la migrazione** `alembic/versions/0002_domain_tables.py`:

```python
"""Tabelle del dominio M2: products, intents, proposals, orders, rejections.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("slug", sa.Text, nullable=False),
        sa.Column("short_description", sa.Text, nullable=False),
        sa.Column("sport", sa.String(16), nullable=False),
        sa.Column("category", sa.Text),
        sa.Column("destination", sa.Text),
        sa.Column("country", sa.String(2)),
        sa.Column("venue", sa.Text),
        sa.Column("hotel", sa.Text),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("min_pax", sa.Integer),
        sa.Column("max_pax", sa.Integer),
        sa.Column("min_date", sa.Date),
        sa.Column("max_date", sa.Date),
        sa.Column("availabilities", sa.JSON, nullable=False),
        sa.Column("duration_days", sa.Integer),
        sa.Column("hofj_updated_at", sa.String(40)),
        sa.Column("raw", sa.JSON, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bookable", sa.Boolean, nullable=False),
        sa.Column("bookable_checked_at", sa.DateTime(timezone=True)),
        sa.Column("archived", sa.Boolean, nullable=False),
        sa.Column("provider_id", sa.String(32)),
    )
    op.create_table(
        "intents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("criteria", sa.JSON, nullable=False),
        sa.Column("profile", sa.JSON, nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("intent_id", sa.String(36), sa.ForeignKey("intents.id"), nullable=False),
        sa.Column("product_id", sa.String(32), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("pax", sa.Integer, nullable=False),
        sa.Column("price_from", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_proposals_intent_id", "proposals", ["intent_id"])
    op.create_table(
        "orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("proposal_id", sa.String(36), sa.ForeignKey("proposals.id"), nullable=False),
        sa.Column("intent_id", sa.String(36), sa.ForeignKey("intents.id"), nullable=False),
        sa.Column("product_id", sa.String(32), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("pax", sa.Integer, nullable=False),
        sa.Column("price_from", sa.Numeric(12, 2), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("traveler", sa.JSON, nullable=False),
        sa.Column("itinerary_id", sa.Text),
        sa.Column("payment_url", sa.Text),
        sa.Column("payment_ref", sa.Text),
        sa.Column("booking_code", sa.Text),
        sa.Column("failure_reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("proposal_id", name="uq_orders_proposal_id"),
    )
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_table(
        "rejections",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("intent_id", sa.String(36), sa.ForeignKey("intents.id"), nullable=False),
        sa.Column("proposal_id", sa.String(36), sa.ForeignKey("proposals.id"), nullable=False),
        sa.Column("product_id", sa.String(32), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("proposal_id", name="uq_rejections_proposal_id"),
    )
    op.create_index("ix_rejections_intent_id", "rejections", ["intent_id"])


def downgrade() -> None:
    op.drop_table("rejections")
    op.drop_table("orders")
    op.drop_table("proposals")
    op.drop_table("intents")
    op.drop_table("products")
```

In `alembic/env.py`, dopo `from vela.adapters.db import metadata  # noqa: E402` aggiungere:

```python
import vela.adapters.schema  # noqa: E402,F401  registra le tabelle sul metadata
```

In `tests/test_migrations.py` sostituire ogni `["0001"]` con `["0002"]` e `self.assertIn("0001", res.stdout)` con `self.assertIn("0002", res.stdout)`.

- [ ] **Step 3: Eseguire** `python3 -m unittest tests.test_migrations -v` → PASS (SQLite crea le 5 tabelle; Postgres saltato senza `DATABASE_URL`).

- [ ] **Step 4: Scrivere i test Postgres** in `tests/test_repo_postgres.py`:

```python
"""Contratto dei repository su Postgres. Gira solo con DATABASE_URL, nello schema `vela_test`."""
import os
import unittest
from unittest.mock import patch

from repo_contract import RepositoryContract, intent, order, proposal
from support import make_product

INI = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
TEST_SCHEMA = "vela_test"


def test_url() -> str:
    from vela.config import Settings
    url = Settings.from_env().database_url
    sep = "&" if "?" in url else "?"
    return url + sep + "options=-csearch_path%3D" + TEST_SCHEMA


@unittest.skipUnless(os.environ.get("DATABASE_URL"), "serve DATABASE_URL")
class PostgresRepositoriesTest(RepositoryContract, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import text
        from vela.adapters.db import make_engine
        from vela.config import Settings
        with make_engine(Settings.from_env().database_url).begin() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS %s" % TEST_SCHEMA))
        with patch.dict(os.environ, {"DATABASE_URL": test_url()}):
            command.upgrade(Config(INI), "head")
        cls.engine = make_engine(test_url())

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def make_repos(self):
        from sqlalchemy import delete
        from vela.adapters.repo_postgres import PostgresRepositories
        from vela.adapters.schema import intents_t, orders_t, products_t, proposals_t, rejections_t
        with self.engine.begin() as conn:
            for table in (rejections_t, orders_t, proposals_t, intents_t, products_t):
                conn.execute(delete(table))
        return PostgresRepositories(self.engine)

    def test_list_all_omits_raw_but_get_includes_it(self):
        self.repos.products.upsert_many([make_product(1)])
        from dataclasses import replace
        self.repos.products.upsert_many([replace(make_product(1), raw={"big": "x" * 1000})])
        self.assertEqual(self.repos.products.list_all()[0].raw, {})
        self.assertEqual(self.repos.products.get("1").raw, {"big": "x" * 1000})

    def test_duplicate_order_leaves_repository_usable(self):
        from vela.ports.repositories import DuplicateOrder
        self.seed()
        self.repos.proposals.add(proposal())
        self.repos.orders.add(order())
        with self.assertRaises(DuplicateOrder):
            self.repos.orders.add(order("o2", "p1"))
        self.assertEqual(self.repos.orders.get("o1").id, "o1")
        self.repos.proposals.add(proposal("p9"))
        self.repos.orders.add(order("o3", "p9"))   # altra proposta: la connessione è pulita
        self.assertEqual(self.repos.orders.get_by_proposal("p9").id, "o3")
```

- [ ] **Step 5: Eseguire** `set -a; . ./.env; set +a; python3 -m unittest tests.test_repo_postgres -v` → `ModuleNotFoundError: vela.adapters.repo_postgres` (la classe viene importata dentro `make_repos`, quindi l'errore compare nei test, non all'import).

- [ ] **Step 6: Scrivere `vela/adapters/repo_postgres.py`**:

```python
"""Repository Postgres con SQLAlchemy Core (RNF-01): una transazione per metodo, nessuno stato in processo."""
from datetime import date
from typing import Iterable, List, Optional, Set

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from vela.adapters.schema import intents_t, orders_t, products_t, proposals_t, rejections_t
from vela.domain.models import (Availability, Intent, Order, OrderStatus, Product, Proposal,
                                Rejection, criteria_from_dict, criteria_to_dict,
                                profile_from_dict, profile_to_dict)
from vela.ports.repositories import DuplicateOrder


def _product_row(p: Product) -> dict:
    return {
        "id": p.id, "title": p.title, "slug": p.slug, "short_description": p.short_description,
        "sport": p.sport, "category": p.category, "destination": p.destination,
        "country": p.country, "venue": p.venue, "hotel": p.hotel, "price": p.price,
        "currency": p.currency, "min_pax": p.min_pax, "max_pax": p.max_pax,
        "min_date": p.min_date, "max_date": p.max_date,
        "availabilities": [{"start": a.start.isoformat(), "end": a.end.isoformat()}
                           for a in p.availabilities],
        "duration_days": p.duration_days, "hofj_updated_at": p.hofj_updated_at, "raw": p.raw,
        "fetched_at": p.fetched_at, "bookable": p.bookable,
        "bookable_checked_at": p.bookable_checked_at, "archived": p.archived,
        "provider_id": p.provider_id,
    }


def _product(m, raw: Optional[dict]) -> Product:
    return Product(
        id=m["id"], title=m["title"], slug=m["slug"], short_description=m["short_description"],
        sport=m["sport"], category=m["category"], destination=m["destination"],
        country=m["country"], venue=m["venue"], hotel=m["hotel"], price=m["price"],
        currency=m["currency"], min_pax=m["min_pax"], max_pax=m["max_pax"],
        min_date=m["min_date"], max_date=m["max_date"],
        availabilities=tuple(Availability(date.fromisoformat(a["start"]), date.fromisoformat(a["end"]))
                             for a in m["availabilities"]),
        duration_days=m["duration_days"], hofj_updated_at=m["hofj_updated_at"],
        raw=raw if raw is not None else {}, fetched_at=m["fetched_at"], bookable=m["bookable"],
        bookable_checked_at=m["bookable_checked_at"], archived=m["archived"],
        provider_id=m["provider_id"])


class PostgresProducts:
    def __init__(self, engine: Engine):
        self.engine = engine

    def upsert_many(self, products: Iterable[Product]) -> None:
        rows = [_product_row(p) for p in products]
        if not rows:
            return
        stmt = pg_insert(products_t).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[products_t.c.id],
            set_={c.name: stmt.excluded[c.name] for c in products_t.c if c.name != "id"})
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def count(self) -> int:
        with self.engine.connect() as conn:
            return conn.execute(select(func.count()).select_from(products_t)).scalar_one()

    def list_all(self) -> List[Product]:
        columns = [c for c in products_t.c if c.name != "raw"]
        with self.engine.connect() as conn:
            rows = conn.execute(select(*columns).order_by(products_t.c.id)).mappings().all()
        return [_product(m, None) for m in rows]

    def get(self, product_id: str) -> Optional[Product]:
        with self.engine.connect() as conn:
            m = conn.execute(select(products_t).where(products_t.c.id == product_id)).mappings().first()
        return None if m is None else _product(m, m["raw"])


class PostgresIntents:
    def __init__(self, engine: Engine):
        self.engine = engine

    def add(self, intent: Intent) -> None:
        with self.engine.begin() as conn:
            conn.execute(intents_t.insert().values(
                id=intent.id, text=intent.text, criteria=criteria_to_dict(intent.criteria),
                profile=profile_to_dict(intent.profile), language=intent.criteria.language,
                created_at=intent.created_at))

    def get(self, intent_id: str) -> Optional[Intent]:
        with self.engine.connect() as conn:
            m = conn.execute(select(intents_t).where(intents_t.c.id == intent_id)).mappings().first()
        if m is None:
            return None
        return Intent(m["id"], m["text"], criteria_from_dict(m["criteria"]),
                      profile_from_dict(m["profile"]), m["created_at"])


def _proposal(m) -> Proposal:
    return Proposal(m["id"], m["intent_id"], m["product_id"], m["start_date"], m["end_date"],
                    m["pax"], m["price_from"], m["currency"], m["reason"], m["created_at"])


class PostgresProposals:
    def __init__(self, engine: Engine):
        self.engine = engine

    def add(self, p: Proposal) -> None:
        with self.engine.begin() as conn:
            conn.execute(proposals_t.insert().values(
                id=p.id, intent_id=p.intent_id, product_id=p.product_id, start_date=p.start_date,
                end_date=p.end_date, pax=p.pax, price_from=p.price_from, currency=p.currency,
                reason=p.reason, created_at=p.created_at))

    def get(self, proposal_id: str) -> Optional[Proposal]:
        with self.engine.connect() as conn:
            m = conn.execute(select(proposals_t).where(proposals_t.c.id == proposal_id)).mappings().first()
        return None if m is None else _proposal(m)

    def list_for_intent(self, intent_id: str) -> List[Proposal]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(proposals_t).where(proposals_t.c.intent_id == intent_id)
                                .order_by(proposals_t.c.created_at, proposals_t.c.id)).mappings().all()
        return [_proposal(m) for m in rows]


def _order_row(o: Order) -> dict:
    return {
        "id": o.id, "proposal_id": o.proposal_id, "intent_id": o.intent_id,
        "product_id": o.product_id, "status": o.status.value, "pax": o.pax,
        "price_from": o.price_from, "total": o.total, "currency": o.currency,
        "traveler": profile_to_dict(o.traveler), "itinerary_id": o.itinerary_id,
        "payment_url": o.payment_url, "payment_ref": o.payment_ref,
        "booking_code": o.booking_code, "failure_reason": o.failure_reason,
        "created_at": o.created_at, "updated_at": o.updated_at, "paid_at": o.paid_at,
    }


def _order(m) -> Order:
    return Order(m["id"], m["proposal_id"], m["intent_id"], m["product_id"],
                 OrderStatus(m["status"]), m["pax"], m["price_from"], m["total"], m["currency"],
                 profile_from_dict(m["traveler"]), m["created_at"], m["updated_at"],
                 itinerary_id=m["itinerary_id"], payment_url=m["payment_url"],
                 payment_ref=m["payment_ref"], booking_code=m["booking_code"],
                 failure_reason=m["failure_reason"], paid_at=m["paid_at"])


class PostgresOrders:
    def __init__(self, engine: Engine):
        self.engine = engine

    def add(self, order: Order) -> None:
        try:
            with self.engine.begin() as conn:
                conn.execute(orders_t.insert().values(**_order_row(order)))
        except IntegrityError as exc:
            if "uq_orders_proposal_id" in str(exc.orig):
                raise DuplicateOrder(order.proposal_id) from exc
            raise

    def get(self, order_id: str) -> Optional[Order]:
        with self.engine.connect() as conn:
            m = conn.execute(select(orders_t).where(orders_t.c.id == order_id)).mappings().first()
        return None if m is None else _order(m)

    def get_by_proposal(self, proposal_id: str) -> Optional[Order]:
        with self.engine.connect() as conn:
            m = conn.execute(select(orders_t).where(orders_t.c.proposal_id == proposal_id)).mappings().first()
        return None if m is None else _order(m)

    def save(self, order: Order) -> None:
        values = {k: v for k, v in _order_row(order).items() if k != "id"}
        with self.engine.begin() as conn:
            conn.execute(update(orders_t).where(orders_t.c.id == order.id).values(**values))

    def ids_with_status(self, status: OrderStatus) -> List[str]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(orders_t.c.id).where(orders_t.c.status == status.value)
                                .order_by(orders_t.c.id)).all()
        return [r[0] for r in rows]


class PostgresRejections:
    def __init__(self, engine: Engine):
        self.engine = engine

    def add(self, r: Rejection) -> None:
        stmt = pg_insert(rejections_t).values(
            intent_id=r.intent_id, proposal_id=r.proposal_id, product_id=r.product_id,
            reason=r.reason, created_at=r.created_at).on_conflict_do_nothing(
            index_elements=[rejections_t.c.proposal_id])
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def product_ids_for_intent(self, intent_id: str) -> Set[str]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(rejections_t.c.product_id)
                                .where(rejections_t.c.intent_id == intent_id)).all()
        return {r[0] for r in rows}

    def proposal_ids_for_intent(self, intent_id: str) -> Set[str]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(rejections_t.c.proposal_id)
                                .where(rejections_t.c.intent_id == intent_id)).all()
        return {r[0] for r in rows}


class PostgresRepositories:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.products = PostgresProducts(engine)
        self.intents = PostgresIntents(engine)
        self.proposals = PostgresProposals(engine)
        self.orders = PostgresOrders(engine)
        self.rejections = PostgresRejections(engine)
```

- [ ] **Step 7: Eseguire** `set -a; . ./.env; set +a; python3 -m unittest tests.test_repo_postgres tests.test_migrations -v` → PASS. Poi `python3 -m unittest discover -s tests` senza `.env` → PASS con i test Postgres `skipped`.

- [ ] **Step 8: Commit**

```bash
git add vela/adapters/schema.py vela/adapters/repo_postgres.py alembic/versions/0002_domain_tables.py alembic/env.py tests/test_migrations.py tests/test_repo_postgres.py
git commit -m "Add the domain tables, migration 0002 and the Postgres repositories

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 12: Wiring dell'app, lifespan e `GET /replay/checkout/{order_id}`

**Files:**
- Create: `vela/surfaces/replay.py`
- Modify: `vela/app.py`
- Create: `tests/test_app_replay.py`

**Interfaces:**
- Produces: `app.build_vela(settings, engine) -> (Vela, BookingRunner, catalog_loader)` (solleva `RuntimeError` se `vela_upstream_mode != "replay"`); `app.bootstrap(vela, runner, catalog_loader) -> {"catalog_loaded": int, "resumed": list[str]}`; `create_app(settings=None, vela=None, runner=None, catalog_loader=None)`; `app.state.vela`, `app.state.runner`, `app.state.catalog_loader`, `app.state.bootstrap` (dopo lo startup); router `replay` montato solo in replay.

- [ ] **Step 1: Scrivere i test** in `tests/test_app_replay.py`:

```python
import random
import unittest
from datetime import timedelta
from urllib.parse import urlparse

from fastapi.testclient import TestClient

from support import NOW
from vela.adapters.background import InlineRunner
from vela.adapters.hofj_replay import ReplayHofJ
from vela.adapters.repo_memory import MemoryRepositories
from vela.adapters.stripe_fake import FakePayments
from vela.app import create_app
from vela.config import DEFAULT_TRAVELER, Settings
from vela.domain.models import OrderStatus, Participant, TravelerProfile
from vela.domain.usecases import Vela

INTENT = "un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro"
FULL = TravelerProfile("Anna", "Rossi", "anna@x.it", "+390000", participants=(Participant("Bo", "Bi"),))


class Clock:
    def __init__(self):
        self.at = NOW

    def __call__(self):
        self.at += timedelta(seconds=1)
        return self.at


def make_app(preload=False):
    repos = MemoryRepositories()
    hofj = ReplayHofJ(rng=random.Random(7))
    if preload:
        repos.products.upsert_many(hofj.load_catalog())
    vela = Vela(repos, hofj, FakePayments("http://test"), DEFAULT_TRAVELER, now=Clock())
    app = create_app(Settings(vela_upstream_mode="replay", vela_public_url="http://test"),
                     vela=vela, runner=InlineRunner(vela.orders), catalog_loader=hofj.load_catalog)
    return app, vela


def paid_order(vela):
    iid = vela.create_intent(INTENT, FULL).intent_id
    proposal = vela.get_proposal(iid)
    return vela.accept_proposal(proposal.proposal.id)


class BootstrapTest(unittest.TestCase):
    def test_loads_fixture_when_catalog_is_empty(self):
        app, vela = make_app()
        with TestClient(app):
            self.assertEqual(vela.repos.products.count(), 110)
            self.assertEqual(app.state.bootstrap["catalog_loaded"], 110)

    def test_does_not_reload_when_catalog_exists(self):
        app, vela = make_app(preload=True)
        with TestClient(app):
            self.assertEqual(app.state.bootstrap["catalog_loaded"], 0)
            self.assertEqual(vela.repos.products.count(), 110)

    def test_resumes_pending_bookings(self):
        app, vela = make_app(preload=True)
        oid = paid_order(vela).order_id
        vela.orders.mark_paid(oid, "pi")
        with TestClient(app):
            self.assertEqual(app.state.bootstrap["resumed"], [oid])
            self.assertEqual(vela.get_order_status(oid).status, OrderStatus.CONFIRMED)


class CheckoutTest(unittest.TestCase):
    def test_checkout_marks_paid_and_books(self):
        app, vela = make_app(preload=True)
        with TestClient(app) as c:
            accepted = paid_order(vela)
            self.assertTrue(accepted.payment_url.startswith("http://test/replay/checkout/"))
            r = c.get(urlparse(accepted.payment_url).path)
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertEqual(body["order_id"], accepted.order_id)
            self.assertEqual(body["status"], "paid_pending_booking")
            self.assertIn("Pagamento", body["say"])
            status = vela.get_order_status(accepted.order_id)
            self.assertEqual(status.status, OrderStatus.CONFIRMED)
            self.assertRegex(status.booking_code, r"^R-\d{6}$")

    def test_second_visit_has_no_effect(self):
        app, vela = make_app(preload=True)
        with TestClient(app) as c:
            accepted = paid_order(vela)
            path = urlparse(accepted.payment_url).path
            c.get(path)
            code = vela.get_order_status(accepted.order_id).booking_code
            r = c.get(path)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["status"], "confirmed")
            self.assertIn(code, r.json()["say"])
            self.assertEqual(vela.get_order_status(accepted.order_id).booking_code, code)
            self.assertEqual(len(vela.hofj._codes), 1)

    def test_unknown_order_is_404(self):
        app, _ = make_app(preload=True)
        with TestClient(app) as c:
            self.assertEqual(c.get("/replay/checkout/nope").status_code, 404)

    def test_health_still_works(self):
        app, _ = make_app(preload=True)
        with TestClient(app) as c:
            self.assertEqual(c.get("/health").status_code, 503)   # nessun DATABASE_URL nei test


class ModeTest(unittest.TestCase):
    def test_replay_router_absent_in_live(self):
        app = create_app(Settings(vela_upstream_mode="live"))
        self.assertNotIn("/replay/checkout/{order_id}", [getattr(r, "path", None) for r in app.routes])

    def test_live_with_database_is_refused(self):
        with self.assertRaises(RuntimeError) as ctx:
            create_app(Settings(database_url="sqlite://", vela_upstream_mode="live"))
        self.assertIn("M5", str(ctx.exception))

    def test_replay_without_database_has_no_domain(self):
        app = create_app(Settings())
        self.assertIsNone(app.state.vela)
        with TestClient(app) as c:
            self.assertEqual(c.get("/replay/checkout/x").status_code, 503)

    def test_replay_with_database_builds_domain(self):
        app = create_app(Settings(database_url="sqlite://"))
        self.assertIsNotNone(app.state.vela)
        self.assertIsNotNone(app.state.runner)
        self.assertTrue(callable(app.state.catalog_loader))
```

- [ ] **Step 2: Eseguire** `python3 -m unittest tests.test_app_replay -v` → errori (`create_app` non accetta `vela`).

- [ ] **Step 3: Scrivere `vela/surfaces/replay.py`**:

```python
"""``GET /replay/checkout/{order_id}``: il "pagamento" della modalità replay (RNF-08).

Segna l'ordine come pagato e avvia la prenotazione in background. Montato solo con
``VELA_UPSTREAM_MODE=replay``. Risposta JSON, nessuna pagina: la sola pagina web del
progetto è il Checkout di Stripe (spec §6).
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from vela.domain.models import OrderStatus
from vela.domain.orders import NotFound
from vela.domain.say import say_paid, say_status

router = APIRouter()


@router.get("/replay/checkout/{order_id}")
def replay_checkout(order_id: str, request: Request) -> JSONResponse:
    vela = request.app.state.vela
    if vela is None:
        raise HTTPException(status_code=503, detail="dominio non disponibile: DATABASE_URL mancante")
    try:
        order = vela.orders.mark_paid(order_id, "pi_replay_" + order_id)
    except NotFound:
        raise HTTPException(status_code=404, detail="ordine sconosciuto")
    if order.status == OrderStatus.PAID_PENDING_BOOKING:
        request.app.state.runner.submit(order_id)
        say = say_paid()
    else:
        say = say_status(order.status, order.booking_code, order.failure_reason)
    return JSONResponse({"order_id": order_id, "status": order.status.value, "say": say})
```

- [ ] **Step 4: Riscrivere `vela/app.py`**:

```python
"""App FastAPI di Vela: un solo processo per REST, MCP e webhook (RNF-02).

``create_app`` è la factory usata dai test; ``app`` è l'istanza per ``uvicorn vela.app:app``.
In replay il dominio è costruito su Postgres con gli adapter finti; il lifespan carica il
catalogo dalla fixture se la tabella è vuota e riprende le prenotazioni pendenti (RF-27).
"""
from contextlib import asynccontextmanager
from typing import Callable, List, Optional, Tuple

from fastapi import FastAPI
from sqlalchemy.engine import Engine

from vela.adapters.background import BookingRunner
from vela.adapters.db import make_engine
from vela.adapters.hofj_replay import ReplayHofJ
from vela.adapters.repo_postgres import PostgresRepositories
from vela.adapters.stripe_fake import FakePayments
from vela.config import DEFAULT_TRAVELER, Settings
from vela.domain.models import Product
from vela.domain.usecases import Vela
from vela.surfaces.health import router as health_router
from vela.surfaces.replay import router as replay_router

REPLAY = "replay"
CatalogLoader = Callable[[], List[Product]]


def build_vela(settings: Settings, engine: Engine) -> Tuple[Vela, BookingRunner, CatalogLoader]:
    if settings.vela_upstream_mode != REPLAY:
        raise RuntimeError("VELA_UPSTREAM_MODE=%s non disponibile prima di M5: usare replay"
                           % settings.vela_upstream_mode)
    hofj = ReplayHofJ()
    vela = Vela(PostgresRepositories(engine), hofj, FakePayments(settings.vela_public_url),
                DEFAULT_TRAVELER)
    return vela, BookingRunner(vela.orders), hofj.load_catalog


def bootstrap(vela: Vela, runner, catalog_loader: Optional[CatalogLoader]) -> dict:
    loaded = 0
    if catalog_loader is not None and vela.repos.products.count() == 0:
        products = catalog_loader()
        vela.repos.products.upsert_many(products)
        loaded = len(products)
    return {"catalog_loaded": loaded, "resumed": runner.resume()}


def create_app(settings: Optional[Settings] = None, vela: Optional[Vela] = None, runner=None,
               catalog_loader: Optional[CatalogLoader] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url) if settings.database_url else None
    if vela is None and engine is not None:
        vela, runner, catalog_loader = build_vela(settings, engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.vela is not None:
            app.state.bootstrap = bootstrap(app.state.vela, app.state.runner, app.state.catalog_loader)
        yield
        if app.state.runner is not None:
            app.state.runner.shutdown(wait=False)

    app = FastAPI(title="Vela", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.vela = vela
    app.state.runner = runner
    app.state.catalog_loader = catalog_loader
    app.state.bootstrap = None
    app.include_router(health_router)
    if settings.vela_upstream_mode == REPLAY:
        app.include_router(replay_router)
    return app


app = create_app()
```

- [ ] **Step 5: Eseguire** `python3 -m unittest tests.test_app_replay tests.test_health -v` → PASS. Poi l'intera suite: `python3 -m unittest discover -s tests` → PASS.

- [ ] **Step 6: Commit**

```bash
git add vela/app.py vela/surfaces/replay.py tests/test_app_replay.py
git commit -m "Wire the replay domain into the app with catalog bootstrap and the fake checkout

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 13: Documentazione, decisioni e verifica finale

**Files:**
- Modify: `README.md`, `docs/decisions.md`

- [ ] **Step 1: Aggiornare `README.md`.** Sostituire la riga `Stato: M0 (fondamenta). L'app espone solo GET /health.` con:

```markdown
Stato: M2 (dominio e replay). L'app espone `GET /health` e, in replay, `GET /replay/checkout/{order_id}`
(pagamento simulato). I cinque casi d'uso (`create_intent`, `get_proposal`, `reject_proposal`,
`accept_proposal`, `get_order_status`) vivono in `vela/domain/usecases.py` e arrivano su MCP (M3) e REST (M4).
```

Nella sezione "Avvio in locale", dopo il blocco di codice aggiungere:

```markdown
In replay, al primo avvio con la tabella `products` vuota, l'app carica `fixtures/catalog.json`
(110 prodotti) e riprende gli ordini `paid_pending_booking`. `VELA_UPSTREAM_MODE=live` è rifiutato
fino a M5.
```

Nella sezione "Test", dopo "altrimenti vengono saltati." aggiungere:

```markdown
I test Postgres lavorano nello schema `vela_test` (creato se manca) e non toccano le tabelle
dell'app. Per eseguirli in locale: `set -a; . ./.env; set +a; python3 -m unittest discover -s tests`
in una sola riga, senza stampare le variabili.
```

Nella tabella delle variabili: `VELA_PUBLIC_URL` → `| VELA_PUBLIC_URL | in replay su Render | URL pubblico di Vela: base del link di checkout replay (M2) e dei ritorni Stripe (M6). Senza, i link puntano a http://localhost:8000. |`.

Nella "Struttura" aggiornare le righe:

```
vela/domain     modelli, parser, chooser, frasi say, ordini, casi d'uso (M2)
vela/ports      HofJPort, PaymentsPort, repository (M2)
vela/adapters   db.py, repository memoria/Postgres, replay HofJ, pagamento finto, runner (M2); HofJ HTTP (M5), Stripe (M6)
vela/surfaces   health.py, replay.py (M2), MCP (M3), REST (M4), webhook (M6)
```

- [ ] **Step 2: Aggiornare `docs/decisions.md`.** Aggiungere in coda una sezione `## 2026-09-25 — M2: decisioni prese durante l'esecuzione` con una tabella `| Decisione | Scelta | Motivo |` che contenga almeno: (a) schema Postgres `vela_test` per i test dei repository, motivo: i test svuotano le tabelle e non devono toccare i dati dell'app su Render; (b) `list_all()` dei prodotti senza `raw`, motivo: il chooser non ne ha bisogno e il JSON grezzo pesa ~1 MB; (c) `create_booking` replay accetta qualunque id `it-replay-*`, motivo: la ripresa di RF-27 dopo un riavvio non ha più l'itinerario in memoria; (d) `TravelerDefaults` definita nel dominio con i valori di default, `DEFAULT_TRAVELER` in `config.py`, motivo: il dominio non importa la configurazione; più ogni altra scelta fatta dall'esecutore che devii da questo piano.

- [ ] **Step 3: Verifica finale.** Eseguire, in quest'ordine, e riportare l'esito nel messaggio di chiusura:

```bash
python3 -m unittest discover -s tests                                    # senza DATABASE_URL: verde, Postgres skipped
set -a; . ./.env; set +a; python3 -m unittest discover -s tests          # con Postgres: verde, nessuno skipped tra i repository
git grep -n "http" -- vela/domain/say.py                                 # nessun URL nelle frasi
git grep -n -E "fastapi|sqlalchemy|httpx" -- vela/domain vela/ports      # nessun import di infrastruttura nel dominio
git status --short                                                       # pulito
```

- [ ] **Step 4: Commit**

```bash
git add README.md docs/decisions.md
git commit -m "Document the M2 domain, replay checkout and Postgres test schema

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 5 (con l'utente, dopo il merge su `master`):** Render ridistribuisce; il log del deploy mostra `Running upgrade 0001 -> 0002`; `curl https://vela-n506.onrender.com/health` → 200. Registrare l'esito in `docs/decisions.md` come per M0 ("Deploy M2 verificato").

---

## Copertura dei test di completamento della roadmap M2

| Test di completamento (roadmap) | Dove |
|---|---|
| Parser: tabella di intenti it/en → criteri attesi, incluso §10.1 | Task 4 `tests/test_intent.py::TableTest` (prima riga = §10.1) |
| Chooser: mai rifiutato, archiviato o non prenotabile; ordinamento; messaggio RF-09 | Task 5 `ExclusionTest`, `OrderingTest`; Task 6 `test_no_match_covers_every_criterion`; Task 8 `test_never_proposes_a_rejected_product_again` |
| Orchestratore con porte in memoria: intento → proposta → rifiuto → proposta diversa → accettazione → pagamento simulato → `confirmed` con codice | Task 10 `FullReplayFlowTest::test_intent_to_confirmed` (adapter replay veri, fixture reale) |
| Doppio accept → stesso ordine | Task 10 `test_double_accept_returns_same_order`, e dentro il flusso completo |
| Ripresa all'avvio di un `paid_pending_booking` | Task 10 `test_resume_at_boot_completes_pending_booking`; Task 12 `BootstrapTest::test_resumes_pending_bookings` |
| Invariante RF-10 su ogni risposta | `assert_single_product` in ogni test di risposta (Task 8, 10) e su tutte le risposte del flusso completo |
| Test dei repository Postgres solo con `DATABASE_URL` | Task 11 `tests/test_repo_postgres.py` (skip senza), stesso contratto del repository in memoria |
| Modalità replay contro Postgres: fixture caricata, itinerario simulato, pagamento via link | Task 12 `BootstrapTest`, `CheckoutTest` (repository in memoria); Task 11 per la persistenza; Step 5 del Task 13 su Render |

## Requisiti coperti

RF-01, RF-02 (minimo), RF-04, RF-05 (Task 4, 8); RF-06, RF-07 (v1), RF-08 (base), RF-09, RF-10, RF-11 (Task 5, 8); RF-12, RF-13, RF-15, RF-16 (Task 10); RF-25, RF-26, RF-27 (Task 10, 12); RF-39, RF-42 (Task 1, 6, 8, 10); RNF-01 (Task 11), RNF-02 (Task 10, 12), RNF-03 (Task 7, 10, 11), RNF-08 (Task 9, 12). RF-14 e RF-23 sono esercitati contro la porta replay; la chiamata reale è M5.

## Fuori scope (task successive)

- RF-17 sostituzione della proposta su `ProductError` e RF-33/34 `bookable` (M5): le classi di errore e i campi esistono, la logica no.
- Retry con backoff di `create_booking` (RF-24, M5): oggi un errore porta subito a `booking_failed`; la ripresa al boot riprova solo gli ordini rimasti `paid_pending_booking`.
- Scadenza dei link e stato `expired` (RF-21, M6): la transizione è definita, nessun job la esegue.
- Interpretazione dei motivi di rifiuto, intervalli di date, fallback Haiku (M9); ordinamento su geohierarchy e durata (M11); frasi `say` in inglese (M9).
- Nessuna superficie MCP o REST (M3, M4): i casi d'uso si chiamano solo da Python e dai test.
