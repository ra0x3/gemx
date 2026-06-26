# Gemx

**Drive the Gemini web UI from Python.** A play on "Gemini" — Gemx treats
`gemini.google.com` as if it were an API, using Playwright to enter a prompt,
submit it, and capture the structured reply.

It exists because the obvious approaches don't work: Gemini's editor is
[Quill](https://quilljs.com/), which keeps its own document model and ignores
DOM surgery, Playwright `fill()`, and synthetic input events — those leave the
model empty and the turn errors with *"I encountered an error."* Gemx injects
text via `execCommand('insertText')` (the same trusted input pipeline a manual
paste uses), reads the reply from `message-content .markdown`, and retains the
*peak* streamed text because Gemini re-mounts the response node mid-stream.

## Install

```bash
uv add gemx
# Playwright needs a browser the first time:
uv run playwright install chromium
```

## CLI

```bash
# JSON (default)
gemx "List 3 NBA teams as a JSON array"

# XML
gemx --format xml "Describe the solar system as XML"

# Plain text, reading the prompt from stdin
echo "Summarize the plot of Dune in one sentence" | gemx --format txt

# Watch the browser while it works
gemx --no-headless --verbose "Hello there"
```

The chosen `--format` (`json`, `xml`, or `txt`) is appended to the prompt as an
instruction *and* drives how Gemx parses the reply.

| Option | Description |
| --- | --- |
| `-f, --format {json,xml,txt}` | Output format (default: `json`). |
| `-p, --profile-dir PATH` | Chrome profile dir (default: `~/.gemx/profile`). |
| `--no-headless` | Show the browser window. |
| `--browser-channel` | Playwright browser channel to launch; defaults to `chrome` with `--no-headless`. |
| `--response-timeout SECONDS` | Wait for a response to start (default: 180). |
| `--max-retries COUNT` | Retry transient Gemini response failures up to COUNT times. Omitted means no retries. |
| `-v, --verbose` | Log progress to stderr. |

## Library

```python
import asyncio
from pathlib import Path
from gemx import Gemx, GemxConfig, OutputFormat


async def main() -> None:
    config = GemxConfig(profile_dir=Path("~/.gemx/profile"))
    async with Gemx(config) as gemx:
        data = await gemx.ask("List 3 fruits as JSON", OutputFormat.JSON)
        print(data)


asyncio.run(main())
```

## Authentication

Gemx drives a real, signed-in Gemini session. Point `--profile-dir` at a Chrome
profile that is already logged into your Google account (run once with
`--no-headless` to sign in); subsequent runs reuse that profile.

## Development

```bash
uv sync
uv run ruff check .
uv run mypy
uv run pylint src/gemx
uv run pytest
```

The browser-console debugging scripts used to discover and verify the current
Gemini selectors live in [`tests/scripts/`](tests/scripts/).

## License

MIT © ra0x3 — [Stonehedge Labs](https://github.com/stonehedgelabs)
