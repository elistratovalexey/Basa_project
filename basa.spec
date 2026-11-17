# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []
for pkg in ("holidays", "babel", "tkcalendar", "pdfminer", "pdfplumber",
            "pypdfium2", "deep_translator", "qrcode"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception as e:
        print(f"[spec] пропускаю {pkg}: {e}")

hiddenimports += collect_submodules("tabs")
hiddenimports += collect_submodules("dialogs")
hiddenimports += ["sqlite3", "openpyxl", "docx", "PIL", "PIL._tkinter_finder",
                  "cloud_sync", "reminders", "terminal_log", "settings_dialog"]
a = Analysis(["app.py"], pathex=[], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, hookspath=[], runtime_hooks=[],
             excludes=["matplotlib", "PyQt5", "PyQt6", "PySide2", "PySide6", "pytest", "IPython"],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="BasaProject",
          debug=False, strip=False, upx=False, console=False,
          icon="app.ico" if os.path.exists("app.ico") else None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="BasaProject")