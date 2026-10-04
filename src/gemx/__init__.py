"""Gemx — drive the Gemini web UI from Python.

A play on "Gemini". Treats ``gemini.google.com`` as if it were an API.
"""

from __future__ import annotations

from .client import Gemx, GemxConfig
from .errors import (
    GemxError,
    InputError,
    ProfileBusyError,
    ResponseParseError,
    ResponseTimeoutError,
)
from .formats import OutputFormat, format_instruction, parse_output

__all__ = [
    "Gemx",
    "GemxConfig",
    "GemxError",
    "InputError",
    "OutputFormat",
    "ProfileBusyError",
    "ResponseParseError",
    "ResponseTimeoutError",
    "format_instruction",
    "parse_output",
]

__version__ = "0.2.2"
