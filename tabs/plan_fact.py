# -*- coding: utf-8 -*-
"""Вкладка «План-Факт»: карточки работ + справочники типов работ и статусов."""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from tabs.base import BaseTab


class DirectoryDialog(tk.Toplevel):
    """Универсальный справочник: типы работ (work_types) или статусы (work_statuses)."""

    def __init__(self, parent, db_manager, kind, on_changed=None):
        super().__init__(parent)
        self.db = db_manager
        self.kind = kind
        self.on_changed = on_changed
        self.title("База работ" if kind == "work_types" else "База статусов")
        self.geometry("430x430")
        self.resizable(False, False)

        top = ttk.Frame(self, padding=8)
        top.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(top, columns=("name",), show="headings", height=14)
        self.tree.heading("name", text="Тип работ" if kind == "work_types" else "Статус")
        self.tree.column("name", width=380, anchor="w")
        self.tree.pack(side=tk.LEFT, fill="both", expand=True)
        sb = ttk.Scrollbar(top, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        sb.pack(side=tk.RIGHT, fill="y")

        form = ttk.Frame(self, padding=8)
        form.pack(fill="x")
        self.entry = ttk.Entry(form, width=30)
        self.entry.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(form, text="Добавить", command=self.add).pack(side=tk.LEFT, padx=2)
        ttk.Button(form, text="Переименовать", command=self.rename).pack(side=tk.LEFT, padx=2)
        ttk.Button(form, text="Удалить", command=self.delete).pack(side=tk.LEFT, padx=2)
        ttk.Button(form, text="Закрыть", command=self.destroy).pack(side=tk.LEFT, padx=8)

        self.tree.bind("<Double-1>", lambda e: self._pick())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._pick())
        self.reload()
        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _get(self):
        if self.kind == "work_types":
            return self.db.get_work_types()
        return self.db.get_work_statuses()

    def reload(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for n in self._get():
            self.tree.insert("", tk.END, values=(n,))

    def _pick(self):
        sel = self.tree.selection()
        if sel:
            self.entry.delete(0, tk.END)
            self.entry.insert(0, self.tree.item(sel[0])["values"][0])

    def _notify(self):
        if self.on_changed:
            try:
                self.on_changed()
            except Exception:
                pass

    def add(self):
        name = self.entry.get().strip()
        if not name:
            messagebox.showwarning("Внимание", "Введите название!")
            return
        ok = self.db.add_work_type(name) if self.kind == "work_types" else self.db.add_work_status(name)
        if ok:
            self.entry.delete(0, tk.END)
            self.reload()
            self._notify()
        else:
            messagebox.showwarning("Внимание", "Такая запись уже существует.")

    def rename(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите строку!")
            return
        old = self.tree.item(sel[0])["values"][0]
        new = self.entry.get().strip()
        if not new:
            messagebox.showwarning("Внимание", "Введите новое название!")
            return
        ok = (self.db.rename_work_type(old, new) if self.kind == "work_types"
              else self.db.rename_work_status(old, new))
        if ok:
            self.reload()
            self._notify()
        else:
            messagebox.showwarning("Внимание", "Не удалось переименовать (имя занято?).")

    def delete(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите строку!")
            return
        name = self.tree.item(sel[0])["values"][0]
        if not messagebox.askyesno("Подтверждение", f"Удалить «{name}»?\n"
                                                    "Записи в План-Факт сохранят старое значение текстом."):
            return
        if self.kind == "work_types":
            self.db.delete_work_type(name)
        else:
            self.db.delete_work_status(name)
        self.reload()
        self._notify()


class PlanFactTab(BaseTab):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        self.editing_number = None
        self.create_ui()

    def create_ui(self):
        # === Кнопки управления ===
        ctrl = ttk.Frame(self.parent)
        ctrl.pack(fill="x", pady=5)
        ttk.Button(ctrl, text="Добавить", command=self.add_record).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl, text="Сохранить изменения", command=self.save_record).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl, text="Редактировать", command=self.edit_record).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl, text="Удалить", command=self.delete_record).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl, text="База работ", command=self.open_work_types).pack(side=tk.LEFT, padx=20)
        ttk.Button(ctrl, text="Статус", command=self.open_statuses).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl, text="Очистить форму", command=self.clear_form).pack(side=tk.LEFT, padx=5)
        self.lbl_mode = ttk.Label(ctrl, text="", foreground="#0066cc")
        self.lbl_mode.pack(side=tk.RIGHT, padx=10)

        # === Форма карточки работы ===
        form = ttk.LabelFrame(self.parent, text="Карточка работы", padding=8)
        form.pack(fill="x", pady=5)
        ttk.Label(form, text="Наименование работ:").grid(row=0, column=0, sticky="w", pady=4)
        self.entry_name = ttk.Entry(form, width=70)
        self.entry_name.grid(row=0, column=1, columnspan=5, sticky="ew", pady=4, padx=5)

        ttk.Label(form, text="Тип работ:").grid(row=1, column=0, sticky="w", pady=4)
        self.combo_type = ttk.Combobox(form, state="readonly", width=28)
        self.combo_type.grid(row=1, column=1, sticky="w", pady=4, padx=5)
        ttk.Button(form, text="+", width=2,
                   command=self.add_type_inline).grid(row=1, column=2, padx=2)

        ttk.Label(form, text="Статус:").grid(row=1, column=3, sticky="w", pady=4, padx=(20, 0))
        self.combo_status = ttk.Combobox(form, state="readonly", width=24)
        self.combo_status.grid(row=1, column=4, sticky="w", pady=4, padx=5)
        ttk.Button(form, text="+", width=2,
                   command=self.add_status_inline).grid(row=1, column=5, padx=2)
        form.columnconfigure(1, weight=1)

        # === Таблица работ ===
        tbl = ttk.LabelFrame(self.parent, text="Работы по проекту", padding=6)
        tbl.pack(fill="both", expand=True, pady=5)
        cols = ("number", "name", "work_type", "status")
        self.tree = ttk.Treeview(tbl, columns=cols, show="headings", height=12)
        for c, t, w in (("number", "№", 50), ("name", "Наименование работ", 420),
                        ("work_type", "Тип работ", 200), ("status", "Статус", 160)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center" if c == "number" else "w")
        sb = ttk.Scrollbar(tbl, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        self.tree.pack(side=tk.LEFT, fill="both", expand=True)
        sb.pack(side=tk.RIGHT, fill="y")
        self.tree.bind("<Double-1>", lambda e: self.edit_record())

    # ------------------------------------------------------------------
    # Справочники
    # ------------------------------------------------------------------
    def _refresh_combos(self):
        self.combo_type['values'] = self.db_manager.get_work_types()
        self.combo_status['values'] = self.db_manager.get_work_statuses()

    def add_type_inline(self):
        name = simpledialog.askstring("Тип работ", "Новый тип работ:", parent=self.root)
        if name and name.strip():
            if self.db_manager.add_work_type(name):
                self._refresh_combos()
                self.combo_type.set(name.strip())
            else:
                messagebox.showwarning("Внимание", "Такой тип уже существует.")

    def add_status_inline(self):
        name = simpledialog.askstring("Статус", "Новый статус:", parent=self.root)
        if name and name.strip():
            if self.db_manager.add_work_status(name):
                self._refresh_combos()
                self.combo_status.set(name.strip())
            else:
                messagebox.showwarning("Внимание", "Такой статус уже существует.")

    def open_work_types(self):
        DirectoryDialog(self.root, self.db_manager, "work_types", on_changed=self._on_dir_changed)

    def open_statuses(self):
        DirectoryDialog(self.root, self.db_manager, "work_statuses", on_changed=self._on_dir_changed)

    def _on_dir_changed(self):
        self._refresh_combos()
        self.load_records()

    def clear_form(self):
        self.editing_number = None
        self.entry_name.delete(0, tk.END)
        self.combo_type.set("")
        self.combo_status.set("")
        self.lbl_mode.config(text="")

    # ------------------------------------------------------------------
    # Записи
    # ------------------------------------------------------------------
    def load_records(self):
        self._refresh_combos()
        for i in self.tree.get_children():
            self.tree.delete(i)
        if not self.app.current_project:
            return
        pid = self.db_manager.get_project_id(self.app.current_project)
        if not pid:
            return
        for r in self.db_manager.get_plan_fact(pid):
            self.tree.insert("", tk.END, values=(
                r["number"], r["name"] or "", r["work_type"] or "", r["status"] or ""))

    def _form_data(self):
        return {
            "name": self.entry_name.get().strip(),
            "work_type": self.combo_type.get().strip(),
            "status": self.combo_status.get().strip(),
            "note": "",
        }

    def add_record(self):
        if self.editing_number is not None:
            messagebox.showinfo("Внимание", "Форма в режиме редактирования — нажмите «Сохранить изменения».")
            return
        self.save_record()

    def save_record(self):
        if not self.app.current_project:
            messagebox.showwarning("Внимание", "Выберите проект!")
            return
        data = self._form_data()
        if not data["name"]:
            messagebox.showwarning("Внимание", "Введите наименование работ!")
            return
        pid = self.db_manager.get_project_id(self.app.current_project)
        if not pid:
            return
        if self.editing_number is None:
            data["number"] = self.db_manager.get_next_number("plan_fact", pid)
            self.db_manager.add_plan_fact(pid, data)
            self.app.log_action(f"План-Факт: добавлена работа №{data['number']} ({data['name']})")
        else:
            self.db_manager.update_plan_fact(pid, self.editing_number, data)
            self.app.log_action(f"План-Факт: работа №{self.editing_number} изменена")
        self.load_records()
        self.clear_form()

    def edit_record(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите работу в таблице!")
            return
        v = self.tree.item(sel[0])["values"]
        self.editing_number = v[0]
        self.entry_name.delete(0, tk.END)
        self.entry_name.insert(0, v[1])
        self.combo_type.set(v[2])
        self.combo_status.set(v[3])
        self.lbl_mode.config(text=f"Редактирование работы №{v[0]}")

    def delete_record(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите работу в таблице!")
            return
        number = self.tree.item(sel[0])["values"][0]
        if not messagebox.askyesno("Подтверждение", f"Удалить работу №{number}?"):
            return
        pid = self.db_manager.get_project_id(self.app.current_project)
        if pid:
            self.db_manager.delete_plan_fact(pid, number)
            self.app.log_action(f"План-Факт: работа №{number} удалена")
            if self.editing_number == number:
                self.clear_form()
            self.load_records()