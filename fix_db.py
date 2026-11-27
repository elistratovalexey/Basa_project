# -*- coding: utf-8 -*-
"""Немедленное исправление БД на Windows: добавляет недостающие колонки
План-Факт v4 (remind_date и др.), из-за которых падает синхронизация.
Запуск:  python fix_db.py     (или  py fix_db.py)
Перед запуском ЗАКРОЙТЕ программу «Управление проектами».
"""
import os
import sqlite3

NEED = [
    ("remind_date",     "TEXT DEFAULT ''"),
    ("link_spec_id",    "INTEGER DEFAULT 0"),
    ("link_order_batch", "INTEGER DEFAULT 0"),
    ("auto_dates",      "INTEGER DEFAULT 0"),
    ("cost_weight",     "REAL DEFAULT 0"),
    ("notify_days",     "INTEGER DEFAULT 3"),
    ("is_blocked",      "INTEGER DEFAULT 0"),
    ("delay_reason",    "TEXT DEFAULT ''"),
    ("blocked_note",    "TEXT DEFAULT ''"),
    ("baseline_start",  "TEXT DEFAULT ''"),
    ("baseline_end",    "TEXT DEFAULT ''"),
]


def candidates():
    seen, out = set(), []
    roots = [os.environ.get("APPDATA"), os.environ.get("LOCALAPPDATA"), os.getcwd()]
    for root in roots:
        if not root:
            continue
        for p in (os.path.join(root, "BasaProject", "projects.db"),
                  os.path.join(root, "projects.db")):
            if p not in seen:
                seen.add(p)
                out.append(p)
    return out


def patch(path):
    con = sqlite3.connect(path, timeout=10)
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        if "plan_fact" not in tables:
            print(f"– пропуск (нет plan_fact): {path}")
            return False
        cols = [r[1] for r in con.execute("PRAGMA table_info(plan_fact)")]
        added = []
        for c, t in NEED:
            if c not in cols:
                con.execute(f"ALTER TABLE plan_fact ADD COLUMN {c} {t}")
                added.append(c)
        con.commit()
        print(f"✓ {path}")
        print("   добавлено:", ", ".join(added) if added else "всё уже на месте")
        return True
    finally:
        con.close()


def main():
    print("Поиск projects.db…\n")
    patched = False
    for p in candidates():
        if os.path.isfile(p):
            try:
                if patch(p):
                    patched = True
            except sqlite3.OperationalError as e:
                print(f"✗ {p}: {e}")
                print("   Закройте программу и повторите — БД занята.")
    if not patched:
        print("\nБД не найдена в стандартных папках.")
        print("Откройте в программе «Папка данных», скопируйте путь к projects.db")
        print("и запустите:  python fix_db.py \"C:\\путь\\projects.db\"")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        patch(sys.argv[1])
    else:
        main()
    input("\nГотово. Нажмите Enter для выхода…")