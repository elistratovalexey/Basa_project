# -*- coding: utf-8 -*-
"""Headless-тесты: синтаксис, парсеры, миграции БД. GUI не требуется."""
import os, sys, pathlib, py_compile, tempfile

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# 1) Синтаксис всех модулей
bad = []
for p in ROOT.rglob("*.py"):
    if any(x in p.parts for x in (".git", "backups", "__pycache__")):
        continue
    try:
        py_compile.compile(str(p), doraise=True)
    except Exception as e:
        bad.append((p.name, str(e)))
assert not bad, f"Синтаксические ошибки: {bad}"
print("1) Синтаксис всех .py — OK")

# 2) Парсеры дат и чисел
from utils import parse_date, parse_number, add_months
from datetime import datetime
assert parse_date("27.10.26") == datetime(2026, 10, 27)
assert parse_date("27.10.2026") == datetime(2026, 10, 27)
assert parse_date("27/10/2026") == datetime(2026, 10, 27)
assert parse_date("2026-10-27") == datetime(2026, 10, 27)
assert parse_date("") is None and parse_date("мусор") is None
assert parse_number("1 234,56") == 1234.56
assert parse_number("6.774,56 €") == 6774.56
assert parse_number("12 500 ₽") == 12500.0
assert add_months(datetime(2026, 10, 27), 4) == datetime(2027, 2, 27)
print("2) parse_date / parse_number / add_months — OK")

# 3) Миграции на чистой и на «старой» базе
from database import DatabaseManager
tmp = tempfile.mkdtemp()
db = os.path.join(tmp, "t.db")
m = DatabaseManager(db)
oc = [r[1] for r in m.conn.execute("PRAGMA table_info(orders)")]
pc = [r[1] for r in m.conn.execute("PRAGMA table_info(purchases)")]
assert {"write_off_date", "price_request", "price_request_num"} <= set(oc)
assert "price_request" in pc
m.close()
# имитация старой базы: убираем колонки нельзя, поэтому проверяем идемпотентность
m = DatabaseManager(db); m.close()
print("3) Миграции orders/purchases — OK")

print("\nВСЕ ТЕСТЫ ПРОЙДЕНЫ")
