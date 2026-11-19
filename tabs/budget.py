# -*- coding: utf-8 -*-
"""Вкладка «Бюджет»: план / заказано / оплачено / получено в рублях + курсы ЦБ.

Закупки считаются из ДВУХ источников:
  • orders                    — вкладка «Заказы»
  • purchase_specifications   — вкладка «Спецификация Закупок» (счета поставщиков)
Разбивка показывается отдельными итогами и типами строк в расшифровке.
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

from tabs.base import BaseTab


class BudgetTab(BaseTab):
    # (ключ в словаре бюджета, заголовок, мелкий шрифт)
    SUMMARY_KEYS = [
        ("plan_sell", "План продажи", False),
        ("income", "Оплачено заказчиком", False),
        ("plan_buy", "Закупки (план, всего)", False),
        ("plan_buy_orders", "в т.ч. заказы", True),
        ("plan_buy_specs", "в т.ч. счета поставщиков", True),
        ("paid_sup", "Оплачено поставщикам", False),
        ("received", "Получено (закупки)", False),
        ("plan_margin", "Маржа план", False),
        ("margin", "Маржа факт", False),
    ]

    def __init__(self, app, parent):
        super().__init__(app, parent)
        self._last = None          # последний рассчитанный бюджет (для фильтров)
        self.create_ui()

    # ==================================================================
    # Интерфейс
    # ==================================================================
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
        for i, (k, title, small) in enumerate(self.SUMMARY_KEYS):
            box = ttk.Frame(summary)
            box.grid(row=i // 4, column=i % 4, sticky="w", padx=12, pady=4)
            ttk.Label(box, text=title + ":",
                      font=("Arial", 8 if small else 9, "bold")).pack(anchor="w")
            self.lbl[k] = ttk.Label(box, text="0,00 ₽", font=("Arial", 10 if small else 12))
            self.lbl[k].pack(anchor="w")

        self.lbl_split = ttk.Label(self.parent, text="", foreground="#666", justify="left")
        self.lbl_split.pack(fill="x", padx=14, pady=(0, 4))

        # --- Фильтры расшифровки ---
        flt = ttk.Frame(self.parent)
        flt.pack(fill="x", pady=(2, 0))
        ttk.Label(flt, text="Тип строки:").pack(side=tk.LEFT, padx=(14, 4))
        self.combo_kind = ttk.Combobox(flt, width=28, state="readonly", values=["Все типы"])
        self.combo_kind.set("Все типы")
        self.combo_kind.pack(side=tk.LEFT)
        self.combo_kind.bind("<<ComboboxSelected>>", lambda e: self._fill_detail())
        self.hide_zero = tk.BooleanVar(value=True)
        ttk.Checkbutton(flt, text="Скрывать нулевые", variable=self.hide_zero,
                        command=self._fill_detail).pack(side=tk.LEFT, padx=12)
        self.lbl_count = ttk.Label(flt, text="", foreground="gray")
        self.lbl_count.pack(side=tk.LEFT, padx=8)

        det = ttk.LabelFrame(self.parent, text="Расшифровка", padding=6)
        det.pack(fill="both", expand=True, pady=5)
        cols = ("kind", "item", "amount", "cur", "rub")
        self.tree = ttk.Treeview(det, columns=cols, show="headings", height=16)
        for c, t, w in (("kind", "Тип", 190), ("item", "Позиция", 380),
                        ("amount", "Сумма", 120), ("cur", "Валюта", 70), ("rub", "В рублях", 140)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="e" if c in ("amount", "rub") else "w")
        sb = ttk.Scrollbar(det, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        self.tree.pack(side=tk.LEFT, fill="both", expand=True)
        sb.pack(side=tk.RIGHT, fill="y")

        # подсветка типов строк
        self.tree.tag_configure("sell", foreground="#0a58ca")
        self.tree.tag_configure("income", foreground="#198754")
        self.tree.tag_configure("order", foreground="#333333")
        self.tree.tag_configure("spec", background="#fff3cd")     # счета поставщиков — новые
        self.tree.tag_configure("paysup", foreground="#b02a37")

    # ==================================================================
    # Форматирование
    # ==================================================================
    def _fmt(self, v):
        try:
            return f"{float(v):,.2f} ₽".replace(",", " ").replace(".", ",")
        except (TypeError, ValueError):
            return "— ₽"

    @staticmethod
    def _num(v):
        try:
            return f"{float(v):,.2f}".replace(",", " ")
        except (TypeError, ValueError):
            return "0,00"

    @staticmethod
    def _tag_for(kind):
        k = (kind or "").lower()
        if "план (спецификация)" in k:
            return "sell"
        if "оплата заказчика" in k:
            return "income"
        if "закупка (спецификация)" in k:
            return "spec"
        if "оплата поставщику" in k:
            return "paysup"
        return "order"

    # ==================================================================
    # Курсы
    # ==================================================================
    def _auto_fetch_rates(self, silent=False):
        try:
            from utils import get_exchange_rates
            rates = get_exchange_rates()
            n = self.db_manager.save_rates(rates, datetime.now().strftime("%d.%m.%Y"))
            if not silent:
                messagebox.showinfo("Курсы", f"Сохранено курсов: {n}")
            return n > 0
        except Exception as e:
            if not silent:
                messagebox.showerror("Курсы", f"Не удалось получить курсы ЦБ:\n{e}")
            return False

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
        win.resizable(False, False)
        win.transient(self.root)
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
        win.bind("<Escape>", lambda e: win.destroy())
        win.update_idletasks()
        try:
            win.grab_set()
        except tk.TclError:
            pass

    # ==================================================================
    # Расчёт и вывод
    # ==================================================================
    def load_budget(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        self._last = None
        proj = self.app.current_project

        # если курсов ещё нет — пробуем один раз подтянуть ЦБ автоматически
        if not self.db_manager.has_rates():
            self._auto_fetch_rates(silent=True)

        if not proj:
            for k in self.lbl:
                self.lbl[k].config(text="—", foreground="gray")
            self.lbl_split.config(text="")
            self.lbl_count.config(text="")
            return

        try:
            b = self.db_manager.get_project_budget(proj)
        except Exception as e:
            messagebox.showerror("Ошибка бюджета", str(e))
            return
        self._last = b

        # --- итоги ---
        for k, lab in self.lbl.items():
            val = b.get(k, 0.0)
            lab.config(text=self._fmt(val),
                       foreground="green" if (val or 0) >= 0 else "red")

        # --- разбивка закупок / совместимость со старым database.py ---
        if "plan_buy_specs" in b:
            orders = b.get("plan_buy_orders", 0.0)
            specs = b.get("plan_buy_specs", 0.0)
            n_spec = sum(1 for d in b.get("detail", []) if d[0] == "Закупка (спецификация)")
            self.lbl_split.config(
                foreground="#666",
                text=f"Закупки: заказы {self._num(orders)} ₽ + счета поставщиков "
                     f"{self._num(specs)} ₽ = {self._num(b.get('plan_buy', 0.0))} ₽   "
                     f"(строк по счетам: {n_spec})")
        else:
            self.lbl_split.config(
                foreground="red",
                text="⚠ database.py без поддержки счетов: обновите метод get_project_budget — "
                     "суммы из «Спецификации Закупок» пока не учитываются.")

        # --- расшифровка ---
        kinds = sorted({d[0] for d in b.get("detail", []) if d[0]})
        self.combo_kind["values"] = ["Все типы"] + kinds
        if self.combo_kind.get() not in self.combo_kind["values"]:
            self.combo_kind.set("Все типы")
        self._fill_detail()

        # --- курсы ---
        rates_txt = " · ".join(f"{c} {self.db_manager.get_rate(c):.4f}"
                               for c in ("USD", "EUR", "CNY", "TRY"))
        if self.db_manager.has_rates():
            self.lbl_rates.config(foreground="gray", text="Курсы: " + rates_txt)
        else:
            self.lbl_rates.config(
                foreground="red",
                text="⚠ Курсы не загружены (все валюты = 1). "
                     "Нажмите «Курсы ЦБ на сегодня» или «Курсы вручную».")

    def _fill_detail(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        b = self._last or {}
        rows = b.get("detail", [])
        kind_filter = self.combo_kind.get()
        hide_zero = self.hide_zero.get()
        shown = 0
        for kind, item, amount, cur, rub in rows:
            if kind_filter and kind_filter != "Все типы" and kind != kind_filter:
                continue
            if hide_zero and not (amount or rub):
                continue
            self.tree.insert("", tk.END, tags=(self._tag_for(kind),), values=(
                kind, item, self._num(amount), cur, self._num(rub)))
            shown += 1
        self.lbl_count.config(text=f"показано {shown} из {len(rows)}")

    # ==================================================================
    # Экспорт
    # ==================================================================
    def export(self):
        try:
            import openpyxl
            from openpyxl.styles import Font
        except ImportError:
            messagebox.showerror("Нет библиотеки", "pip install openpyxl")
            return
        if not self.app.current_project:
            messagebox.showwarning("Внимание", "Выберите проект!")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            initialfile=f"Бюджет_{self.app.current_project}.xlsx")
        if not path:
            return
        b = self._last or self.db_manager.get_project_budget(self.app.current_project)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Бюджет"
        bold = Font(bold=True)
        ws.append(["Проект", self.app.current_project])
        ws.append(["Дата", datetime.now().strftime("%d.%m.%Y %H:%M")])
        ws.append([])
        for k, title, _small in self.SUMMARY_KEYS:
            ws.append([title, round(b.get(k, 0.0), 2)])
        ws["A1"].font = bold
        ws.append([])
        ws.append(["Тип", "Позиция", "Сумма", "Валюта", "В рублях"])
        for cell in ws[ws.max_row]:
            cell.font = bold
        for row in b.get("detail", []):
            ws.append([row[0], row[1], round(row[2] or 0, 2), row[3], round(row[4] or 0, 2)])
        for col, width in (("A", 26), ("B", 52), ("C", 16), ("D", 10), ("E", 18)):
            ws.column_dimensions[col].width = width
        ws.freeze_panes = "A5"
        try:
            wb.save(path)
            messagebox.showinfo("Успех", f"Сохранено:\n{path}")
        except PermissionError:
            messagebox.showerror("Ошибка доступа",
                                 f"Файл открыт в другой программе или нет прав:\n{path}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))