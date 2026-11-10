import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from tabs.base import BaseTab
from dialogs.calendar_dialog import CalendarDialog
from dialogs.payment_dialog import PaymentDialog
from config import CURRENCIES
from utils import parse_number_or_zero, format_money


class FinancesTab(BaseTab):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        self.create_ui()

    def create_ui(self):
        frame_fin = ttk.LabelFrame(self.parent, text="Договор", padding=10)
        frame_fin.pack(fill="x", pady=5)
        
        self.app.entry_contract_date = self._create_date_entry(frame_fin, "Дата договора:", 0)
        
        ttk.Label(frame_fin, text="Сумма:").grid(row=0, column=2, sticky="w", padx=20)
        self.app.entry_contract_amount = ttk.Entry(frame_fin, width=15)
        self.app.entry_contract_amount.grid(row=0, column=3, sticky="w")
        
        self.app.combo_contract_currency = ttk.Combobox(
            frame_fin, values=CURRENCIES, state="readonly", width=14)
        self.app.combo_contract_currency.grid(row=0, column=4, sticky="w", padx=5)
        
        # Пересчёт сроков при ручном вводе даты договора
        self.app.entry_contract_date.bind("<KeyRelease>", 
                                          lambda e: self.app.calculate_dates())
        self.app.entry_contract_date.bind("<FocusOut>", 
                                          lambda e: self.app.calculate_dates())

        frame_payments = ttk.LabelFrame(self.parent, text="Платежи", padding=10)
        frame_payments.pack(fill="both", expand=True, pady=5)
        
        columns = ("number", "date", "amount", "currency", "percent", "paid", "contract_date")
        self.app.payment_tree = ttk.Treeview(
            frame_payments, columns=columns, show="headings", height=6)
        
        self.app.payment_tree.heading("number", text="№")
        self.app.payment_tree.heading("date", text="Дата")
        self.app.payment_tree.heading("amount", text="Сумма")
        self.app.payment_tree.heading("currency", text="Валюта")
        self.app.payment_tree.heading("percent", text="%")
        self.app.payment_tree.heading("paid", text="Оплачено")
        self.app.payment_tree.heading("contract_date", text="Когда")
        
        self.app.payment_tree.column("number", width=40, anchor="center")
        self.app.payment_tree.column("date", width=80, anchor="center")
        self.app.payment_tree.column("amount", width=90, anchor="e")
        self.app.payment_tree.column("currency", width=80, anchor="center")
        self.app.payment_tree.column("percent", width=50, anchor="center")
        self.app.payment_tree.column("paid", width=60, anchor="center")
        self.app.payment_tree.column("contract_date", width=100, anchor="w")
        
        scrollbar = ttk.Scrollbar(
            frame_payments, orient=tk.VERTICAL, command=self.app.payment_tree.yview)
        self.app.payment_tree.configure(yscroll=scrollbar.set)
        self.app.payment_tree.pack(side=tk.LEFT, fill="both", expand=True)
        scrollbar.pack(side=tk.RIGHT, fill="y")
        
        btn_frame = ttk.Frame(frame_payments)
        btn_frame.pack(pady=5)
        ttk.Button(btn_frame, text="Добавить", command=self.add_payment).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Редактировать", command=self.edit_payment).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Удалить", command=self.delete_payment).pack(side=tk.LEFT, padx=5)
        
        self.app.payment_tree.bind("<Double-1>", lambda e: self.edit_payment())
        
        self.app.lbl_payment_totals = ttk.Label(
            frame_payments, text="Итого: нет платежей",
            font=("Arial", 10, "bold"), foreground="darkblue")
        self.app.lbl_payment_totals.pack(pady=5)

    def _create_date_entry(self, parent, text, row):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Label(frame, text=text).pack(side=tk.LEFT, padx=(0, 5))
        entry = ttk.Entry(frame, width=15)
        entry.pack(side=tk.LEFT, padx=(0, 5))
        btn = ttk.Button(frame, text="📅", width=3, 
                        command=lambda: self._select_date(entry))
        btn.pack(side=tk.LEFT)
        return entry

    def _select_date(self, entry):
        current = entry.get()
        dialog = CalendarDialog(self.root, current if current else None)
        self.root.wait_window(dialog)
        if dialog.result:
            entry.delete(0, tk.END)
            entry.insert(0, dialog.result)
            self.app.calculate_dates()

    # === Методы работы с платежами ===
    
    def add_payment(self):
        if not self.app.current_project:
            messagebox.showwarning("Внимание", "Выберите проект!")
            return
        
        contract_amount_str = self.app.entry_contract_amount.get().strip()
        contract_currency = self.app.combo_contract_currency.get()
        contract_amount = parse_number_or_zero(contract_amount_str)
        
        dialog = PaymentDialog(
            self.root, "Добавить", self.app.payment_counter,
            contract_amount=contract_amount,
            contract_currency=contract_currency
        )
        self.root.wait_window(dialog)
        
        if dialog.result:
            payment = dialog.result
            project_id = self.db_manager.get_project_id(self.app.current_project)
            if project_id:
                self.db_manager.add_payment(project_id, payment)
                self.load_payments()
                self.app.payment_counter += 1
                self.app.log_action(f"Платеж №{payment['number']} добавлен")
                if self.app.del_base_var.get() == "От даты первого платежа":
                    self.app.calculate_dates()

    def edit_payment(self):
        selected = self.app.payment_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите платеж!")
            return
        
        item = self.app.payment_tree.item(selected[0])
        values = item["values"]
        
        contract_amount_str = self.app.entry_contract_amount.get().strip()
        contract_currency = self.app.combo_contract_currency.get()
        contract_amount = parse_number_or_zero(contract_amount_str)
        
        # ИСПРАВЛЕНО: явная проверка значения "paid"
        paid_value = values[5]
        is_paid = (paid_value == "✓") if paid_value else False
        
        dialog = PaymentDialog(
            self.root, "Редактировать", values[0], {
                "date": values[1], 
                "amount": values[2], 
                "currency": values[3],
                "contract_date": values[6], 
                "percent": values[4], 
                "paid": is_paid
            }, 
            contract_amount=contract_amount, 
            contract_currency=contract_currency
        )
        self.root.wait_window(dialog)
        
        if dialog.result:
            project_id = self.db_manager.get_project_id(self.app.current_project)
            if project_id:
                self.db_manager.update_payment(project_id, values[0], dialog.result)
                self.load_payments()
                if self.app.del_base_var.get() == "От даты первого платежа":
                    self.app.calculate_dates()

    def delete_payment(self):
        selected = self.app.payment_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите платеж!")
            return
        
        number = self.app.payment_tree.item(selected[0])["values"][0]
        
        if messagebox.askyesno("Подтверждение", f"Удалить №{number}?"):
            project_id = self.db_manager.get_project_id(self.app.current_project)
            if project_id:
                self.db_manager.delete_payment(project_id, number)
                self.load_payments()
                if self.app.del_base_var.get() == "От даты первого платежа":
                    self.app.calculate_dates()

    def load_payments(self):
        for item in self.app.payment_tree.get_children():
            self.app.payment_tree.delete(item)
        
        if not self.app.current_project:
            self.update_payment_totals()
            return
        
        project_id = self.db_manager.get_project_id(self.app.current_project)
        if not project_id:
            self.update_payment_totals()
            return
        
        payments = self.db_manager.get_payments(project_id)
        
        for p in payments:
            paid_mark = "✓" if p["paid"] else ""
            self.app.payment_tree.insert("", tk.END, values=(
                p["number"], 
                p["date"] or "", 
                p["amount"] or "", 
                p["currency"] or "",
                p["percent"] or "", 
                paid_mark, 
                p["contract_date"] or ""
            ))
        
        self.app.payment_counter = self.db_manager.get_next_number("payments", project_id)
        self.update_payment_totals()

    def update_payment_totals(self):
        # ИСПРАВЛЕНО: проверка существования виджета
        if not hasattr(self.app, 'lbl_payment_totals'):
            return
        
        if not self.app.current_project:
            self.app.lbl_payment_totals.config(text="Итого: нет платежей")
            return
        
        project_id = self.db_manager.get_project_id(self.app.current_project)
        if not project_id:
            self.app.lbl_payment_totals.config(text="Итого: нет платежей")
            return
        
        payments = self.db_manager.get_payments(project_id)
        
        totals = {}
        for p in payments:
            currency = p["currency"] or "Не указана"
            amount = parse_number_or_zero(p["amount"])
            if currency not in totals:
                totals[currency] = 0
            totals[currency] += amount
        
        if not totals:
            self.app.lbl_payment_totals.config(text="Итого: нет платежей")
            return
        
        parts = []
        for currency, total in totals.items():
            formatted = format_money(total)
            parts.append(f"{formatted} {currency}")
        
        totals_str = "Итого: " + " | ".join(parts)
        self.app.lbl_payment_totals.config(text=totals_str)