"""Adapter Haiku (RF-03) con un client finto: nessuna chiamata ad Anthropic."""
import unittest
from datetime import date
from types import SimpleNamespace

import anthropic

from vela.adapters.haiku import (MAX_RETRIES, MODEL, SYSTEM, TIMEOUT_SECONDS, TOOL,
                                 TOOL_NAME, HaikuExtractor)

TODAY = date(2026, 9, 25)
INPUT = {"sport": "padel", "area": "Spain", "period_start": "2026-10-01",
         "period_end": "2026-10-31", "pax": 2, "budget": 800}


def _request():
    try:
        import httpx2 as http
    except ImportError:
        import httpx as http
    return http.Request("POST", "https://api.anthropic.com/v1/messages")


class FakeMessages:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def client(response=None, error=None):
    return SimpleNamespace(messages=FakeMessages(response, error))


def tool_use(name=TOOL_NAME, data=INPUT):
    return SimpleNamespace(type="tool_use", name=name, input=data)


class HaikuExtractorTest(unittest.TestCase):
    def test_request_shape(self):
        c = client(SimpleNamespace(content=[tool_use()], stop_reason="tool_use"))
        HaikuExtractor(c).extract("padel a ottobre", TODAY)
        call = c.messages.calls[0]
        self.assertEqual(call["model"], "claude-haiku-4-5-20251001")
        self.assertEqual(MODEL, call["model"])
        self.assertEqual(call["tool_choice"], {"type": "tool", "name": TOOL_NAME})
        self.assertEqual(call["tools"], [TOOL])
        self.assertIn("2026-09-25", call["messages"][0]["content"])
        self.assertIn("padel a ottobre", call["messages"][0]["content"])
        self.assertLessEqual(call["max_tokens"], 1024)

    def test_schema_matches_domain_fields(self):
        props = TOOL["input_schema"]["properties"]
        self.assertEqual(set(props), {"sport", "area", "period_start", "period_end", "pax", "budget"})
        self.assertEqual(set(TOOL["input_schema"]["required"]), set(props))

    def test_sport_enum_includes_any(self):
        # M17: "indifferente" / "tutti e due" è una risposta valida (RF-02, RF-04)
        self.assertEqual(TOOL["input_schema"]["properties"]["sport"]["enum"],
                         ["padel", "tennis", "any", None])

    def test_system_prompt_covers_synonyms_any_and_exclusions(self):
        for piece in ("terra rossa", "Terrarossa", "clay", "paddle", "Weebora", "any",
                      "beach tennis", "paddle tennis"):
            self.assertIn(piece, SYSTEM)

    def test_returns_tool_input(self):
        c = client(SimpleNamespace(content=[SimpleNamespace(type="text", text="ok"), tool_use()],
                                   stop_reason="tool_use"))
        self.assertEqual(HaikuExtractor(c).extract("x", TODAY), INPUT)

    def test_no_tool_use_is_none(self):
        c = client(SimpleNamespace(content=[SimpleNamespace(type="text", text="?")],
                                   stop_reason="end_turn"))
        self.assertIsNone(HaikuExtractor(c).extract("x", TODAY))

    def test_other_tool_or_bad_input_is_none(self):
        self.assertIsNone(HaikuExtractor(client(SimpleNamespace(
            content=[tool_use(name="altro")], stop_reason="tool_use"))).extract("x", TODAY))
        self.assertIsNone(HaikuExtractor(client(SimpleNamespace(
            content=[tool_use(data="testo")], stop_reason="tool_use"))).extract("x", TODAY))

    def test_api_errors_are_none(self):
        for error in (anthropic.APIConnectionError(request=_request()),
                      anthropic.APITimeoutError(request=_request())):
            with self.subTest(error=type(error).__name__):
                with self.assertLogs("vela.adapters.haiku", level="WARNING") as logs:
                    self.assertIsNone(HaikuExtractor(client(error=error)).extract("segreto", TODAY))
                self.assertNotIn("segreto", "\n".join(logs.output))

    def test_from_api_key_configures_client(self):
        ex = HaikuExtractor.from_api_key("sk-ant-test")
        self.assertIsInstance(ex.client, anthropic.Anthropic)
        self.assertEqual(ex.client.timeout, TIMEOUT_SECONDS)
        self.assertEqual(ex.client.max_retries, MAX_RETRIES)
