# -*- coding: utf-8 -*-
"""Вкладка «Бюджет»: план / заказано / оплачено / получено в рублях + курсы ЦБ."""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
from tabs.base import BaseTab


class BudgetTab(BaseTab):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        self.create_ui()

    def create_ui(self):
        top = ttk.Frame(self.parent)
        top.pack(fill="x", pady=5)
        ttk.Button(top, text="Пересчитать", command=self.load_budget).pack(side=tk.LEFT, padx=5)
        ttk.Button(top, text="Курсы ЦБ на сегодня", command=self.fetch_rates).pack(side=tk.LEFT, padx=5)
        ttk.Button(top, text="Курсы вручную", command=self.manual_rates).pack(side=tk.LEFT, padx=5)
        ttk.Button(top, text="Экспорт в Excel", command=self.export).pack(side=tk.RIGHT, padx=5)
        self.lbl_rates = ttk.Label(top, text="", foreground="gray")
        self.lbl_rates.pack(side=tk.RIGHT, padx=10)

        summary = ttk.LabelFrame(self.parent, text="Итоги по проекту (₽)", padding=8)
        summary.pack(fill="x", pady=5)
        self.lbl = {}
        keys = [("plan_sell", "План продажи"), ("income", "Оплачено заказчиком"),
                ("plan_buy", "Закупки (план)"), ("paid_sup", "Оплачено поставщикам"),
                ("received", "Получено (закупки)"), ("plan_margin", "Маржа план"),
                ("margin", "Маржа факт")]
        for i, (k, title) in enumerate(keys):
            box = ttk.Frame(summary)
            box.grid(row=i // 4, column=i % 4, sticky="w", padx=12, pady=4)
            ttk.Label(box, text=title + ":", font=("Arial", 9, "bold")).pack(anchor="w")
            self.lbl[k] = ttk.Label(box, text="0,00 ₽", font=("Arial", 12))
            self.lbl[k].pack(anchor="w")

        det = ttk.LabelFrame(self.parent, text="Расшифровка", padding=6)
        det.pack(fill="both", expand=True, pady=5)
        cols = ("kind", "item", "amount", "cur", "rub")
        self.tree = ttk.Treeview(det, columns=cols, show="headings", height=16)
        for c, t, w in (("kind", "Тип", 170), ("item", "Позиция", 380),
                        ("amount", "Сумма", 120), ("cur", "Валюта", 70), ("rub", "В рублях", 140)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="e" if c in ("amount", "rub") else "w")
        sb = ttk.Scrollbar(det, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        self.tree.pack(side=tk.LEFT, fill="both", expand=True)
        sb.pack(side=tk.RIGHT, fill="y")

    def _fmt(self, v):
        return f"{v:,.2f} ₽".replace(",", " ").replace(".", ",")

    def load_budget(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        proj = self.app.current_project
        if not proj:
            for k in self.lbl:
                self.lbl[k].config(text="—")
            return
        try:
            b = self.db_manager.get_project_budget(proj)
        except Exception as e:
            messagebox.showerror("Ошибка бюджета", str(e))
            return
        for k, lab in self.lbl.items():
            lab.config(text=self._fmt(b.get(k, 0.0)),
                       foreground="green" if b.get(k, 0) >= 0 else "red")
        for kind, item, amount, cur, rub in b.get("detail", []):
            self.tree.insert("", tk.END, values=(kind, item, f"{amount:,.2f}".replace(",", " "),
                                                 cur, f"{rub:,.2f}".replace(",", " ")))
        rates = " · ".join(f"{c} {self.db_manager.get_rate(c):.2f}" for c in ("USD", "EUR", "CNY", "TRY"))
        self.lbl_rates.config(text="Курсы: " + rates)

    def fetch_rates(self):
        try:
            from utils import get_exchange_rates
            rates = get_exchange_rates()
            n = self.db_manager.save_rates(rates, datetime.now().strftime("%d.%m.%Y"))
            messagebox.showinfo("Курсы", f"Сохранено курсов: {n}")
            self.load_budget()
        except Exception as e:
            messagebox.showerror("Ошибка курсов", str(e))

    def manual_rates(self):
        win = tk.Toplevel(self.root)
        win.title("Курсы вручную")
        win.geometry("320x260")
        entries = {}
        for i, code in enumerate(("USD", "EUR", "CNY", "TRY")):
            ttk.Label(win, text=code + " → ₽:").grid(row=i, column=0, padx=10, pady=6, sticky="w")
            e = ttk.Entry(win, width=14)
            e.grid(row=i, column=1, padx=10, pady=6)
            e.insert(0, f"{self.db_manager.get_rate(code):.4f}")
            entries[code] = e

        def save():
            rates = {}
            for code, e in entries.items():
                try:
                    rates[code] = float(e.get().replace(",", "."))
                except ValueError:
                    pass
            self.db_manager.save_rates(rates, datetime.now().strftime("%d.%m.%Y"))
            win.destroy()
            self.load_budget()

        ttk.Button(win, text="Сохранить", command=save).grid(row=5, column=0, columnspan=2, pady=12)

    def export(self):
        try:
            import openpyxl
        except ImportError:
            messagebox.showerror("Нет библиотеки", "pip install openpyxl")
            return
        if not self.app.current_project:
            messagebox.showwarning("Внимание", "Выберите проект!")
            return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx",
                                            initialfile=f"Бюджет_{self.app.current_project}.xlsx")
        if not path:
            return
        b = self.db_manager.get_project_budget(self.app.current_project)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Бюджет"
        ws.append(["Проект", self.app.current_project])
        ws.append(["Дата", datetime.now().strftime("%d.%m.%Y %H:%M")])
        ws.append([])
        for k, title in (("plan_sell", "План продажи"), ("income", "Оплачено заказчиком"),
                         ("plan_buy", "Закупки (план)"), ("paid_sup", "Оплачено поставщикам"),
                         ("received", "Получено"), ("plan_margin", "Маржа план"), ("margin", "Маржа факт")):
            ws.append([title, round(b.get(k, 0), 2)])
        ws.append([])
        ws.append(["Тип", "Позиция", "Сумма", "Валюта", "В рублях"])
        for row in b.get("detail", []):
            ws.append([row[0], row[1], round(row[2], 2), row[3], round(row[4], 2)])
        try:
            wb.save(path)
            messagebox.showinfo("Успех", f"Сохранено:\n{path}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))