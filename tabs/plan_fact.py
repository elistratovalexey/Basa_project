# -*- coding: utf-8 -*-
"""План-Факт v4: сроки, зависимости, baseline, блокировки, загрузка, аудит,
уведомления, база наименований работ и правка полей прямо в таблице."""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
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
        self._orders = {}
        self._work_names = {}
        self._pf_inline = None
        self.create_ui()

    # ==================================================================
    # Интерфейс
    # ==================================================================
    def create_ui(self):
        top = ttk.Frame(self.parent)
        top.pack(fill="x", pady=3)
        for text, cmd in (("Добавить", self.add_record), ("Сохранить", self.save_record),
                          ("Удалить", self.delete_record), ("Зависимости…", self.open_links),
                          ("Пересчитать", self.recalc), ("Из заказов", self.sync_orders),
                          ("Зафиксировать базу", self.set_baseline),
                          ("Загрузка", self.open_workload), ("Задержки", self.open_delays),
                          ("История", self.open_audit), ("Уведомления", self.open_notifications),
                          ("База наименований работ", self.open_work_names)):
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
        self.c_name = ttk.Combobox(card, width=46)
        self.c_name.grid(row=0, column=3, columnspan=4, sticky="ew", padx=(0, 4))
        self.c_name.bind("<<ComboboxSelected>>", self.on_work_name_selected)
        self.e_name = self.c_name          # совместимость с остальным кодом
        ttk.Button(card, text="+", width=2,
                   command=self.add_work_name_inline).grid(row=0, column=7, sticky="w", padx=(0, 8))
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
        ttk.Button(card, text="📅", width=2,
                   command=lambda: self._pick(self.e_start_plan)).grid(row=2, column=2, sticky="w")
        ttk.Label(card, text="Начало факт:").grid(row=2, column=3, sticky="w")
        self.e_start_fact = ttk.Entry(card, width=12)
        self.e_start_fact.grid(row=2, column=4, sticky="w")
        ttk.Button(card, text="📅", width=2,
                   command=lambda: self._pick(self.e_start_fact)).grid(row=2, column=5, sticky="w")
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
        ttk.Button(card, text="📅", width=2,
                   command=lambda: self._pick(self.e_end_fact)).grid(row=3, column=2, sticky="w")
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
        ttk.Checkbutton(card, text="🔒 Заблокирована", variable=self.v_blocked).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=3)
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
        ttk.Checkbutton(flt, text="Просроченные", variable=self.v_overdue,
                        command=self.load_records).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(flt, text="В работе", variable=self.v_inwork,
                        command=self.load_records).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(flt, text="Заблокированные", variable=self.v_blocked_only,
                        command=self.load_records).pack(side=tk.LEFT, padx=5)
        ttk.Label(flt, text="Ответственный:").pack(side=tk.LEFT, padx=(10, 3))
        self.c_f_resp = ttk.Combobox(flt, width=18, state="readonly")
        self.c_f_resp.pack(side=tk.LEFT)
        self.c_f_resp.bind("<<ComboboxSelected>>", lambda e: self.load_records())
        ttk.Label(flt, text="Подпроект:").pack(side=tk.LEFT, padx=(10, 3))
        self.c_f_sub = ttk.Combobox(flt, width=18, state="readonly")
        self.c_f_sub.pack(side=tk.LEFT)
        self.c_f_sub.bind("<<ComboboxSelected>>", lambda e: self.load_records())
        ttk.Button(flt, text="Сброс", command=self.reset_filters).pack(side=tk.LEFT, padx=6)

        tf = ttk.LabelFrame(self.parent,
                            text="Работы по проекту  ·  двойной клик по ячейке — правка, "
                                 "Enter — сохранить, Tab — дальше, Esc — отмена", padding=6)
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
            self.tree.column(c, width=w,
                             anchor="w" if c in ("name", "sub", "type", "resp", "depends") else "center")
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
        self.tree.bind("<Double-1>", self.on_tree_double_click)

    # ==================================================================
    # Служебное
    # ==================================================================
    def _pick(self, entry):
        try:
            from dialogs.calendar_dialog import CalendarDialog
        except ImportError:
            entry.delete(0, tk.END)
            entry.insert(0, datetime.now().strftime("%d.%m.%Y"))
            self._recalc_label()
            return
        dlg = CalendarDialog(self.root, entry.get() or None)
        self.root.wait_window(dlg)
        if getattr(dlg, "result", None):
            entry.delete(0, tk.END)
            entry.insert(0, dlg.result)
            self._recalc_label()

    def _recalc_label(self):
        end = self.db_manager.pf_end_plan(self.e_start_plan.get(), _num(self.e_dur.get()),
                                          self.c_unit.get())
        self.lbl_end_plan.config(text=end or "—")

    def _refresh_dicts(self):
        proj = self.app.current_project or ""
        pid = self.db_manager.get_project_id(proj)
        self.c_type["values"] = self.db_manager.get_work_types()
        self.c_status["values"] = self.db_manager.get_work_statuses()
        resp = [r["name"] for r in self.db_manager.get_responsibles()]
        self.c_resp["values"] = resp
        self.c_reason["values"] = self.db_manager.get_delay_reasons()
        self._refresh_work_names()
        try:
            self.c_subproject["values"] = [""] + [r["name"] for r in
                                                  self.db_manager.get_subprojects(proj)]
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
        self.v_overdue.set(False)
        self.v_inwork.set(False)
        self.v_blocked_only.set(False)
        self.c_f_resp.set("")
        self.c_f_sub.set("")
        self.load_records()

    # ==================================================================
    # База наименований работ
    # ==================================================================
    def _has_work_names(self):
        return hasattr(self.db_manager, "get_work_names")

    def _refresh_work_names(self):
        self._work_names = {}
        if not self._has_work_names():
            try:
                self.c_name["values"] = []
            except Exception:
                pass
            return
        try:
            for r in self.db_manager.get_work_names():
                self._work_names[r["name"]] = dict(r)
            self.c_name["values"] = sorted(self._work_names.keys())
        except Exception as e:
            print(f"[plan_fact] work_names: {e}")

    def add_work_name_inline(self):
        if not self._has_work_names():
            messagebox.showerror("Нет справочника",
                                 "В database.py нет методов базы наименований работ.\n"
                                 "Добавьте блок _ensure_work_names / get_work_names / add_work_name.",
                                 parent=self.root)
            return
        name = self.e_name.get().strip()
        if not name:
            messagebox.showwarning("Внимание", "Введите наименование работ!", parent=self.root)
            return
        ok = self.db_manager.add_work_name(name, self.c_type.get().strip(),
                                           _num(self.e_dur.get()), self.c_unit.get())
        self._refresh_work_names()
        if ok:
            self.app.log_action(f"База наименований работ: добавлено «{name}»")
            messagebox.showinfo("Готово", f"«{name}» сохранено в базу наименований работ.",
                                parent=self.root)
        else:
            messagebox.showinfo("Информация", "Такое наименование уже есть в базе.", parent=self.root)

    def on_work_name_selected(self, event=None):
        rec = self._work_names.get(self.e_name.get())
        if not rec:
            return
        if rec.get("work_type") and not self.c_type.get().strip():
            self.c_type.set(rec["work_type"])
        if _num(rec.get("duration_qty")) > 0 and not _num(self.e_dur.get()):
            self.e_dur.delete(0, tk.END)
            self.e_dur.insert(0, f'{_num(rec["duration_qty"]):g}')
            self.c_unit.set(rec.get("duration_unit") or UNITS[0])
        self._recalc_label()

    def open_work_names(self):
        if not self._has_work_names():
            messagebox.showerror("Нет справочника",
                                 "В database.py нет методов базы наименований работ.\n"
                                 "Добавьте блок _ensure_work_names / get_work_names / add_work_name "
                                 "/ update_work_name / delete_work_name.", parent=self.root)
            return
        WorkNamesDialog(self.root, self.db_manager)
        self._refresh_work_names()

    # ==================================================================
    # Загрузка таблицы
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
                    rest.append(r)
                    continue
                insert(r, iids.get(par, ""))
                inserted.add(r["id"])
            pending = rest
            if not pending:
                break
        for r in pending:
            insert(r, "")
        for iid in iids.values():
            self.tree.item(iid, open=True)

    def _reselect(self, number):
        for iid in self.tree.get_children():
            if self._row_num.get(iid) == number:
                self.tree.selection_set(iid)
                self.tree.see(iid)
                self.on_select()
                return
        for parent in self.tree.get_children():
            for iid in self.tree.get_children(parent):
                if self._row_num.get(iid) == number:
                    self.tree.selection_set(iid)
                    self.tree.see(iid)
                    self.on_select()
                    return

    # ==================================================================
    # Карточка
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
            messagebox.showwarning("Внимание", "Выберите проект!")
            return
        self.clear_form()
        pid = self.db_manager.get_project_id(self.app.current_project)
        self.e_num.insert(0, str(self.db_manager.get_next_number("plan_fact", pid)))
        self.e_start_plan.insert(0, datetime.now().strftime("%d.%m.%Y"))
        self._recalc_label()
        self.e_name.focus_set()

    def save_record(self):
        if not self.app.current_project:
            messagebox.showwarning("Внимание", "Выберите проект!")
            return
        data = self._collect()
        if not data["name"]:
            messagebox.showwarning("Внимание", "Укажите наименование работ!")
            return
        if data["is_blocked"] and not data["delay_reason"]:
            messagebox.showwarning("Внимание", "Для заблокированной работы укажите причину задержки!")
            return
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
        self._reselect(num)

    def delete_record(self):
        num = self._current_number
        if num is None:
            messagebox.showwarning("Внимание", "Выберите работу!")
            return
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
    # ИНЛАЙН-РЕДАКТИРОВАНИЕ таблицы работ
    # ==================================================================
    _PF_EDIT_COLS = {
        0: ("number", "int"),
        1: ("name", "workname"),
        2: ("subproject", "subproject"),
        3: ("work_type", "worktype"),
        4: ("responsible", "responsible"),
        5: ("status", "workstatus"),
        6: ("start_plan", "date"),
        7: ("start_fact", "date"),
        8: ("duration", "duration"),
        10: ("end_fact", "date"),
        12: ("progress", "percent"),
        17: ("is_blocked", "blocked"),
        18: ("cost_weight", "float"),
    }
    _PF_READONLY = {
        9: "Окончание план = Начало план + Выполнение.\nМеняйте «Начало план» или «Выполнение».",
        11: "Δ дней считается автоматически: факт (или сегодня) − план.",
        13: "Прогноз = Начало факт + Выполнение.",
        14: "Резерв считается по зависимостям и концу проекта.",
        16: "Сдвиг базы = Окончание план − базовый план.\nБаза фиксируется кнопкой «Зафиксировать базу».",
    }

    def on_tree_double_click(self, event):
        tree = self.tree
        if tree.identify_region(event.x, event.y) != "cell":
            return
        row, col = tree.identify_row(event.y), tree.identify_column(event.x)
        if not row or not col or row not in self._row_num:
            return
        idx = int(col.replace("#", "")) - 1
        if idx == 15:                       # «Зависит от» → окно связей
            self.on_select()
            self.open_links()
            return "break"
        if idx in self._PF_READONLY:
            messagebox.showinfo("Расчётное поле", self._PF_READONLY[idx], parent=self.root)
            return "break"
        self._pf_inline_begin(row, col, idx)
        return "break"

    def _pf_editor_values(self, kind):
        if kind == "workname":
            return sorted(self._work_names.keys())
        if kind == "worktype":
            return self.db_manager.get_work_types()
        if kind == "workstatus":
            return self.db_manager.get_work_statuses()
        if kind == "responsible":
            return [r["name"] for r in self.db_manager.get_responsibles()]
        if kind == "subproject":
            try:
                return [""] + [r["name"] for r in
                               self.db_manager.get_subprojects(self.app.current_project)]
            except Exception:
                return [""]
        if kind == "reason":
            return self.db_manager.get_delay_reasons()
        return []

    def _pf_inline_begin(self, row, col, idx, _retry=False):
        spec = self._PF_EDIT_COLS.get(idx)
        if not spec:
            return
        self._pf_inline_cancel()
        tree = self.tree
        try:
            if not tree.exists(row):
                return
            box = tree.bbox(row, col)
        except Exception:
            return
        if not box:
            if not _retry:
                try:
                    tree.see(row)
                except Exception:
                    pass
                self.root.after(60, lambda: self._pf_inline_begin(row, col, idx, True))
            return
        x, y, w, h = box
        field, kind = spec
        values = list(tree.item(row)["values"])
        old = values[idx] if idx < len(values) else ""
        combo_kinds = ("workname", "worktype", "workstatus", "responsible", "subproject")

        if kind == "duration":
            frame = ttk.Frame(tree)
            frame.place(x=x, y=y, width=max(w, 210), height=h)
            parts = str(old).split(None, 1)
            eq = ttk.Entry(frame, width=6)
            eq.pack(side=tk.LEFT)
            eq.insert(0, parts[0] if parts else "0")
            cu = ttk.Combobox(frame, values=UNITS, width=17, state="readonly")
            cu.pack(side=tk.LEFT)
            cu.set(parts[1] if len(parts) > 1 else UNITS[0])
            eq.focus_set()
            eq.select_range(0, tk.END)
            widget = entry = eq
            widget = frame
            getter = lambda: (eq.get(), cu.get())
            new_sig = lambda v: f"{_num(v[0]):g} {v[1]}"
        elif kind == "blocked":
            frame = ttk.Frame(tree)
            frame.place(x=x, y=y, width=max(w, 260), height=h)
            var = tk.BooleanVar(value=bool(str(old).strip()))
            ttk.Checkbutton(frame, text="🔒", variable=var).pack(side=tk.LEFT)
            cr = ttk.Combobox(frame, values=self._pf_editor_values("reason"), width=24)
            cr.pack(side=tk.LEFT)
            num = self._row_num.get(row)
            pid = self.db_manager.get_project_id(self.app.current_project)
            cur = next((dict(r) for r in self.db_manager.get_plan_fact(pid)
                        if r["number"] == num), {})
            cr.set(cur.get("delay_reason") or "")
            cr.focus_set()
            widget, entry = frame, cr
            getter = lambda: (1 if var.get() else 0, cr.get().strip())
            new_sig = lambda v: "🔒" if v[0] else ""
        elif kind == "date":
            frame = ttk.Frame(tree)
            frame.place(x=x, y=y, width=max(w, 130), height=h)
            ed = ttk.Entry(frame)
            ed.pack(side=tk.LEFT, fill="both", expand=True)
            ed.insert(0, str(old))
            ed.select_range(0, tk.END)
            ed.focus_set()

            def pick():
                self._pick(ed)
                self._pf_inline_commit()
            ttk.Button(frame, text="📅", width=2, command=pick).pack(side=tk.LEFT)
            widget, entry = frame, ed
            getter = lambda: ed.get().strip()
            new_sig = lambda v: str(v)
        elif kind in combo_kinds:
            ed = ttk.Combobox(tree, values=self._pf_editor_values(kind),
                              state="normal" if kind == "workname" else "readonly")
            ed.set(old)
            ed.place(x=x, y=y, width=max(w, 170), height=h)
            ed.focus_set()
            ed.bind("<<ComboboxSelected>>", lambda e: self._pf_inline_commit())
            widget = entry = ed
            getter = lambda: ed.get().strip()
            new_sig = lambda v: str(v)
            self.root.after(30, lambda w=ed: self._pf_post(w))
        else:
            ed = ttk.Entry(tree)
            ed.insert(0, str(old))
            ed.select_range(0, tk.END)
            ed.place(x=x, y=y, width=max(w, 80), height=h)
            ed.focus_set()
            widget = entry = ed
            getter = lambda: ed.get().strip()
            new_sig = lambda v: str(v)

        entry.bind("<Return>", lambda e: self._pf_inline_commit())
        entry.bind("<Escape>", lambda e: self._pf_inline_cancel())
        entry.bind("<FocusOut>", lambda e, w=entry: self._pf_focus_out(w))
        entry.bind("<Tab>", lambda e: self._pf_tab(row, idx))
        self._pf_inline = {"widget": widget, "entry": entry, "row": row, "idx": idx,
                           "field": field, "kind": kind, "get": getter,
                           "sig": str(old), "new_sig": new_sig,
                           "combo": kind in combo_kinds}

    def _pf_post(self, ed):
        info = getattr(self, "_pf_inline", None)
        if not info or info["entry"] is not ed:
            return
        try:
            ed.tk.call("ttk::combobox::Post", ed)
        except tk.TclError:
            try:
                ed.event_generate("<Alt-Down>")
            except Exception:
                pass

    def _pf_combo_busy(self, ed):
        try:
            pop = ed.tk.call("ttk::combobox::PopdownWindow", ed)
        except Exception:
            return False
        try:
            if pop and int(ed.tk.call("winfo", "ismapped", pop)):
                return True
        except Exception:
            pass
        try:
            f = self.focus_get()
            if f is not None and pop and str(f).startswith(str(pop)):
                return True
        except Exception:
            pass
        return False

    def _pf_focus_out(self, ed):
        info = getattr(self, "_pf_inline", None)
        if not info or info["entry"] is not ed:
            return

        def check():
            cur = getattr(self, "_pf_inline", None)
            if not cur or cur["entry"] is not ed:
                return
            if cur.get("combo") and self._pf_combo_busy(ed):
                return
            try:
                if self.focus_get() is ed:
                    return
            except Exception:
                pass
            self._pf_inline_commit()
        self.root.after(180, check)

    def _pf_inline_cancel(self):
        info = getattr(self, "_pf_inline", None)
        self._pf_inline = None
        if info:
            try:
                info["widget"].destroy()
            except Exception:
                pass

    def _pf_tab(self, row, idx):
        self._pf_inline_commit()
        nxt = idx + 1
        while nxt <= max(self._PF_EDIT_COLS):
            if nxt in self._PF_EDIT_COLS:
                try:
                    if self.tree.exists(row):
                        self._pf_inline_begin(row, f"#{nxt + 1}", nxt)
                except Exception:
                    pass
                break
            nxt += 1
        return "break"

    def _pf_inline_commit(self):
        info = getattr(self, "_pf_inline", None)
        if not info:
            return "break"
        self._pf_inline = None
        try:
            raw = info["get"]()
        except Exception:
            raw = None
        try:
            info["widget"].destroy()
        except Exception:
            pass
        if raw is None:
            return "break"
        if info["new_sig"](raw) == info["sig"]:
            return "break"

        row, field, kind = info["row"], info["field"], info["kind"]
        number = self._row_num.get(row)
        pid = self.db_manager.get_project_id(self.app.current_project or "")
        if number is None or not pid:
            return "break"

        try:
            if field == "number":
                new_num = int(_num(raw, 0))
                if new_num <= 0:
                    messagebox.showwarning("Внимание", "Номер должен быть положительным", parent=self.root)
                    return "break"
                if any(r["number"] == new_num for r in self.db_manager.get_plan_fact(pid)):
                    messagebox.showwarning("Внимание", f"Номер {new_num} уже занят!", parent=self.root)
                    return "break"
                self.db_manager.conn.execute(
                    "UPDATE plan_fact SET number=? WHERE project_id=? AND number=?",
                    (new_num, pid, number))
                self.db_manager.conn.commit()
                self._current_number = new_num
                self