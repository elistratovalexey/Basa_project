# -*- coding: utf-8 -*-
"""База наименований склада. При первом открытии наполняется из заказов."""
import tkinter as tk
from tkinter import ttk, messagebox


class WarehouseNamesDialog(tk.Toplevel):
    def __init__(self, parent, db, on_changed=None):
        super().__init__(parent)
        self.db = db
        self.on_changed = on_changed
        self.title("База наименований (склад)")
        self.geometry("900x560")
        self.transient(parent)

        if not self.db.get_warehouse_names():
            n = self.db.sync_warehouse_names_from_orders()
            if n:
                print(f"[warehouse] наименований из заказов: {n}")

        top = ttk.Frame(self, padding=(10, 8))
        top.pack(fill="x")
        ttk.Button(top, text="Обновить из заказов",
                   command=self.sync).pack(side=tk.LEFT, padx=4)
        ttk.Label(top, text="Поиск:").pack(side=tk.LEFT, padx=(12, 4))
        self.e_find = ttk.Entry(top, width=26)
        self.e_find.pack(side=tk.LEFT)
        self.e_find.bind("<KeyRelease>", lambda e: self.reload())

        mid = ttk.Frame(self, padding=(10, 0))
        mid.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(mid, columns=("name", "article", "unit", "note"),
                                 show="headings", height=13)
        for c, t, w in (("name", "Наименование", 380), ("article", "Артикул", 150),
                        ("unit", "Ед.", 60), ("note", "Примечание", 200)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center" if c == "unit" else "w")
        vs = ttk.Scrollbar(mid, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=vs.set)
        self.tree.pack(side=tk.LEFT, fill="both", expand=True)
        vs.pack(side=tk.RIGHT, fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.pick)

        f = ttk.Frame(self, padding=(10, 6))
        f.pack(fill="x")
        ttk.Label(f, text="Наименование:").grid(row=0, column=0, sticky="w")
        self.e_name = ttk.Entry(f, width=50)
        self.e_name.grid(row=0, column=1, columnspan=3, sticky="ew", pady=3)
        ttk.Label(f, text="Артикул:").grid(row=1, column=0, sticky="w")
        self.e_article = ttk.Entry(f, width=20)
        self.e_article.grid(row=1, column=1, sticky="w", pady=3)
        ttk.Label(f, text="Ед.:").grid(row=1, column=2, sticky="e", padx=(10, 4))
        self.e_unit = ttk.Entry(f, width=8)
        self.e_unit.grid(row=1, column=3, sticky="w")
        self.e_unit.insert(0, "шт")
        ttk.Label(f, text="Примечание:").grid(row=2, column=0, sticky="w")
        self.e_note = ttk.Entry(f, width=50)
        self.e_note.grid(row=2, column=1, columnspan=3, sticky="ew", pady=3)
        f.grid_columnconfigure(1, weight=1)

        bf = ttk.Frame(self, padding=(10, 0, 10, 10))
        bf.pack(fill="x")
        for t, c in (("Добавить", self.add), ("Сохранить изменения", self.save),
                     ("Удалить", self.delete), ("Закрыть", self.destroy)):
            ttk.Button(bf, text=t, command=c).pack(side=tk.LEFT, padx=4)
        self.bind("<Escape>", lambda e: self.destroy())
        self.reload()
        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def reload(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        find = self.e_find.get().strip().lower()
        for r in self.db.get_warehouse_names():
            if find and find not in (r["name"] or "").lower() \
                    and find not in (r["article"] or "").lower():
                continue
            self.tree.insert("", tk.END, iid=str(r["id"]),
                             values=(r["name"], r["article"] or "", r["unit"] or "",
                                     r["note"] or ""))
        if self.on_changed:
            try:
                self.on_changed()
            except Exception:
                pass

    def sync(self):
        n = self.db.sync_warehouse_names_from_orders()
        self.reload()
        messagebox.showinfo("Из заказов", f"Добавлено наименований: {n}", parent=self)

    def pick(self, e=None):
        s = self.tree.selection()
        if not s:
            return
        v = self.tree.item(s[0])["values"]
        for entry, val in ((self.e_name, v[0]), (self.e_article, v[1]),
                           (self.e_unit, v[2] or "шт"), (self.e_note, v[3])):
            entry.delete(0, tk.END)
            entry.insert(0, val or "")

    def add(self):
        if self.db.add_warehouse_name(self.e_name.get(), self.e_article.get(),
                                      self.e_unit.get(), self.e_note.get()):
            self.reload()
        else:
            messagebox.showwarning("Внимание", "Пустое или уже существующее наименование",
                                   parent=self)

    def save(self):
        s = self.tree.selection()
        if not s:
            messagebox.showwarning("Внимание", "Выберите запись!", parent=self)
            return
        if self.db.update_warehouse_name(int(s[0]), self.e_name.get(), self.e_article.get(),
                                         self.e_unit.get(), self.e_note.get()):
            self.reload()
        else:
            messagebox.showwarning("Внимание", "Наименование занято", parent=self)

    def delete(self):
        s = self.tree.selection()
        if s and messagebox.askyesno("Подтверждение",
                                     "Удалить наименование из базы?\n"
                                     "Позиции склада не изменятся.", parent=self):
            self.db.delete_warehouse_name(int(s[0]))
            self.reload()
