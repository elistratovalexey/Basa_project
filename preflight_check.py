# -*- coding: utf-8 -*-
"""Pre-build code check for Basa_project. Exit code 1 = do not build.

Output is ASCII-only: safe on Windows console (cp1252) and on Linux.
Cyrillic search patterns are written via \\uXXXX escapes so this file
does not flag itself.

Checks (ERROR -> build blocked):
  * syntax of every project .py (ast.parse)
  * 'def init(' instead of dunder __init__
  * 'abspath(file)' instead of __file__
  * backslash after ')' before an import line
  * Cyrillic keysym in bind() -> TclError at startup
  * window_geometry placeholders left in code
  * lambda closing over 'e' from except -> NameError at call time
  * local module imported but file missing in repo (both import forms)
Checks (WARN -> build allowed):
  * tabs in indentation
  * no stdout guard in app.py (print() fails in windowed exe)
  * missing optional build file (basa.spec)
  * missing local module imported inside try/except (soft import)

Usage:  python preflight_check.py [-q]
        -q  do not print the per-file "checked" list
"""
import ast
import io
import pathlib
import re
import sys
import tokenize

<<<<<<< HEAD
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
    
=======
>>>>>>> eb530b97f2cefc0e88447bc32c25d0016fd68c35
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

QUIET = "-q" in sys.argv
ROOT = pathlib.Path(__file__).resolve().parent
DIRS = [ROOT, ROOT / "tabs", ROOT / "dialogs"]
SKIP_DIRS = {"venv", "venv_win", ".venv", "env", ".git", "backups", "logs",
             "__pycache__", "build", "dist", "Output", "site-packages",
             "app", "gradle", ".github"}

# Tooling files contain the search patterns as literal text -> content checks skipped
TOOLING = {"preflight_check.py", "test_project.py", "check_deps.py", "debug_word.py"}

# Patterns assembled so that this file never matches itself
BAD_ABS = "abspath" + "(file)"
BAD_KEY = "\u041a\u041b\u042e\u0427"                                  # КЛЮЧ
BAD_SIZE = "\u0428\u0418\u0420\u0418\u041d\u0410x\u0412\u042b\u0421\u041e\u0422\u0410"
RE_INIT = re.compile(r"^\s*def init\(", re.M)
RE_BACKSLASH = re.compile(r"\)\s*\\\s*\n\s*from ")
RE_CYR_KEYSYM = re.compile(r"<Control-[\u0430-\u044f\u0410-\u042f]>")
RE_CLOSURE_E = re.compile(r"lambda\s*:\s*[^\n]*\bstr\(e\)")

errors, warnings, files = [], [], []


def code_only(src):
    """Source with comments stripped: checks must not fire on explanations."""
    try:
        toks = [t for t in tokenize.generate_tokens(io.StringIO(src).readline)
                if t.type != tokenize.COMMENT]
        return tokenize.untokenize(toks)
    except Exception:
        return src


def collect_files():
    seen = set()
    for d in DIRS:
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.py")):
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            if p not in seen:
                seen.add(p)
                files.append(p)


collect_files()

# ---------------------------------------------------------------
# 1. Per-file checks
# ---------------------------------------------------------------
trees = {}
for p in files:
    rel = p.relative_to(ROOT).as_posix()
    raw = p.read_text(encoding="utf-8")
    try:
        trees[p] = ast.parse(raw, filename=str(p))
    except SyntaxError as e:
        errors.append(f"{rel}:{e.lineno}: {e.msg}")
        continue
    except Exception as e:
        errors.append(f"{rel}: cannot parse ({type(e).__name__}: {e})")
        continue

    src = code_only(raw)

    if RE_INIT.search(src):
        errors.append(f"{rel}: 'def init(' instead of dunder __init__")
    if "\t" in raw:
        warnings.append(f"{rel}: tab characters in indentation")

    if p.name in TOOLING:
        continue

    if BAD_ABS in src:
        errors.append(f"{rel}: {BAD_ABS} used instead of __file__")
    if RE_BACKSLASH.search(src):
        errors.append(f"{rel}: backslash after ')' before import -> SyntaxError")
    if RE_CYR_KEYSYM.search(src):
        errors.append(f"{rel}: Cyrillic keysym in bind -> TclError at startup")
<<<<<<< HEAD
    m = RE_GEOM_PLACEHOLDER.search(src)
    if m:
        errors.append(f"{rel}: placeholder passed to {m.group(1)}() — "
                      f"replace with a real window key and size")        errors.append(f"{rel}: window_geometry placeholders left in code")
=======
    if BAD_KEY in src or BAD_SIZE in src:
        errors.append(f"{rel}: window_geometry placeholders left in code")
    if RE_CLOSURE_E.search(src):
        errors.append(f"{rel}: lambda closes over 'e' from except -> NameError; "
                      f"use msg = str(e) then lambda m=msg: ...")
>>>>>>> eb530b97f2cefc0e88447bc32c25d0016fd68c35

# ---------------------------------------------------------------
# 2. Local imports must resolve to files present in the repo
#    (this is what catches a lost module before PyInstaller builds a broken exe)
# ---------------------------------------------------------------
present = set()
for p in files:
    mod = p.relative_to(ROOT).as_posix()[:-3].replace("/", ".")
    if mod.endswith(".__init__"):
        mod = mod[:-9]
    present.add(mod)
    present.add(mod.split(".")[0])

LOCAL_TOP = {m.split(".")[0] for m in present}

for p, tree in trees.items():
    rel = p.relative_to(ROOT).as_posix()
    in_try = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Try):
            for sub in n.body:
                for x in ast.walk(sub):
                    in_try.add(id(x))

    def report(missing_name, lineno, soft):
        msg = f"{rel}:{lineno}: import {missing_name} -> FILE MISSING in repo"
        if soft:
            warnings.append(msg + " (soft import, feature disabled)")
        else:
            errors.append(msg)

    for n in ast.walk(tree):
        soft = id(n) in in_try
        if isinstance(n, ast.Import):
            for a in n.names:
                top = a.name.split(".")[0]
                if top in LOCAL_TOP and a.name not in present:
                    report(a.name, n.lineno, soft)
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            top = n.module.split(".")[0]
            if top in LOCAL_TOP and n.module not in present:
                report(n.module, n.lineno, soft)

# ---------------------------------------------------------------
# 3. app.py / build files
# ---------------------------------------------------------------
app_path = ROOT / "app.py"
if app_path.exists():
    app_src = app_path.read_text(encoding="utf-8")
    if "sys.stdout is None" not in app_src:
        warnings.append("app.py: no stdout guard (print() fails in windowed exe)")
else:
    errors.append("app.py is missing")

if not (ROOT / "requirements.txt").exists():
    errors.append("requirements.txt is missing")
if not (ROOT / "basa.spec").exists():
    warnings.append("basa.spec is missing (needed for Windows build)")

# ---------------------------------------------------------------
# 4. Report
# ---------------------------------------------------------------
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
