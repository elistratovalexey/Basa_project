import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta
from tabs.base import BaseTab
from dialogs.calendar_dialog import CalendarDialog
from utils import add_months, parse_date as _parse_date


class DeadlinesTab(BaseTab):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        self.create_ui()

    def create_ui(self):
        frame_del = ttk.LabelFrame(self.parent, text="Поставка", padding=10)
        frame_del.pack(fill="x", pady=5)
        ttk.Label(frame_del, text="Считать от:").grid(row=0, column=0, sticky="w", pady=5)
        self.app.del_base_var = tk.StringVar(value="От даты договора")
        radio_frame = ttk.Frame(frame_del)
        radio_frame.grid(row=0, column=1, columnspan=4, sticky="w", pady=5)
        ttk.Radiobutton(radio_frame, text="Даты договора",
                       variable=self.app.del_base_var, value="От даты договора",
                       command=self.calculate_dates).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(radio_frame, text="Даты первого платежа",
                       variable=self.app.del_base_var, value="От даты первого платежа",
                       command=self.calculate_dates).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(radio_frame, text="Даты подтверждения",
                       variable=self.app.del_base_var, value="От даты подтверждения",
                       command=self.calculate_dates).pack(side=tk.LEFT, padx=5)
        ttk.Label(frame_del, text="Срок:").grid(row=1, column=0, sticky="w")
        self.app.entry_del_term = ttk.Entry(frame_del, width=10)
        self.app.entry_del_term.grid(row=1, column=1, sticky="w", padx=5)
        self.app.combo_del_unit = ttk.Combobox(frame_del, values=["Календарные дни", "Рабочие дни", "Недели", "Месяцы"], state="readonly", width=18)
        self.app.combo_del_unit.grid(row=1, column=2, sticky="w")
        self.app.combo_del_unit.bind("<<ComboboxSelected>>", lambda e: self.calculate_dates())
        self.app.entry_del_term.bind("<KeyRelease>", lambda e: self.calculate_dates())
        ttk.Label(frame_del, text="Дата поставки:").grid(row=2, column=0, sticky="w", pady=5)
        self.app.entry_del_deadline = ttk.Entry(frame_del, width=20, state="readonly")
        self.app.entry_del_deadline.grid(row=2, column=1, sticky="w", pady=5)
        self.app.lbl_del_base = ttk.Label(frame_del, text="", foreground="blue")
        self.app.lbl_del_base.grid(row=2, column=2, sticky="w", padx=10, pady=5)

        ttk.Label(frame_del, text="Дата подтверждения:").grid(row=3, column=0, sticky="w", pady=5)
        self.app.entry_confirmation_date = ttk.Entry(frame_del, width=15)
        self.app.entry_confirmation_date.grid(row=3, column=1, sticky="w", padx=5, pady=5)
        self.app.btn_cal_confirmation = ttk.Button(frame_del, text="", width=3, command=self.select_confirmation_date)
        self.app.btn_cal_confirmation.grid(row=3, column=2, padx=5, pady=5)
        self.app.entry_confirmation_date.bind("<KeyRelease>", lambda e: self.calculate_dates())

        frame_work = ttk.LabelFrame(self.parent, text="Работы", padding=10)
        frame_work.pack(fill="x", pady=5)
        self.app.entry_work_start = self._create_date_entry(frame_work, "Начало:", 0)
        ttk.Label(frame_work, text="Срок:").grid(row=1, column=0, sticky="w", pady=5)
        self.app.entry_work_term = ttk.Entry(frame_work, width=10)
        self.app.entry_work_term.grid(row=1, column=1, sticky="w", padx=5)
        self.app.combo_work_unit = ttk.Combobox(frame_work, values=["Календарные дни", "Рабочие дни", "Недели", "Месяцы"], state="readonly", width=18)
        self.app.combo_work_unit.grid(row=1, column=2, sticky="w")
        self.app.combo_work_unit.bind("<<ComboboxSelected>>", lambda e: self.calculate_dates())
        self.app.entry_work_term.bind("<KeyRelease>", lambda e: self.calculate_dates())
        ttk.Label(frame_work, text="Сдача:").grid(row=2, column=0, sticky="w", pady=5)
        self.app.entry_work_deadline = ttk.Entry(frame_work, width=20, state="readonly")
        self.app.entry_work_deadline.grid(row=2, column=1, sticky="w", pady=5)

    def _create_date_entry(self, parent, text, row):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Label(frame, text=text).pack(side=tk.LEFT, padx=(0, 5))
        entry = ttk.Entry(frame, width=15)
        entry.pack(side=tk.LEFT, padx=(0, 5))
        btn = ttk.Button(frame, text="", width=3, command=lambda: self._select_date(entry))
        btn.pack(side=tk.LEFT)
        return entry

    def _select_date(self, entry):
        current = entry.get()
        dialog = CalendarDialog(self.root, current if current else None)
        self.root.wait_window(dialog)
        if dialog.result:
            entry.delete(0, tk.END)
            entry.insert(0, dialog.result)
            self.calculate_dates()

    def select_confirmation_date(self):
        current = self.app.entry_confirmation_date.get()
        dialog = CalendarDialog(self.root, current if current else None)
        self.root.wait_window(dialog)
        if dialog.result:
            self.app.entry_confirmation_date.delete(0, tk.END)
            self.app.entry_confirmation_date.insert(0, dialog.result)
            self.calculate_dates()

    def parse_date(self, date_str):
        return _parse_date(date_str)

    def is_working_day(self, date):
        if date.weekday() >= 5:
            return False
        if date in self.app.russian_holidays:
            return False
        return True

    def add_working_days(self, start_date, days):
        current = start_date
        added = 0
        while added < days:
            current += timedelta(days=1)
            if self.is_working_day(current):
                added += 1
        return current

    def get_first_payment_date(self):
        if not self.app.current_project:
            return None
        project_id = self.db_manager.get_project_id(self.app.current_project)
        if not project_id:
            return None
        payments = self.db_manager.get_payments(project_id)
        # Берём самую раннюю корректную дату, а не просто платёж №1
        # (номер и хронология могут не совпадать)
        dated = [(self.parse_date(p['date']), p['date']) for p in payments]
        dated = [d for d in dated if d[0]]
        if dated:
            return min(dated)[1]
        return None

    def calculate_deadline(self, start_date_str, term_str, unit):
        start_date = self.parse_date(start_date_str)
        term_str = (term_str or "").strip()
        if not start_date or not term_str.isdigit():
            return ""
        term = int(term_str)
        if term <= 0:
            return ""
        if unit == "Календарные дни":
            end_date = start_date + timedelta(days=term)
        elif unit == "Рабочие дни":
            end_date = self.add_working_days(start_date, term)
        elif unit == "Недели":
            end_date = start_date + timedelta(weeks=term)
        elif unit == "Месяцы":
            end_date = add_months(start_date, term)
        else:
            return ""
        return end_date.strftime("%d.%m.%Y")

    def calculate_dates(self):
        base_date_type = self.app.del_base_var.get()
        base_date_str = ""
        if base_date_type == "От даты договора":
            base_date_str = self.app.entry_contract_date.get()
            self.app.lbl_del_base.config(text="")
        elif base_date_type == "От даты первого платежа":
            base_date_str = self.get_first_payment_date()
            if base_date_str:
                self.app.lbl_del_base.config(text=f"(от платежа: {base_date_str})")
            else:
                self.app.lbl_del_base.config(text="(нет платежей)")
        elif base_date_type == "От даты подтверждения":
            base_date_str = self.app.entry_confirmation_date.get()
            if base_date_str:
                self.app.lbl_del_base.config(text=f"(от подтверждения: {base_date_str})")
            else:
                self.app.lbl_del_base.config(text="(не указана дата подтверждения)")
        del_deadline = self.calculate_deadline(base_date_str, self.app.entry_del_term.get(), self.app.combo_del_unit.get())
        self.app.entry_del_deadline.config(state="normal")
        self.app.entry_del_deadline.delete(0, tk.END)
        self.app.entry_del_deadline.insert(0, del_deadline)
        self.app.entry_del_deadline.config(state="readonly")
        work_deadline = self.calculate_deadline(self.app.entry_work_start.get(), self.app.entry_work_term.get(), self.app.combo_work_unit.get())
        self.app.entry_work_deadline.config(state="normal")
        self.app.entry_work_deadline.delete(0, tk.END)
        self.app.entry_work_deadline.insert(0, work_deadline)
        self.app.entry_work_deadline.config(state="readonly")