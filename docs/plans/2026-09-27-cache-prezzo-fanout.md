# Cache del prezzo con fanout: piano di implementazione

> **Per chi esegue:** sotto-skill richiesta: superpowers:subagent-driven-development (consigliata)
> o superpowers:executing-plans, un task alla volta. I passi usano le checkbox (`- [ ]`).

**Obiettivo:** N accettazioni identiche nello stesso picco costano 5 chiamate HofJ per il prezzo
invece di 5·N, e chi rifiuta il prezzo in cache non costa chiamate.

**Architettura:** una tabella Postgres `price_quotes` per chiave (prodotto, data, adulti, camere,
valuta) dietro una porta `QuoteRepository`. `accept_proposal` risponde dalla cache (hit), elegge
un leader che fa il carrello, oppure aggancia l'ordine al prezzo in volo. Il job del leader
pubblica il prezzo e sblocca gli agganciati nella stessa transazione. Gli ordini serviti dalla
cache creano il carrello solo dopo il sì. Se il leader esce senza prezzo, gli agganciati tornano
ordini normali.

**Tecnologie:** Python 3.12, SQLAlchemy Core, Alembic, unittest (`uv run`), ruff.

**Spec:** `docs/superpowers/specs/2026-09-27-cache-prezzo-fanout-design.md`: leggila prima di
iniziare, il piano argomenta da lì.

## Vincoli globali

- Il link porta sempre il totale reale del carrello del viaggiatore (RF-16).
- Nessun servizio nuovo, nessuna dipendenza nuova: cache in Postgres, in memoria nei test.
- Interfacce pubbliche invariate: REST, MCP, campi di `OrderStatusResponse`.
- Migrazione `0015`, `down_revision = "0011"` (0012-0014 sono riservate a M21-C, M21-F, M22).
- `Settings.price_quote_ttl_seconds = 900`; il costruttore di `Vela` ha default `0` = cache e
  fanout spenti, accettazione identica a oggi.
- Requisito nuovo: **RF-84**.
- Nessuna chiamata esterna nei test. Test: `uv run python3 -m unittest discover -s tests`.
  Lint: `uv run ruff check .`. Entrambi verdi prima di ogni commit.
- Commenti e docstring in italiano, come il codice intorno. Messaggi di commit in inglese, come
  la storia del repo, chiusi da `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- `agent-log/` non si tocca a mano.
- Test Postgres solo con `DATABASE_URL` verso un database usa e getta.

## Punti da guardare in review

1. **Due accettazioni identiche nello stesso istante** su più istanze: un solo leader, un solo
   carrello. Test: `test_quote_concurrent_claim_has_one_winner` (Task 1, contratto, gira anche
   su Postgres).
2. **Il leader pubblica mentre un agganciato controlla se è vivo**: nessun rilascio per errore,
   perché `publish` avviene prima che il leader lasci `queued`. Test:
   `test_leader_publishes_before_leaving_queued` (Task 2).
3. **Accettazione che perde il `claim` proprio mentre un leader pubblica**: l'ordine prende
   subito il prezzo invece di restare agganciato a una riga già `ready`. Test:
   `test_lost_claim_after_publish_takes_the_price` (Task 2).
4. **Prezzo cambiato tra la cache e il carrello**: nessun link con un importo diverso da quello
   confermato. Test: `test_confirm_without_cart_asks_again_when_price_changed` (Task 3).
5. **Leader che sparisce senza rilascio** (crash): gli agganciati non restano bloccati. Test:
   `test_follower_unsticks_when_leader_left_without_release` (Task 4).

---

## Mappa dei file

| File | Cosa cambia |
|---|---|
| `vela/domain/models.py` | `QuoteStatus`, `QuoteKey`, `PriceQuote`; `Order.follows_quote`, `Order.confirmed_total` |
| `vela/ports/repositories.py` | porta `QuoteRepository`; `Repositories.quotes` |
| `vela/adapters/schema.py` | `price_quotes_t`; due colonne su `orders_t` |
| `alembic/versions/0015_price_quotes.py` | nuova migrazione |
| `vela/adapters/repo_memory.py` | `MemoryQuotes`; `MemoryRepositories.quotes` |
| `vela/adapters/repo_postgres.py` | `PostgresQuotes`; colonne nuove in `_order_row`/`_order` |
| `vela/domain/quotes.py` | nuovo: `quote_key`, `release_quote`, `unstick` |
| `vela/domain/usecases.py` | `accept_proposal` (hit, leader, agganciato), `_confirm`, `_await_progress`, `_queue_position`, `get_order_status`, `_cancel_unpaid_order` |
| `vela/domain/purchase.py` | passo 3: `publish`, confronto con `confirmed_total`; `release_quote` nelle uscite |
| `vela/domain/say.py` | `say_price_changed_since` |
| `vela/config.py`, `vela/app.py` | `price_quote_ttl_seconds` e cablaggio |
| `loadtest/journey.py` | accettazione `200 awaiting_confirmation` |
| `tests/repo_contract.py`, `tests/test_repo_postgres.py`, `tests/test_migrations.py` | contratto e migrazione |
| `tests/test_price_quotes.py` | nuovo: flussi del dominio |
| `tests/test_say.py`, `tests/test_config.py`, `tests/test_loadtest_journey.py` | casi nuovi |
| `docs/spec.md`, `docs/decisions.md`, `docs/roadmap.md`, `loadtest/README.md` | RF-84 e decisioni |

---

### Task 1: Dati e repository della cache

**File:**
- Modifica: `vela/domain/models.py`, `vela/ports/repositories.py`, `vela/adapters/schema.py`,
  `vela/adapters/repo_memory.py`, `vela/adapters/repo_postgres.py`
- Crea: `alembic/versions/0015_price_quotes.py`
- Test: `tests/repo_contract.py`, `tests/test_repo_postgres.py`, `tests/test_migrations.py`

**Interfacce prodotte:**
- `QuoteKey(product_id: str, start_date: date, adults: int, rooms: int, currency: str)` (NamedTuple)
- `QuoteStatus.PENDING | READY`; `PriceQuote(key, status, leader_order_id, updated_at, total=None, priced_at=None)`
- `Order.follows_quote: bool = False`, `Order.confirmed_total: Optional[Decimal] = None`
- `repos.quotes.get(key) -> Optional[PriceQuote]`
- `repos.quotes.claim(key, order_id, now, fresh_after) -> bool`
- `repos.quotes.publish(key, leader_order_id, total, now) -> List[str]` (id degli ordini sbloccati)
- `repos.quotes.release(key, leader_order_id) -> List[Order]` (ordini sganciati)

- [ ] **Passo 1: test di contratto che falliscono**

In `tests/repo_contract.py` aggiungi all'import `QuoteKey, QuoteStatus` da `vela.domain.models`,
poi dopo `test_concurrent_save_if_status_has_one_winner`:

```python
    # cache del prezzo (RF-84)
    KEY = QuoteKey("1", date(2026, 10, 1), 2, 1, "EUR")

    def quote_world(self, n, follows=True):
        """`n` ordini `queued` sulla stessa chiave: prodotto 1, 1 ottobre, 2 adulti, 1 camera."""
        self.seed()
        for i in range(1, n + 1):
            self.repos.proposals.add(proposal("p%d" % i))
            self.repos.orders.add(replace(order("o%d" % i, "p%d" % i), status=OrderStatus.QUEUED,
                                          total=None, itinerary_id=None, rooms=1,
                                          enqueued_at=NOW + timedelta(seconds=i),
                                          follows_quote=follows))

    def test_order_roundtrip_with_quote_fields(self):
        self.seed()
        self.repos.proposals.add(proposal())
        o = replace(order(), follows_quote=True, confirmed_total=Decimal("700"))
        self.repos.orders.add(o)
        self.assertEqual(self.repos.orders.get("o1"), o)

    def test_quote_claim_first_wins_then_refused_while_leader_queued(self):
        self.quote_world(2)
        self.assertIsNone(self.repos.quotes.get(self.KEY))
        self.assertTrue(self.repos.quotes.claim(self.KEY, "o1", NOW, NOW - timedelta(minutes=15)))
        q = self.repos.quotes.get(self.KEY)
        self.assertEqual((q.status, q.leader_order_id, q.total), (QuoteStatus.PENDING, "o1", None))
        self.assertFalse(self.repos.quotes.claim(self.KEY, "o2", NOW, NOW - timedelta(minutes=15)))
        self.assertEqual(self.repos.quotes.get(self.KEY).leader_order_id, "o1")

    def test_quote_claim_takes_over_when_leader_not_queued(self):
        self.quote_world(2)
        self.repos.quotes.claim(self.KEY, "o1", NOW, NOW)
        self.repos.orders.save(replace(self.repos.orders.get("o1"), status=OrderStatus.FAILED))
        self.assertTrue(self.repos.quotes.claim(self.KEY, "o2", NOW, NOW))
        self.assertEqual(self.repos.quotes.get(self.KEY).leader_order_id, "o2")

    def test_quote_claim_refuses_fresh_ready_and_takes_expired(self):
        self.quote_world(2)
        self.repos.quotes.publish(self.KEY, "o1", Decimal("700"), NOW)
        self.assertFalse(self.repos.quotes.claim(self.KEY, "o2", NOW, NOW - timedelta(minutes=15)))
        self.assertTrue(self.repos.quotes.claim(self.KEY, "o2", NOW + timedelta(minutes=16),
                                                NOW + timedelta(minutes=1)))
        q = self.repos.quotes.get(self.KEY)
        self.assertEqual((q.status, q.total, q.priced_at), (QuoteStatus.PENDING, None, None))

    def test_quote_publish_fans_out_only_to_followers_of_the_key(self):
        self.quote_world(3)
        self.repos.quotes.claim(self.KEY, "o1", NOW, NOW)
        self.repos.orders.save(replace(self.repos.orders.get("o1"), follows_quote=False))
        other = replace(self.repos.orders.get("o3"), rooms=2)          # altra chiave
        self.repos.orders.save(other)
        later = NOW + timedelta(seconds=30)
        ids = self.repos.quotes.publish(self.KEY, "o1", Decimal("700"), later)
        self.assertEqual(ids, ["o2"])
        o2 = self.repos.orders.get("o2")
        self.assertEqual((o2.status, o2.total, o2.follows_quote, o2.updated_at),
                         (OrderStatus.AWAITING_CONFIRMATION, Decimal("700"), False, later))
        self.assertEqual(self.repos.orders.get("o1").status, OrderStatus.QUEUED)   # il leader no
        self.assertEqual(self.repos.orders.get("o3"), other)
        q = self.repos.quotes.get(self.KEY)
        self.assertEqual((q.status, q.total, q.priced_at), (QuoteStatus.READY, Decimal("700"), later))

    def test_quote_release_only_by_pending_leader_and_frees_followers(self):
        self.quote_world(3)
        self.repos.quotes.claim(self.KEY, "o1", NOW, NOW)
        self.repos.orders.save(replace(self.repos.orders.get("o1"), follows_quote=False))
        self.assertEqual(self.repos.quotes.release(self.KEY, "o2"), [])   # non è il leader
        freed = self.repos.quotes.release(self.KEY, "o1")
        self.assertEqual([o.id for o in freed], ["o2", "o3"])
        self.assertTrue(all(not o.follows_quote for o in freed))
        self.assertEqual(freed[0].enqueued_at, NOW + timedelta(seconds=2))
        self.assertFalse(self.repos.orders.get("o2").follows_quote)
        self.assertIsNone(self.repos.quotes.get(self.KEY))
        self.assertEqual(self.repos.quotes.release(self.KEY, "o1"), [])   # una volta sola

    def test_quote_release_ignores_ready_rows(self):
        self.quote_world(1)
        self.repos.quotes.publish(self.KEY, "o1", Decimal("700"), NOW)
        self.assertEqual(self.repos.quotes.release(self.KEY, "o1"), [])
        self.assertEqual(self.repos.quotes.get(self.KEY).status, QuoteStatus.READY)

    def test_quote_concurrent_claim_has_one_winner(self):
        self.quote_world(THREADS)
        results = all_at_once(lambda i: self.repos.quotes.claim(self.KEY, "o%d" % (i + 1), NOW, NOW))
        self.assertEqual(results.count(True), 1, results)
        winner = "o%d" % (results.index(True) + 1)
        self.assertEqual(self.repos.quotes.get(self.KEY).leader_order_id, winner)
```

In `tests/test_repo_postgres.py`, in `make_repos`, importa anche `price_quotes_t` e mettilo per
primo nella tupla delle tabelle da svuotare:
`for table in (price_quotes_t, jobs_t, quota_window_t, rejections_t, orders_t, proposals_t, intents_t, products_t):`.

In `tests/test_migrations.py` sostituisci `"0011"` con `"0015"` nelle righe che controllano la
testa (`test_single_head_is_initial_revision`, `test_ini_paths_do_not_depend_on_cwd`,
`test_upgrade_head_then_downgrade_base` e il test Postgres verso la riga 264); **non** toccare
`command.upgrade(alembic_config(), "0011")` del test di M21-D. Nel test SQLite, dopo le
asserzioni sulle colonne di `orders`, aggiungi:

```python
                    self.assertIn("price_quotes", tables)
                    self.assertFalse(order_cols["follows_quote"]["nullable"])
                    self.assertTrue(order_cols["confirmed_total"]["nullable"])
```

- [ ] **Passo 2: verifica che falliscano**

Run: `uv run python3 -m unittest tests.test_repo_memory tests.test_migrations -v 2>&1 | tail -20`
Atteso: errori `ImportError: cannot import name 'QuoteKey'` e testa `0011` ≠ `0015`.

- [ ] **Passo 3: modelli**

In `vela/domain/models.py` aggiungi `NamedTuple` all'import di `typing`
(`from typing import NamedTuple, Optional`). In fondo a `Order` aggiungi:

```python
    follows_quote: bool = False                       # RF-84: agganciato a un prezzo in volo, senza job
    confirmed_total: Optional[Decimal] = None         # RF-84: totale confermato prima del carrello
```

Dopo la classe `Order`:

```python
class QuoteStatus(str, Enum):
    """RF-84: prezzo in volo (`pending`, un leader sta facendo il carrello) o letto (`ready`)."""
    PENDING = "pending"
    READY = "ready"


class QuoteKey(NamedTuple):
    """RF-84: due ordini con la stessa chiave hanno per HofJ lo stesso carrello, a meno di
    cliente e passeggeri, quindi lo stesso prezzo."""
    product_id: str
    start_date: date
    adults: int
    rooms: int
    currency: str


@dataclass(frozen=True)
class PriceQuote:
    key: QuoteKey
    status: QuoteStatus
    leader_order_id: str
    updated_at: datetime
    total: Optional[Decimal] = None
    priced_at: Optional[datetime] = None    # base del TTL, solo `ready`
```

- [ ] **Passo 4: porta**

In `vela/ports/repositories.py`: import `from decimal import Decimal`; aggiungi `PriceQuote,
QuoteKey` all'import dei modelli. Dopo `RejectionRepository`:

```python
class QuoteRepository(Protocol):
    """RF-84: cache del prezzo per chiave, condivisa tra le istanze."""
    def get(self, key: QuoteKey) -> Optional[PriceQuote]: ...
    def claim(self, key: QuoteKey, order_id: str, now: datetime, fresh_after: datetime) -> bool:
        """Atomica: `order_id` diventa leader (riga `pending`) se la riga manca, se è `ready` con
        `priced_at < fresh_after`, o se è `pending` con un leader che non è più `queued`."""
    def publish(self, key: QuoteKey, leader_order_id: str, total: Decimal, now: datetime) -> List[str]:
        """Riga `ready` con il totale e, nella stessa transazione, gli ordini `queued` agganciati
        alla chiave passano a `awaiting_confirmation` con quel totale (fanout). Id sbloccati."""
    def release(self, key: QuoteKey, leader_order_id: str) -> List[Order]:
        """Cancella la riga se è `pending` con quel leader e sgancia i suoi ordini
        (`follows_quote` falso), restituiti in ordine di id; altrimenti []."""
```

In `Repositories` aggiungi `quotes: QuoteRepository` dopo `quota: QuotaStore`.

- [ ] **Passo 5: schema e migrazione**

In `vela/adapters/schema.py`, dentro `orders_t` prima dello `UniqueConstraint`:

```python
    Column("follows_quote", Boolean, nullable=False, server_default=text("false")),   # 0015 (RF-84)
    Column("confirmed_total", Numeric(12, 2)),                                         # 0015 (RF-84)
```

In fondo al file:

```python
# RF-84: cache del prezzo con fanout (migrazione 0015). Nessuna FK verso `orders`: il leader è un
# riferimento debole, un leader sparito vale come leader non più `queued`.
price_quotes_t = Table(
    "price_quotes", metadata,
    Column("product_id", String(32), primary_key=True),
    Column("start_date", Date, primary_key=True),
    Column("adults", Integer, primary_key=True),
    Column("rooms", Integer, primary_key=True),
    Column("currency", String(3), primary_key=True),
    Column("status", String(16), nullable=False),
    Column("leader_order_id", String(36), nullable=False),
    Column("total", Numeric(12, 2)),
    Column("priced_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
```

Crea `alembic/versions/0015_price_quotes.py`:

```python
"""Cache del prezzo con fanout (RF-84): tabella `price_quotes` e, su `orders`, `follows_quote`
(bool, default falso) e `confirmed_total` (numerico, nullo).

Numero 0015: 0012, 0013 e 0014 sono riservati a M21-C, M21-F e M22. Si aggancia alla testa di
oggi (0011); chi fa il merge per secondo riaggancia la catena (decisione del 2026-09-27).
Gli ordini già in tabella non sono agganciati a niente. `batch_alter_table` perché la migrazione
giri anche su SQLite (test).

Revision ID: 0015
Revises: 0011
Create Date: 2026-09-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "price_quotes",
        sa.Column("product_id", sa.String(32), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("adults", sa.Integer, nullable=False),
        sa.Column("rooms", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("leader_order_id", sa.String(36), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=True),
        sa.Column("priced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("product_id", "start_date", "adults", "rooms", "currency"),
    )
    with op.batch_alter_table("orders") as batch:
        batch.add_column(sa.Column("follows_quote", sa.Boolean, nullable=False,
                                   server_default=sa.false()))
        batch.add_column(sa.Column("confirmed_total", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("confirmed_total")
        batch.drop_column("follows_quote")
    op.drop_table("price_quotes")
```

- [ ] **Passo 6: repository in memoria**

In `vela/adapters/repo_memory.py` aggiungi all'import dei modelli `PriceQuote, QuoteKey,
QuoteStatus` e `from decimal import Decimal`. Dopo `MemoryRejections`:

```python
class MemoryQuotes:
    """RF-84. Legge ordini e proposte dei repository accanto, come il JOIN di Postgres; il lock
    degli ordini tiene fanout e rilascio atomici rispetto alle altre scritture sugli ordini."""

    def __init__(self, orders: "MemoryOrders", proposals: "MemoryProposals"):
        self._items: Dict[QuoteKey, PriceQuote] = {}
        self._orders, self._proposals = orders, proposals
        self._lock = threading.Lock()

    def get(self, key: QuoteKey) -> Optional[PriceQuote]:
        return self._items.get(key)

    def claim(self, key: QuoteKey, order_id: str, now: datetime, fresh_after: datetime) -> bool:
        with self._lock:
            quote = self._items.get(key)
            if quote is not None and not self._takeable(quote, fresh_after):
                return False
            self._items[key] = PriceQuote(key, QuoteStatus.PENDING, order_id, now)
            return True

    def _takeable(self, quote: PriceQuote, fresh_after: datetime) -> bool:
        if quote.status == QuoteStatus.READY:
            return quote.priced_at < fresh_after
        leader = self._orders.get(quote.leader_order_id)
        return leader is None or leader.status != OrderStatus.QUEUED

    def _followers(self, key: QuoteKey) -> List[Order]:
        out = []
        for o in self._orders._items.values():
            if not o.follows_quote or o.status != OrderStatus.QUEUED:
                continue
            p = self._proposals.get(o.proposal_id)
            if p is not None and QuoteKey(o.product_id, p.start_date, o.pax, o.rooms, o.currency) == key:
                out.append(o)
        return sorted(out, key=lambda o: o.id)

    def publish(self, key: QuoteKey, leader_order_id: str, total: Decimal, now: datetime) -> List[str]:
        with self._lock, self._orders._lock:
            self._items[key] = PriceQuote(key, QuoteStatus.READY, leader_order_id, now, total, now)
            ids = []
            for o in self._followers(key):
                self._orders._items[o.id] = replace(o, status=OrderStatus.AWAITING_CONFIRMATION,
                                                    total=total, follows_quote=False, updated_at=now)
                ids.append(o.id)
            return ids

    def release(self, key: QuoteKey, leader_order_id: str) -> List[Order]:
        with self._lock, self._orders._lock:
            quote = self._items.get(key)
            if (quote is None or quote.status != QuoteStatus.PENDING
                    or quote.leader_order_id != leader_order_id):
                return []
            del self._items[key]
            freed = [replace(o, follows_quote=False) for o in self._followers(key)]
            for o in freed:
                self._orders._items[o.id] = o
            return freed
```

In `MemoryRepositories.clear`, dopo `self.jobs = MemoryJobs()`:
`self.quotes = MemoryQuotes(self.orders, self.proposals)`.

- [ ] **Passo 7: repository Postgres**

In `vela/adapters/repo_postgres.py`:
- import: aggiungi `delete` a quelli di `sqlalchemy`; `price_quotes_t` a quelli di `schema`;
  `PriceQuote, QuoteKey, QuoteStatus` ai modelli; `from decimal import Decimal`.
- `_order_row`: aggiungi `"follows_quote": o.follows_quote, "confirmed_total": o.confirmed_total,`.
- `_order`: aggiungi `follows_quote=bool(m["follows_quote"]), confirmed_total=m["confirmed_total"]`.

Dopo `PostgresRejections`:

```python
_QUOTE_FIELDS = ("status", "leader_order_id", "total", "priced_at", "updated_at")


def _quote_where(key: QuoteKey):
    t = price_quotes_t.c
    return and_(t.product_id == key.product_id, t.start_date == key.start_date,
                t.adults == key.adults, t.rooms == key.rooms, t.currency == key.currency)


def _followers_where(key: QuoteKey):
    """Ordini `queued` agganciati alla chiave; la data sta sulla proposta."""
    o = orders_t.c
    return and_(o.follows_quote.is_(True), o.status == OrderStatus.QUEUED.value,
                o.product_id == key.product_id, o.pax == key.adults, o.rooms == key.rooms,
                o.currency == key.currency,
                o.proposal_id.in_(select(proposals_t.c.id).where(proposals_t.c.start_date == key.start_date)))


def _quote(m) -> PriceQuote:
    return PriceQuote(QuoteKey(m["product_id"], m["start_date"], m["adults"], m["rooms"], m["currency"]),
                      QuoteStatus(m["status"]), m["leader_order_id"], m["updated_at"],
                      m["total"], m["priced_at"])


class PostgresQuotes:
    """RF-84: una riga per chiave; elezione del leader con un solo `INSERT ... ON CONFLICT`."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def get(self, key: QuoteKey) -> Optional[PriceQuote]:
        with self.engine.connect() as conn:
            m = conn.execute(select(price_quotes_t).where(_quote_where(key))).mappings().first()
        return None if m is None else _quote(m)

    def _upsert(self, key: QuoteKey, **values):
        stmt = pg_insert(price_quotes_t).values(**key._asdict(), **values)
        return stmt, {f: stmt.excluded[f] for f in _QUOTE_FIELDS}

    def claim(self, key: QuoteKey, order_id: str, now: datetime, fresh_after: datetime) -> bool:
        t = price_quotes_t.c
        leader_queued = (select(orders_t.c.id).where(orders_t.c.id == t.leader_order_id,
                                                     orders_t.c.status == OrderStatus.QUEUED.value)
                         .exists())
        stmt, excluded = self._upsert(key, status=QuoteStatus.PENDING.value, leader_order_id=order_id,
                                      total=None, priced_at=None, updated_at=now)
        stmt = stmt.on_conflict_do_update(
            index_elements=list(QuoteKey._fields), set_=excluded,
            where=or_(and_(t.status == QuoteStatus.READY.value, t.priced_at < fresh_after),
                      and_(t.status == QuoteStatus.PENDING.value, ~leader_queued)))
        with self.engine.begin() as conn:
            return conn.execute(stmt).rowcount == 1

    def publish(self, key: QuoteKey, leader_order_id: str, total: Decimal, now: datetime) -> List[str]:
        stmt, excluded = self._upsert(key, status=QuoteStatus.READY.value, leader_order_id=leader_order_id,
                                      total=total, priced_at=now, updated_at=now)
        fanout = (update(orders_t).where(_followers_where(key))
                  .values(status=OrderStatus.AWAITING_CONFIRMATION.value, total=total,
                          follows_quote=False, updated_at=now)
                  .returning(orders_t.c.id))
        with self.engine.begin() as conn:
            conn.execute(stmt.on_conflict_do_update(index_elements=list(QuoteKey._fields), set_=excluded))
            return sorted(r[0] for r in conn.execute(fanout))

    def release(self, key: QuoteKey, leader_order_id: str) -> List[Order]:
        t = price_quotes_t.c
        with self.engine.begin() as conn:
            gone = conn.execute(delete(price_quotes_t).where(
                _quote_where(key), t.status == QuoteStatus.PENDING.value,
                t.leader_order_id == leader_order_id)).rowcount
            if gone != 1:
                return []
            rows = conn.execute(update(orders_t).where(_followers_where(key))
                                .values(follows_quote=False).returning(*orders_t.c)).mappings().all()
        return sorted((_order(m) for m in rows), key=lambda o: o.id)
```

In `PostgresRepositories.__init__`, dopo `self.jobs`: `self.quotes = PostgresQuotes(engine)`.

- [ ] **Passo 8: verifica**

Run: `uv run python3 -m unittest tests.test_repo_memory tests.test_migrations tests.test_repo_postgres -v 2>&1 | tail -20`
Atteso: PASS; `test_repo_postgres` saltato senza `DATABASE_URL`. **Con `DATABASE_URL` usa e
getta** va eseguito e deve passare: è l'unico posto dove si prova l'`ON CONFLICT ... WHERE`.
Poi l'intera suite e `uv run ruff check .`.

- [ ] **Passo 9: commit**

```bash
git add vela/domain/models.py vela/ports/repositories.py vela/adapters/schema.py \
  vela/adapters/repo_memory.py vela/adapters/repo_postgres.py alembic/versions/0015_price_quotes.py \
  tests/repo_contract.py tests/test_repo_postgres.py tests/test_migrations.py
git commit -m "Store price quotes with atomic leader election (RF-84)"
```

---

### Task 2: Accettazione con cache e fanout del leader

**File:**
- Crea: `vela/domain/quotes.py`, `tests/test_price_quotes.py`
- Modifica: `vela/domain/usecases.py`, `vela/domain/purchase.py`, `vela/config.py`, `vela/app.py`
- Test: `tests/test_price_quotes.py`, `tests/test_config.py`

**Interfacce:**
- Usa: `repos.quotes.*`, `QuoteKey`, `QuoteStatus`, `Order.follows_quote` (Task 1).
- Produce: `quote_key(order: Order, start_date: date) -> QuoteKey` in `vela/domain/quotes.py`;
  `Vela(..., price_quote_ttl_seconds: int = 0)`; `Vela._quote_key(order) -> QuoteKey`;
  `PurchaseJob._publish(order, total)`; `Settings.price_quote_ttl_seconds = 900`.
  In `tests/test_price_quotes.py` la classe `World` riusata dai Task 3 e 4.

- [ ] **Passo 1: test che falliscono**

Crea `tests/test_price_quotes.py`:

```python
"""Cache del prezzo con fanout (RF-84): hit, leader, agganciati, conferma senza carrello, ripiego.

Repository in memoria, HofJ finto, worker in linea; l'orologio avanza di un minuto per giro così
il token bucket (B = 8, 5 chiamate per acquisto) lascia passare un carrello dopo l'altro.
"""
import unittest
from datetime import date, timedelta
from decimal import Decimal

from support import NOW, FakeHofJ, StubPayments, inline_worker, make_product
from vela.adapters.repo_memory import MemoryRepositories
from vela.config import DEFAULT_TRAVELER, Settings
from vela.domain.models import (Area, Criteria, Intent, JobKind, OrderQueued, OrderStatus,
                                OrderStatusResponse, Participant, Period, Proposal, QuoteKey,
                                QuoteStatus, TravelerProfile)
from vela.domain.usecases import Vela

CRITERIA = Criteria("padel", Area("country", "Spagna", "ES"),
                    Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre"), 2, Decimal("800"))
PROFILE = TravelerProfile("Anna", "Rossi", "a@x.it", "+39 333", 2, (Participant("Bo", "Bi"),))
START = date(2026, 10, 1)
KEY = QuoteKey("1", START, 2, 1, "EUR")


class Clock:
    def __init__(self):
        self.at = NOW

    def __call__(self):
        return self.at

    def advance(self, seconds):
        self.at += timedelta(seconds=seconds)


class World:
    def __init__(self, ttl=900, total=None, hofj=None):
        self.clock = Clock()
        self.repos = MemoryRepositories()
        self.repos.products.upsert_many([make_product(1, price=350, destination="Valencia"),
                                         make_product(2, price=390, destination="Lanzarote")])
        self.hofj = hofj or FakeHofJ(total=total)
        self.payments = StubPayments()
        self.vela = Vela(self.repos, self.hofj, self.payments, DEFAULT_TRAVELER, now=self.clock,
                         price_quote_ttl_seconds=ttl)
        self.worker = inline_worker(self.vela)
        self.worker.processor.refresh_quota()          # il boot
        self.n = 0

    def traveler(self, product_id="1", start=START, pax=2):
        """Un intento e la sua proposta; restituisce l'id della proposta."""
        self.n += 1
        iid, pid = "i%d" % self.n, "p%d" % self.n
        self.repos.intents.add(Intent(iid, "padel", CRITERIA, PROFILE, NOW))
        self.repos.proposals.add(Proposal(pid, iid, product_id, start, start + timedelta(days=3), pax,
                                          Decimal("350"), "EUR", "Motivo.", NOW))
        return pid

    def accept(self, pid):
        return self.vela.accept_proposal(pid)

    def order(self, pid):
        return self.repos.orders.get_by_proposal(pid)

    def job(self, pid):
        return self.repos.jobs.active_for_order(self.order(pid).id, JobKind.PURCHASE)

    def carts(self):
        return sum(1 for c in self.hofj.calls if c[0] == "create_itinerary")

    def settle(self, rounds=6):
        for _ in range(rounds):
            self.worker.drain()
            self.clock.advance(60)


class LeaderAndFollowersTest(unittest.TestCase):
    def test_leader_then_followers_get_the_price_with_one_cart(self):
        w = World()
        pids = [w.traveler() for _ in range(3)]
        results = [w.accept(pid) for pid in pids]
        self.assertTrue(all(isinstance(r, OrderQueued) for r in results))
        self.assertIsNotNone(w.job(pids[0]))
        self.assertFalse(w.order(pids[0]).follows_quote)
        for pid in pids[1:]:
            self.assertIsNone(w.job(pid))
            self.assertTrue(w.order(pid).follows_quote)
        self.assertEqual(w.repos.quotes.get(KEY).status, QuoteStatus.PENDING)
        w.settle()
        for pid in pids:
            o = w.order(pid)
            self.assertEqual((o.status, o.total, o.follows_quote),
                             (OrderStatus.AWAITING_CONFIRMATION, Decimal("700"), False))
        self.assertEqual(w.carts(), 1)
        self.assertIsNotNone(w.order(pids[0]).itinerary_id)
        self.assertIsNone(w.order(pids[1]).itinerary_id)

    def test_hit_answers_at_once_without_job_or_calls(self):
        w = World()
        w.accept(w.traveler())
        w.settle()
        calls = len(w.hofj.calls)
        pid = w.traveler()
        result = w.accept(pid)
        self.assertIsInstance(result, OrderStatusResponse)
        self.assertEqual((result.status, result.total), (OrderStatus.AWAITING_CONFIRMATION, Decimal("700")))
        self.assertIn("700", result.say)
        self.assertIsNone(w.job(pid))
        self.assertEqual(len(w.hofj.calls), calls)

    def test_expired_quote_makes_a_new_leader(self):
        w = World()
        w.accept(w.traveler())
        w.settle()
        w.clock.advance(901)
        pid = w.traveler()
        self.assertIsInstance(w.accept(pid), OrderQueued)
        self.assertIsNotNone(w.job(pid))
        self.assertEqual(w.repos.quotes.get(KEY).leader_order_id, w.order(pid).id)

    def test_other_key_does_not_share(self):
        w = World()
        w.accept(w.traveler())
        other = w.traveler(start=START + timedelta(days=7))
        w.accept(other)
        self.assertIsNotNone(w.job(other))
        self.assertFalse(w.order(other).follows_quote)

    def test_unbookable_product_is_not_a_hit(self):
        w = World()
        w.accept(w.traveler())
        w.settle()
        w.repos.products.set_bookable("1", False, NOW)
        pid = w.traveler()
        self.assertIsInstance(w.accept(pid), OrderQueued)
        self.assertIsNotNone(w.job(pid))

    def test_follower_position_is_the_leaders(self):
        w = World()
        first, second = w.traveler(), w.traveler()
        leader = w.accept(first)
        follower = w.accept(second)
        self.assertEqual(follower.position, leader.position)
        self.assertIsNotNone(follower.position)

    def test_ttl_zero_is_todays_flow(self):
        w = World(ttl=0)
        pids = [w.traveler() for _ in range(2)]
        for pid in pids:
            w.accept(pid)
            self.assertIsNotNone(w.job(pid))
            self.assertFalse(w.order(pid).follows_quote)
        w.settle()
        self.assertIsNone(w.repos.quotes.get(KEY))
        self.assertEqual(w.carts(), 2)

    def test_lost_claim_after_publish_takes_the_price(self):
        """Il `claim` perde perché nel frattempo un leader ha pubblicato: niente attesa inutile."""
        w = World()
        w.accept(w.traveler())
        claim = w.repos.quotes.claim

        def publish_then_lose(key, order_id, now, fresh_after):
            w.repos.quotes.publish(key, "leader", Decimal("700"), now)
            return False

        w.repos.quotes.claim = publish_then_lose
        pid = w.traveler()
        w.accept(pid)
        w.repos.quotes.claim = claim
        o = w.order(pid)
        self.assertEqual((o.status, o.total, o.follows_quote),
                         (OrderStatus.AWAITING_CONFIRMATION, Decimal("700"), False))
        self.assertIsNone(w.job(pid))

    def test_leader_publishes_before_leaving_queued(self):
        """Al momento del `publish` il leader è ancora `queued`: un agganciato che controlla il
        leader in quell'istante non lo vede uscito."""
        w = World()
        leader_pid = w.traveler()
        w.accept(leader_pid)
        w.accept(w.traveler())
        seen = []
        publish = w.repos.quotes.publish

        def spy(key, leader_order_id, total, now):
            seen.append(w.repos.orders.get(leader_order_id).status)
            return publish(key, leader_order_id, total, now)

        w.repos.quotes.publish = spy
        w.settle()
        self.assertEqual(seen, [OrderStatus.QUEUED])


class SettingsTest(unittest.TestCase):
    def test_default_ttl_is_fifteen_minutes(self):
        self.assertEqual(Settings().price_quote_ttl_seconds, 900)
```

- [ ] **Passo 2: verifica che falliscano**

Run: `uv run python3 -m unittest tests.test_price_quotes -v 2>&1 | tail -15`
Atteso: `TypeError: __init__() got an unexpected keyword argument 'price_quote_ttl_seconds'` e
`AttributeError` su `Settings`.

- [ ] **Passo 3: modulo di dominio**

Crea `vela/domain/quotes.py`:

```python
"""Cache del prezzo con fanout (RF-84).

Due ordini con la stessa chiave hanno per HofJ lo stesso carrello, a meno di cliente e
passeggeri: il prezzo si scopre una volta (il leader) e vale per tutti fino al TTL. Qui le
regole che servono sia ai casi d'uso sia al job d'acquisto.
"""
from datetime import date

from vela.domain.models import Order, QuoteKey


def quote_key(order: Order, start_date: date) -> QuoteKey:
    """La data sta sulla proposta, il resto sull'ordine."""
    return QuoteKey(order.product_id, start_date, order.pax, order.rooms, order.currency)
```

- [ ] **Passo 4: `Settings` e cablaggio**

In `vela/config.py`, dopo `accept_poll_seconds`:

```python
    price_quote_ttl_seconds: int = 900                 # RF-84: vita del prezzo in cache; 0 = cache e fanout spenti
```

In `vela/app.py`, in `build_vela`, aggiungi alla costruzione di `Vela`
`price_quote_ttl_seconds=settings.price_quote_ttl_seconds`.

- [ ] **Passo 5: `Vela`**

In `vela/domain/usecases.py`:
- import: `from datetime import datetime, timedelta, timezone`; aggiungi `QuoteKey, QuoteStatus`
  ai modelli; `from vela.domain.quotes import quote_key`.
- `__init__`: nuovo parametro `price_quote_ttl_seconds: int = 0` (ultimo), e nel corpo:

```python
        # RF-84: vita del prezzo in cache; 0 = cache e fanout spenti (accettazione come prima)
        self.price_quote_ttl = timedelta(seconds=price_quote_ttl_seconds)
```

In `accept_proposal`, sostituisci il blocco da `order = Order(...)` fino a
`result = self._await_progress(order.id)` compreso con:

```python
        quotes_on = self.price_quote_ttl > timedelta(0)
        order = Order(self.new_id(), proposal.id, intent.id, proposal.product_id, OrderStatus.QUEUED,
                      proposal.pax, proposal.price_from, None, proposal.currency, profile, now, now,
                      enqueued_at=enqueued_at, rooms=chosen, follows_quote=quotes_on)
        cached = self._cached_total(order, proposal, product, now) if quotes_on else None
        if cached is not None:   # RF-84: hit, nessun job e nessuna chiamata
            order = replace(order, status=OrderStatus.AWAITING_CONFIRMATION, total=cached,
                            follows_quote=False)
        try:
            self.repos.orders.add(order)
        except DuplicateOrder:
            return self.get_order_status(self.repos.orders.get_by_proposal(proposal_id).id)
        if cached is not None:
            result = self.get_order_status(order.id)
        else:
            if not quotes_on or self._lead(order, proposal, now):
                self.repos.jobs.enqueue(Job(self.new_id(), JobKind.PURCHASE, order.id, JobStatus.PENDING,
                                            enqueued_at, now))
            result = self._await_progress(order.id)
```

(Le due righe dopo, `return replace(result, ...) if prefix else result`, restano.)

Dopo `_rooms_correction` aggiungi:

```python
    # --- RF-84: cache del prezzo --------------------------------------------

    def _quote_key(self, order: Order) -> QuoteKey:
        return quote_key(order, self.repos.proposals.get(order.proposal_id).start_date)

    def _cached_total(self, order: Order, proposal: Proposal, product: Optional[Product],
                      now: datetime) -> Optional[Decimal]:
        """Il totale in cache se è `ready`, più giovane del TTL e il prodotto è ancora prenotabile."""
        quote = self.repos.quotes.get(quote_key(order, proposal.start_date))
        if (quote is None or quote.status != QuoteStatus.READY or product is None
                or not product.bookable or quote.priced_at < now - self.price_quote_ttl):
            return None
        return quote.total

    def _lead(self, order: Order, proposal: Proposal, now: datetime) -> bool:
        """L'ordine, nato agganciato, prova a diventare leader. Se perde e intanto un leader ha
        pubblicato prende subito quel prezzo; altrimenti resta agganciato."""
        key = quote_key(order, proposal.start_date)
        if self.repos.quotes.claim(key, order.id, now, now - self.price_quote_ttl):
            return self.repos.orders.save_if_status(replace(order, follows_quote=False),
                                                    OrderStatus.QUEUED)
        quote = self.repos.quotes.get(key)
        if quote is not None and quote.status == QuoteStatus.READY:
            self.repos.orders.save_if_status(
                replace(order, status=OrderStatus.AWAITING_CONFIRMATION, total=quote.total,
                        follows_quote=False, updated_at=now), OrderStatus.QUEUED)
        return False
```

`_queue_position`: un agganciato ha la posizione del suo leader. Sostituisci la prima riga
(`position = self.repos.jobs.queued_purchase_position(order_id)`) con:

```python
        order = self.repos.orders.get(order_id)
        if order is not None and order.follows_quote:   # RF-84: la posizione del leader
            quote = self.repos.quotes.get(self._quote_key(order))
            if quote is not None and quote.status == QuoteStatus.PENDING:
                order_id = quote.leader_order_id
        position = self.repos.jobs.queued_purchase_position(order_id)
```

- [ ] **Passo 6: `publish` nel job d'acquisto**

In `vela/domain/purchase.py` importa `from vela.domain.quotes import quote_key`. Nel ramo
`STEP_TOTAL` di `_step`, subito dopo `itinerary = hofj.get_itinerary(order.itinerary_id)`:

```python
            self._publish(order, itinerary.total)   # RF-84: prima che l'ordine lasci `queued`
```

Dopo `_save_order`:

```python
    def _publish(self, order: Order, total) -> None:
        """RF-84: se la chiave è in cache (la riga esiste solo con la cache accesa), il prezzo letto
        la aggiorna e sblocca gli agganciati. Va chiamata prima di salvare il nuovo stato: finché
        il leader è `queued` nessun agganciato lo crede uscito e lo rilascia."""
        key = quote_key(order, self.repos.proposals.get(order.proposal_id).start_date)
        if self.repos.quotes.get(key) is None:
            return
        ids = self.repos.quotes.publish(key, order.id, total, self.now())
        if ids:
            log.info("quote_fanout order_id=%s followers=%d", order.id, len(ids))
```

Aggiorna la docstring del modulo, riga del passo 3:
`3 importo da pagare (`get_itinerary`, salva `total`, pubblica il prezzo in cache, RF-84)  1`.

- [ ] **Passo 7: verifica**

Run: `uv run python3 -m unittest tests.test_price_quotes -v 2>&1 | tail -15` → PASS.
Poi suite intera e ruff: i test esistenti devono restare verdi senza modifiche (con `Vela` a
TTL 0 di default il flusso è quello di prima). Se un test di superficie che passa da
`build_vela` cambia comportamento, fermati e segnalalo invece di adattarlo.

- [ ] **Passo 8: commit**

```bash
git add vela/domain/quotes.py vela/domain/usecases.py vela/domain/purchase.py vela/config.py \
  vela/app.py tests/test_price_quotes.py
git commit -m "Serve the actual price from the quote cache and fan it out (RF-84)"
```

---

### Task 3: Conferma senza carrello e prezzo cambiato

**File:**
- Modifica: `vela/domain/usecases.py` (`_confirm`, `get_order_status`), `vela/domain/purchase.py`
  (`STEP_TOTAL`), `vela/domain/say.py`
- Test: `tests/test_price_quotes.py`, `tests/test_say.py`

**Interfacce:**
- Usa: `World` (Task 2), `Order.confirmed_total` (Task 1), `PurchaseJob._publish` (Task 2).
- Produce: `say.say_price_changed_since(total: Decimal, confirmed: Decimal, lang: str = "it") -> str`.

- [ ] **Passo 1: test che falliscono**

In `tests/test_price_quotes.py` aggiungi:

```python
class ConfirmWithoutCartTest(unittest.TestCase):
    def hit(self, w):
        w.accept(w.traveler())
        w.settle()
        pid = w.traveler()
        w.accept(pid)
        return pid

    def test_confirm_without_cart_goes_to_the_link_when_the_price_matches(self):
        w = World()
        pid = self.hit(w)
        w.accept(pid)                                        # il sì
        o = w.order(pid)
        self.assertEqual((o.status, o.confirmed_total), (OrderStatus.QUEUED, Decimal("700")))
        self.assertEqual(w.job(pid).step, 0)                 # il carrello non c'è ancora
        w.settle()
        o = w.order(pid)
        self.assertEqual((o.status, o.total), (OrderStatus.AWAITING_PAYMENT, Decimal("700")))
        self.assertIsNotNone(o.itinerary_id)
        self.assertEqual(w.carts(), 2)

    def test_confirm_without_cart_asks_again_when_price_changed(self):
        w = World()
        pid = self.hit(w)
        w.accept(pid)
        w.hofj.total = Decimal("768")
        w.settle()
        o = w.order(pid)
        self.assertEqual((o.status, o.total, o.confirmed_total),
                         (OrderStatus.AWAITING_CONFIRMATION, Decimal("768"), Decimal("700")))
        self.assertEqual(w.payments.links, [])
        status = w.vela.get_order_status(o.id)
        self.assertIn("768", status.say)
        self.assertIn("700", status.say)
        self.assertEqual(w.repos.quotes.get(KEY).total, Decimal("768"))
        carts = w.carts()
        w.accept(pid)                                        # il secondo sì
        self.assertEqual(w.job(pid).step, 4)                 # dal link: il carrello c'è
        w.settle()
        self.assertEqual(w.order(pid).status, OrderStatus.AWAITING_PAYMENT)
        self.assertTrue(w.payments.links[-1].url.endswith(o.id))
        self.assertEqual(w.carts(), carts)

    def test_leader_confirm_still_starts_from_the_link(self):
        w = World()
        pid = w.traveler()
        w.accept(pid)
        w.settle()
        w.accept(pid)
        self.assertEqual(w.job(pid).step, 4)
        self.assertIsNone(w.order(pid).confirmed_total)
```

In `tests/test_say.py` (importa `say_price_changed_since` da `vela.domain.say` insieme agli
altri import di quel file):

```python
class PriceChangedSinceTest(unittest.TestCase):
    def test_italian(self):
        text = say_price_changed_since(Decimal("768"), Decimal("700"))
        self.assertIn("768", text)
        self.assertIn("700", text)
        self.assertIn("Confermi?", text)

    def test_english(self):
        text = say_price_changed_since(Decimal("768"), Decimal("700"), "en")
        self.assertIn("768", text)
        self.assertIn("you confirmed", text)
        self.assertIn("Do you confirm?", text)
```

- [ ] **Passo 2: verifica che falliscano**

Run: `uv run python3 -m unittest tests.test_price_quotes.ConfirmWithoutCartTest tests.test_say -v 2>&1 | tail -15`
Atteso: `ImportError` su `say_price_changed_since`; `confirmed_total` è `None` e lo step è 4.

- [ ] **Passo 3: frase**

In `vela/domain/say.py`, dopo `say_confirm_price`:

```python
def say_price_changed_since(total: Decimal, confirmed: Decimal, lang: str = "it") -> str:
    """RF-84: il carrello, creato dopo il sì a un prezzo in cache, costa un'altra cifra. Il link
    nasce solo con un nuovo sì."""
    if lang == "en":
        return ("In the meantime the price has changed: it is now %s in total instead of the %s you "
                "confirmed. Do you confirm? If you say yes, I'll prepare the payment link." % (
                    fmt_money(total, lang), fmt_money(confirmed, lang).replace(" euros", "")))
    return ("Nel frattempo il prezzo è cambiato: ora è %s in totale invece dei %s che avevi "
            "confermato. Confermi? Se mi dici di sì preparo il link di pagamento." % (
                fmt_money(total), fmt_money(confirmed).replace(" euro", "")))
```

- [ ] **Passo 4: `_confirm`**

In `vela/domain/usecases.py` importa `STEP_ITINERARY` accanto a `STEP_LINK` e sostituisci
`_confirm`:

```python
    def _confirm(self, order: Order) -> Union[OrderQueued, OrderStatusResponse]:
        """Il sì al prezzo effettivo: l'ordine torna in coda. Con il carrello il job riparte dal
        link; senza (RF-84, prezzo dalla cache) riparte dal carrello e al passo 3 confronta il
        totale con quello confermato qui."""
        now = self.now()
        cart = order.itinerary_id is not None
        confirmed = order if cart else replace(order, confirmed_total=order.total)
        self.repos.orders.save(replace(confirmed, status=OrderStatus.QUEUED, updated_at=now))
        if self.repos.jobs.active_for_order(order.id, JobKind.PURCHASE) is None:
            self.repos.jobs.enqueue(Job(self.new_id(), JobKind.PURCHASE, order.id, JobStatus.PENDING,
                                        now, now, step=STEP_LINK if cart else STEP_ITINERARY))
        return self._await_progress(order.id)
```

- [ ] **Passo 5: passo 3 del job**

In `vela/domain/purchase.py` sostituisci il ramo `STEP_TOTAL` con:

```python
        elif job.step == STEP_TOTAL:
            itinerary = hofj.get_itinerary(order.itinerary_id)
            self._publish(order, itinerary.total)   # RF-84: prima che l'ordine lasci `queued`
            priced = replace(order, total=itinerary.total, currency=itinerary.currency)
            if order.confirmed_total == itinerary.total and order.currency == itinerary.currency:
                self._save_order(priced)   # RF-84: il viaggiatore ha già detto sì a questo importo
            else:
                if order.confirmed_total is not None:
                    log.info("quote_price_changed order_id=%s confirmed=%s total=%s",
                             order.id, order.confirmed_total, itinerary.total)
                self._save_order(replace(priced, status=OrderStatus.AWAITING_CONFIRMATION))
```

(`confirmed_total` è `None` per il leader e per gli ordini di prima: `None == totale` è falso e
si va a `awaiting_confirmation` come oggi.) Aggiorna la docstring del modulo: dopo la freccia di
`awaiting_confirmation` aggiungi la riga
`(RF-84: se l'ordine ha già un `confirmed_total` uguale, si prosegue al link senza fermarsi)`.

- [ ] **Passo 6: `get_order_status`**

In `get_order_status`, nel `return OrderStatusResponse(...)` finale sostituisci l'argomento
`say.say_status(status, order.booking_code, ...)` con la variabile `sentence`, calcolata subito
prima del `return`:

```python
        sentence = say.say_status(status, order.booking_code, order.failure_reason, lang, order.total,
                                  price_from_total=estimate, phone_tail=tail, pax=order.pax)
        if (status == OrderStatus.AWAITING_CONFIRMATION and order.confirmed_total is not None
                and order.total != order.confirmed_total):   # RF-84
            sentence = say.say_price_changed_since(order.total, order.confirmed_total, lang)
```

- [ ] **Passo 7: verifica**

Run: `uv run python3 -m unittest tests.test_price_quotes tests.test_say tests.test_purchase_job -v 2>&1 | tail -15` → PASS.
Poi suite intera e ruff.

- [ ] **Passo 8: commit**

```bash
git add vela/domain/usecases.py vela/domain/purchase.py vela/domain/say.py \
  tests/test_price_quotes.py tests/test_say.py
git commit -m "Create the cart after the yes and ask again if the price changed (RF-84)"
```

---

### Task 4: Ripiego quando il leader esce senza prezzo

**File:**
- Modifica: `vela/domain/quotes.py`, `vela/domain/purchase.py` (`_fail_order`, `_replace`),
  `vela/domain/usecases.py` (`_cancel_unpaid_order`, `_await_progress`, `get_order_status`)
- Test: `tests/test_price_quotes.py`

**Interfacce:**
- Usa: `repos.quotes.release`, `repos.quotes.get`, `quote_key`, `World`.
- Produce: `release_quote(repos, order, now, new_id) -> int` e
  `unstick(repos, order, now, new_id) -> None` in `vela/domain/quotes.py`.

- [ ] **Passo 1: test che falliscono**

In `tests/test_price_quotes.py` aggiungi gli import `from dataclasses import replace` e
`from vela.ports.hofj import ConfigError, ProductError`, poi:

```python
class FallbackTest(unittest.TestCase):
    def three(self, **hofj):
        w = World(hofj=FakeHofJ(**hofj)) if hofj else World()
        pids = [w.traveler() for _ in range(3)]
        for pid in pids:
            w.accept(pid)
        return w, pids

    def assert_released(self, w, followers):
        """Riga sparita, agganciati sganciati; dopo qualche giro ognuno ha il suo carrello."""
        self.assertIsNone(w.repos.quotes.get(KEY))
        for pid in followers:
            self.assertFalse(w.order(pid).follows_quote)
        w.settle()
        for pid in followers:
            o = w.order(pid)
            self.assertEqual(o.status, OrderStatus.AWAITING_CONFIRMATION, pid)
            self.assertIsNotNone(o.itinerary_id, pid)

    def test_failed_leader_hands_followers_their_own_jobs(self):
        w, pids = self.three(fail_at={"create_itinerary": [ConfigError("401")]})
        w.worker.drain()
        self.assertEqual(w.order(pids[0]).status, OrderStatus.FAILED)
        self.assert_released(w, pids[1:])

    def test_unbookable_leader_hands_followers_their_own_jobs(self):
        w, pids = self.three(fail_at={"create_itinerary": [ProductError("502")]})
        w.worker.drain()
        self.assertNotEqual(w.order(pids[0]).status, OrderStatus.QUEUED)   # replaced o failed
        self.assert_released(w, pids[1:])

    def test_cancelled_leader_hands_followers_their_own_jobs_in_their_place(self):
        w, pids = self.three()
        w.vela._cancel_unpaid_order(pids[0])   # RF-49, senza passare dal chooser di reject_proposal
        self.assertEqual(w.order(pids[0]).status, OrderStatus.CANCELLED)
        for pid in pids[1:]:                   # prima di ogni drain: il job c'è, al suo posto
            o = w.order(pid)
            job = w.repos.jobs.active_for_order(o.id, JobKind.PURCHASE)
            self.assertEqual(job.enqueued_at, o.enqueued_at)
        self.assert_released(w, pids[1:])

    def test_follower_unsticks_when_leader_left_without_release(self):
        w, pids = self.three()
        leader = w.order(pids[0])
        w.repos.orders.save(replace(leader, status=OrderStatus.FAILED))   # uscita senza rilascio
        w.vela.get_order_status(w.order(pids[1]).id)
        self.assert_released(w, pids[1:])

    def test_release_by_a_follower_changes_nothing(self):
        from vela.domain.quotes import release_quote
        w, pids = self.three()
        self.assertEqual(release_quote(w.repos, w.order(pids[1]), NOW, lambda: "x"), 0)
        self.assertEqual(w.repos.quotes.get(KEY).status, QuoteStatus.PENDING)
        self.assertTrue(w.order(pids[2]).follows_quote)

    def test_cancelled_follower_is_left_out_of_the_fanout(self):
        w, pids = self.three()
        w.vela._cancel_unpaid_order(pids[1])
        w.settle()
        self.assertEqual(w.order(pids[1]).status, OrderStatus.CANCELLED)
        self.assertEqual(w.order(pids[2]).status, OrderStatus.AWAITING_CONFIRMATION)
```

- [ ] **Passo 2: verifica che falliscano**

Run: `uv run python3 -m unittest tests.test_price_quotes.FallbackTest -v 2>&1 | tail -15`
Atteso: gli agganciati restano `follows_quote` senza job (`AssertionError`), `ImportError` su
`release_quote`.

- [ ] **Passo 3: `release_quote` e `unstick`**

In `vela/domain/quotes.py` sostituisci gli import e aggiungi le funzioni:

```python
import logging
from datetime import date, datetime
from typing import Callable

from vela.domain.models import Job, JobKind, JobStatus, Order, OrderStatus, QuoteKey, QuoteStatus
from vela.ports.repositories import Repositories

log = logging.getLogger("vela.quotes")
```

```python
def release_quote(repos: Repositories, order: Order, now: datetime, new_id: Callable[[], str]) -> int:
    """Ripiego: se `order` è il leader di un prezzo in volo, la riga sparisce e ogni agganciato
    torna un ordine normale con il suo job, al suo posto in coda. No-op negli altri casi.
    Da chiamare in ogni uscita del leader senza prezzo (failed, replaced, cancelled)."""
    proposal = repos.proposals.get(order.proposal_id)
    if proposal is None:
        return 0
    return _release(repos, quote_key(order, proposal.start_date), order.id, now, new_id)


def unstick(repos: Repositories, order: Order, now: datetime, new_id: Callable[[], str]) -> None:
    """Rete di sicurezza: un agganciato il cui leader non è più `queued` (crash, uscita senza
    rilascio) fa il rilascio al posto suo. Il rilascio è atomico: tra più agganciati che ci
    provano insieme vince uno solo."""
    if not order.follows_quote or order.status != OrderStatus.QUEUED:
        return
    key = quote_key(order, repos.proposals.get(order.proposal_id).start_date)
    quote = repos.quotes.get(key)
    if quote is None or quote.status != QuoteStatus.PENDING:
        return
    leader = repos.orders.get(quote.leader_order_id)
    if leader is None or leader.status != OrderStatus.QUEUED:
        _release(repos, key, quote.leader_order_id, now, new_id)


def _release(repos: Repositories, key: QuoteKey, leader_order_id: str, now: datetime,
             new_id: Callable[[], str]) -> int:
    freed = repos.quotes.release(key, leader_order_id)
    for o in freed:
        repos.jobs.enqueue(Job(new_id(), JobKind.PURCHASE, o.id, JobStatus.PENDING,
                               o.enqueued_at or now, now))
    if freed:
        log.info("quote_released leader=%s followers=%d", leader_order_id, len(freed))
    return len(freed)
```

- [ ] **Passo 4: uscite del leader nel job**

In `vela/domain/purchase.py` importa `release_quote` da `vela.domain.quotes`.

`_fail_order` diventa:

```python
    def _fail_order(self, job: Job, reason: str) -> None:
        order = self.repos.orders.get(job.order_id)
        if order is not None and order.status == OrderStatus.QUEUED:
            self._save_order(replace(order, status=OrderStatus.FAILED,
                                     failure_reason=say.failure_reason(reason, self._lang(order))))
        if order is not None:
            release_quote(self.repos, order, self.now(), self.new_id)   # RF-84: ripiego
```

In `_replace`, subito prima di `return self._close(job, JobStatus.DONE, exc)`:

```python
        release_quote(self.repos, order, now, self.new_id)   # RF-84: ripiego
```

- [ ] **Passo 5: rinuncia e rete di sicurezza nei casi d'uso**

In `vela/domain/usecases.py` estendi l'import: `from vela.domain.quotes import quote_key,
release_quote, unstick`.

`_cancel_unpaid_order`, dopo `self.repos.orders.save(...)`:

```python
        release_quote(self.repos, order, self.now(), self.new_id)   # RF-84: ripiego
```

`_await_progress`: nel ciclo, sostituisci
`if self.repos.orders.get(order_id).status != OrderStatus.QUEUED:` e la riga che segue con:

```python
            current = self.repos.orders.get(order_id)
            if current.status != OrderStatus.QUEUED:
                return self.get_order_status(order_id)
            unstick(self.repos, current, self.now(), self.new_id)   # RF-84
```

`get_order_status`: dopo `order = self.orders.get(order_id)`:

```python
        if order.follows_quote:   # RF-84: un leader uscito senza rilascio non blocca nessuno
            unstick(self.repos, order, self.now(), self.new_id)
            order = self.orders.get(order_id)
```

- [ ] **Passo 6: verifica**

Run: `uv run python3 -m unittest tests.test_price_quotes tests.test_purchase_job tests.test_queue_flow -v 2>&1 | tail -15` → PASS.
Poi suite intera (con e senza `DATABASE_URL`) e ruff.

- [ ] **Passo 7: commit**

```bash
git add vela/domain/quotes.py vela/domain/purchase.py vela/domain/usecases.py tests/test_price_quotes.py
git commit -m "Hand followers their own jobs when the leader leaves without a price (RF-84)"
```

---

### Task 5: Load test e documentazione

**File:**
- Modifica: `loadtest/journey.py`, `loadtest/README.md`, `docs/spec.md`, `docs/decisions.md`,
  `docs/roadmap.md`
- Test: `tests/test_loadtest_journey.py`

- [ ] **Passo 1: test che fallisce**

In `tests/test_loadtest_journey.py`, dopo `test_confirms_the_actual_price_then_pays`:

```python
    def test_cache_hit_on_accept_confirms_then_pays(self):
        """RF-84: l'accettazione risponde subito 200 con il prezzo dalla cache, senza coda."""
        hit = status("awaiting_confirmation", order_id="o1", total="700.00")
        s = Script(create_intent=[INTENT], get_proposal=[PROPOSAL], accept_proposal=[hit],
                   get_order_status=[status("awaiting_confirmation", total="700.00"),
                                     status("awaiting_payment", payment_url="http://vela:8000/replay/checkout/o1"),
                                     status("confirmed")],
                   replay_checkout=[(200, {"status": "paid_pending_booking"})])
        rec = run_journey(Traveler(1, 0, TEXT, "padel", False, True, True, poll=(30, 30)),
                          s, s.clock, s.sleep, 900, {})
        self.assertEqual(rec["final"], "confirmed")
        self.assertIsNone(rec["wait_seconds"])
        accepts = [c[1] for c in s.calls if c[0] == "accept_proposal"]
        self.assertEqual(accepts, ["/v1/proposals/p1/accept"] * 2)
```

- [ ] **Passo 2: verifica che fallisca**

Run: `uv run python3 -m unittest tests.test_loadtest_journey -v 2>&1 | tail -8`
Atteso: `final` = `accept_order_status`.

- [ ] **Passo 3: `journey.py`**

Sostituisci `if status != 202:` con:

```python
    hit = status == 200 and queued.get("status") == "awaiting_confirmation"   # RF-84: prezzo dalla cache
    if status != 202 and not hit:
```

- [ ] **Passo 4: verifica**

Run: `uv run python3 -m unittest tests.test_loadtest_journey -v 2>&1 | tail -8` → PASS.

- [ ] **Passo 5: documentazione**

- `docs/spec.md`:
  - nell'intestazione aggiungi "RF-84 aggiunto e RF-14, RF-16, RF-45, RF-46, RF-48, RF-49
    aggiornati il 2026-09-27 per la cache del prezzo con fanout
    (`docs/superpowers/specs/2026-09-27-cache-prezzo-fanout-design.md`)";
  - in §4.10, dopo RF-49, il requisito nuovo:
    > **RF-84** Il prezzo effettivo si mette in cache per chiave (prodotto, data di inizio,
    > adulti, camere, valuta) per 15 minuti (`price_quote_ttl_seconds`, 0 = spenta). Con un
    > prezzo in cache `accept_proposal` risponde subito `awaiting_confirmation`, senza coda né
    > chiamate a HofJ, e il carrello si crea dopo il sì. Con un prezzo in volo per la stessa
    > chiave l'ordine si aggancia al leader, senza job suo, e riceve il prezzo quando il leader
    > lo legge. Se il carrello creato dopo il sì costa un'altra cifra, l'ordine torna
    > `awaiting_confirmation` e serve un nuovo sì; il link porta sempre il totale del carrello.
    > Se il leader esce senza prezzo, gli agganciati tornano ordini normali al loro posto in coda;
  - una frase di rimando a RF-84 in RF-14 ("il carrello di un ordine servito dalla cache nasce
    dopo il sì"), RF-16 (conferma senza carrello), RF-45 (hit e agganciati), RF-46 (passo 3),
    RF-48 (posizione del leader), RF-49 (rinuncia del leader);
  - nell'elenco delle migrazioni (vicino a "0013 (M21-F)") aggiungi "0015 (RF-84):
    `price_quotes`, `orders.follows_quote`, `orders.confirmed_total`".
- `docs/decisions.md`, in fondo, sezione `## 2026-09-27 — Cache del prezzo con fanout (RF-84)`
  con tabella `| Tema | Decisione | Perché |` e righe: cosa si condivide (solo il prezzo, il
  carrello è per viaggiatore); opzione C, cache + fanout; Postgres invece di Redis o cache per
  processo; TTL 15 minuti e interruttore a 0; ripiego sugli agganciati; `confirmed_total` e
  secondo giro di conferma; `publish` prima dello stato del leader; migrazione 0015 riagganciata
  da chi fa il merge per secondo; finestra di crash tra `release` e accodamento accettata; load
  test: `journey.py` adattato, giri di `RESULTS.md` da rifare in una task separata.
- `docs/roadmap.md`, prima di `## Matrice dei requisiti`: sezione `## M23 — Cache del prezzo
  con fanout` con **Scope**, **Test**, **Copre** (RF-14, RF-16, RF-45, RF-46, RF-48, RF-49,
  RF-84), **Stato** (fatto il 2026-09-27); nella matrice la riga `| RF-84 | M23 |`.
- `loadtest/README.md`, sezione "Scenario": una frase: "Con la cache del prezzo (RF-84) chi
  accetta un viaggio già prezzato riceve subito `200 awaiting_confirmation`: il viaggiatore
  finto lo tratta come un prezzo arrivato e conferma al primo giro di polling."

- [ ] **Passo 6: verifica finale**

Run: `uv run python3 -m unittest discover -s tests 2>&1 | tail -3` → OK (con `DATABASE_URL`
usa e getta, anche i test Postgres). Run: `uv run ruff check .` → pulito.

- [ ] **Passo 7: commit**

```bash
git add loadtest/journey.py loadtest/README.md tests/test_loadtest_journey.py docs/spec.md \
  docs/decisions.md docs/roadmap.md
git commit -m "Accept cache hits in the load test journey and document RF-84"
```
