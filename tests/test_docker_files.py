import os
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


class EntrypointTest(unittest.TestCase):
    def test_is_executable(self):
        self.assertTrue(os.access(os.path.join(ROOT, "docker-entrypoint.sh"), os.X_OK))

    def test_runs_migrations_before_uvicorn(self):
        script = read("docker-entrypoint.sh")
        self.assertIn("set -e", script)
        migrate = script.index("alembic upgrade head")
        serve = script.index("exec uvicorn vela.app:app")
        self.assertLess(migrate, serve)

    def test_binds_render_port(self):
        self.assertIn('--port "${PORT:-8000}"', read("docker-entrypoint.sh"))


class DockerfileTest(unittest.TestCase):
    def test_uses_python_312_uv_image_and_entrypoint(self):
        dockerfile = read("Dockerfile")
        self.assertIn("python3.12", dockerfile)
        self.assertIn("uv sync --frozen --no-dev", dockerfile)
        self.assertIn('ENTRYPOINT ["./docker-entrypoint.sh"]', dockerfile)

    def test_runs_as_non_root(self):
        self.assertIn("USER ", read("Dockerfile"))


class DockerignoreTest(unittest.TestCase):
    def test_excludes_secrets_and_scratch(self):
        lines = read(".dockerignore").splitlines()
        for pattern in (".env", ".env.*", ".venv", "agent-log", ".git"):
            self.assertIn(pattern, lines)

    def test_keeps_what_the_build_needs(self):
        lines = read(".dockerignore").splitlines()
        for needed in ("alembic", "alembic.ini", "pyproject.toml", "uv.lock", "vela"):
            self.assertNotIn(needed, lines)
