import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import os
import traceback
from datetime import datetime, timedelta

from utils import add_months, add_working_days_with_holidays
from dialogs.calendar_dialog import CalendarDialog
from dialogs.order_item_edit_dialog import OrderItemEditDialog
from dialogs.order_export_dialog import OrderExportDialog
from dialogs.supplier_dialog import SupplierDialog

try:
    from dialogs.order_file_parser import parse_file_to_rows_with_text
except Exception:
    parse_file_to_rows_with_text = None
try:
    from dialogs.file_import_dialog import FileImportMatchDialog
except Exception:
    FileImportMatchDialog = None
try:
    import openpyxl
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

try:
    from config import ORDER_CURRENCIES, TIME_UNITS
except ImportError:
    ORDER_CURRENCIES = ["EUR", "USD", "CNY", "RUB", "TRY"]
    TIME_UNITS = ["Календарные дни", "Рабочие дни", "Недели", "Месяцы"]


def _f(v, default=0.0):
    try:
        return float(str(v).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return default


class OrderDialog(tk.Toplevel):
    def __init__(self, parent, db_manager, batch_id=None,
                 russian_holidays=None, project_name=None):
        super().__init__(parent)
        self.parent = parent
        if not hasattr(self.parent, "log_action"):
            _app = getattr(parent, "app", None)
            if _app is not None and hasattr(_app, "log_action"):
                self.parent = _app

        self.title("База заказов")
        self.geometry("1650x1000")
        try:
            from dialogs.window_geometry import restore_geometry, track_geometry
            restore_geometry(self, "order_dialog", "1650x1000")
            track_geometry(self, "order_dialog")
        except Exception:
            pass

        self.db_manager = db_manager
        self.project_name = project_name or ""
        self.russian_holidays = russian_holidays or set()
        self.current_batch_id = None
        self.current_item_id = None
        self.sort_column = "order_date"
        self.sort_order = "DESC"
        self._display2batch = {}
        self._inline = None

        self.create_ui()

        if batch_id:
            self.current_batch_id = batch_id
            self.load_items(batch_id)
            for iid in self.tree_batches.get_children():
                if self._batch_of(self.tree_batches.item(iid)['values'][0]) == batch_id:
                    self.tree_batches.selection_set(iid)
                    self.tree_batches.see(iid)
                    self._load_batch_to_form(self.tree_batches.item(iid)['values'])
                    break

    # ==================================================================
    # Интерфейс
    # ==================================================================
    def create_ui(self):
        ff = ttk.Frame(self)
        ff.pack(fill="x", padx=8, pady=6)
        ttk.Label(ff, text="Заказы", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(ff, text="Фильтр по производителю:").pack(side=tk.LEFT)
        self.combo_filter_manufacturer = ttk.Combobox(ff, width=20, state="readonly")
        self.combo_filter_manufacturer.pack(side=tk.LEFT, padx=5)
        self.combo_filter_manufacturer.bind("<<ComboboxSelected>>", lambda e: self.load_batches())
        ttk.Label(ff, text="Дата оплаты:").pack(side=tk.LEFT, padx=(10, 0))
        self.combo_filter_payment = ttk.Combobox(ff, width=10, state="readonly",
                                                 values=["Все", "Есть дата", "Нет даты"])
        self.combo_filter_payment.set("Все")
        self.combo_filter_payment.pack(side=tk.LEFT, padx=5)
        self.combo_filter_payment.bind("<<ComboboxSelected>>", lambda e: self.load_batches())
        ttk.Label(ff, text="Получено:").pack(side=tk.LEFT, padx=(10, 0))
        self.combo_filter_received = ttk.Combobox(ff, width=12, state="readonly",
                                                  values=["Все", "Получено", "Не получено"])
        self.combo_filter_received.set("Все")
        self.combo_filter_received.pack(side=tk.LEFT, padx=5)
        self.combo_filter_received.bind("<<ComboboxSelected>>", lambda e: self.load_batches())
        ttk.Button(ff, text="База Поставщиков", command=self.open_suppliers).pack(side=tk.RIGHT, padx=5)
        ttk.Button(ff, text="Экспорт в Excel", command=self.open_export_dialog).pack(side=tk.RIGHT, padx=5)

        # --- Верхняя таблица: 19 колонок, правка по двойному клику ---
        bf = ttk.LabelFrame(self, text="Заказы  ·  двойной клик по ячейке — правка, Enter — сохранить, Esc — отмена",
                            padding=4)
        bf.pack(fill="both", expand=False, padx=8, pady=4)
        cols_b = ("batch_id", "manufacturer", "subproject", "kd", "order_date",
                  "project_name", "payment_date", "delivery_days", "delivery_unit_order",
                  "min_delivery_date", "max_delivery_date", "invoice_number", "supplier",
                  "delivery_number", "received", "receipt_date", "write_off_date",
                  "price_request", "status")
        self.tree_batches = ttk.Treeview(bf, columns=cols_b, show="headings", height=8)
        heads = {"batch_id": ("№ заказа", 60), "manufacturer": ("Производитель", 110),
                 "subproject": ("Подпроект", 110), "kd": ("КД", 60),
                 "order_date": ("Дата заказа", 90), "project_name": ("Проект", 130),
                 "payment_date": ("Дата оплаты", 90), "delivery_days": ("Доставка", 60),
                 "delivery_unit_order": ("Ед. доставки", 90),
                 "min_delivery_date": ("Min дата пост.", 100),
                 "max_delivery_date": ("Max дата пост.", 100),
                 "invoice_number": ("Номер инвойса", 110), "supplier": ("Поставщик", 150),
                 "delivery_number": ("Номер поставки", 100), "received": ("Получено", 60),
                 "receipt_date": ("Дата получения", 100), "write_off_date": ("Дата списания", 100),
                 "price_request": ("Запрос цены", 80), "status": ("Статус", 110)}
        for c in cols_b:
            t, w = heads[c]
            self.tree_batches.heading(c, text=t, command=lambda cc=c: self.sort_by_column(cc))
            self.tree_batches.column(c, width=w, anchor="center" if c in
                                     ("batch_id", "order_date", "payment_date", "delivery_days",
                                      "min_delivery_date", "max_delivery_date", "received",
                                      "receipt_date", "write_off_date", "price_request") else "w")
        sb = ttk.Scrollbar(bf, orient=tk.VERTICAL, command=self.tree_batches.yview)
        self.tree_batches.configure(yscroll=sb.set)
        self.tree_batches.pack(side=tk.LEFT, fill="both", expand=True)
        sb.pack(side=tk.RIGHT, fill="y")
        self.tree_batches.bind("<<TreeviewSelect>>", self.on_select_batch)
        self.tree_batches.bind("<Button-1>", self.on_batch_click)
        self.tree_batches.bind("<Double-1>", self.on_batch_double_click)

        # --- Заголовок заказа ---
        hf = ttk.LabelFrame(self, text="Заголовок заказа", padding=8)
        hf.pack(fill="x", padx=8, pady=4)
        ttk.Label(hf, text="Дата заказа:").grid(row=0, column=0, sticky="w")
        self.entry_batch_date = ttk.Entry(hf, width=12)
        self.entry_batch_date.grid(row=0, column=1, padx=5)
        ttk.Button(hf, text="📅", width=3, command=self.select_order_date).grid(row=0, column=2)
        ttk.Label(hf, text="Проект:").grid(row=0, column=3, sticky="w", padx=(12, 0))
        self.entry_batch_project = ttk.Entry(hf, width=18)
        self.entry_batch_project.grid(row=0, column=4, padx=5)
        ttk.Label(hf, text="Дата оплаты:").grid(row=0, column=5, sticky="w", padx=(12, 0))
        self.entry_batch_payment = ttk.Entry(hf, width=12)
        self.entry_batch_payment.grid(row=0, column=6, padx=5)
        ttk.Button(hf, text="📅", width=3, command=self.select_payment_date).grid(row=0, column=7)
        ttk.Label(hf, text="Номер инвойса:").grid(row=0, column=8, sticky="w", padx=(12, 0))
        self.entry_invoice_number = ttk.Entry(hf, width=16)
        self.entry_invoice_number.grid(row=0, column=9, padx=5)
        ttk.Label(hf, text="Поставщик:").grid(row=0, column=10, sticky="w", padx=(12, 0))
        self.combo_batch_supplier = ttk.Combobox(hf, width=22)
        self.combo_batch_supplier.grid(row=0, column=11, padx=5)
        ttk.Label(hf, text="Номер поставки:").grid(row=0, column=12, sticky="w", padx=(12, 0))
        self.entry_delivery_number = ttk.Entry(hf, width=14)
        self.entry_delivery_number.grid(row=0, column=13, padx=5)

        ttk.Label(hf, text="Производитель:").grid(row=1, column=0, sticky="w", pady=4)
        self.combo_batch_manufacturer = ttk.Combobox(hf, width=16)
        self.combo_batch_manufacturer.grid(row=1, column=1, padx=5, pady=4)
        ttk.Label(hf, text="Подпроект:").grid(row=1, column=3, sticky="w", pady=4)
        self.combo_batch_subproject = ttk.Combobox(hf, width=16)
        self.combo_batch_subproject.grid(row=1, column=4, padx=5, pady=4)
        ttk.Label(hf, text="КД:").grid(row=1, column=5, sticky="w", pady=4)
        self.combo_batch_kd = ttk.Combobox(hf, width=10)
        self.combo_batch_kd.grid(row=1, column=6, padx=5, pady=4)
        ttk.Label(hf, text="Доставка:").grid(row=1, column=8, sticky="w", pady=4)
        self.entry_delivery_days = ttk.Entry(hf, width=6)
        self.entry_delivery_days.grid(row=1, column=9, padx=5, pady=4)
        ttk.Label(hf, text="Ед.:").grid(row=1, column=10, sticky="w", pady=4)
        self.combo_delivery_unit = ttk.Combobox(hf, values=TIME_UNITS, state="readonly", width=16)
        self.combo_delivery_unit.grid(row=1, column=11, padx=5, pady=4)
        self.received_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(hf, text="Получено", variable=self.received_var,
                        command=self.on_received_change).grid(row=1, column=12, sticky="w", pady=4)
        ttk.Label(hf, text="Дата получения:").grid(row=1, column=13, sticky="w", pady=4)
        self.entry_receipt_date = ttk.Entry(hf, width=12)
        self.entry_receipt_date.grid(row=1, column=14, padx=5, pady=4)
        ttk.Button(hf, text="📅", width=3, command=self.select_receipt_date).grid(row=1, column=15, pady=4)

        ttk.Label(hf, text="Дата списания:").grid(row=2, column=0, sticky="w", pady=4)
        self.entry_write_off_date = ttk.Entry(hf, width=12)
        self.entry_write_off_date.grid(row=2, column=1, padx=5, pady=4)
        ttk.Button(hf, text="📅", width=3, command=self.select_write_off_date).grid(row=2, column=2, pady=4)
        ttk.Label(hf, text="Статус:").grid(row=2, column=3, sticky="w", pady=4)
        self.lbl_batch_status = ttk.Label(hf, text="", foreground="#0066cc", font=("Arial", 9, "bold"))
        self.lbl_batch_status.grid(row=2, column=4, sticky="w", pady=4)

        # --- Кнопки действий ---
        af = ttk.Frame(self)
        af.pack(fill="x", padx=8, pady=4)
        ttk.Button(af, text="Импорт из файла (Excel/PDF)", command=self.import_from_file).pack(side=tk.LEFT, padx=4)
        ttk.Button(af, text="Рассчитать даты", command=self.calculate_delivery_dates).pack(side=tk.LEFT, padx=4)
        ttk.Button(af, text="Статус / ETA", command=self.edit_status).pack(side=tk.LEFT, padx=4)
        ttk.Button(af, text="Заполнить статусы", command=self.fill_item_statuses).pack(side=tk.LEFT, padx=4)
        ttk.Button(af, text="Получено ВСЁ", command=self.receive_all_items).pack(side=tk.LEFT, padx=4)
        ttk.Button(af, text="Сохранить заказ", command=self.save_batch).pack(side=tk.LEFT, padx=4)
        ttk.Button(af, text="Удалить заказ", command=self.delete_batch).pack(side=tk.LEFT, padx=4)
        ttk.Button(af, text="База статусов артикула", command=self.open_item_statuses).pack(side=tk.LEFT, padx=4)
        ttk.Button(af, text="Заказ в файл АНГ", command=self.export_order_to_excel).pack(side=tk.RIGHT, padx=4)

        # --- Нижняя таблица: 12 колонок, «Остаток» после «Получено, кол-во» ---
        pf = ttk.LabelFrame(self, text="Позиции заказа  ·  двойной клик по ячейке — правка, "
                                       "Enter — сохранить, Tab — дальше, Esc — отмена", padding=6)
        pf.pack(fill="both", expand=True, padx=8, pady=4)
        cols_i = ("id", "article", "name", "quantity", "qty_received", "rest",
                  "delivery_term", "delivery_unit", "price", "currency", "note", "item_status")
        self.tree_items = ttk.Treeview(pf, columns=cols_i, show="headings", height=10,
                                       selectmode="extended")
        heads_i = {"id": ("ID", 55), "article": ("Артикул", 150), "name": ("Наименование", 260),
                   "quantity": ("Кол-во", 65), "qty_received": ("Получено, кол-во", 100),
                   "rest": ("Остаток", 75),
                   "delivery_term": ("Срок поставки", 85), "delivery_unit": ("Единица", 90),
                   "price": ("Цена", 85), "currency": ("Валюта", 60),
                   "note": ("Примечание", 190), "item_status": ("Статус артикула", 125)}
        for c in cols_i:
            t, w = heads_i[c]
            self.tree_items.heading(c, text=t)
            self.tree_items.column(c, width=w, anchor="center" if c in
                                   ("id", "quantity", "qty_received", "rest", "delivery_term",
                                    "price", "currency") else "w")
        si = ttk.Scrollbar(pf, orient=tk.VERTICAL, command=self.tree_items.yview)
        self.tree_items.configure(yscroll=si.set)
        self.tree_items.pack(side=tk.LEFT, fill="both", expand=True)
        si.pack(side=tk.RIGHT, fill="y")
        self.tree_items.tag_configure('part', background='#fff2cc')
        self.tree_items.tag_configure('full', background='#d9ead3')
        self.tree_items.bind("<<TreeviewSelect>>", self.on_select_item)
        self.tree_items.bind("<Double-1>", self.on_items_double_click)

        # --- Форма позиции ---
        itf = ttk.LabelFrame(self, text="Позиция", padding=6)
        itf.pack(fill="x", padx=8, pady=4)
        ttk.Label(itf, text="Артикул:").grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.entry_item_article = ttk.Entry(itf, width=26)
        self.entry_item_article.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        ttk.Label(itf, text="Наименование:").grid(row=0, column=2, sticky="w", padx=(0, 5))
        self.entry_item_name = ttk.Entry(itf, width=34)
        self.entry_item_name.grid(row=0, column=3, sticky="ew", padx=(0, 10))
        ttk.Label(itf, text="Кол-во:").grid(row=0, column=4, sticky="w", padx=(0, 5))
        self.entry_item_quantity = ttk.Entry(itf, width=9)
        self.entry_item_quantity.grid(row=0, column=5, sticky="w", padx=(0, 10))
        ttk.Label(itf, text="Получено:").grid(row=0, column=6, sticky="w", padx=(0, 5))
        self.entry_item_qty_received = ttk.Entry(itf, width=9)
        self.entry_item_qty_received.grid(row=0, column=7, sticky="w", padx=(0, 10))
        ttk.Label(itf, text="Остаток:").grid(row=0, column=8, sticky="w", padx=(0, 5))
        self.lbl_item_rest = ttk.Label(itf, text="0", foreground="#b00", font=("Arial", 9, "bold"))
        self.lbl_item_rest.grid(row=0, column=9, sticky="w")

        ttk.Label(itf, text="Срок:").grid(row=1, column=0, sticky="w", padx=(0, 5), pady=(8, 0))
        self.entry_item_delivery_term = ttk.Entry(itf, width=10)
        self.entry_item_delivery_term.grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Label(itf, text="Единица:").grid(row=1, column=2, sticky="w", padx=(0, 5), pady=(8, 0))
        self.combo_item_delivery_unit = ttk.Combobox(itf, values=TIME_UNITS, state="readonly", width=18)
        self.combo_item_delivery_unit.grid(row=1, column=3, sticky="w", pady=(8, 0))
        ttk.Label(itf, text="Цена:").grid(row=1, column=4, sticky="w", padx=(0, 5), pady=(8, 0))
        self.entry_item_price = ttk.Entry(itf, width=12)
        self.entry_item_price.grid(row=1, column=5, sticky="w", pady=(8, 0))
        ttk.Label(itf, text="Валюта:").grid(row=1, column=6, sticky="w", padx=(0, 5), pady=(8, 0))
        self.combo_item_currency = ttk.Combobox(itf, values=ORDER_CURRENCIES, state="readonly", width=10)
        self.combo_item_currency.grid(row=1, column=7, sticky="w", pady=(8, 0))

        ttk.Label(itf, text="Примечание:").grid(row=2, column=0, sticky="w", padx=(0, 5), pady=(8, 0))
        self.entry_item_note = ttk.Entry(itf, width=50)
        self.entry_item_note.grid(row=2, column=1, columnspan=9, sticky="ew", pady=(8, 0))

        ttk.Label(itf, text="Статус артикула:").grid(row=3, column=0, sticky="w", padx=(0, 5), pady=(8, 0))
        self.combo_item_status = ttk.Combobox(itf, width=24, state="readonly")
        self.combo_item_status.grid(row=3, column=1, sticky="w", pady=(8, 0))
        self.combo_item_status.bind("<<ComboboxSelected>>", self.on_item_status_selected)
        ttk.Button(itf, text="+", width=2,
                   command=self.add_item_status_inline).grid(row=3, column=2, sticky="w", padx=4, pady=(8, 0))
        ttk.Button(itf, text="Применить к выбранным",
                   command=self.apply_status_to_selected).grid(row=3, column=3, columnspan=2,
                                                               sticky="w", padx=6, pady=(8, 0))
        self.lbl_status_hint = ttk.Label(itf, text="", foreground="gray")
        self.lbl_status_hint.grid(row=3, column=5, columnspan=5, sticky="w", pady=(8, 0))

        for col in (1, 3, 5):
            itf.grid_columnconfigure(col, weight=1)

        btnf = ttk.Frame(itf)
        btnf.grid(row=4, column=0, columnspan=10, pady=(10, 0))
        ttk.Button(btnf, text="Сохранить позицию", command=self.save_item).pack(side=tk.LEFT, padx=5)
        ttk.Button(btnf, text="Удалить позицию", command=self.delete_item).pack(side=tk.LEFT, padx=5)
        ttk.Button(btnf, text="Карточка позиции", command=self.edit_item).pack(side=tk.LEFT, padx=5)
        ttk.Button(btnf, text="Закрыть", command=self.destroy).pack(side=tk.RIGHT, padx=5)

        self.load_manufacturers_for_combo()
        if hasattr(self.db_manager, "ensure_column"):
            self.db_manager.ensure_column("orders", "write_off_date")
        self._refresh_item_statuses()
        self.load_batches()

        self._bind_ids = []
        for seq in ("<Control-c>", "<Control-C>", "<Control-v>", "<Control-V>",
                    "<Control-x>", "<Control-X>"):
            self._bind_ids.append((seq, self.bind_all(seq, self._handle_clipboard)))
        self._original_destroy = self.destroy
        self.destroy = self._safe_destroy
        self._safe_grab()

    def _safe_grab(self, attempts=10):
        try:
            if self.winfo_exists() and self.winfo_viewable():
                self.grab_set()
            elif attempts > 0:
                self.after(60, lambda a=attempts - 1: self._safe_grab(a))
        except tk.TclError:
            if attempts > 0:
                self.after(60, lambda a=attempts - 1: self._safe_grab(a))

    def _safe_destroy(self):
        self._inline_cancel()
        for seq, _bid in getattr(self, "_bind_ids", []):
            try:
                self.unbind_all(seq)
            except Exception:
                pass
        self._original_destroy()

    def _batch_of(self, display):
        return self._display2batch.get(str(display), display)

    def _log(self, msg):
        try:
            if hasattr(self.parent, "log_action"):
                self.parent.log_action(msg)
        except Exception:
            pass

    # ==================================================================
    # Буфер обмена (русская раскладка)
    # ==================================================================
    def _handle_clipboard(self, event):
        try:
            if event.widget.winfo_toplevel() != self:
                return None
        except Exception:
            return None
        ch = (event.char or "").lower()
        if ch in ("c", "с"):
            return self._copy_ru()
        if ch in ("v", "м"):
            return self._paste_ru()
        if ch in ("x", "х"):
            return self._cut_ru()
        return None

    def _copy_ru(self):
        try:
            w = self.focus_get()
            if w is not None and hasattr(w, "selection_get"):
                self.clipboard_clear()
                self.clipboard_append(w.selection_get())
        except Exception:
            pass
        return "break"

    def _paste_ru(self):
        try:
            w = self.focus_get()
            if w is not None and hasattr(w, "insert"):
                data = self.clipboard_get()
                try:
                    w.delete(tk.SEL_FIRST, tk.SEL_LAST)
                except Exception:
                    pass
                w.insert(tk.INSERT, data)
        except Exception:
            pass
        return "break"

    def _cut_ru(self):
        try:
            w = self.focus_get()
            if w is not None and hasattr(w, "selection_get"):
                self.clipboard_clear()
                self.clipboard_append(w.selection_get())
                w.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except Exception:
            pass
        return "break"

    # ==================================================================
    # Справочники
    # ==================================================================
    def load_manufacturers_filter(self):
        c = self.db_manager.conn.cursor()
        c.execute("SELECT DISTINCT manufacturer FROM orders WHERE manufacturer IS NOT NULL "
                  "AND manufacturer != '' ORDER BY manufacturer")
        self.combo_filter_manufacturer['values'] = [''] + [r[0] for r in c.fetchall()]

    def load_suppliers(self):
        c = self.db_manager.conn.cursor()
        c.execute("SELECT name FROM suppliers ORDER BY name")
        self.combo_batch_supplier['values'] = [r[0] for r in c.fetchall()]

    def open_suppliers(self):
        self.wait_window(SupplierDialog(self, self.db_manager))
        self.load_suppliers()

    def sort_by_column(self, column):
        if self.sort_column == column:
            self.sort_order = "ASC" if self.sort_order == "DESC" else "DESC"
        else:
            self.sort_column = column
            self.sort_order = "ASC"
        self.load_batches()

    def load_manufacturers_for_combo(self):
        c = self.db_manager.conn.cursor()
        c.execute("SELECT name FROM manufacturers ORDER BY name")
        self.combo_batch_manufacturer['values'] = [r[0] for r in c.fetchall()]
        self.load_subprojects_for_combo()
        self.load_kd_for_combo()
        self.load_suppliers()
        self.load_manufacturers_filter()

    def load_subprojects_for_combo(self):
        c = self.db_manager.conn.cursor()
        if self.project_name:
            c.execute("SELECT name FROM subprojects WHERE (project_name=? OR project_name='' "
                      "OR project_name IS NULL) ORDER BY name", (self.project_name,))
        else:
            c.execute("SELECT name FROM subprojects ORDER BY name")
        self.combo_batch_subproject['values'] = [r[0] for r in c.fetchall()]

    def load_kd_for_combo(self):
        c = self.db_manager.conn.cursor()
        if self.project_name:
            c.execute("SELECT kd_number FROM kd_directory WHERE (project_name=? OR project_name='' "
                      "OR project_name IS NULL) ORDER BY kd_number", (self.project_name,))
        else:
            c.execute("SELECT kd_number FROM kd_directory ORDER BY kd_number")
        self.combo_batch_kd['values'] = [r[0] for r in c.fetchall()]

    # ==================================================================
    # НОВОЕ 1: Заполнить статусы артикулов статусом заказа
    # ==================================================================
    def _current_order_status(self):
        try:
            st = (self.db_manager.get_order_status(self.current_batch_id) or {}).get("status") or ""
        except Exception:
            st = ""
        return st.strip() or (self.lbl_batch_status.cget("text") or "").strip()

    def fill_item_statuses(self):
        if self.current_batch_id is None:
            messagebox.showwarning("Внимание", "Выберите заказ!", parent=self)
            return
        status = self._current_order_status()
        if not status:
            if messagebox.askyesno("Статус заказа пустой",
                                   "У заказа не заполнен статус.\nЗаполнить его сейчас?", parent=self):
                self.edit_status()
                status = self._current_order_status()
            if not status:
                messagebox.showinfo("Отмена", "Статус заказа не задан — статусы артикулов не изменены.",
                                    parent=self)
                return
        items = self._items_rows(self.current_batch_id)
        if not items:
            messagebox.showinfo("Информация", "В заказе нет позиций.", parent=self)
            return
        if not messagebox.askyesno("Подтверждение",
                                   f"Проставить статус «{status}» всем позициям заказа ({len(items)} шт.)?",
                                   parent=self):
            return
        try:
            self.db_manager.add_item_status(status)     # добавляем в справочник, если нового
        except Exception:
            pass
        self.db_manager.set_batch_item_status(self.current_batch_id, status)
        self._refresh_item_statuses()
        self._reload_items_keep(self.current_item_id)
        self.lbl_status_hint.config(text=f"«{status}» проставлен {len(items)} позициям")
        self._log(f"Заказ {self.current_batch_id}: статус артикулов «{status}» проставлен {len(items)} позициям")

    # ==================================================================
    # НОВОЕ 2: Получено ВСЁ
    # ==================================================================
    def receive_all_items(self):
        if self.current_batch_id is None:
            messagebox.showwarning("Внимание", "Выберите заказ!", parent=self)
            return
        items = self._items_rows(self.current_batch_id)
        if not items:
            messagebox.showinfo("Информация", "В заказе нет позиций.", parent=self)
            return
        if not messagebox.askyesno("Подтверждение",
                                   f"Отметить полученным ВСЁ количество по {len(items)} позициям?\n"
                                   "Дата получения будет проставлена, статус заказа станет «Получен».",
                                   parent=self):
            return
        today = datetime.now().strftime("%d.%m.%Y")
        done = 0
        for it in items:
            qty = _f(it.get("quantity"), 0)
            try:
                if hasattr(self.db_manager, "receive_order_item"):
                    self.db_manager.receive_order_item(it["id"], qty, today)
                else:
                    self.db_manager.update_order_item(it["id"], {"qty_received": qty})
                done += 1
            except Exception as e:
                print(f"[order_dialog] receive_all: {e}")
        self._reload_items_keep(self.current_item_id)
        self._refresh_batches_keep_selection()
        self._log(f"Заказ {self.current_batch_id}: получено ВСЁ по {done} позициям")
        messagebox.showinfo("Готово", f"Отмечено полученным: {done} позиций", parent=self)

    # ==================================================================
    # Статусы артикулов
    # ==================================================================
    def _refresh_item_statuses(self):
        vals = []
        try:
            if hasattr(self.db_manager, "get_item_statuses"):
                vals = list(self.db_manager.get_item_statuses())
        except Exception as e:
            print(f"[order_dialog] статусы артикулов: {e}")
        if not vals:
            vals = ["Не заказан", "Заказан", "В производстве", "Отгружен",
                    "Получен", "Брак/замена", "Отменён"]
        try:
            self.combo_item_status['values'] = vals
        except Exception:
            pass

    def on_item_status_selected(self, event=None):
        status = self.combo_item_status.get().strip()
        if not status:
            return
        if self.current_item_id is None:
            self.lbl_status_hint.config(text="выберите позицию или нажмите «Применить к выбранным»")
            return
        try:
            self.db_manager.set_item_status(self.current_item_id, status)
            self._reload_items_keep(self.current_item_id)
            self.combo_item_status.set(status)
            self.lbl_status_hint.config(text=f"позиция #{self.current_item_id}: {status}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить статус:\n{e}", parent=self)

    def add_item_status_inline(self):
        name = simpledialog.askstring("Статус артикула", "Новый статус:", parent=self)
        if name and name.strip():
            if self.db_manager.add_item_status(name):
                self._refresh_item_statuses()
                self.combo_item_status.set(name.strip())
                self.on_item_status_selected()
            else:
                messagebox.showwarning("Внимание", "Такой статус уже есть.", parent=self)

    def open_item_statuses(self):
        try:
            from dialogs.item_status_dialog import ItemStatusesDialog
        except ImportError:
            messagebox.showerror("Ошибка", "dialogs/item_status_dialog.py не найден", parent=self)
            return
        ItemStatusesDialog(self, self.db_manager, on_changed=self._refresh_item_statuses)
        self._refresh_item_statuses()
        if self.current_batch_id is not None:
            self._reload_items_keep(self.current_item_id)

    def apply_status_to_selected(self):
        sel = self.tree_items.selection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите одну или несколько позиций!", parent=self)
            return
        status = self.combo_item_status.get().strip()
        if not status:
            messagebox.showwarning("Внимание", "Выберите статус артикула в списке!", parent=self)
            return
        for iid in sel:
            self.db_manager.set_item_status(self.tree_items.item(iid)['values'][0], status)
        self.load_items(self.current_batch_id)
        self.lbl_status_hint.config(text=f"«{status}» присвоен {len(sel)} позициям")

    # ==================================================================
    # ИНЛАЙН-РЕДАКТИРОВАНИЕ (обе таблицы)
    # ==================================================================
    # нижняя таблица: индекс -> (поле БД, тип)
    _ITEM_EDIT_COLS = {
        1: ("article", "text"),
        2: ("name", "text"),
        3: ("quantity", "int"),
        4: ("qty_received", "float"),
        # 5 = Остаток (вычисляемый, не редактируется)
        6: ("delivery_term", "int"),
        7: ("delivery_unit", "unit"),
        8: ("price", "text"),
        9: ("currency", "currency"),
        10: ("note", "text"),
        11: ("item_status", "status"),
    }
    # верхняя таблица: индекс -> (колонка orders, тип)
    _BATCH_EDIT_COLS = {
        1: ("manufacturer", "manufacturer"),
        2: ("subproject", "subproject"),
        3: ("kd", "kd"),
        4: ("order_date", "date"),
        5: ("project_name", "project"),
        6: ("payment_date", "date"),
        7: ("delivery_days", "int"),
        8: ("delivery_unit_order", "unit"),
        9: ("min_delivery_date", "date"),
        10: ("max_delivery_date", "date"),
        11: ("invoice_number", "text"),
        12: ("supplier", "supplier"),
        13: ("delivery_number", "text"),
        # 14 и 17 — флаги, переключаются одиночным кликом
        15: ("receipt_date", "date"),
        16: ("write_off_date", "date"),
        18: ("status", "order_status"),
    }

    def on_items_double_click(self, event):
        tree = self.tree_items
        if tree.identify_region(event.x, event.y) != "cell":
            return
        row, col = tree.identify_row(event.y), tree.identify_column(event.x)
        if not row or not col:
            return
        idx = int(col.replace("#", "")) - 1
        if idx == 0:
            self.edit_item()
            return "break"
        if idx == 5:
            messagebox.showinfo("Остаток", "Остаток = Кол-во − Получено и считается автоматически.\n"
                                           "Измените «Кол-во» или «Получено, кол-во».", parent=self)
            return "break"
        self._inline_begin(tree, "items", row, col, idx, self._ITEM_EDIT_COLS)
        return "break"

    def on_batch_double_click(self, event):
        tree = self.tree_batches
        if tree.identify_region(event.x, event.y) != "cell":
            return
        row, col = tree.identify_row(event.y), tree.identify_column(event.x)
        if not row or not col:
            return
        idx = int(col.replace("#", "")) - 1
        if idx in (0, 14, 17):
            return "break"          # номер и флаги — одиночный клик
        self._inline_begin(tree, "batches", row, col, idx, self._BATCH_EDIT_COLS)
        return "break"

    def _editor_values(self, kind):
        c = self.db_manager.conn
        if kind == "unit":
            return TIME_UNITS
        if kind == "currency":
            return ORDER_CURRENCIES
        if kind == "status":
            try:
                return self.db_manager.get_item_statuses()
            except Exception:
                return []
        if kind == "order_status":
            return list(getattr(self.db_manager, "ORDER_STATUSES",
                                ["Запрос цены", "КП получено", "Размещён", "Подтверждён",
                                 "Оплачен", "Отгружен", "Получен", "Списан"]))
        if kind == "manufacturer":
            return [r[0] for r in c.execute("SELECT name FROM manufacturers ORDER BY name")]
        if kind == "supplier":
            return [r[0] for r in c.execute("SELECT name FROM suppliers ORDER BY name")]
        if kind == "project":
            return [r[0] for r in c.execute("SELECT name FROM projects ORDER BY name")]
        if kind == "subproject":
            return [r[0] for r in c.execute(
                "SELECT name FROM subprojects WHERE (project_name=? OR project_name='' "
                "OR project_name IS NULL) ORDER BY name", (self.project_name,))]
        if kind == "kd":
            return [r[0] for r in c.execute(
                "SELECT kd_number FROM kd_directory WHERE (project_name=? OR project_name='' "
                "OR project_name IS NULL) ORDER BY kd_number", (self.project_name,))]
        return []

    def _inline_begin(self, tree, which, row, col, idx, mapping):
        spec = mapping.get(idx)
        if not spec:
            return
        self._inline_cancel()
        try:
            if not tree.exists(row):
                return
            box = tree.bbox(row, col)
        except Exception:
            return
        if not box:
            return
        x, y, w, h = box
        field, kind = spec
        values = list(tree.item(row)['values'])
        old = values[idx] if idx < len(values) else ""

        if kind == "date":
            frame = ttk.Frame(tree)
            frame.place(x=x, y=y, width=max(w, 130), height=h)
            ed = ttk.Entry(frame)
            ed.pack(side=tk.LEFT, fill="both", expand=True)
            ed.insert(0, str(old))
            ed.select_range(0, tk.END)
            ed.focus_set()

            def pick():
                dlg = CalendarDialog(self, ed.get() or None)
                self.wait_window(dlg)
                if dlg.result:
                    ed.delete(0, tk.END)
                    ed.insert(0, dlg.result)
                    self._inline_commit()
            ttk.Button(frame, text="📅", width=2, command=pick).pack(side=tk.LEFT)
            widget = frame
        elif kind in ("unit", "currency", "status", "order_status", "manufacturer",
                      "supplier", "project", "subproject", "kd"):
            ed = ttk.Combobox(tree, values=self._editor_values(kind))
            ed.set(old)
            ed.place(x=x, y=y, width=w, height=h)
            ed.focus_set()
            ed.bind("<<ComboboxSelected>>", lambda e: self._inline_commit())
            widget = ed
        else:
            ed = ttk.Entry(tree)
            ed.insert(0, str(old))
            ed.select_range(0, tk.END)
            ed.place(x=x, y=y, width=w, height=h)
            ed.focus_set()
            widget = ed

        ed.bind("<Return>", lambda e: self._inline_commit())
        ed.bind("<Escape>", lambda e: self._inline_cancel())
        ed.bind("<FocusOut>", lambda e: self.after(120, self._inline_commit_if_alive))
        ed.bind("<Tab>", lambda e: self._inline_tab(tree, which, row, idx, mapping))
        self._inline = {"widget": widget, "entry": ed, "tree": tree, "which": which,
                        "row": row, "idx": idx, "field": field, "kind": kind, "old": old}

    def _inline_commit_if_alive(self):
        if self._inline:
            self._inline_commit()

    def _inline_tab(self, tree, which, row, idx, mapping):
        self._inline_commit()
        nxt = idx + 1
        while nxt <= max(mapping):
            if nxt in mapping:
                try:
                    if tree.exists(row):
                        self._inline_begin(tree, which, row, f"#{nxt + 1}", nxt, mapping)
                except Exception:
                    pass
                break
            nxt += 1
        return "break"

    def _inline_cancel(self):
        info = getattr(self, "_inline", None)
        self._inline = None
        if info:
            try:
                info["widget"].destroy()
            except Exception:
                pass

    def _inline_commit(self):
        info = getattr(self, "_inline", None)
        if not info:
            return "break"
        self._inline = None
        ed, row, idx = info["entry"], info["row"], info["idx"]
        try:
            raw = ed.get()
        except Exception:
            raw = info["old"]
        try:
            info["widget"].destroy()
        except Exception:
            pass

        kind, field = info["kind"], info["field"]
        value = str(raw).strip()
        if kind == "int":
            try:
                value = int(_f(value, 0))
            except Exception:
                messagebox.showwarning("Ошибка", "Нужно целое число!", parent=self)
                return "break"
        elif kind == "float":
            value = max(0.0, _f(value, 0))
        elif kind == "date" and value:
            d = None
            for fmt in ("%d.%m.%Y", "%d.%m.%y"):
                try:
                    d = datetime.strptime(value, fmt)
                    break
                except ValueError:
                    continue
            if d is None:
                messagebox.showwarning("Ошибка", "Дата в формате ДД.ММ.ГГГГ", parent=self)
                return "break"
            value = d.strftime("%d.%m.%Y")

        if str(value) == str(info["old"]):
            return "break"

        try:
            if info["which"] == "items":
                self._commit_item(row, idx, field, value)
            else:
                self._commit_batch(row, field, value)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить:\n{e}", parent=self)
        return "break"

    def _commit_item(self, row, idx, field, value):
        item_id = self.tree_items.item(row)['values'][0]
        if field == "qty_received":
            if hasattr(self.db_manager, "receive_order_item"):
                self.db_manager.receive_order_item(item_id, value,
                                                   datetime.now().strftime("%d.%m.%Y"))
            else:
                self.db_manager.update_order_item(item_id, {field: value})
        else:
            self.db_manager.update_order_item(item_id, {field: value})
        self._log(f"Позиция #{item_id}: {field} = {value}")
        if field in ("quantity", "qty_received"):
            self._reload_items_keep(item_id)
            self._refresh_batches_keep_selection()
        else:
            vals = list(self.tree_items.item(row)['values'])
            vals[idx] = value
            self.tree_items.item(row, values=vals)
            self.current_item_id = item_id
            self.on_select_item()
            self._paint_item_row(row)

    def _commit_batch(self, row, field, value):
        batch_id = self._batch_of(self.tree_batches.item(row)['values'][0])
        db = self.db_manager
        if field == "status":
            db.set_order_status(batch_id, status=value)
        elif field == "receipt_date":
            db.conn.execute("UPDATE orders SET receipt_date=? WHERE order_batch_id=?", (value, batch_id))
            db.conn.commit()
        elif field == "write_off_date":
            db.set_order_write_off_date(batch_id, value)
        elif field == "delivery_number":
            db.set_order_delivery_number(batch_id, value)
        else:
            db.conn.execute(f"UPDATE orders SET {field}=? WHERE order_batch_id=?", (value, batch_id))
            db.conn.commit()
        if field == "project_name":
            self.project_name = value
            self.load_subprojects_for_combo()
            self.load_kd_for_combo()
        self._log(f"Заказ {batch_id}: {field} = {value}")
        self.current_batch_id = batch_id
        self._refresh_batches_keep_selection()

    def _paint_item_row(self, iid):
        try:
            v = self.tree_items.item(iid)['values']
            q, r = _f(v[3]), _f(v[4])
        except (IndexError, TypeError):
            return
        if q > 0 and r >= q:
            self.tree_items.item(iid, tags=('full',))
        elif r > 0:
            self.tree_items.item(iid, tags=('part',))
        else:
            self.tree_items.item(iid, tags=())

    # ==================================================================
    # Календари формы
    # ==================================================================
    def _pick_date(self, entry):
        dlg = CalendarDialog(self, entry.get() or None)
        self.wait_window(dlg)
        if dlg.result:
            entry.delete(0, tk.END)
            entry.insert(0, dlg.result)
            return True
        return False

    def select_order_date(self):
        self._pick_date(self.entry_batch_date)

    def select_payment_date(self):
        self._pick_date(self.entry_batch_payment)

    def select_receipt_date(self):
        if self._pick_date(self.entry_receipt_date) and self.current_batch_id:
            self.save_batch()

    def select_write_off_date(self):
        if self._pick_date(self.entry_write_off_date) and self.current_batch_id:
            self.db_manager.set_order_write_off_date(self.current_batch_id,
                                                     self.entry_write_off_date.get())
            self._refresh_batches_keep_selection()

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

    def _reload_items_keep(self, item_id):
        self.load_items(self.current_batch_id)
        if item_id is None:
            return
        for iid in self.tree_items.get_children():
            if self.tree_items.item(iid)['values'][0] == item_id:
                self.tree_items.selection_set(iid)
                self.tree_items.see(iid)
                self.current_item_id = item_id
                self.on_select_item()
                break

    def _set_topmost(self, value):
        try:
            self.attributes('-topmost', value)
        except tk.TclError:
            pass

    # ==================================================================
    # Статус заказа
    # ==================================================================
    def edit_status(self):
        if self.current_batch_id is None:
            messagebox.showwarning("Внимание", "Выберите заказ!", parent=self)
            return
        try:
            from dialogs.order_status_dialog import OrderStatusDialog
        except ImportError:
            messagebox.showerror("Ошибка", "dialogs/order_status_dialog.py не найден", parent=self)
            return
        batch_id = self.current_batch_id
        dlg = OrderStatusDialog(self, self.db_manager, batch_id)
        self.wait_window(dlg)
        self._refresh_batches_keep_selection()

    # ==================================================================
    # Форма заказа
    # ==================================================================
    def _load_batch_to_form(self, values):
        if not values or len(values) < 17:
            return
        self.entry_batch_date.delete(0, tk.END); self.entry_batch_date.insert(0, values[4])
        self.entry_batch_project.delete(0, tk.END); self.entry_batch_project.insert(0, values[5])
        self.entry_batch_payment.delete(0, tk.END); self.entry_batch_payment.insert(0, values[6])
        self.entry_delivery_days.delete(0, tk.END); self.entry_delivery_days.insert(0, values[7])
        self.combo_delivery_unit.set(values[8])
        self.combo_batch_manufacturer.set(values[1])
        self.combo_batch_subproject.set(values[2])
        self.combo_batch_kd.set(values[3])
        self.entry_invoice_number.delete(0, tk.END); self.entry_invoice_number.insert(0, values[11])
        self.combo_batch_supplier.set(values[12])
        self.entry_delivery_number.delete(0, tk.END); self.entry_delivery_number.insert(0, values[13])
        self.received_var.set(values[14] == "✓")
        self.entry_receipt_date.delete(0, tk.END); self.entry_receipt_date.insert(0, values[15])
        self.entry_write_off_date.delete(0, tk.END); self.entry_write_off_date.insert(0, values[16])
        try:
            self.lbl_batch_status.config(text=values[18] if len(values) > 18 else "")
        except Exception:
            pass

    def calculate_delivery_dates(self):
        self._set_topmost(True)
        try:
            if not self.current_batch_id:
                messagebox.showwarning("Внимание", "Выберите заказ!", parent=self)
                return
            pay = self.entry_batch_payment.get().strip()
            if not pay:
                messagebox.showwarning("Внимание", "Укажите дату оплаты!", parent=self)
                return
            try:
                payment_date = datetime.strptime(pay, "%d.%m.%Y")
            except ValueError:
                messagebox.showerror("Ошибка", "Неверный формат даты оплаты!", parent=self)
                return
            try:
                delivery_days = int(self.entry_delivery_days.get())
            except ValueError:
                messagebox.showerror("Ошибка", "Неверное количество дней доставки!", parent=self)
                return
            unit = self.combo_delivery_unit.get()
            if not unit:
                messagebox.showwarning("Внимание", "Выберите единицу доставки!", parent=self)
                return

            def to_days(n, u):
                if u == "Недели":
                    return n * 7
                if u == "Месяцы":
                    return (add_months(payment_date, n) - payment_date).days
                if u == "Рабочие дни":
                    return (add_working_days_with_holidays(payment_date, n,
                                                           self.russian_holidays) - payment_date).days
                return n

            total = to_days(delivery_days, unit)
            terms = [to_days(i['delivery_term'] or 0, i['delivery_unit'] or "Недели")
                     for i in self._items_rows(self.current_batch_id)
                     if (i['delivery_term'] or 0) > 0]
            min_supply = min(terms) if terms else 0
            max_supply = max(terms) if terms else 0
            min_date = (payment_date + timedelta(days=min_supply + total)).strftime("%d.%m.%Y")
            max_date = (payment_date + timedelta(days=max_supply + total)).strftime("%d.%m.%Y")

            self.db_manager.update_order_batch(
                self.current_batch_id, self.entry_batch_date.get(), self.entry_batch_project.get(),
                pay, delivery_days, unit, min_date, max_date)
            self._save_header_fields()
            self._refresh_batches_keep_selection()
            messagebox.showinfo("Успех", f"Даты рассчитаны:\nMin: {min_date}\nMax: {max_date}",
                                parent=self)
        finally:
            self._set_topmost(False)
            self.lift()
            self.focus_force()

    def _save_header_fields(self):
        c = self.db_manager.conn.cursor()
        c.execute('''UPDATE orders SET manufacturer=?, subproject=?, kd=?, supplier=?, invoice_number=?
                     WHERE order_batch_id=?''',
                  (self.combo_batch_manufacturer.get().strip(),
                   self.combo_batch_subproject.get().strip(),
                   self.combo_batch_kd.get().strip(),
                   self.combo_batch_supplier.get().strip(),
                   self.entry_invoice_number.get().strip(),
                   self.current_batch_id))
        self.db_manager.conn.commit()

    # ==================================================================
    # Верхняя таблица
    # ==================================================================
    def load_batches(self):
        for item in self.tree_batches.get_children():
            self.tree_batches.delete(item)
        self._display2batch = {}
        today = datetime.now().date()
        f_man = self.combo_filter_manufacturer.get().strip()
        f_pay = self.combo_filter_payment.get()
        f_rec = self.combo_filter_received.get()

        if self.sort_column == "order_date":
            order_clause = ("ORDER BY CASE WHEN MAX(order_date)='' OR MAX(order_date) IS NULL "
                            "THEN 1 ELSE 0 END, substr(MAX(order_date),7,4)||"
                            "substr(MAX(order_date),4,2)||substr(MAX(order_date),1,2) "
                            + self.sort_order)
        elif self.sort_column == "batch_id":
            order_clause = f"ORDER BY order_batch_id {self.sort_order}"
        else:
            order_clause = f"ORDER BY MAX({self.sort_column}) {self.sort_order}"

        base_query = '''SELECT order_batch_id, MAX(order_date) order_date,
            MAX(project_name) project_name, MAX(payment_date) payment_date,
            MAX(manufacturer) manufacturer, MAX(delivery_days) delivery_days,
            MAX(delivery_unit_order) delivery_unit_order,
            MAX(min_delivery_date) min_delivery_date, MAX(max_delivery_date) max_delivery_date,
            (SELECT subproject FROM orders WHERE order_batch_id=o.order_batch_id LIMIT 1) subproject,
            (SELECT kd FROM orders WHERE order_batch_id=o.order_batch_id LIMIT 1) kd,
            (SELECT invoice_number FROM orders WHERE order_batch_id=o.order_batch_id LIMIT 1) invoice_number,
            (SELECT supplier FROM orders WHERE order_batch_id=o.order_batch_id LIMIT 1) supplier,
            (SELECT delivery_number FROM orders WHERE order_batch_id=o.order_batch_id LIMIT 1) delivery_number,
            (SELECT received FROM orders WHERE order_batch_id=o.order_batch_id LIMIT 1) received,
            (SELECT receipt_date FROM orders WHERE order_batch_id=o.order_batch_id LIMIT 1) receipt_date,
            (SELECT write_off_date FROM orders WHERE order_batch_id=o.order_batch_id LIMIT 1) write_off_date,
            (SELECT price_request FROM orders WHERE order_batch_id=o.order_batch_id LIMIT 1) price_request,
            (SELECT price_request_num FROM orders WHERE order_batch_id=o.order_batch_id LIMIT 1) price_request_num,
            (SELECT status FROM orders WHERE order_batch_id=o.order_batch_id LIMIT 1) status
            FROM orders o'''

        where, params = "", []
        if f_man:
            where += " WHERE manufacturer = ?"
            params.append(f_man)
        if f_pay == "Есть дата":
            where += (" AND" if where else " WHERE") + " payment_date IS NOT NULL AND payment_date != ''"
        elif f_pay == "Нет даты":
            where += (" AND" if where else " WHERE") + " (payment_date IS NULL OR payment_date = '')"
        if f_rec == "Получено":
            where += (" AND" if where else " WHERE") + " received = 1"
        elif f_rec == "Не получено":
            where += (" AND" if where else " WHERE") + " (received = 0 OR received IS NULL)"

        c = self.db_manager.conn.cursor()
        c.execute(base_query + where + f" GROUP BY order_batch_id {order_clause}", params)
        for r in c.fetchall():
            received_mark = "✓" if r['received'] else ""
            pr, prn = r['price_request'] or 0, r['price_request_num'] or 0
            disp = f"Z{prn}" if (pr and prn) else str(r['order_batch_id'])
            self._display2batch[disp] = r['order_batch_id']
            status = r['status'] or ""
            values = (disp, r['manufacturer'] or "", r['subproject'] or "", r['kd'] or "",
                      r['order_date'] or "", r['project_name'] or "", r['payment_date'] or "",
                      r['delivery_days'] or 0, r['delivery_unit_order'] or "",
                      r['min_delivery_date'] or "", r['max_delivery_date'] or "",
                      r['invoice_number'] or "", r['supplier'] or "", r['delivery_number'] or "",
                      received_mark, r['receipt_date'] or "", r['write_off_date'] or "",
                      "✓" if pr else "", status)
            iid = self.tree_batches.insert("", tk.END, values=values)
            tags = []
            if status in ("Получен", "Списан"):
                tags.append('st_done')
            elif status in ("Подтверждён", "Оплачен", "Отгружен"):
                tags.append('st_active')
            if r['min_delivery_date'] and r['max_delivery_date']:
                try:
                    mn = datetime.strptime(r['min_delivery_date'], "%d.%m.%Y").date()
                    mx = datetime.strptime(r['max_delivery_date'], "%d.%m.%Y").date()
                    if today < mn and (mn - today).days <= 7:
                        tags.append('warning')
                    elif today > mx and not received_mark:
                        tags.append('overdue')
                except ValueError:
                    pass
            if tags:
                self.tree_batches.item(iid, tags=tuple(tags))

        self.tree_batches.tag_configure('warning', background='lightgreen')
        self.tree_batches.tag_configure('overdue', background='lightcoral')
        self.tree_batches.tag_configure('st_done', background='#d9ead3')
        self.tree_batches.tag_configure('st_active', background='#d0e0f0')
        self.current_batch_id = None
        self.current_item_id = None
        self.clear_batch_form()
        self.clear_items()

    def on_batch_click(self, event):
        """Одиночный клик по флагам: #15 = Получено, #18 = Запрос цены."""
        tree = self.tree_batches
        try:
            if tree.identify_region(event.x, event.y) != "cell":
                return
            col = tree.identify_column(event.x)
            row_id = tree.identify_row(event.y)
        except Exception:
            return
        if col not in ('#15', '#18') or not row_id:
            return
        values = tree.item(row_id)['values']
        batch_id = self._batch_of(values[0])
        if col == '#15':
            new = 0 if values[14] == "✓" else 1
            date = datetime.now().strftime("%d.%m.%Y") if new else ""
            self.db_manager.set_order_received(batch_id, new, date)
        else:
            new = 0 if values[17] == "✓" else 1
            self.db_manager.set_order_price_request(batch_id, new)
            self._log(f"Переключено price_request={new} у заказа {values[0]}")
        self.current_batch_id = batch_id
        self._refresh_batches_keep_selection()

    def clear_batch_form(self):
        for e in (self.entry_batch_date, self.entry_batch_project, self.entry_batch_payment,
                  self.entry_delivery_days, self.entry_invoice_number, self.entry_delivery_number,
                  self.entry_receipt_date, self.entry_write_off_date):
            e.delete(0, tk.END)
        for c in (self.combo_delivery_unit, self.combo_batch_manufacturer,
                  self.combo_batch_subproject, self.combo_batch_kd, self.combo_batch_supplier):
            c.set('')
        self.received_var.set(False)
        try:
            self.lbl_batch_status.config(text="")
        except Exception:
            pass

    def clear_items(self):
        for item in self.tree_items.get_children():
            self.tree_items.delete(item)
        self.clear_item_form()

    def clear_item_form(self):
        for e in (self.entry_item_article, self.entry_item_name, self.entry_item_quantity,
                  self.entry_item_qty_received, self.entry_item_delivery_term,
                  self.entry_item_price, self.entry_item_note):
            e.delete(0, tk.END)
        self.combo_item_delivery_unit.set('')
        self.combo_item_currency.set('')
        try:
            self.combo_item_status.set('')
            self.lbl_item_rest.config(text="0")
            self.lbl_status_hint.config(text="")
        except Exception:
            pass

    def _items_rows(self, batch_id):
        """Позиции заказа; qty_received добираем запросом, если БД-метод его не отдаёт."""
        rows = self.db_manager.get_order_items(batch_id)
        if rows and 'qty_received' not in rows[0]:
            q = {r['id']: r['q'] for r in self.db_manager.conn.execute(
                "SELECT id, IFNULL(qty_received,0) q FROM orders WHERE order_batch_id=?", (batch_id,))}
            for r in rows:
                r['qty_received'] = q.get(r['id'], 0)
        return rows

    def load_items(self, batch_id):
        self._refresh_item_statuses()
        for item in self.tree_items.get_children():
            self.tree_items.delete(item)
        self.current_item_id = None
        self.clear_item_form()
        try:
            rows = self._items_rows(batch_id)
        except Exception:
            traceback.print_exc()
            return
        for r in rows:
            q = _f(r.get('quantity'), 0)
            rec = _f(r.get('qty_received'), 0)
            rest = q - rec
            iid = self.tree_items.insert("", tk.END, values=(
                r['id'], r['article'] or "", r['name'] or "", r['quantity'] or 0,
                rec, f"{rest:g}", r['delivery_term'] or "", r['delivery_unit'] or "",
                r['price'] or "", r['currency'] or "", r['note'] or "",
                r.get('item_status', '')))
            self._paint_item_row(iid)
        if not rows:
            print(f"[order_dialog] Заказ {batch_id}: позиций в БД не найдено")

    def on_select_batch(self, event=None):
        sel = self.tree_batches.selection()
        if not sel:
            return
        try:
            values = self.tree_batches.item(sel[0])['values']
            if not values:
                return
            batch_id = self._batch_of(values[0])
            try:
                batch_id = int(batch_id)
            except (TypeError, ValueError):
                pass
            if batch_id == self.current_batch_id and self.tree_items.get_children():
                self._load_batch_to_form(values)
                return
            self.current_batch_id = batch_id
            self._load_batch_to_form(values)
            proj = values[5] if len(values) > 5 else ""
            if proj and proj != self.project_name:
                self.project_name = proj
                self.load_subprojects_for_combo()
                self.load_kd_for_combo()
            self.load_items(batch_id)
        except Exception:
            traceback.print_exc()
            self._log("Ошибка выбора заказа:\n" + traceback.format_exc(limit=4))

    def on_received_change(self):
        if not self.current_batch_id:
            return
        new = 1 if self.received_var.get() else 0
        date = self.entry_receipt_date.get()
        if new and not date:
            date = datetime.now().strftime("%d.%m.%Y")
            self.entry_receipt_date.insert(0, date)
        self.db_manager.set_order_received(self.current_batch_id, new, date)
        self._refresh_batches_keep_selection()

    # ==================================================================
    # Позиции
    # ==================================================================
    def on_select_item(self, event=None):
        sel = self.tree_items.selection()
        if not sel:
            return
        v = self.tree_items.item(sel[-1])['values']
        self.current_item_id = v[0]
        self.entry_item_article.delete(0, tk.END); self.entry_item_article.insert(0, v[1])
        self.entry_item_name.delete(0, tk.END); self.entry_item_name.insert(0, v[2])
        self.entry_item_quantity.delete(0, tk.END); self.entry_item_quantity.insert(0, v[3])
        self.entry_item_qty_received.delete(0, tk.END); self.entry_item_qty_received.insert(0, v[4])
        try:
            self.lbl_item_rest.config(text=str(v[5]))
        except Exception:
            pass
        self.entry_item_delivery_term.delete(0, tk.END); self.entry_item_delivery_term.insert(0, v[6])
        self.combo_item_delivery_unit.set(v[7])
        self.entry_item_price.delete(0, tk.END); self.entry_item_price.insert(0, v[8])
        self.combo_item_currency.set(v[9])
        self.entry_item_note.delete(0, tk.END); self.entry_item_note.insert(0, v[10])
        try:
            self.combo_item_status.set(v[11] if len(v) > 11 else "")
            self.lbl_status_hint.config(text=f"выбрано позиций: {len(sel)}" if len(sel) > 1 else "")
        except Exception:
            pass

    def edit_item(self):
        sel = self.tree_items.selection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите позицию!", parent=self)
            return
        v = self.tree_items.item(sel[0])['values']
        item_id = v[0]
        data = {'id': item_id, 'article': str(v[1] or ''), 'name': str(v[2] or ''),
                'quantity': int(_f(v[3])), 'qty_received': _f(v[4]),
                'delivery_term': int(_f(v[6])), 'delivery_unit': str(v[7] or ''),
                'price': str(v[8] or ''), 'currency': str(v[9] or ''),
                'note': str(v[10] or ''), 'item_status': str(v[11]) if len(v) > 11 else ''}
        dlg = OrderItemEditDialog(self, data)
        self.wait_window(dlg)
        if dlg.result is not None:
            try:
                dlg.result.setdefault('item_status', data['item_status'])
                self.db_manager.update_order_item(item_id, dlg.result)
                if 'qty_received' in dlg.result and hasattr(self.db_manager, "receive_order_item"):
                    self.db_manager.receive_order_item(item_id, _f(dlg.result['qty_received']),
                                                       datetime.now().strftime("%d.%m.%Y"))
                self._reload_items_keep(item_id)
                self._log(f"Позиция #{item_id} отредактирована")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить изменения:\n{e}", parent=self)
                traceback.print_exc()

    def save_batch(self):
        if self.current_batch_id is None:
            messagebox.showwarning("Внимание", "Выберите заказ!", parent=self)
            return
        min_date = max_date = ""
        for item in self.tree_batches.get_children():
            v = self.tree_batches.item(item)['values']
            if self._batch_of(v[0]) == self.current_batch_id:
                min_date, max_date = v[9], v[10]
                break
        self.db_manager.update_order_batch(
            self.current_batch_id, self.entry_batch_date.get(), self.entry_batch_project.get(),
            self.entry_batch_payment.get(), int(_f(self.entry_delivery_days.get())),
            self.combo_delivery_unit.get(), min_date, max_date)
        self._save_header_fields()
        self.db_manager.set_order_delivery_number(self.current_batch_id,
                                                  self.entry_delivery_number.get().strip())
        self.db_manager.set_order_received(self.current_batch_id,
                                           1 if self.received_var.get() else 0,
                                           self.entry_receipt_date.get())
        self.db_manager.set_order_write_off_date(self.current_batch_id,
                                                 self.entry_write_off_date.get().strip())
        self._refresh_batches_keep_selection()

    def delete_batch(self):
        if self.current_batch_id is None:
            messagebox.showwarning("Внимание", "Выберите заказ!", parent=self)
            return
        if messagebox.askyesno("Подтверждение", "Удалить заказ и все его позиции?", parent=self):
            self.db_manager.delete_order_batch(self.current_batch_id)
            self.load_batches()

    def save_item(self):
        if self.current_item_id is None:
            messagebox.showwarning("Внимание", "Выберите позицию!", parent=self)
            return
        item_id = self.current_item_id
        qty = int(_f(self.entry_item_quantity.get()))
        rec = _f(self.entry_item_qty_received.get())
        self.db_manager.update_order_item(item_id, {
            'article': self.entry_item_article.get(),
            'name': self.entry_item_name.get(),
            'quantity': qty,
            'delivery_term': int(_f(self.entry_item_delivery_term.get())),
            'delivery_unit': self.combo_item_delivery_unit.get(),
            'price': self.entry_item_price.get(),
            'currency': self.combo_item_currency.get(),
            'note': self.entry_item_note.get(),
            'item_status': self.combo_item_status.get(),
        })
        if hasattr(self.db_manager, "receive_order_item"):
            self.db_manager.receive_order_item(item_id, rec, datetime.now().strftime("%d.%m.%Y"))
        else:
            self.db_manager.update_order_item(item_id, {'qty_received': rec})
        self._reload_items_keep(item_id)
        self._refresh_batches_keep_selection()

    def delete_item(self):
        if self.current_item_id is None:
            messagebox.showwarning("Внимание", "Выберите позицию!", parent=self)
            return
        if messagebox.askyesno("Подтверждение", "Удалить позицию?", parent=self):
            self.db_manager.delete_order_item(self.current_item_id)
            if not self.db_manager.get_order_items(self.current_batch_id):
                self.db_manager.delete_order_batch(self.current_batch_id)
                self.load_batches()
            else:
                self.load_items(self.current_batch_id)

    # ==================================================================
    # Импорт / экспорт
    # ==================================================================
    def import_from_file(self):
        if self.current_batch_id is None:
            messagebox.showwarning("Внимание", "Сначала выберите заказ!", parent=self)
            return
        if parse_file_to_rows_with_text is None or FileImportMatchDialog is None:
            messagebox.showerror("Ошибка", "Модули импорта КП не найдены", parent=self)
            return
        path = filedialog.askopenfilename(
            title="Выберите файл коммерческого предложения",
            filetypes=[("Excel и PDF", "*.xlsx *.xls *.pdf"), ("Excel", "*.xlsx *.xls"),
                       ("PDF", "*.pdf"), ("All files", "*.*")], parent=self)
        if not path:
            return
        try:
            rows, text = parse_file_to_rows_with_text(path)
        except Exception as e:
            messagebox.showerror("Ошибка парсинга", f"Не удалось прочитать файл:\n{e}", parent=self)
            return
        if not rows:
            messagebox.showwarning("Пустой файл", "Файл не содержит данных", parent=self)
            return
        items = self._items_rows(self.current_batch_id)
        if not items:
            messagebox.showwarning("Пустой заказ", "В заказе нет позиций для сопоставления", parent=self)
            return
        self.wait_window(FileImportMatchDialog(self, items, rows, self.db_manager, text))
        self.load_items(self.current_batch_id)

    def open_export_dialog(self):
        self.wait_window(OrderExportDialog(self, self.db_manager))

    @staticmethod
    def _sanitize_filename(s):
        bad = '/:*?"<>|\r\n\t'
        res = "".join('_' if ch in bad else ch for ch in str(s)).strip()
        return res[:80] if res else "unknown"

    def export_order_to_excel(self):
        if not HAS_OPENPYXL:
            messagebox.showwarning("Нет библиотеки", "Установите: pip install openpyxl", parent=self)
            return
        if self.current_batch_id is None:
            messagebox.showwarning("Внимание", "Выделите заказ!", parent=self)
            return
        header = None
        for b in self.db_manager.get_order_batches():
            if b['order_batch_id'] == self.current_batch_id:
                header = b
                break
        if header is None:
            messagebox.showwarning("Внимание", "Заказ не найден!", parent=self)
            return
        items = self._items_rows(self.current_batch_id)
        if not items:
            messagebox.showwarning("Внимание", "В заказе нет позиций!", parent=self)
            return
        date_str = header['order_date'] or ""
        project_str = header['project_name'] or ""
        mans, subs = [], []
        for p in items:
            m = (p['manufacturer'] or "").strip()
            s = (p['subproject'] or "").strip()
            if m and m not in mans:
                mans.append(m)
            if s and s not in subs:
                subs.append(s)
        pr = header['price_request'] if 'price_request' in header.keys() else 0
        prn = header['price_request_num'] if 'price_request_num' in header.keys() else 0
        label = f"Z{prn}" if (pr and prn) else str(header['order_batch_id'])
        filename = (f"order {label} {date_str or 'nodate'} "
                    f"{self._sanitize_filename('_'.join(mans) or 'unknown')}.xlsx")
        directory = filedialog.askdirectory(title="Выберите папку", parent=self)
        if not directory:
            return
        full_path = os.path.join(directory, filename)
        if os.path.exists(full_path) and not messagebox.askyesno(
                "Файл существует", f"Перезаписать?\n{full_path}", parent=self):
            return
        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Order"
            bold = Font(bold=True)
            ws['A1'] = "Order"; ws['A1'].font = bold
            ws['A2'] = date_str
            ws['B2'] = ", ".join(mans)
            ws['C2'] = project_str
            ws['D2'] = ", ".join(subs)
            for cell in (ws['A2'], ws['B2'], ws['C2'], ws['D2']):
                cell.font = bold
            for i, h in enumerate(["Manufacturer", "Article", "Name (EN)", "Quantity"], start=1):
                ws.cell(row=4, column=i, value=h).font = bold
            row = 5
            for p in items:
                ws.cell(row=row, column=1, value=p['manufacturer'] or "")
                ws.cell(row=row, column=2, value=p['article'] or "")
                ws.cell(row=row, column=3, value=p['name_eng'] or "")
                ws.cell(row=row, column=4, value=p['quantity'] if p['quantity'] is not None else "")
                row += 1
            for col in range(1, 5):
                width = max((len(str(ws.cell(row=r, column=col).value or ""))
                             for r in range(1, ws.max_row + 1)), default=10)
                ws.column_dimensions[get_column_letter(col)].width = min(max(width + 2, 10), 60)
            wb.save(full_path)
        except PermissionError:
            self._log(f"Ошибка экспорта Excel (доступ): {full_path}")
            messagebox.showerror("Ошибка доступа",
                                 f"Файл открыт в другой программе или нет прав:\n{full_path}",
                                 parent=self)
            return
        except Exception as e:
            print(traceback.format_exc())
            self._log(f"Ошибка экспорта Excel: {e}")
            messagebox.showerror("Ошибка", f"Не удалось создать файл.\nПричина: {e}", parent=self)
            return
        messagebox.showinfo("Успех", f"Файл сохранён:\n{full_path}", parent=self)