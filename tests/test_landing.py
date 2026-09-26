import os
import re
import unittest
from html.parser import HTMLParser

ROOT = os.path.join(os.path.dirname(__file__), "..")
LANDING = os.path.join(ROOT, "landing")
WIDGET_SRC = "https://unpkg.com/@elevenlabs/convai-widget-embed"


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class Page(HTMLParser):
    """Tag e attributi di index.html, in ordine."""

    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def parse_page():
    page = Page()
    page.feed(read("landing", "index.html"))
    page.close()
    return page


def config_value(key):
    m = re.search(r'%s:\s*"([^"]*)"' % key, read("landing", "config.js"))
    return m.group(1) if m else None


class IndexHtmlTest(unittest.TestCase):
    def setUp(self):
        self.html = read("landing", "index.html")
        self.page = parse_page()

    def test_is_italian(self):
        html_tag = [attrs for tag, attrs in self.page.tags if tag == "html"][0]
        self.assertEqual(html_tag.get("lang"), "it")

    def test_local_references_exist(self):
        for tag, attrs in self.page.tags:
            for name in ("href", "src"):
                ref = attrs.get(name)
                if not ref or re.match(r"^(https?:|mailto:|tel:|#)", ref):
                    continue
                self.assertTrue(os.path.isfile(os.path.join(LANDING, ref)), ref)

    def test_mcp_url_matches_config(self):
        m = re.search(r'<code id="mcp-url">([^<]*)</code>', self.html)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), config_value("mcpUrl"))
        self.assertRegex(m.group(1), r"^https://.+/mcp$")

    def test_works_without_javascript(self):
        """Senza JS: URL leggibile, voce e telefono "In arrivo", pulsante Copia nascosto."""
        self.assertIn('data-soon="voice"', self.html)
        self.assertIn('data-soon="phone"', self.html)
        button = [attrs for tag, attrs in self.page.tags if attrs.get("id") == "copy-mcp"][0]
        self.assertIn("hidden", button)
        link = [attrs for tag, attrs in self.page.tags if attrs.get("id") == "phone-link"][0]
        self.assertIn("hidden", link)

    def test_is_not_a_homepage(self):
        self.assertNotIn("<table", self.html.lower())

    def test_does_not_load_the_widget_statically(self):
        self.assertNotIn(WIDGET_SRC, self.html)
        self.assertNotIn("<elevenlabs-convai", self.html)


class ConfigTest(unittest.TestCase):
    def test_declares_the_three_values(self):
        for key in ("mcpUrl", "elevenLabsAgentId", "phoneNumber"):
            self.assertIsNotNone(config_value(key), key)


class StylesTest(unittest.TestCase):
    def test_long_urls_wrap_on_small_screens(self):
        self.assertIn("overflow-wrap: anywhere", read("landing", "styles.css"))

    def test_hidden_wins_over_display_rules(self):
        self.assertIn("[hidden] { display: none !important; }", read("landing", "styles.css"))


if __name__ == "__main__":
    unittest.main()
