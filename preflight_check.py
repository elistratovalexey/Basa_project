# -*- coding: utf-8 -*-
"""Pre-build code check. Exit code 1 = do not build.
ASCII-only output: safe on Windows console (cp1252) and Linux.

Usage:  python preflight_check.py [-q]
"""
import ast
import io
import pathlib
import re
import sys
import tokenize

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

QUIET = "-q" in sys.argv
ROOT = pathlib.Path(__file__).resolve().parent
DIRS = [ROOT, ROOT / "tabs", ROOT / "dialogs"]
SKIP_DIRS = {"venv", "venv_win", ".git", "backups", "logs", "__pycache__",
             "build", "dist", "app", "gradle"}
TOOLING = {"preflight_check.py", "test_project.py", "check_deps.py", "debug_word.py"}

BAD_ABS = "abspath" + "(file)"
BAD_KEY = "\u041a\u041b\u042e\u0427"
BAD_SIZE = "\u0428\u0418\u0420\u0418\u041d\u0410x\u0412\u042b\u0421\u041e\u0422\u0410"

RE_INIT = re.compile(r"^\s*def init\(", re.M)
RE_BACKSLASH = re.compile(r"\)\s*\\\s*\n\s*from ")
RE_CYR_KEYSYM = re.compile(r"<Control-[\u0430-\u044f\u0410-\u042f]>")
RE_GEOM_PLACEHOLDER = re.compile(
    r"(restore_geometry|track_geometry)\s*\([^)]*(?:" + BAD_KEY + "|" + BAD_SIZE + ")")
RE_CONFLICT = re.compile(r"^(<<<<<<< |=======$|>>>>>>> )", re.M)


def code_only(src):
    """Source without comments so checks do not fire on explanations."""
    try:
        toks = [t for t in tokenize.generate_tokens(io.StringIO(src).readline)
                if t.type != tokenize.COMMENT]
        return tokenize.untokenize(toks)
    except Exception:
        return src


errors, warnings, files = [], [], []
for d in DIRS:
    if d.is_dir():
        for p in sorted(d.glob("*.py")):
            if not any(part in SKIP_DIRS for part in p.parts):
                files.append(p)

for p in files:
    rel = p.relative_to(ROOT).as_posix()
    raw = p.read_text(encoding="utf-8")

    if RE_CONFLICT.search(raw):
        errors.append(f"{rel}: UNRESOLVED GIT MERGE CONFLICT markers")
        continue

    try:
        ast.parse(raw, filename=str(p))
    except SyntaxError as e:
        errors.append(f"{rel}:{e.lineno}: {e.msg}")
        continue

    src = code_only(raw)
    if RE_INIT.search(raw):
        errors.append(f"{rel}: 'def init(' instead of dunder __init__")
    if "\t" in raw:
        warnings.append(f"{rel}: tab characters in indentation")

    if p.name in TOOLING:
        continue

    if BAD_ABS in src:
        errors.append(f"{rel}: {BAD_ABS} used instead of __file__")
    if RE_BACKSLASH.search(raw):
        errors.append(f"{rel}: backslash after ')' before import")
    if RE_CYR_KEYSYM.search(src):
        errors.append(f"{rel}: Cyrillic keysym in bind -> TclError at startup")
    m = RE_GEOM_PLACEHOLDER.search(src)
    if m:
        errors.append(f"{rel}: placeholder passed to {m.group(1)}()")
    if "lambda: fail(str(e))" in src:
        errors.append(f"{rel}: closure over exception var 'e' -> NameError")

# --- локальные импорты должны разрешаться в файлы репозитория ---
present = set()
for p in files:
    mod = p.relative_to(ROOT).as_posix()[:-3].replace("/", ".")
    if mod.endswith(".__init__"):
        mod = mod[:-9]
    present.add(mod)
    present.add(mod.split(".")[0])
LOCAL_TOP = {m.split(".")[0] for m in present}

for p in files:
    rel = p.relative_to(ROOT).as_posix()
    try:
        tree = ast.parse(p.read_text(encoding="utf-8"))
    except Exception:
        continue
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                top = a.name.split(".")[0]
                if top in LOCAL_TOP and a.name not in present:
                    errors.append(f"{rel}:{n.lineno}: import {a.name} -> FILE MISSING")
        elif isinstance(n, ast.ImportFrom) and n.module:
            top = n.module.split(".")[0]
            if top in LOCAL_TOP and n.module not in present:
                errors.append(f"{rel}:{n.lineno}: from {n.module} -> FILE MISSING")

# --- файлы сборки ---
for f in ("app.py", "basa.spec", "requirements.txt", "paths.py", "version.py"):
    if not (ROOT / f).exists():
        errors.append(f"{f}: MISSING build file")
if not (ROOT / "VERSION").exists():
    warnings.append("VERSION: missing (version.py will use default base)")

app_path = ROOT / "app.py"
if app_path.exists() and "sys.stdout is None" not in app_path.read_text(encoding="utf-8"):
    warnings.append("app.py: no stdout guard (print() fails in windowed exe)")

if not QUIET:
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