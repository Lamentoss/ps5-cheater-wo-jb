# PyInstaller spec: pyinstaller packaging/ps5-cheater.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
VERSION = "0.1.0"

hidden = (
    collect_submodules("pyremoteplay", filter=lambda name: ".gui" not in name and ".gamepad" not in name)
    + collect_submodules("uvicorn")
    + collect_submodules("mcp", filter=lambda name: not name.startswith("mcp.cli"))
    + ["netifaces", "ps5cheater.server", "ps5cheater.mcp_server"]
)
datas = [
    (str(ROOT / "src/ps5cheater/static"), "ps5cheater/static"),
    (str(ROOT / "src/ps5cheater/seed"), "ps5cheater/seed"),
] + collect_data_files("mcp")

a = Analysis(
    [str(ROOT / "packaging/entry.py")],
    pathex=[str(ROOT / "src")],
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "PySide6", "pygame", "pytest", "matplotlib", "numpy.tests"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ps5-cheater", console=False,
          target_arch="arm64", icon=str(ROOT / "packaging/icon.icns"))
coll = COLLECT(exe, a.binaries, a.datas, name="ps5-cheater")
app = BUNDLE(
    coll,
    name="PS5 Cheater.app",
    icon=str(ROOT / "packaging/icon.icns"),
    bundle_identifier="io.github.lamentoss.ps5cheater",
    version=VERSION,
    info_plist={
        "CFBundleDisplayName": "PS5 Cheater",
        "CFBundleShortVersionString": VERSION,
        "LSUIElement": True,
        "LSMinimumSystemVersion": "13.0",
        "NSLocalNetworkUsageDescription": "PS5 Cheater finds and connects to your PS5 on the local network.",
        "NSHumanReadableCopyright": "GPL-3.0-or-later",
    },
)
