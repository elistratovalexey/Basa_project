import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from datetime import datetime, timedelta
import os
import holidays
import re
import traceback
from collections import defaultdict

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

try:
    from config import TIME_UNITS, ORDER_CURRENCIES
except ImportError:
    TIME_UNITS = ["Календарные дни", "Рабочие дни", "Недели", "Месяцы"]
    ORDER_CURRENCIES = ["EUR", "USD", "CNY", "RUB"]

try:
    from utils import add_months, add_working_days_with_holidays, parse_number, parse_delivery_time, translate_time_unit
except ImportError:
    import calendar

    def add_months(source_date, months):
        if months == 0:
            return source_date
        month = source_date.month - 1 + months
        year = source_date.year + month // 12
        month = month % 12 + 1
        day = min(source_date.day, calendar.monthrange(year, month)[1])
        return source_date.replace(year=year, month=month, day=day)

    def add_working_days_with_holidays(start_date, days, holidays_set):
        current = start_date
        added = 0
        while added < days:
            current += timedelta(days=1)
            if current.weekday() < 5 and current not in holidays_set:
                added += 1
        return current

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

from dialogs.order_file_parser import parse_file_to_rows_with_text
from dialogs.order_item_edit_dialog import OrderItemEditDialog
from dialogs.order_export_dialog import OrderExportDialog
from dialogs.calendar_dialog import CalendarDialog
from dialogs.file_import_dialog import FileImportMatchDialog
from dialogs.supplier_dialog import SupplierDialog


class OrderDialog(tk.Toplevel):
    def __init__(self, parent, db_manager, batch_id=None, russian_holidays=None, project_name=None):
        super().__init__(parent)
        self.title("База заказов")
        self.geometry("1600x1000")
        self.resizable(True, True)
        try:
            from dialogs.window_geometry import restore_geometry, track_geometry
            restore_geometry(self, "order_dialog", "1600x1000")
            track_geometry(self, "order_dialog")
        except Exception:
            pass
        self.db_manager = db_manager
        self.current_batch_id = batch_id
        self.current_item_id = None
        self.parent = parent
        self.russian_holidays = russian_holidays or holidays.Russia()
        self.project_name = project_name
        self.sort_column = "order_date"
        self.sort_order = "ASC"
        # НОВОЕ: соответствие "отображаемый номер (Z1/53)" -> реальный order_batch_id
        self._display2batch = {}

        top_frame = ttk.LabelFrame(self, text="Заказы", padding=8)
        top_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        filter_frame = ttk.Frame(top_frame)
        filter_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(filter_frame, text="Фильтр по производителю:").pack(side=tk.LEFT, padx=5)
        self.combo_filter_manufacturer = ttk.Combobox(filter_frame, width=20, state="readonly")
        self.combo_filter_manufacturer.pack(side=tk.LEFT, padx=5)
        self.combo_filter_manufacturer.bind("<<ComboboxSelected>>", lambda e: self.load_batches())

        ttk.Label(filter_frame, text="Дата оплаты:").pack(side=tk.LEFT, padx=(15, 5))
        self.combo_filter_payment = ttk.Combobox(filter_frame, values=["Все", "Есть дата", "Нет даты"],
                                                 state="readonly", width=12)
        self.combo_filter_payment.set("Все")
        self.combo_filter_payment.pack(side=tk.LEFT, padx=5)
        self.combo_filter_payment.bind("<<ComboboxSelected>>", lambda e: self.load_batches())

        ttk.Label(filter_frame, text="Получено:").pack(side=tk.LEFT, padx=(15, 5))
        self.combo_filter_received = ttk.Combobox(filter_frame, values=["Все", "Получено", "Не получено"],
                                                  state="readonly", width=12)
        self.combo_filter_received.set("Все")
        self.combo_filter_received.pack(side=tk.LEFT, padx=5)
        self.combo_filter_received.bind("<<ComboboxSelected>>", lambda e: self.load_batches())

        ttk.Button(filter_frame, text="Экспорт в Excel", command=self.open_export_dialog).pack(side=tk.RIGHT, padx=5)
        ttk.Button(filter_frame, text="База Поставщиков", command=self.open_suppliers).pack(side=tk.RIGHT, padx=5)
        self.load_manufacturers_filter()

        # НОВОЕ: колонка price_request в конце (не сбивает номера колонок #15/#16/#17)
        cols_b = ("batch_id", "manufacturer", "subproject", "kd", "order_date", "project_name",
                  "payment_date", "delivery_days", "delivery_unit_order", "min_delivery_date", "max_delivery_date",
                  "invoice_number", "supplier", "delivery_number", "received", "receipt_date",
                  "write_off_date", "price_request","status")
        self.tree_batches = ttk.Treeview(top_frame, columns=cols_b, show="headings", height=6)
        self.tree_batches.heading("batch_id", text="№ заказа", command=lambda: self.sort_by_column("batch_id"))
        self.tree_batches.heading("manufacturer", text="Производитель")
        self.tree_batches.heading("subproject", text="Подпроект")
        self.tree_batches.heading("kd", text="КД")
        self.tree_batches.heading("order_date", text="Дата заказа", command=lambda: self.sort_by_column("order_date"))
        self.tree_batches.heading("project_name", text="Проект")
        self.tree_batches.heading("payment_date", text="Дата оплаты")
        self.tree_batches.heading("delivery_days", text="Доставка")
        self.tree_batches.heading("delivery_unit_order", text="Ед. доставки")
        self.tree_batches.heading("min_delivery_date", text="Min дата поставки МСК")
        self.tree_batches.heading("max_delivery_date", text="Max дата поставки МСК")
        self.tree_batches.heading("invoice_number", text="Номер инвойса")
        self.tree_batches.heading("supplier", text="Поставщик")
        self.tree_batches.heading("delivery_number", text="Номер поставки")
        self.tree_batches.heading("received", text="Получено")
        self.tree_batches.heading("receipt_date", text="Дата получения")
        self.tree_batches.heading("write_off_date", text="Дата списания")
        self.tree_batches.heading("price_request", text="Запрос цены")

        self.tree_batches.column("batch_id", width=70, anchor="center")
        self.tree_batches.column("manufacturer", width=100, anchor="w")
        self.tree_batches.column("subproject", width=120, anchor="w")
        self.tree_batches.column("kd", width=80, anchor="w")
        self.tree_batches.column("order_date", width=90, anchor="center")
        self.tree_batches.column("project_name", width=150, anchor="w")
        self.tree_batches.column("payment_date", width=90, anchor="center")
        self.tree_batches.column("delivery_days", width=70, anchor="center")
        self.tree_batches.column("delivery_unit_order", width=90, anchor="w")
        self.tree_batches.column("min_delivery_date", width=100, anchor="center", stretch=False)
        self.tree_batches.column("max_delivery_date", width=100, anchor="center", stretch=False)
        self.tree_batches.column("invoice_number", width=120, anchor="w")
        self.tree_batches.column("supplier", width=150, anchor="w")
        self.tree_batches.column("delivery_number", width=120, anchor="w")
        self.tree_batches.column("received", width=70, anchor="center")
        self.tree_batches.column("receipt_date", width=100, anchor="center")
        self.tree_batches.column("write_off_date", width=90, anchor="center", stretch=False)
        self.tree_batches.column("price_request", width=80, anchor="center")
        self.tree_batches.heading("status", text="Статус")
        self.tree_batches.column("status", width=110, anchor="w")       

        sb_b = ttk.Scrollbar(top_frame, orient=tk.VERTICAL, command=self.tree_batches.yview)
        sb_bx = ttk.Scrollbar(top_frame, orient=tk.HORIZONTAL, command=self.tree_batches.xview)
        self.tree_batches.configure(yscroll=sb_b.set, xscroll=sb_bx.set)
        sb_b.pack(side=tk.RIGHT, fill=tk.Y)
        sb_bx.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree_batches.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree_batches.bind("<<TreeviewSelect>>", self.on_select_batch)
        self.tree_batches.bind("<Button-1>", self.on_batch_click)

        bf = ttk.LabelFrame(self, text="Заголовок заказа", padding=8)
        bf.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(bf, text="Дата заказа:").grid(row=0, column=0, sticky="w", padx=(0, 2))
        self.entry_batch_date = ttk.Entry(bf, width=10)
        self.entry_batch_date.grid(row=0, column=1, sticky="w", padx=(0, 5))
        self.btn_cal_order = ttk.Button(bf, text="📅", width=3, command=self.select_order_date)
        self.btn_cal_order.grid(row=0, column=2, padx=(0, 5))

        ttk.Label(bf, text="Проект:").grid(row=0, column=3, sticky="w", padx=(0, 2))
        self.entry_batch_project = ttk.Entry(bf, width=15)
        self.entry_batch_project.grid(row=0, column=4, sticky="w", padx=(0, 5))

        ttk.Label(bf, text="Дата оплаты:").grid(row=0, column=5, sticky="w", padx=(0, 2))
        self.entry_batch_payment = ttk.Entry(bf, width=10)
        self.entry_batch_payment.grid(row=0, column=6, sticky="w", padx=(0, 5))
        self.btn_cal_payment = ttk.Button(bf, text="📅", width=3, command=self.select_payment_date)
        self.btn_cal_payment.grid(row=0, column=7, padx=(0, 5))

        ttk.Label(bf, text="Номер инвойса:").grid(row=0, column=8, sticky="w", padx=(0, 2))
        self.entry_invoice_number = ttk.Entry(bf, width=15)
        self.entry_invoice_number.grid(row=0, column=9, sticky="w", padx=(0, 5))

        ttk.Label(bf, text="Поставщик:").grid(row=0, column=10, sticky="w", padx=(0, 2))
        self.combo_batch_supplier = ttk.Combobox(bf, width=18)
        self.combo_batch_supplier.grid(row=0, column=11, sticky="w", padx=(0, 5))
        self.load_suppliers()

        ttk.Label(bf, text="Номер поставки:").grid(row=0, column=12, sticky="w", padx=(0, 2))
        self.entry_delivery_number = ttk.Entry(bf, width=15)
        self.entry_delivery_number.grid(row=0, column=13, sticky="w", padx=(0, 5))

        ttk.Label(bf, text="Производитель:").grid(row=1, column=0, sticky="w", padx=(0, 2))
        self.combo_batch_manufacturer = ttk.Combobox(bf, width=20)
        self.combo_batch_manufacturer.grid(row=1, column=1, sticky="w", padx=(0, 5))

        ttk.Label(bf, text="Подпроект:").grid(row=1, column=2, sticky="w", padx=(0, 2))
        self.combo_batch_subproject = ttk.Combobox(bf, width=20)
        self.combo_batch_subproject.grid(row=1, column=3, sticky="w", padx=(0, 5))

        ttk.Label(bf, text="КД:").grid(row=1, column=4, sticky="w", padx=(0, 2))
        self.combo_batch_kd = ttk.Combobox(bf, width=20)
        self.combo_batch_kd.grid(row=1, column=5, sticky="w", padx=(0, 5))

        ttk.Label(bf, text="Доставка:").grid(row=1, column=6, sticky="w", padx=(0, 2))
        self.entry_delivery_days = ttk.Entry(bf, width=8)
        self.entry_delivery_days.grid(row=1, column=7, sticky="w", padx=(0, 5))

        ttk.Label(bf, text="Ед.:").grid(row=1, column=8, sticky="w", padx=(0, 2))
        self.combo_delivery_unit = ttk.Combobox(bf, values=TIME_UNITS, state="readonly", width=12)
        self.combo_delivery_unit.grid(row=1, column=9, sticky="w", padx=(0, 5))

        self.received_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bf, text="Получено", variable=self.received_var,
                        command=self.on_received_change).grid(row=1, column=10, sticky="w", padx=(0, 5))

        ttk.Label(bf, text="Дата получения:").grid(row=1, column=11, sticky="w", padx=(0, 2))
        self.entry_receipt_date = ttk.Entry(bf, width=10)
        self.entry_receipt_date.grid(row=1, column=12, sticky="w", padx=(0, 5))
        self.btn_cal_receipt = ttk.Button(bf, text="📅", width=3, command=self.select_receipt_date)
        self.btn_cal_receipt.grid(row=1, column=13, padx=(0, 5))

        ttk.Label(bf, text="Дата списания:").grid(row=2, column=0, sticky="w", padx=(0, 2), pady=(8, 0))
        self.entry_write_off_date = ttk.Entry(bf, width=10)
        self.entry_write_off_date.grid(row=2, column=1, sticky="w", padx=(0, 5), pady=(8, 0))
        self.btn_cal_write_off = ttk.Button(bf, text="📅", width=3, command=self.select_write_off_date)
        self.btn_cal_write_off.grid(row=2, column=2, padx=(0, 5), pady=(8, 0))

        import_frame = ttk.Frame(self)
        import_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(import_frame, text="Импорт из файла (Excel/PDF)", command=self.import_from_file).pack(side=tk.LEFT, padx=5)
        ttk.Label(import_frame, text="— выберите файл коммерческого предложения").pack(side=tk.LEFT, padx=10)
        ttk.Separator(import_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Button(import_frame, text="Рассчитать даты", command=self.calculate_delivery_dates).pack(side=tk.LEFT, padx=5)
        ttk.Button(import_frame, text="Статус / ETA", command=self.edit_status).pack(side=tk.LEFT, padx=5)
        ttk.Button(import_frame, text="Сохранить заказ", command=self.save_batch).pack(side=tk.LEFT, padx=5)
        ttk.Button(import_frame, text="Удалить заказ", command=self.delete_batch).pack(side=tk.LEFT, padx=5)
        ttk.Button(import_frame, text="Заказ в файл АНГ", command=self.export_order_to_excel).pack(side=tk.RIGHT, padx=5)

        bot_frame = ttk.LabelFrame(self, text="Позиции заказа", padding=8)
        bot_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        cols_i = ("id", "article", "name", "quantity", "delivery_term", "delivery_unit", "price", "currency", "note")
        self.tree_items = ttk.Treeview(bot_frame, columns=cols_i, show="headings", height=10)
        for col, title, width, anc in [
            ("id", "ID", 50, "center"), ("article", "Артикул", 130, "w"),
            ("name", "Наименование", 250, "w"), ("quantity", "Кол-во", 60, "center"),
            ("delivery_term", "Срок поставки", 80, "center"),
            ("delivery_unit", "Единица", 110, "w"), ("price", "Цена", 80, "e"),
            ("currency", "Валюта", 70, "center"), ("note", "Примечание", 150, "w")
        ]:
            self.tree_items.heading(col, text=title)
            self.tree_items.column(col, width=width, anchor=anc)

        sb_i = ttk.Scrollbar(bot_frame, orient=tk.VERTICAL, command=self.tree_items.yview)
        self.tree_items.configure(yscroll=sb_i.set)
        self.tree_items.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_i.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_items.bind("<<TreeviewSelect>>", self.on_select_item)
        self.tree_items.bind("<Double-1>", lambda e: self.edit_item())

        itf = ttk.LabelFrame(self, text="Позиция", padding=8)
        itf.pack(fill=tk.X, padx=10, pady=(5, 10))
        ttk.Label(itf, text="Артикул:").grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.entry_item_article = ttk.Entry(itf, width=20)
        self.entry_item_article.grid(row=0, column=1, sticky="ew", padx=(0, 15))
        ttk.Label(itf, text="Наименование:").grid(row=0, column=2, sticky="w", padx=(0, 5))
        self.entry_item_name = ttk.Entry(itf, width=30)
        self.entry_item_name.grid(row=0, column=3, sticky="ew", padx=(0, 15))
        ttk.Label(itf, text="Кол-во:").grid(row=0, column=4, sticky="w", padx=(0, 5))
        self.entry_item_quantity = ttk.Entry(itf, width=10)
        self.entry_item_quantity.grid(row=0, column=5, sticky="w", padx=(0, 15))
        ttk.Label(itf, text="Срок:").grid(row=1, column=0, sticky="w", padx=(0, 5), pady=(8, 0))
        self.entry_item_delivery_term = ttk.Entry(itf, width=10)
        self.entry_item_delivery_term.grid(row=1, column=1, sticky="w", padx=(0, 15), pady=(8, 0))
        ttk.Label(itf, text="Единица:").grid(row=1, column=2, sticky="w", padx=(0, 5), pady=(8, 0))
        self.combo_item_delivery_unit = ttk.Combobox(itf, values=TIME_UNITS, state="readonly", width=16)
        self.combo_item_delivery_unit.grid(row=1, column=3, sticky="w", padx=(0, 15), pady=(8, 0))
        ttk.Label(itf, text="Цена:").grid(row=1, column=4, sticky="w", padx=(0, 5), pady=(8, 0))
        self.entry_item_price = ttk.Entry(itf, width=12)
        self.entry_item_price.grid(row=1, column=5, sticky="w", padx=(0, 15), pady=(8, 0))
        ttk.Label(itf, text="Валюта:").grid(row=1, column=6, sticky="w", padx=(0, 5), pady=(8, 0))
        self.combo_item_currency = ttk.Combobox(itf, values=ORDER_CURRENCIES, state="readonly", width=10)
        self.combo_item_currency.grid(row=1, column=7, sticky="w", pady=(8, 0))
        ttk.Label(itf, text="Примечание:").grid(row=2, column=0, sticky="w", padx=(0, 5), pady=(8, 0))
        self.entry_item_note = ttk.Entry(itf, width=50)
        self.entry_item_note.grid(row=2, column=1, columnspan=7, sticky="ew", pady=(8, 0))
        for col in (1, 3, 5):
            itf.grid_columnconfigure(col, weight=1)
        btnf = ttk.Frame(itf)
        btnf.grid(row=3, column=0, columnspan=8, pady=(10, 0))
        ttk.Button(btnf, text="Сохранить позицию", command=self.save_item).pack(side=tk.LEFT, padx=5)
        ttk.Button(btnf, text="Удалить позицию", command=self.delete_item).pack(side=tk.LEFT, padx=5)
        ttk.Button(btnf, text="Закрыть", command=self.destroy).pack(side=tk.RIGHT, padx=5)

        self.load_manufacturers_for_combo()
        if hasattr(self.db_manager, "ensure_column"):
            self.db_manager.ensure_column("orders", "write_off_date")
        self.load_batches()
        if batch_id:
            self.load_items(batch_id)

        self._bind_ids = []
        for seq in ("<Control-c>", "<Control-C>", "<Control-v>", "<Control-V>",
                    "<Control-x>", "<Control-X>"):
            bid = self.bind_all(seq, self._handle_clipboard)
            self._bind_ids.append((seq, bid))
        self._original_destroy = self.destroy
        self.destroy = self._safe_destroy
        
    def edit_status(self):
        if self.current_batch_id is None:
            messagebox.showwarning("Внимание", "Выберите заказ!")
            return
        from dialogs.order_status_dialog import OrderStatusDialog
        OrderStatusDialog(self, self.db_manager, self._batch_of(self.current_batch_id)
                          if hasattr(self, "_batch_of") else self.current_batch_id)
        self.load_batches()

    def _safe_destroy(self):
        for seq, bid in self._bind_ids:
            try:
                self.unbind_all(seq)
            except:
                pass
        self._original_destroy()

    def _batch_of(self, display):
        """НОВОЕ: реальный order_batch_id по отображаемому номеру (Z1 / 53)."""
        return self._display2batch.get(str(display), display)

    def _handle_clipboard(self, event):
        widget = event.widget
        try:
            toplevel = widget.winfo_toplevel()
        except:
            return None
        if toplevel != self:
            return None
        char = event.char.lower() if event.char else ''
        if char in ('c', 'с'):
            return self._copy_ru(event)
        elif char in ('v', 'м'):
            return self._paste_ru(event)
        elif char in ('x', 'х'):
            return self._cut_ru(event)
        return None

    def _copy_ru(self, event=None):
        try:
            widget = self.focus_get()
            if widget and hasattr(widget, 'selection_get'):
                try:
                    text = widget.selection_get()
                    self.clipboard_clear()
                    self.clipboard_append(text)
                except:
                    pass
        except:
            pass
        return "break"

    def _paste_ru(self, event=None):
        try:
            widget = self.focus_get()
            if widget and hasattr(widget, 'insert'):
                try:
                    clipboard_data = self.clipboard_get()
                    try:
                        start = widget.index(tk.SEL_FIRST)
                        end = widget.index(tk.SEL_LAST)
                        widget.delete(start, end)
                    except:
                        pass
                    widget.insert(tk.INSERT, clipboard_data)
                except:
                    pass
        except:
            pass
        return "break"

    def _cut_ru(self, event=None):
        try:
            widget = self.focus_get()
            if widget and hasattr(widget, 'selection_get'):
                try:
                    text = widget.selection_get()
                    self.clipboard_clear()
                    self.clipboard_append(text)
                    widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
                except:
                    pass
        except:
            pass
        return "break"

    def load_manufacturers_filter(self):
        c = self.db_manager.conn.cursor()
        c.execute("SELECT DISTINCT manufacturer FROM orders WHERE manufacturer IS NOT NULL AND manufacturer != '' ORDER BY manufacturer")
        manufacturers = [row[0] for row in c.fetchall()]
        self.combo_filter_manufacturer['values'] = [''] + manufacturers

    def load_suppliers(self):
        if not hasattr(self, 'combo_batch_supplier'):
            return
        c = self.db_manager.conn.cursor()
        c.execute("SELECT DISTINCT name FROM suppliers ORDER BY name")
        suppliers = [row[0] for row in c.fetchall()]
        self.combo_batch_supplier['values'] = suppliers

    def open_suppliers(self):
        dialog = SupplierDialog(self, self.db_manager)
        self.wait_window(dialog)
        self.load_suppliers()

    def sort_by_column(self, column):
        if self.sort_column == column:
            self.sort_order = "ASC" if self.sort_order == "DESC" else "DESC"
        else:
            self.sort_column = column
            self.sort_order = "ASC"
        self.load_batches()

    def load_manufacturers_for_combo(self):
        if not hasattr(self, 'combo_batch_manufacturer'):
            return
        c = self.db_manager.conn.cursor()
        c.execute("SELECT DISTINCT name FROM manufacturers ORDER BY name")
        manufacturers = [row[0] for row in c.fetchall()]
        self.combo_batch_manufacturer['values'] = manufacturers
        self.load_subprojects_for_combo()
        self.load_kd_for_combo()

    def load_subprojects_for_combo(self):
        if not hasattr(self, 'combo_batch_subproject'):
            return
        c = self.db_manager.conn.cursor()
        if self.project_name:
            c.execute('''SELECT DISTINCT name FROM subprojects
                        WHERE (project_name=? OR project_name='' OR project_name IS NULL)
                        ORDER BY name''', (self.project_name,))
        else:
            c.execute("SELECT DISTINCT name FROM subprojects ORDER BY name")
        subprojects = [row[0] for row in c.fetchall()]
        self.combo_batch_subproject['values'] = subprojects

    def load_kd_for_combo(self):
        if not hasattr(self, 'combo_batch_kd'):
            return
        c = self.db_manager.conn.cursor()
        if self.project_name:
            c.execute('''SELECT DISTINCT kd_number FROM kd_directory
                        WHERE (project_name=? OR project_name='' OR project_name IS NULL)
                        ORDER BY kd_number''', (self.project_name,))
        else:
            c.execute("SELECT DISTINCT kd_number FROM kd_directory ORDER BY kd_number")
        kd_list = [row[0] for row in c.fetchall()]
        self.combo_batch_kd['values'] = kd_list

    def select_order_date(self):
        current = self.entry_batch_date.get()
        dialog = CalendarDialog(self, current if current else None)
        self.wait_window(dialog)
        if dialog.result:
            self.entry_batch_date.delete(0, tk.END)
            self.entry_batch_date.insert(0, dialog.result)

    def select_payment_date(self):
        current = self.entry_batch_payment.get()
        dialog = CalendarDialog(self, current if current else None)
        self.wait_window(dialog)
        if dialog.result:
            self.entry_batch_payment.delete(0, tk.END)
            self.entry_batch_payment.insert(0, dialog.result)

    def select_receipt_date(self):
        current = self.entry_receipt_date.get()
        dialog = CalendarDialog(self, current if current else None)
        self.wait_window(dialog)
        if dialog.result:
            self.entry_receipt_date.delete(0, tk.END)
            self.entry_receipt_date.insert(0, dialog.result)
            if self.current_batch_id:
                self.save_batch()

    def select_write_off_date(self):
        current = self.entry_write_off_date.get()
        dialog = CalendarDialog(self, current if current else None)
        self.wait_window(dialog)
        if dialog.result:
            self.entry_write_off_date.delete(0, tk.END)
            self.entry_write_off_date.insert(0, dialog.result)
            if self.current_batch_id:
                self._save_write_off_date(self.current_batch_id, dialog.result)
                self._refresh_batches_keep_selection()

    def _save_write_off_date(self, batch_id, value):
        try:
            self.db_manager.set_order_write_off_date(batch_id, value)
        except AttributeError:
            c = self.db_manager.conn.cursor()
            c.execute("UPDATE orders SET write_off_date=? WHERE order_batch_id=?",
                      (value, batch_id))
            self.db_manager.conn.commit()

    def _refresh_batches_keep_selection(self):
        keep_id = self.current_batch_id
        self.load_batches()
        for item in self.tree_batches.get_children():
            v = self.tree_batches.item(item)['values']
            if self._batch_of(v[0]) == keep_id:
                self.tree_batches.selection_set(item)
                self.tree_batches.see(item)
                self.current_batch_id = keep_id
                self._load_batch_to_form(v)
                self.load_items(keep_id)
                break

    def _set_topmost(self, value):
        try:
            self.attributes('-topmost', value)
        except tk.TclError:
            pass

    def _load_batch_to_form(self, values):
        if not values or len(values) < 17:
            return
        self.entry_batch_date.delete(0, tk.END)
        self.entry_batch_date.insert(0, values[4])
        self.entry_batch_project.delete(0, tk.END)
        self.entry_batch_project.insert(0, values[5])
        self.entry_batch_payment.delete(0, tk.END)
        self.entry_batch_payment.insert(0, values[6])
        self.entry_delivery_days.delete(0, tk.END)
        self.entry_delivery_days.insert(0, values[7])
        self.combo_delivery_unit.set(values[8])
        self.combo_batch_manufacturer.set(values[1])
        self.combo_batch_subproject.set(values[2])
        self.combo_batch_kd.set(values[3])
        self.entry_invoice_number.delete(0, tk.END)
        self.entry_invoice_number.insert(0, values[11])
        self.combo_batch_supplier.set(values[12])
        self.entry_delivery_number.delete(0, tk.END)
        self.entry_delivery_number.insert(0, values[13] if len(values) > 13 else "")
        self.received_var.set(values[14] == "✓")
        self.entry_receipt_date.delete(0, tk.END)
        self.entry_receipt_date.insert(0, values[15] if len(values) > 15 else "")
        self.entry_write_off_date.delete(0, tk.END)
        self.entry_write_off_date.insert(0, values[16] if len(values) > 16 else "")

    def calculate_delivery_dates(self):
        self._set_topmost(True)
        self.lift()
        self.focus_force()
        try:
            if not self.current_batch_id:
                messagebox.showwarning("Внимание", "Выберите заказ!", parent=self)
                return
            payment_date_str = self.entry_batch_payment.get().strip()
            if not payment_date_str:
                messagebox.showwarning("Внимание", "Укажите дату оплаты!", parent=self)
                return
            try:
                payment_date = datetime.strptime(payment_date_str, "%d.%m.%Y")
            except:
                messagebox.showerror("Ошибка", "Неверный формат даты оплаты!", parent=self)
                return
            try:
                delivery_days = int(self.entry_delivery_days.get())
            except:
                messagebox.showerror("Ошибка", "Неверное количество дней доставки!", parent=self)
                return
            delivery_unit = self.combo_delivery_unit.get()
            if not delivery_unit:
                messagebox.showwarning("Внимание", "Выберите единицу доставки!", parent=self)
                return

            current_manufacturer = self.combo_batch_manufacturer.get()
            current_subproject = self.combo_batch_subproject.get()
            current_kd = self.combo_batch_kd.get()
            current_supplier = self.combo_batch_supplier.get()
            current_invoice = self.entry_invoice_number.get()

            if delivery_unit == "Недели":
                delivery_days_total = delivery_days * 7
            elif delivery_unit == "Месяцы":
                delivery_date = add_months(payment_date, delivery_days)
                delivery_days_total = (delivery_date - payment_date).days
            elif delivery_unit == "Рабочие дни":
                delivery_date = add_working_days_with_holidays(payment_date, delivery_days, self.russian_holidays)
                delivery_days_total = (delivery_date - payment_date).days
            else:
                delivery_days_total = delivery_days

            items = self.db_manager.get_order_items(self.current_batch_id)
            min_supply_days = None
            max_supply_days = 0
            for item in items:
                item_days = item['delivery_term'] or 0
                if item_days == 0:
                    continue
                item_unit = item['delivery_unit'] or "Недели"
                if item_unit == "Недели":
                    days_in_days = item_days * 7
                elif item_unit == "Месяцы":
                    supply_date = add_months(payment_date, item_days)
                    days_in_days = (supply_date - payment_date).days
                elif item_unit == "Рабочие дни":
                    supply_date = add_working_days_with_holidays(payment_date, item_days, self.russian_holidays)
                    days_in_days = (supply_date - payment_date).days
                else:
                    days_in_days = item_days
                if min_supply_days is None or days_in_days < min_supply_days:
                    min_supply_days = days_in_days
                if days_in_days > max_supply_days:
                    max_supply_days = days_in_days
            if min_supply_days is None:
                min_supply_days = 0

            min_date = payment_date + timedelta(days=min_supply_days + delivery_days_total)
            max_date = payment_date + timedelta(days=max_supply_days + delivery_days_total)
            entry_min_delivery = min_date.strftime("%d.%m.%Y")
            entry_max_delivery = max_date.strftime("%d.%m.%Y")

            self.db_manager.update_order_batch(
                self.current_batch_id,
                self.entry_batch_date.get(),
                self.entry_batch_project.get(),
                self.entry_batch_payment.get(),
                delivery_days, delivery_unit,
                entry_min_delivery, entry_max_delivery
            )

            if current_manufacturer or current_subproject or current_kd or current_supplier or current_invoice:
                c = self.db_manager.conn.cursor()
                c.execute('''UPDATE orders SET manufacturer=?, subproject=?, kd=?, supplier=?, invoice_number=?
                    WHERE order_batch_id=?''',
                    (current_manufacturer, current_subproject, current_kd, current_supplier,
                     current_invoice, self.current_batch_id))
                self.db_manager.conn.commit()

            self.load_batches()
            for item in self.tree_batches.get_children():
                v = self.tree_batches.item(item)['values']
                if self._batch_of(v[0]) == self.current_batch_id:
                    self.tree_batches.selection_set(item)
                    self.tree_batches.see(item)
                    self._load_batch_to_form(v)
                    break

            self._set_topmost(False)
            self.update_idletasks()
            self.lift()
            self.focus_force()
            messagebox.showinfo(
                "Успех",
                f"Даты доставки рассчитаны и сохранены!\nMin: {entry_min_delivery}\nMax: {entry_max_delivery}",
                parent=self
            )
            self.lift()
            self.focus_force()
        finally:
            self._set_topmost(False)

    def load_batches(self):
        for item in self.tree_batches.get_children():
            self.tree_batches.delete(item)
        self._display2batch = {}
        today = datetime.now().date()
        filter_manufacturer = self.combo_filter_manufacturer.get().strip()
        filter_payment = self.combo_filter_payment.get()
        filter_received = self.combo_filter_received.get()

        c = self.db_manager.conn.cursor()
        if self.sort_column == "order_date":
            order_clause = (
                f"ORDER BY CASE WHEN MAX(order_date) = '' OR MAX(order_date) IS NULL THEN 1 ELSE 0 END, "
                f"substr(MAX(order_date), 7, 4) || substr(MAX(order_date), 4, 2) || substr(MAX(order_date), 1, 2) {self.sort_order}"
            )
        elif self.sort_column == "batch_id":
            order_clause = f"ORDER BY order_batch_id {self.sort_order}"
        else:
            order_clause = f"ORDER BY MAX({self.sort_column}) {self.sort_order}"

        base_query = '''SELECT order_batch_id, order_date, project_name, payment_date, manufacturer,
            delivery_days, delivery_unit_order, min_delivery_date, max_delivery_date,
            (SELECT subproject FROM orders WHERE order_batch_id = o.order_batch_id LIMIT 1) as subproject,
            (SELECT kd FROM orders WHERE order_batch_id = o.order_batch_id LIMIT 1) as kd,
            (SELECT invoice_number FROM orders WHERE order_batch_id = o.order_batch_id LIMIT 1) as invoice_number,
            (SELECT supplier FROM orders WHERE order_batch_id = o.order_batch_id LIMIT 1) as supplier,
            (SELECT delivery_number FROM orders WHERE order_batch_id = o.order_batch_id LIMIT 1) as delivery_number,
            (SELECT received FROM orders WHERE order_batch_id = o.order_batch_id LIMIT 1) as received,
            (SELECT receipt_date FROM orders WHERE order_batch_id = o.order_batch_id LIMIT 1) as receipt_date,
            (SELECT write_off_date FROM orders WHERE order_batch_id = o.order_batch_id LIMIT 1) as write_off_date,
            (SELECT price_request FROM orders WHERE order_batch_id = o.order_batch_id LIMIT 1) as price_request,
            (SELECT price_request_num FROM orders WHERE order_batch_id = o.order_batch_id LIMIT 1) as price_request_num,
            (SELECT status FROM orders WHERE order_batch_id = o.order_batch_id LIMIT 1) as status
            FROM orders o'''

        where_clause = ""
        params = []
        if filter_manufacturer:
            where_clause += " WHERE manufacturer = ?"
            params.append(filter_manufacturer)
        if filter_payment == "Есть дата":
            where_clause += (" AND" if where_clause else " WHERE") + " payment_date IS NOT NULL AND payment_date != ''"
        elif filter_payment == "Нет даты":
            where_clause += (" AND" if where_clause else " WHERE") + " (payment_date IS NULL OR payment_date = '')"
        if filter_received == "Получено":
            where_clause += (" AND" if where_clause else " WHERE") + " received = 1"
        elif filter_received == "Не получено":
            where_clause += (" AND" if where_clause else " WHERE") + " (received = 0 OR received IS NULL)"

        query = base_query + where_clause + f" GROUP BY order_batch_id {order_clause}"
        c.execute(query, params)

        for r in c.fetchall():
            received_mark = "✓" if r['received'] else ""
            pr = r['price_request'] or 0
            prn = r['price_request_num'] or 0
            # НОВОЕ: заказы-запросы цены нумеруются отдельно: Z1, Z2, ...
            disp = f"Z{prn}" if (pr and prn) else str(r['order_batch_id'])
            self._display2batch[disp] = r['order_batch_id']
            values = (
                disp, r['manufacturer'] or "",
                r['subproject'] or "", r['kd'] or "",
                r['order_date'] or "", r['project_name'] or "",
                r['payment_date'] or "",
                r['delivery_days'] or 0, r['delivery_unit_order'] or "",
                r['min_delivery_date'] or "", r['max_delivery_date'] or "",
                r['invoice_number'] or "", r['supplier'] or "",
                r['delivery_number'] or "",
                received_mark, r['receipt_date'] or "", r['write_off_date'] or "",
                r['status'] or "",        
                "✓" if pr else ""
            )
            item_id = self.tree_batches.insert("", tk.END, values=values)
            if r['min_delivery_date'] and r['max_delivery_date']:
                try:
                    min_date = datetime.strptime(r['min_delivery_date'], "%d.%m.%Y").date()
                    max_date = datetime.strptime(r['max_delivery_date'], "%d.%m.%Y").date()
                    if today < min_date and (min_date - today).days <= 7:
                        self.tree_batches.item(item_id, tags=('warning',))
                    elif today > max_date:
                        self.tree_batches.item(item_id, tags=('overdue',))
                except:
                    pass

        self.tree_batches.tag_configure('warning', background='lightgreen')
        self.tree_batches.tag_configure('overdue', background='lightcoral')
        self.current_batch_id = None
        self.current_item_id = None
        self.clear_batch_form()
        self.clear_items()

    def on_batch_click(self, event):
        """Клик по ячейкам-флагам: #15 = Получено, #18 = Запрос цены."""
        tree = self.tree_batches
        try:
            region = tree.identify_region(event.x, event.y)
            col = tree.identify_column(event.x)
            row_id = tree.identify_row(event.y)
        except Exception:
            return
        if region != "cell":
            return
        if col not in ('#15', '#18'):
            return
        if not row_id:
            return
        values = tree.item(row_id)['values']
        batch_id = self._batch_of(values[0])
        if col == '#15':
            current_received = 1 if values[14] == "✓" else 0
            new_received = 0 if current_received else 1
            receipt_date = ""
            if new_received == 1:
                receipt_date = datetime.now().strftime("%d.%m.%Y")
            self.db_manager.set_order_received(batch_id, new_received, receipt_date)
        else:
            current_pr = 1 if values[17] == "✓" else 0
            new_pr = 0 if current_pr else 1
            self.db_manager.set_order_price_request(batch_id, new_pr)
            if hasattr(self.parent, 'log_action'):
                self.parent.log_action(f"Переключено price_request={new_pr} у заказа {values[0]}")
        self.load_batches()
        for item in tree.get_children():
            v = tree.item(item)['values']
            if self._batch_of(v[0]) == batch_id:
                tree.selection_set(item)
                tree.see(item)
                break

    def clear_batch_form(self):
        self.entry_batch_date.delete(0, tk.END)
        self.entry_batch_project.delete(0, tk.END)
        self.entry_batch_payment.delete(0, tk.END)
        self.entry_delivery_days.delete(0, tk.END)
        self.entry_invoice_number.delete(0, tk.END)
        self.entry_delivery_number.delete(0, tk.END)
        self.entry_receipt_date.delete(0, tk.END)
        self.entry_write_off_date.delete(0, tk.END)
        self.combo_delivery_unit.set('')
        self.combo_batch_manufacturer.set('')
        self.combo_batch_subproject.set('')
        self.combo_batch_kd.set('')
        self.combo_batch_supplier.set('')
        self.received_var.set(False)

    def clear_items(self):
        for item in self.tree_items.get_children():
            self.tree_items.delete(item)
        self.clear_item_form()

    def clear_item_form(self):
        for e in (self.entry_item_article, self.entry_item_name, self.entry_item_quantity,
                  self.entry_item_delivery_term, self.entry_item_price, self.entry_item_note):
            e.delete(0, tk.END)
        self.combo_item_delivery_unit.set('')
        self.combo_item_currency.set('')

    def load_items(self, batch_id):
        for item in self.tree_items.get_children():
            self.tree_items.delete(item)
        self.current_item_id = None
        self.clear_item_form()
        for r in self.db_manager.get_order_items(batch_id):
            self.tree_items.insert("", tk.END, values=(
                r['id'], r['article'] or "", r['name'] or "",
                r['quantity'] or "", r['delivery_term'] or "", r['delivery_unit'] or "",
                r['price'] or "", r['currency'] or "", r['note'] or ""))

    def on_select_batch(self, event):
        selected = self.tree_batches.selection()
        if not selected:
            return
        values = self.tree_batches.item(selected[0])['values']
        self.current_batch_id = self._batch_of(values[0])
        self._load_batch_to_form(values)
        project_from_order = values[5]
        if project_from_order and project_from_order != self.project_name:
            self.project_name = project_from_order
            self.load_subprojects_for_combo()
            self.load_kd_for_combo()
        self.load_items(self.current_batch_id)

    def on_received_change(self):
        if not self.current_batch_id:
            return
        new_value = 1 if self.received_var.get() else 0
        receipt_date = self.entry_receipt_date.get()
        if new_value == 1 and not receipt_date:
            receipt_date = datetime.now().strftime("%d.%m.%Y")
            self.entry_receipt_date.delete(0, tk.END)
            self.entry_receipt_date.insert(0, receipt_date)
        self.db_manager.set_order_received(self.current_batch_id, new_value, receipt_date)
        self.load_batches()
        for item in self.tree_batches.get_children():
            v = self.tree_batches.item(item)['values']
            if self._batch_of(v[0]) == self.current_batch_id:
                self.tree_batches.selection_set(item)
                self.tree_batches.see(item)
                self._load_batch_to_form(v)
                break

    def on_select_item(self, event):
        selected = self.tree_items.selection()
        if not selected:
            return
        v = self.tree_items.item(selected[0])['values']
        self.current_item_id = v[0]
        self.entry_item_article.delete(0, tk.END); self.entry_item_article.insert(0, v[1])
        self.entry_item_name.delete(0, tk.END); self.entry_item_name.insert(0, v[2])
        self.entry_item_quantity.delete(0, tk.END); self.entry_item_quantity.insert(0, v[3])
        self.entry_item_delivery_term.delete(0, tk.END); self.entry_item_delivery_term.insert(0, v[4])
        self.combo_item_delivery_unit.set(v[5])
        self.entry_item_price.delete(0, tk.END); self.entry_item_price.insert(0, v[6])
        self.combo_item_currency.set(v[7])
        self.entry_item_note.delete(0, tk.END); self.entry_item_note.insert(0, v[8])

    def edit_item(self):
        selected = self.tree_items.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите позицию!")
            return
        v = self.tree_items.item(selected[0])['values']
        item_id = v[0]
        item_data = {
            'id': item_id,
            'article': str(v[1]) if len(v) > 1 and v[1] else '',
            'name': str(v[2]) if len(v) > 2 and v[2] else '',
            'quantity': int(v[3]) if len(v) > 3 and v[3] else 0,
            'delivery_term': int(v[4]) if len(v) > 4 and v[4] else 0,
            'delivery_unit': str(v[5]) if len(v) > 5 and v[5] else '',
            'price': str(v[6]) if len(v) > 6 and v[6] else '',
            'currency': str(v[7]) if len(v) > 7 and v[7] else '',
            'note': str(v[8]) if len(v) > 8 and v[8] else '',
        }
        dialog = OrderItemEditDialog(self, item_data)
        self.wait_window(dialog)
        if dialog.result is not None:
            try:
                self.db_manager.update_order_item(item_id, dialog.result)
                self.load_items(self.current_batch_id)
                if hasattr(self.parent, 'log_action'):
                    self.parent.log_action(f"Позиция #{item_id} отредактирована: {dialog.result.get('article', '')}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить изменения:\n{e}")
                traceback.print_exc()

    def save_batch(self):
        if self.current_batch_id is None:
            messagebox.showwarning("Внимание", "Выберите заказ!")
            return
        manufacturer = self.combo_batch_manufacturer.get().strip()
        subproject = self.combo_batch_subproject.get().strip()
        kd = self.combo_batch_kd.get().strip()
        supplier = self.combo_batch_supplier.get().strip()
        invoice_number = self.entry_invoice_number.get().strip()
        delivery_number = self.entry_delivery_number.get().strip()
        received = 1 if self.received_var.get() else 0
        receipt_date = self.entry_receipt_date.get()
        min_date = ""
        max_date = ""
        for item in self.tree_batches.get_children():
            v = self.tree_batches.item(item)['values']
            if self._batch_of(v[0]) == self.current_batch_id:
                min_date = v[9] if len(v) > 9 else ""
                max_date = v[10] if len(v) > 10 else ""
                break
        self.db_manager.update_order_batch(
            self.current_batch_id,
            self.entry_batch_date.get(),
            self.entry_batch_project.get(),
            self.entry_batch_payment.get(),
            self.entry_delivery_days.get(),
            self.combo_delivery_unit.get(),
            min_date, max_date
        )
        if manufacturer or subproject or kd or supplier or invoice_number:
            c = self.db_manager.conn.cursor()
            c.execute('''UPDATE orders SET manufacturer=?, subproject=?, kd=?, supplier=?, invoice_number=?
                WHERE order_batch_id=?''',
                (manufacturer, subproject, kd, supplier, invoice_number, self.current_batch_id))
            self.db_manager.conn.commit()
        self.db_manager.set_order_delivery_number(self.current_batch_id, delivery_number)
        self.db_manager.set_order_received(self.current_batch_id, received, receipt_date)
        self._save_write_off_date(self.current_batch_id, self.entry_write_off_date.get().strip())
        self._refresh_batches_keep_selection()

    def delete_batch(self):
        if self.current_batch_id is None:
            messagebox.showwarning("Внимание", "Выберите заказ!")
            return
        if messagebox.askyesno("Подтверждение", "Удалить заказ и все его позиции?"):
            self.db_manager.delete_order_batch(self.current_batch_id)
            self.load_batches()

    def save_item(self):
        if self.current_item_id is None:
            messagebox.showwarning("Внимание", "Выберите позицию!")
            return
        try:
            quantity = int(self.entry_item_quantity.get()) if self.entry_item_quantity.get() else 0
            delivery_term = int(self.entry_item_delivery_term.get()) if self.entry_item_delivery_term.get() else 0
        except:
            messagebox.showwarning("Ошибка", "Некорректное число!")
            return
        update_data = {
            'article': self.entry_item_article.get(),
            'name': self.entry_item_name.get(),
            'quantity': quantity,
            'delivery_term': delivery_term,
            'delivery_unit': self.combo_item_delivery_unit.get(),
            'price': self.entry_item_price.get(),
            'currency': self.combo_item_currency.get(),
            'note': self.entry_item_note.get(),
        }
        self.db_manager.update_order_item(self.current_item_id, update_data)
        self.load_items(self.current_batch_id)

    def delete_item(self):
        if self.current_item_id is None:
            messagebox.showwarning("Внимание", "Выберите позицию!")
            return
        if messagebox.askyesno("Подтверждение", "Удалить позицию?"):
            self.db_manager.delete_order_item(self.current_item_id)
            remaining = self.db_manager.get_order_items(self.current_batch_id)
            if not remaining:
                self.db_manager.delete_order_batch(self.current_batch_id)
                self.load_batches()
            else:
                self.load_items(self.current_batch_id)

    def import_from_file(self):
        if self.current_batch_id is None:
            messagebox.showwarning("Внимание", "Сначала выберите заказ!")
            return
        filepath = filedialog.askopenfilename(
            title="Выберите файл коммерческого предложения",
            filetypes=[("Excel и PDF", "*.xlsx *.xls *.pdf"), ("Excel", "*.xlsx *.xls"),
                       ("PDF", "*.pdf"), ("All files", "*.*")])
        if not filepath:
            return
        try:
            file_rows, full_text = parse_file_to_rows_with_text(filepath)
        except Exception as e:
            messagebox.showerror("Ошибка парсинга", f"Не удалось прочитать файл:\n{e}")
            return
        if not file_rows:
            messagebox.showwarning("Пустой файл", "Файл не содержит данных")
            return
        order_items = self.db_manager.get_order_items(self.current_batch_id)
        if not order_items:
            messagebox.showwarning("Пустой заказ", "В заказе нет позиций для сопоставления")
            return
        dialog = FileImportMatchDialog(self, order_items, file_rows, self.db_manager, full_text)
        self.wait_window(dialog)
        self.load_items(self.current_batch_id)

    def open_export_dialog(self):
        dialog = OrderExportDialog(self, self.db_manager)
        self.wait_window(dialog)

    @staticmethod
    def _sanitize_filename(s):
        bad = '\\/:*?"<>|\r\n\t'
        out = []
        for ch in str(s):
            out.append('_' if ch in bad else ch)
        res = "".join(out).strip()
        return res[:80] if res else "unknown"

    def export_order_to_excel(self):
        if not HAS_OPENPYXL:
            messagebox.showwarning("Нет библиотеки", "Установите: pip install openpyxl")
            return
        if self.current_batch_id is None:
            messagebox.showwarning("Внимание", "Выделите заказ!")
            return
        header = None
        for b in self.db_manager.get_order_batches():
            if b['order_batch_id'] == self.current_batch_id:
                header = b
                break
        if header is None:
            messagebox.showwarning("Внимание", "Заказ не найден!")
            return
        batch_id = header['order_batch_id']
        date_str = header['order_date'] or ""
        project_str = header['project_name'] or ""
        items = self.db_manager.get_order_items(self.current_batch_id)
        if not items:
            messagebox.showwarning("Внимание", "В заказе нет позиций!")
            return
        seen = []
        for p in items:
            m = (p['manufacturer'] or "").strip()
            if m and m not in seen:
                seen.append(m)
        manufacturer_str = ", ".join(seen) if seen else ""
        manufacturer_file = "_".join(seen) if seen else "unknown"
        seen_sub = []
        for p in items:
            s = (p['subproject'] or "").strip()
            if s and s not in seen_sub:
                seen_sub.append(s)
        subproject_str = ", ".join(seen_sub) if seen_sub else ""
        date_part = date_str if date_str else "nodate"
        pr = header['price_request'] if 'price_request' in header.keys() else 0
        prn = header['price_request_num'] if 'price_request_num' in header.keys() else 0
        order_label = f"Z{prn}" if (pr and prn) else str(batch_id)
        base_name = f"order {order_label} {date_part} {self._sanitize_filename(manufacturer_file)}"
        filename = base_name + ".xlsx"
        directory = filedialog.askdirectory(title="Выберите папку", parent=self)
        if not directory:
            return
        full_path = os.path.join(directory, filename)
        if os.path.exists(full_path):
            if not messagebox.askyesno("Файл существует", f"Перезаписать?\n{full_path}", parent=self):
                return
        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Order"
            bold = Font(bold=True)
            ws['A1'] = "Order"
            ws['A1'].font = bold
            ws['A2'] = date_str
            ws['B2'] = manufacturer_str
            ws['C2'] = project_str
            ws['D2'] = subproject_str
            for cell in [ws['A2'], ws['B2'], ws['C2'], ws['D2']]:
                cell.font = bold
            headers = ["Manufacturer", "Article", "Name (EN)", "Quantity"]
            for i, h in enumerate(headers, start=1):
                ws.cell(row=4, column=i, value=h).font = bold
            row = 5
            for p in items:
                ws.cell(row=row, column=1, value=p['manufacturer'] or "")
                ws.cell(row=row, column=2, value=p['article'] or "")
                ws.cell(row=row, column=3, value=p['name_eng'] or "")
                ws.cell(row=row, column=4, value=p['quantity'] if p['quantity'] is not None else "")
                row += 1
            for col_idx in range(1, 5):
                max_len = 0
                for r in range(1, ws.max_row + 1):
                    v = ws.cell(row=r, column=col_idx).value
                    if v is not None:
                        max_len = max(max_len, len(str(v)))
                ws.column_dimensions[get_column_letter(col_idx)].width = min(max(max_len + 2, 10), 60)
            wb.save(full_path)
        except PermissionError:
            error_msg = f"ОШИБКА ДОСТУПА: Файл открыт в другой программе или нет прав на запись.\nПуть: {full_path}"
            print(error_msg)
            if hasattr(self.parent, 'log_action'):
                self.parent.log_action(f"Ошибка экспорта Excel (доступ): {full_path}")
            messagebox.showerror("Ошибка доступа", error_msg)
            return
        except Exception as e:
            error_msg = f"Не удалось создать файл.\nПричина: {e}"
            full_traceback = traceback.format_exc()
            print("\n" + "="*50)
            print("ПОЛНАЯ ОШИБКА ЭКСПОРТА EXCEL:")
            print(full_traceback)
            print("="*50 + "\n")
            if hasattr(self.parent, 'log_action'):
                self.parent.log_action(f"Ошибка экспорта Excel: {e}")
            messagebox.showerror("Ошибка", error_msg + "\n\nПодробности смотрите в терминале.")
            return
        messagebox.showinfo("Успех", f"Файл успешно сохранён:\n{full_path}", parent=self)