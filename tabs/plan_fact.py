# -*- coding: utf-8 -*-
"""План-Факт v2: сроки, ответственные, зависимости, контроль выполнения."""
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
        self.create_ui()

    # ==================================================================
    def create_ui(self):
        top = ttk.Frame(self.parent)
        top.pack(fill="x", pady=4)
        for text, cmd in (("Добавить", self.add_record),
                          ("Сохранить", self.save_record),
                          ("Удалить", self.delete_record),
                          ("Зависимости…", self.open_links),
                          ("Пересчитать сроки", self.recalc),
                          ("База работ", self.open_work_types),
                          ("База статусов", self.open_work_statuses),
                          ("База ответственных", self.open_responsibles),
                          ("Ганта", self.open_gantt),
                          ("Экспорт", self.export),
                          ("Очистить форму", self.clear_form)):
            ttk.Button(top, text=text, command=cmd).pack(side=tk.LEFT, padx=3)

        self.lbl_summary = ttk.Label(self.parent, text="", font=("Arial", 9, "bold"),
                                     foreground="#0a58ca")
        self.lbl_summary.pack(fill="x", padx=8, pady=(2, 4))

        # --- Карточка работы ---
        card = ttk.LabelFrame(self.parent, text="Карточка работы", padding=8)
        card.pack(fill="x", padx=6, pady=4)

        ttk.Label(card, text="№:").grid(row=0, column=0, sticky="w")
        self.e_num = ttk.Entry(card, width=6)
        self.e_num.grid(row=0, column=1, sticky="w", padx=(0, 10))
        ttk.Label(card, text="Наименование работ:").grid(row=0, column=2, sticky="w")
        self.e_name = ttk.Entry(card, width=52)
        self.e_name.grid(row=0, column=3, columnspan=5, sticky="ew", padx=(0, 10))
        ttk.Label(card, text="Подпроект:").grid(row=0, column=8, sticky="w")
        self.c_subproject = ttk.Combobox(card, width=22)
        self.c_subproject.grid(row=0, column=9, sticky="w")

        ttk.Label(card, text="Тип работ:").grid(row=1, column=0, sticky="w", pady=4)
        self.c_type = ttk.Combobox(card, width=22)
        self.c_type.grid(row=1, column=1, columnspan=2, sticky="w", pady=4)
        ttk.Button(card, text="+", width=2, command=self.add_work_type).grid(row=1, column=2, sticky="e")
        ttk.Label(card, text="Ответственный:").grid(row=1, column=3, sticky="w")
        self.c_resp = ttk.Combobox(card, width=24)
        self.c_resp.grid(row=1, column=4, sticky="w")
        ttk.Button(card, text="База ответственных", command=self.open_responsibles).grid(
            row=1, column=5, sticky="w", padx=4)
        ttk.Label(card, text="Статус:").grid(row=1, column=6, sticky="w")
        self.c_status = ttk.Combobox(card, width=18)
        self.c_status.grid(row=1, column=7, sticky="w")
        ttk.Button(card, text="+", width=2, command=self.add_work_status).grid(row=1, column=8, sticky="w")
        self.v_milestone = tk.BooleanVar(value=False)
        ttk.Checkbutton(card, text="Веха", variable=self.v_milestone).grid(row=1, column=9, sticky="w")

        ttk.Label(card, text="Начало план:").grid(row=2, column=0, sticky="w", pady=4)
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
        self.c_unit = ttk.Combobox(card, values=UNITS, width=17, state="readonly")
        self.c_unit.set(UNITS[0])
        self.c_unit.grid(row=2, column=8, sticky="w")
        ttk.Label(card, text="Окончание план:").grid(row=2, column=9, sticky="w")
        self.lbl_end_plan = ttk.Label(card, text="—", foreground="#0a58ca",
                                      font=("Arial", 9, "bold"))
        self.lbl_end_plan.grid(row=2, column=10, sticky="w")

        ttk.Label(card, text="Окончание факт:").grid(row=3, column=0, sticky="w", pady=4)
        self.e_end_fact = ttk.Entry(card, width=12)
        self.e_end_fact.grid(row=3, column=1, sticky="w")
        ttk.Button(card, text="📅", width=2,
                   command=lambda: self._pick(self.e_end_fact)).grid(row=3, column=2, sticky="w")
        ttk.Label(card, text="% выполнения:").grid(row=3, column=3, sticky="w")
        self.e_progress = ttk.Entry(card, width=6)
        self.e_progress.grid(row=3, column=4, sticky="w")
        self.e_progress.insert(0, "0")
        ttk.Label(card, text="Входит в работу:").grid(row=3, column=6, sticky="w")
        self.c_parent = ttk.Combobox(card, width=30, state="readonly")
        self.c_parent.grid(row=3, column=7, columnspan=2, sticky="w")
        ttk.Label(card, text="Прогноз / Δ:").grid(row=3, column=9, sticky="w")
        self.lbl_forecast = ttk.Label(card, text="—", foreground="gray")
        self.lbl_forecast.grid(row=3, column=10, sticky="w")

        ttk.Label(card, text="Комментарии:").grid(row=4, column=0, sticky="nw", pady=4)
        self.e_comment = tk.Text(card, width=100, height=2)
        self.e_comment.grid(row=4, column=1, columnspan=10, sticky="ew", pady=4)
        card.grid_columnconfigure(3, weight=1)

        for w in (self.e_start_plan, self.e_dur):
            w.bind("<KeyRelease>", lambda e: self._recalc_label())
        self.c_unit.bind("<<ComboboxSelected>>", lambda e: self._recalc_label())

        # --- Фильтры ---
        flt = ttk.Frame(self.parent)
        flt.pack(fill="x", padx=6, pady=2)
        self.v_overdue = tk.BooleanVar(value=False)
        self.v_inwork = tk.BooleanVar(value=False)
        ttk.Checkbutton(flt, text="Только просроченные", variable=self.v_overdue,
                        command=self.load_records).pack(side=tk.LEFT, padx=6)
        ttk.Checkbutton(flt, text="Только в работе", variable=self.v_inwork,
                        command=self.load_records).pack(side=tk.LEFT, padx=6)
        ttk.Label(flt, text="Ответственный:").pack(side=tk.LEFT, padx=(12, 4))
        self.c_f_resp = ttk.Combobox(flt, width=20, state="readonly")
        self.c_f_resp.pack(side=tk.LEFT)
        self.c_f_resp.bind("<<ComboboxSelected>>", lambda e: self.load_records())
        ttk.Label(flt, text="Подпроект:").pack(side=tk.LEFT, padx=(12, 4))
        self.c_f_sub = ttk.Combobox(flt, width=20, state="readonly")
        self.c_f_sub.pack(side=tk.LEFT)
        self.c_f_sub.bind("<<ComboboxSelected>>", lambda e: self.load_records())
        ttk.Button(flt, text="Сброс", command=self.reset_filters).pack(side=tk.LEFT, padx=8)

        # --- Таблица (дерево) ---
        tf = ttk.LabelFrame(self.parent, text="Работы по проекту (дерево подчинённости)", padding=6)
        tf.pack(fill="both", expand=True, padx=6, pady=4)
        cols = ("num", "name", "sub", "type", "resp", "status", "sp", "sf",
                "dur", "ep", "ef", "delta", "prog", "forecast", "slack", "depends")
        self.tree = ttk.Treeview(tf, columns=cols, show="tree headings", height=14)
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=30, stretch=False)
        heads = [("num", "№", 45), ("name", "Наименование работ", 280), ("sub", "Подпроект", 120),
                 ("type", "Тип работ", 110), ("resp", "Ответственный", 130),
                 ("status", "Статус", 110), ("sp", "Начало план", 90), ("sf", "Начало факт", 90),
                 ("dur", "Выполнение", 110), ("ep", "Окончание план", 100),
                 ("ef", "Окончание факт", 100), ("delta", "Δ дней", 65),
                 ("prog", "%", 50), ("forecast", "Прогноз", 90),
                 ("slack", "Резерв", 65), ("depends", "Зависит от", 130)]
        for c, t, w in heads:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w" if c in ("name", "sub", "type", "resp", "depends") else "center")
        vs = ttk.Scrollbar(tf, orient=tk.VERTICAL, command=self.tree.yview)
        hs = ttk.Scrollbar(tf, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscroll=vs.set, xscroll=hs.set)
        self.tree.pack(side=tk.LEFT, fill="both", expand=True)
        vs.pack(side=tk.RIGHT, fill="y")
        hs.pack(side=tk.BOTTOM, fill="x")
        self.tree.tag_configure("overdue", background="#f8d7da")
        self.tree.tag_configure("soon", background="#fff3cd")
        self.tree.tag_configure("done", background="#d9ead3")
        self.tree.tag_configure("critical", foreground="#8b0000")
        self.tree.tag_configure("latestart", foreground="#b02a37")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", lambda e: self.open_links())

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
        pid = self.db_manager.get_project_id(self.app.current_project or "")
        self.c_type["values"] = self.db_manager.get_work_types()
        self.c_status["values"] = self.db_manager.get_work_statuses()
        self.c_resp["values"] = [r["name"] for r in self.db_manager.get_responsibles()]
        try:
            self.c_subproject["values"] = [""] + [r["name"] for r in
                                                  self.db_manager.get_subprojects(self.app.current_project)]
        except Exception:
            pass
        rows = self.db_manager.get_plan_fact(pid) if pid else []
        self._parents = {"— нет —": 0}
        for r in rows:
            self._parents[f'№{r["number"]} · {r["name"] or ""}'] = r["id"]
        self.c_parent["values"] = list(self._parents.keys())
        if not self.c_parent.get():
            self.c_parent.set("— нет —")
        self.c_f_resp["values"] = [""] + [r["name"] for r in self.db_manager.get_responsibles()]
        subs = sorted({(r["subproject"] or "") for r in rows if r["subproject"]})
        self.c_f_sub["values"] = [""] + subs

    def reset_filters(self):
        self.v_overdue.set(False)
        self.v_inwork.set(False)
        self.c_f_resp.set("")
        self.c_f_sub.set("")
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
            text=(f"Работ: {s['total']} · выполнено {s['done']} · в работе {s['in_work']} · "
                  f"просрочено {s['overdue']} · старт просрочен {s['late_start']} · "
                  f"критических {s['critical']} · выполнение проекта {s['progress']}%"))

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
            if f_resp and (r.get("responsible") or "") != f_resp:
                return False
            if f_sub and (r.get("subproject") or "") != f_sub:
                return False
            return True

        def insert(r, parent_iid=""):
            mm = met.get(r["id"], {})
            dur = f'{_num(r.get("duration_qty")):g} {r.get("duration_unit") or ""}'.strip()
            tags = []
            if mm.get("light") in ("overdue", "soon", "done"):
                tags.append(mm["light"])
            if mm.get("critical"):
                tags.append("critical")
            if mm.get("late_start"):
                tags.append("latestart")
            iid = self.tree.insert(parent_iid, tk.END, text="", tags=tuple(tags), values=(
                r["number"], r.get("name") or "", r.get("subproject") or "",
                r.get("work_type") or "", r.get("responsible") or "", r.get("status") or "",
                r.get("start_plan") or "", r.get("start_fact") or "", dur,
                r.get("end_plan") or "", r.get("end_fact") or "",
                mm.get("delta") if mm.get("delta") is not None else "",
                f'{mm.get("progress", 0)}%', mm.get("forecast") or "",
                mm.get("slack") if mm.get("slack") is not None else "",
                mm.get("depends") or "—"))
            iids[r["id"]] = iid
            self._row_num[iid] = r["number"]
            return iid

        # первый проход — корни и дети с уже вставленным родителем
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
        self.tree.item("", open=True)
        for iid in iids.values():
            self.tree.item(iid, open=True)

    # ==================================================================
    def on_select(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        num = self._row_num.get(sel[0])
        if num is None:
            return
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
        self.v_milestone.set(bool(row.get("is_milestone")))
        for e, k in ((self.e_start_plan, "start_plan"), (self.e_start_fact, "start_fact"),
                     (self.e_end_fact, "end_fact")):
            e.delete(0, tk.END); e.insert(0, row.get(k) or "")
        self.e_dur.delete(0, tk.END); self.e_dur.insert(0, f'{_num(row.get("duration_qty")):g}')
        self.c_unit.set(row.get("duration_unit") or UNITS[0])
        self.e_progress.delete(0, tk.END); self.e_progress.insert(0, str(row.get("progress") or 0))
        self.e_comment.delete("1.0", tk.END); self.e_comment.insert("1.0", row.get("comment") or "")
        par = int(row.get("parent_id") or 0)
        label = next((k for k, v in self._parents.items() if v == par), "— нет —")
        self.c_parent.set(label)
        self._recalc_label()
        mm = self.db_manager.pf_metrics(pid)["rows"].get(row["id"], {})
        self.lbl_forecast.config(
            text=f'{mm.get("forecast") or "—"} / Δ {mm.get("delta") if mm.get("delta") is not None else "—"}')

    def clear_form(self):
        self._current_number = None
        for e in (self.e_num, self.e_name, self.e_start_plan, self.e_start_fact,
                  self.e_end_fact, self.e_dur):
            e.delete(0, tk.END)
        self.e_progress.delete(0, tk.END); self.e_progress.insert(0, "0")
        self.e_comment.delete("1.0", tk.END)
        for c in (self.c_subproject, self.c_type, self.c_resp, self.c_status):
            c.set("")
        self.c_unit.set(UNITS[0])
        self.c_parent.set("— нет —")
        self.v_milestone.set(False)
        self.lbl_end_plan.config(text="—")
        self.lbl_forecast.config(text="—")

    def _collect(self):
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
            "comment": self.e_comment.get("1.0", tk.END).strip(),
            "note": self.e_comment.get("1.0", tk.END).strip(),
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
        pid = self.db_manager.get_project_id(self.app.current_project)
        num = int(_num(self.e_num.get(), 0)) or self.db_manager.get_next_number("plan_fact", pid)
        exists = any(r["number"] == num for r in self.db_manager.get_plan_fact(pid))
        if exists and self._current_number == num:
            self.db_manager.update_plan_fact(pid, num, data)
            action = "отредактирована"
        elif exists:
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

    # ==================================================================
    def _selected_row(self):
        if self._current_number is None:
            messagebox.showwarning("Внимание", "Выберите работу!")
            return None, None
        pid = self.db_manager.get_project_id(self.app.current_project)
        row = next((dict(r) for r in self.db_manager.get_plan_fact(pid)
                    if r["number"] == self._current_number), None)
        return pid, row

    def open_links(self):
        pid, row = self._selected_row()
        if not row:
            return
        WorkLinksDialog(self.root, self.db_manager, pid, row)
        self.db_manager.pf_recalc_schedule(pid)
        self.load_records()

    def open_responsibles(self):
        ResponsiblesDialog(self.root, self.db_manager)
        self._refresh_dicts()

    def open_work_types(self):
        DirectoryDialog(self.root, self.db_manager, "Типы работ",
                        self.db_manager.get_work_types, self.db_manager.add_work_type,
                        self.db_manager.rename_work_type, self.db_manager.delete_work_type)
        self._refresh_dicts()

    def open_work_statuses(self):
        DirectoryDialog(self.root, self.db_manager, "Статусы работ",
                        self.db_manager.get_work_statuses, self.db_manager.add_work_status,
                        self.db_manager.rename_work_status, self.db_manager.delete_work_status)
        self._refresh_dicts()

    def add_work_type(self):
        from tkinter import simpledialog
        n = simpledialog.askstring("Тип работ", "Новый тип:", parent=self.root)
        if n and self.db_manager.add_work_type(n):
            self._refresh_dicts()
            self.c_type.set(n.strip())

    def add_work_status(self):
        from tkinter import simpledialog
        n = simpledialog.askstring("Статус", "Новый статус:", parent=self.root)
        if n and self.db_manager.add_work_status(n):
            self._refresh_dicts()
            self.c_status.set(n.strip())

    def open_gantt(self):
        pid = self.db_manager.get_project_id(self.app.current_project or "")
        if not pid:
            return
        GanttDialog(self.root, self.db_manager, pid, self.app.current_project)

    def export(self):
        try:
            import openpyxl
            from openpyxl.styles import Font
        except ImportError:
            messagebox.showerror("Нет библиотеки", "pip install openpyxl")
            return
        if not self.app.current_project:
            return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx",
                                            initialfile=f"План-Факт_{self.app.current_project}.xlsx")
        if not path:
            return
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "План-Факт"
        heads = ["№", "Наименование", "Подпроект", "Тип", "Ответственный", "Статус",
                 "Начало план", "Начало факт", "Выполнение", "Окончание план",
                 "Окончание факт", "Δ дней", "%", "Прогноз", "Резерв", "Зависит от", "Комментарии"]
        ws.append([self.app.current_project])
        ws.append(heads)
        for c in ws[2]:
            c.font = Font(bold=True)
        pid = self.db_manager.get_project_id(self.app.current_project)
        rows = {r["id"]: dict(r) for r in self.db_manager.get_plan_fact(pid)}
        met = self.db_manager.pf_metrics(pid)["rows"]
        for r in rows.values():
            mm = met.get(r["id"], {})
            ws.append([r["number"], r.get("name"), r.get("subproject"), r.get("work_type"),
                       r.get("responsible"), r.get("status"), r.get("start_plan"),
                       r.get("start_fact"),
                       f'{_num(r.get("duration_qty")):g} {r.get("duration_unit") or ""}',
                       r.get("end_plan"), r.get("end_fact"), mm.get("delta"),
                       mm.get("progress"), mm.get("forecast"), mm.get("slack"),
                       mm.get("depends"), r.get("comment")])
        for col, w in zip("ABCDEFGHIJKLMNOPQ",
                          (5, 40, 18, 16, 18, 14, 12, 12, 18, 14, 14, 8, 6, 12, 8, 18, 40)):
            ws.column_dimensions[col].width = w
        ws.freeze_panes = "C3"
        try:
            wb.save(path)
            messagebox.showinfo("Успех", f"Сохранено:\n{path}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))


# ======================================================================
class ResponsiblesDialog(tk.Toplevel):
    """База ответственных."""
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.title("База ответственных")
        self.geometry("720x460")
        self.transient(parent)
        cols = ("name", "pos", "email", "phone")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=12)
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
        ttk.Button(bf, text="Добавить", command=self.add).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Сохранить изменения", command=self.save).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Удалить", command=self.delete).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Закрыть", command=self.destroy).pack(side=tk.LEFT, padx=4)
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
        v = self.tree.item(s[0])["values"]
        for k, val in zip(("name", "pos", "email", "phone"), v):
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
        if not s:
            return
        if self.db.update_responsible(int(s[0]), self.e["name"].get(), self.e["pos"].get(),
                                      self.e["email"].get(), self.e["phone"].get()):
            self.reload()
        else:
            messagebox.showwarning("Внимание", "ФИО занято", parent=self)

    def delete(self):
        s = self.tree.selection()
        if s and messagebox.askyesno("Подтверждение", "Удалить ответственного?", parent=self):
            self.db.delete_responsible(int(s[0]))
            self.reload()


class WorkLinksDialog(tk.Toplevel):
    """Зависимости работы по срокам."""
    def __init__(self, parent, db, pid, row):
        super().__init__(parent)
        self.db, self.pid, self.row = db, pid, row
        self.title(f'Зависимости · №{row["number"]} {row.get("name") or ""}')
        self.geometry("760x420")
        self.transient(parent)
        self.rows = {r["id"]: dict(r) for r in db.get_plan_fact(pid)}
        ttk.Label(self, text="Эта работа начинается/заканчивается в зависимости от:",
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
        ttk.Button(bf, text="Добавить связь", command=self.add).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Удалить связь", command=self.remove).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Закрыть", command=self.destroy).pack(side=tk.LEFT, padx=4)
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
            messagebox.showwarning("Внимание", "Выберите работу", parent=self)
            return
        t = next((k for k, v in LINK_LABELS.items() if v == self.c_type.get()), "FS")
        ok, err = self.db.add_pf_link(self.pid, self.row["id"], wid, t, _num(self.e_lag.get()))
        if not ok:
            messagebox.showerror("Ошибка", err, parent=self)
            return
        self.db.pf_recalc_schedule(self.pid)
        self.reload()

    def remove(self):
        s = self.tree.selection()
        if s:
            self.db.delete_pf_link(int(s[0]))
            self.reload()


class DirectoryDialog(tk.Toplevel):
    """Универсальный справочник (типы работ / статусы)."""
    def __init__(self, parent, db, title, getter, adder, renamer, deleter):
        super().__init__(parent)
        self.getter, self.adder, self.renamer, self.deleter = getter, adder, renamer, deleter
        self.title(title)
        self.geometry("420x420")
        self.transient(parent)
        self.tree = ttk.Treeview(self, columns=("n",), show="headings", height=14)
        self.tree.heading("n", text=title)
        self.tree.column("n", width=360)
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)
        f = ttk.Frame(self)
        f.pack(fill="x", padx=8)
        self.e = ttk.Entry(f, width=30)
        self.e.pack(side=tk.LEFT, padx=4)
        ttk.Button(f, text="Добавить", command=self.add).pack(side=tk.LEFT, padx=2)
        ttk.Button(f, text="Переименовать", command=self.rename).pack(side=tk.LEFT, padx=2)
        ttk.Button(f, text="Удалить", command=self.delete).pack(side=tk.LEFT, padx=2)
        self.tree.bind("<<TreeviewSelect>>",
                       lambda e: self._fill())
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
    """Простая диаграмма Ганта: план / факт / сегодня."""
    def __init__(self, parent, db, pid, project):
        super().__init__(parent)
        self.title(f"Диаграмма Ганта · {project}")
        self.geometry("1100x600")
        rows = [dict(r) for r in db.get_plan_fact(pid)]
        met = db.pf_metrics(pid)["rows"]
        dates = []
        for r in rows:
            for k in ("start_plan", "end_plan", "start_fact", "end_fact"):
                d = db.pf_parse(r.get(k))
                if d:
                    dates.append(d)
        if not dates:
            ttk.Label(self, text="Нет дат для отображения").pack(padx=20, pady=20)
            return
        d0, d1 = min(dates), max(dates)
        span = max((d1 - d0).days + 1, 1)
        cv = tk.Canvas(self, bg="white")
        sb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=cv.yview)
        cv.configure(yscroll=sb.set, scrollregion=(0, 0, 260 + span * 14, len(rows) * 26 + 60))
        cv.pack(side=tk.LEFT, fill="both", expand=True)
        sb.pack(side=tk.RIGHT, fill="y")
        left, top, scale = 250, 40, 14
        for i in range(0, span, 7):
            x = left + i * scale
            cv.create_line(x, top - 10, x, top + len(rows) * 26, fill="#eee")
            cv.create_text(x, top - 20, text=(d0 + __import__("datetime").timedelta(days=i)).strftime("%d.%m"),
                           font=("Arial", 7), anchor="w")
        today_x = left + (datetime.now() - d0).days * scale
        cv.create_line(today_x, top - 10, today_x, top + len(rows) * 26, fill="red", dash=(4, 2))
        for i, r in enumerate(rows):
            y = top + i * 26
            cv.create_text(5, y + 8, anchor="w", font=("Arial", 8),
                           text=f'№{r["number"]} {(r.get("name") or "")[:34]}')
            sp, ep = db.pf_parse(r.get("start_plan")), db.pf_parse(r.get("end_plan"))
            sf, ef = db.pf_parse(r.get("start_fact")), db.pf_parse(r.get("end_fact"))
            if sp and ep:
                cv.create_rectangle(left + (sp - d0).days * scale, y + 2,
                                    left + ((ep - d0).days + 1) * scale, y + 12,
                                    fill="#cfe2f3", outline="#3d85c6")
            if sf:
                e = ef or datetime.now()
                color = "#b6d7a8" if met.get(r["id"], {}).get("light") == "done" else "#ffd966"
                if met.get(r["id"], {}).get("light") == "overdue":
                    color = "#ea9999"
                cv.create_rectangle(left + (sf - d0).days * scale, y + 14,
                                    left + ((e - d0).days + 1) * scale, y + 22,
                                    fill=color, outline="#999")
        cv.create_text(left, 10, anchor="w", font=("Arial", 8, "bold"),
                       text="Сверху — план, снизу — факт; красная линия — сегодня")