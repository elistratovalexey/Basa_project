import sqlite3
import os
import glob
from datetime import datetime


def _date_sort_key(date_str):
    """Ключ сортировки для дат ДД.ММ.ГГГГ (пустые/неверные — в конец)"""
    try:
        return (0, datetime.strptime(str(date_str).strip(), "%d.%m.%Y"))
    except (ValueError, TypeError):
        return (1, datetime.max)


class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        db_dir = os.path.dirname(os.path.abspath(db_path))
        if db_dir and not os.path.isdir(db_dir):
            raise FileNotFoundError(f"Папка базы данных не найдена: {db_dir}")

        # timeout: база лежит на сетевом диске и может быть открыта
        # несколькими пользователями — ждём снятия блокировки, а не падаем
        # сразу с "database is locked"
        self.conn = sqlite3.connect(db_path, timeout=15)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout = 15000")
        self.create_tables()
        self._ensure_order_columns()
        self._ensure_order_received_columns()
        self._ensure_order_delivery_number_column()
        self._ensure_order_write_off_column()
        self._ensure_price_request_columns()
        self._ensure_delivery_addresses_table()
        self._ensure_purchase_payments_ext_columns()
        self._ensure_purchase_spec_items_table()
        self._ensure_purchase_spec_delivery_address()
        self._ensure_suppliers_columns()
        self._ensure_indexes()

    def _ensure_indexes(self):
        """Индексы для ускорения выборок по проекту / заказу / спецификации"""
        c = self.conn.cursor()
        for sql in (
            "CREATE INDEX IF NOT EXISTS idx_payments_project ON payments(project_id, number)",
            "CREATE INDEX IF NOT EXISTS idx_specifications_project ON specifications(project_id, number)",
            "CREATE INDEX IF NOT EXISTS idx_purchases_project ON purchases(project_id, number)",
            "CREATE INDEX IF NOT EXISTS idx_orders_batch ON orders(order_batch_id)",
            "CREATE INDEX IF NOT EXISTS idx_nomenclature_article ON nomenclature(article)",
            "CREATE INDEX IF NOT EXISTS idx_pspec_project ON purchase_specifications(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_pspec_items_spec ON purchase_spec_items(spec_id)",
            "CREATE INDEX IF NOT EXISTS idx_ppayments_spec ON purchase_payments(spec_id)",
        ):
            try:
                c.execute(sql)
            except sqlite3.OperationalError as e:
                print(f"Индекс не создан: {e}")
        self.conn.commit()

    # === Резервное копирование ===
    def backup(self, backup_dir, keep=15, prefix="projects"):
        """Делает онлайн-копию БД (sqlite backup API) и удаляет старые копии.
        Возвращает путь к копии или None."""
        try:
            os.makedirs(backup_dir, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target = os.path.join(backup_dir, f"{prefix}_{stamp}.db")
            n = 1
            while os.path.exists(target):
                target = os.path.join(backup_dir, f"{prefix}_{stamp}_{n}.db")
                n += 1
            dst = sqlite3.connect(target)
            try:
                self.conn.backup(dst)
            finally:
                dst.close()
            copies = sorted(glob.glob(os.path.join(backup_dir, f"{prefix}_*.db")))
            for old in copies[:-keep] if keep > 0 else []:
                try:
                    os.remove(old)
                except OSError:
                    pass
            return target
        except Exception as e:
            print(f"Резервная копия не создана: {e}")
            return None

    # === Миграции схемы ===
    def _ensure_order_columns(self):
        """Добавляет недостающие колонки в таблицу orders"""
        c = self.conn.cursor()
        c.execute("PRAGMA table_info(orders)")
        columns = [row[1] for row in c.fetchall()]
        if 'delivery_term' not in columns:
            c.execute("ALTER TABLE orders ADD COLUMN delivery_term INTEGER DEFAULT 0")
        if 'delivery_unit' not in columns:
            c.execute("ALTER TABLE orders ADD COLUMN delivery_unit TEXT DEFAULT ''")
        if 'price' not in columns:
            c.execute("ALTER TABLE orders ADD COLUMN price TEXT DEFAULT ''")
        if 'currency' not in columns:
            c.execute("ALTER TABLE orders ADD COLUMN currency TEXT DEFAULT ''")
        self.conn.commit()

    def _ensure_order_received_columns(self):
        """Добавляет колонки received и receipt_date в таблицу orders"""
        c = self.conn.cursor()
        c.execute("PRAGMA table_info(orders)")
        columns = [row[1] for row in c.fetchall()]
        if 'received' not in columns:
            c.execute("ALTER TABLE orders ADD COLUMN received INTEGER DEFAULT 0")
        if 'receipt_date' not in columns:
            c.execute("ALTER TABLE orders ADD COLUMN receipt_date TEXT DEFAULT ''")
        self.conn.commit()

    def _ensure_order_delivery_number_column(self):
        """Добавляет колонку delivery_number в таблицу orders"""
        c = self.conn.cursor()
        c.execute("PRAGMA table_info(orders)")
        columns = [row[1] for row in c.fetchall()]
        if 'delivery_number' not in columns:
            c.execute("ALTER TABLE orders ADD COLUMN delivery_number TEXT DEFAULT ''")
        self.conn.commit()

    def _ensure_order_write_off_column(self):
        """Добавляет колонку write_off_date (дата списания) в таблицу orders"""
        c = self.conn.cursor()
        c.execute("PRAGMA table_info(orders)")
        columns = [row[1] for row in c.fetchall()]
        if 'write_off_date' not in columns:
            c.execute("ALTER TABLE orders ADD COLUMN write_off_date TEXT DEFAULT ''")
            self.conn.commit()
            print("Миграция: добавлена колонка orders.write_off_date")

    def _ensure_price_request_columns(self):
        """Колонки флага 'Запрос цены' в purchases и orders + Z-нумерация."""
        c = self.conn.cursor()
        c.execute("PRAGMA table_info(purchases)")
        cols = [row[1] for row in c.fetchall()]
        if 'price_request' not in cols:
            c.execute("ALTER TABLE purchases ADD COLUMN price_request INTEGER DEFAULT 0")
            print("Миграция: добавлена колонка purchases.price_request")
        c.execute("PRAGMA table_info(orders)")
        cols = [row[1] for row in c.fetchall()]
        if 'price_request' not in cols:
            c.execute("ALTER TABLE orders ADD COLUMN price_request INTEGER DEFAULT 0")
        if 'price_request_num' not in cols:
            c.execute("ALTER TABLE orders ADD COLUMN price_request_num INTEGER DEFAULT 0")
            print("Миграция: добавлены колонки orders.price_request / price_request_num")
        self.conn.commit()

    def _ensure_delivery_addresses_table(self):
        """Создаёт таблицу адресов доставки, если её нет"""
        c = self.conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS delivery_addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            address TEXT NOT NULL,
            contact TEXT,
            phone TEXT,
            note TEXT
        )''')
        self.conn.commit()

    def _ensure_purchase_payments_ext_columns(self):
        """Добавляет расширенные поля в таблицу purchase_payments"""
        c = self.conn.cursor()
        c.execute("PRAGMA table_info(purchase_payments)")
        columns = [row[1] for row in c.fetchall()]
        ext_cols = {
            'invoice_number': 'TEXT DEFAULT ""',
            'invoice_date': 'TEXT DEFAULT ""',
            'supplier_name': 'TEXT DEFAULT ""',
            'supplier_inn': 'TEXT DEFAULT ""',
            'payment_purpose': 'TEXT DEFAULT ""',
            'delivery_term': 'TEXT DEFAULT ""',
            'delivery_date': 'TEXT DEFAULT ""',
            'vat_amount': 'REAL DEFAULT 0',
            'total_with_vat': 'REAL DEFAULT 0',
        }
        for col, dtype in ext_cols.items():
            if col not in columns:
                c.execute(f"ALTER TABLE purchase_payments ADD COLUMN {col} {dtype}")
        self.conn.commit()

    def _ensure_purchase_spec_items_table(self):
        """Создаёт таблицу позиций спецификации закупок"""
        c = self.conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS purchase_spec_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            spec_id INTEGER NOT NULL,
            name TEXT,
            quantity REAL DEFAULT 0,
            price REAL DEFAULT 0,
            total REAL DEFAULT 0,
            delivery_term TEXT,
            delivery_unit TEXT,
            FOREIGN KEY (spec_id) REFERENCES purchase_specifications(id)
        )''')
        self.conn.commit()

    def _ensure_purchase_spec_delivery_address(self):
        """Добавляет колонку delivery_address в таблицу purchase_specifications"""
        c = self.conn.cursor()
        c.execute("PRAGMA table_info(purchase_specifications)")
        columns = [row[1] for row in c.fetchall()]
        if 'delivery_address' not in columns:
            c.execute("ALTER TABLE purchase_specifications ADD COLUMN delivery_address TEXT DEFAULT ''")
        self.conn.commit()

    def _ensure_suppliers_columns(self):
        """Добавляет недостающие колонки в таблицу suppliers"""
        c = self.conn.cursor()
        c.execute("PRAGMA table_info(suppliers)")
        columns = [row[1] for row in c.fetchall()]
        additional_columns = {
            'contact': 'TEXT DEFAULT ""',
            'phone': 'TEXT DEFAULT ""',
            'email': 'TEXT DEFAULT ""',
            'address': 'TEXT DEFAULT ""',
            'note': 'TEXT DEFAULT ""'
        }
        for col_name, col_type in additional_columns.items():
            if col_name not in columns:
                c.execute(f"ALTER TABLE suppliers ADD COLUMN {col_name} {col_type}")
        self.conn.commit()

    def create_tables(self):
        c = self.conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            path TEXT NOT NULL,
            contract_date TEXT,
            contract_amount TEXT,
            contract_currency TEXT,
            del_term TEXT,
            del_unit TEXT,
            del_base_date TEXT,
            confirmation_date TEXT,
            work_start TEXT,
            work_term TEXT,
            work_unit TEXT,
            delivery_address TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            number INTEGER NOT NULL,
            date TEXT,
            amount TEXT,
            currency TEXT,
            percent TEXT,
            paid INTEGER DEFAULT 0,
            contract_date TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS specifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            number INTEGER NOT NULL,
            name TEXT,
            quantity TEXT,
            price TEXT,
            currency TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            number INTEGER NOT NULL,
            manufacturer TEXT,
            subproject TEXT,
            kd TEXT,
            article TEXT,
            name TEXT,
            name_eng TEXT,
            quantity INTEGER DEFAULT 0,
            note TEXT,
            ordered INTEGER DEFAULT 0,
            order_date TEXT,
            in_order INTEGER DEFAULT 0,
            received INTEGER DEFAULT 0,
            receipt_date TEXT,
            price_request INTEGER DEFAULT 0
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_batch_id INTEGER NOT NULL,
            order_date TEXT,
            project_name TEXT,
            payment_date TEXT,
            manufacturer TEXT,
            subproject TEXT,
            kd TEXT,
            article TEXT,
            name TEXT,
            name_eng TEXT,
            quantity INTEGER DEFAULT 0,
            note TEXT,
            delivery_days INTEGER DEFAULT 0,
            delivery_unit_order TEXT,
            min_delivery_date TEXT,
            max_delivery_date TEXT,
            invoice_number TEXT,
            supplier TEXT,
            delivery_number TEXT DEFAULT '',
            received INTEGER DEFAULT 0,
            receipt_date TEXT DEFAULT '',
            write_off_date TEXT DEFAULT '',
            price_request INTEGER DEFAULT 0,
            price_request_num INTEGER DEFAULT 0
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_batch_id INTEGER NOT NULL,
            article TEXT,
            name TEXT,
            name_eng TEXT,
            quantity INTEGER DEFAULT 0,
            delivery_term INTEGER DEFAULT 0,
            delivery_unit TEXT,
            price TEXT,
            currency TEXT,
            note TEXT,
            manufacturer TEXT,
            subproject TEXT,
            kd TEXT,
            FOREIGN KEY (order_batch_id) REFERENCES orders(order_batch_id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS nomenclature (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            manufacturer TEXT,
            article TEXT,
            name_rus TEXT,
            name_eng TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS manufacturers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS subprojects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            project_name TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS kd_directory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kd_number TEXT NOT NULL,
            project_name TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            contact TEXT,
            phone TEXT,
            email TEXT,
            address TEXT,
            note TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS purchase_specifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            supplier TEXT,
            name TEXT,
            quantity REAL DEFAULT 0,
            price REAL DEFAULT 0,
            total REAL DEFAULT 0,
            currency TEXT,
            delivery_term INTEGER DEFAULT 0,
            delivery_unit TEXT,
            payment_date TEXT,
            delivery_date TEXT,
            fully_paid INTEGER DEFAULT 0,
            received INTEGER DEFAULT 0,
            delivery_address TEXT,
            note TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS purchase_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            spec_id INTEGER NOT NULL,
            number INTEGER NOT NULL,
            date TEXT,
            amount REAL DEFAULT 0,
            currency TEXT,
            percent REAL DEFAULT 0,
            paid INTEGER DEFAULT 0,
            FOREIGN KEY (spec_id) REFERENCES purchase_specifications(id)
        )''')
        self.conn.commit()

    # === Проекты ===
    def get_all_projects(self, sort_by="name"):
        """sort_by: 'name' | 'contract_date' (новые сверху) | 'id'"""
        c = self.conn.cursor()
        c.execute("SELECT * FROM projects ORDER BY id")
        rows = c.fetchall()
        if sort_by == "name":
            rows = sorted(rows, key=lambda r: (r["name"] or "").upper())
        elif sort_by == "contract_date":
            dated = [r for r in rows if _date_sort_key(r["contract_date"])[0] == 0]
            undated = [r for r in rows if _date_sort_key(r["contract_date"])[0] == 1]
            dated.sort(key=lambda r: _date_sort_key(r["contract_date"])[1], reverse=True)
            rows = dated + undated
        return rows

    def get_project(self, name):
        c = self.conn.cursor()
        c.execute("SELECT * FROM projects WHERE name=?", (name,))
        return c.fetchone()

    def get_project_id(self, name):
        c = self.conn.cursor()
        c.execute("SELECT id FROM projects WHERE name=?", (name,))
        row = c.fetchone()
        return row['id'] if row else None

    def add_project(self, name, path):
        c = self.conn.cursor()
        try:
            c.execute("INSERT INTO projects (name, path) VALUES (?, ?)", (name, path))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def update_project(self, name, data):
        c = self.conn.cursor()
        c.execute('''UPDATE projects SET 
            contract_date=?, contract_amount=?, contract_currency=?,
            del_term=?, del_unit=?, del_base_date=?,
            confirmation_date=?, work_start=?, work_term=?, work_unit=?,
            delivery_address=?
            WHERE name=?''',
            (data.get('contract_date', ''), data.get('contract_amount', ''),
             data.get('contract_currency', ''), data.get('del_term', ''),
             data.get('del_unit', ''), data.get('del_base_date', ''),
             data.get('confirmation_date', ''), data.get('work_start', ''),
             data.get('work_term', ''), data.get('work_unit', ''),
             data.get('delivery_address', ''), name))
        self.conn.commit()

    def rename_project(self, old_name, new_name):
        """Переименование проекта с обновлением ссылок по имени (заказы, подпроекты, КД)"""
        if not new_name or old_name == new_name:
            return False
        if self.get_project(new_name):
            return False
        try:
            with self.conn:
                self.conn.execute("UPDATE projects SET name=? WHERE name=?", (new_name, old_name))
                self.conn.execute("UPDATE orders SET project_name=? WHERE project_name=?", (new_name, old_name))
                self.conn.execute("UPDATE subprojects SET project_name=? WHERE project_name=?", (new_name, old_name))
                self.conn.execute("UPDATE kd_directory SET project_name=? WHERE project_name=?", (new_name, old_name))
            return True
        except sqlite3.Error as e:
            print(f"Ошибка переименования проекта: {e}")
            return False

    def update_project_path(self, name, path):
        with self.conn:
            self.conn.execute("UPDATE projects SET path=? WHERE name=?", (path, name))

    def delete_project(self, name):
        """Удаляет проект и все зависимые записи одной транзакцией.
        Заказы (orders) сохраняются как история — они привязаны к имени проекта."""
        project = self.get_project(name)
        if not project:
            return
        project_id = project['id']
        with self.conn:
            c = self.conn.cursor()
            c.execute("""DELETE FROM purchase_payments WHERE spec_id IN
                         (SELECT id FROM purchase_specifications WHERE project_id=?)""", (project_id,))
            c.execute("""DELETE FROM purchase_spec_items WHERE spec_id IN
                         (SELECT id FROM purchase_specifications WHERE project_id=?)""", (project_id,))
            c.execute("DELETE FROM purchase_specifications WHERE project_id=?", (project_id,))
            c.execute("DELETE FROM payments WHERE project_id=?", (project_id,))
            c.execute("DELETE FROM specifications WHERE project_id=?", (project_id,))
            c.execute("DELETE FROM purchases WHERE project_id=?", (project_id,))
            c.execute("DELETE FROM projects WHERE id=?", (project_id,))

    # === Платежи ===
    def get_payments(self, project_id):
        c = self.conn.cursor()
        c.execute("SELECT * FROM payments WHERE project_id=? ORDER BY number", (project_id,))
        return c.fetchall()

    def add_payment(self, project_id, data):
        c = self.conn.cursor()
        c.execute('''INSERT INTO payments (project_id, number, date, amount, currency, percent, paid, contract_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (project_id, data.get('number', 1), data.get('date', ''),
             data.get('amount', ''), data.get('currency', ''),
             data.get('percent', ''), data.get('paid', 0),
             data.get('contract_date', '')))
        self.conn.commit()

    def update_payment(self, project_id, number, data):
        c = self.conn.cursor()
        c.execute('''UPDATE payments SET date=?, amount=?, currency=?, percent=?, paid=?, contract_date=?
            WHERE project_id=? AND number=?''',
            (data.get('date', ''), data.get('amount', ''), data.get('currency', ''),
             data.get('percent', ''), data.get('paid', 0), data.get('contract_date', ''),
             project_id, number))
        self.conn.commit()

    def delete_payment(self, project_id, number):
        c = self.conn.cursor()
        c.execute("DELETE FROM payments WHERE project_id=? AND number=?", (project_id, number))
        self.conn.commit()

    # === Спецификации ===
    def get_specifications(self, project_id):
        c = self.conn.cursor()
        c.execute("SELECT * FROM specifications WHERE project_id=? ORDER BY number", (project_id,))
        return c.fetchall()

    def add_specification(self, project_id, data):
        c = self.conn.cursor()
        c.execute('''INSERT INTO specifications (project_id, number, name, quantity, price, currency)
            VALUES (?, ?, ?, ?, ?, ?)''',
            (project_id, data.get('number', 1), data.get('name', ''),
             data.get('quantity', ''), data.get('price', ''), data.get('currency', '')))
        self.conn.commit()

    def update_specification(self, project_id, number, data):
        c = self.conn.cursor()
        c.execute('''UPDATE specifications SET name=?, quantity=?, price=?, currency=?
            WHERE project_id=? AND number=?''',
            (data.get('name', ''), data.get('quantity', ''),
             data.get('price', ''), data.get('currency', ''),
             project_id, number))
        self.conn.commit()

    def delete_specification(self, project_id, number):
        c = self.conn.cursor()
        c.execute("DELETE FROM specifications WHERE project_id=? AND number=?", (project_id, number))
        self.conn.commit()

    # === Закупки ===
    def get_purchases(self, project_id):
        """НОВОЕ: JOIN с projects, чтобы каждая строка несла имя своего проекта
        (колонка project_name) — нужно для колонки «Проект» во вкладке «Закупки»."""
        c = self.conn.cursor()
        c.execute('''SELECT p.*, pr.name AS project_name
                     FROM purchases p
                     LEFT JOIN projects pr ON pr.id = p.project_id
                     WHERE p.project_id=? ORDER BY p.number''', (project_id,))
        return c.fetchall()

    def get_next_number(self, table, project_id):
        """Следующий свободный номер в таблице (payments / specifications / purchases)
        по ВСЕМ записям проекта — не зависит от фильтров в интерфейсе."""
        if table not in ("payments", "specifications", "purchases"):
            raise ValueError(table)
        c = self.conn.cursor()
        c.execute(f"SELECT MAX(CAST(number AS INTEGER)) AS m FROM {table} WHERE project_id=?", (project_id,))
        row = c.fetchone()
        return (row["m"] or 0) + 1

    def get_purchase_by_number(self, project_id, number):
        c = self.conn.cursor()
        c.execute("SELECT * FROM purchases WHERE project_id=? AND number=?", (project_id, number))
        return c.fetchone()

    def add_purchase(self, project_id, data):
        c = self.conn.cursor()
        c.execute('''INSERT INTO purchases 
            (project_id, number, manufacturer, subproject, kd, article, name, name_eng,
             quantity, note, ordered, order_date, in_order, received, receipt_date, price_request)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (project_id, data.get('number', 1), data.get('manufacturer', ''),
             data.get('subproject', ''), data.get('kd', ''), data.get('article', ''),
             data.get('name', ''), data.get('name_eng', ''),
             data.get('quantity', 0), data.get('note', ''),
             data.get('ordered', 0), data.get('order_date', ''),
             data.get('in_order', 0), data.get('received', 0),
             data.get('receipt_date', ''), data.get('price_request', 0)))
        self.conn.commit()

    def update_purchase(self, project_id, number, data):
        c = self.conn.cursor()
        c.execute('''UPDATE purchases SET 
            manufacturer=?, subproject=?, kd=?, article=?, name=?, name_eng=?,
            quantity=?, note=?, ordered=?, order_date=?, in_order=?, received=?,
            receipt_date=?, price_request=?
            WHERE project_id=? AND number=?''',
            (data.get('manufacturer', ''), data.get('subproject', ''),
             data.get('kd', ''), data.get('article', ''),
             data.get('name', ''), data.get('name_eng', ''),
             data.get('quantity', 0), data.get('note', ''),
             data.get('ordered', 0), data.get('order_date', ''),
             data.get('in_order', 0), data.get('received', 0),
             data.get('receipt_date', ''), data.get('price_request', 0),
             project_id, number))
        self.conn.commit()

    def set_purchase_flag(self, project_id, number, field, value):
        if field not in ("ordered", "in_order", "received", "price_request"):
            raise ValueError(f"Недопустимое поле: {field}")
        c = self.conn.cursor()
        c.execute(f"UPDATE purchases SET {field}=? WHERE project_id=? AND number=?",
                  (value, project_id, number))
        self.conn.commit()

    def move_purchase(self, from_project_id, number, to_project_id):
        """НОВОЕ: переносит закупку в другой проект с перенумерацией
        (чтобы не было дублей номеров в целевом проекте).
        Возвращает новый номер позиции."""
        if from_project_id == to_project_id:
            return number
        new_number = self.get_next_number("purchases", to_project_id)
        c = self.conn.cursor()
        c.execute('''UPDATE purchases SET project_id=?, number=?
                     WHERE project_id=? AND number=?''',
                  (to_project_id, new_number, from_project_id, number))
        self.conn.commit()
        return new_number

    def delete_purchase(self, project_id, number):
        c = self.conn.cursor()
        c.execute("DELETE FROM purchases WHERE project_id=? AND number=?", (project_id, number))
        self.conn.commit()

    # === Заказы ===
    def get_next_order_batch_id(self):
        c = self.conn.cursor()
        c.execute("SELECT MAX(order_batch_id) as max_id FROM orders")
        row = c.fetchone()
        return (row['max_id'] or 0) + 1

    def get_next_price_request_num(self):
        """Следующий номер Z-серии (запросы цены)."""
        c = self.conn.cursor()
        c.execute("SELECT MAX(price_request_num) AS m FROM orders WHERE price_request=1")
        row = c.fetchone()
        return (row['m'] or 0) + 1

    def get_order_batches(self):
        """Получает список заказов с учётом received, receipt_date, delivery_number,
        write_off_date, price_request, price_request_num"""
        c = self.conn.cursor()
        c.execute('''SELECT order_batch_id, 
                            MAX(order_date) as order_date, 
                            MAX(project_name) as project_name, 
                            MAX(payment_date) as payment_date,
                            MAX(manufacturer) as manufacturer,
                            MAX(delivery_days) as delivery_days, 
                            MAX(delivery_unit_order) as delivery_unit_order, 
                            MAX(min_delivery_date) as min_delivery_date, 
                            MAX(max_delivery_date) as max_delivery_date,
                            MAX(invoice_number) as invoice_number,
                            MAX(supplier) as supplier,
                            MAX(delivery_number) as delivery_number,
                            MAX(received) as received,
                            MAX(receipt_date) as receipt_date,
                            MAX(write_off_date) as write_off_date,
                            MAX(price_request) as price_request,
                            MAX(price_request_num) as price_request_num
                     FROM orders 
                     GROUP BY order_batch_id 
                     ORDER BY order_batch_id DESC''')
        return c.fetchall()

    def get_order_items(self, batch_id):
        """Получает позиции заказа из таблицы orders по order_batch_id"""
        c = self.conn.cursor()
        c.execute('''SELECT id, article, name, name_eng, quantity, note, 
                            manufacturer, subproject, kd,
                            delivery_term, delivery_unit, price, currency
                     FROM orders 
                     WHERE order_batch_id=? 
                     ORDER BY id''',
                  (batch_id,))
        rows = c.fetchall()
        result = []
        for row in rows:
            result.append({
                'id': row['id'],
                'article': row['article'] or '',
                'name': row['name'] or '',
                'name_eng': row['name_eng'] or '',
                'quantity': row['quantity'] or 0,
                'delivery_term': row['delivery_term'] or 0,
                'delivery_unit': row['delivery_unit'] or '',
                'price': row['price'] or '',
                'currency': row['currency'] or '',
                'note': row['note'] or '',
                'manufacturer': row['manufacturer'] or '',
                'subproject': row['subproject'] or '',
                'kd': row['kd'] or '',
            })
        return result

    def add_order(self, data):
        c = self.conn.cursor()
        c.execute('''INSERT INTO orders 
            (order_batch_id, order_date, project_name, payment_date, manufacturer,
             subproject, kd, article, name, name_eng, quantity, note,
             price_request, price_request_num)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (data.get('order_batch_id', 0), data.get('order_date', ''),
             data.get('project_name', ''), data.get('payment_date', ''),
             data.get('manufacturer', ''), data.get('subproject', ''),
             data.get('kd', ''), data.get('article', ''),
             data.get('name', ''), data.get('name_eng', ''),
             data.get('quantity', 0), data.get('note', ''),
             data.get('price_request', 0), data.get('price_request_num', 0)))
        self.conn.commit()

    def update_order_batch(self, batch_id, order_date, project_name, payment_date,
                           delivery_days, delivery_unit, min_date, max_date):
        c = self.conn.cursor()
        c.execute('''UPDATE orders SET order_date=?, project_name=?, payment_date=?,
            delivery_days=?, delivery_unit_order=?, min_delivery_date=?, max_delivery_date=?
            WHERE order_batch_id=?''',
            (order_date, project_name, payment_date,
             delivery_days, delivery_unit, min_date, max_date, batch_id))
        self.conn.commit()

    def set_order_received(self, batch_id, value, receipt_date=""):
        """Устанавливает флаг 'Получено' для всех позиций заказа"""
        c = self.conn.cursor()
        c.execute("UPDATE orders SET received=?, receipt_date=? WHERE order_batch_id=?",
                  (value, receipt_date, batch_id))
        self.conn.commit()

    def set_order_delivery_number(self, batch_id, delivery_number):
        """Устанавливает номер поставки для всех позиций заказа"""
        c = self.conn.cursor()
        c.execute("UPDATE orders SET delivery_number=? WHERE order_batch_id=?",
                  (delivery_number, batch_id))
        self.conn.commit()

    def set_order_write_off_date(self, batch_id, write_off_date):
        """Устанавливает дату списания для всех позиций заказа"""
        c = self.conn.cursor()
        c.execute("UPDATE orders SET write_off_date=? WHERE order_batch_id=?",
                  (write_off_date, batch_id))
        self.conn.commit()

    def set_order_price_request(self, batch_id, value):
        """Включить/выключить 'Запрос цены' для заказа.
        При включении назначает следующий номер Z-серии, если его ещё нет."""
        c = self.conn.cursor()
        if value:
            c.execute("SELECT MAX(price_request_num) FROM orders WHERE order_batch_id=?", (batch_id,))
            num = c.fetchone()[0] or 0
            if not num:
                num = self.get_next_price_request_num()
            c.execute("UPDATE orders SET price_request=1, price_request_num=? WHERE order_batch_id=?",
                      (num, batch_id))
        else:
            c.execute("UPDATE orders SET price_request=0 WHERE order_batch_id=?", (batch_id,))
        self.conn.commit()

    def get_order_projects(self):
        """Получить список уникальных проектов из заказов"""
        c = self.conn.cursor()
        c.execute("SELECT DISTINCT project_name FROM orders WHERE project_name IS NOT NULL AND project_name != '' ORDER BY project_name")
        return [row[0] for row in c.fetchall()]

    def delete_order_batch(self, batch_id):
        c = self.conn.cursor()
        c.execute("DELETE FROM orders WHERE order_batch_id=?", (batch_id,))
        c.execute("DELETE FROM order_items WHERE order_batch_id=?", (batch_id,))
        self.conn.commit()

    def update_order_item(self, item_id, data):
        """Обновление позиции заказа в таблице orders по id строки"""
        c = self.conn.cursor()
        c.execute("SELECT article, name, name_eng, quantity, note, manufacturer, subproject, kd, delivery_term, delivery_unit, price, currency FROM orders WHERE id=?", (item_id,))
        current = c.fetchone()
        if not current:
            return
        article = data.get('article', current['article'] or '')
        name = data.get('name', current['name'] or '')
        name_eng = data.get('name_eng', current['name_eng'] or '')
        quantity = data.get('quantity', current['quantity'] or 0)
        note = data.get('note', current['note'] or '')
        manufacturer = data.get('manufacturer', current['manufacturer'] or '')
        subproject = data.get('subproject', current['subproject'] or '')
        kd = data.get('kd', current['kd'] or '')
        delivery_term = data.get('delivery_term', current['delivery_term'] or 0)
        delivery_unit = data.get('delivery_unit', current['delivery_unit'] or '')
        price = data.get('price', current['price'] or '')
        currency = data.get('currency', current['currency'] or '')
        c.execute('''UPDATE orders SET 
                        article=?, name=?, name_eng=?, quantity=?, 
                        note=?, manufacturer=?, subproject=?, kd=?,
                        delivery_term=?, delivery_unit=?, price=?, currency=?
                     WHERE id=?''',
                  (article, name, name_eng, quantity, note,
                   manufacturer, subproject, kd,
                   delivery_term, delivery_unit, price, currency,
                   item_id))
        self.conn.commit()

    def delete_order_item(self, item_id):
        c = self.conn.cursor()
        c.execute("DELETE FROM orders WHERE id=?", (item_id,))
        self.conn.commit()

    # === Номенклатура ===
    def search_nomenclature(self, query, field='article'):
        c = self.conn.cursor()
        if field == 'article':
            c.execute("SELECT * FROM nomenclature WHERE article LIKE ? LIMIT 10", (f"%{query}%",))
        else:
            c.execute("SELECT * FROM nomenclature WHERE name_rus LIKE ? OR name_eng LIKE ? LIMIT 10",
                      (f"%{query}%", f"%{query}%"))
        return c.fetchall()

    def add_nomenclature(self, data):
        c = self.conn.cursor()
        c.execute('''INSERT INTO nomenclature (manufacturer, article, name_rus, name_eng)
            VALUES (?, ?, ?, ?)''',
            (data.get('manufacturer', ''), data.get('article', ''),
             data.get('name_rus', ''), data.get('name_eng', '')))
        self.conn.commit()

    def get_nomenclature(self):
        c = self.conn.cursor()
        c.execute("SELECT * FROM nomenclature ORDER BY article")
        return c.fetchall()

    def delete_nomenclature(self, item_id):
        c = self.conn.cursor()
        c.execute("DELETE FROM nomenclature WHERE id=?", (item_id,))
        self.conn.commit()

    def find_nomenclature_by_article(self, article):
        """Точный поиск по артикулу (без учёта регистра и пробелов по краям)."""
        if not article:
            return None
        c = self.conn.cursor()
        c.execute("SELECT * FROM nomenclature WHERE UPPER(TRIM(article)) = UPPER(TRIM(?)) LIMIT 1", (article,))
        return c.fetchone()

    # === Производители ===
    def get_manufacturers(self):
        c = self.conn.cursor()
        c.execute("SELECT * FROM manufacturers ORDER BY name")
        return c.fetchall()

    def add_manufacturer(self, name):
        c = self.conn.cursor()
        try:
            c.execute("INSERT INTO manufacturers (name) VALUES (?)", (name,))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def rename_manufacturer(self, old_name, new_name):
        """Переименование производителя с обновлением закупок, заказов и номенклатуры."""
        try:
            with self.conn:
                self.conn.execute("UPDATE manufacturers SET name=? WHERE name=?", (new_name, old_name))
                for table in ("purchases", "orders", "nomenclature"):
                    self.conn.execute(f"UPDATE {table} SET manufacturer=? WHERE manufacturer=?", (new_name, old_name))
            return True
        except sqlite3.IntegrityError:
            return False

    def delete_manufacturer(self, name):
        c = self.conn.cursor()
        c.execute("DELETE FROM manufacturers WHERE name=?", (name,))
        self.conn.commit()

    # === Подпроекты ===
    def get_subprojects(self, project_name=None):
        c = self.conn.cursor()
        if project_name:
            c.execute("SELECT * FROM subprojects WHERE project_name=? OR project_name='' OR project_name IS NULL ORDER BY name",
                      (project_name,))
        else:
            c.execute("SELECT * FROM subprojects ORDER BY name")
        return c.fetchall()

    def add_subproject(self, name, project_name=""):
        c = self.conn.cursor()
        c.execute("INSERT INTO subprojects (name, project_name) VALUES (?, ?)", (name, project_name))
        self.conn.commit()

    def delete_subproject(self, name):
        c = self.conn.cursor()
        c.execute("DELETE FROM subprojects WHERE name=?", (name,))
        self.conn.commit()

    def update_subproject(self, subproject_id, new_name, new_project_name):
        """Обновляет подпроект по ID"""
        c = self.conn.cursor()
        c.execute("UPDATE subprojects SET name=?, project_name=? WHERE id=?",
                  (new_name, new_project_name, subproject_id))
        self.conn.commit()

    # === КД ===
    def get_kd_directory(self, project_name=None):
        c = self.conn.cursor()
        if project_name:
            c.execute("SELECT * FROM kd_directory WHERE project_name=? OR project_name='' OR project_name IS NULL ORDER BY kd_number",
                      (project_name,))
        else:
            c.execute("SELECT * FROM kd_directory ORDER BY kd_number")
        return c.fetchall()

    def add_kd(self, kd_number, project_name=""):
        c = self.conn.cursor()
        c.execute("INSERT INTO kd_directory (kd_number, project_name) VALUES (?, ?)", (kd_number, project_name))
        self.conn.commit()

    def delete_kd(self, kd_number):
        c = self.conn.cursor()
        c.execute("DELETE FROM kd_directory WHERE kd_number=?", (kd_number,))
        self.conn.commit()

    # === Поставщики ===
    def get_suppliers(self):
        c = self.conn.cursor()
        c.execute("SELECT * FROM suppliers ORDER BY name")
        return c.fetchall()

    def add_supplier(self, data):
        """Добавляет поставщика. Принимает словарь data. Возвращает True при успехе."""
        c = self.conn.cursor()
        try:
            c.execute('''INSERT INTO suppliers (name, contact, phone, email, address, note)
                VALUES (?, ?, ?, ?, ?, ?)''',
                (data.get('name', ''), data.get('contact', ''),
                 data.get('phone', ''), data.get('email', ''),
                 data.get('address', ''), data.get('note', '')))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def update_supplier(self, supplier_id, data):
        """Обновляет поставщика по ID. Принимает id и словарь data."""
        c = self.conn.cursor()
        c.execute('''UPDATE suppliers SET name=?, contact=?, phone=?, email=?, address=?, note=?
            WHERE id=?''',
            (data.get('name', ''), data.get('contact', ''),
             data.get('phone', ''), data.get('email', ''),
             data.get('address', ''), data.get('note', ''),
             supplier_id))
        self.conn.commit()

    def delete_supplier(self, supplier_id):
        """Удаляет поставщика по ID."""
        c = self.conn.cursor()
        c.execute("DELETE FROM suppliers WHERE id=?", (supplier_id,))
        self.conn.commit()

    # === Спецификации закупок ===
    def get_purchase_specifications(self, project_id):
        c = self.conn.cursor()
        c.execute("SELECT * FROM purchase_specifications WHERE project_id=? ORDER BY id", (project_id,))
        return c.fetchall()

    def add_purchase_spec(self, project_id, data):
        c = self.conn.cursor()
        c.execute('''INSERT INTO purchase_specifications 
            (project_id, supplier, name, quantity, price, total, currency,
             delivery_term, delivery_unit, payment_date, delivery_date,
             fully_paid, received, delivery_address, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (project_id, data.get('supplier', ''), data.get('name', ''),
             data.get('quantity', 0), data.get('price', 0), data.get('total', 0),
             data.get('currency', ''), data.get('delivery_term', 0),
             data.get('delivery_unit', ''), data.get('payment_date', ''),
             data.get('delivery_date', ''), data.get('fully_paid', 0),
             data.get('received', 0), data.get('delivery_address', ''),
             data.get('note', '')))
        self.conn.commit()

    def update_purchase_spec(self, spec_id, data):
        c = self.conn.cursor()
        c.execute('''UPDATE purchase_specifications SET 
            supplier=?, name=?, quantity=?, price=?, total=?, currency=?,
            delivery_term=?, delivery_unit=?, payment_date=?, delivery_date=?,
            fully_paid=?, received=?, delivery_address=?, note=?
            WHERE id=?''',
            (data.get('supplier', ''), data.get('name', ''),
             data.get('quantity', 0), data.get('price', 0), data.get('total', 0),
             data.get('currency', ''), data.get('delivery_term', 0),
             data.get('delivery_unit', ''), data.get('payment_date', ''),
             data.get('delivery_date', ''), data.get('fully_paid', 0),
             data.get('received', 0), data.get('delivery_address', ''),
             data.get('note', ''),
             spec_id))
        self.conn.commit()

    def delete_purchase_spec(self, spec_id):
        c = self.conn.cursor()
        c.execute("DELETE FROM purchase_payments WHERE spec_id=?", (spec_id,))
        c.execute("DELETE FROM purchase_spec_items WHERE spec_id=?", (spec_id,))
        c.execute("DELETE FROM purchase_specifications WHERE id=?", (spec_id,))
        self.conn.commit()

    # === Позиции спецификации закупок ===
    def add_purchase_spec_item(self, spec_id, data):
        c = self.conn.cursor()
        c.execute('''INSERT INTO purchase_spec_items 
            (spec_id, name, quantity, price, total, delivery_term, delivery_unit)
            VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (spec_id, data.get('name', ''), data.get('quantity', 0),
             data.get('price', 0), data.get('total', 0),
             data.get('delivery_term', ''), data.get('delivery_unit', '')))
        self.conn.commit()

    def get_purchase_spec_items(self, spec_id):
        c = self.conn.cursor()
        c.execute("SELECT * FROM purchase_spec_items WHERE spec_id=? ORDER BY id", (spec_id,))
        return c.fetchall()

    def update_purchase_spec_item(self, item_id, data):
        c = self.conn.cursor()
        c.execute('''UPDATE purchase_spec_items SET 
            name=?, quantity=?, price=?, total=?, delivery_term=?, delivery_unit=?
            WHERE id=?''',
            (data.get('name', ''), data.get('quantity', 0),
             data.get('price', 0), data.get('total', 0),
             data.get('delivery_term', ''), data.get('delivery_unit', ''),
             item_id))
        self.conn.commit()

    def delete_purchase_spec_item(self, item_id):
        c = self.conn.cursor()
        c.execute("DELETE FROM purchase_spec_items WHERE id=?", (item_id,))
        self.conn.commit()

    def delete_purchase_spec_items(self, spec_id):
        c = self.conn.cursor()
        c.execute("DELETE FROM purchase_spec_items WHERE spec_id=?", (spec_id,))
        self.conn.commit()

    # === Платежи по спецификации закупок ===
    def get_purchase_payments(self, spec_id):
        c = self.conn.cursor()
        c.execute("SELECT * FROM purchase_payments WHERE spec_id=? ORDER BY number", (spec_id,))
        return c.fetchall()

    def get_purchase_payments_ext(self, spec_id):
        c = self.conn.cursor()
        c.execute("SELECT * FROM purchase_payments WHERE spec_id=? ORDER BY number", (spec_id,))
        return c.fetchall()

    def add_purchase_payment(self, spec_id, data):
        c = self.conn.cursor()
        c.execute('''INSERT INTO purchase_payments (spec_id, number, date, amount, currency, percent, paid)
            VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (spec_id, data.get('number', 1), data.get('date', ''),
             data.get('amount', 0), data.get('currency', ''),
             data.get('percent', 0), data.get('paid', 0)))
        self.conn.commit()

    def add_purchase_payment_ext(self, spec_id, data):
        c = self.conn.cursor()
        c.execute('''INSERT INTO purchase_payments 
            (spec_id, number, date, amount, currency, percent, paid,
             invoice_number, invoice_date, supplier_name, supplier_inn,
             payment_purpose, delivery_term, delivery_date, vat_amount, total_with_vat)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (spec_id, data.get('number', 1), data.get('date', ''),
             data.get('amount', 0), data.get('currency', ''),
             data.get('percent', 0), data.get('paid', 0),
             data.get('invoice_number', ''), data.get('invoice_date', ''),
             data.get('supplier_name', ''), data.get('supplier_inn', ''),
             data.get('payment_purpose', ''), data.get('delivery_term', ''),
             data.get('delivery_date', ''), data.get('vat_amount', 0),
             data.get('total_with_vat', 0)))
        self.conn.commit()

    def update_purchase_payment(self, payment_id, data):
        c = self.conn.cursor()
        c.execute('''UPDATE purchase_payments SET number=?, date=?, amount=?, currency=?, percent=?, paid=?
            WHERE id=?''',
            (data.get('number', 1), data.get('date', ''),
             data.get('amount', 0), data.get('currency', ''),
             data.get('percent', 0), data.get('paid', 0),
             payment_id))
        self.conn.commit()

    def update_purchase_payment_ext(self, payment_id, data):
        c = self.conn.cursor()
        c.execute('''UPDATE purchase_payments SET 
            number=?, date=?, amount=?, currency=?, percent=?, paid=?,
            invoice_number=?, invoice_date=?, supplier_name=?, supplier_inn=?,
            payment_purpose=?, delivery_term=?, delivery_date=?, vat_amount=?, total_with_vat=?
            WHERE id=?''',
            (data.get('number', 1), data.get('date', ''),
             data.get('amount', 0), data.get('currency', ''),
             data.get('percent', 0), data.get('paid', 0),
             data.get('invoice_number', ''), data.get('invoice_date', ''),
             data.get('supplier_name', ''), data.get('supplier_inn', ''),
             data.get('payment_purpose', ''), data.get('delivery_term', ''),
             data.get('delivery_date', ''), data.get('vat_amount', 0),
             data.get('total_with_vat', 0),
             payment_id))
        self.conn.commit()

    def delete_purchase_payment(self, payment_id):
        c = self.conn.cursor()
        c.execute("DELETE FROM purchase_payments WHERE id=?", (payment_id,))
        self.conn.commit()

    # === Адреса доставки ===
    def get_delivery_addresses(self):
        c = self.conn.cursor()
        c.execute("SELECT * FROM delivery_addresses ORDER BY name")
        return c.fetchall()

    def add_delivery_address(self, data):
        c = self.conn.cursor()
        c.execute('''INSERT INTO delivery_addresses (name, address, contact, phone, note)
            VALUES (?, ?, ?, ?, ?)''',
            (data.get('name', ''), data.get('address', ''),
             data.get('contact', ''), data.get('phone', ''), data.get('note', '')))
        self.conn.commit()

    def update_delivery_address(self, addr_id, data):
        c = self.conn.cursor()
        c.execute('''UPDATE delivery_addresses SET name=?, address=?, contact=?, phone=?, note=?
            WHERE id=?''',
            (data.get('name', ''), data.get('address', ''),
             data.get('contact', ''), data.get('phone', ''), data.get('note', ''),
             addr_id))
        self.conn.commit()

    def delete_delivery_address(self, addr_id):
        c = self.conn.cursor()
        c.execute("DELETE FROM delivery_addresses WHERE id=?", (addr_id,))
        self.conn.commit()

    def close(self):
        if self.conn:
            try:
                self.conn.close()
            except sqlite3.Error:
                pass
            self.conn = None