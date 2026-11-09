import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime, timedelta
import os
import re

try:
    from utils import parse_number, parse_delivery_time, translate_time_unit
except ImportError:
    def parse_number(s):
        if s is None:
            return None
        s = str(s).strip()
        if not s:
            return None
        if '.' in s and ',' in s:
            s = s.replace('.', '').replace(',', '.')
        elif ',' in s:
            s = s.replace(',', '.')
        try:
            return float(s)
        except:
            return None

    def translate_time_unit(unit_str):
        if not unit_str:
            return "Недели"
        unit_upper = unit_str.upper().strip()
        unit_map = {
            'HAFTA': 'Недели', 'WEEK': 'Недели', 'WEEKS': 'Недели',
            'GÜN': 'Календарные дни', 'DAY': 'Календарные дни', 'DAYS': 'Календарные дни',
            'AY': 'Месяцы', 'MONTH': 'Месяцы', 'MONTHS': 'Месяцы',
            'İŞ GÜNÜ': 'Рабочие дни', 'İŞGÜNÜ': 'Рабочие дни',
        }
        return unit_map.get(unit_upper, "Недели")

    def parse_delivery_time(time_str):
        if not time_str:
            return None, None
        time_str = str(time_str).strip()
        time_upper = time_str.upper()
        match = re.match(r'(\d+)\s*[-–]\s*(\d+)\s+([A-ZА-Я]+(?:\s+[A-ZА-Я]+)?)', time_upper)
        if match:
            num1 = int(match.group(1))
            num2 = int(match.group(2))
            unit = match.group(3)
            max_num = max(num1, num2)
            translated_unit = translate_time_unit(unit)
            return max_num, translated_unit
        match = re.match(r'(\d+)\s+([A-ZА-Я]+(?:\s+[A-ZА-Я]+)?)', time_upper)
        if match:
            num = int(match.group(1))
            unit = match.group(2)
            translated_unit = translate_time_unit(unit)
            return num, translated_unit
        return None, None

try:
    from dialogs.order_file_parser import parse_file_to_rows_with_text
except ImportError:
    pass

try:
    from dialogs.payment_schedule_dialog import PaymentScheduleDialog
except ImportError:
    pass


class PurchaseSpecTab:
    def __init__(self, app, parent):
        self.app = app
        self.parent = parent
        self.db_manager = app.db_manager
        self.root = app.root
        self.current_spec_id = None
        self.current_item_id = None
        self.create_ui()

    # ==================================================================
    # UI
    # ==================================================================
    def create_ui(self):
        # === Верхняя таблица: Спецификации закупок ===
        spec_frame = ttk.LabelFrame(self.parent, text="Спецификация закупок", padding=8)
        spec_frame.pack(fill=tk.X, padx=10, pady=5)

        info_frame = ttk.Frame(spec_frame)
        info_frame.pack(fill=tk.X, pady=(0, 5))
        info_label = ttk.Label(info_frame, text="💡 Двойной щелчок мыши по строке - открывается окно оплат",
                            font=("Arial", 9, "italic"), foreground="#0066cc")
        info_label.pack(side=tk.LEFT, padx=5)

        btn_frame = ttk.Frame(spec_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(btn_frame, text="Добавить позицию", command=self.add_purchase_spec).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Редактировать", command=self.edit_purchase_spec).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Удалить", command=self.delete_purchase_spec).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Импорт из файла", command=self.import_spec_from_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="База доставок", command=self.open_delivery_addresses).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Справочник номенклатуры", command=self.open_nomenclature).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Справочник поставщиков", command=self.open_suppliers).pack(side=tk.RIGHT, padx=5)

        cols = ("id", "supplier", "description", "total", "currency", "delivery_term",
                "delivery_unit", "payment_date", "delivery_date", "paid", "received",
                "delivery_address", "note")
        self.spec_tree = ttk.Treeview(spec_frame, columns=cols, show="headings", height=8)
        self.spec_tree.heading("id", text="№")
        self.spec_tree.heading("supplier", text="Поставщик")
        self.spec_tree.heading("description", text="Описание")
        self.spec_tree.heading("total", text="Сумма")
        self.spec_tree.heading("currency", text="Валюта")
        self.spec_tree.heading("delivery_term", text="Срок")
        self.spec_tree.heading("delivery_unit", text="Ед.")
        self.spec_tree.heading("payment_date", text="Дата оплаты")
        self.spec_tree.heading("delivery_date", text="Дата поставки")
        self.spec_tree.heading("paid", text="Оплачен")
        self.spec_tree.heading("received", text="Получен")
        self.spec_tree.heading("delivery_address", text="Адрес доставки")
        self.spec_tree.heading("note", text="Примечание")

        self.spec_tree.column("id", width=40, anchor="center")
        self.spec_tree.column("supplier", width=120, anchor="w")
        self.spec_tree.column("description", width=200, anchor="w")
        self.spec_tree.column("total", width=80, anchor="e")
        self.spec_tree.column("currency", width=60, anchor="center")
        self.spec_tree.column("delivery_term", width=50, anchor="center")
        self.spec_tree.column("delivery_unit", width=80, anchor="w")
        self.spec_tree.column("payment_date", width=90, anchor="center")
        self.spec_tree.column("delivery_date", width=90, anchor="center")
        self.spec_tree.column("paid", width=60, anchor="center")
        self.spec_tree.column("received", width=60, anchor="center")
        self.spec_tree.column("delivery_address", width=150, anchor="w")
        self.spec_tree.column("note", width=150, anchor="w")

        # Стиль строки «ИТОГО»
        self.spec_tree.tag_configure('total_row', background='#cfe9d2', font=('Arial', 9, 'bold'))

        sb = ttk.Scrollbar(spec_frame, orient=tk.VERTICAL, command=self.spec_tree.yview)
        self.spec_tree.configure(yscroll=sb.set)
        self.spec_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.spec_tree.bind("<<TreeviewSelect>>", self.on_select_spec)
        self.spec_tree.bind("<Double-1>", self.on_double_click_spec)

        # === Нижняя таблица: Позиции спецификации ===
        items_frame = ttk.LabelFrame(self.parent, text="Позиции спецификации", padding=8)
        items_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        items_btn_frame = ttk.Frame(items_frame)
        items_btn_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(items_btn_frame, text="Добавить позицию", command=self.add_purchase_spec_item).pack(side=tk.LEFT, padx=5)
        ttk.Button(items_btn_frame, text="Редактировать позицию", command=self.edit_purchase_spec_item).pack(side=tk.LEFT, padx=5)
        ttk.Button(items_btn_frame, text="Удалить позицию", command=self.delete_purchase_spec_item).pack(side=tk.LEFT, padx=5)

        # Итого СВЕРХУ таблицы позиций
        total_frame = ttk.Frame(items_frame)
        total_frame.pack(fill=tk.X, pady=(5, 0))
        self.lbl_total = ttk.Label(total_frame, text="Итого: 0.00", font=("Arial", 10, "bold"))
        self.lbl_total.pack(side=tk.LEFT, padx=5)
        ttk.Button(total_frame, text="Перенести сумму в спецификацию", command=self.transfer_total).pack(side=tk.RIGHT, padx=5)

        # Итого СНИЗУ таблицы позиций.
        # ВАЖНО: pack(side=BOTTOM) вызывается ДО упаковки дерева и скроллбара,
        # иначе tkinter отдаст метке верхнюю полку и она уедет наверх (дубль).
        total_bottom_frame = ttk.Frame(items_frame)
        total_bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 0))
        self.lbl_total_bottom = ttk.Label(total_bottom_frame, text="Итого: 0.00", font=("Arial", 10, "bold"))
        self.lbl_total_bottom.pack(side=tk.LEFT, padx=5)

        item_cols = ("id", "number", "name", "quantity", "price", "total", "delivery_term", "delivery_unit")
        self.items_tree = ttk.Treeview(items_frame, columns=item_cols, show="headings", height=10)
        self.items_tree.heading("id", text="ID")
        self.items_tree.heading("number", text="№")
        self.items_tree.heading("name", text="Наименование")
        self.items_tree.heading("quantity", text="Кол-во")
        self.items_tree.heading("price", text="Цена")
        self.items_tree.heading("total", text="Сумма")
        self.items_tree.heading("delivery_term", text="Срок поставки")
        self.items_tree.heading("delivery_unit", text="Ед.")

        self.items_tree.column("id", width=50, anchor="center")
        self.items_tree.column("number", width=40, anchor="center")
        self.items_tree.column("name", width=250, anchor="w")
        self.items_tree.column("quantity", width=60, anchor="center")
        self.items_tree.column("price", width=80, anchor="e")
        self.items_tree.column("total", width=80, anchor="e")
        self.items_tree.column("delivery_term", width=80, anchor="center")
        self.items_tree.column("delivery_unit", width=80, anchor="w")

        item_sb = ttk.Scrollbar(items_frame, orient=tk.VERTICAL, command=self.items_tree.yview)
        self.items_tree.configure(yscroll=item_sb.set)
        self.items_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        item_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.items_tree.bind("<<TreeviewSelect>>", self.on_select_item)

        # === Панель редактирования позиции ===
        edit_frame = ttk.LabelFrame(self.parent, text="Редактировать позицию", padding=8)
        edit_frame.pack(fill=tk.X, padx=10, pady=(5, 10))

        ttk.Label(edit_frame, text="Наименование:").grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.entry_item_name = ttk.Entry(edit_frame, width=40)
        self.entry_item_name.grid(row=0, column=1, sticky="ew", padx=(0, 15))

        ttk.Label(edit_frame, text="Кол-во:").grid(row=0, column=2, sticky="w", padx=(0, 5))
        self.entry_item_quantity = ttk.Entry(edit_frame, width=15)
        self.entry_item_quantity.grid(row=0, column=3, sticky="w", padx=(0, 15))

        ttk.Label(edit_frame, text="Цена:").grid(row=0, column=4, sticky="w", padx=(0, 5))
        self.entry_item_price = ttk.Entry(edit_frame, width=15)
        self.entry_item_price.grid(row=0, column=5, sticky="w", padx=(0, 15))

        ttk.Label(edit_frame, text="Сумма:").grid(row=0, column=6, sticky="w", padx=(0, 5))
        self.entry_item_total = ttk.Entry(edit_frame, width=15)
        self.entry_item_total.grid(row=0, column=7, sticky="w")

        ttk.Label(edit_frame, text="Срок поставки:").grid(row=1, column=0, sticky="w", padx=(0, 5), pady=(8, 0))
        self.entry_item_delivery_term = ttk.Entry(edit_frame, width=15)
        self.entry_item_delivery_term.grid(row=1, column=1, sticky="w", padx=(0, 15), pady=(8, 0))

        ttk.Label(edit_frame, text="Единица:").grid(row=1, column=2, sticky="w", padx=(0, 5), pady=(8, 0))
        self.combo_item_unit = ttk.Combobox(edit_frame, values=["шт.", "комп.", "уп.", "м.", "кг.", "л."],
                                             state="readonly", width=12)
        self.combo_item_unit.grid(row=1, column=3, sticky="w", padx=(0, 15), pady=(8, 0))

        for col in (1, 3, 5):
            edit_frame.grid_columnconfigure(col, weight=1)

        btn_frame2 = ttk.Frame(edit_frame)
        btn_frame2.grid(row=2, column=0, columnspan=8, pady=(10, 0))
        ttk.Button(btn_frame2, text="Сохранить позицию", command=self.save_item).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame2, text="Очистить", command=self.clear_item_form).pack(side=tk.LEFT, padx=5)

        self.load_specs()

    def open_nomenclature(self):
        from dialogs.nomenclature_dialog import NomenclatureDialog
        dialog = NomenclatureDialog(self.root, self.db_manager)
        self.root.wait_window(dialog)

    def open_suppliers(self):
        from dialogs.supplier_dialog import SupplierDialog
        dialog = SupplierDialog(self.root, self.db_manager)
        self.root.wait_window(dialog)

    def open_delivery_addresses(self):
        from dialogs.delivery_address_dialog import DeliveryAddressDialog
        dialog = DeliveryAddressDialog(self.root, self.db_manager)
        self.root.wait_window(dialog)

    # ==================================================================
    # Загрузка таблиц + строка ИТОГО + защиты
    # ==================================================================
    def load_specs(self):
        for item in self.spec_tree.get_children():
            self.spec_tree.delete(item)
        if not self.app.current_project:
            return
        project_id = self.db_manager.get_project_id(self.app.current_project)
        if not project_id:
            return
        specs = self.db_manager.get_purchase_specifications(project_id)

        # Суммируем по валютам
        totals_by_cur = {}
        for spec in specs:
            cur = spec['currency'] or "RUB"
            try:
                val = float(spec['total'] or 0)
            except (TypeError, ValueError):
                val = 0.0
            totals_by_cur[cur] = totals_by_cur.get(cur, 0.0) + val

        def total_values():
            if len(totals_by_cur) == 1:
                cur, val = next(iter(totals_by_cur.items()))
                desc = f"ИТОГО позиций: {len(specs)}"
                total_str = round(val, 2)
                cur_str = cur
            elif totals_by_cur:
                desc = (f"ИТОГО позиций: {len(specs)} | " +
                        "; ".join(f"{c}: {v:,.2f}".replace(",", " ") for c, v in totals_by_cur.items()))
                total_str = ""
                cur_str = "смеш."
            else:
                desc = "ИТОГО позиций: 0"
                total_str = ""
                cur_str = ""
            return ("", "ИТОГО:", desc, total_str, cur_str,
                    "", "", "", "", "", "", "", "")

        # ЕДИНСТВЕННАЯ строка ИТОГО — СВЕРХУ таблицы
        self.spec_tree.insert("", 0, values=total_values(), tags=('total_row',))

        for spec in specs:
            paid_mark = "✓" if spec['fully_paid'] else ""
            received_mark = "✓" if spec['received'] else ""
            self.spec_tree.insert("", tk.END, values=(
                spec['id'], spec['supplier'] or "", spec['name'] or "",
                spec['total'] or 0, spec['currency'] or "",
                spec['delivery_term'] or 0, spec['delivery_unit'] or "",
                spec['payment_date'] or "", spec['delivery_date'] or "",
                paid_mark, received_mark,
                spec['delivery_address'] or "", spec['note'] or ""
            ))

    def _is_total_row(self, item_id):
        return 'total_row' in self.spec_tree.item(item_id)['tags']

    def on_select_spec(self, event):
        selected = self.spec_tree.selection()
        if not selected:
            return
        if self._is_total_row(selected[0]):
            return
        values = self.spec_tree.item(selected[0])['values']
        self.current_spec_id = values[0]
        self.app.current_purchase_spec_id = self.current_spec_id
        self.load_purchase_spec_items()

    def on_double_click_spec(self, event):
        """Обработчик двойного клика - открытие окна оплат"""
        selected = self.spec_tree.selection()
        if not selected:
            return
        if self._is_total_row(selected[0]):
            return
        values = self.spec_tree.item(selected[0])['values']
        spec_id = values[0]
        total_amount = values[3]
        try:
            total_amount = float(total_amount)
        except (TypeError, ValueError):
            total_amount = 0
        if total_amount == 0:
            messagebox.showwarning("Внимание",
                "Сумма спецификации равна 0!\nСначала импортируйте файл или укажите сумму.")
            return
        try:
            dialog = PaymentScheduleDialog(self.root, self.db_manager,
                                            spec_id, total_amount)
            self.root.wait_window(dialog)
        except NameError:
            messagebox.showerror("Ошибка",
                "Модуль PaymentScheduleDialog не найден!\n"
                "Создайте файл dialogs/payment_schedule_dialog.py")
            return
        self.load_specs()
        self.load_purchase_spec_items()

    def load_purchase_spec_items(self):
        for item in self.items_tree.get_children():
            self.items_tree.delete(item)
        if not self.current_spec_id:
            self.lbl_total.config(text="Итого: 0.00 RUB")
            if hasattr(self, 'lbl_total_bottom'):
                self.lbl_total_bottom.config(text="Итого: 0.00 RUB")
            return
        items = self.db_manager.get_purchase_spec_items(self.current_spec_id)
        total = 0
        for idx, item in enumerate(items, start=1):
            item_total = item['total'] or 0
            total += item_total
            self.items_tree.insert("", tk.END, values=(
                item['id'], idx, item['name'] or "",
                item['quantity'] or 0, item['price'] or 0,
                item_total, item['delivery_term'] or "", item['delivery_unit'] or ""
            ))
        text = f"Итого: {total:.2f} RUB"
        self.lbl_total.config(text=text)
        if hasattr(self, 'lbl_total_bottom'):
            self.lbl_total_bottom.config(text=text)

    def on_select_item(self, event):
        selected = self.items_tree.selection()
        if not selected:
            return
        values = self.items_tree.item(selected[0])['values']
        self.current_item_id = values[0]
        self.entry_item_name.delete(0, tk.END)
        self.entry_item_name.insert(0, values[2])
        self.entry_item_quantity.delete(0, tk.END)
        self.entry_item_quantity.insert(0, str(values[3]))
        self.entry_item_price.delete(0, tk.END)
        self.entry_item_price.insert(0, str(values[4]))
        self.entry_item_total.delete(0, tk.END)
        self.entry_item_total.insert(0, str(values[5]))
        self.entry_item_delivery_term.delete(0, tk.END)
        self.entry_item_delivery_term.insert(0, str(values[6]))
        self.combo_item_unit.set(values[7])

    # ==================================================================
    # CRUD
    # ==================================================================
    def add_purchase_spec(self):
        from dialogs.purchase_spec_dialog import PurchaseSpecDialog
        dialog = PurchaseSpecDialog(self.root, "Добавить", None, self.db_manager)
        self.root.wait_window(dialog)
        if dialog.result:
            project_id = self.db_manager.get_project_id(self.app.current_project)
            if project_id:
                self.db_manager.add_purchase_spec(project_id, dialog.result)
                self.load_specs()
                self.app.log_action(f"Добавлена спецификация закупки: {dialog.result.get('supplier', '')}")

    def edit_purchase_spec(self):
        selected = self.spec_tree.selection()
        if selected and self._is_total_row(selected[0]):
            messagebox.showwarning("Внимание", "Строку «ИТОГО» нельзя редактировать!")
            return
        if not self.current_spec_id:
            messagebox.showwarning("Внимание", "Выберите спецификацию!")
            return
        specs = self.db_manager.get_purchase_specifications(
            self.db_manager.get_project_id(self.app.current_project))
        spec_data = None
        for spec in specs:
            if spec['id'] == self.current_spec_id:
                spec_data = dict(spec)
                break
        if not spec_data:
            return
        from dialogs.purchase_spec_dialog import PurchaseSpecDialog
        dialog = PurchaseSpecDialog(self.root, "Редактировать", spec_data, self.db_manager)
        self.root.wait_window(dialog)
        if dialog.result:
            self.db_manager.update_purchase_spec(self.current_spec_id, dialog.result)
            self.load_specs()
            self.app.log_action(f"Отредактирована спецификация закупки #{self.current_spec_id}")

    def delete_purchase_spec(self):
        selected = self.spec_tree.selection()
        if selected and self._is_total_row(selected[0]):
            messagebox.showwarning("Внимание", "Строку «ИТОГО» нельзя удалить!")
            return
        if not self.current_spec_id:
            messagebox.showwarning("Внимание", "Выберите спецификацию!")
            return
        if messagebox.askyesno("Подтверждение", "Удалить спецификацию и все её позиции?"):
            self.db_manager.delete_purchase_spec(self.current_spec_id)
            self.current_spec_id = None
            self.app.current_purchase_spec_id = None
            self.load_specs()
            self.load_purchase_spec_items()
            self.app.log_action(f"Удалена спецификация закупки")

    def add_purchase_spec_item(self):
        if not self.current_spec_id:
            messagebox.showwarning("Внимание", "Сначала выберите спецификацию в верхней таблице!")
            return
        from dialogs.purchase_spec_item_dialog import PurchaseSpecItemDialog
        dialog = PurchaseSpecItemDialog(self.root, "Добавить", None)
        self.root.wait_window(dialog)
        if dialog.result:
            self.db_manager.add_purchase_spec_item(self.current_spec_id, dialog.result)
            self.load_purchase_spec_items()
            self.app.log_action(f"Добавлена позиция в спецификацию #{self.current_spec_id}")

    def edit_purchase_spec_item(self):
        selected = self.items_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите позицию!")
            return
        values = self.items_tree.item(selected[0])['values']
        item_id = values[0]
        items = self.db_manager.get_purchase_spec_items(self.current_spec_id)
        item_data = None
        for item in items:
            if dict(item)['id'] == item_id:
                item_data = dict(item)
                break
        if not item_data:
            return
        from dialogs.purchase_spec_item_dialog import PurchaseSpecItemDialog
        dialog = PurchaseSpecItemDialog(self.root, "Редактировать", item_data)
        self.root.wait_window(dialog)
        if dialog.result:
            self.db_manager.update_purchase_spec_item(item_id, dialog.result)
            self.load_purchase_spec_items()
            self.app.log_action(f"Отредактирована позиция #{item_id}")

    def delete_purchase_spec_item(self):
        selected = self.items_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите позицию для удаления!")
            return
        if messagebox.askyesno("Подтверждение", "Удалить выбранную позицию?"):
            try:
                item_id = self.items_tree.item(selected[0])['values'][0]
                c = self.db_manager.conn.cursor()
                c.execute("DELETE FROM purchase_spec_items WHERE id=?", (item_id,))
                self.db_manager.conn.commit()
                self.current_item_id = None
                self.entry_item_name.delete(0, tk.END)
                self.entry_item_quantity.delete(0, tk.END)
                self.entry_item_price.delete(0, tk.END)
                self.entry_item_total.delete(0, tk.END)
                self.entry_item_delivery_term.delete(0, tk.END)
                self.combo_item_unit.set('')
                self.load_purchase_spec_items()
                if self.current_spec_id:
                    c.execute('''SELECT SUM(total) FROM purchase_spec_items WHERE spec_id=?''',
                            (self.current_spec_id,))
                    total = c.fetchone()[0] or 0
                    c.execute("UPDATE purchase_specifications SET total=? WHERE id=?",
                            (total, self.current_spec_id))
                    self.db_manager.conn.commit()
                    self.load_specs()
                messagebox.showinfo("Успех", f"Позиция #{item_id} удалена")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось удалить позицию:\n{e}")

    def save_item(self):
        if not self.current_item_id:
            messagebox.showwarning("Внимание", "Выберите позицию в нижней таблице!")
            return
        try:
            quantity = float(self.entry_item_quantity.get().replace(',', '.')) if self.entry_item_quantity.get() else 0
            price = float(self.entry_item_price.get().replace(',', '.')) if self.entry_item_price.get() else 0
            total = float(self.entry_item_total.get().replace(',', '.')) if self.entry_item_total.get() else 0
            delivery_term = self.entry_item_delivery_term.get()
        except ValueError:
            messagebox.showwarning("Ошибка", "Некорректное число!")
            return
        item_data = {
            'name': self.entry_item_name.get(),
            'quantity': quantity,
            'price': price,
            'total': total,
            'delivery_term': delivery_term,
            'delivery_unit': self.combo_item_unit.get(),
        }
        self.db_manager.update_purchase_spec_item(self.current_item_id, item_data)
        self.load_purchase_spec_items()
        messagebox.showinfo("Успех", "Позиция сохранена!")

    def clear_item_form(self):
        self.entry_item_name.delete(0, tk.END)
        self.entry_item_quantity.delete(0, tk.END)
        self.entry_item_price.delete(0, tk.END)
        self.entry_item_total.delete(0, tk.END)
        self.entry_item_delivery_term.delete(0, tk.END)
        self.combo_item_unit.set('')
        self.current_item_id = None

    def transfer_total(self):
        if not self.current_spec_id:
            messagebox.showwarning("Внимание", "Выберите спецификацию!")
            return
        total_text = self.lbl_total.cget("text")
        total_match = re.search(r'([\d,\.]+)', total_text)
        if total_match:
            total = float(total_match.group(1).replace(',', '.'))
            c = self.db_manager.conn.cursor()
            c.execute("UPDATE purchase_specifications SET total=? WHERE id=?", (total, self.current_spec_id))
            self.db_manager.conn.commit()
            self.load_specs()
            messagebox.showinfo("Успех", f"Сумма {total:.2f} перенесена в спецификацию")

    # ==================================================================
    # Вспомогательные текстовые функции
    # ==================================================================
    def clean_text(self, text):
        """Удаляет HTML теги (<br>) и переносы строк из текста"""
        if not text:
            return ""
        s = str(text)
        s = re.sub(r'<br\s*/?>', ' ', s, flags=re.IGNORECASE)
        s = re.sub(r'<[^>]+>', ' ', s)
        s = s.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ')
        s = re.sub(r'\s+', ' ', s)
        s = re.sub(r'\s+([,.;:!?])', r'\1', s)
        return s.strip()

    def fix_latin_chars(self, text):
        """Исправляет латинские буквы, похожие на кириллические, в аббревиатурах ООО/АО"""
        if not text:
            return text
        text = re.sub(r'[OОo]{3}', 'ООО', text)
        text = re.sub(r'A[oO]', 'АО', text)
        return text

    def _rows_look_valid(self, rows):
        """True, если среди строк есть хотя бы одна, похожая на позицию товара:
        непустое наименование + кол-во > 0 + (цена или сумма) > 0.
        Используется вместо жёсткого порога 'строк >= 2', чтобы не терять
        однопозиционные счета (например, СИКРАФТ УТ-7042)."""
        if not rows:
            return False
        for row in rows:
            if not row or len(row) < 3:
                continue
            name = self.clean_text(row[2] if len(row) > 2 and row[2] else "")
            try:
                qty = float(str(row[3]).replace(',', '.').replace(' ', '')) if len(row) > 3 and row[3] else 0
            except (TypeError, ValueError):
                qty = 0
            try:
                price = float(str(row[5]).replace("'", "").replace(',', '.').replace(' ', '')) if len(row) > 5 and row[5] else 0
            except (TypeError, ValueError):
                price = 0
            try:
                total = float(str(row[6]).replace("'", "").replace(',', '.').replace(' ', '')) if len(row) > 6 and row[6] else 0
            except (TypeError, ValueError):
                total = 0
            if name and qty > 0 and (price > 0 or total > 0):
                return True
        return False

    # ==================================================================
    # Поиск поставщика (ШАГИ 0–6)
    # ==================================================================
    def find_supplier_in_invoice(self, full_text):
        normalized = re.sub(r'<[^>]+>', ' ', full_text)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        normalized = self.fix_latin_chars(normalized)

        print(f"\n{'='*60}")
        print(f"=== ПОИСК ПОСТАВЩИКА ===")
        print(f"Нормализованный текст (первые 500 симв.): {normalized[:500]}...")

        org_replacements = {
            r'Общество\s+с\s+ограниченной\s+ответственностью': 'ООО',
            r'Акционерное\s+общество': 'АО',
            r'Открытое\s+акционерное\s+общество': 'ОАО',
            r'Закрытое\s+акционерное\s+общество': 'ЗАО',
            r'Публичное\s+акционерное\s+общество': 'ПАО',
            r'Индивидуальный\s+предприниматель': 'ИП',
        }

        def normalize_org_type(text):
            for full_name, short_name in org_replacements.items():
                text = re.sub(full_name, short_name, text, flags=re.IGNORECASE)
            return text

        def extract_org_and_inn(text_segment):
            fixed_segment = self.fix_latin_chars(text_segment)
            pattern = r'(ООО|АО|ИП|ОАО|ЗАО|ПАО)\s*[«"]([^»"]+?)[»"]\s*,?\s*ИНН\s*(\d{10,12})'
            match = re.search(pattern, fixed_segment, re.IGNORECASE)
            if match:
                org_type = match.group(1)
                org_name = match.group(2).strip().rstrip(',.;:')
                inn = match.group(3)
                org_name = re.split(r'[,;\s]*(?:КПП|Адрес|г\.|ул\.|ИНН)', org_name)[0].strip()
                return f'{org_type} "{org_name}"', inn
            soft_pattern = r'(ООО|АО|ИП|ОАО|ЗАО|ПАО)\s*[«"]([^»"]+?)[»"]'
            match = re.search(soft_pattern, fixed_segment, re.IGNORECASE)
            if match:
                org_type = match.group(1)
                org_name = match.group(2).strip().rstrip(',.;:')
                org_name = re.split(r'[,;\s]*(?:КПП|Адрес|г\.|ул\.|ИНН)', org_name)[0].strip()
                inn_match = re.search(r'ИНН\s*(\d{10,12})', fixed_segment)
                inn = inn_match.group(1) if inn_match else ""
                return f'{org_type} "{org_name}"', inn
            return None, None

        def get_buyer_info(norm_text):
            """Собирает ИНН/названия покупателей.
            Сегмент учитывается ТОЛЬКО если сразу после метки идёт организация
            (ООО/АО/ИП/Общество…/«…»/ИНН…) и в пределах 200 символов.
            Это отсекает пустые метки в шапке (ЭД609) и текстовые упоминания
            вида «Покупатель выражает согласие … ООО"ЭлектроДом"» (оферта = поставщик)."""
            buyer_inns = set()
            buyer_names = set()
            buyer_patterns = [
                r'Покупатель[:\s]*([^\n]{5,500}?)(?=\s+(?:Основание|№|Грузополучатель|$))',
                r'Грузополучатель[:\s]*([^\n]{5,500}?)(?=\s+(?:Основание|№|$))',
                r'Заказчик[:\s]*([^\n]{5,500}?)(?=\s+(?:Основание|№|$))',
                r'Плательщик[:\s]*([^\n]{5,500}?)(?=\s+(?:Основание|№|$))',
            ]
            org_start_re = re.compile(
                r'\s*(?:ООО|ОАО|ЗАО|ПАО|АО|ИП|Общество|Акционерное|ИНН\s*\d|[«"])',
                re.IGNORECASE)
            for pattern in buyer_patterns:
                matches = list(re.finditer(pattern, norm_text, re.IGNORECASE))
                for m in matches:
                    segment = m.group(1)[:200]
                    if not org_start_re.match(segment):
                        continue
                    for inn in re.findall(r'ИНН\s*(\d{10,12})', segment):
                        buyer_inns.add(inn)
                    for nm in re.findall(r'[«"]([^»"]{3,80}?)[»"]', segment):
                        buyer_names.add(nm.strip().lower())
            print(f"Найденные ИНН покупателей: {buyer_inns}")
            print(f"Найденные названия покупателей: {buyer_names}")
            return buyer_inns, buyer_names

        def is_valid_supplier(supplier_name, supplier_inn, buyer_inns, buyer_names):
            if supplier_inn and supplier_inn in buyer_inns:
                print(f"⚠ '{supplier_name}' с ИНН {supplier_inn} = ПОКУПАТЕЛЬ, отклоняем!")
                return False
            if supplier_name:
                clean_name = re.sub(r'^[A-ZА-Я]+\s*["«]?', '', supplier_name)
                clean_name = re.sub(r'["»]$', '', clean_name).strip().lower()
                for bn in buyer_names:
                    if bn in clean_name or clean_name in bn:
                        print(f"⚠ '{supplier_name}' совпадает с покупателем '{bn}', отклоняем!")
                        return False
            return True

        buyer_inns, buyer_names = get_buyer_info(normalized)

        # ШАГ 0: Через "Получатель" в банковских реквизитах
        poluchatel_patterns = [
            r'([«"][^»"]{3,80}?[»"])\s*Получатель',
            r'Получатель.{0,100}?([«"][^»"]{3,80}?[»"])',
            r'([«"][^»"]{3,80}?[»"]).{0,50}?Получатель',
        ]
        for pat in poluchatel_patterns:
            match = re.search(pat, normalized, re.IGNORECASE | re.DOTALL)
            if match:
                org_name_raw = match.group(1).strip('«»""').strip()
                context = normalized[max(0, match.start()-300):match.end()+300]
                inn_match = re.search(r'ИНН\s*(\d{10,12})', context)
                supplier_inn = inn_match.group(1) if inn_match else ""
                type_before = normalized[max(0, match.start()-50):match.start()]
                org_type = "ООО"
                for t in ['АО', 'ПАО', 'ОАО', 'ЗАО']:
                    if t in type_before.upper():
                        org_type = t
                        break
                supplier_name = f'{org_type} "{org_name_raw}"'
                if is_valid_supplier(supplier_name, supplier_inn, buyer_inns, buyer_names):
                    print(f"✓ [ШАГ 0] НАЙДЕН ЧЕРЕЗ 'Получатель' -> {supplier_name}, ИНН={supplier_inn}")
                    return supplier_name, supplier_inn

        # ШАГ 1: "Грузоотправитель:"
        gruzootpr_pattern = r'Грузоотправитель[:\s]*([^\n]{5,300}?)(?=\s+(?:Покупатель|Основание|№|$))'
        match = re.search(gruzootpr_pattern, normalized, re.IGNORECASE)
        if match:
            segment = match.group(1).strip()
            supplier_name, supplier_inn = extract_org_and_inn(segment)
            if supplier_name and is_valid_supplier(supplier_name, supplier_inn, buyer_inns, buyer_names):
                print(f"✓ [ШАГ 1] НАЙДЕН ЧЕРЕЗ 'Грузоотправитель:' -> {supplier_name}, ИНН={supplier_inn}")
                return supplier_name, supplier_inn

        # ШАГ 2 (СТАРЫЯ ЛОГИКА): "Поставщик:", "Исполнитель:", "Продавец:"
        old_supplier_patterns = [
            r'Поставщик\s*[:\(]?\s*(.+?)(?:,|ИНН|КПП|\n)',
            r'Исполнитель\s*[:\(]?\s*(.+?)(?:,|ИНН|КПП|\n)',
            r'Продавец\s*[:\(]?\s*(.+?)(?:,|ИНН|КПП|\n)',
        ]
        for pattern in old_supplier_patterns:
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                org_text = match.group(1).strip()
                org_text_normalized = normalize_org_type(org_text)
                supplier_name, supplier_inn = extract_org_and_inn(org_text_normalized)
                if supplier_name:
                    context_start = max(0, match.start() - 100)
                    context_end = min(len(normalized), match.end() + 100)
                    context_before = normalized[context_start:match.start()]
                    context_after = normalized[match.end():context_end]
                    buyer_markers = ['Покупатель', 'Грузополучатель', 'Заказчик', 'Плательщик']
                    combined_context = (context_before + ' ' + context_after).upper()
                    is_near_buyer = any(marker.upper() in combined_context for marker in buyer_markers)
                    if not is_near_buyer and is_valid_supplier(supplier_name, supplier_inn, buyer_inns, buyer_names):
                        print(f"✓ [ШАГ 2] НАЙДЕН ЧЕРЕЗ старый маркер -> {supplier_name}, ИНН={supplier_inn}")
                        return supplier_name, supplier_inn
                    else:
                        print(f"⚠ [ШАГ 2] '{supplier_name}' отклонена (покупатель рядом)")

        # ШАГ 3: Вложенный "Грузоотправитель:" внутри "Поставщик:"
        complex_postavshik_pattern = r'Поставщик[:\s]*([^\n]{5,800}?)(?=\s+Основание|$)'
        match = re.search(complex_postavshik_pattern, normalized, re.IGNORECASE)
        if match:
            segment = match.group(1).strip()
            inner_gruz_match = re.search(r'Грузоотправитель[:\s]*(.+?)$', segment, re.IGNORECASE)
            if inner_gruz_match:
                inner_segment = inner_gruz_match.group(1)
                supplier_name, supplier_inn = extract_org_and_inn(inner_segment)
                if supplier_name and is_valid_supplier(supplier_name, supplier_inn, buyer_inns, buyer_names):
                    print(f"✓ [ШАГ 3] НАЙДЕН ЧЕРЕЗ вложенный 'Грузоотправитель:' -> {supplier_name}, ИНН={supplier_inn}")
                    return supplier_name, supplier_inn
            all_orgs = re.finditer(
                r'(ООО|АО|ИП|ОАО|ЗАО|ПАО)\s*[«"]([^»"]+?)[»"]\s*,?\s*ИНН\s*(\d{10,12})',
                segment, re.IGNORECASE
            )
            for m in all_orgs:
                org_type = m.group(1)
                org_name = m.group(2).strip().rstrip(',.;:')
                inn = m.group(3)
                org_name = re.split(r'[,;\s]*(?:КПП|Адрес|г\.|ул\.|ИНН)', org_name)[0].strip()
                candidate_name = f'{org_type} "{org_name}"'
                if is_valid_supplier(candidate_name, inn, buyer_inns, buyer_names):
                    print(f"✓ [ШАГ 3] НАЙДЕН КАК ПЕРВАЯ ВАЛИДНАЯ ОРГАНИЗАЦИЯ В СЕГМЕНТЕ -> {candidate_name}, ИНН={inn}")
                    return candidate_name, inn

        # ШАГ 4: Первая организация до границы Покупатель/Грузополучатель
        purchase_pos = normalized.find('Покупатель')
        gruzopoluchatel_pos = normalized.find('Грузополучатель')
        boundaries = [p for p in [purchase_pos, gruzopoluchatel_pos] if p > 0]
        boundary_pos = min(boundaries) if boundaries else len(normalized)
        sale_part = normalized[:boundary_pos]
        first_org_pattern = r'(ООО|АО|ИП|ОАО|ЗАО|ПАО)\s*[«"]([^»"]+?)[»"]\s*,?\s*ИНН\s*(\d{10,12})'
        matches = list(re.finditer(first_org_pattern, sale_part, re.IGNORECASE))
        if matches:
            for m in matches:
                org_type = m.group(1)
                org_name = m.group(2).strip().rstrip(',.;:')
                inn = m.group(3)
                org_name = re.split(r'[,;\s]*(?:КПП|Адрес|г\.|ул\.|ИНН)', org_name)[0].strip()
                candidate_name = f'{org_type} "{org_name}"'
                if is_valid_supplier(candidate_name, inn, buyer_inns, buyer_names):
                    print(f"✓ [ШАГ 4] НАЙДЕН КАК ПЕРВАЯ ВАЛИДНАЯ ОРГАНИЗАЦИЯ ДО ГРАНИЦЫ -> {candidate_name}, ИНН={inn}")
                    return candidate_name, inn

        # ШАГ 5 (FALLBACK): первая в документе организация с ИНН —
        # аббревиатура ИЛИ полное наименование, если она НЕ покупатель.
        any_org_pattern = (r'(Общество\s+с\s+ограниченной\s+ответственностью|'
                           r'Акционерное\s+общество|'
                           r'ООО|АО|ИП|ОАО|ЗАО|ПАО)\s*[«"]([^»"]{3,80}?)[»"]\s*,?\s*ИНН\s*(\d{10,12})')
        for m in re.finditer(any_org_pattern, normalized, re.IGNORECASE):
            org_type = normalize_org_type(m.group(1)).strip()
            org_name = m.group(2).strip().rstrip(',.;:')
            inn = m.group(3)
            org_name = re.split(r'[,;\s]*(?:КПП|Адрес|г\.|ул\.|ИНН)', org_name)[0].strip()
            candidate_name = f'{org_type} "{org_name}"'
            if inn in buyer_inns:
                continue
            if any(bn in org_name.lower() or org_name.lower() in bn for bn in buyer_names):
                continue
            if is_valid_supplier(candidate_name, inn, buyer_inns, buyer_names):
                print(f"✓ [ШАГ 5] FALLBACK (первая орг. с ИНН) -> {candidate_name}, ИНН={inn}")
                return candidate_name, inn

        # ШАГ 6: иностранные компании без ИНН (LTD / LLC / GmbH / SISTEMLERI / STI …)
        m = re.search(r'([A-Z][A-Z0-9&\.\- ]{4,90}?'
                      r'(?:LTD|LLC|INC|GMBH|CORP|SISTEMLERI|SISTEMLER|SYSTEMS|TECHNOLOGIES|STI|ŞTİ)'
                      r'(?:\s+[A-Z\.]{2,6}\.?)*)', normalized)
        if m:
            cand = m.group(1).strip(' .,-')
            if len(cand) >= 8:
                print(f"✓ [ШАГ 6] FALLBACK иностранная компания -> {cand}")
                return cand, ""

        print("✗ ПОСТАВЩИК НЕ НАЙДЕН НИ ОДНИМ СПОСОБОМ")
        return None, None

    # ==================================================================
    # Общий текстовый парсер (fallback)
    # ==================================================================
    def _try_parse_item_line(self, line, fallback_number):
        parts_v1 = [p.strip() for p in re.split(r'\s{2,}', line) if p.strip()]
        parts_v2 = line.split()
        parts = parts_v1 if len(parts_v1) >= 3 else parts_v2
        if len(parts) < 3:
            return None
        numeric_tokens = []
        text_tokens = []
        unit_candidates = ['шт', 'шт.', 'уп', 'упак', 'уп.', 'компл', 'комплект',
                          'м', 'м.', 'кг', 'кг.', 'л', 'л.', 'боб', 'бухта', 'рулон',
                          'партия', 'набор', 'пара', 'тыс', 'тыс.', 'усл', 'усл.']
        units_found = []
        for i, part in enumerate(parts):
            cleaned = part.replace(' ', '').replace('\xa0', '').replace("'", '')
            cleaned = cleaned.replace('₽', '').replace('руб', '').replace('РУБ', '')
            cleaned = cleaned.replace(',', '.')
            try:
                val = float(cleaned)
                if val > 0:
                    numeric_tokens.append((i, part, val))
                    continue
            except:
                pass
            if part.lower().strip('. ') in unit_candidates:
                units_found.append(part)
                continue
            text_tokens.append((i, part))
        if len(numeric_tokens) < 2 or not text_tokens:
            return None
        number = str(fallback_number)
        if parts and parts[0].isdigit() and len(parts[0]) <= 3:
            number = parts[0]
        nums_sorted_by_value = sorted(numeric_tokens, key=lambda x: x[2])
        quantity = price = total = 0
        if len(nums_sorted_by_value) >= 3:
            quantity = nums_sorted_by_value[0][2]
            price = nums_sorted_by_value[1][2]
            total = nums_sorted_by_value[2][2]
        elif len(nums_sorted_by_value) == 2:
            quantity = nums_sorted_by_value[0][2]
            total = nums_sorted_by_value[1][2]
            if quantity > 0:
                price = total / quantity
        if quantity <= 0:
            return None
        name_parts = [t[1] for t in text_tokens]
        name = ' '.join(name_parts).strip()
        article_code = ""
        if len(name_parts) > 2:
            potential_article = ' '.join(name_parts[:2])
            rest_of_name = ' '.join(name_parts[2:])
            if '-' in potential_article or any(c.isdigit() for c in potential_article):
                article_code = potential_article
                name = rest_of_name if rest_of_name.strip() else potential_article
        unit = units_found[0] if units_found else "шт."
        delivery = ""
        full_lower = line.lower()
        if 'раб' in full_lower:
            m = re.search(r'(от\s+\d+\s+до\s+\d+\s*раб\.?\s*дн|до\s+\d+\s*раб\.?\s*дн|\d+\s*раб\.?\s*дн)', full_lower)
            if m:
                delivery = m.group(1)
        elif 'нед' in full_lower:
            m = re.search(r'(от\s+\d+\s+до\s+\d+\s*нед|\d+\s*нед)', full_lower)
            if m:
                delivery = m.group(1)
        elif 'наличии' in full_lower:
            delivery = "в наличии"
        return [
            number, article_code, name,
            str(int(quantity)) if quantity == int(quantity) else f"{quantity:.2f}",
            unit, f"{price:.2f}", f"{total:.2f}", delivery, "", "", "RUB"
        ]

    def parse_invoice_from_text(self, text):
        rows = []
        lines = text.split('\n')
        print(f"=== TEXT PARSE v2: анализ {len(lines)} строк ===")
        in_items_section = False
        for line_num, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            upper_line = re.sub(r'\s+', '', stripped.upper())
            start_markers = ['НАИМЕНОВАНИЕ', 'ТОВАРЫ', 'ТОВАР', 'АРТИКУЛ', 'КОД']
            has_number_col = '№' in stripped or 'N.' in upper_line
            if has_number_col and any(m in upper_line for m in start_markers):
                in_items_section = True
                print(f"Строка {line_num}: НАЧАЛО ТАБЛИЦЫ ТОВАРОВ -> '{stripped[:80]}'")
                continue
            if in_items_section:
                end_markers_upper = ['ИТОГО', 'ВСЕГО', 'НАИМЕНОВАНИЙ', 'ОБЩАЯСУММА',
                                     'СПРАВОЧНО', 'УСЛОВИЯ', 'ГЕН.', 'ГЛ.']
                compact_line = re.sub(r'\s+', '', upper_line)
                if any(m in compact_line for m in end_markers_upper):
                    print(f"Строка {line_num}: КОНЕЦ ТАБЛИЦЫ ТОВАРОВ -> '{stripped[:80]}'")
                    break
                parsed_row = self._try_parse_item_line(stripped, len(rows) + 1)
                if parsed_row:
                    rows.append(parsed_row)
                    print(f"  ✓ Строка {len(rows)}: №{parsed_row[0]}, '{parsed_row[2][:40]}...', qty={parsed_row[3]}, price={parsed_row[5]}, total={parsed_row[6]}")
        print(f"=== TEXT PARSE ЗАВЕРШЁН: найдено {len(rows)} строк ===")
        return rows

    # ==================================================================
    # Словари единиц измерения (общие для всех парсеров)
    # ==================================================================
    EKF_UNIT_TOKENS = {'шт', 'ш', 'уп', 'упак', 'компл', 'комплект', 'м', 'кг', 'л',
                       'боб', 'бухта', 'рулон', 'пара', 'набор', 'тыс', 'усл'}
    EKF_UNIT_NORM = {'ш': 'шт.', 'шт': 'шт.', 'уп': 'упак.', 'упак': 'упак.',
                     'компл': 'компл.', 'комплект': 'комплект', 'м': 'м.', 'кг': 'кг.',
                     'л': 'л.', 'боб': 'боб.', 'бухта': 'бухта', 'рулон': 'рулон',
                     'пара': 'пара', 'набор': 'набор', 'тыс': 'тыс.', 'усл': 'усл.'}

    def _assemble_number_from_fragments(self, fragment_list):
        """Собирает число из фрагментов: ['20','378',',01'] -> 20378.01"""
        if not fragment_list:
            return None
        combined = ''.join(str(f) for f in fragment_list)
        combined = re.sub(r'[,]{2,}', ',', combined)
        combined = re.sub(r'[.]{2,}', '.', combined)
        combined = combined.replace(' ', '').replace('\xa0', '')
        try:
            return float(combined.replace(',', '.'))
        except ValueError:
            pass
        try:
            return float(combined.replace(',', ''))
        except ValueError:
            return None

    def _ekf_reconstruct_name(self, text_parts):
        """Склеивает фрагменты наименования: продолжение слова — без пробела."""
        cleaned_parts = []
        for p in text_parts:
            p = re.sub(r'<br\s*/?>', ' ', str(p), flags=re.IGNORECASE)
            p = re.sub(r'\s+', ' ', p).strip()
            if p:
                cleaned_parts.append(p)
        out = ""
        for i, part in enumerate(cleaned_parts):
            if i == 0:
                out = part
            else:
                prev_last = out[-1] if out else ''
                curr_first = part[0] if part else ''
                last_word = out.split(' ')[-1] if out else ''
                glue = False
                if curr_first.islower() and not part.startswith(' '):
                    if prev_last.islower() or prev_last.isdigit():
                        glue = True
                    elif prev_last.isupper() and len(last_word) == 1:
                        glue = True
                if glue:
                    out += part
                else:
                    out += ' ' + part
        return out.strip()

    def _tok_is_num(self, t):
        t = t.strip()
        return bool(re.fullmatch(r'\d+(?:[.,]\d+)?', t)) or bool(re.fullmatch(r',\d+', t))

    # ==================================================================
    # ПРИОРИТЕТ 0: PIPE-СТРУКТУРНЫЕ СТРОКИ (Кабель.РФ, ВсеИнструменты)
    # ==================================================================
    def _parse_pipe_structured_rows(self, full_text):
        rows = []
        lines = full_text.split('\n')
        print(f"=== PIPE STRUCTURED PARSER: анализ {len(lines)} строк ===")
        for line in lines:
            s = line.strip()
            if s.count('|') < 4:
                continue
            cells = [c.strip() for c in s.split('|')]
            while cells and cells[0] == '':
                cells.pop(0)
            while cells and cells[-1] == '':
                cells.pop()
            if len(cells) < 5:
                continue
            if all(re.fullmatch(r'[\-:\s]*', c or '') for c in cells):
                continue
            joined = ''.join(cells).upper()
            if 'НАИМЕНОВАНИЕ' in joined and ('КОЛ-ВО' in joined or 'КОЛВО' in joined
                                             or 'ЦЕНА' in joined or 'ТОВАР' in joined):
                continue
            if not re.fullmatch(r'\d{1,4}', cells[0]):
                continue
            number = cells[0]

            unit_idx = -1
            unit = 'шт.'
            for i, c in enumerate(cells):
                cl = c.lower().strip('. ')
                if cl in self.EKF_UNIT_TOKENS:
                    unit_idx = i
                    unit = self.EKF_UNIT_NORM.get(cl, c)
                    break
            if unit_idx < 3:
                continue

            qty = self._assemble_number_from_fragments([cells[unit_idx - 1]]) or 0
            if qty <= 0:
                continue

            article = ''
            start = 1
            if (not re.search(r'[а-яА-ЯёЁ]', cells[1])
                    and re.fullmatch(r'[\dA-Za-z\-\._\s]{3,24}', cells[1])):
                article = cells[1]
                start = 2
            mid = cells[start:unit_idx - 1]
            delivery_parts = [c for c in mid if re.search(r'раб|нед|наличии|заказ|дн', c, re.I)]
            name_parts = [c for c in mid if c not in delivery_parts]
            name = self.clean_text(' '.join(name_parts))
            if not name:
                continue
            delivery = self.clean_text(' '.join(delivery_parts))

            chains = []
            notes = []
            for c in cells[unit_idx + 1:]:
                if re.fullmatch(r'[\d\s.,]+', c):
                    v = self._assemble_number_from_fragments([c])
                    if v is not None:
                        chains.append(v)
                elif c:
                    notes.append(c)

            price, total = 0.0, 0.0
            best = None
            for i in range(len(chains)):
                for j in range(i + 1, len(chains)):
                    ci, cj = chains[i], chains[j]
                    if cj > 0 and abs(qty * ci - cj) <= max(0.02 * cj, 0.5):
                        if best is None or cj > best[1]:
                            best = (ci, cj)
            if best:
                price, total = best
            elif len(chains) >= 2:
                price, total = chains[0], chains[-1]
            elif len(chains) == 1:
                total = chains[0]
                price = round(total / qty, 2) if qty else 0.0
            if total <= 0:
                continue

            qty_str = str(int(qty)) if qty == int(qty) else f"{qty:.3f}".rstrip('0').rstrip('.')
            rows.append([
                number, article, name, qty_str, unit,
                f"{price:.2f}", f"{total:.2f}", delivery, '', ' '.join(notes), 'RUB'
            ])
            print(f"  ✓ [PIPE] №{number} '{name[:40]}...' qty={qty_str} "
                  f"price={price:.2f} total={total:.2f} {unit}")
        print(f"=== PIPE STRUCTURED PARSER ЗАВЕРШЁН: найдено {len(rows)} позиций ===")
        return rows

    # ==================================================================
    # ПРИОРИТЕТ 1: ТОКЕННАЯ ГРАММАТИКА (EKF)
    # ==================================================================
    def _numeric_chains(self, tokens):
        """Группировка чисел по правилу запятой: фрагменты одного числа идут подряд
        и ЗАКАНЧИВАЮТСЯ токеном с запятой (',01' / '378,01' / '0,01')."""
        chains = []
        cur = []
        for t in tokens:
            ts = t.strip()
            if not self._tok_is_num(ts):
                if cur:
                    v = self._assemble_number_from_fragments(cur)
                    if v is not None:
                        chains.append(v)
                    cur = []
                continue
            cur.append(ts)
            if ',' in ts:
                v = self._assemble_number_from_fragments(cur)
                if v is not None:
                    chains.append(v)
                cur = []
        if cur:
            v = self._assemble_number_from_fragments(cur)
            if v is not None:
                chains.append(v)
        return chains

    def _parse_token_line(self, tokens):
        if not tokens or len(tokens) < 6:
            return None

        unit_idx = -1
        unit = 'шт.'
        for i in range(len(tokens) - 1, -1, -1):
            tl = tokens[i].lower().strip('. ')
            if tl in self.EKF_UNIT_TOKENS:
                unit_idx = i
                unit = tokens[i].strip()
                if tl == 'уп' and i + 1 < len(tokens) and tokens[i + 1].lower().startswith('ак'):
                    unit = 'упак.'
                elif tl == 'ш':
                    unit = 'шт.'
                elif tl == 'м':
                    unit = 'м.'
                elif tl == 'компл':
                    unit = 'компл.'
                break
        if unit_idx < 2:
            return None

        j = unit_idx - 1
        qty_tokens = []
        while j >= 0 and self._tok_is_num(tokens[j]):
            qty_tokens.insert(0, tokens[j])
            j -= 1
        if not qty_tokens:
            return None
        qty = self._assemble_number_from_fragments(qty_tokens) or 0
        if qty > 100000 and len(qty_tokens) > 1:
            qty = self._assemble_number_from_fragments(qty_tokens[-1:]) or 0
        qty_start = j + 1
        if qty <= 0:
            return None

        number = tokens[0] if re.fullmatch(r'\d{1,3}', tokens[0]) else ""

        a = 1 if re.fullmatch(r'\d{1,3}', tokens[0]) else 0
        art_tokens = []
        while a < qty_start:
            tkn = tokens[a]
            if re.fullmatch(r'[a-z0-9\-\.\_]+', tkn):
                art_tokens.append(tkn)
                a += 1
                continue
            if (not re.search(r'[а-яА-ЯёЁ]', tkn)) and tkn.isascii() \
                    and re.search(r'[-0-9]', tkn) and len(tkn) <= 8:
                art_tokens.append(tkn)
                a += 1
                continue
            break
        article = ''.join(art_tokens)

        name_tokens = tokens[a:qty_start]
        cut = len(name_tokens)
        for k in range(len(name_tokens)):
            tk = name_tokens[k].lower()
            if tk in ('под', 'в') and k + 1 < len(name_tokens) and name_tokens[k + 1].lower() in ('заказ', 'наличии'):
                cut = k
                break
            if tk == 'от' and k + 1 < len(name_tokens) and name_tokens[k + 1].isdigit():
                cut = k
                break
        name_tokens = name_tokens[:cut]
        name = self._ekf_reconstruct_name(name_tokens)
        if not name:
            return None

        chains = self._numeric_chains(tokens[unit_idx + 1:])
        if not chains:
            return None

        price = 0.0
        total = 0.0
        best = None
        for i in range(len(chains)):
            for jj in range(i + 1, len(chains)):
                ci, cj = chains[i], chains[jj]
                if cj > 0 and abs(qty * ci - cj) <= max(0.02 * cj, 0.5):
                    if best is None or cj > best[1]:
                        best = (ci, cj)
        if best:
            price, total = best
        else:
            total = max(chains)
            price = round(total / qty, 2) if qty else 0.0
        if total <= 0:
            return None

        return [
            number, article, name,
            str(int(qty)) if qty == int(qty) else f"{qty:.2f}",
            unit, f"{price:.2f}", f"{total:.2f}", "", "", "", "RUB"
        ]

    def _parse_invoice_by_grammar(self, full_text):
        rows = []
        lines = full_text.split('\n')
        started = False
        auto = 0
        print(f"=== TOKEN GRAMMAR PARSER: анализ {len(lines)} строк ===")
        for ln in lines:
            s = ln.strip()
            if not s:
                continue
            comp = re.sub(r'\s+', '', s.upper())
            if not started:
                if ('№' in s) and ('АРТИКУЛ' in comp or 'КОД' in comp) \
                        and ('ЦЕНА' in comp or 'КОЛВО' in comp or 'КОЛ-ВО' in comp):
                    started = True
                    print(f"Найден заголовок таблицы: '{s[:70]}'")
                continue
            if any(k in comp for k in ['СПРАВОЧНО', 'ИТОГО:', 'ИТОГОК', 'ВСЕГОНАИМЕНОВАНИЙ',
                                       'ВТОМЧИСЛЕ', 'УСЛОВИЯОПЛАТЫ']):
                print(f"Конец таблицы: '{s[:70]}'")
                break
            if re.match(r'^[\|\-\s:]+$', s):
                continue
            tokens = s.split()
            parsed = self._parse_token_line(tokens)
            if parsed:
                auto += 1
                if not parsed[0]:
                    parsed[0] = str(auto)
                rows.append(parsed)
                print(f"  ✓ Позиция {len(rows)}: №{parsed[0]} арт='{parsed[1][:14]}' "
                      f"'{parsed[2][:40]}...' qty={parsed[3]} price={parsed[5]} total={parsed[6]} {parsed[4]}")
        print(f"=== TOKEN GRAMMAR PARSER ЗАВЕРШЁН: найдено {len(rows)} позиций ===")
        return rows

    # ==================================================================
    # ПРИОРИТЕТ 2: ПОТОКОВЫЙ ПАРСЕР ОБЛАСТИ ТАБЛИЦЫ
    # ==================================================================
    STREAM_STOP_WORDS = {'от', 'до', 'раб.дн.', 'раб', 'дн.', 'заказ', 'под',
                         'наличии', 'есть', 'нет', 'шт', 'упак', 'комплекта'}

    def _parse_region_stream(self, full_text):
        """Находит области таблиц товаров и парсит их как единый поток токенов."""
        lines = full_text.split('\n')
        rows = []
        i = 0
        n = len(lines)
        while i < n:
            s = lines[i].strip()
            comp = re.sub(r'\s+', '', s.upper())
            if ('№' in s) and ('НАИМЕНОВАНИЕ' in comp or 'ТОВАР' in comp) \
                    and ('КОЛ-ВО' in comp or 'КОЛВО' in comp or 'ЦЕНА' in comp):
                j = i + 1
                region_lines = []
                while j < n:
                    t = lines[j].strip()
                    tc = re.sub(r'\s+', '', t.upper())
                    if any(k in tc for k in ['ВСЕГОНАИМЕНОВАНИЙ', 'ИТОГО:', 'СПРАВОЧНО',
                                             'УСЛОВИЯОПЛАТЫ', 'ВТОМЧИСЛЕ', 'ВСЕГООПЛАТЕ']):
                        break
                    if t:
                        region_lines.append(t)
                    j += 1
                if region_lines:
                    print(f"=== STREAM PARSER: область строк {i}..{j}, "
                          f"{len(region_lines)} строк склеено ===")
                    rows.extend(self._parse_stream_rows(' '.join(region_lines)))
                i = j + 1
                continue
            i += 1
        print(f"=== STREAM PARSER ЗАВЕРШЁН: найдено {len(rows)} позиций ===")
        return rows

    def _parse_stream_rows(self, region):
        """Парсит склеенную область таблицы: якорь = единица измерения."""
        tokens = region.split()
        rows = []
        idx = 0
        auto = 0
        while idx < len(tokens):
            tl = tokens[idx].lower().strip('. ')
            if tl not in self.EKF_UNIT_TOKENS:
                idx += 1
                continue
            unit_idx = idx

            qty_tokens = []
            k = unit_idx - 1
            while k >= 0 and self._tok_is_num(tokens[k]):
                qty_tokens.insert(0, tokens[k])
                k -= 1
            if not qty_tokens:
                idx += 1
                continue
            if any(',' in t for t in qty_tokens):
                qty = self._assemble_number_from_fragments(qty_tokens) or 0
            elif len(qty_tokens) > 1:
                qty = self._assemble_number_from_fragments([qty_tokens[-1]]) or 0
            else:
                qty = self._assemble_number_from_fragments(qty_tokens) or 0
            if qty <= 0 or qty > 100000:
                idx += 1
                continue
            qty_start = k + 1

            name_tokens = []
            number = ''
            p = qty_start - 1
            while p >= 0:
                tk = tokens[p]
                if tk.lower().strip('. ') in self.STREAM_STOP_WORDS:
                    break
                if re.fullmatch(r'\d{1,4}', tk):
                    number = tk
                    break
                name_tokens.insert(0, tk)
                p -= 1
                if len(name_tokens) > 60:
                    break
            header_words = {'цена', 'сумма', '(сндс)', 'сндс', 'ед.', 'кол-во',
                            'наименование', 'примечание', 'артикул', 'товар', 'объем', 'м3'}
            while name_tokens and name_tokens[0].lower().strip('. ') in header_words:
                name_tokens.pop(0)

            chains = []
            q = unit_idx + 1
            cur = []
            while q < len(tokens):
                if self._tok_is_num(tokens[q]):
                    cur.append(tokens[q])
                    q += 1
                    if ',' in tokens[q - 1]:
                        v = self._assemble_number_from_fragments(cur)
                        if v is not None:
                            chains.append(v)
                        cur = []
                else:
                    if cur:
                        v = self._assemble_number_from_fragments(cur)
                        if v is not None:
                            chains.append(v)
                        cur = []
                    break
            if cur:
                v = self._assemble_number_from_fragments(cur)
                if v is not None:
                    chains.append(v)
            if len(chains) < 2:
                idx = unit_idx + 1
                continue

            best = None
            for a in range(len(chains)):
                for b in range(a + 1, len(chains)):
                    ci, cj = chains[a], chains[b]
                    if cj > 0 and abs(qty * ci - cj) <= max(0.02 * cj, 0.5):
                        if best is None or cj > best[1]:
                            best = (ci, cj)
            if best:
                price, total = best
            else:
                price, total = chains[0], chains[1]

            name = self._ekf_reconstruct_name(name_tokens)
            if not name:
                idx = unit_idx + 1
                continue
            auto += 1
            qty_str = str(int(qty)) if qty == int(qty) else f"{qty:.3f}".rstrip('0').rstrip('.')
            rows.append([
                number or str(auto), '', name, qty_str,
                self.EKF_UNIT_NORM.get(tl, tokens[unit_idx]),
                f"{price:.2f}", f"{total:.2f}", '', '', '', 'RUB'
            ])
            print(f"  ✓ [STREAM] №{rows[-1][0]} '{name[:40]}' qty={qty_str} "
                  f"price={price:.2f} total={total:.2f} {rows[-1][4]}")
            idx = q
        return rows

    # --- Legacy markdown helpers (сохранены для совместимости) ---
    def _parse_markdown_table(self, text_block):
        rows = []
        for line in text_block.strip().split('\n'):
            line = line.strip()
            if not line.startswith('|'):
                continue
            if re.match(r'^[\|\-\s:]+$', line):
                continue
            cells = [c.strip() for c in line.split('|')]
            if cells and cells[0] == '':
                cells = cells[1:]
            if cells and cells[-1] == '':
                cells = cells[:-1]
            if cells:
                rows.append(cells)
        return rows

    def _reconstruct_ejf_row(self, cells, expected_columns=9):
        if not cells:
            return None
        filtered_cells = [c for c in cells if c.strip()]
        if len(filtered_cells) < 3:
            return None
        number = ""
        start_idx = 0
        if filtered_cells[0].strip().isdigit():
            number = filtered_cells[0].strip()
            start_idx = 1
        article_parts = []
        while start_idx < len(filtered_cells):
            cell = filtered_cells[start_idx].strip()
            if len(cell) <= 15 and (any(c.isdigit() for c in cell) or '-' in cell or '_' in cell):
                article_parts.append(cell)
                start_idx += 1
            else:
                break
        article = ''.join(article_parts) if article_parts else ""
        name_parts = []
        numeric_values = []
        unit = ""
        while start_idx < len(filtered_cells):
            cell = filtered_cells[start_idx].strip()
            cleaned_for_num = cell.replace(' ', '').replace('\xa0', '').replace("'", '')
            cleaned_for_num = cleaned_for_num.replace('₽', '').replace('руб', '')
            try:
                val = float(cleaned_for_num.replace(',', '.'))
                numeric_values.append(val)
                start_idx += 1
                continue
            except:
                pass
            if cell in [',', '.', ';', ':']:
                start_idx += 1
                continue
            lower_cell = cell.lower().strip('. ')
            unit_list = ['шт', 'уп', 'упак', 'компл', 'комплект', 'м', 'кг', 'л',
                        'боб', 'бухта', 'рулон', 'пара', 'набор', 'тыс', 'усл']
            if lower_cell in unit_list or lower_cell.rstrip('.') in unit_list:
                unit = cell
                start_idx += 1
                continue
            name_parts.append(cell)
            start_idx += 1
        reconstructed_name = self._ekf_reconstruct_name(name_parts)
        quantity = price = total = 0
        if len(numeric_values) >= 3:
            qty_candidates = [(i, v) for i, v in enumerate(numeric_values) if v == int(v) and 0 < v <= 10000]
            if qty_candidates:
                qty_idx, quantity = qty_candidates[0]
                remaining = [v for i, v in enumerate(numeric_values) if i != qty_idx]
                if len(remaining) >= 2:
                    price = min(remaining[0], remaining[1])
                    total = max(remaining[0], remaining[1])
                    if abs(total - quantity * price) > 1.0 and abs(price - quantity * total) < 1.0:
                        price, total = total, price
                elif len(remaining) == 1:
                    total = remaining[0]
                    if quantity > 0:
                        price = total / quantity
        elif len(numeric_values) == 2:
            quantity = numeric_values[0] if numeric_values[0] == int(numeric_values[0]) else 1
            total = numeric_values[1]
            if quantity > 0:
                price = total / quantity
        if not reconstructed_name or quantity <= 0:
            return None
        return {'number': number, 'article': article, 'name': reconstructed_name.strip(),
                'quantity': quantity, 'unit': unit if unit else 'шт.',
                'price': round(price, 2), 'total': round(total, 2)}

    # ==================================================================
    # ЦЕПОЧКА ПАРСЕРОВ + ИМПОРТ
    # ==================================================================
    def _run_invoice_parsers(self, filepath, full_text):
        """Приоритет: pipe → токенная грамматика → потоковый → общий текст."""
        print("\n--- ПРИОРИТЕТ 0: pipe-структурные строки (строка таблицы = одна линия с '|') ---")
        rows = self._parse_pipe_structured_rows(full_text)
        if rows and len(rows) >= 1:
            return rows, "pipe_structured"
        print("\n--- ПРИОРИТЕТ 1: токенная грамматика (якорь=единица, запятая завершает число) ---")
        rows = self._parse_invoice_by_grammar(full_text)
        if rows and len(rows) >= 2:
            return rows, "token_grammar"
        print("\n--- ПРИОРИТЕТ 2: потоковый парсер области таблицы ---")
        rows = self._parse_region_stream(full_text)
        if rows and len(rows) >= 1:
            return rows, "region_stream"
        print("\n--- ПРИОРИТЕТ 3: общий текстовый парсер ---")
        rows = self.parse_invoice_from_text(full_text)
        return rows, "general_text"

    def _extract_full_text(self, filepath):
        full_text = ""
        try:
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    txt = page.extract_text(x_tolerance=1.5, y_tolerance=3)
                    if txt:
                        full_text += txt + "\n"
        except Exception as e:
            print(f"[TEXT] ошибка извлечения: {e}")
        return full_text

    def import_invoice_from_pdf(self):
        """Служебный метод прямого импорта PDF (кнопка удалена, оставлен для совместимости)."""
        if not self.app.current_project:
            messagebox.showwarning("Внимание", "Выберите проект!")
            return
        filepath = filedialog.askopenfilename(
            title="Выберите PDF-счет (EKF / ВсеИнструменты / Кабель.РФ)",
            filetypes=[("PDF файлы", "*.pdf"), ("Все файлы", "*.*")])
        if not filepath:
            return
        full_text = self._extract_full_text(filepath)
        if not full_text.strip():
            messagebox.showwarning("Пустой файл", "Не удалось извлечь текст из PDF")
            return
        print(f"\n{'='*60}")
        print(f"=== ИМПОРТ СЧЕТА PDF: {os.path.basename(filepath)} ===")
        supplier_name, supplier_inn = self.find_supplier_in_invoice(full_text)
        if not supplier_name:
            messagebox.showerror("Ошибка", "Не удалось определить поставщика из счета.")
            return
        print(f"Поставщик: {supplier_name} (ИНН: {supplier_inn})")

        project_id = self.db_manager.get_project_id(self.app.current_project)
        spec_data = {
            'supplier': supplier_name, 'name': f"Счет {os.path.basename(filepath)}",
            'quantity': 0, 'price': 0, 'total': 0, 'currency': 'RUB',
            'delivery_term': 0, 'delivery_unit': 'Календарные дни',
            'payment_date': '', 'delivery_date': '', 'fully_paid': 0, 'received': 0,
            'delivery_address': '', 'note': f"Импорт PDF: ИНН={supplier_inn}",
        }
        self.db_manager.add_purchase_spec(project_id, spec_data)
        specs_after = self.db_manager.get_purchase_specifications(project_id)
        new_spec_id = specs_after[-1]['id'] if specs_after else None
        if not new_spec_id:
            messagebox.showerror("Ошибка", "Не удалось создать спецификацию")
            return

        parsed_rows, method = self._run_invoice_parsers(filepath, full_text)
        items_added = 0
        total_sum = 0.0
        for row in parsed_rows:
            if len(row) < 7:
                continue
            name = self.clean_text(row[2])
            try:
                quantity = float(str(row[3]).replace(',', '.'))
            except (TypeError, ValueError):
                quantity = 0
            try:
                price = float(str(row[5]).replace(',', '.'))
            except (TypeError, ValueError):
                price = 0
            try:
                total = float(str(row[6]).replace(',', '.'))
            except (TypeError, ValueError):
                total = 0
            unit = row[4] if len(row) > 4 and row[4] else "шт."
            if not name or quantity <= 0:
                continue
            self.db_manager.add_purchase_spec_item(new_spec_id, {
                'name': name, 'quantity': quantity, 'price': round(price, 2),
                'total': round(total, 2), 'delivery_term': '', 'delivery_unit': unit,
            })
            items_added += 1
            total_sum += total
        if total_sum > 0:
            c = self.db_manager.conn.cursor()
            c.execute("UPDATE purchase_specifications SET total=? WHERE id=?",
                     (round(total_sum, 2), new_spec_id))
            self.db_manager.conn.commit()
        self.load_specs()
        self.current_spec_id = new_spec_id
        self.app.current_purchase_spec_id = new_spec_id
        self.load_purchase_spec_items()
        messagebox.showinfo("Успех",
            f"Метод: {method}\nИмпортировано позиций: {items_added}\n"
            f"Поставщик: {supplier_name}\nИНН: {supplier_inn}\nОбщая сумма: {total_sum:.2f} RUB")
        self.app.log_action(f"Импорт счета PDF [{method}] ({items_added} поз.): {supplier_name}")
        print(f"{'='*60}\n")

    def import_spec_from_file(self):
        if not self.app.current_project:
            messagebox.showwarning("Внимание", "Выберите проект!")
            return
        filepath = filedialog.askopenfilename(
            title="Выберите файл (PDF, Excel или Word)",
            filetypes=[
                ("Все поддерживаемые", "*.pdf *.xlsx *.xls *.docx"),
                ("PDF", "*.pdf"),
                ("Excel", "*.xlsx *.xls"),
                ("Word", "*.docx"),
                ("All files", "*.*")
            ])
        if not filepath:
            return
        try:
            file_rows, full_text = parse_file_to_rows_with_text(filepath)
        except Exception as e:
            messagebox.showerror("Ошибка парсинга", f"Не удалось прочитать файл:\n{e}")
            return

        # === FALLBACK запускается ТОЛЬКО если базовый парсер не дал
        #     ни одной валидной строки (раньше порог был "строк < 2",
        #     из-за чего терялись однопозиционные счета) ===
        if not self._rows_look_valid(file_rows):
            print("\n=== СПЕЦИАЛИЗИРОВАННЫЙ ПАРСИНГ (fallback) ===")
            if filepath.lower().endswith('.pdf'):
                file_rows, method = self._run_invoice_parsers(filepath, full_text)
                print(f"Выбран метод: {method}, строк: {len(file_rows)}")
            else:
                file_rows = self.parse_invoice_from_text(full_text)
                print(f"После текстового парсинга получено строк: {len(file_rows)}")

        if not file_rows:
            messagebox.showwarning("Пустой файл", "Файл не содержит данных")
            return

        print(f"\n{'='*60}")
        print(f"=== ИМПОРТ ИЗ ФАЙЛА: {os.path.basename(filepath)} ===")
        print(f"Получено строк: {len(file_rows)}")

        supplier_name, supplier_inn = self.find_supplier_in_invoice(full_text)
        if not supplier_name:
            messagebox.showerror("Ошибка",
                "Не удалось найти поставщика в файле.\n\n"
                "Проверьте структуру документа или укажите поставщика вручную.")
            return
        print(f"=== РЕЗУЛЬТАТ ПОИСКА ===")
        print(f"Поставщик: {supplier_name}")
        print(f"ИНН: {supplier_inn}")

        delivery_term = 0
        delivery_unit = "Календарные дни"
        delivery_match = re.search(r'(\d+)\s*(раб\.?\s*дн|рабочих?\s*дн|дн|дней|нед|недель|мес|месяц)',
                                    full_text, re.IGNORECASE)
        if delivery_match:
            delivery_term = int(delivery_match.group(1))
            unit_str = delivery_match.group(2).lower()
            if 'раб' in unit_str:
                delivery_unit = "Рабочие дни"
            elif 'нед' in unit_str:
                delivery_unit = "Недели"
            elif 'мес' in unit_str:
                delivery_unit = "Месяцы"

        project_id = self.db_manager.get_project_id(self.app.current_project)
        spec_data = {
            'supplier': supplier_name,
            'name': f"Импорт из {os.path.basename(filepath)}",
            'quantity': 0, 'price': 0, 'total': 0, 'currency': 'RUB',
            'delivery_term': delivery_term, 'delivery_unit': delivery_unit,
            'payment_date': '', 'delivery_date': '', 'fully_paid': 0, 'received': 0,
            'delivery_address': '',
            'note': f"Импортировано из {os.path.basename(filepath)}, ИНН: {supplier_inn}",
        }
        self.db_manager.add_purchase_spec(project_id, spec_data)
        specs = self.db_manager.get_purchase_specifications(project_id)
        new_spec_id = specs[-1]['id'] if specs else None
        if not new_spec_id:
            messagebox.showerror("Ошибка", "Не удалось создать спецификацию")
            return

        items_added = 0
        total_sum = 0
        for row_idx, row in enumerate(file_rows):
            if len(row) < 3:
                continue
            row_text = ' '.join([str(c) for c in row if c]).upper()
            if any(word in row_text for word in ['ИТОГО', 'ВСЕГО', 'НАИМЕНОВАНИЙ',
                                                  'ОБЩАЯ СУММА', 'ВСЕГО К ОПЛАТЕ']):
                continue
            raw_name = row[2] if len(row) > 2 and row[2] else ""
            name = self.clean_text(raw_name)
            raw_delivery = row[7] if len(row) > 7 and row[7] else ""
            delivery = self.clean_text(raw_delivery)
            try:
                quantity = float(str(row[3]).replace(',', '.').replace(' ', '')) if len(row) > 3 and row[3] else 0
            except (TypeError, ValueError):
                quantity = 0
            try:
                price = float(str(row[5]).replace("'", "").replace(',', '.').replace(' ', '')
                             .replace('₽', '').replace('руб', '').replace('€', '').replace('$', '')) if len(row) > 5 and row[5] else 0
            except (TypeError, ValueError):
                price = 0
            try:
                total = float(str(row[6]).replace("'", "").replace(',', '.').replace(' ', '')
                             .replace('₽', '').replace('руб', '').replace('€', '').replace('$', '')) if len(row) > 6 and row[6] else 0
            except (TypeError, ValueError):
                total = 0
            unit = self.clean_text(row[4]) if len(row) > 4 and row[4] else ""
            if total == 0 and quantity > 0 and price > 0:
                total = quantity * price

            # === СВЕРКА ЦЕНЫ И СУММЫ ===
            # Если qty*price не сходится с суммой из документа (например, цена
            # без НДС, а сумма с НДС), доверяем СУММЕ и пересчитываем цену.
            if total > 0 and quantity > 0:
                expected = total / quantity
                if abs(price - expected) > max(0.02 * expected, 0.5):
                    print(f"  ⚠ Сверка: цена {price:.2f} не совпадает с суммой/кол-вом "
                          f"({expected:.2f}), цена пересчитана")
                    price = round(expected, 2)

            if not name or quantity == 0:
                continue
            item_data = {
                'name': name, 'quantity': quantity, 'price': price, 'total': total,
                'delivery_term': delivery, 'delivery_unit': unit,
            }
            self.db_manager.add_purchase_spec_item(new_spec_id, item_data)
            items_added += 1
            total_sum += item_data['total']
            print(f"  ✓ Позиция {items_added}: {name[:50]}... кол-во={quantity}, цена={price}, сумма={total}")

        if total_sum > 0:
            c = self.db_manager.conn.cursor()
            c.execute("UPDATE purchase_specifications SET total=? WHERE id=?", (total_sum, new_spec_id))
            self.db_manager.conn.commit()

        self.load_specs()
        self.current_spec_id = new_spec_id
        self.app.current_purchase_spec_id = new_spec_id
        self.load_purchase_spec_items()
        try:
            messagebox.showinfo("Успех",
                f"Создана новая позиция спецификации!\n"
                f"Поставщик: {supplier_name}\nИНН: {supplier_inn}\n"
                f"Срок поставки: {delivery_term} {delivery_unit}\n"
                f"Импортировано {items_added} позиций\n"
                f"Общая сумма: {total_sum:.2f} RUB")
        except Exception:
            pass
        self.app.log_action(f"Импортирована спецификация из {os.path.basename(filepath)}: {supplier_name}")
        print(f"{'='*60}\n")