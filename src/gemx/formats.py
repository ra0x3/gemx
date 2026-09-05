"""Output formats Gemx can request from Gemini.

The chosen format is injected into the prompt as an instruction and also drives
how Gemx extracts the structured payload from Gemini's reply.
"""

from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Any
from xml.etree import ElementTree as ET


class OutputFormat(StrEnum):
    """Structured output formats Gemx understands."""

    JSON = "json"
    XML = "xml"
    TXT = "txt"

    @classmethod
    def from_str(cls, value: str) -> OutputFormat:
        """Parse a format name case-insensitively.

        Raises:
            ValueError: If ``value`` is not a supported format.
        """
        try:
            return cls(value.strip().lower())
        except ValueError as exc:
            supported = ", ".join(f.value for f in cls)
            raise ValueError(
                f"Unsupported output format {value!r}; expected one of: {supported}"
            ) from exc


def format_instruction(fmt: OutputFormat) -> str:
    """Return the prompt instruction that asks Gemini for ``fmt`` output."""
    if fmt is OutputFormat.JSON:
        return (
            "Respond with a single valid JSON object only. Do not include prose, "
            "markdown fences, or commentary outside the JSON."
        )
    if fmt is OutputFormat.XML:
        return (
            "Respond with a single well-formed XML document only. Do not include "
            "prose, markdown fences, or commentary outside the XML."
        )
    return (
        "Respond with plain text only. Do not include markdown fences, JSON, or "
        "XML."
    )


def _strip_fences(text: str) -> str:
    """Strip a leading format label and surrounding markdown code fences."""
    text = text.strip()
    text = re.sub(r"^(JSON|XML)\s*\n?", "", text, flags=re.IGNORECASE)
    fence = re.search(r"```[a-zA-Z]*\s*(.*?)```", text, flags=re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return text


def _clean_json_text(text: str) -> str:
    """Best-effort repair of common JSON quirks in LLM output."""
    text = text.strip()
    # Escape stray double-quotes inside values that denote feet/inches ("6'7"")
    # or pounds ("282 lbs""), which otherwise break the string early.
    text = re.sub(r'(\d+\'\d+)"(")', r'\1\\"\2', text)
    text = re.sub(r'(\d+ lbs)"(")', r'\1\\"\2', text)
    # Strip trailing commas before a closing brace/bracket.
    text = re.sub(r",\s*([}\]])", r"\1", text)
    # Python-isms LLMs sometimes emit instead of JSON literals.
    text = re.sub(r"\bNone\b", "null", text)
    text = re.sub(r"\bTrue\b", "true", text)
    text = re.sub(r"\bFalse\b", "false", text)
    # Leading + on numbers (e.g. "margin": +5).
    text = re.sub(r"([:,\[])\s*\+(\d+\.?\d*)", r"\1 \2", text)
    return text


def _first_json_object(text: str) -> str | None:
    """The first complete top-level ``{...}`` in ``text``, or None.

    ``rfind("}")`` walks past the object into whatever Gemini wrote after it,
    and on a reply that is still streaming it lands on a nested brace, so the
    slice it hands back is not the object at all. Depth counting stops at the
    real end; strings and their escapes are skipped so a brace inside a value
    does not move the depth.
    """
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def parse_output(text: str, fmt: OutputFormat) -> Any:
    """Extract a structured value from Gemini's raw reply for ``fmt``.

    JSON yields a ``dict``/``list``, XML yields an
    :class:`xml.etree.ElementTree.Element`, and TXT yields the cleaned ``str``.

    Raises:
        ValueError: If the payload cannot be parsed as ``fmt``.
    """
    cleaned = _strip_fences(text)

    if fmt is OutputFormat.TXT:
        return cleaned

    if fmt is OutputFormat.JSON:
        repaired = _clean_json_text(cleaned)
        candidate = _first_json_object(repaired)
        if candidate is None:
            start = repaired.find("{")
            end = repaired.rfind("}") + 1
            candidate = repaired[start:end] if start != -1 and end != 0 else repaired
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Could not parse JSON from response: {exc}") from exc

    start = cleaned.find("<")
    end = cleaned.rfind(">") + 1
    candidate = cleaned[start:end] if start != -1 and end != 0 else cleaned
    try:
        return ET.fromstring(candidate)
    except ET.ParseError as exc:
        raise ValueError(f"Could not parse XML from response: {exc}") from exc
