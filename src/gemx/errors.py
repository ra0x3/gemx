"""Exceptions raised by Gemx."""

from __future__ import annotations


class GemxError(Exception):
    """Base class for all Gemx errors."""


class InputError(GemxError):
    """The prompt could not be entered into Gemini's editor."""


class ResponseTimeoutError(GemxError):
    """Gemini did not produce a response within the configured window."""


class ResponseParseError(GemxError):
    """Gemini responded, but the payload could not be parsed for the format."""
