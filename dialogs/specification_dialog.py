import tkinter as tk
from tkinter import ttk, messagebox


class SpecificationDialog(tk.Toplevel):
    def __init__(self, parent, title, number, spec_data=None):
        super().__init__(parent)
        self.title(title)
        self.geometry("550x420")
        self.resizable(False, False)
        self.result = None

        # Номер
        ttk.Label(self, text="№:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.entry_number = ttk.Entry(self, width=30)
        self.entry_number.grid(row=0, column=1, sticky="w", padx=10, pady=5)
        self.entry_number.insert(0, str(number))

        # Наименование
        ttk.Label(self, text="Наименование:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.entry_name = ttk.Entry(self, width=40)
        self.entry_name.grid(row=1, column=1, sticky="ew", padx=10, pady=5)

        # Единица измерения
        ttk.Label(self, text="Ед. изм.:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        self.combo_unit = ttk.Combobox(self, values=["шт.", "комп.", "уп.", "м.", "кг.", "л.", "т.", "пар.", "компл."],
                                        state="readonly", width=27)
        self.combo_unit.grid(row=2, column=1, sticky="w", padx=10, pady=5)
        self.combo_unit.set("шт.")

        # Количество
        ttk.Label(self, text="Количество:").grid(row=3, column=0, sticky="w", padx=10, pady=5)
        self.entry_quantity = ttk.Entry(self, width=30)
        self.entry_quantity.grid(row=3, column=1, sticky="w", padx=10, pady=5)

        # Цена
        ttk.Label(self, text="Цена:").grid(row=4, column=0, sticky="w", padx=10, pady=5)
        self.entry_price = ttk.Entry(self, width=30)
        self.entry_price.grid(row=4, column=1, sticky="w", padx=10, pady=5)
        self.entry_price.bind("<KeyRelease>", self.calc_total)

        # Сумма
        ttk.Label(self, text="Сумма:").grid(row=5, column=0, sticky="w", padx=10, pady=5)
        self.entry_total = ttk.Entry(self, width=30)
        self.entry_total.grid(row=5, column=1, sticky="w", padx=10, pady=5)
        self.entry_total.bind("<KeyRelease>", self.calc_price)

        # Валюта
        ttk.Label(self, text="Валюта:").grid(row=6, column=0, sticky="w", padx=10, pady=5)
        self.combo_currency = ttk.Combobox(self, values=["RUB", "USD", "EUR", "CNY", "TRY"],
                                            state="readonly", width=27)
        self.combo_currency.grid(row=6, column=1, sticky="w", padx=10, pady=5)
        self.combo_currency.set("RUB")

        # НДС
        ttk.Label(self, text="НДС (%):").grid(row=7, column=0, sticky="w", padx=10, pady=5)
        self.combo_vat = ttk.Combobox(self, values=["0", "5", "7", "10", "20", "22"],
                                       state="readonly", width=27)
        self.combo_vat.grid(row=7, column=1, sticky="w", padx=10, pady=5)
        self.combo_vat.set("20")

        # Примечание
        ttk.Label(self, text="Примечание:").grid(row=8, column=0, sticky="nw", padx=10, pady=5)
        self.entry_note = tk.Text(self, width=40, height=3)
        self.entry_note.grid(row=8, column=1, sticky="ew", padx=10, pady=5)

        self.grid_columnconfigure(1, weight=1)

        # Заполняем данными если редактируем
        if spec_data:
            self.entry_name.insert(0, spec_data.get('name', ''))
            self.combo_unit.set(spec_data.get('unit', 'шт.'))
            self.entry_quantity.insert(0, str(spec_data.get('quantity', '')))
            self.entry_price.insert(0, str(spec_data.get('price', '')))
            self.entry_total.insert(0, str(spec_data.get('total', '')))
            self.combo_currency.set(spec_data.get('currency', 'RUB'))
            self.combo_vat.set(str(spec_data.get('vat', '20')))
            if spec_data.get('note'):
                self.entry_note.insert("1.0", spec_data.get('note'))

        # Кнопки
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=9, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frame, text="Сохранить", command=self.save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self.destroy).pack(side=tk.LEFT, padx=5)

        self.grab_set()

    def calc_total(self, event=None):
        """Автоматический расчет суммы = количество * цена"""
        try:
            qty = float(self.entry_quantity.get().replace(',', '.')) if self.entry_quantity.get() else 0
            price = float(self.entry_price.get().replace(',', '.')) if self.entry_price.get() else 0
            total = qty * price
            self.entry_total.delete(0, tk.END)
            self.entry_total.insert(0, f"{total:.2f}")
        except:
            pass

    def calc_price(self, event=None):
        """Автоматический расчет цены = сумма / количество"""
        try:
            qty = float(self.entry_quantity.get().replace(',', '.')) if self.entry_quantity.get() else 0
            total = float(self.entry_total.get().replace(',', '.')) if self.entry_total.get() else 0
            if qty > 0:
                price = total / qty
                self.entry_price.delete(0, tk.END)
                self.entry_price.insert(0, f"{price:.2f}")
        except:
            pass

    def save(self):
        name = self.entry_name.get().strip()
        if not name:
            messagebox.showwarning("Ошибка", "Введите наименование!")
            return

        try:
            quantity = float(self.entry_quantity.get().replace(',', '.')) if self.entry_quantity.get() else 0
            price = float(self.entry_price.get().replace(',', '.')) if self.entry_price.get() else 0
            total = float(self.entry_total.get().replace(',', '.')) if self.entry_total.get() else 0
            vat = int(self.combo_vat.get()) if self.combo_vat.get() else 0
        except ValueError:
            messagebox.showwarning("Ошибка", "Некорректное число!")
            return

        self.result = {
            'number': self.entry_number.get().strip(),
            'name': name,
            'unit': self.combo_unit.get(),
            'quantity': quantity,
            'price': price,
            'total': total,
            'currency': self.combo_currency.get(),
            'vat': vat,
            'note': self.entry_note.get("1.0", tk.END).strip(),
        }
        self.destroy()