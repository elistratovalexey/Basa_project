import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from config import CURRENCIES


class PaymentDialog(tk.Toplevel):
    def __init__(self, parent, title, number, payment_data=None,
                 contract_amount=None, contract_currency=None):
        super().__init__(parent)
        self.title(title)
        self.geometry("520x380")
        try:
            from dialogs.window_geometry import restore_geometry, track_geometry
            restore_geometry(self, "payment_dialog", "520x380")
            track_geometry(self, "payment_dialog")
        except Exception:
            pass
        self.resizable(False, False)
        self.result = None

        # Создаем все виджеты
        ttk.Label(self, text="№ платежа:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.entry_number = ttk.Entry(self, width=25)
        self.entry_number.grid(row=0, column=1, sticky="w", padx=10, pady=5)
        self.entry_number.insert(0, str(number))

        ttk.Label(self, text="Дата платежа:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.entry_date = ttk.Entry(self, width=20)
        self.entry_date.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        if payment_data and payment_data.get("date"):
            self.entry_date.insert(0, payment_data["date"])
        self.btn_cal = ttk.Button(self, text="📅", width=3, command=self.select_date)
        self.btn_cal.grid(row=1, column=2, padx=5, pady=5)

        ttk.Label(self, text="Сумма:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        self.entry_amount = ttk.Entry(self, width=25)
        self.entry_amount.grid(row=2, column=1, sticky="w", padx=10, pady=5)
        # НОВОЕ: авто-расчёт % от суммы договора при вводе суммы
        self.entry_amount.bind("<KeyRelease>", lambda e: self._auto_percent())

        ttk.Label(self, text="Валюта:").grid(row=3, column=0, sticky="w", padx=10, pady=5)
        self.combo_currency = ttk.Combobox(self, values=CURRENCIES, state="readonly", width=22)
        self.combo_currency.grid(row=3, column=1, sticky="w", padx=10, pady=5)
        self.combo_currency.set(CURRENCIES[0])

        # НОВОЕ: параметры договора, переданные вкладкой «Финансы»
        self.contract_amount = None
        if contract_amount not in (None, ""):
            try:
                self.contract_amount = float(str(contract_amount).replace(' ', '').replace(',', '.'))
            except (TypeError, ValueError):
                self.contract_amount = None
        self.contract_currency = contract_currency or ""
        if self.contract_currency and self.contract_currency in CURRENCIES:
            self.combo_currency.set(self.contract_currency)
        if self.contract_amount:
            ttk.Label(self,
                      text=f"Договор: {self.contract_amount:,.2f} {self.contract_currency}".replace(',', ' '),
                      foreground="#0066cc").grid(row=3, column=2, sticky="w", padx=10, pady=5)

        ttk.Label(self, text="Когда платят:").grid(row=4, column=0, sticky="w", padx=10, pady=5)
        self.entry_contract = ttk.Entry(self, width=25)
        self.entry_contract.grid(row=4, column=1, sticky="w", padx=10, pady=5)

        ttk.Label(self, text="% от суммы договора:").grid(row=5, column=0, sticky="w", padx=10, pady=5)
        self.entry_percent = ttk.Entry(self, width=25)
        self.entry_percent.grid(row=5, column=1, sticky="w", padx=10, pady=5)

        self.paid_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="Оплачено", variable=self.paid_var).grid(row=6, column=1, sticky="w", padx=10, pady=5)

        # Заполняем данные если есть
        if payment_data:
            self.entry_amount.delete(0, tk.END)
            self.entry_amount.insert(0, payment_data["amount"])
            self.combo_currency.set(payment_data["currency"])
            self.entry_contract.delete(0, tk.END)
            self.entry_contract.insert(0, payment_data["contract_date"])
            self.entry_percent.delete(0, tk.END)
            self.entry_percent.insert(0, payment_data.get("percent", ""))
            if payment_data.get("paid"):
                self.paid_var.set(True)
            # НОВОЕ: процента нет, но сумма договора известна — досчитываем
            if self.contract_amount and not payment_data.get("percent"):
                try:
                    amt = float(str(payment_data.get("amount", 0)).replace(' ', '').replace(',', '.'))
                    if amt:
                        self.entry_percent.delete(0, tk.END)
                        self.entry_percent.insert(0, f"{amt / self.contract_amount * 100:.2f}")
                except (TypeError, ValueError):
                    pass

        # Кнопки
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=7, column=0, columnspan=3, pady=15)
        ttk.Button(btn_frame, text="Сохранить", command=self.save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self.destroy).pack(side=tk.LEFT, padx=5)
        self.grab_set()

    def _auto_percent(self):
        """НОВОЕ: автоматический расчёт % от суммы договора при вводе суммы."""
        if not self.contract_amount:
            return
        try:
            amount = float(self.entry_amount.get().replace(' ', '').replace(',', '.'))
        except (TypeError, ValueError):
            return
        percent = amount / self.contract_amount * 100
        self.entry_percent.delete(0, tk.END)
        self.entry_percent.insert(0, f"{percent:.2f}")

    def select_date(self):
        from dialogs.calendar_dialog import CalendarDialog
        current = self.entry_date.get()
        dialog = CalendarDialog(self, current if current else None)
        self.wait_window(dialog)
        if dialog.result:
            self.entry_date.delete(0, tk.END)
            self.entry_date.insert(0, dialog.result)

    def save(self):
        date_val = self.entry_date.get().strip()
        amount_val = self.entry_amount.get().strip()
        if not amount_val:
            messagebox.showwarning("Ошибка", "Введите сумму!")
            return
        try:
            float(amount_val.replace(" ", "").replace(",", "."))
        except:
            messagebox.showwarning("Ошибка", "Некорректная сумма!")
            return
        self.result = {
            "number": self.entry_number.get(),
            "date": date_val,
            "amount": amount_val,
            "currency": self.combo_currency.get(),
            "contract_date": self.entry_contract.get(),
            "percent": self.entry_percent.get().strip(),
            "paid": 1 if self.paid_var.get() else 0
        }
        self.destroy()