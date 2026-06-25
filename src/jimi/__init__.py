"""Jimi — drive the Gemini web UI from Python.

A play on "Gemini". Treats ``gemini.google.com`` as if it were an API.
"""

from __future__ import annotations

from .client import Jimi, JimiConfig
from .errors import (
    InputError,
    JimiError,
    ResponseParseError,
    ResponseTimeoutError,
)
from .formats import OutputFormat, format_instruction, parse_output

__all__ = [
    "InputError",
    "Jimi",
    "JimiConfig",
    "JimiError",
    "OutputFormat",
    "ResponseParseError",
    "ResponseTimeoutError",
    "format_instruction",
    "parse_output",
]

__version__ = "0.1.0"
