# -*- coding: utf-8 -*-
"""Напоминания: просрочки, поставки на неделе, неоплаченные счета, запросы цены."""
import json
import os
import subprocess
from datetime import datetime

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "reminders_state.json")


def _load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(st):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def collect(db, project_name=None):
    d = db.get_dashboard(project_name)
    items = []
    for r in d["overdue"]:
        items.append(("critical", f"Просрочка {abs(r['Дней'])} дн.: заказ {r['№']} · {r['Проект']} · {r['Поставщик']}"))
    for r in d["soon"]:
        items.append(("normal", f"Поставка через {r['Дней']} дн.: заказ {r['№']} · {r['Проект']}"))
    for r in d["pay_week"]:
        items.append(("normal", f"Оплата на неделе: {r['Поставщик']} · {r['Сумма']} {r['Валюта']} · {r['Дата оплаты']}"))
    for r in d["no_confirm"]:
        items.append(("normal", f"Нет подтверждения {r['Дней']} дн.: заказ {r['№']} · {r['Поставщик']}"))
    for r in d["price_requests"]:
        items.append(("low", f"Запрос цены без оплаты/ответа: {r['№']} · {r['Проект']}"))
    return items


def _notify(title, body, urgency="normal"):
    try:
        subprocess.Popen(["notify-send", "-u", urgency, title, body],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def run_once(app, force=False):
    db = getattr(app, "db_manager", None)
    if db is None:
        return 0
    today = datetime.now().strftime("%Y-%m-%d")
    state = _load_state()
    items = collect(db)
    fresh = [(u, t) for u, t in items if state.get(t) != today]
    if not fresh and not force:
        return 0
    crit = [t for u, t in fresh if u == "critical"]
    other = [t for u, t in fresh if u != "critical"]
    if crit:
        _notify("База проектов · ПРОСРОЧКИ", "\n".join(crit[:8]), "critical")
    if other:
        _notify("База проектов · напоминания", "\n".join(other[:8]), "normal")
    if not crit and not other:
        _notify("База проектов", "Актуальных напоминаний нет", "low")
    for _, t in fresh:
        state[t] = today
    _save_state(state)
    if hasattr(app, "log_action"):
        try:
            app.log_action(f"Напоминания: {len(fresh)} (просрочек {len(crit)})")
        except Exception:
            pass
    return len(fresh)


def start_reminders(app, interval_min=60, first_delay_sec=20):
    """Периодический запуск через Tk after(). Вызывать после построения UI."""
    root = getattr(app, "root", None)
    if root is None:
        return

    def tick():
        try:
            run_once(app)
        except Exception as e:
            print(f"[reminders] {e}")
        try:
            root.after(interval_min * 60 * 1000, tick)
        except Exception:
            pass

    try:
        root.after(first_delay_sec * 1000, tick)
    except Exception:
        pass