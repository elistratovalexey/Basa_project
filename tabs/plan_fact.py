# -*- coding: utf-8 -*-
"""План-Факт v3: сроки, зависимости, baseline, блокировки, загрузка, аудит, уведомления."""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from datetime import datetime

from tabs.base import BaseTab

UNITS = ["Календарные дни", "Рабочие дни", "Недели"]
LINK_LABELS = {"FS": "FS · окончание→начало", "SS": "SS · начало→начало",
               "FF": "FF · окончание→окончание", "SF": "SF · начало→окончание",
               "NONE": "Нет зависимости"}


def _num(v, d=0.0):
    try:
        return float(str(v).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return d


class PlanFactTab(BaseTab):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        self._current_number = None
        self._row_num = {}
        self._parents = {}
        self.create_ui()

    # ==================================================================
    def create_ui(self):
        top = ttk.Frame(self.parent)
        top.pack(fill="x", pady=3)
        for text, cmd in (("Добавить", self.add_record), ("Сохранить", self.save_record),
                          ("Удалить", self.delete_record), ("Зависимости…", self.open_links),
                          ("Пересчитать", self.recalc), ("Из заказов", self.sync_orders),
                          ("Зафиксировать базу", self.set_baseline),
                          ("Загрузка", self.open_workload), ("Задержки", self.open_delays),
                          ("История", self.open_audit), ("Уведомления", self.open_notifications)):
            ttk.Button(top, text=text, command=cmd).pack(side=tk.LEFT, padx=2)

        top2 = ttk.Frame(self.parent)
        top2.pack(fill="x", pady=2)
        for text, cmd in (("База работ", self.open_work_types),
                          ("База статусов", self.open_work_statuses),
                          ("База ответственных", self.open_responsibles),
                          ("База причин", self.open_delay_reasons),
                          ("Ганта", self.open_gantt), ("Экспорт", self.export),
                          ("Очистить форму", self.clear_form)):
            ttk.Button(top2, text=text, command=cmd).pack(side=tk.LEFT, padx=2)
        self.lbl_notify = ttk.Label(top2, text="", foreground="#b02a37")
        self.lbl_notify.pack(side=tk.RIGHT, padx=8)

        self.lbl_summary = ttk.Label(self.parent, text="", font=("Arial", 9, "bold"),
                                     foreground="#0a58ca")
        self.lbl_summary.pack(fill="x", padx=8, pady=(2, 4))

        card = ttk.LabelFrame(self.parent, text="Карточка работы", padding=8)
        card.pack(fill="x", padx=6, pady=4)

        ttk.Label(card, text="№:").grid(row=0, column=0, sticky="w")
        self.e_num = ttk.Entry(card, width=6)
        self.e_num.grid(row=0, column=1, sticky="w", padx=(0, 8))
        ttk.Label(card, text="Наименование работ:").grid(row=0, column=2, sticky="w")
        self.e_name = ttk.Entry(card, width=48)
        self.e_name.grid(row=0, column=3, columnspan=5, sticky="ew", padx=(0, 8))
        ttk.Label(card, text="Подпроект:").grid(row=0, column=8, sticky="w")
        self.c_subproject = ttk.Combobox(card, width=20)
        self.c_subproject.grid(row=0, column=9, sticky="w")

        ttk.Label(card, text="Тип работ:").grid(row=1, column=0, sticky="w", pady=3)
        self.c_type = ttk.Combobox(card, width=20)
        self.c_type.grid(row=1, column=1, columnspan=2, sticky="w")
        ttk.Label(card, text="Ответственный:").grid(row=1, column=3, sticky="w")
        self.c_resp = ttk.Combobox(card, width=22)
        self.c_resp.grid(row=1, column=4, sticky="w")
        ttk.Label(card, text="Статус:").grid(row=1, column=5, sticky="w")
        self.c_status = ttk.Combobox(card, width=16)
        self.c_status.grid(row=1, column=6, sticky="w")
        self.v_milestone = tk.BooleanVar(value=False)
        ttk.Checkbutton(card, text="Веха", variable=self.v_milestone).grid(row=1, column=7, sticky="w")
        ttk.Label(card, text="%:").grid(row=1, column=8, sticky="w")
        self.e_progress = ttk.Entry(card, width=6)
        self.e_progress.grid(row=1, column=9, sticky="w")
        self.e_progress.insert(0, "0")

        ttk.Label(card, text="Начало план:").grid(row=2, column=0, sticky="w", pady=3)
        self.e_start_plan = ttk.Entry(card, width=12)
        self.e_start_plan.grid(row=2, column=1, sticky="w")
        ttk.Button(card, text="📅", width=2, command=lambda: self._pick(self.e_start_plan)).grid(row=2, column=2, sticky="w")
        ttk.Label(card, text="Начало факт:").grid(row=2, column=3, sticky="w")
        self.e_start_fact = ttk.Entry(card, width=12)
        self.e_start_fact.grid(row=2, column=4, sticky="w")
        ttk.Button(card, text="📅", width=2, command=lambda: self._pick(self.e_start_fact)).grid(row=2, column=5, sticky="w")
        ttk.Label(card, text="Выполнение:").grid(row=2, column=6, sticky="w")
        self.e_dur = ttk.Entry(card, width=7)
        self.e_dur.grid(row=2, column=7, sticky="w")
        self.c_unit = ttk.Combobox(card, values=UNITS, width=16, state="readonly")
        self.c_unit.set(UNITS[0])
        self.c_unit.grid(row=2, column=8, sticky="w")
        ttk.Label(card, text="Окончание план:").grid(row=2, column=9, sticky="w")
        self.lbl_end_plan = ttk.Label(card, text="—", foreground="#0a58ca", font=("Arial", 9, "bold"))
        self.lbl_end_plan.grid(row=2, column=10, sticky="w")

        ttk.Label(card, text="Окончание факт:").grid(row=3, column=0, sticky="w", pady=3)
        self.e_end_fact = ttk.Entry(card, width=12)
        self.e_end_fact.grid(row=3, column=1, sticky="w")
        ttk.Button(card, text="📅", width=2, command=lambda: self._pick(self.e_end_fact)).grid(row=3, column=2, sticky="w")
        ttk.Label(card, text="Входит в работу:").grid(row=3, column=3, sticky="w")
        self.c_parent = ttk.Combobox(card, width=28, state="readonly")
        self.c_parent.grid(row=3, column=4, columnspan=2, sticky="w")
        ttk.Label(card, text="Стоимость (вес) ₽:").grid(row=3, column=6, sticky="w")
        self.e_cost = ttk.Entry(card, width=12)
        self.e_cost.grid(row=3, column=7, sticky="w")
        ttk.Label(card, text="Прогноз / Δ / база:").grid(row=3, column=8, sticky="w")
        self.lbl_forecast = ttk.Label(card, text="—", foreground="gray")
        self.lbl_forecast.grid(row=3, column=9, columnspan=2, sticky="w")

        self.v_blocked = tk.BooleanVar(value=False)
        ttk.Checkbutton(card, text="🔒 Заблокирована", variable=self.v_blocked).grid(row=4, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Label(card, text="Причина:").grid(row=4, column=2, sticky="w")
        self.c_reason = ttk.Combobox(card, width=24)
        self.c_reason.grid(row=4, column=3, columnspan=2, sticky="w")
        ttk.Label(card, text="Связать с заказом:").grid(row=4, column=5, sticky="w")
        self.c_order = ttk.Combobox(card, width=18, state="readonly")
        self.c_order.grid(row=4, column=6, columnspan=2, sticky="w")
        self.v_auto = tk.BooleanVar(value=False)
        ttk.Checkbutton(card, text="Даты из заказа", variable=self.v_auto).grid(row=4, column=8, sticky="w")
        ttk.Label(card, text="Уведомлять за, дн:").grid(row=4, column=9, sticky="w")
        self.e_notify = ttk.Entry(card, width=5)
        self.e_notify.grid(row=4, column=10, sticky="w")
        self.e_notify.insert(0, "3")

        ttk.Label(card, text="Комментарии:").grid(row=5, column=0, sticky="nw", pady=3)
        self.e_comment = tk.Text(card, width=100, height=2)
        self.e_comment.grid(row=5, column=1, columnspan=10, sticky="ew", pady=3)
        card.grid_columnconfigure(3, weight=1)

        for w in (self.e_start_plan, self.e_dur):
            w.bind("<KeyRelease>", lambda e: self._recalc_label())
        self.c_unit.bind("<<ComboboxSelected>>", lambda e: self._recalc_label())

        flt = ttk.Frame(self.parent)
        flt.pack(fill="x", padx=6, pady=2)
        self.v_overdue = tk.BooleanVar(value=False)
        self.v_inwork = tk.BooleanVar(value=False)
        self.v_blocked_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(flt, text="Просроченные", variable=self.v_overdue, command=self.load_records).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(flt, text="В работе", variable=self.v_inwork, command=self.load_records).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(flt, text="Заблокированные", variable=self.v_blocked_only, command=self.load_records).pack(side=tk.LEFT, padx=5)
        ttk.Label(flt, text="Ответственный:").pack(side=tk.LEFT, padx=(10, 3))
        self.c_f_resp = ttk.Combobox(flt, width=18, state="readonly")
        self.c_f_resp.pack(side=tk.LEFT)
        self.c_f_resp.bind("<<ComboboxSelected>>", lambda e: self.load_records())
        ttk.Label(flt, text="Подпроект:").pack(side=tk.LEFT, padx=(10, 3))
        self.c_f_sub = ttk.Combobox(flt, width=18, state="readonly")
        self.c_f_sub.pack(side=tk.LEFT)
        self.c_f_sub.bind("<<ComboboxSelected>>", lambda e: self.load_records())
        ttk.Button(flt, text="Сброс", command=self.reset_filters).pack(side=tk.LEFT, padx=6)

        tf = ttk.LabelFrame(self.parent, text="Работы по проекту (дерево подчинённости)", padding=6)
        tf.pack(fill="both", expand=True, padx=6, pady=4)
        cols = ("num", "name", "sub", "type", "resp", "status", "sp", "sf", "dur",
                "ep", "ef", "delta", "prog", "forecast", "slack", "depends", "base", "lock", "cost")
        self.tree = ttk.Treeview(tf, columns=cols, show="tree headings", height=13)
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=28, stretch=False)
        heads = [("num", "№", 42), ("name", "Наименование работ", 250), ("sub", "Подпроект", 110),
                 ("type", "Тип", 100), ("resp", "Ответственный", 120), ("status", "Статус", 100),
                 ("sp", "Начало план", 88), ("sf", "Начало факт", 88), ("dur", "Выполнение", 105),
                 ("ep", "Окончание план", 95), ("ef", "Окончание факт", 95), ("delta", "Δ дней", 60),
                 ("prog", "%", 45), ("forecast", "Прогноз", 88), ("slack", "Резерв", 60),
                 ("depends", "Зависит от", 120), ("base", "Сдвиг базы", 80),
                 ("lock", "🔒", 40), ("cost", "Стоимость ₽", 100)]
        for c, t, w in heads:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w" if c in ("name", "sub", "type", "resp", "depends") else "center")
        vs = ttk.Scrollbar(tf, orient=tk.VERTICAL, command=self.tree.yview)
        hs = ttk.Scrollbar(tf, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscroll=vs.set, xscroll=hs.set)
        self.tree.pack(side=tk.LEFT, fill="both", expand=True)
        vs.pack(side=tk.RIGHT, fill="y")
        hs.pack(side=tk.BOTTOM, fill="x")
        for tag, kw in (("overdue", {"background": "#f8d7da"}), ("soon", {"background": "#fff3cd"}),
                        ("done", {"background": "#d9ead3"}), ("blocked", {"background": "#e2e3e5"}),
                        ("critical", {"foreground": "#8b0000"}), ("latestart", {"foreground": "#b02a37"})):
            self.tree.tag_configure(tag, **kw)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", lambda e: self.open_links())

    # ==================================================================
    def _pick(self, entry):
        try:
            from dialogs.calendar_dialog import CalendarDialog
        except ImportError:
            entry.delete(0, tk.END); entry.insert(0, datetime.now().strftime("%d.%m.%Y"))
            self._recalc_label(); return
        dlg = CalendarDialog(self.root, entry.get() or None)
        self.root.wait_window(dlg)
        if getattr(dlg, "result", None):
            entry.delete(0, tk.END); entry.insert(0, dlg.result)
            self._recalc_label()

    def _recalc_label(self):
        end = self.db_manager.pf_end_plan(self.e_start_plan.get(), _num(self.e_dur.get()), self.c_unit.get())
        self.lbl_end_plan.config(text=end or "—")

    def _refresh_dicts(self):
        proj = self.app.current_project or ""
        pid = self.db_manager.get_project_id(proj)
        self.c_type["values"] = self.db_manager.get_work_types()
        self.c_status["values"] = self.db_manager.get_work_statuses()
        resp = [r["name"] for r in self.db_manager.get_responsibles()]
        self.c_resp["values"] = resp
        self.c_reason["values"] = self.db_manager.get_delay_reasons()
        try:
            self.c_subproject["values"] = [""] + [r["name"] for r in self.db_manager.get_subprojects(proj)]
        except Exception:
            pass
        rows = self.db_manager.get_plan_fact(pid) if pid else []
        self._parents = {"— нет —": 0}
        for r in rows:
            self._parents[f'№{r["number"]} · {r["name"] or ""}'] = r["id"]
        self.c_parent["values"] = list(self._parents.keys())
        if not self.c_parent.get():
            self.c_parent.set("— нет —")
        self._orders = {"— нет —": 0}
        try:
            for b in self.db_manager.get_order_batches():
                if (b["project_name"] or "") == proj:
                    lbl = f'№{b["order_batch_id"]} · {b["supplier"] or ""} {b["order_date"] or ""}'.strip()
                    self._orders[lbl] = b["order_batch_id"]
        except Exception:
            pass
        self.c_order["values"] = list(self._orders.keys())
        if not self.c_order.get():
            self.c_order.set("— нет —")
        self.c_f_resp["values"] = [""] + resp
        self.c_f_sub["values"] = [""] + sorted({(r["subproject"] or "") for r in rows if r["subproject"]})

    def reset_filters(self):
        self.v_overdue.set(False); self.v_inwork.set(False); self.v_blocked_only.set(False)
        self.c_f_resp.set(""); self.c_f_sub.set("")
        self.load_records()

    # ==================================================================
    def load_records(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        self._row_num = {}
        self._refresh_dicts()
        proj = self.app.current_project
        if not proj:
            self.lbl_summary.config(text="Выберите проект")
            return
        pid = self.db_manager.get_project_id(proj)
        if not pid:
            return
        rows = [dict(r) for r in self.db_manager.get_plan_fact(pid)]
        m = self.db_manager.pf_metrics(pid)
        met, s = m["rows"], m["summary"]
        self.lbl_summary.config(
            text=(f"Работ {s['total']} · выполнено {s['done']} · в работе {s['in_work']} · "
                  f"просрочено {s['overdue']} · старт просрочен {s['late_start']} · "
                  f"🔒 {s['blocked']} · критических {s['critical']} · "
                  f"выполнение: {s['progress']}% по дням / {s['progress_cost']}% по деньгам · "
                  f"сдвиг от базы до {s['base_shift']} дн"))
        try:
            notes = self.db_manager.pf_notifications(pid)
            bad = sum(1 for n in notes if n["kind"] in ("overdue", "late_start", "blocked"))
            self.lbl_notify.config(text=f"🔔 событий: {len(notes)} (критичных {bad})" if notes else "")
        except Exception:
            pass

        f_resp, f_sub = self.c_f_resp.get(), self.c_f_sub.get()
        by_id = {r["id"]: r for r in rows}
        iids = {}

        def visible(r):
            mm = met.get(r["id"], {})
            if self.v_overdue.get() and mm.get("light") != "overdue":
                return False
            if self.v_inwork.get() and not (r.get("start_fact") and
                                            (r.get("status") or "") not in ("Выполнено", "Завершено")):
                return False
            if self.v_blocked_only.get() and not r.get("is_blocked"):
                return False
            if f_resp and (r.get("responsible") or "") != f_resp:
                return False
            if f_sub and (r.get("subproject") or "") != f_sub:
                return False
            return True

        def insert(r, parent_iid=""):
            mm = met.get(r["id"], {})
            dur = f'{_num(r.get("duration_qty")):g} {r.get("duration_unit") or ""}'.strip()
            tags = []
            if mm.get("light") in ("overdue", "soon", "done", "blocked"):
                tags.append(mm["light"])
            if mm.get("critical"):
                tags.append("critical")
            if mm.get("late_start"):
                tags.append("latestart")
            iid = self.tree.insert(parent_iid, tk.END, text="", tags=tuple(tags), values=(
                r["number"], r.get("name") or "", r.get("subproject") or "", r.get("work_type") or "",
                r.get("responsible") or "", r.get("status") or "", r.get("start_plan") or "",
                r.get("start_fact") or "", dur, r.get("end_plan") or "", r.get("end_fact") or "",
                mm.get("delta") if mm.get("delta") is not None else "", f'{mm.get("progress", 0)}%',
                mm.get("forecast") or "", mm.get("slack") if mm.get("slack") is not None else "",
                mm.get("depends") or "—",
                mm.get("base_shift") if mm.get("base_shift") is not None else "",
                "🔒" if r.get("is_blocked") else "",
                f'{_num(r.get("cost_weight")):,.0f}'.replace(",", " ") if _num(r.get("cost_weight")) else ""))
            iids[r["id"]] = iid
            self._row_num[iid] = r["number"]

        pending = [r for r in rows if visible(r)]
        inserted = set()
        for _ in range(6):
            rest = []
            for r in pending:
                par = int(r.get("parent_id") or 0)
                if par and par in by_id and par not in inserted:
                    rest.append(r); continue
                insert(r, iids.get(par, ""))
                inserted.add(r["id"])
            pending = rest
            if not pending:
                break
        for r in pending:
            insert(r, "")
        for iid in iids.values():
            self.tree.item(iid, open=True)

    # ==================================================================
    def on_select(self, event=None):
        sel = self.tree.selection()
        if not sel or sel[0] not in self._row_num:
            return
        num = self._row_num[sel[0]]
        pid = self.db_manager.get_project_id(self.app.current_project)
        row = next((dict(r) for r in self.db_manager.get_plan_fact(pid) if r["number"] == num), None)
        if not row:
            return
        self._current_number = num
        self.e_num.delete(0, tk.END); self.e_num.insert(0, str(num))
        self.e_name.delete(0, tk.END); self.e_name.insert(0, row.get("name") or "")
        self.c_subproject.set(row.get("subproject") or "")
        self.c_type.set(row.get("work_type") or "")
        self.c_resp.set(row.get("responsible") or "")
        self.c_status.set(row.get("status") or "")
        self.c_reason.set(row.get("delay_reason") or "")
        self.v_milestone.set(bool(row.get("is_milestone")))
        self.v_blocked.set(bool(row.get("is_blocked")))
        self.v_auto.set(bool(row.get("auto_dates")))
        for e, k in ((self.e_start_plan, "start_plan"), (self.e_start_fact, "start_fact"),
                     (self.e_end_fact, "end_fact")):
            e.delete(0, tk.END); e.insert(0, row.get(k) or "")
        self.e_dur.delete(0, tk.END); self.e_dur.insert(0, f'{_num(row.get("duration_qty")):g}')
        self.c_unit.set(row.get("duration_unit") or UNITS[0])
        self.e_progress.delete(0, tk.END); self.e_progress.insert(0, str(row.get("progress") or 0))
        self.e_cost.delete(0, tk.END)
        if _num(row.get("cost_weight")):
            self.e_cost.insert(0, f'{_num(row.get("cost_weight")):.2f}')
        self.e_notify.delete(0, tk.END); self.e_notify.insert(0, str(row.get("notify_days") or 3))
        self.e_comment.delete("1.0", tk.END); self.e_comment.insert("1.0", row.get("comment") or "")
        par = int(row.get("parent_id") or 0)
        self.c_parent.set(next((k for k, v in self._parents.items() if v == par), "— нет —"))
        ob = int(row.get("link_order_batch") or 0)
        self.c_order.set(next((k for k, v in self._orders.items() if v == ob), "— нет —"))
        self._recalc_label()
        mm = self.db_manager.pf_metrics(pid)["rows"].get(row["id"], {})
        self.lbl_forecast.config(
            text=f'{mm.get("forecast") or "—"} / Δ {mm.get("delta") if mm.get("delta") is not None else "—"}'
                 f' / база {mm.get("base_shift") if mm.get("base_shift") is not None else "—"}')

    def clear_form(self):
        self._current_number = None
        for e in (self.e_num, self.e_name, self.e_start_plan, self.e_start_fact,
                  self.e_end_fact, self.e_dur, self.e_cost):
            e.delete(0, tk.END)
        self.e_progress.delete(0, tk.END); self.e_progress.insert(0, "0")
        self.e_notify.delete(0, tk.END); self.e_notify.insert(0, "3")
        self.e_comment.delete("1.0", tk.END)
        for c in (self.c_subproject, self.c_type, self.c_resp, self.c_status, self.c_reason):
            c.set("")
        self.c_unit.set(UNITS[0]); self.c_parent.set("— нет —"); self.c_order.set("— нет —")
        self.v_milestone.set(False); self.v_blocked.set(False); self.v_auto.set(False)
        self.lbl_end_plan.config(text="—"); self.lbl_forecast.config(text="—")

    def _collect(self):
        comment = self.e_comment.get("1.0", tk.END).strip()
        return {
            "name": self.e_name.get().strip(),
            "subproject": self.c_subproject.get().strip(),
            "work_type": self.c_type.get().strip(),
            "responsible": self.c_resp.get().strip(),
            "status": self.c_status.get().strip(),
            "start_plan": self.e_start_plan.get().strip(),
            "start_fact": self.e_start_fact.get().strip(),
            "duration_qty": _num(self.e_dur.get()),
            "duration_unit": self.c_unit.get() or UNITS[0],
            "end_plan": self.db_manager.pf_end_plan(self.e_start_plan.get(),
                                                    _num(self.e_dur.get()), self.c_unit.get()),
            "end_fact": self.e_end_fact.get().strip(),
            "progress": int(_num(self.e_progress.get())),
            "is_milestone": 1 if self.v_milestone.get() else 0,
            "parent_id": self._parents.get(self.c_parent.get(), 0),
            "is_blocked": 1 if self.v_blocked.get() else 0,
            "delay_reason": self.c_reason.get().strip(),
            "blocked_note": comment,
            "link_order_batch": self._orders.get(self.c_order.get(), 0),
            "auto_dates": 1 if self.v_auto.get() else 0,
            "cost_weight": _num(self.e_cost.get()),
            "notify_days": int(_num(self.e_notify.get(), 3)),
            "comment": comment, "note": comment,
        }

    def add_record(self):
        if not self.app.current_project:
            messagebox.showwarning("Внимание", "Выберите проект!"); return
        self.clear_form()
        pid = self.db_manager.get_project_id(self.app.current_project)
        self.e_num.insert(0, str(self.db_manager.get_next_number("plan_fact", pid)))
        self.e_start_plan.insert(0, datetime.now().strftime("%d.%m.%Y"))
        self._recalc_label()
        self.e_name.focus_set()

    def save_record(self):
        if not self.app.current_project:
            messagebox.showwarning("Внимание", "Выберите проект!"); return
        data = self._collect()
        if not data["name"]:
            messagebox.showwarning("Внимание", "Укажите наименование работ!"); return
        if data["is_blocked"] and not data["delay_reason"]:
            messagebox.showwarning("Внимание", "Для заблокированной работы укажите причину задержки!"); return
        pid = self.db_manager.get_project_id(self.app.current_project)
        num = int(_num(self.e_num.get(), 0)) or self.db_manager.get_next_number("plan_fact", pid)
        exists = any(r["number"] == num for r in self.db_manager.get_plan_fact(pid))
        if exists:
            self.db_manager.update_plan_fact(pid, num, data)
            action = "обновлена"
        else:
            data["number"] = num
            self.db_manager.add_plan_fact(pid, data)
            action = "добавлена"
        self.db_manager.pf_recalc_schedule(pid)
        self._current_number = num
        self.app.log_action(f"План-Факт: работа №{num} {action} ({data['name']})")
        self.load_records()

    def delete_record(self):
        num = self._current_number
        if num is None:
            messagebox.showwarning("Внимание", "Выберите работу!"); return
        if not messagebox.askyesno("Подтверждение", f"Удалить работу №{num}?"):
            return
        pid = self.db_manager.get_project_id(self.app.current_project)
        row = next((r for r in self.db_manager.get_plan_fact(pid) if r["number"] == num), None)
        if row:
            for l in self.db_manager.get_pf_links(pid):
                if l["work_id"] == row["id"] or l["depends_on"] == row["id"]:
                    self.db_manager.delete_pf_link(l["id"])
            self.db_manager.conn.execute("UPDATE plan_fact SET parent_id=0 WHERE parent_id=?", (row["id"],))
            self.db_manager.conn.commit()
        self.db_manager.delete_plan_fact(pid, num)
        self.app.log_action(f"План-Факт: работа №{num} удалена")
        self.clear_form()
        self.load_records()

    def recalc(self):
        pid = self.db_manager.get_project_id(self.app.current_project or "")
        if not pid:
            return
        n = self.db_manager.pf_recalc_schedule(pid)
        self.load_records()
        messagebox.showinfo("Пересчёт", f"Обновлено дат по зависимостям: {n}")

    def sync_orders(self):
        pid = self.db_manager.get_project_id(self.app.current_project or "")
        if not pid:
            return
        n = self.db_manager.pf_sync_from_orders(pid)
        c = self.db_manager.pf_cost_from_orders(pid)
        self.db_manager.pf_recalc_schedule(pid)
        self.load_records()
        messagebox.showinfo("Из заказов", f"Обновлено дат: {n}\nПодтянуто сумм: {c}")

    def set_baseline(self):
        pid = self.db_manager.get_project_id(self.app.current_project or "")
        if not pid:
            return
        ans = messagebox.askyesnocancel(
            "Базовый план",
            "Зафиксировать текущие даты как базовый план?\n\n"
            "«Да» — только для работ без базы\n"
            "«Нет» — перезаписать базу у ВСЕХ работ\n"
            "«Отмена» — ничего не делать")
        if ans is None:
            return
        n = self.db_manager.pf_set_baseline(pid, only_empty=bool(ans))
        self.load_records()
        messagebox.showinfo("Базовый план", f"Зафиксировано работ: {n}")

    # ==================================================================
    def _pid_row(self):
        if self._current_number is None:
            return None, None
        pid = self.db_manager.get_project_id(self.app.current_project)
        row = next((dict(r) for r in self.db_manager.get_plan_fact(pid)
                    if r["number"] == self._current_number), None)
        return pid, row

    def open_links(self):
        pid, row = self._pid_row()
        if not row:
            messagebox.showwarning("Внимание", "Выберите работу!"); return
        WorkLinksDialog(self.root, self.db_manager, pid, row)
        self.db_manager.pf_recalc_schedule(pid)
        self.load_records()

    def open_responsibles(self):
        ResponsiblesDialog(self.root, self.db_manager)
        self._refresh_dicts()

    def open_work_types(self):
        DirectoryDialog(self.root, "Типы работ", self.db_manager.get_work_types,
                        self.db_manager.add_work_type, self.db_manager.rename_work_type,
                        self.db_manager.delete_work_type)
        self._refresh_dicts()

    def open_work_statuses(self):
        DirectoryDialog(self.root, "Статусы работ", self.db_manager.get_work_statuses,
                        self.db_manager.add_work_status, self.db_manager.rename_work_status,
                        self.db_manager.delete_work_status)
        self._refresh_dicts()

    def open_delay_reasons(self):
        DirectoryDialog(self.root, "Причины задержек", self.db_manager.get_delay_reasons,
                        self.db_manager.add_delay_reason, self.db_manager.rename_delay_reason,
                        self.db_manager.delete_delay_reason)
        self._refresh_dicts()

    def _need_pid(self):
        pid = self.db_manager.get_project_id(self.app.current_project or "")
        if not pid:
            messagebox.showwarning("Внимание", "Выберите проект!")
        return pid

    def open_workload(self):
        pid = self._need_pid()
        if pid:
            TableReportDialog(self.root, "Загрузка ответственных",
                              [("Ответственный", 180), ("Работ", 60), ("Дней", 70),
                               ("Просроч.", 70), ("🔒", 50), ("Пик парал.", 80), ("Статус", 110)],
                              [[w["name"], w["works"], w["days"], w["overdue"], w["blocked"],
                                w["peak"], "ПЕРЕГРУЗ" if w["overload"] else "норма"]
                               for w in self.db_manager.pf_workload(pid)],
                              highlight=lambda row: row[6] == "ПЕРЕГРУЗ")

    def open_delays(self):
        pid = self._need_pid()
        if pid:
            TableReportDialog(self.root, "Аналитика задержек",
                              [("Причина", 200), ("Работ", 70), ("Дней просрочки", 110),
                               ("🔒", 60), ("№ работ", 220)],
                              [[d["reason"], d["count"], d["days"], d["blocked"], d["numbers"]]
                               for d in self.db_manager.pf_delay_analytics(pid)])

    def open_audit(self):
        pid = self._need_pid()
        if not pid:
            return
        _, row = self._pid_row()
        rows = self.db_manager.pf_audit(pid, row["id"] if row else None)
        TableReportDialog(self.root, "История изменений" + (f' · №{row["number"]}' if row else " · все работы"),
                          [("Когда", 130), ("№", 50), ("Поле", 120),
                           ("Было", 130), ("Стало", 130), ("Кто", 110)],
                          [[r["ts"], r["number"], r["field"], r["old_value"],
                            r["new_value"], r["author"] or r["device"]] for r in rows])

    def open_notifications(self):
        pid = self._need_pid()
        if not pid:
            return
        notes = self.db_manager.pf_notifications(pid)
        TableReportDialog(self.root, "Уведомления по работам",
                          [("№", 50), ("Работа", 230), ("Ответственный", 140), ("Событие", 300)],
                          [[n["number"], n["name"], n["responsible"], n["text"]] for n in notes],
                          highlight=lambda row: "ПРОСРОЧКА" in str(row[3]) or "🔒" in str(row[3]))

    def open_gantt(self):
        pid = self._need_pid()
        if pid:
            GanttDialog(self.root, self.db_manager, pid, self.app.current_project)

    def export(self):
        try:
            import openpyxl
            from openpyxl.styles import Font
        except ImportError:
            messagebox.showerror("Нет библиотеки", "pip install openpyxl"); return
        pid = self._need_pid()
        if not pid:
            return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx",
                                            initialfile=f"План-Факт_{self.app.current_project}.xlsx")
        if not path:
            return
        met = self.db_manager.pf_metrics(pid)["rows"]
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "План-Факт"
        heads = ["№", "Наименование", "Подпроект", "Тип", "Ответственный", "Статус",
                 "Начало план", "Начало факт", "Выполнение", "Окончание план", "Окончание факт",
                 "Δ дней", "%", "Прогноз", "Резерв", "Зависит от", "Сдвиг базы",
                 "Заблокирована", "Причина", "Стоимость ₽", "Комментарии"]
        ws.append([self.app.current_project])
        ws.append(heads)
        for c in ws[2]:
            c.font = Font(bold=True)
        for r in self.db_manager.get_plan_fact(pid):
            mm = met.get(r["id"], {})
            ws.append([r["number"], r["name"], r["subproject"], r["work_type"], r["responsible"],
                       r["status"], r["start_plan"], r["start_fact"],
                       f'{_num(r["duration_qty"]):g} {r["duration_unit"] or ""}',
                       r["end_plan"], r["end_fact"], mm.get("delta"), mm.get("progress"),
                       mm.get("forecast"), mm.get("slack"), mm.get("depends"), mm.get("base_shift"),
                       "да" if r["is_blocked"] else "", r["delay_reason"],
                       round(_num(r["cost_weight"]), 2), r["comment"]])
        ws2 = wb.create_sheet("Загрузка")
        ws2.append(["Ответственный", "Работ", "Дней", "Просрочено", "Блокировано", "Пик", "Перегруз"])
        for w in self.db_manager.pf_workload(pid):
            ws2.append([w["name"], w["works"], w["days"], w["overdue"], w["blocked"],
                        w["peak"], "да" if w["overload"] else ""])
        ws3 = wb.create_sheet("Задержки")
        ws3.append(["Причина", "Работ", "Дней просрочки", "Блокировано", "№"])
        for d in self.db_manager.pf_delay_analytics(pid):
            ws3.append([d["reason"], d["count"], d["days"], d["blocked"], d["numbers"]])
        ws4 = wb.create_sheet("История")
        ws4.append(["Когда", "№", "Поле", "Было", "Стало", "Кто"])
        for a in self.db_manager.pf_audit(pid, limit=2000):
            ws4.append([a["ts"], a["number"], a["field"], a["old_value"], a["new_value"], a["author"]])
        ws.freeze_panes = "C3"
        try:
            wb.save(path)
            messagebox.showinfo("Успех", f"Сохранено (4 листа):\n{path}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))


# ======================================================================
class TableReportDialog(tk.Toplevel):
    """Универсальное окно отчёта."""
    def __init__(self, parent, title, columns, rows, highlight=None):
        super().__init__(parent)
        self.title(title)
        self.geometry("980x520")
        self.transient(parent)
        cols = tuple(f"c{i}" for i in range(len(columns)))
        tv = ttk.Treeview(self, columns=cols, show="headings", height=18)
        for i, (t, w) in enumerate(columns):
            tv.heading(cols[i], text=t)
            tv.column(cols[i], width=w, anchor="w" if i in (0, 1) else "center")
        vs = ttk.Scrollbar(self, orient=tk.VERTICAL, command=tv.yview)
        hs = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=tv.xview)
        tv.configure(yscroll=vs.set, xscroll=hs.set)
        tv.pack(side=tk.LEFT, fill="both", expand=True, padx=(8, 0), pady=8)
        vs.pack(side=tk.RIGHT, fill="y")
        hs.pack(side=tk.BOTTOM, fill="x")
        tv.tag_configure("bad", background="#f8d7da")
        for row in rows:
            tags = ("bad",) if highlight and highlight(row) else ()
            tv.insert("", tk.END, values=row, tags=tags)
        if not rows:
            tv.insert("", tk.END, values=["— нет данных —"] + [""] * (len(columns) - 1))
        ttk.Button(self, text="Закрыть", command=self.destroy).pack(side=tk.BOTTOM, pady=4)
        self.bind("<Escape>", lambda e: self.destroy())
        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            pass


class ResponsiblesDialog(tk.Toplevel):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.title("База ответственных")
        self.geometry("720x460")
        self.transient(parent)
        self.tree = ttk.Treeview(self, columns=("name", "pos", "email", "phone"),
                                 show="headings", height=12)
        for c, t, w in (("name", "ФИО", 200), ("pos", "Должность", 160),
                        ("email", "E-mail", 160), ("phone", "Телефон", 120)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)
        f = ttk.Frame(self)
        f.pack(fill="x", padx=8)
        self.e = {}
        for i, (k, t) in enumerate((("name", "ФИО"), ("pos", "Должность"),
                                    ("email", "E-mail"), ("phone", "Телефон"))):
            ttk.Label(f, text=t + ":").grid(row=i, column=0, sticky="w", pady=2)
            self.e[k] = ttk.Entry(f, width=40)
            self.e[k].grid(row=i, column=1, sticky="w", pady=2)
        bf = ttk.Frame(self)
        bf.pack(pady=8)
        for t, c in (("Добавить", self.add), ("Сохранить изменения", self.save),
                     ("Удалить", self.delete), ("Закрыть", self.destroy)):
            ttk.Button(bf, text=t, command=c).pack(side=tk.LEFT, padx=4)
        self.tree.bind("<<TreeviewSelect>>", self.pick)
        self.reload()
        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def reload(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for r in self.db.get_responsibles():
            self.tree.insert("", tk.END, iid=str(r["id"]),
                             values=(r["name"], r["position"], r["email"], r["phone"]))

    def pick(self, e=None):
        s = self.tree.selection()
        if not s:
            return
        for k, val in zip(("name", "pos", "email", "phone"), self.tree.item(s[0])["values"]):
            self.e[k].delete(0, tk.END)
            self.e[k].insert(0, val or "")

    def add(self):
        if self.db.add_responsible(self.e["name"].get(), self.e["pos"].get(),
                                   self.e["email"].get(), self.e["phone"].get()):
            self.reload()
        else:
            messagebox.showwarning("Внимание", "Пустое или уже существующее ФИО", parent=self)

    def save(self):
        s = self.tree.selection()
        if s and self.db.update_responsible(int(s[0]), self.e["name"].get(), self.e["pos"].get(),
                                            self.e["email"].get(), self.e["phone"].get()):
            self.reload()

    def delete(self):
        s = self.tree.selection()
        if s and messagebox.askyesno("Подтверждение", "Удалить ответственного?", parent=self):
            self.db.delete_responsible(int(s[0]))
            self.reload()


class WorkLinksDialog(tk.Toplevel):
    def __init__(self, parent, db, pid, row):
        super().__init__(parent)
        self.db, self.pid, self.row = db, pid, row
        self.title(f'Зависимости · №{row["number"]} {row.get("name") or ""}')
        self.geometry("760x420")
        self.transient(parent)
        self.rows = {r["id"]: dict(r) for r in db.get_plan_fact(pid)}
        ttk.Label(self, text="Эта работа зависит по срокам от:",
                  font=("Arial", 9, "bold")).pack(anchor="w", padx=10, pady=(10, 4))
        self.tree = ttk.Treeview(self, columns=("dep", "type", "lag"), show="headings", height=8)
        for c, t, w in (("dep", "Зависит от работы", 380), ("type", "Тип связи", 220), ("lag", "Лаг, дней", 90)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True, padx=10)
        f = ttk.Frame(self)
        f.pack(fill="x", padx=10, pady=8)
        ttk.Label(f, text="Работа:").grid(row=0, column=0, sticky="w")
        self.c_dep = ttk.Combobox(f, width=44, state="readonly")
        self.c_dep.grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(f, text="Тип:").grid(row=0, column=2, sticky="w")
        self.c_type = ttk.Combobox(f, width=24, state="readonly",
                                   values=[LINK_LABELS[k] for k in ("FS", "SS", "FF", "SF", "NONE")])
        self.c_type.set(LINK_LABELS["FS"])
        self.c_type.grid(row=0, column=3, sticky="w", padx=4)
        ttk.Label(f, text="Лаг:").grid(row=1, column=0, sticky="w", pady=4)
        self.e_lag = ttk.Entry(f, width=6)
        self.e_lag.grid(row=1, column=1, sticky="w", padx=4)
        self.e_lag.insert(0, "0")
        bf = ttk.Frame(self)
        bf.pack(pady=6)
        for t, c in (("Добавить связь", self.add), ("Удалить связь", self.remove), ("Закрыть", self.destroy)):
            ttk.Button(bf, text=t, command=c).pack(side=tk.LEFT, padx=4)
        self._map = {f'№{r["number"]} · {r.get("name") or ""}': wid
                     for wid, r in self.rows.items() if wid != row["id"]}
        self.c_dep["values"] = list(self._map.keys())
        self.reload()
        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def reload(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for l in self.db.get_pf_links(self.pid, self.row["id"]):
            p = self.rows.get(l["depends_on"])
            label = f'№{p["number"]} · {p.get("name") or ""}' if p else f'id {l["depends_on"]}'
            self.tree.insert("", tk.END, iid=str(l["id"]),
                             values=(label, LINK_LABELS.get(l["link_type"], l["link_type"]), l["lag_days"]))

    def add(self):
        wid = self._map.get(self.c_dep.get())
        if not wid:
            messagebox.showwarning("Внимание", "Выберите работу", parent=self); return
        t = next((k for k, v in LINK_LABELS.items() if v == self.c_type.get()), "FS")
        ok, err = self.db.add_pf_link(self.pid, self.row["id"], wid, t, _num(self.e_lag.get()))
        if not ok:
            messagebox.showerror("Ошибка", err, parent=self); return
        self.db.pf_recalc_schedule(self.pid)
        self.reload()

    def remove(self):
        s = self.tree.selection()
        if s:
            self.db.delete_pf_link(int(s[0]))
            self.reload()


class DirectoryDialog(tk.Toplevel):
    def __init__(self, parent, title, getter, adder, renamer, deleter):
        super().__init__(parent)
        self.getter, self.adder, self.renamer, self.deleter = getter, adder, renamer, deleter
        self.title(title)
        self.geometry("440x430")
        self.transient(parent)
        self.tree = ttk.Treeview(self, columns=("n",), show="headings", height=14)
        self.tree.heading("n", text=title)
        self.tree.column("n", width=380)
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)
        f = ttk.Frame(self)
        f.pack(fill="x", padx=8, pady=(0, 8))
        self.e = ttk.Entry(f, width=28)
        self.e.pack(side=tk.LEFT, padx=4)
        for t, c in (("Добавить", self.add), ("Переименовать", self.rename), ("Удалить", self.delete)):
            ttk.Button(f, text=t, command=c).pack(side=tk.LEFT, padx=2)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._fill())
        self.reload()
        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _fill(self):
        s = self.tree.selection()
        if s:
            self.e.delete(0, tk.END)
            self.e.insert(0, self.tree.item(s[0])["values"][0])

    def reload(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for n in self.getter():
            self.tree.insert("", tk.END, values=(n,))

    def add(self):
        if self.adder(self.e.get()):
            self.reload()

    def rename(self):
        s = self.tree.selection()
        if s and self.renamer(self.tree.item(s[0])["values"][0], self.e.get()):
            self.reload()

    def delete(self):
        s = self.tree.selection()
        if s and messagebox.askyesno("Подтверждение", "Удалить?", parent=self):
            self.deleter(self.tree.item(s[0])["values"][0])
            self.reload()


class GanttDialog(tk.Toplevel):
    def __init__(self, parent, db, pid, project):
        super().__init__(parent)
        self.title(f"Диаграмма Ганта · {project}")
        self.geometry("1150x620")
        rows = [dict(r) for r in db.get_plan_fact(pid)]
        met = db.pf_metrics(pid)["rows"]
        dates = []
        for r in rows:
            for k in ("start_plan", "end_plan", "start_fact", "end_fact", "baseline_start", "baseline_end"):
                d = db.pf_parse(r.get(k))
                if d:
                    dates.append(d)
        if not dates:
            ttk.Label(self, text="Нет дат для отображения").pack(padx=20, pady=20)
            return
        from datetime import timedelta
        d0, d1 = min(dates), max(dates)
        span = max((d1 - d0).days + 1, 1)
        cv = tk.Canvas(self, bg="white")
        sb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=cv.yview)
        cv.configure(yscroll=sb.set, scrollregion=(0, 0, 280 + span * 14, len(rows) * 30 + 60))
        cv.pack(side=tk.LEFT, fill="both", expand=True)
        sb.pack(side=tk.RIGHT, fill="y")
        left, top, scale = 270, 40, 14
        for i in range(0, span, 7):
            x = left + i * scale
            cv.create_line(x, top - 10, x, top + len(rows) * 30, fill="#eee")
            cv.create_text(x, top - 20, text=(d0 + timedelta(days=i)).strftime("%d.%m"),
                           font=("Arial", 7), anchor="w")
        tx = left + (datetime.now() - d0).days * scale
        cv.create_line(tx, top - 10, tx, top + len(rows) * 30, fill="red", dash=(4, 2))
        for i, r in enumerate(rows):
            y = top + i * 30
            mark = "🔒 " if r.get("is_blocked") else ""
            cv.create_text(5, y + 10, anchor="w", font=("Arial", 8),
                           text=f'{mark}№{r["number"]} {(r.get("name") or "")[:32]}')
            bs, be = db.pf_parse(r.get("baseline_start")), db.pf_parse(r.get("baseline_end"))
            sp, ep = db.pf_parse(r.get("start_plan")), db.pf_parse(r.get("end_plan"))
            sf, ef = db.pf_parse(r.get("start_fact")), db.pf_parse(r.get("end_fact"))
            if bs and be:
                cv.create_rectangle(left + (bs - d0).days * scale, y,
                                    left + ((be - d0).days + 1) * scale, y + 4,
                                    fill="#cccccc", outline="")
            if sp and ep:
                cv.create_rectangle(left + (sp - d0).days * scale, y + 6,
                                    left + ((ep - d0).days + 1) * scale, y + 15,
                                    fill="#cfe2f3", outline="#3d85c6")
            if sf:
                e = ef or datetime.now()
                light = met.get(r["id"], {}).get("light")
                color = {"done": "#b6d7a8", "overdue": "#ea9999", "blocked": "#d9d2e9"}.get(light, "#ffd966")
                cv.create_rectangle(left + (sf - d0).days * scale, y + 17,
                                    left + ((e - d0).days + 1) * scale, y + 25,
                                    fill=color, outline="#999")
        cv.create_text(left, 10, anchor="w", font=("Arial", 8, "bold"),
                       text="серая — базовый план, синяя — текущий план, цветная — факт; красная линия — сегодня")