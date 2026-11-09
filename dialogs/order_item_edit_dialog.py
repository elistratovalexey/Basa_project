import tkinter as tk
from tkinter import ttk, messagebox

try:
    from config import TIME_UNITS, ORDER_CURRENCIES
except ImportError:
    TIME_UNITS = ["Календарные дни", "Рабочие дни", "Недели", "Месяцы"]
    ORDER_CURRENCIES = ["EUR", "USD", "CNY", "RUB"]


class OrderItemEditDialog(tk.Toplevel):
    def __init__(self, parent, item_data):
        super().__init__(parent)
        self.title("Редактировать позицию")
        self.geometry("650x420")
        from dialogs.window_geometry import restore_geometry, track_geometry
        restore_geometry(self, "КЛЮЧ", "ШИРИНАxВЫСОТА")
        track_geometry(self, "КЛЮЧ")
        self.resizable(False, False)
        self.result = None
        self.item_data = item_data

        ttk.Label(self, text="Артикул:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.entry_article = tk.Entry(self, width=35)
        self.entry_article.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        ttk.Label(self, text="Наименование:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.entry_name = tk.Entry(self, width=35)
        self.entry_name.grid(row=1, column=1, sticky="ew", padx=5, pady=5)

        ttk.Label(self, text="Кол-во:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        self.entry_quantity = tk.Entry(self, width=15)
        self.entry_quantity.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(self, text="Срок поставки:").grid(row=3, column=0, sticky="w", padx=10, pady=5)
        self.entry_delivery_term = tk.Entry(self, width=10)
        self.entry_delivery_term.grid(row=3, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(self, text="Единица:").grid(row=3, column=2, sticky="w", padx=10, pady=5)
        self.combo_delivery_unit = ttk.Combobox(self, values=TIME_UNITS, state="readonly", width=18)
        self.combo_delivery_unit.grid(row=3, column=3, sticky="w", padx=5, pady=5)

        ttk.Label(self, text="Цена:").grid(row=4, column=0, sticky="w", padx=10, pady=5)
        self.entry_price = tk.Entry(self, width=15)
        self.entry_price.grid(row=4, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(self, text="Валюта:").grid(row=4, column=2, sticky="w", padx=10, pady=5)
        self.combo_currency = ttk.Combobox(self, values=ORDER_CURRENCIES, state="readonly", width=10)
        self.combo_currency.grid(row=4, column=3, sticky="w", padx=5, pady=5)

        ttk.Label(self, text="Примечание:").grid(row=5, column=0, sticky="w", padx=10, pady=5)
        self.entry_note = tk.Entry(self, width=35)
        self.entry_note.grid(row=5, column=1, sticky="ew", padx=5, pady=5, columnspan=3)

        self.grid_columnconfigure(1, weight=1)

        self.entry_article.insert(0, str(item_data.get('article', '')))
        self.entry_name.insert(0, str(item_data.get('name', '')))
        self.entry_quantity.insert(0, str(item_data.get('quantity', 0)))
        self.entry_delivery_term.insert(0, str(item_data.get('delivery_term', 0)))

        unit = item_data.get('delivery_unit', '')
        self.combo_delivery_unit.set(unit if unit else TIME_UNITS[0])

        self.entry_price.insert(0, str(item_data.get('price', '')))

        currency = item_data.get('currency', '')
        self.combo_currency.set(currency if currency else ORDER_CURRENCIES[0])

        self.entry_note.insert(0, str(item_data.get('note', '')))

        self.after(100, lambda: self.entry_article.focus_set())

        btn_frame = tk.Frame(self)
        btn_frame.grid(row=6, column=0, columnspan=4, pady=15)
        tk.Button(btn_frame, text="Сохранить", command=self.save, width=12).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Отмена", command=self.destroy, width=12).pack(side=tk.LEFT, padx=5)

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

    def save(self):
        try:
            quantity = int(self.entry_quantity.get()) if self.entry_quantity.get() else 0
            delivery_term = int(self.entry_delivery_term.get()) if self.entry_delivery_term.get() else 0
        except ValueError:
            messagebox.showwarning("Ошибка", "Некорректное число!")
            return
        self.result = {
            'article': self.entry_article.get(),
            'name': self.entry_name.get(),
            'quantity': quantity,
            'delivery_term': delivery_term,
            'delivery_unit': self.combo_delivery_unit.get(),
            'price': self.entry_price.get(),
            'currency': self.combo_currency.get(),
            'note': self.entry_note.get(),
        }
        self.destroy()
