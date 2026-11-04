#!/bin/bash
# Builds dist/PS5 Cheater.app and a zip for the release page.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
"$PY" packaging/make_icon.py
"$PY" -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/ps5-cheater.spec
VERSION=$("$PY" -c "import sys; sys.path.insert(0, 'src'); import ps5cheater; print(ps5cheater.__version__)")
ditto -c -k --keepParent --sequesterRsrc "dist/PS5 Cheater.app" "dist/PS5-Cheater-${VERSION}-macos-arm64.zip"
ls -lh dist/*.zip
