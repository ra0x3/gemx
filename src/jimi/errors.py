"""Exceptions raised by Jimi."""

from __future__ import annotations


class JimiError(Exception):
    """Base class for all Jimi errors."""


class InputError(JimiError):
    """The prompt could not be entered into Gemini's editor."""


class ResponseTimeoutError(JimiError):
    """Gemini did not produce a response within the configured window."""


class ResponseParseError(JimiError):
    """Gemini responded, but the payload could not be parsed for the format."""
