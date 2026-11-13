import tkinter as tk
from tkinter import ttk, messagebox
import re
import os

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

try:
    from config import TIME_UNITS, ORDER_CURRENCIES
except ImportError:
    TIME_UNITS = ["Календарные дни", "Рабочие дни", "Недели", "Месяцы"]
    ORDER_CURRENCIES = ["EUR", "USD", "CNY", "RUB"]

try:
    from utils import parse_number, parse_delivery_time, translate_time_unit
except ImportError:
    def parse_number(s):
        if s is None: return None
        s = str(s).strip()
        if not s: return None
        if '.' in s and ',' in s: s = s.replace('.', '').replace(',', '.')
        elif ',' in s: s = s.replace(',', '.')
        try: return float(s)
        except: return None

    def translate_time_unit(unit_str):
        if not unit_str: return "Недели"
        u = unit_str.upper().strip()
        m = {'HAFTA': 'Недели', 'WEEK': 'Недели', 'WEEKS': 'Недели', 'НЕДЕЛЬ': 'Недели',
             'GÜN': 'Календарные дни', 'DAY': 'Календарные дни', 'DAYS': 'Календарные дни',
             'AY': 'Месяцы', 'MONTH': 'Месяцы', 'MONTHS': 'Месяцы'}
        return m.get(u, "Недели")

    def parse_delivery_time(time_str):
        if not time_str: return None, None
        t = str(time_str).strip().upper()
        match = re.match(r'(\d+)\s*[-–]\s*(\d+)\s+([A-ZА-Я]+(?:\s+[A-ZА-Я]+)?)', t)
        if match:
            n1, n2, unit = int(match.group(1)), int(match.group(2)), match.group(3)
            return max(n1, n2), translate_time_unit(unit)
        match = re.match(r'(\d+)\s+([A-ZА-Я]+(?:\s+[A-ZА-Я]+)?)', t)
        if match:
            return int(match.group(1)), translate_time_unit(match.group(2))
        return None, None


class FileImportMatchDialog(tk.Toplevel):
    def __init__(self, parent, order_items, file_rows, db_manager, full_text=""):
        super().__init__(parent)
        self.title("Сопоставление строк из файла")
        self.geometry("1400x750")
        from dialogs.window_geometry import restore_geometry, track_geometry
        restore_geometry(self, "file_import_dialog", "1400x750")
        track_geometry(self, "file_import_dialog")
        self.resizable(True, True)
        self.db_manager = db_manager
        
        self.order_items = []
        for item in order_items:
            if hasattr(item, 'keys'):
                self.order_items.append(dict(item))
            else:
                self.order_items.append(item)
                
        self.file_rows = file_rows
        self.full_text = full_text
        self.matches = {}
        self.unmatched_file = []
        self.unmatched_order = []
        
        self.global_delivery_time = self._find_global_delivery_time()

        top_frame = ttk.LabelFrame(self, text="Сопоставленные строки", padding=8)
        top_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        cols = ("order_article", "order_name", "order_qty", "file_article", "file_name",
                "file_qty", "delivery_term", "delivery_unit", "price", "currency", "qty_match")
        self.tree = ttk.Treeview(top_frame, columns=cols, show="headings", height=12)
        
        headers_map = {
            "order_article": "Артикул (заказ)", "order_name": "Наименование (заказ)",
            "order_qty": "Кол-во (заказ)", "file_article": "Артикул (файл)",
            "file_name": "Наименование (файл)", "file_qty": "Кол-во (файл)",
            "delivery_term": "Срок", "delivery_unit": "Единица",
            "price": "Цена", "currency": "Валюта", "qty_match": "Совп."
        }
        for col_id, header_text in headers_map.items():
            self.tree.heading(col_id, text=header_text)
            
        widths = {"order_article": 130, "order_name": 220, "order_qty": 60, "file_article": 130,
                  "file_name": 220, "file_qty": 60, "delivery_term": 60, "delivery_unit": 110,
                  "price": 90, "currency": 70, "qty_match": 50}
        anchors = {"order_article": "w", "order_name": "w", "order_qty": "center", "file_article": "w",
                   "file_name": "w", "file_qty": "center", "delivery_term": "center", "delivery_unit": "w",
                   "price": "e", "currency": "center", "qty_match": "center"}
                   
        for col_id in cols:
            self.tree.column(col_id, width=widths.get(col_id, 100), anchor=anchors.get(col_id, "w"))

        scrollbar = ttk.Scrollbar(top_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.tag_configure('mismatch', background='#FFB6C1')

        bot_frame = ttk.Frame(self)
        bot_frame.pack(fill=tk.X, padx=10, pady=5)

        unmatched_order_frame = ttk.LabelFrame(bot_frame, text="Не сопоставлены в заказе", padding=5)
        unmatched_order_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        self.tree_unmatched_order = ttk.Treeview(unmatched_order_frame,
            columns=("article", "name", "qty"), show="headings", height=5)
        self.tree_unmatched_order.heading("article", text="Артикул")
        self.tree_unmatched_order.heading("name", text="Наименование")
        self.tree_unmatched_order.heading("qty", text="Кол-во")
        self.tree_unmatched_order.column("article", width=120)
        self.tree_unmatched_order.column("name", width=220)
        self.tree_unmatched_order.column("qty", width=60)
        self.tree_unmatched_order.pack(fill=tk.BOTH, expand=True)

        unmatched_file_frame = ttk.LabelFrame(bot_frame, text="Не сопоставлены в файле", padding=5)
        unmatched_file_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        self.tree_unmatched_file = ttk.Treeview(unmatched_file_frame,
            columns=("article", "name", "qty", "time", "price"), show="headings", height=5)
        self.tree_unmatched_file.heading("article", text="Артикул")
        self.tree_unmatched_file.heading("name", text="Наименование")
        self.tree_unmatched_file.heading("qty", text="Кол-во")
        self.tree_unmatched_file.heading("time", text="Срок (файл)")
        self.tree_unmatched_file.heading("price", text="Цена")
        self.tree_unmatched_file.column("article", width=120)
        self.tree_unmatched_file.column("name", width=220)
        self.tree_unmatched_file.column("qty", width=60)
        self.tree_unmatched_file.column("time", width=110)
        self.tree_unmatched_file.column("price", width=80)
        self.tree_unmatched_file.pack(fill=tk.BOTH, expand=True)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btn_frame, text="Авто-сопоставить", command=self.auto_match).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Применить сопоставления", command=self.apply).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self.destroy).pack(side=tk.RIGHT, padx=5)

        self._do_matching()
        self.grab_set()

    def _find_global_delivery_time(self):
        if not self.full_text:
            return None, None
        text = self.full_text.upper()
        patterns = [
            r'(\d+)\s*[-–]\s*(\d+)\s*(HAFTA|WEEK|НЕДЕЛЬ|WEEKS|GÜN|DAY|ДНЕЙ|DAYS|AY|MONTH|МЕСЯЦЕВ|MONTHS)',
            r'(\d+)\s*(HAFTA|WEEK|НЕДЕЛЬ|WEEKS|GÜN|DAY|ДНЕЙ|DAYS|AY|MONTH|МЕСЯЦЕВ|MONTHS)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                if match.lastindex == 3:
                    num1 = int(match.group(1))
                    num2 = int(match.group(2))
                    unit = match.group(3)
                    max_num = max(num1, num2)
                else:
                    max_num = int(match.group(1))
                    unit = match.group(2)
                translated_unit = translate_time_unit(unit)
                return max_num, translated_unit
        return None, None

    def _extract_article_from_name(self, name):
        """Извлекает артикул из наименования"""
        if not name:
            return ""
        name = str(name).strip()
        # Ищем числовые последовательности (артикулы обычно цифры)
        matches = re.findall(r'\b(\d{4,10})\b', name)
        if matches:
            return matches[0]
        # Ищем паттерны типа "DSBG-200-100"
        match = re.search(r'([A-Z]+)\s+([A-Z0-9]+[-][A-Z0-9\-]+(?:[-][A-Z0-9\-]+)*)', name)
        if match:
            return match.group(2)
        match = re.search(r'([A-Z0-9]+-[A-Z0-9\-]+)', name)
        if match:
            return match.group(1)
        return ""

    def _normalize_article(self, article):
        """Нормализует артикул для сравнения - убирает пробелы, приводит к верхнему регистру"""
        if not article:
            return ""
        return str(article).upper().replace(' ', '').replace('-', '').replace('_', '')

    def _parse_file_row(self, row):
        if not row or len(row) < 4:
            return None
        
        no = str(row[0]).strip() if len(row) > 0 else ""
        if not no or not no.isdigit():
            return None
        
        description = ""
        qty = ""
        unit_price = ""
        time_str = ""
        currency = ""
        article = ""
        
        # Определяем формат по содержимому второй колонки
        second_cell = str(row[1]).strip().upper() if len(row) > 1 else ""
        
        # Список известных брендов
        known_brands = ['HIWIN', 'FESTO', 'DESTACO', 'SMC', 'OMRON', 
                        'MITSUBISHI', 'SIEMENS', 'SCHNEIDER', 'ABB',
                        'BOSCH', 'REXROTH', 'PARKER', 'EATON', 'IGUS',
                        'CAMOZZI', 'SCHUNK', 'FANUC', 'YASKAWA']
        
        is_brand_format = second_cell in known_brands
        
        if is_brand_format and len(row) >= 7:
            # Формат HIWIN/FESTO: SN | Brand | Name | Quantity | Unit price | Total price | Lead time
            brand = str(row[1]).strip() if len(row) > 1 else ""
            description = str(row[2]).strip() if len(row) > 2 else ""
            qty = str(row[3]).strip() if len(row) > 3 else ""
            unit_price = str(row[4]).strip() if len(row) > 4 else ""
            time_str = str(row[6]).strip() if len(row) > 6 else ""
            article = self._extract_article_from_name(description)
            
            # Определяем валюту из заголовка цены или ячейки
            if len(row) > 4:
                price_cell = str(row[4]).strip().upper()
                if 'CNY' in price_cell or '￥' in price_cell or '¥' in price_cell:
                    currency = 'CNY'
                elif 'EUR' in price_cell or '€' in price_cell:
                    currency = 'EUR'
                elif 'USD' in price_cell or '$' in price_cell:
                    currency = 'USD'
        elif len(row) >= 7:
            # Турецкий формат: NO | Ürün Tanımı | Ölçü | Miktar | Birim | Birim Fiyat | Teslim Süresi | ...
            description = str(row[1]).strip() if len(row) > 1 else ""
            qty = str(row[3]).strip() if len(row) > 3 else ""
            unit_price = str(row[5]).strip() if len(row) > 5 else ""
            time_str = str(row[6]).strip() if len(row) > 6 else ""
            if not time_str and len(row) > 7:
                time_str = str(row[7]).strip()
            article = self._extract_article_from_name(description)
            
            # Валюта может быть в cells[6] или cells[5]
            if len(row) > 6:
                cell6 = str(row[6]).strip().upper()
                if cell6 in ['EUR', 'USD', 'CNY', 'RUB', 'TRY', 'TL']:
                    currency = cell6
        else:
            # Китайский формат (6 колонок): NO | Description | Unit | Qty | Unit Price | Total Price
            description = str(row[1]).strip() if len(row) > 1 else ""
            qty = str(row[3]).strip() if len(row) > 3 else ""
            unit_price = str(row[4]).strip() if len(row) > 4 else ""
            article = self._extract_article_from_name(description)
        
        # Парсим цену и валюту
        price = ""
        if unit_price:
            currency_match = re.search(r'(EUR|USD|CNY|RUB|TRY|TL)', unit_price.upper())
            if currency_match:
                currency = currency_match.group(1)
                price_part = unit_price[:currency_match.start()].strip()
                if parse_number(price_part) is not None:
                    price = price_part
            else:
                if '￥' in unit_price or '¥' in unit_price:
                    currency = 'CNY'
                    price_match = re.search(r'[￥¥]\s*([\d.,]+)', unit_price)
                    if price_match:
                        price = price_match.group(1)
                elif '€' in unit_price:
                    currency = 'EUR'
                    price_match = re.search(r'€\s*([\d.,]+)', unit_price)
                    if price_match:
                        price = price_match.group(1)
                elif '$' in unit_price:
                    currency = 'USD'
                    price_match = re.search(r'\$\s*([\d.,]+)', unit_price)
                    if price_match:
                        price = price_match.group(1)
                else:
                    if parse_number(unit_price) is not None:
                        price = unit_price
        
        # Если валюта не найдена, ищем в других ячейках
        if not currency:
            for cell in row:
                cell_str = str(cell).strip().upper()
                if cell_str in ['EUR', 'USD', 'CNY', 'RUB', 'TRY', 'TL']:
                    currency = cell_str
                    break
        
        delivery_num = None
        delivery_unit = None
        if time_str:
            delivery_num, delivery_unit = parse_delivery_time(time_str)
        
        return {
            'no': no,
            'name': description,
            'article': article,
            'qty': qty,
            'price': price,
            'currency': currency,
            'time': time_str,
            'delivery_num': delivery_num,
            'delivery_unit': delivery_unit,
        }
    def _normalize_text(self, text):
        if not text:
            return ""
        text = str(text).upper().strip()
        text = re.sub(r'[\s\-_]+', ' ', text)
        return text

    def _articles_match(self, art1, art2):
        if not art1 or not art2:
            return False
        art1_norm = self._normalize_text(art1)
        art2_norm = self._normalize_text(art2)
        if art1_norm == art2_norm:
            return True
        if art1_norm in art2_norm or art2_norm in art1_norm:
            return True
        # Нормализация без дефисов и пробелов
        art1_clean = art1_norm.replace('-', '').replace(' ', '').replace('_', '')
        art2_clean = art2_norm.replace('-', '').replace(' ', '').replace('_', '')
        if art1_clean == art2_clean:
            return True
        if art1_clean in art2_clean or art2_clean in art1_clean:
            if len(min(art1_clean, art2_clean, key=len)) >= 4:
                return True
        parts1 = set(re.split(r'[\s\-]+', art1_norm))
        parts2 = set(re.split(r'[\s\-]+', art2_norm))
        common = parts1 & parts2
        significant_common = [p for p in common if len(p) > 2]
        if len(significant_common) >= 2:
            return True
        return False

    def _names_match(self, name1, name2):
        """Улучшенное сравнение наименований"""
        if not name1 or not name2:
            return False
        
        name1_norm = self._normalize_text(name1)
        name2_norm = self._normalize_text(name2)
        
        # Точное совпадение
        if name1_norm == name2_norm:
            return True
        
        # Одно содержится в другом
        if name1_norm in name2_norm or name2_norm in name1_norm:
            return True
        
        # Разбиваем на слова и ищем общие значимые слова
        words1 = set(name1_norm.split())
        words2 = set(name2_norm.split())
        significant_words1 = {w for w in words1 if len(w) > 3}
        significant_words2 = {w for w in words2 if len(w) > 3}
        common = significant_words1 & significant_words2
        if len(common) >= 2:
            return True
        
        # Проверяем частичное совпадение слов
        for word in significant_words1:
            if any(word in w2 or w2 in word for w2 in significant_words2):
                return True
        
        return False

    def _article_in_name(self, article, name):
        """Проверяет, содержится ли артикул в наименовании"""
        if not article or not name:
            return False
        art_norm = self._normalize_text(article)
        name_norm = self._normalize_text(name)
        
        # Проверяем вхождение нормализованного артикула в наименование
        if art_norm in name_norm:
            return True
        
        # Проверяем вхождение очищенного артикула
        art_clean = self._normalize_article(article)
        name_clean = self._normalize_article(name)
        if art_clean in name_clean and len(art_clean) >= 6:
            return True
        
        return False

    def _do_matching(self):
        self.matches = {}
        self.unmatched_file = []
        self.unmatched_order = []
        parsed_rows = []
        
        for row in self.file_rows:
            parsed = self._parse_file_row(row)
            if parsed and (parsed['name'] or parsed['article'] or parsed['qty']):
                if parsed.get('delivery_num') is None and self.global_delivery_time[0]:
                    parsed['delivery_num'] = self.global_delivery_time[0]
                    parsed['delivery_unit'] = self.global_delivery_time[1]
                parsed_rows.append(parsed)
                
        file_used = set()
        
        for item in self.order_items:
            order_article = str(item.get('article', '') or '').strip()
            order_name = str(item.get('name', '') or '').strip()
            order_qty = item.get('quantity', 0)
            matched = False
            
            for idx, parsed in enumerate(parsed_rows):
                if idx in file_used:
                    continue
                    
                file_article = str(parsed.get('article', '') or '').strip()
                file_name = str(parsed.get('name', '') or '').strip()
                
                # 1. Точное совпадение артикулов
                if order_article and file_article:
                    if self._articles_match(order_article, file_article):
                        matched = True
                
                # 2. Артикул заказа содержится в наименовании файла
                if not matched and order_article and file_name:
                    order_art_norm = order_article.upper().replace(' ', '').replace('-', '').replace('_', '')
                    file_name_norm = file_name.upper().replace(' ', '').replace('-', '').replace('_', '')
                    if order_art_norm in file_name_norm and len(order_art_norm) >= 4:
                        matched = True
                
                # 3. Артикул файла содержится в наименовании заказа
                if not matched and file_article and order_name:
                    file_art_norm = file_article.upper().replace(' ', '').replace('-', '').replace('_', '')
                    order_name_norm = order_name.upper().replace(' ', '').replace('-', '').replace('_', '')
                    if file_art_norm in order_name_norm and len(file_art_norm) >= 4:
                        matched = True
                
                # 4. Сравнение наименований
                if not matched and order_name and file_name:
                    if self._names_match(order_name, file_name):
                        matched = True
                
                if matched:
                    file_qty = 0
                    if parsed.get('qty') and parsed['qty'].isdigit():
                        file_qty = int(parsed['qty'])
                        
                    qty_matches = (order_qty == file_qty) if file_qty > 0 else True
                    
                    self.matches[item['id']] = {
                        'parsed': parsed,
                        'qty_matches': qty_matches
                    }
                    file_used.add(idx)
                    break
                    
            if not matched:
                self.unmatched_order.append(item)
                
        for idx, parsed in enumerate(parsed_rows):
            if idx not in file_used:
                self.unmatched_file.append(parsed)
                
        self._refresh_trees()

    def _refresh_trees(self):
        for t in (self.tree, self.tree_unmatched_order, self.tree_unmatched_file):
            for it in t.get_children():
                t.delete(it)
                
        for item in self.order_items:
            if item['id'] in self.matches:
                match_data = self.matches[item['id']]
                m = match_data['parsed']
                delivery_term = m.get('delivery_num', '') or ''
                delivery_unit = m.get('delivery_unit', '') or ''
                qty_match = "✓" if match_data['qty_matches'] else "✗"
                tag = 'mismatch' if not match_data['qty_matches'] else ''
                
                item_id = self.tree.insert("", tk.END, values=(
                    item.get('article', ''),
                    item.get('name', ''),
                    item.get('quantity', ''),
                    m.get('article', ''),
                    m.get('name', ''),
                    m.get('qty', ''),
                    delivery_term,
                    delivery_unit,
                    m.get('price', ''),
                    m.get('currency', ''),
                    qty_match,
                ))
                if tag:
                    self.tree.item(item_id, tags=(tag,))
                    
        for item in self.unmatched_order:
            self.tree_unmatched_order.insert("", tk.END, values=(
                item.get('article', ''),
                item.get('name', ''),
                item.get('quantity', ''),
            ))
            
        for parsed in self.unmatched_file:
            self.tree_unmatched_file.insert("", tk.END, values=(
                parsed.get('article', ''),
                parsed.get('name', ''),
                parsed.get('qty', ''),
                parsed.get('time', ''),
                parsed.get('price', ''),
            ))

    def auto_match(self):
        self._do_matching()

    def apply(self):
        updated_count = 0
        for item in self.order_items:
            if item['id'] in self.matches:
                match_data = self.matches[item['id']]
                m = match_data['parsed']
                
                delivery_term = m.get('delivery_num', 0) or 0
                delivery_unit = m.get('delivery_unit', '') or ''
                price = m.get('price', '')
                currency = m.get('currency', '')
                qty = 0
                if m.get('qty') and m['qty'].isdigit():
                    qty = int(m['qty'])
                    
                self.db_manager.update_order_item(item['id'], {
                    'manufacturer': item.get('manufacturer', ''),
                    'subproject': item.get('subproject', ''),
                    'kd': item.get('kd', ''),
                    'article': m.get('article', '') or item.get('article', ''),
                    'name': item.get('name', ''),
                    'name_eng': item.get('name_eng', ''),
                    'quantity': qty if qty > 0 else item.get('quantity', 0),
                    'note': item.get('note', ''),
                    'delivery_term': delivery_term,
                    'delivery_unit': delivery_unit,
                    'price': price,
                    'currency': currency,
                })
                updated_count += 1
                
        messagebox.showinfo("Успех", f"Обновлено {updated_count} позиций из {len(self.matches)} сопоставленных")
        self.destroy()
