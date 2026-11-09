import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime


class PaymentScheduleDialog(tk.Toplevel):
    """Диалог управления таблицей оплат по спецификации"""
    
    def __init__(self, parent, db_manager, spec_id, total_amount):
        super().__init__(parent)
        self.title(f"Оплаты по спецификации #{spec_id}")
        self.geometry("800x600")
        from dialogs.window_geometry import restore_geometry, track_geometry
        restore_geometry(self, "КЛЮЧ", "ШИРИНАxВЫСОТА")
        track_geometry(self, "КЛЮЧ")
        
        self.resizable(True, True)
        
        self.db_manager = db_manager
        self.spec_id = spec_id
        self.total_amount = float(total_amount) if total_amount else 0
        self.current_payment_id = None
        
        self.create_ui()
        self.load_payments()
               # Было: self.grab_set()
        def _safe_grab():
            try:
                if self.winfo_exists() and self.winfo_viewable():
                    self.grab_set()
                else:
                    self.after(100, _safe_grab)
            except tk.TclError:
                self.after(100, _safe_grab)
        self.after(50, _safe_grab)
        self.transient(parent)
    
    def create_ui(self):
        # === Таблица оплат ===
        table_frame = ttk.LabelFrame(self, text="Список оплат", padding=8)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        cols = ("id", "number", "date", "amount", "currency", "percent", "paid")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=12)
        self.tree.heading("id", text="ID")
        self.tree.heading("number", text="№ платежа")
        self.tree.heading("date", text="Дата")
        self.tree.heading("amount", text="Сумма")
        self.tree.heading("currency", text="Валюта")
        self.tree.heading("percent", text="% от суммы")
        self.tree.heading("paid", text="Оплачен")
        
        self.tree.column("id", width=50, anchor="center")
        self.tree.column("number", width=80, anchor="center")
        self.tree.column("date", width=110, anchor="center")
        self.tree.column("amount", width=120, anchor="e")
        self.tree.column("currency", width=70, anchor="center")
        self.tree.column("percent", width=90, anchor="center")
        self.tree.column("paid", width=70, anchor="center")
        
        sb = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", lambda e: self.edit_payment())
        
        # Кнопки управления
        btn_frame = ttk.Frame(table_frame)
        btn_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(btn_frame, text="Добавить", command=self.add_payment).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Редактировать", command=self.edit_payment).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Удалить", command=self.delete_payment).pack(side=tk.LEFT, padx=5)
        
        # === Форма редактирования ===
        form_frame = ttk.LabelFrame(self, text="Редактирование платежа", padding=8)
        form_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttk.Label(form_frame, text="№:").grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.entry_number = ttk.Entry(form_frame, width=20)
        self.entry_number.grid(row=0, column=1, sticky="w", padx=(0, 15))
        
        ttk.Label(form_frame, text="Дата:").grid(row=0, column=2, sticky="w", padx=(0, 5))
        self.entry_date = ttk.Entry(form_frame, width=12)
        self.entry_date.grid(row=0, column=3, sticky="w", padx=(0, 15))
        ttk.Button(form_frame, text="📅", width=3, command=self.select_date).grid(row=0, column=4, padx=(0, 15))
        
        ttk.Label(form_frame, text="Сумма:").grid(row=0, column=5, sticky="w", padx=(0, 5))
        self.entry_amount = ttk.Entry(form_frame, width=15)
        self.entry_amount.grid(row=0, column=6, sticky="w", padx=(0, 15))
        self.entry_amount.bind("<KeyRelease>", self.calculate_percent)
        
        ttk.Label(form_frame, text="Валюта:").grid(row=0, column=7, sticky="w", padx=(0, 5))
        self.combo_currency = ttk.Combobox(form_frame, values=["RUB", "USD", "EUR", "CNY"], 
                                            state="readonly", width=10)
        self.combo_currency.grid(row=0, column=8, sticky="w", padx=(0, 15))
        self.combo_currency.set("RUB")
        
        ttk.Label(form_frame, text="%:").grid(row=0, column=9, sticky="w", padx=(0, 5))
        self.entry_percent = ttk.Entry(form_frame, width=10)
        self.entry_percent.grid(row=0, column=10, sticky="w")
        
        self.paid_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(form_frame, text="Оплачен", variable=self.paid_var).grid(row=1, column=0, columnspan=3, 
                                                                                   sticky="w", padx=(0, 15), pady=(8, 0))
        
        # Кнопки сохранения
        btn_frame2 = ttk.Frame(form_frame)
        btn_frame2.grid(row=1, column=3, columnspan=8, pady=(8, 0))
        ttk.Button(btn_frame2, text="Сохранить", command=self.save_payment).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame2, text="Очистить форму", command=self.clear_form).pack(side=tk.LEFT, padx=5)
        
        # === Итоговая строка ===
        total_frame = ttk.Frame(self)
        total_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        self.lbl_total_amount = ttk.Label(total_frame, 
            text=f"Общая сумма: {self.total_amount:.2f}", 
            font=("Arial", 10, "bold"))
        self.lbl_total_amount.pack(side=tk.LEFT, padx=10)
        
        self.lbl_paid = ttk.Label(total_frame, 
            text="Оплачено: 0.00", 
            font=("Arial", 10, "bold"), foreground="blue")
        self.lbl_paid.pack(side=tk.LEFT, padx=20)
        
        self.lbl_remaining = ttk.Label(total_frame, 
            text=f"Осталось: {self.total_amount:.2f}", 
            font=("Arial", 10, "bold"), foreground="red")
        self.lbl_remaining.pack(side=tk.LEFT, padx=20)
        
        self.lbl_percent = ttk.Label(total_frame, 
            text="0%", 
            font=("Arial", 10, "bold"))
        self.lbl_percent.pack(side=tk.LEFT, padx=10)
        
        # Кнопка закрытия
        ttk.Button(self, text="Закрыть", command=self.destroy).pack(pady=(0, 10))
    
    def load_payments(self):
        """Загрузить список оплат из БД"""
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        c = self.db_manager.conn.cursor()
        # ИСПОЛЬЗУЕМ ПРАВИЛЬНЫЕ ИМЕНА КОЛОНОК
        c.execute('''SELECT id, number, date, amount, currency, percent, paid 
                     FROM purchase_payments 
                     WHERE spec_id=? 
                     ORDER BY date''', (self.spec_id,))
        
        payments = c.fetchall()
        total_paid = 0
        
        for row in payments:
            pay_id, number, date, amount, currency, percent, paid = row
            amount = float(amount) if amount else 0
            percent = float(percent) if percent else 0
            total_paid += amount
            
            paid_mark = "✓" if paid else ""
            
            self.tree.insert("", tk.END, values=(
                pay_id,
                number or "",
                date or "",
                f"{amount:.2f}",
                currency or "RUB",
                f"{percent:.1f}%",
                paid_mark
            ))
        
        self.update_totals(total_paid)
    
    def update_totals(self, total_paid):
        """Обновить итоговую строку"""
        remaining = self.total_amount - total_paid
        percent_paid = (total_paid / self.total_amount * 100) if self.total_amount > 0 else 0
        
        self.lbl_paid.config(text=f"Оплачено: {total_paid:.2f}")
        self.lbl_remaining.config(text=f"Осталось: {remaining:.2f}")
        self.lbl_percent.config(text=f"{percent_paid:.1f}%")
        
        if remaining <= 0:
            self.lbl_remaining.config(foreground="green", text="Оплачено полностью ✓")
            self.lbl_percent.config(foreground="green")
        else:
            self.lbl_remaining.config(foreground="red")
            self.lbl_percent.config(foreground="black")
    
    def on_select(self, event):
        """При выборе строки в таблице - заполнить форму"""
        selected = self.tree.selection()
        if not selected:
            return
        values = self.tree.item(selected[0])['values']
        self.current_payment_id = values[0]
        self.entry_number.delete(0, tk.END)
        self.entry_number.insert(0, str(values[1]))
        self.entry_date.delete(0, tk.END)
        self.entry_date.insert(0, values[2])
        self.entry_amount.delete(0, tk.END)
        self.entry_amount.insert(0, values[3])
        self.combo_currency.set(values[4])
        self.entry_percent.delete(0, tk.END)
        self.entry_percent.insert(0, values[5].replace('%', ''))
        self.paid_var.set(values[6] == "✓")
    
    def calculate_percent(self, event=None):
        """Автоматически рассчитать % от суммы"""
        try:
            amount = float(self.entry_amount.get().replace(',', '.'))
            percent = (amount / self.total_amount * 100) if self.total_amount > 0 else 0
            self.entry_percent.delete(0, tk.END)
            self.entry_percent.insert(0, f"{percent:.1f}")
        except:
            pass
    
    def select_date(self):
        """Открыть календарь"""
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
    
    def add_payment(self):
        """Подготовить форму для добавления нового платежа"""
        self.current_payment_id = None
        self.entry_number.delete(0, tk.END)
        self.entry_date.delete(0, tk.END)
        self.entry_date.insert(0, datetime.now().strftime("%d.%m.%Y"))
        self.entry_amount.delete(0, tk.END)
        self.entry_percent.delete(0, tk.END)
        self.combo_currency.set("RUB")
        self.paid_var.set(False)
    
    def edit_payment(self):
        """Редактировать выбранный платёж"""
        if self.current_payment_id is None:
            messagebox.showwarning("Внимание", "Выберите платёж в таблице!")
            return
        self.save_payment()
    
    def delete_payment(self):
        """Удалить выбранный платёж"""
        if self.current_payment_id is None:
            messagebox.showwarning("Внимание", "Выберите платёж в таблице!")
            return
        
        if messagebox.askyesno("Подтверждение", "Удалить этот платёж?"):
            c = self.db_manager.conn.cursor()
            c.execute("DELETE FROM purchase_payments WHERE id=?", (self.current_payment_id,))
            self.db_manager.conn.commit()
            self.current_payment_id = None
            self.clear_form()
            self.load_payments()
            messagebox.showinfo("Успех", "Платёж удалён")
    
    def save_payment(self):
        """Сохранить платёж (добавить или обновить)"""
        try:
            number = int(self.entry_number.get().strip()) if self.entry_number.get().strip() else 0
            date = self.entry_date.get().strip()
            amount = float(self.entry_amount.get().replace(',', '.'))
            currency = self.combo_currency.get() or "RUB"
            percent = float(self.entry_percent.get().replace(',', '.')) if self.entry_percent.get() else 0
            paid = 1 if self.paid_var.get() else 0
        except ValueError:
            messagebox.showwarning("Ошибка", "Некорректные данные!")
            return
        
        if amount <= 0:
            messagebox.showwarning("Ошибка", "Сумма должна быть больше 0!")
            return
        
        c = self.db_manager.conn.cursor()
        
        try:
            if self.current_payment_id is None:
                # Добавляем новый - ИСПОЛЬЗУЕМ ПРАВИЛЬНЫЕ ИМЕНА КОЛОНОК
                c.execute('''INSERT INTO purchase_payments 
                             (spec_id, number, date, amount, currency, percent, paid) 
                             VALUES (?, ?, ?, ?, ?, ?, ?)''', 
                          (self.spec_id, number, date, amount, currency, percent, paid))
                msg = "Платёж добавлен"
            else:
                # Обновляем существующий
                c.execute('''UPDATE purchase_payments 
                             SET number=?, date=?, amount=?, currency=?, percent=?, paid=?
                             WHERE id=?''', 
                          (number, date, amount, currency, percent, paid, self.current_payment_id))
                msg = "Платёж обновлён"
            
            self.db_manager.conn.commit()
            self.load_payments()
            self.clear_form()
            messagebox.showinfo("Успех", msg)
        except Exception as e:
            messagebox.showerror("Ошибка БД", f"Не удалось сохранить платёж:\n{e}")
            import traceback
            traceback.print_exc()
    
    def clear_form(self):
        """Очистить форму"""
        self.current_payment_id = None
        self.entry_number.delete(0, tk.END)
        self.entry_date.delete(0, tk.END)
        self.entry_amount.delete(0, tk.END)
        self.entry_percent.delete(0, tk.END)
        self.combo_currency.set("RUB")
        self.paid_var.set(False)
