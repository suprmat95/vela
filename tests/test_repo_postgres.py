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
        from vela.adapters.schema import (intents_t, orders_t, products_t, proposals_t,
                                           rejections_t, stripe_events_t)
        with self.engine.begin() as conn:
            for table in (stripe_events_t, rejections_t, orders_t, proposals_t, intents_t,
                          products_t):
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
