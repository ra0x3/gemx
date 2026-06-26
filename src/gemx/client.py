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
RESPONSE_SELECTORS = (
    "message-content .markdown",
    "message-content",
    "model-response .markdown",
    "model-response",
    ".model-response-text",
    ".markdown",
)

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

_INSTALL_RESPONSE_OBSERVER_JS = """(selectors) => {
    if (window.__gemxResponseObserver) {
        window.__gemxResponseObserver.disconnect();
    }
    window.__gemxInitialCounts = {};
    selectors.forEach(sel => {
        window.__gemxInitialCounts[sel] = document.querySelectorAll(sel).length;
    });
    window.__gemxBestResponse = { text: '', selector: '', length: 0 };

    const scan = () => {
        selectors.forEach(sel => {
            const els = Array.from(document.querySelectorAll(sel));
            const initial = window.__gemxInitialCounts[sel] || 0;
            els.slice(initial).forEach(el => {
                const text = el.innerText || el.textContent || '';
                if (text.length > window.__gemxBestResponse.length) {
                    window.__gemxBestResponse = {
                        text,
                        selector: sel,
                        length: text.length
                    };
                }
            });
        });
        return window.__gemxBestResponse;
    };

    scan();
    window.__gemxResponseObserver = new MutationObserver(scan);
    window.__gemxResponseObserver.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true
    });
    return window.__gemxInitialCounts;
}"""

_READ_RESPONSE_OBSERVER_JS = """() => {
    return window.__gemxBestResponse || { text: '', selector: '', length: 0 };
}"""

_LONGEST_RESPONSE_JS = """(args) => {
    const [selectors, initialCounts] = args;
    let best = '';
    let selector = '';
    selectors.forEach(sel => {
        const els = Array.from(document.querySelectorAll(sel));
        const initial = initialCounts[sel] || 0;
        els.slice(initial).forEach(el => {
            const t = el.innerText || el.textContent || '';
            if (t.length > best.length) {
                best = t;
                selector = sel;
            }
        });
    });
    const observed = window.__gemxBestResponse || { text: '', selector: '', length: 0 };
    if ((observed.text || '').length > best.length) {
        return observed;
    }
    return { text: best, selector, length: best.length };
}"""

_PAGE_ELEMENTS_JS = """() => {
    return {
        hasTextarea: document.querySelector('textarea') !== null,
        hasContentEditable: document.querySelector('[contenteditable="true"]') !== null,
        hasRichTextarea: document.querySelector('rich-textarea') !== null,
        hasQlEditor: document.querySelector('.ql-editor') !== null,
        visibleButtons: Array.from(document.querySelectorAll('button')).slice(0, 5)
            .map(b => b.innerText || b.textContent).filter(t => t),
        pageHeight: document.body.scrollHeight,
        viewportHeight: window.innerHeight
    };
}"""

_RESPONSE_DIAGNOSTICS_JS = """() => {
    return {
        hasThinking: document.querySelector('.thinking, .loading, [aria-label*="Loading"], [aria-label*="Thinking"]') !== null,
        hasError: document.querySelector('.error, [data-error], [aria-label*="Error"]') !== null,
        hasInput: document.querySelector('textarea, [contenteditable="true"]') !== null,
        bodyText: document.body.innerText.substring(0, 200)
    };
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

_SEND_BUTTON_STATE_JS = """(selector) => {
    const btn = document.querySelector(selector);
    if (!btn) return { exists: false };
    return {
        exists: true,
        disabled: btn.disabled || btn.getAttribute('aria-disabled') === 'true',
        visible: btn.offsetParent !== null
    };
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
    browser_channel: str | None = None
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
    # The peak response must exceed this length and stay non-growing (or be
    # emptied) for this many poll ticks before it is accepted as complete.
    # Matches the original bot/gemini.py driver (stable_count >= 2).
    min_response_chars: int = 50
    stable_ticks: int = 2
    # How often (seconds) to emit page diagnostics while waiting for the response
    # node to appear.
    diagnostics_interval_s: int = 10


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
        raw = await self.ask_raw(full_prompt, fmt)
        return parse_output(raw, fmt)

    async def ask_raw(
        self, prompt: str, expected_format: OutputFormat | None = None
    ) -> str:
        """Send ``prompt`` verbatim and return Gemini's raw reply text.

        If ``expected_format`` is JSON or XML, Gemx waits for the response to
        parse before returning. Gemini can briefly stop growing while still
        holding an incomplete structured payload.
        """
        cfg = self._config
        profile = cfg.profile_dir.expanduser()
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                str(profile),
                headless=cfg.headless,
                channel=cfg.browser_channel,
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
                return await self._await_response(page, expected_format)
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

        page_elements = await page.evaluate(_PAGE_ELEMENTS_JS)
        logger.info("page elements: %s", page_elements)

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
        initial_counts = await page.evaluate(
            _INSTALL_RESPONSE_OBSERVER_JS, list(RESPONSE_SELECTORS)
        )
        logger.info("response observer installed: %s", initial_counts)
        button_info = await page.evaluate(_SEND_BUTTON_STATE_JS, SEND_SELECTOR)
        logger.info("send button state: %s", button_info)
        # The original driver clicked the button via document.querySelector(...)
        # .click() rather than Playwright's actionability-gated page.click(); the
        # latter can no-op against Gemini's send button.
        clicked: bool = await page.evaluate(_CLICK_SEND_JS, SEND_SELECTOR)
        logger.info(
            "found send button (%s); submitting clicked=%s",
            SEND_SELECTOR,
            clicked,
        )
        await page.wait_for_timeout(cfg.settle_after_submit_ms)

    async def _await_response(
        self, page: Page, expected_format: OutputFormat | None = None
    ) -> str:
        cfg = self._config
        initial_counts = await page.evaluate(
            "() => window.__gemxInitialCounts || {}"
        )

        # Wait for either a durable response node or transient observed text.
        logger.info(
            "waiting for response node/text (timeout=%ds, initial=%s)",
            cfg.response_timeout_s,
            initial_counts,
        )
        elapsed = 0
        while elapsed < cfg.response_timeout_s:
            current = await page.evaluate(
                _LONGEST_RESPONSE_JS, [list(RESPONSE_SELECTORS), initial_counts]
            )
            current_text = str(current.get("text") or "")
            if current_text:
                logger.info(
                    "response text appeared after %ds (%d chars via %s)",
                    elapsed,
                    len(current_text),
                    current.get("selector"),
                )
                break
            if elapsed > 0 and elapsed % cfg.diagnostics_interval_s == 0:
                diag = await page.evaluate(_RESPONSE_DIAGNOSTICS_JS)
                observed = await page.evaluate(_READ_RESPONSE_OBSERVER_JS)
                logger.info(
                    "diag @%ds: thinking=%s error=%s input=%s observed=%s",
                    elapsed,
                    diag.get("hasThinking"),
                    diag.get("hasError"),
                    diag.get("hasInput"),
                    observed.get("length"),
                )
                if diag.get("hasError"):
                    logger.warning(
                        "error indicator detected; page snippet: %s",
                        diag.get("bodyText"),
                    )
            await asyncio.sleep(cfg.poll_interval_s)
            elapsed += cfg.poll_interval_s
        else:
            await page.screenshot(path="/tmp/gemini-timeout-debug.png")
            body_text = await page.evaluate(
                "() => document.body.innerText.substring(0, 500)"
            )
            logger.error("response node timeout; page content: %s", body_text)
            raise ResponseTimeoutError(
                f"No response text after {cfg.response_timeout_s}s"
            )

        # Stream until the longest node's text stops growing, retaining the peak.
        # Gemini flashes the finished answer then re-mounts/empties the node, so
        # the peak text is retained. Structured responses must parse before they
        # count as complete; a stable partial JSON object is still incomplete.
        logger.info(
            "streaming response (stabilize timeout=%ds)",
            cfg.stabilization_timeout_s,
        )
        best = ""
        last_len = 0
        stable = 0
        waited = 0
        complete = False
        last_parse_error: ValueError | None = None
        while waited < cfg.stabilization_timeout_s:
            await asyncio.sleep(cfg.poll_interval_s)
            waited += cfg.poll_interval_s
            current = await page.evaluate(
                _LONGEST_RESPONSE_JS, [list(RESPONSE_SELECTORS), initial_counts]
            )
            current_text = str(current.get("text") or "")
            current_selector = str(current.get("selector") or "")
            current_length = len(current_text)
            if current_length > len(best):
                best = current_text
            if current_length > last_len:
                logger.info(
                    "response growing: %d chars (was %d via %s)",
                    current_length,
                    last_len,
                    current_selector,
                )
                last_len = current_length
                stable = 0
            elif best and current_length <= last_len:
                # Either stable or the node was emptied after flashing the answer.
                # For structured output, still prove the peak text parses.
                stable += 1
                logger.debug(
                    "response settled for %ds (current: %d, peak: %d)",
                    stable * cfg.poll_interval_s,
                    current_length,
                    len(best),
                )
                if stable >= cfg.stable_ticks and len(best) > cfg.min_response_chars:
                    if expected_format in (OutputFormat.JSON, OutputFormat.XML):
                        try:
                            parse_output(best, expected_format)
                        except ValueError as exc:
                            last_parse_error = exc
                            if waited % cfg.diagnostics_interval_s == 0:
                                logger.info(
                                    "response stable but %s is incomplete "
                                    "after %ds: %s",
                                    expected_format.value,
                                    waited,
                                    exc,
                                )
                            continue
                    logger.info(
                        "generation complete after ~%ds (peak length: %d chars)",
                        waited,
                        len(best),
                    )
                    complete = True
                    break
            elif waited % cfg.diagnostics_interval_s == 0:
                logger.info("still waiting for response content after %ds...", waited)

        if not best:
            raise ResponseTimeoutError("Response node never produced text")
        if expected_format in (OutputFormat.JSON, OutputFormat.XML) and not complete:
            await page.screenshot(path="/tmp/gemini-incomplete-response.png")
            logger.warning(
                "response did not parse as %s; preview: %r",
                expected_format.value,
                best[:500],
            )
            if last_parse_error is not None:
                raise ResponseTimeoutError(
                    "Response did not become complete "
                    f"{expected_format.value} after "
                    f"{cfg.stabilization_timeout_s}s: {last_parse_error}"
                ) from last_parse_error
            raise ResponseTimeoutError(
                "Response did not become complete "
                f"{expected_format.value} after {cfg.stabilization_timeout_s}s"
            )
        return best

    async def __aenter__(self) -> Gemx:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None
