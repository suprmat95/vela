import unittest

from quota_contract import QuotaContract
from vela.adapters.repo_memory import MemoryQuota


class MemoryQuotaTest(QuotaContract, unittest.TestCase):
    def make_store(self):
        return MemoryQuota(margin=0.10, reserve=0.20)


if __name__ == "__main__":
    unittest.main()
