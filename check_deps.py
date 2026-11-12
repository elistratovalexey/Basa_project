# -*- coding: utf-8 -*-
"""Проверка сторонних зависимостей в текущем окружении."""
import importlib
import sys

MODULES = {
    "holidays": "holidays",
    "openpyxl": "openpyxl",
    "docx": "python-docx",
    "pdfplumber": "pdfplumber",
    "deep_translator": "deep-translator",
    "tkcalendar": "tkcalendar",
}

print("Интерпретатор:", sys.executable)
missing = []
for mod, pkg in MODULES.items():
    try:
        m = importlib.import_module(mod)
        print(f"  OK   {mod:16} {getattr(m, '__version__', '')}")
    except Exception as e:
        print(f"  FAIL {mod:16} -> pip install {pkg}   ({e.__class__.__name__})")
        missing.append(pkg)

if missing:
    print("\nДоустановите:\n  python -m pip install " + " ".join(missing))
    sys.exit(1)
print("\nВсе зависимости установлены")