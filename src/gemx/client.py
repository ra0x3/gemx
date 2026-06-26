"""Drive the Gemini web UI via Playwright.

This is a formalized version of a hack that drives ``gemini.google.com/app`` as
if it were an API. The non-obvious parts (and why this exists):

* **Input** must go through ``document.execCommand('insertText')``. Gemini's
  editor is Quill, which keeps its own document model and ignores DOM surgery,
  Playwright ``fill()``, and synthetic ``InputEvent``s — those leave the model
  empty and the turn errors with "I encountered an error". ``execCommand`` fires
  the trusted ``beforeinput``/``input`` pair Quill honors, exactly like a paste.
* **The response** lives in ``message-content .markdown`` (not a bare
  ``.markdown``), and Gemini re-mounts / empties that node after streaming, so we
  retain the *peak* text seen rather than reading the DOM once at the end.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.async_api import Page, async_playwright

from .errors import InputError, ResponseTimeoutError
from .formats import OutputFormat, format_instruction, parse_output

logger = logging.getLogger("gemx")

GEMINI_URL = "https://gemini.google.com/app"
INPUT_SELECTOR = '.ql-editor[contenteditable="true"]'
SEND_SELECTOR = 'button[aria-label="Send message"]'
RESPONSE_SELECTOR = "message-content .markdown"

_INSERT_TEXT_JS = """(text) => {
    const editor = document.querySelector('.ql-editor[contenteditable="true"]');
    if (!editor) return false;
    editor.focus();
    const sel = window.getSelection();
    sel.removeAllRanges();
    const range = document.createRange();
    range.selectNodeContents(editor);
    range.collapse(false);
    sel.addRange(range);
    return document.execCommand('insertText', false, text);
}"""

_LONGEST_RESPONSE_JS = """(args) => {
    const [selector, initialCount] = args;
    const els = document.querySelectorAll(selector);
    if (els.length <= initialCount) return '';
    let best = '';
    els.forEach(el => {
        const t = el.innerText || el.textContent || '';
        if (t.length > best.length) best = t;
    });
    return best;
}"""

_SCROLL_INPUT_JS = """(selector) => {
    const el = document.querySelector(selector);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
}"""

_CLICK_SEND_JS = """(selector) => {
    const btn = document.querySelector(selector);
    if (btn) { btn.click(); return true; }
    return false;
}"""

_DISMISS_WELCOME_JS = """() => {
    const buttons = Array.from(document.querySelectorAll('button, [role="button"]'));
    for (const btn of buttons) {
        const text = btn.innerText || btn.textContent || '';
        if (text.match(/continue|get started|skip|next|accept|try gemini/i)) {
            btn.click();
            return true;
        }
    }
    return false;
}"""


@dataclass(frozen=True, slots=True)
class GemxConfig:  # pylint: disable=too-many-instance-attributes
    """Tunables for a :class:`Gemx` session.

    Defaults mirror the behavior of the original ``bot/gemini.py`` driver this
    library was extracted from; every value is overridable.
    """

    profile_dir: Path
    headless: bool = True
    nav_timeout_ms: int = 60_000
    input_timeout_ms: int = 30_000
    response_timeout_s: int = 180
    stabilization_timeout_s: int = 120
    poll_interval_s: int = 2
    viewport_width: int = 1280
    viewport_height: int = 720
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    launch_args: tuple[str, ...] = field(
        default=(
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
        )
    )
    # Extra HTTP headers passed to the persistent context (the original driver
    # supplied a "clean headers" set). None means no extra headers.
    extra_http_headers: tuple[tuple[str, str], ...] | None = None
    # Settle waits (ms) that the original driver interleaved so Gemini's UI/Quill
    # editor caught up before the next action.
    post_load_settle_ms: int = 5_000
    settle_after_input_ms: int = 1_000
    settle_after_submit_ms: int = 500
    scroll_input_into_view: bool = True
    # The original required the peak response to exceed this length and stay
    # stable for this many ticks before accepting it as complete.
    min_response_chars: int = 50
    stable_ticks: int = 2


class Gemx:
    """A Gemini web-UI session.

    Use as an async context manager so the browser is cleaned up::

        async with Gemx(GemxConfig(profile_dir=Path("~/.gemx/profile"))) as gemx:
            data = await gemx.ask("List 3 fruits", OutputFormat.JSON)
    """

    def __init__(self, config: GemxConfig) -> None:
        self._config = config

    async def ask(
        self, prompt: str, fmt: OutputFormat = OutputFormat.JSON
    ) -> Any:
        """Send ``prompt`` to Gemini and return its reply parsed as ``fmt``.

        The format instruction is appended to the prompt so Gemini emits the
        requested shape.

        Raises:
            InputError: If the prompt could not be entered.
            ResponseTimeoutError: If no response arrived in time.
            ResponseParseError: If the reply could not be parsed as ``fmt``.
        """
        full_prompt = f"{prompt}\n\n{format_instruction(fmt)}"
        raw = await self.ask_raw(full_prompt)
        return parse_output(raw, fmt)

    async def ask_raw(self, prompt: str) -> str:
        """Send ``prompt`` verbatim and return Gemini's raw reply text."""
        cfg = self._config
        profile = cfg.profile_dir.expanduser()
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                str(profile),
                headless=cfg.headless,
                args=list(cfg.launch_args),
                user_agent=cfg.user_agent,
                viewport={
                    "width": cfg.viewport_width,
                    "height": cfg.viewport_height,
                },
                extra_http_headers=(
                    dict(cfg.extra_http_headers)
                    if cfg.extra_http_headers
                    else None
                ),
            )
            try:
                page = (
                    context.pages[0] if context.pages else await context.new_page()
                )
                await self._navigate(page)
                await self._enter_prompt(page, prompt)
                await self._submit(page)
                return await self._await_response(page)
            finally:
                await context.close()

    async def _navigate(self, page: Page) -> None:
        cfg = self._config
        logger.info("navigating to %s", GEMINI_URL)
        await page.goto(GEMINI_URL, wait_until="load", timeout=cfg.nav_timeout_ms)
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_load_state("networkidle", timeout=30_000)
        await page.wait_for_timeout(5_000)

        await page.wait_for_timeout(cfg.post_load_settle_ms)

        body_text = await page.evaluate("() => document.body.innerText || ''")
        if "welcome to gemini" in body_text.lower():
            logger.info("welcome screen detected; dismissing")
            dismissed = await page.evaluate(_DISMISS_WELCOME_JS)
            logger.info("welcome screen dismissed=%s", dismissed)
            await page.wait_for_timeout(3_000 if dismissed else 1_000)

        await page.wait_for_selector(INPUT_SELECTOR, timeout=cfg.input_timeout_ms)
        logger.info("input box ready (%s)", INPUT_SELECTOR)

        if cfg.scroll_input_into_view:
            await page.evaluate(_SCROLL_INPUT_JS, INPUT_SELECTOR)
            await page.wait_for_timeout(1_000)

    async def _enter_prompt(self, page: Page, prompt: str) -> None:
        cfg = self._config
        await page.click(INPUT_SELECTOR)
        ok: bool = await page.evaluate(_INSERT_TEXT_JS, prompt)
        entered = (await page.locator(INPUT_SELECTOR).first.inner_text()).strip()
        logger.info("entered prompt: ok=%s chars=%d", ok, len(entered))
        if not ok or not entered:
            raise InputError("Quill did not accept the prompt text")
        await page.wait_for_timeout(cfg.settle_after_input_ms)

    async def _submit(self, page: Page) -> None:
        cfg = self._config
        await page.wait_for_selector(SEND_SELECTOR, timeout=cfg.input_timeout_ms)
        # The original driver clicked the button via document.querySelector(...)
        # .click() rather than Playwright's actionability-gated page.click(); the
        # latter can no-op against Gemini's send button.
        clicked: bool = await page.evaluate(_CLICK_SEND_JS, SEND_SELECTOR)
        logger.info("found send button (%s); submitting clicked=%s", SEND_SELECTOR, clicked)
        await page.wait_for_timeout(cfg.settle_after_submit_ms)

    async def _await_response(self, page: Page) -> str:
        cfg = self._config
        initial = await page.evaluate(
            "(s) => document.querySelectorAll(s).length", RESPONSE_SELECTOR
        )

        # Wait for a new response node to appear.
        logger.info(
            "waiting for response node (timeout=%ds, %d existing)",
            cfg.response_timeout_s,
            initial,
        )
        elapsed = 0
        while elapsed < cfg.response_timeout_s:
            count = await page.evaluate(
                "(s) => document.querySelectorAll(s).length", RESPONSE_SELECTOR
            )
            if count > initial:
                logger.info("response node appeared after %ds", elapsed)
                break
            await asyncio.sleep(cfg.poll_interval_s)
            elapsed += cfg.poll_interval_s
        else:
            raise ResponseTimeoutError(
                f"No response node after {cfg.response_timeout_s}s"
            )

        # Stream until the longest node's text stops growing, retaining the peak.
        # Gemini flashes the finished answer then re-mounts/empties the node, so
        # the peak text is retained and a non-growing tick counts as settling.
        logger.info("streaming response (stabilize timeout=%ds)", cfg.stabilization_timeout_s)
        best = ""
        last_len = 0
        stable = 0
        waited = 0
        while waited < cfg.stabilization_timeout_s:
            await asyncio.sleep(cfg.poll_interval_s)
            waited += cfg.poll_interval_s
            current: str = await page.evaluate(
                _LONGEST_RESPONSE_JS, [RESPONSE_SELECTOR, initial]
            )
            if len(current) > len(best):
                best = current
            if len(current) > last_len:
                logger.info("response growing: %d chars (t=%ds)", len(current), waited)
                last_len = len(current)
                stable = 0
            elif best:
                stable += 1
                logger.info(
                    "response stable %d/%d at %d chars (t=%ds)",
                    stable,
                    cfg.stable_ticks,
                    len(best),
                    waited,
                )
                if stable >= cfg.stable_ticks and len(best) > cfg.min_response_chars:
                    logger.info("response settled at %d chars", len(best))
                    break

        if not best:
            raise ResponseTimeoutError("Response node never produced text")
        return best

    async def __aenter__(self) -> Gemx:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None
