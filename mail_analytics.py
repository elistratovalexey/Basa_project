# -*- coding: utf-8 -*-
"""Аналитика переписки: надёжность поставщиков, инвойсы без заказа,
заказы без переписки, цены из писем → история цен.

Ничего не меняет в схеме БД — читает mail.db и projects.db.
"""
import re
import statistics
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime


def _dt(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    return None


def _norm_inv(s):
    return re.sub(r"[\s\-./]", "", str(s or "")).upper()


def _domain(email):
    email = (email or "").strip().lower()
    return email.split("@")[-1] if "@" in email else (email or "—")


# ======================================================================
def supplier_rating(mail_db, db_manager):
    """C2/C3: время ответа, доля отвеченных, письма с рисками — по домену отправителя."""
    known = {}
    try:
        for s in db_manager.get_suppliers():
            em = (s["email"] or "").strip().lower()
            if em:
                known[_domain(em)] = s["name"]
            known[(s["name"] or "").strip().lower()] = s["name"]
    except Exception:
        pass

    inc = mail_db.conn.execute("""SELECT id, thread_id, project_id, sender, sender_email,
                                         date_iso, risk_flag, risk_words, needs_reply, replied_at
                                  FROM messages WHERE direction='Входящее'""").fetchall()
    groups = {}
    for r in inc:
        dom = _domain(r["sender_email"])
        g = groups.setdefault(dom, {"name": known.get(dom, ""), "n": 0, "answered": 0,
                                    "hours": [], "risk": 0, "words": set(), "waiting": 0})
        g["n"] += 1
        if r["risk_flag"]:
            g["risk"] += 1
            for w in (r["risk_words"] or "").split(","):
                if w.strip():
                    g["words"].add(w.strip())
        reply = mail_db.conn.execute(
            """SELECT MIN(date_iso) d FROM messages
               WHERE thread_id=? AND project_id=? AND direction='Исходящее' AND date_iso>?""",
            (r["thread_id"], r["project_id"], r["date_iso"])).fetchone()
        d0, d1 = _dt(r["date_iso"]), _dt(reply["d"] if reply else "")
        if d0 and d1 and d1 >= d0:
            g["answered"] += 1
            g["hours"].append((d1 - d0).total_seconds() / 3600)
        elif r["needs_reply"] and not r["replied_at"]:
            g["waiting"] += 1

    rows = []
    for dom, g in groups.items():
        med = statistics.median(g["hours"]) if g["hours"] else None
        rows.append([
            g["name"] or dom, dom, g["n"], g["answered"],
            f"{g['answered'] / g['n'] * 100:.0f}%" if g["n"] else "—",
            f"{med / 24:.1f}" if med is not None else "—",
            f"{max(g['hours']) / 24:.1f}" if g["hours"] else "—",
            g["risk"], g["waiting"], ", ".join(sorted(g["words"]))[:60],
        ])
    rows.sort(key=lambda r: (-(r[7] or 0), -(float(r[5]) if r[5] != "—" else 0)))
    return rows


SUP_COLUMNS = [("Поставщик / домен", 190), ("Домен", 150), ("Писем", 60),
               ("Отвечено", 75), ("Доля", 60), ("Ответ, дн (мед.)", 110),
               ("Худший, дн", 90), ("⚠ риски", 70), ("Ждут ответа", 90),
               ("Слова риска", 160)]


# ======================================================================
def unlinked_invoices(mail_db, db_manager):
    """C4: инвойсы, найденные в письмах, но не привязанные к заказу."""
    known = set()
    try:
        for b in db_manager.get_order_batches():
            if b["invoice_number"]:
                known.add(_norm_inv(b["invoice_number"]))
        for r in db_manager.conn.execute(
                "SELECT invoice_number FROM purchase_payments WHERE invoice_number!=''"):
            known.add(_norm_inv(r["invoice_number"]))
    except Exception:
        pass

    rows = []
    q = """SELECT e.value inv, m.id, m.project_name, m.date_sent, m.sender, m.subject,
                  m.order_batch_id
           FROM extracted e JOIN messages m ON m.id=e.msg_id
           WHERE e.kind='invoice' ORDER BY m.date_iso DESC"""
    seen = set()
    for r in mail_db.conn.execute(q).fetchall():
        key = (r["project_name"], _norm_inv(r["inv"]))
        if key in seen:
            continue
        seen.add(key)
        if r["order_batch_id"]:
            continue
        state = "есть в заказах — привяжите" if _norm_inv(r["inv"]) in known else "НЕ ЗАВЕДЁН"
        rows.append([r["project_name"] or "", r["date_sent"] or "", r["inv"],
                     state, r["sender"] or "", (r["subject"] or "")[:70], r["id"]])
    rows.sort(key=lambda x: (x[3] != "НЕ ЗАВЕДЁН", x[1]), reverse=False)
    return rows


INV_COLUMNS = [("Проект", 130), ("Дата", 110), ("Инвойс", 140),
               ("Состояние", 190), ("От кого", 170), ("Тема", 300)]


# ======================================================================
def orders_without_mail(mail_db, db_manager, project_name=None, min_days=7):
    """C5: заказы, по которым нет ни одного привязанного письма."""
    today = datetime.now()
    rows = []
    for b in db_manager.get_order_batches():
        proj = b["project_name"] or ""
        if project_name and proj != project_name:
            continue
        pid = db_manager.get_project_id(proj)
        if not pid:
            continue
        n = mail_db.conn.execute(
            "SELECT COUNT(*) c FROM messages WHERE project_id=? AND order_batch_id=?",
            (pid, b["order_batch_id"])).fetchone()["c"]
        if n:
            continue
        inv = _norm_inv(b["invoice_number"])
        if inv:
            hit = mail_db.conn.execute(
                """SELECT COUNT(*) c FROM extracted e JOIN messages m ON m.id=e.msg_id
                   WHERE m.project_id=? AND e.kind='invoice'""", (pid,)).fetchone()
            if hit and hit["c"]:
                for r in mail_db.conn.execute(
                        """SELECT e.value v FROM extracted e JOIN messages m ON m.id=e.msg_id
                           WHERE m.project_id=? AND e.kind='invoice'""", (pid,)):
                    if _norm_inv(r["v"]) == inv:
                        n = 1
                        break
        if n:
            continue
        d0 = _dt(b["order_date"])
        age = (today - d0).days if d0 else 0
        if age < min_days:
            continue
        rows.append([proj, b["order_batch_id"], b["supplier"] or "",
                     b["invoice_number"] or "", b["order_date"] or "", age,
                     b["status"] if "status" in b.keys() else ""])
    rows.sort(key=lambda r: -r[5])
    return rows


NOMAIL_COLUMNS = [("Проект", 140), ("№ заказа", 80), ("Поставщик", 180),
                  ("Инвойс", 140), ("Дата заказа", 110), ("Дней без писем", 110)]


# ======================================================================
def price_candidates(mail_db, db_manager, project_name=None):
    """C7: цены из писем, которые можно записать в историю цен.

    Берём только однозначные случаи: в заказе ровно одна позиция
    и в письме ровно одна сумма — иначе требуется ручное сопоставление.
    """
    ok, manual = [], []
    q = """SELECT DISTINCT m.id, m.project_name, m.order_batch_id, m.date_sent, m.sender
           FROM messages m JOIN extracted e ON e.msg_id=m.id
           WHERE e.kind='amount' AND m.order_batch_id>0"""
    for r in mail_db.conn.execute(q).fetchall():
        if project_name and (r["project_name"] or "") != project_name:
            continue
        amounts = [x for x in mail_db.get_extracted(r["id"]) if x["kind"] == "amount"]
        try:
            items = db_manager.get_order_items(r["order_batch_id"])
        except Exception:
            items = []
        if len(amounts) == 1 and len(items) == 1:
            it = items[0]
            price = float(amounts[0]["value"])
            cur = amounts[0]["extra"] or it.get("currency") or ""
            ok.append({"project": r["project_name"], "batch": r["order_batch_id"],
                       "article": it.get("article") or "", "name": it.get("name") or "",
                       "manufacturer": it.get("manufacturer") or "",
                       "supplier": r["sender"] or "", "price": price, "currency": cur,
                       "qty": it.get("quantity") or 0, "date": r["date_sent"] or "",
                       "msg_id": r["id"]})
        else:
            manual.append([r["project_name"] or "", r["order_batch_id"],
                           len(amounts), len(items), r["date_sent"] or "",
                           (r["sender"] or "")[:40]])
    return ok, manual


PRICE_COLUMNS = [("Проект", 130), ("№ заказа", 75), ("Артикул", 160),
                 ("Наименование", 220), ("Цена", 100), ("Валюта", 65), ("Дата", 110)]


def commit_prices(db_manager, candidates):
    """Записывает однозначные цены в price_history с источником «Переписка»."""
    n = 0
    with db_manager.conn:
        for c in candidates:
            db_manager.conn.execute("""INSERT INTO price_history
                (article, name, manufacturer, supplier, price, currency, qty, date,
                 project_name, order_batch_id, source)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (c["article"], c["name"], c["manufacturer"], c["supplier"],
                 c["price"], c["currency"], c["qty"], c["date"],
                 c["project"], c["batch"], "Переписка"))
            n += 1
    return n


# ======================================================================
class MailAnalyticsDialog(tk.Toplevel):
    """Окно с четырьмя отчётами по переписке."""

    def __init__(self, parent, mail_db, db_manager, project_name=None):
        super().__init__(parent)
        self.db, self.pdb = mail_db, db_manager
        self.project = project_name
        self.title("Аналитика переписки" + (f" · {project_name}" if project_name else " · все проекты"))
        self.geometry("1180x640")
        self.transient(parent)

        top = ttk.Frame(self, padding=(8, 6))
        top.pack(fill="x")
        self.v_project = tk.BooleanVar(value=bool(project_name))
        ttk.Checkbutton(top, text="Только текущий проект", variable=self.v_project,
                        command=self.reload).pack(side=tk.LEFT)
        ttk.Button(top, text="Обновить", command=self.reload).pack(side=tk.LEFT, padx=8)
        self.lbl = ttk.Label(top, text="", foreground="#0066cc")
        self.lbl.pack(side=tk.LEFT, padx=12)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=6)
        self.t_sup = self._tab(nb, "  Надёжность поставщиков  ", SUP_COLUMNS)
        self.t_inv = self._tab(nb, "  Инвойсы без заказа  ", INV_COLUMNS)
        self.t_nom = self._tab(nb, "  Заказы без переписки  ", NOMAIL_COLUMNS)
        self.t_prc = self._tab(nb, "  Цены из писем  ", PRICE_COLUMNS)

        bf = ttk.Frame(self, padding=(8, 0, 8, 8))
        bf.pack(fill="x")
        ttk.Button(bf, text="Цены → в историю цен",
                   command=self.commit_prices).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Закрыть", command=self.destroy).pack(side=tk.RIGHT, padx=4)
        self.bind("<Escape>", lambda e: self.destroy())
        self._prices = []
        self.reload()
        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _tab(self, nb, title, columns):
        frame = ttk.Frame(nb, padding=6)
        nb.add(frame, text=title)
        cols = tuple(f"c{i}" for i in range(len(columns)))
        tv = ttk.Treeview(frame, columns=cols, show="headings", height=18)
        for i, (t, w) in enumerate(columns):
            tv.heading(cols[i], text=t)
            tv.column(cols[i], width=w, anchor="w" if i in (0, 1) else "center")
        vs = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tv.yview)
        hs = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=tv.xview)
        tv.configure(yscroll=vs.set, x
