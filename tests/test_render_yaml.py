import os
import re
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")

# Variabili di spec §6.
ENV_VARS = ["HOFJ_API_KEY", "HOFJ_BASE_URL", "HOFJ_BRANDS", "DATABASE_URL", "STRIPE_SECRET_KEY",
            "STRIPE_WEBHOOK_SECRET", "VELA_API_TOKEN", "VELA_UPSTREAM_MODE", "ANTHROPIC_API_KEY",
            "VELA_PUBLIC_URL"]


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def service_block(text, name):
    """Il blocco YAML del servizio `name` in `services:` (testuale, senza dipendenze)."""
    services = text.split("\ndatabases:")[0]
    for block in services.split("\n  - type: ")[1:]:
        if re.search(r"^\s+name: %s$" % re.escape(name), block, re.M):
            return block
    return None


class RenderYamlTest(unittest.TestCase):
    def setUp(self):
        self.text = read("render.yaml")

    def test_docker_web_service_with_health_check(self):
        self.assertIn("type: web", self.text)
        self.assertIn("runtime: docker", self.text)
        self.assertIn("healthCheckPath: /health", self.text)

    def test_database_url_comes_from_managed_postgres(self):
        block = self.text[self.text.index("key: DATABASE_URL"):]
        self.assertIn("fromDatabase", block[:200])
        self.assertIn("databases:", self.text)

    def test_every_env_var_is_declared(self):
        for var in ENV_VARS:
            self.assertIn("key: " + var, self.text, var)

    def test_secrets_are_not_in_the_repo(self):
        for var in ENV_VARS:
            if var in ("DATABASE_URL", "VELA_UPSTREAM_MODE"):
                continue
            m = re.search(r"key: %s\n\s+(\w+):" % var, self.text)
            self.assertIsNotNone(m, var)
            self.assertEqual(m.group(1), "sync", var)

    def test_upstream_mode_is_live_on_render(self):
        """M7: Render gira contro HofJ staging; il valore sta nel Blueprint perché una
        sincronizzazione non lo riporti a replay."""
        self.assertRegex(self.text, r"key: VELA_UPSTREAM_MODE\n\s+value: live")


class LandingServiceTest(unittest.TestCase):
    def setUp(self):
        self.text = read("render.yaml")

    def test_landing_is_a_static_site(self):
        block = service_block(self.text, "vela-landing")
        self.assertIsNotNone(block)
        self.assertIn("runtime: static", block)
        self.assertIn("staticPublishPath: ./landing", block)
        self.assertRegex(block, r"buildFilter:\n\s+paths:\n\s+- landing/\*\*")

    def test_api_ignores_landing_changes(self):
        block = service_block(self.text, "vela")
        self.assertIn("runtime: docker", block)
        self.assertRegex(block, r"buildFilter:\n\s+ignoredPaths:\n\s+- landing/\*\*")


class ReadmeTest(unittest.TestCase):
    def test_lists_every_env_var(self):
        readme = read("README.md")
        for var in ENV_VARS:
            self.assertIn("`%s`" % var, readme, var)

    def test_documents_test_and_run_commands(self):
        readme = read("README.md")
        self.assertIn("python3 -m unittest discover -s tests", readme)
        self.assertIn("uv sync", readme)
        self.assertIn("docker build", readme)

    def test_documents_the_landing(self):
        readme = read("README.md")
        self.assertIn("python3 -m http.server -d landing", readme)
        self.assertIn("landing/config.js", readme)
        self.assertIn("vela-landing", readme)
