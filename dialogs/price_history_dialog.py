# -*- coding: utf-8 -*-
"""История цен: все закупки по артикулу/наименованию, лучший поставщик."""
import tkinter as tk
from tkinter import ttk, messagebox


class PriceHistoryDialog(tk.Toplevel):
    def __init__(self, parent, db_manager, article=""):
        super().__init__(parent)
        self.db = db_manager
        self.title("История цен")
        self.geometry("1150x600")

        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=6)
        ttk.Label(top, text="Артикул:").pack(side=tk.LEFT)
        self.entry = ttk.Entry(top, width=24)
        self.entry.pack(side=tk.LEFT, padx=6)
        self.entry.insert(0, article)
        ttk.Button(top, text="Показать", command=self.load).pack(side=tk.LEFT, padx=5)
        ttk.Button(top, text="Обновить историю из БД", command=self.rebuild).pack(side=tk.LEFT, padx=5)
        self.lbl = ttk.Label(top, text="", foreground="#0066cc")
        self.lbl.pack(side=tk.LEFT, padx=15)

        cols = ("date", "article", "name", "sup", "price", "cur", "qty", "proj", "src")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=20)
        for c, t, w in (("date", "Дата", 90), ("article", "Артикул", 130), ("name", "Наименование", 280),
                        ("sup", "Поставщик", 170), ("price", "Цена", 100), ("cur", "Валюта", 70),
                        ("qty", "Кол-во", 70), ("proj", "Проект", 130), ("src", "Источник", 110)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="e" if c in ("price", "qty") else "w")
        self.tree.pack(fill="both", expand=True, padx=8, pady=6)
        self.load()
        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def rebuild(self):
        n = self.db.rebuild_price_history()
        messagebox.showinfo("История цен", f"Записей обновлено: {n}")
        self.load()

    def load(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        art = self.entry.get().strip()
        try:
            if not self.db.get_price_history(limit=1):
                self.db.rebuild_price_history()
            rows = self.db.get_price_history(art or None)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
            return
        for r in rows:
            self.tree.insert("", tk.END, values=(
                r["date"] or "", r["article"] or "", r["name"] or "", r["supplier"] or "",
                f"{r['price']:,.2f}".replace(",", " "), r["currency"] or "",
                r["qty"], r["project_name"] or "", r["source"] or ""))
        if art:
            s = self.db.get_price_summary(art)
            if s:
                d = f" · Δ к прошлой {s['delta']:+.1f}%" if s["delta"] is not None else ""
                self.lbl.config(text=f"Последняя: {s['last']['price']:,.2f} {s['last']['currency']} "
                                     f"({s['last']['supplier']}) · мин {s['min']:,.2f} "
                                     f"({s['best']['supplier']}) · записей {s['count']}{d}")
            else:
                self.lbl.config(text="История по артикулу не найдена")
        else:
            self.lbl.config(text=f"Всего записей: {len(rows)}")