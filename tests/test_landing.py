import json
import os
import re
import unittest
from html.parser import HTMLParser

ROOT = os.path.join(os.path.dirname(__file__), "..")
LANDING = os.path.join(ROOT, "landing")
WIDGET_SRC = "https://unpkg.com/@elevenlabs/convai-widget-embed"
CONNECTOR_NAME = "Pacchetti Viaggio di Padel Tennis"
# id del prodotto nelle fixture → nome citato nelle conversazioni d'esempio.
EXAMPLE_TRIPS = {
    "688": "Marina di Pietrasanta",
    "695": "Corralejo Tennis Academy",
    "369": "Piatti Tennis Center",
    "1023": "Weekend all'insegna del padel a Málaga",
    "1044": "Il Tesoro Nascosto del Lago di Como",
}


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
        m = re.search(r'<input id="mcp-url"[^>]*value="([^"]*)"', self.html)
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

    def test_has_no_design_placeholders(self):
        self.assertIsNone(re.search(r"\[[A-ZÀ-Ý ]{3,}\]", self.html))

    def test_connector_name_matches_the_readme(self):
        self.assertIn(CONNECTOR_NAME, self.html)
        self.assertIn(CONNECTOR_NAME, read("README.md"))

    def test_example_trips_exist_in_the_fixtures(self):
        """Le conversazioni d'esempio citano viaggi veri del catalogo registrato."""
        titles = {}
        for name in ("catalog.json", "catalog-tennis.json"):
            for p in json.loads(read("fixtures", name))["products"]:
                titles[p["id"]] = p["title"]
        for pid, name in EXAMPLE_TRIPS.items():
            self.assertIn(name, titles.get(pid, ""), pid)
            self.assertIn(name, self.html, pid)

    def test_does_not_load_the_widget_statically(self):
        self.assertNotIn(WIDGET_SRC, self.html)
        self.assertNotIn("<elevenlabs-convai", self.html)


class ConfigTest(unittest.TestCase):
    def test_declares_the_three_values(self):
        for key in ("mcpUrl", "elevenLabsAgentId", "phoneNumber"):
            self.assertIsNotNone(config_value(key), key)


class StylesTest(unittest.TestCase):
    def test_url_field_fits_small_screens(self):
        css = read("landing", "styles.css")
        self.assertRegex(css, r"\.url-row input\{[^}]*min-width:0")
        self.assertRegex(css, r"@media \(max-width:480px\)\{[^@]*\.url-row\{flex-direction:column")

    def test_hidden_wins_over_display_rules(self):
        self.assertRegex(read("landing", "styles.css"), r"\[hidden\]\s*\{\s*display:\s*none\s*!important")


class ScriptsTest(unittest.TestCase):
    def test_config_loads_before_main(self):
        srcs = [attrs["src"] for tag, attrs in parse_page().tags
                if tag == "script" and "src" in attrs]
        self.assertEqual(srcs, ["config.js", "main.js"])

    def test_main_makes_no_requests_but_the_widget(self):
        js = read("landing", "main.js")
        for forbidden in ("fetch(", "XMLHttpRequest", "innerHTML", "document.write"):
            self.assertNotIn(forbidden, js)
        self.assertIn(WIDGET_SRC, js)


if __name__ == "__main__":
    unittest.main()
