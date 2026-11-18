# -*- coding: utf-8 -*-
"""Pre-build code check. Exit code 1 = do not build.
ASCII-only output: safe on Windows console (cp1252) and Linux."""
import ast
import pathlib
import re
import sys
import io
import tokenize

for f in ("version.py", "VERSION"):
    if not (ROOT / f).exists():
        errors.append(f"{f}: MISSING (версия не будет вычисляться)")


def code_only(src):
    """Текст без комментариев — проверки не срабатывают на пояснения в коде."""
    try:
        toks = [t for t in tokenize.generate_tokens(io.StringIO(src).readline)
                if t.type != tokenize.COMMENT]
        return tokenize.untokenize(toks)
    except Exception:
        return src
    
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = pathlib.Path(__file__).resolve().parent
DIRS = [ROOT, ROOT / "tabs", ROOT / "dialogs"]
SKIP_DIRS = {"venv", "venv_win", ".git", "backups", "logs", "__pycache__", "build", "dist"}
# Служебные файлы содержат шаблоны проверок в виде текста -> контент-проверки к ним не применяем
TOOLING = {"preflight_check.py", "test_project.py", "check_deps.py", "debug_word.py"}

# шаблоны собираются конкатенацией/escape, чтобы файл не детектировал сам себя
BAD_ABS = "abspath" + "(file)"
BAD_KEY = "\u041a\u041b\u042e\u0427"                                  # КЛЮЧ
BAD_SIZE = "\u0428\u0418\u0420\u0418\u041d\u0410x\u0412\u042b\u0421\u041e\u0422\u0410"
RE_INIT = re.compile(r"^\s*def init\(", re.M)
RE_BACKSLASH = re.compile(r"\)\s*\\\s*\n\s*from ")
RE_CYR_KEYSYM = re.compile(r"<Control-[\u0430-\u044f\u0410-\u042f]>")

errors, warnings, files = [], [], []
for d in DIRS:
    if d.is_dir():
        for p in sorted(d.glob("*.py")):
            if not any(part in SKIP_DIRS for part in p.parts):
                files.append(p)

for p in files:
    rel = p.relative_to(ROOT).as_posix()
    src = p.read_text(encoding="utf-8")
    try:
        ast.parse(src, filename=str(p))
    except SyntaxError as e:
        errors.append(f"{rel}:{e.lineno}: {e.msg}")
        continue

    if RE_INIT.search(src):
        errors.append(f"{rel}: 'def init(' instead of dunder __init__")
    if "\t" in src:
        warnings.append(f"{rel}: tab characters in indentation")

    if p.name in TOOLING:
        continue                      # дальше — проверки содержимого, не для инструментов

    if BAD_ABS in src:
        errors.append(f"{rel}: {BAD_ABS} used instead of __file__")
    if RE_BACKSLASH.search(src):
        errors.append(f"{rel}: backslash after ')' before import -> SyntaxError")
    if RE_CYR_KEYSYM.search(src):
        errors.append(f"{rel}: Cyrillic keysym in bind -> TclError at startup")
    m = RE_GEOM_PLACEHOLDER.search(src)
    if m:
        errors.append(f"{rel}: placeholder passed to {m.group(1)}() — "
                      f"replace with a real window key and size")        errors.append(f"{rel}: window_geometry placeholders left in code")

app_path = ROOT / "app.py"
if app_path.exists():
    if "sys.stdout is None" not in app_path.read_text(encoding="utf-8"):
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