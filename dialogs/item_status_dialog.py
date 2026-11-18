# -*- coding: utf-8 -*-
"""Справочник «База статусов артикулов»: список, добавление, переименование, удаление."""
import tkinter as tk
from tkinter import ttk, messagebox


class ItemStatusesDialog(tk.Toplevel):
    def __init__(self, parent, db_manager, on_changed=None):
        super().__init__(parent)
        self.db = db_manager
        self.on_changed = on_changed
        self.title("База статусов артикулов")
        self.geometry("460x460")
        self.resizable(False, False)

        top = ttk.Frame(self, padding=8)
        top.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(top, columns=("name",), show="headings", height=15)
        self.tree.heading("name", text="Статус артикула")
        self.tree.column("name", width=400, anchor="w")
        self.tree.pack(side=tk.LEFT, fill="both", expand=True)
        sb = ttk.Scrollbar(top, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        sb.pack(side=tk.RIGHT, fill="y")

        form = ttk.Frame(self, padding=8)
        form.pack(fill="x")
        self.entry = ttk.Entry(form, width=26)
        self.entry.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(form, text="Добавить", command=self.add).pack(side=tk.LEFT, padx=2)
        ttk.Button(form, text="Переименовать", command=self.rename).pack(side=tk.LEFT, padx=2)
        ttk.Button(form, text="Удалить", command=self.delete).pack(side=tk.LEFT, padx=2)
        ttk.Button(form, text="Закрыть", command=self.destroy).pack(side=tk.LEFT, padx=8)

        ttk.Label(self, padding=(10, 0, 10, 8), foreground="gray",
                  text="Переименование обновляет статус у всех позиций заказов.").pack(fill="x")

        self.tree.bind("<<TreeviewSelect>>", self._pick)
        self.tree.bind("<Double-1>", self._pick)
        self.entry.bind("<Return>", lambda e: self.add())
        self.reload()
        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def reload(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for n in self.db.get_item_statuses():
            self.tree.insert("", tk.END, values=(n,))

    def _pick(self, event=None):
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
            messagebox.showwarning("Внимание", "Введите название статуса!", parent=self)
            return
        if self.db.add_item_status(name):
            self.entry.delete(0, tk.END)
            self.reload()
            self._notify()
        else:
            messagebox.showwarning("Внимание", "Такой статус уже есть.", parent=self)

    def rename(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите статус!", parent=self)
            return
        old = self.tree.item(sel[0])["values"][0]
        new = self.entry.get().strip()
        if not new:
            messagebox.showwarning("Внимание", "Введите новое название!", parent=self)
            return
        if self.db.rename_item_status(old, new):
            self.reload()
            self._notify()
        else:
            messagebox.showwarning("Внимание", "Не удалось переименовать (имя занято?).", parent=self)

    def delete(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите статус!", parent=self)
            return
        name = self.tree.item(sel[0])["values"][0]
        if not messagebox.askyesno("Подтверждение",
                                   f"Удалить статус «{name}»?\n"
                                   "У позиций он останется текстом до переназначения.", parent=self):
            return
        self.db.delete_item_status(name)
        self.reload()
        self._notify()