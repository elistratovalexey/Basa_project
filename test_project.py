# -*- coding: utf-8 -*-
"""Быстрые headless-тесты: синтаксис кода проекта, парсеры, миграции БД.
venv и сторонние библиотеки НЕ сканируются."""
import ast
import os
import pathlib
import sys
import tempfile
import warnings
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore", SyntaxWarning)  # предупреждения сторонних библиотек

CODE_DIRS = [ROOT, ROOT / "tabs", ROOT / "dialogs"]
FAILURES = []


def project_py_files():
    seen = set()
    for d in CODE_DIRS:
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.py")):
            if p.resolve() == pathlib.Path(__file__).resolve():
                continue
            if p not in seen:
                seen.add(p)
                yield p


# --- 1. Синтаксис (ast.parse, без записи .pyc, только наши папки) ---
print("1) Синтаксис файлов проекта:")
n = 0
for p in project_py_files():
    n += 1
    rel = p.relative_to(ROOT)
    try:
        ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        print(f"   OK   {rel}", flush=True)
    except SyntaxError as e:
        print(f"   FAIL {rel}:{e.lineno}: {e.msg}", flush=True)
        FAILURES.append(f"синтаксис {rel}:{e.lineno}: {e.msg}")
print(f"   проверено файлов: {n}")

# --- 2. Парсеры дат и чисел ---
print("2) Парсеры utils:")
try:
    from utils import parse_date, parse_number, add_months
    cases = [
        ("parse_date('27.10.2026')", parse_date("27.10.2026"), datetime(2026, 10, 27)),
        ("parse_date('27.10.26')",   parse_date("27.10.26"),   datetime(2026, 10, 27)),
        ("parse_date('27/10/2026')", parse_date("27/10/2026"), datetime(2026, 10, 27)),
        ("parse_date('2026-10-27')", parse_date("2026-10-27"), datetime(2026, 10, 27)),
        ("parse_date('')",           parse_date(""),           None),
        ("parse_number('1 234,56')", parse_number("1 234,56"), 1234.56),
        ("parse_number('6.774,56 €')", parse_number("6.774,56 €"), 6774.56),
        ("add_months(27.10.2026, 4)", add_months(datetime(2026, 10, 27), 4), datetime(2027, 2, 27)),
    ]
    for name, got, want in cases:
        ok = (got == want)
        print(f"   {'OK  ' if ok else 'FAIL'} {name} -> {got!r}")
        if not ok:
            FAILURES.append(f"{name}: ожидалось {want!r}, получено {got!r}")
except Exception as e:
    print(f"   FAIL импорт utils: {e}")
    FAILURES.append(f"импорт utils: {e}")

# --- 3. Миграции БД на временной базе ---
print("3) Миграции database.DatabaseManager:")
try:
    from database import DatabaseManager
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "t.db")
    m = DatabaseManager(db)
    oc = [r[1] for r in m.conn.execute("PRAGMA table_info(orders)")]
    pc = [r[1] for r in m.conn.execute("PRAGMA table_info(purchases)")]
    for col, table, cols in (("write_off_date", "orders", oc),
                             ("price_request", "orders", oc),
                             ("price_request_num", "orders", oc),
                             ("price_request", "purchases", pc)):
        ok = col in cols
        print(f"   {'OK  ' if ok else 'FAIL'} {table}.{col}")
        if not ok:
            FAILURES.append(f"нет колонки {table}.{col} (нужна миграция в database.py)")
    m.close()
    m = DatabaseManager(db)  # идемпотентность повторного открытия
    m.close()
    print("   OK   повторное открытие базы")
except Exception as e:
    print(f"   FAIL database: {e}")
    FAILURES.append(f"database: {e}")
    


print("4) Контракт purchases ↔ database:")
import os, tempfile
from database import DatabaseManager
for name in ("get_next_price_request_num", "move_purchase",
             "set_order_price_request", "set_order_write_off_date"):
    ok = hasattr(DatabaseManager, name)
    print(f"   {'OK  ' if ok else 'FAIL'} DatabaseManager.{name}")
    if not ok: FAILURES.append(f"нет метода {name}")

m = DatabaseManager(os.path.join(tempfile.mkdtemp(), "c.db"))
m.add_project("A", "/tmp"); m.add_project("B", "/tmp")
a, b = m.get_project_id("A"), m.get_project_id("B")
m.add_purchase(a, {"number": 1, "article": "X", "quantity": 1, "price_request": 1})
try:
    print("   OK   project_name =", m.get_purchases(a)[0]["project_name"])
except Exception as e:
    print("   FAIL project_name:", e); FAILURES.append("get_purchases без JOIN")
if hasattr(m, "move_purchase"):
    print("   OK   move_purchase → №", m.move_purchase(a, 1, b))
m.close()

print()
if FAILURES:
    print("НАЙДЕНЫ ПРОБЛЕМЫ:")
    for f in FAILURES:
        print(" -", f)
    sys.exit(1)
print("ВСЕ ТЕСТЫ ПРОЙДЕНЫ")