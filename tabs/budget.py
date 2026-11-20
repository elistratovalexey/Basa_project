# -*- coding: utf-8 -*-
"""Вкладка «Бюджет»: план / закупки / оплаты клиентом и поставщикам / баланс.

Расходы по строкам из «Заказов» умножаются на коэффициент проекта (по умолчанию 1.8).
Счета поставщиков из «Спецификации Закупок» берутся без коэффициента.
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

from tabs.base import BaseTab


class BudgetTab(BaseTab):
    SUMMARY_KEYS = [
        ("plan_sell", "План продажи", False),
        ("income", "Оплачено Клиентом", False),
        ("paid_sup", "Оплачено Поставщикам", False),
        ("balance", "Баланс (клиент − поставщики)", False),
        ("plan_buy", "Закупки (план, всего)", False),
        ("plan_buy_orders", "в т.ч. заказы × коэф.", True),
        ("plan_buy_specs", "в т.ч. счета поставщиков", True),
        ("orders_markup", "надбавка по коэф.", True),
        ("received", "Получено (закупки)", False),
        ("plan_margin", "Маржа план", False),
        ("margin", "Маржа факт", False),
    ]

    def __init__(self, app, parent):
        super().__init__(app, parent)
        self._last = None
        self.create_ui()

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

        # --- коэффициент проекта ---
        cf = ttk.LabelFrame(self.parent, text="Коэффициент расходов на заказы (для этого проекта)", padding=6)
        cf.pack(fill="x", pady=3)
        ttk.Label(cf, text="Множитель:").pack(side=tk.LEFT, padx=(4, 4))
        self.entry_coef = ttk.Entry(cf, width=8)
        self.entry_coef.pack(side=tk.LEFT)
        self.entry_coef.insert(0, "1.8")
        ttk.Button(cf, text="Сохранить и пересчитать", command=self.save_coef).pack(side=tk.LEFT, padx=8)
        ttk.Label(cf, foreground="gray",
                  text="Применяется только к строкам из «Заказы». Счета поставщиков — без множителя."
                  ).pack(side=tk.LEFT, padx=8)

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

        flt = ttk.Frame(self.parent)
        flt.pack(fill="x", pady=(2, 0))
        ttk.Label(flt, text="Тип строки:").pack(side=tk.LEFT, padx=(14, 4))
        self.combo_kind = ttk.Combobox(flt, width=26, state="readonly", values=["Все типы"])
        self.combo_kind.set("Все типы")
        self.combo_kind.pack(side=tk.LEFT)
        self.combo_kind.bind("<<ComboboxSelected>>", lambda e: self._fill_detail())
        self.hide_zero = tk.BooleanVar(value=True)
        ttk.Checkbutton(flt, text="Скрывать нулевые", variable=self.hide_zero,
                        command=self._fill_detail).pack(side=tk.LEFT, padx=12)
        self.show_total_row = tk.BooleanVar(value=True)
        ttk.Checkbutton(flt, text="Итоговая строка", variable=self.show_total_row,
                        command=self._fill_detail).pack(side=tk.LEFT, padx=6)
        self.lbl_count = ttk.Label(flt, text="", foreground="gray")
        self.lbl_count.pack(side=tk.LEFT, padx=8)

        det = ttk.LabelFrame(self.parent, text="Расшифровка", padding=6)
        det.pack(fill="both", expand=True, pady=5)
        cols = ("kind", "item", "amount", "cur", "rub", "paid_client", "paid_sup")
        self.tree = ttk.Treeview(det, columns=cols, show="headings", height=15)
        for c, t, w in (("kind", "Тип", 175), ("item", "Позиция", 300),
                        ("amount", "Сумма", 110), ("cur", "Валюта", 60),
                        ("rub", "В рублях", 120),
                        ("paid_client", "Оплачено Клиентом", 135),
                        ("paid_sup", "Оплачено Поставщикам", 150)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w" if c in ("kind", "item") else "e")
        sb = ttk.Scrollbar(det, orient=tk.VERTICAL, command=self.tree.yview)
        hs = ttk.Scrollbar(det, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscroll=sb.set, xscroll=hs.set)
        self.tree.pack(side=tk.LEFT, fill="both", expand=True)
        sb.pack(side=tk.RIGHT, fill="y")
        hs.pack(side=tk.BOTTOM, fill="x")

        self.tree.tag_configure("sell", foreground="#0a58ca")
        self.tree.tag_configure("income", foreground="#198754")
        self.tree.tag_configure("order", foreground="#333333")
        self.tree.tag_configure("spec", background="#fff3cd")
        self.tree.tag_configure("paysup", foreground="#b02a37")
        self.tree.tag_configure("total", background="#d0e0f0", font=("Arial", 9, "bold"))

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
    def save_coef(self):
        proj = self.app.current_project
        if not proj:
            messagebox.showwarning("Внимание", "Выберите проект!")
            return
        try:
            v = float(self.entry_coef.get().replace(",", "."))
            if v <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Ошибка", "Коэффициент — положительное число, например 1.8")
            return
        if not hasattr(self.db_manager, "set_orders_cost_coef"):
            messagebox.showerror("Ошибка", "Обновите database.py: нет set_orders_cost_coef")
            return
        if self.db_manager.set_orders_cost_coef(proj, v):
            self.app.log_action(f"Бюджет: коэффициент расходов на заказы для «{proj}» = {v:g}")
            self.load_budget()
        else:
            messagebox.showerror("Ошибка", "Не удалось сохранить коэффициент")

    def _load_coef_into_entry(self, proj):
        try:
            v = self.db_manager.get_orders_cost_coef(proj) if hasattr(
                self.db_manager, "get_orders_cost_coef") else 1.8
        except Exception:
            v = 1.8
        self.entry_coef.delete(0, tk.END)
        self.entry_coef.insert(0, f"{v:g}")

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
    def load_budget(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        self._last = None
        proj = self.app.current_project

        if not self.db_manager.has_rates():
            self._auto_fetch_rates(silent=True)

        if not proj:
            for k in self.lbl:
                self.lbl[k].config(text="—", foreground="gray")
            self.lbl_split.config(text="")
            self.lbl_count.config(text="")
            return

        self._load_coef_into_entry(proj)
        try:
            b = self.db_manager.get_project_budget(proj)
        except Exception as e:
            messagebox.showerror("Ошибка бюджета", str(e))
            return
        self._last = b

        for k, lab in self.lbl.items():
            val = b.get(k, 0.0)
            lab.config(text=self._fmt(val),
                       foreground="green" if (val or 0) >= 0 else "red")

        coef = b.get("coef", 1.8)
        if "plan_buy_specs" in b:
            self.lbl_split.config(
                foreground="#666",
                text=f"Закупки: заказы {self._num(b.get('orders_base', 0))} ₽ × {coef:g} = "
                     f"{self._num(b.get('plan_buy_orders', 0))} ₽  +  счета поставщиков "
                     f"{self._num(b.get('plan_buy_specs', 0))} ₽  =  "
                     f"{self._num(b.get('plan_buy', 0))} ₽   |   "
                     f"Баланс оплат: {self._num(b.get('balance', 0))} ₽")
        else:
            unmarked = b.get("paid_sup_unmarked", 0.0)
            extra = ""
            if unmarked > 0:
                extra = (f"\n⚠ Оплаты без галочки «Оплачен»: {self._num(unmarked)} ₽ — "
                         f"учтены в бюджете, но отметьте их в карточках счетов.")
            self.lbl_split.config(
                foreground="#666" if not unmarked else "#b02a37",
                text=f"Закупки: заказы {self._num(b.get('orders_base', 0))} ₽ × {coef:g} = "
                     f"{self._num(b.get('plan_buy_orders', 0))} ₽  +  счета поставщиков "
                     f"{self._num(b.get('plan_buy_specs', 0))} ₽  =  "
                     f"{self._num(b.get('plan_buy', 0))} ₽   |   "
                     f"Баланс оплат: {self._num(b.get('balance', 0))} ₽" + extra)            

        kinds = sorted({d[0] for d in b.get("detail", []) if d[0]})
        self.combo_kind["values"] = ["Все типы"] + kinds
        if self.combo_kind.get() not in self.combo_kind["values"]:
            self.combo_kind.set("Все типы")
        self._fill_detail()

        rates_txt = " · ".join(f"{c} {self.db_manager.get_rate(c):.4f}"
                               for c in ("USD", "EUR", "CNY", "TRY"))
        if self.db_manager.has_rates():
            self.lbl_rates.config(foreground="gray", text="Курсы: " + rates_txt)
        else:
            self.lbl_rates.config(foreground="red",
                                  text="⚠ Курсы не загружены (все валюты = 1).")

    def _fill_detail(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        b = self._last or {}
        rows = b.get("detail", [])
        kind_filter = self.combo_kind.get()
        hide_zero = self.hide_zero.get()
        shown = sum_client = sum_sup = 0.0
        shown = 0
        for kind, item, amount, cur, rub in rows:
            if kind_filter and kind_filter != "Все типы" and kind != kind_filter:
                continue
            if hide_zero and not (amount or rub):
                continue
            pc = rub if kind == "Оплата заказчика" else 0.0
            ps = rub if kind == "Оплата поставщику" else 0.0
            sum_client += pc
            sum_sup += ps
            self.tree.insert("", tk.END, tags=(self._tag_for(kind),), values=(
                kind, item, self._num(amount), cur, self._num(rub),
                self._num(pc) if pc else "", self._num(ps) if ps else ""))
            shown += 1
        if self.show_total_row.get() and shown:
            bal = sum_client - sum_sup
            self.tree.insert("", tk.END, tags=("total",), values=(
                "ИТОГО", f"Баланс: {self._num(bal)} ₽", "", "", "",
                self._num(sum_client), self._num(sum_sup)))
        self.lbl_count.config(text=f"показано {shown} из {len(rows)}")

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
        ws.append(["Коэффициент расходов на заказы", b.get("coef", 1.8)])
        ws.append([])
        for k, title, _s in self.SUMMARY_KEYS:
            ws.append([title, round(b.get(k, 0.0), 2)])
        ws["A1"].font = bold
        ws.append([])
        ws.append(["Тип", "Позиция", "Сумма", "Валюта", "В рублях",
                   "Оплачено Клиентом", "Оплачено Поставщикам"])
        for cell in ws[ws.max_row]:
            cell.font = bold
        tc = ts = 0.0
        for kind, item, amount, cur, rub in b.get("detail", []):
            pc = rub if kind == "Оплата заказчика" else 0.0
            ps = rub if kind == "Оплата поставщику" else 0.0
            tc += pc
            ts += ps
            ws.append([kind, item, round(amount or 0, 2), cur, round(rub or 0, 2),
                       round(pc, 2) if pc else "", round(ps, 2) if ps else ""])
        ws.append(["ИТОГО", f"Баланс: {round(tc - ts, 2)}", "", "", "", round(tc, 2), round(ts, 2)])
        for cell in ws[ws.max_row]:
            cell.font = bold
        for col, width in (("A", 26), ("B", 50), ("C", 16), ("D", 10),
                           ("E", 18), ("F", 20), ("G", 22)):
            ws.column_dimensions[col].width = width
        ws.freeze_panes = "A6"
        try:
            wb.save(path)
            messagebox.showinfo("Успех", f"Сохранено:\n{path}")
        except PermissionError:
            messagebox.showerror("Ошибка доступа",
                                 f"Файл открыт в другой программе или нет прав:\n{path}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))