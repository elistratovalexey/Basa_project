import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

try:
    from config import CURRENCIES
except ImportError:
    CURRENCIES = ["RUB", "USD", "EUR", "CNY", "TRY"]


class PaymentDialog(tk.Toplevel):
    def __init__(self, parent, title, number, payment_data=None,
                 contract_amount=None, contract_currency=None):
        super().__init__(parent)
        self.title(title)
        self.geometry("520x420")
        self.resizable(False, False)
        self.result = None

        # Сохраняем параметры договора для авто-расчёта %
        self.contract_amount = self._parse_amount(contract_amount)
        self.contract_currency = contract_currency or ""

        # === Виджеты ===
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
        self.entry_amount.bind("<KeyRelease>", self._on_amount_change)

        ttk.Label(self, text="Валюта:").grid(row=3, column=0, sticky="w", padx=10, pady=5)
        self.combo_currency = ttk.Combobox(self, values=CURRENCIES, state="readonly", width=22)
        self.combo_currency.grid(row=3, column=1, sticky="w", padx=10, pady=5)
        # НОВОЕ: если передана валюта договора — ставим её по умолчанию
        if self.contract_currency and self.contract_currency in CURRENCIES:
            self.combo_currency.set(self.contract_currency)
        else:
            self.combo_currency.set(CURRENCIES[0])

        # НОВОЕ: подсказка о сумме договора
        if self.contract_amount:
            self.lbl_contract = ttk.Label(
                self,
                text=f"Договор: {self.contract_amount:,.2f} {self.contract_currency}".replace(",", " "),
                foreground="#0066cc")
            self.lbl_contract.grid(row=3, column=2, sticky="w", padx=5)

        ttk.Label(self, text="Когда платят:").grid(row=4, column=0, sticky="w", padx=10, pady=5)
        self.entry_contract = ttk.Entry(self, width=25)
        self.entry_contract.grid(row=4, column=1, sticky="w", padx=10, pady=5)

        ttk.Label(self, text="% от суммы договора:").grid(row=5, column=0, sticky="w", padx=10, pady=5)
        self.entry_percent = ttk.Entry(self, width=25)
        self.entry_percent.grid(row=5, column=1, sticky="w", padx=10, pady=5)

        self.paid_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="Оплачено", variable=self.paid_var).grid(
            row=6, column=1, sticky="w", padx=10, pady=5)

        # Заполняем данные если есть
        if payment_data:
            self.entry_amount.delete(0, tk.END)
            self.entry_amount.insert(0, payment_data.get("amount", ""))
            if payment_data.get("currency"):
                self.combo_currency.set(payment_data["currency"])
            self.entry_contract.delete(0, tk.END)
            self.entry_contract.insert(0, payment_data.get("contract_date", ""))
            self.entry_percent.delete(0, tk.END)
            self.entry_percent.insert(0, payment_data.get("percent", ""))
            if payment_data.get("paid"):
                self.paid_var.set(True)
            # НОВОЕ: если % не указан, но есть сумма договора — досчитываем
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

        # НОВОЕ: безопасный grab_set (избавляет от "grab failed: window not viewable")
        self._safe_grab()

    # ---------- Вспомогательные методы ----------
    @staticmethod
    def _parse_amount(value):
        """Превращает строку/число в float или None."""
        if value in (None, ""):
            return None
        try:
            return float(str(value).replace(' ', '').replace(',', '.'))
        except (TypeError, ValueError):
            return None

    def _on_amount_change(self, event=None):
        """Авто-расчёт % от суммы договора при вводе суммы."""
        if not self.contract_amount:
            return
        amount = self._parse_amount(self.entry_amount.get())
        if amount is None:
            return
        percent = amount / self.contract_amount * 100
        self.entry_percent.delete(0, tk.END)
        self.entry_percent.insert(0, f"{percent:.2f}")

    def _safe_grab(self, attempts=10):
        """grab_set только после того, как окно реально отрисовано."""
        try:
            if self.winfo_exists() and self.winfo_viewable():
                self.grab_set()
            elif attempts > 0:
                self.after(50, lambda: self._safe_grab(attempts - 1))
        except tk.TclError:
            if attempts > 0:
                self.after(50, lambda: self._safe_grab(attempts - 1))

    def select_date(self):
        try:
            from dialogs.calendar_dialog import CalendarDialog
            current = self.entry_date.get()
            dialog = CalendarDialog(self, current if current else None)
            self.wait_window(dialog)
            if dialog.result:
                self.entry_date.delete(0, tk.END)
                self.entry_date.insert(0, dialog.result)
        except ImportError:
            self.entry_date.delete(0, tk.END)
            self.entry_date.insert(0, datetime.now().strftime("%d.%m.%Y"))

    def save(self):
        date_val = self.entry_date.get().strip()
        amount_val = self.entry_amount.get().strip()
        if not amount_val:
            messagebox.showwarning("Ошибка", "Введите сумму!")
            return
        try:
            float(amount_val.replace(" ", "").replace(",", "."))
        except ValueError:
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