"""Tests for the CLI argument parsing and rendering."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from gemx.cli import _render, build_parser
from gemx.formats import OutputFormat


def test_parser_defaults() -> None:
    args = build_parser().parse_args(["hello"])
    assert args.prompt == "hello"
    assert args.format is OutputFormat.JSON
    assert args.profile_dir == Path("~/.gemx/profile")
    assert args.no_headless is False
    assert args.browser_channel is None


def test_parser_format_and_no_headless() -> None:
    args = build_parser().parse_args(["-f", "xml", "--no-headless", "hi"])
    assert args.format is OutputFormat.XML
    assert args.no_headless is True


def test_parser_browser_channel() -> None:
    args = build_parser().parse_args(["--browser-channel", "chrome-beta", "hi"])
    assert args.browser_channel == "chrome-beta"


def test_parser_rejects_bad_format() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["-f", "yaml", "hi"])


def test_render_json() -> None:
    assert _render({"a": 1}, OutputFormat.JSON) == '{\n  "a": 1\n}'


def test_render_txt() -> None:
    assert _render("hello", OutputFormat.TXT) == "hello"


def test_render_xml() -> None:
    el = ET.fromstring("<r><a>1</a></r>")
    assert _render(el, OutputFormat.XML) == "<r><a>1</a></r>"
