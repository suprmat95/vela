import sys
import unittest


class ToolchainTest(unittest.TestCase):
    def test_runs_on_python_312(self):
        self.assertGreaterEqual(
            sys.version_info[:2], (3, 12),
            "la suite va lanciata nel venv di uv (uv sync; source .venv/bin/activate), "
            "non con il python3 di sistema %s" % sys.version.split()[0])
