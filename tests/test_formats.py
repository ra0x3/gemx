"""Tests for output-format parsing and instructions."""

from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest

from jimi.formats import (
    OutputFormat,
    format_instruction,
    parse_output,
)


def test_from_str_case_insensitive() -> None:
    assert OutputFormat.from_str("JSON") is OutputFormat.JSON
    assert OutputFormat.from_str(" xml ") is OutputFormat.XML
    assert OutputFormat.from_str("txt") is OutputFormat.TXT


def test_from_str_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        OutputFormat.from_str("yaml")


@pytest.mark.parametrize("fmt", list(OutputFormat))
def test_format_instruction_nonempty(fmt: OutputFormat) -> None:
    assert format_instruction(fmt).strip()


def test_parse_json_plain() -> None:
    assert parse_output('{"a": 1}', OutputFormat.JSON) == {"a": 1}


def test_parse_json_in_fence() -> None:
    raw = "Here you go:\n```json\n{\"b\": [1, 2]}\n```"
    assert parse_output(raw, OutputFormat.JSON) == {"b": [1, 2]}


def test_parse_json_trailing_comma() -> None:
    assert parse_output('{"a": 1,}', OutputFormat.JSON) == {"a": 1}


def test_parse_json_with_label_prefix() -> None:
    assert parse_output('JSON\n{"x": true}', OutputFormat.JSON) == {"x": True}


def test_parse_json_invalid_raises() -> None:
    with pytest.raises(ValueError):
        parse_output("not json at all", OutputFormat.JSON)


def test_parse_txt_passthrough() -> None:
    assert parse_output("  hello world  ", OutputFormat.TXT) == "hello world"


def test_parse_txt_strips_fence() -> None:
    assert parse_output("```\nplain\n```", OutputFormat.TXT) == "plain"


def test_parse_xml() -> None:
    el = parse_output("<root><a>1</a></root>", OutputFormat.XML)
    assert isinstance(el, ET.Element)
    assert el.tag == "root"
    assert el.findtext("a") == "1"


def test_parse_xml_in_fence() -> None:
    raw = "```xml\n<r><b>2</b></r>\n```"
    el = parse_output(raw, OutputFormat.XML)
    assert el.findtext("b") == "2"


def test_parse_xml_invalid_raises() -> None:
    with pytest.raises(ValueError):
        parse_output("<unclosed>", OutputFormat.XML)
