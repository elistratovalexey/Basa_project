import tkinter as tk
from tkinter import ttk, messagebox


class PurchaseSpecDialog(tk.Toplevel):
    def __init__(self, parent, title, spec_data, db_manager):
        super().__init__(parent)
        self.title(title)
        self.geometry("700x500")
        self.resizable(False, False)
        self.result = None
        self.db_manager = db_manager
        
        # Поставщик
        ttk.Label(self, text="Поставщик:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.combo_supplier = ttk.Combobox(self, width=40)
        self.combo_supplier.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        # Кнопка "+" теперь автоматически добавляет поставщика из поля
        ttk.Button(self, text="+", width=3, command=self.auto_add_supplier).grid(row=0, column=2, padx=(0, 15))
        
        # Наименование
        ttk.Label(self, text="Наименование:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.entry_name = ttk.Entry(self, width=50)
        self.entry_name.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        
        # Сумма
        ttk.Label(self, text="Сумма:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        self.entry_total = ttk.Entry(self, width=15)
        self.entry_total.grid(row=2, column=1, sticky="w", padx=5, pady=5)
        
        # Валюта
        ttk.Label(self, text="Валюта:").grid(row=2, column=2, sticky="w", padx=10, pady=5)
        self.combo_currency = ttk.Combobox(self, values=["RUB", "USD", "EUR", "CNY"], state="readonly", width=10)
        self.combo_currency.grid(row=2, column=3, sticky="w", pady=5)
        
        # Срок поставки
        ttk.Label(self, text="Срок поставки:").grid(row=3, column=0, sticky="w", padx=10, pady=5)
        self.entry_delivery_term = ttk.Entry(self, width=15)
        self.entry_delivery_term.grid(row=3, column=1, sticky="w", padx=5, pady=5)
        
        # Единица
        ttk.Label(self, text="Единица:").grid(row=3, column=2, sticky="w", padx=10, pady=5)
        self.combo_unit = ttk.Combobox(self, values=["Календарные дни", "Рабочие дни", "Недели", "Месяцы"], 
                                        state="readonly", width=15)
        self.combo_unit.grid(row=3, column=3, sticky="w", pady=5)
        
        # Дата оплаты
        ttk.Label(self, text="Дата оплаты:").grid(row=4, column=0, sticky="w", padx=10, pady=5)
        self.entry_payment_date = ttk.Entry(self, width=12)
        self.entry_payment_date.grid(row=4, column=1, sticky="w", padx=5, pady=5)
        self.btn_cal_payment = ttk.Button(self, text="📅", width=3, command=self.select_payment_date)
        self.btn_cal_payment.grid(row=4, column=2, padx=(0, 15), pady=5)
        
        # Дата поставки
        ttk.Label(self, text="Дата поставки:").grid(row=4, column=3, sticky="w", padx=10, pady=5)
        self.entry_delivery_date = ttk.Entry(self, width=12)
        self.entry_delivery_date.grid(row=4, column=4, sticky="w", pady=5)
        # Добавлена кнопка календаря для даты поставки
        self.btn_cal_delivery = ttk.Button(self, text="", width=3, command=self.select_delivery_date)
        self.btn_cal_delivery.grid(row=4, column=5, padx=(5, 15), pady=5)
        
        # Оплачен
        self.paid_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="Оплачен полностью", variable=self.paid_var).grid(row=5, column=0, columnspan=2, 
                                                                                       sticky="w", padx=(10, 15), pady=5)
        # Получен
        self.received_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="Получен", variable=self.received_var).grid(row=5, column=2, columnspan=2, 
                                                                                sticky="w", padx=(10, 15), pady=5)
        
        # Адрес доставки - теперь выпадающий список из базы доставок
        ttk.Label(self, text="Адрес доставки:").grid(row=6, column=0, sticky="w", padx=10, pady=5)
        self.combo_delivery_address = ttk.Combobox(self, width=50)
        self.combo_delivery_address.grid(row=6, column=1, columnspan=4, sticky="ew", padx=5, pady=5)
        
        # Примечание
        ttk.Label(self, text="Примечание:").grid(row=7, column=0, sticky="nw", padx=10, pady=5)
        self.entry_note = tk.Text(self, width=50, height=3)
        self.entry_note.grid(row=7, column=1, columnspan=4, sticky="ew", padx=5, pady=5)
        
        self.grid_columnconfigure(1, weight=1)
        
        # Загружаем поставщиков и адреса доставки
        self.load_suppliers()
        self.load_delivery_addresses()
        
        # Заполняем данные если редактируем
        if spec_data:
            self.combo_supplier.set(spec_data.get('supplier', ''))
            self.entry_name.insert(0, spec_data.get('name', ''))
            self.entry_total.insert(0, str(spec_data.get('total', 0)))
            self.combo_currency.set(spec_data.get('currency', 'RUB'))
            self.entry_delivery_term.insert(0, str(spec_data.get('delivery_term', 0)))
            self.combo_unit.set(spec_data.get('delivery_unit', 'Календарные дни'))
            self.entry_payment_date.insert(0, spec_data.get('payment_date', ''))
            self.entry_delivery_date.insert(0, spec_data.get('delivery_date', ''))
            self.paid_var.set(spec_data.get('fully_paid', 0) == 1)
            self.received_var.set(spec_data.get('received', 0) == 1)
            # Адрес доставки не заполняем при импорте
            if spec_data.get('delivery_address') and title == "Редактировать":
                self.combo_delivery_address.set(spec_data.get('delivery_address'))
            if spec_data.get('note'):
                self.entry_note.insert("1.0", spec_data.get('note'))
        
        # Кнопки
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=8, column=0, columnspan=6, pady=15)
        ttk.Button(btn_frame, text="Сохранить", command=self.save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self.destroy).pack(side=tk.LEFT, padx=5)
        
        self.grab_set()
    
    def load_suppliers(self):
        c = self.db_manager.conn.cursor()
        c.execute("SELECT DISTINCT name FROM suppliers ORDER BY name")
        suppliers = [row[0] for row in c.fetchall()]
        self.combo_supplier['values'] = suppliers
    
    def load_delivery_addresses(self):
        """Загружает адреса доставки из базы"""
        c = self.db_manager.conn.cursor()
        c.execute("SELECT DISTINCT address FROM delivery_addresses ORDER BY address")
        addresses = [row[0] for row in c.fetchall()]
        self.combo_delivery_address['values'] = addresses
    
    def auto_add_supplier(self):
        """Автоматически добавляет поставщика из поля в базу"""
        supplier_name = self.combo_supplier.get().strip()
        if not supplier_name:
            messagebox.showwarning("Внимание", "Введите название поставщика!")
            return
        
        # Проверяем, есть ли уже такой поставщик
        c = self.db_manager.conn.cursor()
        c.execute("SELECT id FROM suppliers WHERE name=?", (supplier_name,))
        if c.fetchone():
            messagebox.showinfo("Информация", f"Поставщик '{supplier_name}' уже существует в базе!")
            return
        
        # Добавляем поставщика
        result = self.db_manager.add_supplier({'name': supplier_name})
        if result:
            messagebox.showinfo("Успех", f"Поставщик '{supplier_name}' добавлен в базу!")
            self.load_suppliers()
        else:
            messagebox.showerror("Ошибка", f"Не удалось добавить поставщика '{supplier_name}'!")
    
    def select_payment_date(self):
        from dialogs.calendar_dialog import CalendarDialog
        current = self.entry_payment_date.get()
        dialog = CalendarDialog(self, current if current else None)
        self.wait_window(dialog)
        if dialog.result:
            self.entry_payment_date.delete(0, tk.END)
            self.entry_payment_date.insert(0, dialog.result)
    
    def select_delivery_date(self):
        """Выбор даты поставки через календарь"""
        from dialogs.calendar_dialog import CalendarDialog
        current = self.entry_delivery_date.get()
        dialog = CalendarDialog(self, current if current else None)
        self.wait_window(dialog)
        if dialog.result:
            self.entry_delivery_date.delete(0, tk.END)
            self.entry_delivery_date.insert(0, dialog.result)
    
    def save(self):
        try:
            total = float(self.entry_total.get().replace(',', '.')) if self.entry_total.get() else 0
            delivery_term = int(self.entry_delivery_term.get()) if self.entry_delivery_term.get() else 0
        except ValueError:
            messagebox.showwarning("Ошибка", "Некорректное число!")
            return
        
        self.result = {
            'supplier': self.combo_supplier.get(),
            'name': self.entry_name.get(),
            'total': total,
            'currency': self.combo_currency.get(),
            'delivery_term': delivery_term,
            'delivery_unit': self.combo_unit.get(),
            'payment_date': self.entry_payment_date.get(),
            'delivery_date': self.entry_delivery_date.get(),
            'fully_paid': 1 if self.paid_var.get() else 0,
            'received': 1 if self.received_var.get() else 0,
            'delivery_address': self.combo_delivery_address.get(),
            'note': self.entry_note.get("1.0", tk.END).strip(),
        }
        self.destroy()