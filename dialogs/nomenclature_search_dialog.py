import tkinter as tk
from tkinter import ttk, messagebox
from config import ORDER_CURRENCIES
from utils import get_exchange_rates, parse_number
from database import DatabaseManager


class NomenclatureSearchDialog(tk.Toplevel):
    def __init__(self, parent, db_manager):
        super().__init__(parent)
        self.title("Поиск по номенклатуре")
        self.geometry("1400x800")
        self.resizable(True, True)
        self.db_manager = db_manager
        self.selected_article = ""
        self.selected_name = ""

        search_frame = ttk.LabelFrame(self, text="Поиск по номенклатуре", padding=10)
        search_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        ttk.Label(search_frame, text="Артикул:").grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.entry_article = ttk.Entry(search_frame, width=30)
        self.entry_article.grid(row=0, column=1, sticky="w", padx=(0, 20))
        self.entry_article.bind('<KeyRelease>', lambda e: self.on_search())

        ttk.Label(search_frame, text="Наименование:").grid(row=0, column=2, sticky="w", padx=(0, 5))
        self.entry_name = ttk.Entry(search_frame, width=40)
        self.entry_name.grid(row=0, column=3, sticky="w", padx=(0, 20))
        self.entry_name.bind('<KeyRelease>', lambda e: self.on_search())

        ttk.Label(search_frame, text="Производитель:").grid(row=0, column=4, sticky="w", padx=(0, 5))
        self.combo_manufacturer = ttk.Combobox(search_frame, width=20, state="readonly")
        self.combo_manufacturer.grid(row=0, column=5, sticky="w")
        self.combo_manufacturer.bind("<<ComboboxSelected>>", lambda e: self.on_search())

        nom_frame = ttk.LabelFrame(self, text="Номенклатура", padding=5)
        nom_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        cols_nom = ("article", "name_rus", "manufacturer")
        self.tree_nomenclature = ttk.Treeview(nom_frame, columns=cols_nom, show="headings", height=8)
        self.tree_nomenclature.heading("article", text="Артикул")
        self.tree_nomenclature.heading("name_rus", text="Наименование")
        self.tree_nomenclature.heading("manufacturer", text="Производитель")
        self.tree_nomenclature.column("article", width=150, anchor="w")
        self.tree_nomenclature.column("name_rus", width=400, anchor="w")
        self.tree_nomenclature.column("manufacturer", width=150, anchor="w")
        sb_nom = ttk.Scrollbar(nom_frame, orient=tk.VERTICAL, command=self.tree_nomenclature.yview)
        self.tree_nomenclature.configure(yscroll=sb_nom.set)
        self.tree_nomenclature.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_nom.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_nomenclature.bind("<<TreeviewSelect>>", self.on_nomenclature_select)

        orders_frame = ttk.LabelFrame(self, text="Заказы", padding=5)
        orders_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        cols_orders = ("order_number", "order_date", "article", "name", "quantity",
                       "delivery_term", "delivery_unit", "price", "currency", "price_rub")
        self.tree_orders = ttk.Treeview(orders_frame, columns=cols_orders, show="headings", height=10)
        for col, title, width, anc in [
            ("order_number", "№ заказа", 80, "center"),
            ("order_date", "Дата заказа", 100, "center"),
            ("article", "Артикул", 150, "w"),
            ("name", "Наименование", 250, "w"),
            ("quantity", "Кол-во", 60, "center"),
            ("delivery_term", "Срок", 60, "center"),
            ("delivery_unit", "Единица", 80, "w"),
            ("price", "Цена", 80, "e"),
            ("currency", "Валюта", 60, "center"),
            ("price_rub", "Цена (₽)", 80, "e"),
        ]:
            self.tree_orders.heading(col, text=title)
            self.tree_orders.column(col, width=width, anchor=anc)
        sb_orders = ttk.Scrollbar(orders_frame, orient=tk.VERTICAL, command=self.tree_orders.yview)
        self.tree_orders.configure(yscroll=sb_orders.set)
        self.tree_orders.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_orders.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_orders.bind("<Double-1>", self.on_order_double_click)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btn_frame, text="Обновить курсы", command=self.refresh_rates).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Закрыть", command=self.destroy).pack(side=tk.RIGHT, padx=5)

        self.exchange_rates = get_exchange_rates()
        self.load_manufacturers_filter()
        self.on_search()
        self.grab_set()

    def load_manufacturers_filter(self):
        c = self.db_manager.conn.cursor()
        c.execute("SELECT DISTINCT manufacturer FROM nomenclature WHERE manufacturer IS NOT NULL AND manufacturer != '' ORDER BY manufacturer")
        manufacturers = [row[0] for row in c.fetchall()]
        self.combo_manufacturer['values'] = [''] + manufacturers

    def on_search(self):
        article_filter = self.entry_article.get().strip().upper()
        name_filter = self.entry_name.get().strip().upper()
        manufacturer_filter = self.combo_manufacturer.get().strip()
        for item in self.tree_nomenclature.get_children():
            self.tree_nomenclature.delete(item)
        c = self.db_manager.conn.cursor()
        query = "SELECT article, name_rus, manufacturer FROM nomenclature WHERE 1=1"
        params = []
        if article_filter:
            query += " AND UPPER(article) LIKE ?"
            params.append(f"%{article_filter}%")
        if name_filter:
            query += " AND UPPER(name_rus) LIKE ?"
            params.append(f"%{name_filter}%")
        if manufacturer_filter:
            query += " AND manufacturer = ?"
            params.append(manufacturer_filter)
        query += " ORDER BY article"
        c.execute(query, params)
        for row in c.fetchall():
            self.tree_nomenclature.insert("", tk.END, values=(
                row[0] or "", row[1] or "", row[2] or ""
            ))

    def on_nomenclature_select(self, event):
        selected = self.tree_nomenclature.selection()
        if not selected:
            return
        values = self.tree_nomenclature.item(selected[0])['values']
        self.selected_article = values[0]
        self.selected_name = values[1]
        self.load_orders()

    def on_order_double_click(self, event):
        selected = self.tree_orders.selection()
        if not selected:
            return
        values = self.tree_orders.item(selected[0])['values']
        batch_id = values[0]
        from dialogs.order_dialog import OrderDialog
        dialog = OrderDialog(self, self.db_manager, batch_id=batch_id)
        self.wait_window(dialog)

    def load_orders(self):
        for item in self.tree_orders.get_children():
            self.tree_orders.delete(item)
        if not self.selected_article:
            return
        c = self.db_manager.conn.cursor()
        c.execute('''SELECT DISTINCT o.order_batch_id, o.order_date, o.article, o.name,
            o.quantity, o.delivery_term, o.delivery_unit, o.price, o.currency
            FROM orders o
            WHERE o.article = ?
            ORDER BY o.order_date DESC''', (self.selected_article,))
        orders = c.fetchall()
        for order in orders:
            price_rub = ""
            if order['currency'] and self.exchange_rates:
                currency = order['currency'].upper()
                if currency in self.exchange_rates:
                    try:
                        price = parse_number(order['price'])
                        if price is not None:
                            price_rub = f"{price * self.exchange_rates[currency]:.2f}"
                        else:
                            price_rub = "Ошибка парсинга"
                    except Exception as e:
                        price_rub = f"Ошибка: {e}"
                else:
                    price_rub = f"Нет курса {currency}"
            elif not self.exchange_rates:
                price_rub = "Курсы не загружены"
            self.tree_orders.insert("", tk.END, values=(
                order['order_batch_id'] or "",
                order['order_date'] or "",
                order['article'] or "",
                order['name'] or "",
                order['quantity'] or "",
                order['delivery_term'] or "",
                order['delivery_unit'] or "",
                order['price'] or "",
                order['currency'] or "",
                price_rub
            ))

    def refresh_rates(self):
        self.exchange_rates = get_exchange_rates()
        if self.exchange_rates:
            messagebox.showinfo("Успех", "Курсы валют обновлены")
            self.load_orders()
        else:
            messagebox.showerror("Ошибка", "Не удалось получить курсы валют")