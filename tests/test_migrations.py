import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from vela.domain.labels import labels_of, ordered

ROOT = os.path.join(os.path.dirname(__file__), "..")
INI = os.path.join(ROOT, "alembic.ini")


def alembic_config():
    return Config(INI)


def versions(url):
    engine = create_engine(url)
    with engine.connect() as conn:
        if "alembic_version" not in inspect(conn).get_table_names():
            return None
        return [row[0] for row in conn.execute(text("SELECT version_num FROM alembic_version"))]


def seed_rejection(conn):
    """Intento, prodotto, proposta e un rifiuto con le sole colonne di prima di 0016."""
    conn.execute(text("INSERT INTO intents (id, text, criteria, profile, language, created_at) "
                      "VALUES ('i1', 'padel', '{}', '{}', 'it', '2026-09-27 10:00:00')"))
    conn.execute(text("INSERT INTO products (id, title, slug, short_description, sport, price, "
                      "currency, availabilities, raw, fetched_at, bookable, archived) VALUES "
                      "('1', 't', 's', '', 'padel', 1, 'EUR', '[]', '{}', '2026-09-27 10:00:00', "
                      "true, false)"))
    conn.execute(text("INSERT INTO proposals (id, intent_id, product_id, start_date, end_date, pax, "
                      "price_from, currency, reason, created_at) VALUES ('p1', 'i1', '1', "
                      "'2026-10-01', '2026-10-04', 2, 350, 'EUR', 'r', '2026-09-27 10:00:00')"))
    conn.execute(text("INSERT INTO rejections (intent_id, proposal_id, product_id, reason, created_at) "
                      "VALUES ('i1', 'p1', '1', 'troppo caro', '2026-09-27 10:00:00')"))


class ScriptsTest(unittest.TestCase):
    def test_single_head_is_initial_revision(self):
        heads = ScriptDirectory.from_config(alembic_config()).get_heads()
        self.assertEqual(heads, ["0016"])

    def test_ini_paths_do_not_depend_on_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = subprocess.run([sys.executable, "-m", "alembic", "-c", os.path.abspath(INI), "heads"],
                                 cwd=tmp, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("0016", res.stdout)


class SqliteUpgradeTest(unittest.TestCase):
    def test_upgrade_head_then_downgrade_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite:///" + os.path.join(tmp, "vela.db")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(alembic_config(), "head")
                self.assertEqual(versions(url), ["0016"])
                with create_engine(url).connect() as conn:
                    tables = inspect(conn).get_table_names()
                    self.assertIn("orders", tables)
                    self.assertNotIn("stripe_events", tables)   # creata da 0003, tolta da 0004
                    self.assertIn("jobs", tables)
                    self.assertIn("quota_window", tables)
                    order_cols = {c["name"]: c for c in inspect(conn).get_columns("orders")}
                    self.assertIn("enqueued_at", order_cols)
                    self.assertIn("replacement_proposal_id", order_cols)
                    self.assertTrue(order_cols["total"]["nullable"])
                    self.assertIn("price_quotes", tables)
                    self.assertFalse(order_cols["follows_quote"]["nullable"])
                    self.assertTrue(order_cols["confirmed_total"]["nullable"])
                    product_cols = {c["name"]: c for c in inspect(conn).get_columns("products")}
                    self.assertTrue(product_cols["brand"]["nullable"])
                    for flag in ("featured", "special_offer"):   # 0010 (M21-B)
                        self.assertFalse(product_cols[flag]["nullable"], flag)
                        # default falso: SQLite lo riflette come "0", Postgres come "false"
                        self.assertIn(str(product_cols[flag]["default"]).lower(), ("0", "false"), flag)
                    self.assertFalse(order_cols["orphan_itineraries"]["nullable"])
                    self.assertTrue(product_cols["max_pax_per_room"]["nullable"])   # 0011 (M21-D)
                    self.assertFalse(order_cols["rooms"]["nullable"])
                    self.assertEqual(str(order_cols["rooms"]["default"]).strip("'"), "1")
                    self.assertFalse(product_cols["levels"]["nullable"])            # 0012 (M21-C)
                    self.assertEqual(str(product_cols["levels"]["default"]).strip("'"), "[]")
                    for flag in ("levels_exclusive", "coaching"):
                        self.assertFalse(product_cols[flag]["nullable"], flag)
                        self.assertIn(str(product_cols[flag]["default"]).lower(), ("0", "false"), flag)
                    rejection_cols = {c["name"]: c for c in inspect(conn).get_columns("rejections")}
                    self.assertTrue(rejection_cols["kind"]["nullable"])             # 0016 (M21-F)
                    self.assertFalse(rejection_cols["keep_product"]["nullable"])
                    self.assertIn(str(rejection_cols["keep_product"]["default"]).lower(), ("0", "false"))
                    quota_cols = {c["name"] for c in inspect(conn).get_columns("quota_window")}
                    self.assertTrue({"tokens", "refilled_at"} <= quota_cols)
                    self.assertNotIn("used", quota_cols)
                    job_indexes = {i["name"]: i for i in inspect(conn).get_indexes("jobs")}
                    self.assertTrue(job_indexes["uq_jobs_active_booking"]["unique"])
                command.downgrade(alembic_config(), "base")
                self.assertEqual(versions(url), [])

    def test_upgrade_keeps_existing_loggers_enabled(self):
        import logging
        logger = logging.getLogger("vela.test_migrations_probe")
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite:///" + os.path.join(tmp, "vela.db")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(alembic_config(), "head")
        self.assertFalse(logger.disabled)

    def test_upgrade_to_0010_backfills_flags_from_raw(self):
        """M21-B: le righe già in tabella prendono `featured` e `special_offer` dal dettaglio
        salvato in `raw` (il sync incrementale non le riscriverebbe finché non cambiano)."""
        rows = {"f": '{"featured": true, "isSpecialOffer": false}',
                "s": '{"featured": false, "isSpecialOffer": true}',
                "n": '{"title": "senza etichette"}',
                "z": '{"featured": null, "isSpecialOffer": null}'}
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite:///" + os.path.join(tmp, "vela.db")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(alembic_config(), "0009")
                engine = create_engine(url)
                with engine.begin() as conn:
                    for pid, raw in rows.items():
                        conn.execute(text(
                            "INSERT INTO products (id, title, slug, short_description, sport, price, "
                            "currency, availabilities, raw, fetched_at, bookable, archived) VALUES "
                            "(:id, 't', 's', '', 'padel', 1, 'EUR', '[]', :raw, "
                            "'2026-09-27 10:00:00', 1, 0)"), {"id": pid, "raw": raw})
                command.upgrade(alembic_config(), "0010")
                with engine.connect() as conn:
                    got = {r[0]: (bool(r[1]), bool(r[2])) for r in conn.execute(
                        text("SELECT id, featured, special_offer FROM products"))}
        self.assertEqual(got, {"f": (True, False), "s": (False, True), "n": (False, False),
                               "z": (False, False)})

    def test_upgrade_to_0011_backfills_max_pax_per_room_from_raw(self):
        """M21-D: le righe già in tabella prendono `max_pax_per_room` dal dettaglio in `raw`;
        assente, nullo o zero = nessun limite. Gli ordini di prima restano a una camera
        (decisione A)."""
        rows = {"two": '{"maxPaxPerRoom": 2}', "none": '{"maxPaxPerRoom": null}',
                "zero": '{"maxPaxPerRoom": 0}', "absent": '{"title": "senza limite"}'}
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite:///" + os.path.join(tmp, "vela.db")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(alembic_config(), "0010")
                engine = create_engine(url)
                with engine.begin() as conn:
                    for pid, raw in rows.items():
                        conn.execute(text(
                            "INSERT INTO products (id, title, slug, short_description, sport, price, "
                            "currency, availabilities, raw, fetched_at, bookable, archived) VALUES "
                            "(:id, 't', 's', '', 'padel', 1, 'EUR', '[]', :raw, "
                            "'2026-09-27 10:00:00', 1, 0)"), {"id": pid, "raw": raw})
                    conn.execute(text(
                        "INSERT INTO orders (id, proposal_id, intent_id, product_id, status, pax, "
                        "price_from, currency, traveler, created_at, updated_at) VALUES "
                        "('o1', 'p1', 'i1', 'two', 'confirmed', 4, 100, 'EUR', '{}', "
                        "'2026-09-27 10:00:00', '2026-09-27 10:00:00')"))
                command.upgrade(alembic_config(), "0011")
                with engine.connect() as conn:
                    got = dict(conn.execute(text("SELECT id, max_pax_per_room FROM products")).all())
                    rooms = conn.execute(text("SELECT rooms FROM orders WHERE id = 'o1'")).scalar()
        self.assertEqual(got, {"two": 2, "none": None, "zero": None, "absent": None})
        self.assertEqual(rooms, 1)

    def test_upgrade_to_0012_backfills_labels_from_raw_with_the_sync_rules(self):
        """M21-C: le righe già in tabella prendono livelli, esclusività e lezioni dal dettaglio
        in `raw`, con `labels_of`, la stessa funzione del sync. Dettagli veri della fixture (962,
        1027, 622) più una riserva esplicita e una riga senza descrizioni."""
        with open(os.path.join(ROOT, "fixtures", "catalog.json"), encoding="utf-8") as fh:
            details = json.load(fh)["details"]
        rows = {pid: details[pid]["raw"] for pid in ("962", "1027", "622")}
        rows["only"] = {"shortDescription": "Solo per avanzati", "description": "Con coach."}
        rows["empty"] = {"title": "senza descrizioni"}
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite:///" + os.path.join(tmp, "vela.db")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(alembic_config(), "0011")
                engine = create_engine(url)
                with engine.begin() as conn:
                    for pid, raw in rows.items():
                        conn.execute(text(
                            "INSERT INTO products (id, title, slug, short_description, sport, price, "
                            "currency, availabilities, raw, fetched_at, bookable, archived) VALUES "
                            "(:id, 't', 's', '', 'padel', 1, 'EUR', '[]', :raw, "
                            "'2026-09-27 10:00:00', 1, 0)"), {"id": pid, "raw": json.dumps(raw)})
                command.upgrade(alembic_config(), "0012")
                with engine.connect() as conn:
                    got = {r[0]: (json.loads(r[1]), bool(r[2]), bool(r[3])) for r in conn.execute(
                        text("SELECT id, levels, levels_exclusive, coaching FROM products"))}
        self.assertEqual(got, {"962": (["intermediate", "advanced"], False, True),
                               "1027": (["beginner", "intermediate"], False, True),
                               "622": ([], False, False),
                               "only": (["advanced"], True, True),
                               "empty": ([], False, False)})
        for pid, raw in rows.items():   # nessuna regola duplicata: è `labels_of`
            labels = labels_of(raw)
            self.assertEqual(got[pid], (ordered(labels.levels), labels.levels_exclusive, labels.coaching))

    def test_0016_follows_0015_and_leaves_0013_0014_unused(self):
        """M21-F: la catena su master è 0012 → 0015 → 0016; una 0013 in mezzo romperebbe i
        database già a 0015 (decisione M23)."""
        scripts = ScriptDirectory.from_config(alembic_config())
        self.assertEqual(scripts.get_revision("0016").down_revision, "0015")
        self.assertEqual(scripts.get_revision("0015").down_revision, "0012")
        for unused in ("0013", "0014"):
            with self.assertRaises(Exception):
                scripts.get_revision(unused)

    def test_upgrade_to_0016_keeps_existing_rejections_without_a_kind(self):
        """M21-F: un rifiuto già in tabella non ha tipo (nullo, nessun tipo inventato) e non
        tiene il prodotto."""
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite:///" + os.path.join(tmp, "vela.db")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(alembic_config(), "0015")
                engine = create_engine(url)
                with engine.begin() as conn:
                    seed_rejection(conn)
                command.upgrade(alembic_config(), "0016")
                with engine.connect() as conn:
                    rows = conn.execute(text("SELECT reason, kind, keep_product FROM rejections")).all()
        self.assertEqual([(r[0], r[1], bool(r[2])) for r in rows], [("troppo caro", None, False)])

    def test_downgrade_from_0016_removes_rejection_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite:///" + os.path.join(tmp, "vela.db")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(alembic_config(), "head")
                engine = create_engine(url)
                with engine.begin() as conn:
                    seed_rejection(conn)
                command.downgrade(alembic_config(), "0015")
                self.assertEqual(versions(url), ["0015"])
                with engine.connect() as conn:
                    cols = {c["name"] for c in inspect(conn).get_columns("rejections")}
                    reasons = [r[0] for r in conn.execute(text("SELECT reason FROM rejections"))]
        self.assertFalse({"kind", "keep_product"} & cols)
        self.assertEqual(reasons, ["troppo caro"])

    def test_downgrade_from_0012_removes_label_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite:///" + os.path.join(tmp, "vela.db")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(alembic_config(), "head")
                command.downgrade(alembic_config(), "0011")
                self.assertEqual(versions(url), ["0011"])
                with create_engine(url).connect() as conn:
                    cols = {c["name"] for c in inspect(conn).get_columns("products")}
        self.assertFalse({"levels", "levels_exclusive", "coaching"} & cols)
        self.assertIn("max_pax_per_room", cols)

    def test_downgrade_from_0011_removes_rooms_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite:///" + os.path.join(tmp, "vela.db")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(alembic_config(), "head")
                command.downgrade(alembic_config(), "0010")
                with create_engine(url).connect() as conn:
                    product_cols = {c["name"] for c in inspect(conn).get_columns("products")}
                    order_cols = {c["name"] for c in inspect(conn).get_columns("orders")}
        self.assertNotIn("max_pax_per_room", product_cols)
        self.assertNotIn("rooms", order_cols)

    def test_downgrade_from_0010_removes_flag_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite:///" + os.path.join(tmp, "vela.db")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(alembic_config(), "head")
                command.downgrade(alembic_config(), "0009")
                with create_engine(url).connect() as conn:
                    cols = {c["name"] for c in inspect(conn).get_columns("products")}
        self.assertFalse({"featured", "special_offer"} & cols)

    def test_downgrade_from_0009_removes_active_booking_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite:///" + os.path.join(tmp, "vela.db")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(alembic_config(), "head")
                command.downgrade(alembic_config(), "0008")
                with create_engine(url).connect() as conn:
                    names = {i["name"] for i in inspect(conn).get_indexes("jobs")}
        self.assertNotIn("uq_jobs_active_booking", names)

    def test_upgrade_to_0009_keeps_the_oldest_active_booking_job(self):
        """Job `booking` doppi già in tabella (la corsa di M13b): resta attivo il più vecchio,
        gli altri diventano `dead`, e l'indice unico si crea."""
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite:///" + os.path.join(tmp, "vela.db")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(alembic_config(), "0008")
                engine = create_engine(url)
                with engine.begin() as conn:
                    for jid, kind, status, at in (("b2", "booking", "pending", "2026-09-26 15:31:52.118"),
                                                  ("b1", "booking", "running", "2026-09-26 15:31:52.113"),
                                                  ("b3", "booking", "done", "2026-09-26 15:30:00.000"),
                                                  ("p1", "purchase", "pending", "2026-09-26 15:31:52.100")):
                        conn.execute(text("INSERT INTO jobs (id, kind, order_id, status, step, attempts, "
                                          "enqueued_at, run_after) VALUES (:id, :kind, 'o1', :status, 0, 0, "
                                          ":at, :at)"), {"id": jid, "kind": kind, "status": status, "at": at})
                command.upgrade(alembic_config(), "0009")
                with engine.connect() as conn:
                    rows = dict(conn.execute(text("SELECT id, status FROM jobs")).all())
        self.assertEqual(rows, {"b1": "running", "b2": "dead", "b3": "done", "p1": "pending"})

    def test_downgrade_from_0008_restores_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite:///" + os.path.join(tmp, "vela.db")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(alembic_config(), "head")
                command.downgrade(alembic_config(), "0007")
                with create_engine(url).connect() as conn:
                    quota_cols = {c["name"] for c in inspect(conn).get_columns("quota_window")}
        self.assertIn("used", quota_cols)

    def test_downgrade_from_0007_removes_bucket_and_orphan_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite:///" + os.path.join(tmp, "vela.db")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(alembic_config(), "head")
                command.downgrade(alembic_config(), "0006")
                with create_engine(url).connect() as conn:
                    quota_cols = {c["name"] for c in inspect(conn).get_columns("quota_window")}
                    order_cols = {c["name"] for c in inspect(conn).get_columns("orders")}
        self.assertFalse({"tokens", "refilled_at"} & quota_cols)
        self.assertNotIn("orphan_itineraries", order_cols)

    def test_downgrade_from_0006_removes_products_brand(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite:///" + os.path.join(tmp, "vela.db")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(alembic_config(), "head")
                command.downgrade(alembic_config(), "0005")
                with create_engine(url).connect() as conn:
                    cols = {c["name"] for c in inspect(conn).get_columns("products")}
                    self.assertNotIn("brand", cols)
                    self.assertIn("provider_id", cols)

    def test_downgrade_from_0005_removes_queue_tables_and_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite:///" + os.path.join(tmp, "vela.db")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(alembic_config(), "head")
                command.downgrade(alembic_config(), "0004")
                with create_engine(url).connect() as conn:
                    tables = inspect(conn).get_table_names()
                    self.assertNotIn("jobs", tables)
                    self.assertNotIn("quota_window", tables)
                    cols = {c["name"] for c in inspect(conn).get_columns("orders")}
                    self.assertNotIn("enqueued_at", cols)
                    self.assertNotIn("replacement_proposal_id", cols)

    def test_downgrade_from_0004_restores_stripe_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite:///" + os.path.join(tmp, "vela.db")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(alembic_config(), "head")
                command.downgrade(alembic_config(), "0003")
                with create_engine(url).connect() as conn:
                    self.assertIn("stripe_events", inspect(conn).get_table_names())

    def test_upgrade_without_database_url_fails_explicitly(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                command.upgrade(alembic_config(), "head")
        self.assertIn("DATABASE_URL", str(ctx.exception))


class PostgresUpgradeTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("DATABASE_URL"), "serve DATABASE_URL")
    def test_upgrade_head_is_idempotent(self):
        from vela.config import Settings
        command.upgrade(alembic_config(), "head")
        command.upgrade(alembic_config(), "head")
        self.assertEqual(versions(Settings.from_env().database_url), ["0016"])

    @unittest.skipUnless(os.environ.get("DATABASE_URL"), "serve DATABASE_URL")
    def test_0016_on_existing_rejections_then_downgrade_and_back(self):
        """M21-F su Postgres: un rifiuto scritto a 0015 resta, senza tipo e senza `keep_product`;
        il downgrade toglie le due colonne e tiene la riga; si torna alla testa."""
        from vela.config import Settings
        url = Settings.from_env().database_url
        command.upgrade(alembic_config(), "head")
        command.downgrade(alembic_config(), "0015")
        engine = create_engine(url)
        ids = ("m21f-i", "m21f-p", "m21f-x")
        try:
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO intents (id, text, criteria, profile, language, created_at) "
                                  "VALUES (:i, 'padel', '{}', '{}', 'it', now())"), {"i": ids[0]})
                conn.execute(text("INSERT INTO products (id, title, slug, short_description, sport, "
                                  "price, currency, availabilities, raw, fetched_at, bookable, archived) "
                                  "VALUES (:x, 't', 's', '', 'padel', 1, 'EUR', '[]', '{}', now(), true, "
                                  "false)"), {"x": ids[2]})
                conn.execute(text("INSERT INTO proposals (id, intent_id, product_id, start_date, end_date, "
                                  "pax, price_from, currency, reason, created_at) VALUES (:p, :i, :x, "
                                  "'2026-10-01', '2026-10-04', 2, 350, 'EUR', 'r', now())"),
                             {"p": ids[1], "i": ids[0], "x": ids[2]})
                conn.execute(text("INSERT INTO rejections (intent_id, proposal_id, product_id, reason, "
                                  "created_at) VALUES (:i, :p, :x, 'troppo caro', now())"),
                             {"i": ids[0], "p": ids[1], "x": ids[2]})
            command.upgrade(alembic_config(), "0016")
            with engine.connect() as conn:
                row = conn.execute(text("SELECT kind, keep_product FROM rejections WHERE proposal_id = :p"),
                                   {"p": ids[1]}).one()
            self.assertEqual(tuple(row), (None, False))
            command.downgrade(alembic_config(), "0015")
            with engine.connect() as conn:
                cols = {c["name"] for c in inspect(conn).get_columns("rejections")}
                left = conn.execute(text("SELECT count(*) FROM rejections WHERE proposal_id = :p"),
                                    {"p": ids[1]}).scalar()
            self.assertFalse({"kind", "keep_product"} & cols)
            self.assertEqual(left, 1)
        finally:
            command.upgrade(alembic_config(), "head")
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM rejections WHERE proposal_id = :p"), {"p": ids[1]})
                conn.execute(text("DELETE FROM proposals WHERE id = :p"), {"p": ids[1]})
                conn.execute(text("DELETE FROM intents WHERE id = :i"), {"i": ids[0]})
                conn.execute(text("DELETE FROM products WHERE id = :x"), {"x": ids[2]})
        self.assertEqual(versions(url), ["0016"])
