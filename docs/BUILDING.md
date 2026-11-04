# Building from source

You need Python 3.10 to 3.12. Python 3.13 and later are not supported by the pinned dependencies.

## Run from source

```bash
git clone https://github.com/Lamentoss/ps5-cheater-wo-jb.git
cd ps5-cheater-wo-jb
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/ps5-cheater
```

| Command | What it does |
| --- | --- |
| `ps5-cheater` | Starts the server and opens the browser |
| `ps5-cheater serve` | Starts the server only |
| `ps5-cheater mcp` | Runs the MCP server over stdio |
| `--port 9000` | Uses another port, 8765 by default |

## Demo mode

Demo mode uses a fake console, so you can try everything without a PS5.

```bash
PS5CHEATER_MOCK=1 PS5CHEATER_HOME=/tmp/ps5-demo .venv/bin/ps5-cheater
```

`PS5CHEATER_HOME` moves the database and log, so your real data stays untouched.

## Tests

```bash
.venv/bin/python -m pytest
```

The tests use the fake console and never touch a real PS5.

## Package the macOS app

```bash
./packaging/build_macos.sh
```

This produces `dist/PS5 Cheater.app` and `dist/PS5-Cheater-<version>-macos-arm64.zip`. The build matches the Mac it runs on, and the app gets an ad-hoc signature only.

## Project layout

| Path | Purpose |
| --- | --- |
| `src/ps5cheater/console.py` | Discovery, pairing, Remote Play session |
| `src/ps5cheater/runner.py` | One connection per run, cheat playback |
| `src/ps5cheater/db.py` | SQLite database and packs |
| `src/ps5cheater/server.py` | Local web server |
| `src/ps5cheater/mcp_server.py` | MCP tools and HTTP transport |
| `src/ps5cheater/static/` | Web interface |
| `src/ps5cheater/seed/` | Built-in cheat packs |
| `packaging/` | macOS app build |

## Why dependencies are pinned

`pyremoteplay` 0.7.6 breaks with newer versions of some libraries, so `pyee`, `async-timeout` and `av` stay on tested versions. `mcp` stays below 2.
