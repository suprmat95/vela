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
