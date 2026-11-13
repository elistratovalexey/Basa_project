# -*- coding: utf-8 -*-
"""
Headless-тесты проекта «База проектов».

Запуск:  python test_project.py

Блоки:
  1) синтаксис всех .py проекта (корень, tabs/, dialogs/)
  2) парсеры utils (даты, числа, месяцы, сроки поставки)
  3) миграции и CRUD database (на временной базе)
  4) контракт API: purchases ↔ database
  5) сторонние зависимости
  6) статические подсказки (предупреждения, не валят прогон)

Код возврата: 0 — всё ОК, 1 — есть ошибки.
"""
import ast
import importlib
import os
import pathlib
import re
import sys
import tempfile
import warnings
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore", SyntaxWarning)

CODE_DIRS = [ROOT, ROOT / "tabs", ROOT / "dialogs"]
SKIP_DIRS = {"venv", ".venv", "env", ".git", "backups", "__pycache__", "logs", "site-packages"}

FAILURES = []
WARNINGS = []


def ok(msg):
    print(f"   OK   {msg}")


def fail(msg):
    print(f"   FAIL {msg}")
    FAILURES.append(msg)


def warn(msg):
    print(f"   WARN {msg}")
    WARNINGS.append(msg)


def project_py_files():
    """Только наши файлы: корень, tabs/, dialogs/ (без вложенных мусорных каталогов)."""
    seen = set()
    for d in CODE_DIRS:
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.py")):
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            if p.resolve() == pathlib.Path(__file__).resolve():
                continue
            if p not in seen:
                seen.add(p)
                yield p


# ------------------------------------------------------------------
# 1. Синтаксис
# ------------------------------------------------------------------
print("1) Синтаксис файлов проекта:")
count = 0
for p in project_py_files():
    count += 1
    rel = p.relative_to(ROOT)
    try:
        ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        ok(str(rel))
    except SyntaxError as e:
        fail(f"{rel}:{e.lineno}: {e.msg}")
    except Exception as e:
        fail(f"{rel}: {type(e).__name__}: {e}")
print(f"   проверено файлов: {count}")


# ------------------------------------------------------------------
# 2. Парсеры utils
# ------------------------------------------------------------------
print("2) Парсеры utils:")
try:
    from utils import parse_date, parse_number, add_months, parse_delivery_time

    date_cases = [
        ("parse_date('27.10.2026')", parse_date("27.10.2026"), datetime(2026, 10, 27)),
        ("parse_date('27.10.26')",   parse_date("27.10.26"),   datetime(2026, 10, 27)),
        ("parse_date('27/10/2026')", parse_date("27/10/2026"), datetime(2026, 10, 27)),
        ("parse_date('2026-10-27')", parse_date("2026-10-27"), datetime(2026, 10, 27)),
        ("parse_date('')",           parse_date(""),           None),
        ("parse_date('мусор')",      parse_date("мусор"),      None),
    ]
    num_cases = [
        ("parse_number('1 234,56')",   parse_number("1 234,56"),   1234.56),
        ("parse_number('6.774,56 €')", parse_number("6.774,56 €"), 6774.56),
        ("parse_number('12 500 ₽')",   parse_number("12 500 ₽"),   12500.0),
        ("parse_number('1234.56')",    parse_number("1234.56"),    1234.56),
        ("parse_number('')",           parse_number(""),           None),
    ]
    other_cases = [
        ("add_months(27.10.2026, 4)", add_months(datetime(2026, 10, 27), 4), datetime(2027, 2, 27)),
        ("add_months(31.01.2026, 1)", add_months(datetime(2026, 1, 31), 1), datetime(2026, 2, 28)),
        ("parse_delivery_time('6-8 HAFTA')", parse_delivery_time("6-8 HAFTA"), (8, "Недели")),
        ("parse_delivery_time('10 GÜN')",    parse_delivery_time("10 GÜN"),    (10, "Календарные дни")),
    ]
    for name, got, want in date_cases + num_cases + other_cases:
        if got == want:
            ok(f"{name} -> {got!r}")
        else:
            fail(f"{name}: ожидалось {want!r}, получено {got!r}")
except Exception as e:
    fail(f"импорт utils: {type(e).__name__}: {e}")


# ------------------------------------------------------------------
# 3. Миграции и CRUD database
# ------------------------------------------------------------------
print("3) Миграции и CRUD database.DatabaseManager:")
try:
    from database import DatabaseManager

    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "t.db")
    m = DatabaseManager(db_path)

    oc = [r[1] for r in m.conn.execute("PRAGMA table_info(orders)")]
    pc = [r[1] for r in m.conn.execute("PRAGMA table_info(purchases)")]
    for col, table, cols in (("write_off_date", "orders", oc),
                             ("price_request", "orders", oc),
                             ("price_request_num", "orders", oc),
                             ("received", "orders", oc),
                             ("receipt_date", "orders", oc),
                             ("delivery_number", "orders", oc),
                             ("price_request", "purchases", pc)):
        if col in cols:
            ok(f"{table}.{col}")
        else:
            fail(f"нет колонки {table}.{col} (нужна миграция в database.py)")

    m.close()
    m = DatabaseManager(db_path)   # идемпотентность повторного открытия
    ok("повторное открытие базы")

    # CRUD
    m.add_project("A", "/tmp")
    m.add_project("B", "/tmp")
    a, b = m.get_project_id("A"), m.get_project_id("B")
    m.add_purchase(a, {"number": 1, "article": "X", "name": "n",
                       "quantity": 2, "price_request": 1})
    if m.get_purchase_by_number(a, 1)["price_request"] == 1:
        ok("add_purchase сохраняет price_request")
    else:
        fail("add_purchase не сохранил price_request")

    m.set_purchase_flag(a, 1, "price_request", 0)
    if m.get_purchase_by_number(a, 1)["price_request"] == 0:
        ok("set_purchase_flag('price_request')")
    else:
        fail("set_purchase_flag('price_request') не сработал")

    try:
        m.set_purchase_flag(a, 1, "hacked", 1)
        fail("set_purchase_flag принял недопустимое поле")
    except ValueError:
        ok("set_purchase_flag отклоняет произвольное поле")

    batch = m.get_next_order_batch_id()
    z = m.get_next_price_request_num() if hasattr(m, "get_next_price_request_num") else 1
    m.add_order({"order_batch_id": batch, "order_date": "12.11.2026",
                 "project_name": "A", "article": "X", "quantity": 2,
                 "price_request": 1, "price_request_num": z})
    head = m.get_order_batches()[0]
    if head["price_request"] == 1 and head["price_request_num"] == z:
        ok(f"add_order / get_order_batches: Z{z}")
    else:
        fail("add_order/get_order_batches не сохраняют price_request/price_request_num")

    m.set_order_write_off_date(batch, "12.11.2026")
    if m.get_order_batches()[0]["write_off_date"] == "12.11.2026":
        ok("set_order_write_off_date")
    else:
        fail("set_order_write_off_date не записал дату")

    m.close()
except Exception as e:
    fail(f"database: {type(e).__name__}: {e}")


# ------------------------------------------------------------------
# 4. Контракт API: purchases ↔ database
# ------------------------------------------------------------------
print("4) Контракт API purchases ↔ database:")
try:
    from database import DatabaseManager

    for name in ("get_next_price_request_num", "move_purchase",
                 "set_order_price_request", "set_order_write_off_date",
                 "set_purchase_flag", "get_purchases"):
        if hasattr(DatabaseManager, name):
            ok(f"DatabaseManager.{name}")
        else:
            fail(f"нет метода DatabaseManager.{name} (вызывается из tabs/purchases.py)")

    tmp = tempfile.mkdtemp()
    m = DatabaseManager(os.path.join(tmp, "c.db"))
    m.add_project("A", "/tmp")
    m.add_project("B", "/tmp")
    a, b = m.get_project_id("A"), m.get_project_id("B")
    m.add_purchase(a, {"number": 1, "article": "X", "quantity": 1, "price_request": 1})

    try:
        pn = m.get_purchases(a)[0]["project_name"]
        ok(f"get_purchases → project_name = {pn}")
    except Exception as e:
        fail(f"get_purchases без JOIN projects: {type(e).__name__}: {e}")

    if hasattr(m, "move_purchase"):
        n = m.move_purchase(a, 1, b)
        if m.get_purchase_by_number(b, n) is not None:
            ok(f"move_purchase → новый №{n} в проекте B")
        else:
            fail("move_purchase не перенёс позицию")
    if hasattr(m, "get_next_price_request_num"):
        ok(f"get_next_price_request_num → {m.get_next_price_request_num()}")
    m.close()
except Exception as e:
    fail(f"контракт API: {type(e).__name__}: {e}")


# ------------------------------------------------------------------
# 5. Сторонние зависимости
# ------------------------------------------------------------------
print("5) Сторонние зависимости:")
DEPS = {
    "holidays": "holidays",
    "openpyxl": "openpyxl",
    "docx": "python-docx",
    "pdfplumber": "pdfplumber",
    "deep_translator": "deep-translator",
    "tkcalendar": "tkcalendar",
}
missing = []
for mod, pkg in DEPS.items():
    try:
        mm = importlib.import_module(mod)
        ok(f"{mod:16} {getattr(mm, '__version__', '')}")
    except Exception as e:
        fail(f"{mod:16} не установлена → pip install {pkg} ({type(e).__name__})")
        missing.append(pkg)
if missing:
    print("   Доустановите: python -m pip install " + " ".join(missing))


# ------------------------------------------------------------------
# 6. Статические подсказки (предупреждения)
# ------------------------------------------------------------------
print("6) Статические подсказки:")
hints = 0
for p in project_py_files():
    rel = p.relative_to(ROOT)
    try:
        s = p.read_text(encoding="utf-8")
    except Exception:
        continue
    if '"КЛЮЧ"' in s or "ШИРИНАxВЫСОТА" in s:
        warn(f"{rel}: остались заглушки window_geometry ('КЛЮЧ' / 'ШИРИНАxВЫСОТА')")
        hints += 1
    for g in re.finditer(r"self\.grab_set\(\)", s):
        ctx = s[max(0, g.start() - 300):g.start()]
        if "_safe_grab" not in ctx and "winfo_viewable" not in ctx:
            warn(f"{rel}: голый self.grab_set() — возможен 'grab failed: window not viewable'")
            hints += 1
            break
    if "traceback." in s and not re.search(r"^\s*import traceback", s, re.M):
        warn(f"{rel}: используется traceback, но нет 'import traceback'")
        hints += 1
    if re.search(r"^\s*def init\(", s, re.M):
        warn(f"{rel}: найдено 'def init(' — возможно, потеряны подчёркивания __init__")
        hints += 1
if hints == 0:
    ok("подсказок нет")


# ------------------------------------------------------------------
# Итог
# ------------------------------------------------------------------
print()
if WARNINGS:
    print(f"ПРЕДУПРЕЖДЕНИЙ: {len(WARNINGS)}")
    for w in WARNINGS:
        print(" -", w)
    print()
if FAILURES:
    print(f"НАЙДЕНЫ ОШИБКИ ({len(FAILURES)}):")
    for f in FAILURES:
        print(" -", f)
    sys.exit(1)
print("ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
sys.exit(0)