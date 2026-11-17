# -*- coding: utf-8 -*-
"""Pre-build code check. Exit code 1 = do not build.
Output is ASCII-only: safe on Windows console (cp1252) and Linux."""
import ast
import pathlib
import re
import sys

# Windows console may be cp1252 -> force UTF-8 with replacement fallback
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = pathlib.Path(__file__).resolve().parent
DIRS = [ROOT, ROOT / "tabs", ROOT / "dialogs"]
SKIP = {"venv", "venv_win", ".git", "backups", "logs", "__pycache__", "build", "dist"}

errors, warnings, files = [], [], []
for d in DIRS:
    if d.is_dir():
        for p in sorted(d.glob("*.py")):
            if not any(part in SKIP for part in p.parts):
                files.append(p)

for p in files:
    rel = p.relative_to(ROOT).as_posix()
    src = p.read_text(encoding="utf-8")
    try:
        ast.parse(src, filename=str(p))
    except SyntaxError as e:
        errors.append(f"{rel}:{e.lineno}: {e.msg}")
        continue
    if re.search(r"^\s*def init\(", src, re.M):
        errors.append(f"{rel}: 'def init(' instead of '__init__'")
    if re.search(r"abspath\(file\)", src):
        errors.append(f"{rel}: 'abspath(file)' instead of '__file__'")
    if re.search(r"\)\s*\\\s*\n\s*from ", src):
        errors.append(f"{rel}: backslash after ')' before import -> SyntaxError")
    if re.search(r"<Control-[\u0430-\u044f\u0410-\u042f]>", src):
        errors.append(f"{rel}: Cyrillic keysym in bind -> TclError at startup")
    if '"\u041a\u041b\u042e\u0427"' in src or "\u0428\u0418\u0420\u0418\u041d\u0410x\u0412\u042b\u0421\u041e\u0422\u0410" in src:
        errors.append(f"{rel}: window_geometry placeholders left in code")
    if "\t" in src:
        warnings.append(f"{rel}: tab characters in indentation")

app_path = ROOT / "app.py"
if app_path.exists():
    app_src = app_path.read_text(encoding="utf-8")
    if "sys.stdout is None" not in app_src:
        warnings.append("app.py: no stdout guard (print() fails in windowed exe)")
else:
    errors.append("app.py is missing")

for p in files:
    print(f"  checked {p.relative_to(ROOT).as_posix()}")
print()
for w in warnings:
    print("WARN ", w)
for e in errors:
    print("ERROR", e)
print(f"\nFiles checked: {len(files)}, errors: {len(errors)}, warnings: {len(warnings)}")
if errors:
    print("PREFLIGHT FAILED")
    sys.exit(1)
print("PREFLIGHT OK - ready to build")