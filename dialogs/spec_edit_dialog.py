# -*- coding: utf-8 -*-
"""Редактирование счёта (спецификации закупки): все основные поля + переход к оплатам."""
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

try:
    from config import CURRENCIES
except ImportError:
    CURRENCIES = ["RUB", "USD", "EUR", "CNY", "TRY"]

try:
    from utils import parse_number
except ImportError:
    def parse_number(s):
        try:
            return float(str(s).replace(" ", "").replace(",", "."))
        except Exception:
            return None


class SpecEditDialog(tk.Toplevel):
    def __init__(self, parent, db_manager, spec_id, on_saved=None):
        super().__init__(parent)
        self.db = db_manager
        self.spec_id = spec_id
        self.on_saved = on_saved
        row = self.db.get_purchase_spec_by_id(spec_id)
        if row is None:
            messagebox.showerror("Ошибка", f"Спецификация №{spec_id} не найдена")
            self.destroy()
            return
        self.row = dict(row)
        self.title(f"Счёт №{spec_id}: {self.row.get('supplier', '')}")
        self.geometry("780x600")
        self.resizable(False, False)

        m = ttk.Frame(self, padding=10)
        m.pack(fill="both", expand=True)
        m.columnconfigure(1, weight=1)
        m.columnconfigure(3, weight=1)
        r = 0

        ttk.Label(m, text="Поставщик:").grid(row=r, column=0, sticky="w", pady=4)
        self.combo_supplier = ttk.Combobox(m, width=40)
        self.combo_supplier.grid(row=r, column=1, columnspan=3, sticky="ew", pady=4)
        try:
            self.combo_supplier['values'] = [s['name'] for s in self.db.get_suppliers()]
        except Exception:
            pass
        self.combo_supplier.set(self.row.get('supplier') or "")
        r += 1

        ttk.Label(m, text="Наименование:").grid(row=r, column=0, sticky="w", pady=4)
        self.entry_name = ttk.Entry(m, width=50)
        self.entry_name.grid(row=r, column=1, columnspan=3, sticky="ew", pady=4)
        self.entry_name.insert(0, self.row.get('name') or "")
        r += 1

        ttk.Label(m, text="Кол-во:").grid(row=r, column=0, sticky="w", pady=4)
        self.entry_qty = ttk.Entry(m, width=12)
        self.entry_qty.grid(row=r, column=1, sticky="w", pady=4)
        self.entry_qty.insert(0, str(self.row.get('quantity') or 0))
        ttk.Label(m, text="Цена:").grid(row=r, column=2, sticky="w", padx=(12, 0), pady=4)
        self.entry_price = ttk.Entry(m, width=14)
        self.entry_price.grid(row=r, column=3, sticky="w", pady=4)
        self.entry_price.insert(0, str(self.row.get('price') or 0))
        r += 1

        ttk.Label(m, text="Сумма:").grid(row=r, column=0, sticky="w", pady=4)
        self.entry_total = ttk.Entry(m, width=14)
        self.entry_total.grid(row=r, column=1, sticky="w", pady=4)
        self.entry_total.insert(0, str(self.row.get('total') or 0))
        ttk.Button(m, text="= Кол-во × Цена", command=self.calc_total).grid(row=r, column=2, sticky="w", padx=6)
        self.combo_currency = ttk.Combobox(m, values=CURRENCIES, state="readonly", width=16)
        self.combo_currency.grid(row=r, column=3, sticky="w", pady=4)
        cur = self.row.get('currency') or ""
        self.combo_currency.set(cur if cur in CURRENCIES else (CURRENCIES[0] if not cur else cur))
        r += 1

        ttk.Label(m, text="Срок поставки:").grid(row=r, column=0, sticky="w", pady=4)
        self.entry_term = ttk.Entry(m, width=12)
        self.entry_term.grid(row=r, column=1, sticky="w", pady=4)
        self.entry_term.insert(0, str(self.row.get('delivery_term') or 0))
        ttk.Label(m, text="Ед. срока:").grid(row=r, column=2, sticky="w", padx=(12, 0), pady=4)
        self.combo_unit = ttk.Combobox(m, values=["Календарные дни", "Рабочие дни", "Недели", "Месяцы"],
                                       state="readonly", width=16)
        self.combo_unit.grid(row=r, column=3, sticky="w", pady=4)
        unit = self.row.get('delivery_unit') or ""
        self.combo_unit.set(unit if unit else "Календарные дни")
        r += 1

        ttk.Label(m, text="Дата оплаты:").grid(row=r, column=0, sticky="w", pady=4)
        self.entry_pay_date = ttk.Entry(m, width=12)
        self.entry_pay_date.grid(row=r, column=1, sticky="w", pady=4)
        self.entry_pay_date.insert(0, self.row.get('payment_date') or "")
        ttk.Button(m, text="📅", width=3,
                   command=lambda: self.pick(self.entry_pay_date)).grid(row=r, column=2, sticky="w", padx=6)
        r += 1

        ttk.Label(m, text="Дата поставки:").grid(row=r, column=0, sticky="w", pady=4)
        self.entry_del_date = ttk.Entry(m, width=12)
        self.entry_del_date.grid(row=r, column=1, sticky="w", pady=4)
        self.entry_del_date.insert(0, self.row.get('delivery_date') or "")
        ttk.Button(m, text="📅", width=3,
                   command=lambda: self.pick(self.entry_del_date)).grid(row=r, column=2, sticky="w", padx=6)
        r += 1

        ttk.Label(m, text="Адрес доставки:").grid(row=r, column=0, sticky="w", pady=4)
        self.combo_addr = ttk.Combobox(m, width=40)
        self.combo_addr.grid(row=r, column=1, columnspan=3, sticky="ew", pady=4)
        try:
            self.combo_addr['values'] = [a['name'] for a in self.db.get_delivery_addresses()]
        except Exception:
            pass
        self.combo_addr.set(self.row.get('delivery_address') or "")
        r += 1

        ttk.Label(m, text="Примечание:").grid(row=r, column=0, sticky="nw", pady=4)
        self.entry_note = ttk.Entry(m, width=50)
        self.entry_note.grid(row=r, column=1, columnspan=3, sticky="ew", pady=4)
        self.entry_note.insert(0, self.row.get('note') or "")
        r += 1

        self.fully_paid_var = tk.BooleanVar(value=bool(self.row.get('fully_paid', 0)))
        self.received_var = tk.BooleanVar(value=bool(self.row.get('received', 0)))
        chk = ttk.Frame(m)
        chk.grid(row=r, column=0, columnspan=4, sticky="w", pady=6)
        ttk.Checkbutton(chk, text="Полностью оплачен", variable=self.fully_paid_var).pack(side=tk.LEFT, padx=(0, 20))
        ttk.Checkbutton(chk, text="Получен", variable=self.received_var).pack(side=tk.LEFT)
        r += 1

        bf = ttk.Frame(m)
        bf.grid(row=r, column=0, columnspan=4, pady=10)
        ttk.Button(bf, text="Сохранить", command=self.save).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text="Оплаты…", command=self.open_payments).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text="Отмена", command=self.destroy).pack(side=tk.LEFT, padx=5)

        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def pick(self, entry):
        try:
            from dialogs.calendar_dialog import CalendarDialog
            d = CalendarDialog(self, entry.get() or None)
            self.wait_window(d)
            if d.result:
                entry.delete(0, tk.END)
                entry.insert(0, d.result)
        except Exception:
            entry.delete(0, tk.END)
            entry.insert(0, datetime.now().strftime("%d.%m.%Y"))

    def calc_total(self):
        q = parse_number(self.entry_qty.get()) or 0
        p = parse_number(self.entry_price.get()) or 0
        self.entry_total.delete(0, tk.END)
        self.entry_total.insert(0, f"{q * p:.2f}")

    def open_payments(self):
        try:
            from dialogs.payment_schedule_dialog import PaymentScheduleDialog
        except ImportError:
            messagebox.showerror("Ошибка", "dialogs/payment_schedule_dialog.py не найден")
            return
        total = parse_number(self.entry_total.get()) or 0
        PaymentScheduleDialog(self, self.db, self.spec_id, total)

    def save(self):
        data = {
            "supplier": self.combo_supplier.get().strip(),
            "name": self.entry_name.get().strip(),
            "quantity": parse_number(self.entry_qty.get()) or 0,
            "price": parse_number(self.entry_price.get()) or 0,
            "total": parse_number(self.entry_total.get()) or 0,
            "currency": self.combo_currency.get(),
            "delivery_term": parse_number(self.entry_term.get()) or 0,
            "delivery_unit": self.combo_unit.get(),
            "payment_date": self.entry_pay_date.get().strip(),
            "delivery_date": self.entry_del_date.get().strip(),
            "fully_paid": 1 if self.fully_paid_var.get() else 0,
            "received": 1 if self.received_var.get() else 0,
            "delivery_address": self.combo_addr.get().strip(),
            "note": self.entry_note.get().strip(),
        }
        try:
            self.db.update_purchase_spec(self.spec_id, data)
        except Exception as e:
            messagebox.showerror("Ошибка БД", f"Не удалось сохранить счёт:\n{e}")
            return
        if self.on_saved:
            try:
                self.on_saved()
            except Exception:
                pass
        messagebox.showinfo("Успех", f"Счёт №{self.spec_id} обновлён")
        self.destroy()