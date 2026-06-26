"""Tests for client construction and prompt composition (no live browser)."""

from __future__ import annotations

from pathlib import Path

import pytest

from gemx import client as client_module
from gemx.client import (
    INPUT_SELECTOR,
    RESPONSE_SELECTOR,
    SEND_SELECTOR,
    Gemx,
    GemxConfig,
)
from gemx.errors import ResponseTimeoutError
from gemx.formats import OutputFormat, format_instruction


class FakeResponsePage:
    def __init__(self, response_texts: list[str]) -> None:
        self._response_texts = response_texts
        self._selector_calls = 0
        self._response_reads = 0
        self.screenshots: list[str] = []

    async def evaluate(self, script: str, *_args: object) -> object:
        if script == "(s) => document.querySelectorAll(s).length":
            self._selector_calls += 1
            return 0 if self._selector_calls == 1 else 1
        if script == client_module._LONGEST_RESPONSE_JS:
            index = min(self._response_reads, len(self._response_texts) - 1)
            self._response_reads += 1
            return self._response_texts[index]
        if "document.body.innerText" in script:
            return ""
        raise AssertionError(f"unexpected evaluate script: {script}")

    async def screenshot(self, path: str) -> None:
        self.screenshots.append(path)


def test_config_defaults() -> None:
    cfg = GemxConfig(profile_dir=Path("/tmp/p"))
    assert cfg.headless is True
    assert cfg.browser_channel is None
    assert cfg.response_timeout_s == 180
    assert "--no-sandbox" in cfg.launch_args


def test_selectors_match_debugged_values() -> None:
    # These are the selectors proven against the live Gemini UI; guard them.
    assert INPUT_SELECTOR == '.ql-editor[contenteditable="true"]'
    assert SEND_SELECTOR == 'button[aria-label="Send message"]'
    assert RESPONSE_SELECTOR == "message-content .markdown"


def test_ask_appends_format_instruction(monkeypatch) -> None:
    captured: dict[str, str] = {}

    async def fake_ask_raw(
        self: Gemx,
        prompt: str,
        expected_format: OutputFormat | None = None,
    ) -> str:
        captured["prompt"] = prompt
        captured["expected_format"] = str(expected_format)
        return '{"ok": true}'

    monkeypatch.setattr(Gemx, "ask_raw", fake_ask_raw)

    import asyncio

    gemx = Gemx(GemxConfig(profile_dir=Path("/tmp/p")))
    result = asyncio.run(gemx.ask("base prompt", OutputFormat.JSON))

    assert result == {"ok": True}
    assert "base prompt" in captured["prompt"]
    assert format_instruction(OutputFormat.JSON) in captured["prompt"]
    assert captured["expected_format"] == "json"


@pytest.mark.asyncio
async def test_await_response_keeps_waiting_until_json_parses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(client_module.asyncio, "sleep", no_sleep)
    page = FakeResponsePage(['{"a": ', '{"a": ', '{"a": 1}', '{"a": 1}'])
    cfg = GemxConfig(
        profile_dir=Path("/tmp/p"),
        poll_interval_s=1,
        stable_ticks=1,
        min_response_chars=1,
        stabilization_timeout_s=5,
    )

    result = await Gemx(cfg)._await_response(page, OutputFormat.JSON)

    assert result == '{"a": 1}'
    assert page.screenshots == []


@pytest.mark.asyncio
async def test_await_response_rejects_stable_incomplete_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(client_module.asyncio, "sleep", no_sleep)
    page = FakeResponsePage(['{"a": ', '{"a": '])
    cfg = GemxConfig(
        profile_dir=Path("/tmp/p"),
        poll_interval_s=1,
        stable_ticks=1,
        min_response_chars=1,
        stabilization_timeout_s=3,
    )

    with pytest.raises(ResponseTimeoutError, match="complete json"):
        await Gemx(cfg)._await_response(page, OutputFormat.JSON)

    assert page.screenshots == ["/tmp/gemini-incomplete-response.png"]
