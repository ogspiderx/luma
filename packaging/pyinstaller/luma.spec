import os

from PyInstaller.utils.hooks import collect_all, copy_metadata

ROOT = os.path.dirname(os.path.dirname(SPECPATH))
ICON_PATH = os.path.join(ROOT, "packaging", "windows", "luma.ico")

textual_datas, textual_binaries, textual_hidden = collect_all("textual")
rich_datas, rich_binaries, rich_hidden = collect_all("rich")

datas = (
    [(os.path.join(ROOT, "luma", "luma.tcss"), "luma")]
    + textual_datas
    + rich_datas
    + copy_metadata("textual")
    + copy_metadata("rich")
)
binaries = textual_binaries + rich_binaries
hiddenimports = textual_hidden + rich_hidden

a = Analysis(
    [os.path.join(ROOT, "packaging", "pyinstaller", "entry.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Luma",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=ICON_PATH if os.path.isfile(ICON_PATH) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="Luma",
)
