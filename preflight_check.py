# -*- coding: utf-8 -*-
"""Проверка кода перед сборкой exe. Код возврата 1 = собирать нельзя."""
import ast
import pathlib
import re
import sys

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
    rel = p.relative_to(ROOT)
    src = p.read_text(encoding="utf-8")
    try:
        ast.parse(src, filename=str(p))
    except SyntaxError as e:
        errors.append(f"{rel}:{e.lineno}: {e.msg}")
        continue
    if re.search(r"^\s*def init\(", src, re.M):
        errors.append(f"{rel}: 'def init(' вместо '__init__'")
    if re.search(r"abspath\(file\)", src):
        errors.append(f"{rel}: 'abspath(file)' вместо '__file__'")
    if re.search(r"\)\s*\\\s*\n\s*from ", src):
        errors.append(f"{rel}: обратный слэш после ')' перед import")
    if re.search(r"<Control-[а-яА-Я]>", src):
        errors.append(f"{rel}: кириллический keysym в bind → TclError при старте")
    if '"КЛЮЧ"' in src or "ШИРИНАxВЫСОТА" in src:
        errors.append(f"{rel}: заглушки window_geometry")
    if "\t" in src:
        warnings.append(f"{rel}: табы в отступах")

app_path = ROOT / "app.py"
if app_path.exists():
    app = app_path.read_text(encoding="utf-8")
    if "sys.stdout is None" not in app:
        warnings.append("app.py: нет защиты stdout (в оконном exe print() упадёт)")
else:
    errors.append("app.py отсутствует")

for p in files:
    print(f"  проверен {p.relative_to(ROOT)}")
print()
for w in warnings:
    print("WARN ", w)
for e in errors:
    print("ERROR", e)
print(f"\nПроверено файлов: {len(files)}, ошибок: {len(errors)}, предупреждений: {len(warnings)}")
if errors:
    sys.exit(1)
print("Код готов к сборке.")