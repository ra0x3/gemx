"""Command-line interface: ``gemx``."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

from . import __version__
from .client import Gemx, GemxConfig
from .errors import GemxError
from .formats import OutputFormat

DEFAULT_PROFILE_DIR = Path("~/.gemx/profile")


def build_parser() -> argparse.ArgumentParser:
    """Construct the ``gemx`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="gemx",
        description="Drive the Gemini web UI from the command line.",
    )
    parser.add_argument("--version", action="version", version=f"gemx {__version__}")
    parser.add_argument(
        "prompt",
        nargs="?",
        help="Prompt to send. If omitted, read from stdin.",
    )
    parser.add_argument(
        "-f",
        "--format",
        type=OutputFormat.from_str,
        default=OutputFormat.JSON,
        metavar="{json,xml,txt}",
        help="Output format requested from Gemini (default: json).",
    )
    parser.add_argument(
        "-p",
        "--profile-dir",
        type=Path,
        default=DEFAULT_PROFILE_DIR,
        help=f"Chrome profile dir for the session (default: {DEFAULT_PROFILE_DIR}).",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Show the browser window instead of running headless.",
    )
    parser.add_argument(
        "--browser-channel",
        default=None,
        help=(
            "Playwright browser channel to launch. Defaults to chrome when "
            "--no-headless is set."
        ),
    )
    parser.add_argument(
        "--response-timeout",
        type=int,
        default=180,
        metavar="SECONDS",
        help="Max seconds to wait for a response to start (default: 180).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=None,
        metavar="COUNT",
        help=(
            "Retry transient Gemini response failures up to COUNT times. "
            "Omitting this flag disables retries."
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Log progress to stderr.",
    )
    return parser


def _render(value: object, fmt: OutputFormat) -> str:
    """Serialize a parsed value back to a string for stdout."""
    if fmt is OutputFormat.JSON:
        return json.dumps(value, indent=2, ensure_ascii=False)
    if fmt is OutputFormat.XML:
        assert isinstance(value, ET.Element)
        return ET.tostring(value, encoding="unicode")
    return str(value)


async def _run(args: argparse.Namespace) -> int:
    prompt = args.prompt if args.prompt is not None else sys.stdin.read()
    prompt = prompt.strip()
    if not prompt:
        print("error: empty prompt", file=sys.stderr)
        return 2

    config = GemxConfig(
        profile_dir=args.profile_dir,
        headless=not args.no_headless,
        browser_channel=args.browser_channel or ("chrome" if args.no_headless else None),
        response_timeout_s=args.response_timeout,
        max_retries=args.max_retries or 0,
    )
    try:
        async with Gemx(config) as gemx:
            result = await gemx.ask(prompt, args.format)
    except GemxError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(_render(result, args.format))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``gemx`` console script."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
