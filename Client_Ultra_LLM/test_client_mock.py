"""Offline safety checks for the static Client P0 HTML mock; no networking."""
from html.parser import HTMLParser
from pathlib import Path
import unittest

HTML = (Path(__file__).with_name("index.html")).read_text(encoding="utf-8")


class Controls(HTMLParser):
    def __init__(self):
        super().__init__()
        self.buttons = []
        self.selects = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "button":
            self.buttons.append(attrs)
        if tag == "select":
            self.selects.append(attrs)


class ClientMockSafetyTests(unittest.TestCase):
    def test_client_identity_and_explicit_offline_scope(self):
        self.assertIn("Ultra LLM Client", HTML)
        self.assertIn("UL-CLIENT-P0 / МАКЕТ", HTML)
        self.assertIn("автономный HTML-макет без API", HTML)

    def test_lifecycle_buttons_and_selections_disabled(self):
        parser = Controls()
        parser.feed(HTML)
        enabled = [btn for btn in parser.buttons if "disabled" not in btn]
        self.assertEqual({btn.get("id") for btn in enabled},
                         {"locale-ru", "locale-en"})
        self.assertTrue(parser.selects)
        self.assertTrue(all("disabled" in item for item in parser.selects))

    def test_no_network_or_process_control(self):
        for forbidden in ("fetch(", "XMLHttpRequest", "new WebSocket",
                          "navigator.sendBeacon", "Invoke-Command"):
            self.assertNotIn(forbidden, HTML)
        self.assertIn("ultra-llm-client.language", HTML)


if __name__ == "__main__":
    unittest.main()
