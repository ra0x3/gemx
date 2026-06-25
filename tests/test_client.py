"""Tests for client construction and prompt composition (no live browser)."""

from __future__ import annotations

from pathlib import Path

from gemx.client import (
    INPUT_SELECTOR,
    RESPONSE_SELECTOR,
    SEND_SELECTOR,
    Gemx,
    GemxConfig,
)
from gemx.formats import OutputFormat, format_instruction


def test_config_defaults() -> None:
    cfg = GemxConfig(profile_dir=Path("/tmp/p"))
    assert cfg.headless is True
    assert cfg.response_timeout_s == 180
    assert "--no-sandbox" in cfg.launch_args


def test_selectors_match_debugged_values() -> None:
    # These are the selectors proven against the live Gemini UI; guard them.
    assert INPUT_SELECTOR == '.ql-editor[contenteditable="true"]'
    assert SEND_SELECTOR == 'button[aria-label="Send message"]'
    assert RESPONSE_SELECTOR == "message-content .markdown"


def test_ask_appends_format_instruction(monkeypatch) -> None:
    captured: dict[str, str] = {}

    async def fake_ask_raw(self: Gemx, prompt: str) -> str:
        captured["prompt"] = prompt
        return '{"ok": true}'

    monkeypatch.setattr(Gemx, "ask_raw", fake_ask_raw)

    import asyncio

    gemx = Gemx(GemxConfig(profile_dir=Path("/tmp/p")))
    result = asyncio.run(gemx.ask("base prompt", OutputFormat.JSON))

    assert result == {"ok": True}
    assert "base prompt" in captured["prompt"]
    assert format_instruction(OutputFormat.JSON) in captured["prompt"]
