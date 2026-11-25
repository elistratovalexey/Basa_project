# -*- coding: utf-8 -*-
"""Напоминания: просрочки поставок, поставки на неделе, неоплаченные счета,
запросы цены без ответа, сроки работ из «План-Факт».

Запуск: start_reminders(app, interval_min=60) — периодический через Tk after().
Ручной запуск: run_once(app, force=True).
Проверка без GUI: python reminders.py
"""
import json
import os
import platform
import subprocess
import tempfile
from datetime import datetime, timedelta


def _log_dir():
    """Логи — в папке данных (paths.LOG_DIR), иначе рядом с модулем."""
    try:
        from paths import LOG_DIR
        return LOG_DIR
    except Exception:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")


STATE_FILE = os.path.join(_log_dir(), "reminders_state.json")
STATE_KEEP_DAYS = 7


def _load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            st = json.load(f)
        return st if isinstance(st, dict) else {}
    except Exception:
        return {}


def _save_state(st):
    """Храним только свежие отметки, чтобы файл не рос бесконечно."""
    try:
        limit = (datetime.now() - timedelta(days=STATE_KEEP_DAYS)).strftime("%Y-%m-%d")
        st = {k: v for k, v in st.items() if str(v) >= limit}
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ======================================================================
def collect(db, project_name=None):
    """Собирает список (urgency, text). urgency: critical | normal | low."""
    items = []

    # --- Заказы и счета (дашборд) ---
    try:
        d = db.get_dashboard(project_name)
    except Exception as e:
        print(f"[reminders] dashboard: {e}")
        d = {}

    for r in d.get("overdue", []):
        items.append(("critical",
                      f"Просрочка {abs(r['Дней'])} дн.: заказ {r['№']} · "
                      f"{r['Проект']} · {r['Поставщик']}"))

    for r in d.get("soon", []):
        items.append(("normal",
                      f"Поставка через {r['Дней']} дн.: заказ {r['№']} · {r['Проект']}"))

    for r in d.get("pay_week", []):
        items.append(("normal",
                      f"Оплата на неделе: {r['Поставщик']} · {r['Сумма']} {r['Валюта']} · "
                      f"{r['Дата оплаты']}"))

    for r in d.get("no_confirm", []):
        items.append(("normal",
                      f"Нет подтверждения {r['Дней']} дн.: заказ {r['№']} · {r['Поставщик']}"))

    for r in d.get("price_requests", []):
        items.append(("low",
                      f"Запрос цены без оплаты/ответа: {r['№']} · {r['Проект']}"))

    # Неоплаченные счета — раньше собирались, но не показывались
    for r in d.get("unpaid_inv", []):
        total = r.get("Сумма") or 0
        try:
            total = f"{float(total):,.0f}".replace(",", " ")
        except (TypeError, ValueError):
            pass
        items.append(("low",
                      f"Неоплаченный счёт: {r.get('Поставщик') or '—'} · {total} "
                      f"{r.get('Валюта') or ''} · {r.get('Проект') or ''}".rstrip()))

    # --- План-Факт: сроки работ (если БД обновлена до v3) ---
    if hasattr(db, "pf_notifications"):
        try:
            for n in db.pf_notifications(days_ahead=3):
                kind = n.get("kind")
                who = n.get("responsible") or "—"
                head = (f"[{n.get('project')}] работа №{n.get('number')} "
                        f"«{n.get('name')}» ({who})")
                if kind in ("overdue", "late_start"):
                    items.append(("critical", f"{head}: {n.get('text')}"))
                elif kind == "blocked":
                    items.append(("normal", f"{head}: {n.get('text')}"))
                elif kind == "deadline_soon":
                    items.append(("normal", f"{head}: {n.get('text')}"))
                elif kind == "start_soon":
                    items.append(("low", f"{head}: {n.get('text')}"))
        except Exception as e:
            print(f"[reminders] план-факт: {e}")

    return items


# ======================================================================
def _notify(title, body, urgency="normal"):
    """Системное уведомление: Linux — notify-send, Windows — balloon tip."""
    urgency = urgency if urgency in ("low", "normal", "critical") else "normal"
    system = platform.system()
    title = str(title).replace("'", "''").strip()
    body = str(body).replace("\n", " · ").replace("'", "''").strip()[:240]

    if system == "Linux":
        try:
            subprocess.Popen(["notify-send", "-u", urgency, title, body],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False

    if system == "Windows":
        try:
            ps1 = os.path.join(tempfile.gettempdir(), "basa_notify.ps1")
            script = (
                "Add-Type -AssemblyName System.Windows.Forms;"
                "Add-Type -AssemblyName System.Drawing;"
                "$n = New-Object System.Windows.Forms.NotifyIcon;"
                "$n.Icon = [System.Drawing.SystemIcons]::Information;"
                f"$n.BalloonTipTitle = '{title}';"
                f"$n.BalloonTipText = '{body}';"
                "$n.Visible = $true; $n.ShowBalloonTip(8000);"
                "Start-Sleep -Seconds 9; $n.Dispose();"
            )
            with open(ps1, "w", encoding="utf-8-sig") as f:
                f.write(script)
            subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-WindowStyle", "Hidden", "-File", ps1],
                creationflags=0x08000000,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False

    return False

def _collect_mail(app):
    """Письма без ответа дольше SLA (из второй базы mail.db)."""
    mdb = getattr(app, "mail_db", None)
    db = getattr(app, "db_manager", None)
    if mdb is None:
        return []
    try:
        sla = int(mdb.get_settings().get("reply_sla_days", 2))
    except Exception:
        sla = 2
    names = {}
    if db is not None:
        try:
            names = {p["id"]: p["name"] for p in db.get_all_projects()}
        except Exception:
            names = {}
    out = []
    try:
        for r in mdb.unanswered_ids(sla_days=sla):
            proj = names.get(r["project_id"], "")
            days = ""
            try:
                d0 = datetime.strptime((r["date_iso"] or "")[:10], "%Y-%m-%d")
                days = f" · {(datetime.now() - d0).days} дн"
            except Exception:
                pass
            out.append(("normal",
                        f"Письмо без ответа: [{proj}] «{r['subject'] or ''}» "
                        f"от {r['sender'] or '—'}{days}"))
    except Exception as e:
        print(f"[reminders] почта: {e}")
    return out
# ======================================================================
def run_once(app, force=False):
    """Один проход: собрать → отфильтровать уже показанные сегодня → уведомить."""
    db = getattr(app, "db_manager", None)
    if db is None:
        return 0

    today = datetime.now().strftime("%Y-%m-%d")
    state = _load_state()

    try:
        items = collect(db)
    try:
        items += _collect_mail(app)
    except Exception as e:
        print(f"[reminders] mail collect: {e}")
    except Exception as e:
        print(f"[reminders] collect: {e}")
        return 0

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
            root.after(max(1, int(interval_min)) * 60 * 1000, tick)
        except Exception:
            pass

    try:
        root.after(first_delay_sec * 1000, tick)
    except Exception:
        pass


# ======================================================================
if __name__ == "__main__":
    # Проверка без GUI: python reminders.py [имя_проекта]
    import sys
    from database import DatabaseManager

    try:
        from config import get_db_path
        path = get_db_path()
    except Exception:
        path = "projects.db"

    db = DatabaseManager(path)
    proj = sys.argv[1] if len(sys.argv) > 1 else None
    rows = collect(db, proj)
    print(f"База: {path}")
    print(f"Состояние: {STATE_FILE}")
    print(f"Напоминаний: {len(rows)} "
          f"(критичных {sum(1 for u, _ in rows if u == 'critical')})")
    for u, t in rows[:40]:
        print(f"  [{u:8}] {t}")
    if "--test" in sys.argv:
        ok = _notify("База проектов · тест", "Проверка уведомлений", "normal")
        print("Тестовое уведомление отправлено:", ok)
    db.close()
