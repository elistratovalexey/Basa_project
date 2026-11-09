import tkinter as tk
from tkinter import ttk, messagebox


class PurchaseSpecItemDialog(tk.Toplevel):
    def __init__(self, parent, title, item_data):
        super().__init__(parent)
        self.title(title)
        self.geometry("500x300")
        self.resizable(False, False)
        self.result = None
        
        # Наименование
        ttk.Label(self, text="Наименование:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.entry_name = ttk.Entry(self, width=40)
        self.entry_name.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        
        # Количество
        ttk.Label(self, text="Количество:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.entry_quantity = ttk.Entry(self, width=15)
        self.entry_quantity.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        
        # Цена
        ttk.Label(self, text="Цена:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        self.entry_price = ttk.Entry(self, width=15)
        self.entry_price.grid(row=2, column=1, sticky="w", padx=5, pady=5)
        
        # Сумма
        ttk.Label(self, text="Сумма:").grid(row=3, column=0, sticky="w", padx=10, pady=5)
        self.entry_total = ttk.Entry(self, width=15)
        self.entry_total.grid(row=3, column=1, sticky="w", padx=5, pady=5)
        
        # Срок поставки
        ttk.Label(self, text="Срок поставки:").grid(row=4, column=0, sticky="w", padx=10, pady=5)
        self.entry_delivery_term = ttk.Entry(self, width=15)
        self.entry_delivery_term.grid(row=4, column=1, sticky="w", padx=5, pady=5)
        
        # Единица
        ttk.Label(self, text="Единица:").grid(row=5, column=0, sticky="w", padx=10, pady=5)
        self.combo_unit = ttk.Combobox(self, values=["шт.", "комп.", "уп.", "м.", "кг.", "л."], state="readonly", width=12)
        self.combo_unit.grid(row=5, column=1, sticky="w", padx=5, pady=5)
        
        self.grid_columnconfigure(1, weight=1)
        
        # Заполняем данные если редактируем
        if item_data:
            self.entry_name.insert(0, item_data.get('name', ''))
            self.entry_quantity.insert(0, str(item_data.get('quantity', 0)))
            self.entry_price.insert(0, str(item_data.get('price', 0)))
            self.entry_total.insert(0, str(item_data.get('total', 0)))
            self.entry_delivery_term.insert(0, item_data.get('delivery_term', ''))
            self.combo_unit.set(item_data.get('delivery_unit', 'шт.'))
        
        # Кнопки
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=6, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frame, text="Сохранить", command=self.save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self.destroy).pack(side=tk.LEFT, padx=5)
        
        self.grab_set()
    
    def save(self):
        try:
            quantity = float(self.entry_quantity.get().replace(',', '.')) if self.entry_quantity.get() else 0
            price = float(self.entry_price.get().replace(',', '.')) if self.entry_price.get() else 0
            total = float(self.entry_total.get().replace(',', '.')) if self.entry_total.get() else 0
        except ValueError:
            messagebox.showwarning("Ошибка", "Некорректное число!")
            return
        
        self.result = {
            'name': self.entry_name.get(),
            'quantity': quantity,
            'price': price,
            'total': total,
            'delivery_term': self.entry_delivery_term.get(),
            'delivery_unit': self.combo_unit.get(),
        }
        self.destroy()