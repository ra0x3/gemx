"""Gemx — drive the Gemini web UI from Python.

A play on "Gemini". Treats ``gemini.google.com`` as if it were an API.
"""

from __future__ import annotations

from .client import Gemx, GemxConfig
from .errors import (
    InputError,
    GemxError,
    ResponseParseError,
    ResponseTimeoutError,
)
from .formats import OutputFormat, format_instruction, parse_output

__all__ = [
    "InputError",
    "Gemx",
    "GemxConfig",
    "GemxError",
    "OutputFormat",
    "ResponseParseError",
    "ResponseTimeoutError",
    "format_instruction",
    "parse_output",
]

__version__ = "0.1.0"
