import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import openpyxl
import re
import os
from datetime import datetime

try:
    from deep_translator import GoogleTranslator
    HAS_TRANSLATOR = True
except ImportError:
    HAS_TRANSLATOR = False


# Расширенный локальный словарь для перевода технических терминов
TECH_DICT = {
    'пневмоцилиндр': 'pneumatic cylinder',
    'дроссель': 'throttle',
    'датчик': 'sensor',
    'штуцер': 'fitting',
    'рельс': 'rail',
    'каретка': 'carriage',
    'направляющая': 'guide',
    'магнитный датчик': 'magnetic sensor',
    'ручка': 'handle',
    'шайба': 'washer',
    'держатель': 'holder',
    'пружина': 'spring',
    'наконечник': 'tip',
    'втулка': 'bushing',
    'палец': 'pin',
    'штифт': 'dowel pin',
    'линейный вал': 'linear shaft',
    'мотор': 'motor',
    'редуктор': 'gearbox',
    'мотор-редуктор': 'gear motor',
    'зеркальное исполнение': 'mirror version',
    'конвейер': 'conveyor',
    'входной': 'input',
    'выходной': 'output',
    'втулка для штифта': 'locating pin bushing',
    'пневмоприжим': 'pneumatic clamp',
    'рычаг': 'lever',
    'прижим': 'clamp',
    'штифтовой пакет': 'dowel pin set',
    'устройство смены инструмента': 'tool changer',
    'магнитно-полевой датчик': 'magnetic field sensor',
    'кабель': 'cable',
    'головка шарнирная': 'spherical head',
    'стойка опорная': 'support stand',
    'фланец с осью': 'flange with axis',
    'фиксатор': 'fixator',
    'буфер': 'buffer',
    'пружинный упор': 'spring stop',
    'лапы': 'feet',
    'муфта гибкая': 'flexible coupling',
    'короб': 'box',
    'масленка': 'grease nipple',
    'эксцентрик': 'eccentric',
    'ловитель': 'catcher',
    'компенсатор': 'compensator',
    'гайки': 'nuts',
    'роликовое колесо': 'roller wheel',
    'электронный замок': 'electronic lock',
    'фронтальная часть с ручкой': 'front part with handle',
    'задние ручки': 'rear handles',
    'индуктивный датчик': 'inductive sensor',
    'индуктивный датчик приближения': 'inductive proximity sensor',
    'индуктивный датчик линейного положения': 'inductive linear position sensor',
    'ёмкостный датчик': 'capacitive sensor',
    'фотоэлектрический датчик': 'photoelectric sensor',
    'отражатель для фотоэлектрического барьера': 'reflector for photoelectric barrier',
    'защитная крышка датчика': 'sensor protective cover',
    'центральный процессор': 'central processor',
    'модуль селективности': 'selectivity module',
    'стабилизированный блок питания': 'stabilized power supply',
    'карта памяти': 'memory card',
    'модуль аналогового ввода': 'analog input module',
    'обжимная шайба': 'locking washer',
    'шайба с вырезом': 'washer with cutout',
    'пилька': 'saw blade',
    'дампфер': 'damper',
    'захват пневматический': 'pneumatic gripper',
    'адаптер фланца': 'flange adapter',
    'шок сенсор': 'shock sensor',
    'холдер': 'holder',
    'обжимная шайба с вырезом': 'locking washer with cutout',
}


def extract_misumi_article(name):
    """
    Извлекает артикул MISUMI из строки наименования.
    Возвращает (артикул, наименование_без_артикула).
    """
    if not name:
        return "", ""
    
    # Паттерн для артикула MISUMI: 2+ заглавных букв, затем буквы/цифры/дефисы/точки
    pattern = r'[A-Z]{2,}[A-Z0-9]*(?:[.\-][A-Z0-9]+)*'
    matches = list(re.finditer(pattern, name))
    
    if not matches:
        return "", name
    
    # Берем последнее совпадение (обычно это и есть артикул)
    last_match = matches[-1]
    article = last_match.group(0)
    
    # Проверяем, что артикул достаточно длинный (минимум 4 символа)
    if len(article) < 4:
        return "", name
    
    # Извлекаем наименование (всё до артикула)
    name_part = name[:last_match.start()].strip()
    name_part = name_part.rstrip(' -_,.')
    
    return article, name_part


def parse_filename(filepath):
    """
    Парсит имя файла для извлечения КД, подпроекта и производителя.
    Пример: 73.12(Узел установки кронштейнов)(FESTO).xlsx
    """
    filename = os.path.basename(filepath)
    name_without_ext = os.path.splitext(filename)[0]
    
    kd = ""
    subproject = ""
    manufacturer = ""
    
    # Ищем КД в начале (цифры с точкой)
    kd_match = re.match(r'^([\d.]+)', name_without_ext)
    if kd_match:
        kd = kd_match.group(1)
    
    # Ищем все скобки
    parts = re.findall(r'\(([^)]+)\)', name_without_ext)
    
    # Первая скобка - подпроект
    if parts:
        subproject = parts[0].strip()
    
    # Вторая скобка - производитель
    if len(parts) >= 2:
        manufacturer_raw = parts[1].strip().upper()
        if 'MISUMI' in manufacturer_raw:
            manufacturer = 'MISUMI'
        elif 'FESTO' in manufacturer_raw:
            manufacturer = 'FESTO'
        elif 'HIWIN' in manufacturer_raw:
            manufacturer = 'HIWIN'
        elif 'TURCK' in manufacturer_raw or 'TURK' in manufacturer_raw:
            manufacturer = 'TURCK'
        elif 'KIPP' in manufacturer_raw:
            manufacturer = 'KIPP'
        elif 'NORELEM' in manufacturer_raw:
            manufacturer = 'NORELEM'
        elif 'SIEMENS' in manufacturer_raw:
            manufacturer = 'Siemens'
        elif 'Blickle' in parts[1] or 'blickle' in parts[1].lower():
            manufacturer = 'Blickle'
        elif 'SICK' in manufacturer_raw:
            manufacturer = 'SICK'
        elif 'IFM' in manufacturer_raw:
            manufacturer = 'IFM'
    
    return kd, subproject, manufacturer


def translate_name_local(name_rus):
    """Перевод наименования на английский с использованием локального словаря"""
    if not name_rus:
        return ""
    
    result = name_rus
    # Сортируем по длине ключа (от длинного к короткому), чтобы сначала заменять длинные фразы
    sorted_keys = sorted(TECH_DICT.keys(), key=len, reverse=True)
    
    for ru_term in sorted_keys:
        en_term = TECH_DICT[ru_term]
        # Используем регулярное выражение для замены с учетом регистра
        pattern = re.compile(re.escape(ru_term), re.IGNORECASE)
        result = pattern.sub(en_term, result)
    
    return result


def is_header_row(row_values):
    """Проверяет, является ли строка заголовком таблицы"""
    if not row_values:
        return False
    
    # Приводим все значения к строкам и в нижний регистр
    row_str = [str(v).strip().lower() if v else '' for v in row_values]
    
    # Проверяем типичные заголовки
    header_keywords = ['№', 'номер', 'наименование', 'name', 'количество', 'qty', 'кол', 'примечание', 'note']
    
    matches = 0
    for cell in row_str:
        for keyword in header_keywords:
            if keyword in cell:
                matches += 1
                break
    
    # Если найдено 2+ совпадений с ключевыми словами заголовка
    return matches >= 2


class ImportFileDialog(tk.Toplevel):
    def __init__(self, parent, db_manager):
        super().__init__(parent)
        self.title("Импорт из файла")
        self.geometry("1200x800")
        self.resizable(True, True)
        self.db_manager = db_manager
        self.file_data = []
        self.import_data = []
        self.file_path = ""
        self._force_close = False  # Флаг принудительного закрытия
        
        self.create_widgets()
        self.grab_set()
        
        # Перехватываем закрытие окна
        self.protocol("WM_DELETE_WINDOW", self._on_closing)
    
    def _on_closing(self):
        """Обработчик закрытия окна"""
        # Если есть данные для импорта, спрашиваем подтверждение
        if self.import_data and not self._force_close:
            result = messagebox.askyesnocancel(
                "Данные не перенесены",
                f"В таблице 'Данные для импорта' есть {len(self.import_data)} строк(и).\n\n"
                "Перенести данные в закупки перед закрытием?"
            )
            
            if result is None:  # Нажата кнопка "Отмена"
                return  # Не закрываем окно
            elif result:  # Нажата кнопка "Да"
                # Переносим данные в закупки
                self._force_close = True
                self.transfer_to_purchases()
                return
            else:  # Нажата кнопка "Нет" - закрываем без сохранения
                self._force_close = True
                self.destroy()
        else:
            # Нет данных или принудительное закрытие
            self.destroy()
    
    def create_widgets(self):
        # Кнопка выбора файла и кнопки действий
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(btn_frame, text="Выбрать файл", command=self.select_file).pack(side=tk.LEFT, padx=5)
        self.lbl_file = ttk.Label(btn_frame, text="Файл не выбран")
        self.lbl_file.pack(side=tk.LEFT, padx=10)
        
        # Кнопки справа: "В Закупки" слева, "Перенести данные" справа
        ttk.Button(btn_frame, text="В Закупки", command=self.transfer_to_purchases).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Перенести данные", command=self.show_transfer_dialog).pack(side=tk.RIGHT, padx=5)
        
        # Таблица данных из файла
        file_frame = ttk.LabelFrame(self, text="Данные из файла", padding=5)
        file_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        cols_file = ("num", "name", "qty", "note")
        self.tree_file = ttk.Treeview(file_frame, columns=cols_file, show="headings", height=15)
        self.tree_file.heading("num", text="№")
        self.tree_file.heading("name", text="Наименование")
        self.tree_file.heading("qty", text="Количество")
        self.tree_file.heading("note", text="Примечание")
        self.tree_file.column("num", width=50, anchor="center")
        self.tree_file.column("name", width=600, anchor="w")
        self.tree_file.column("qty", width=80, anchor="center")
        self.tree_file.column("note", width=200, anchor="w")
        
        sb_file = ttk.Scrollbar(file_frame, orient=tk.VERTICAL, command=self.tree_file.yview)
        self.tree_file.configure(yscroll=sb_file.set)
        self.tree_file.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_file.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Таблица данных для импорта
        import_frame = ttk.LabelFrame(self, text="Данные для импорта", padding=5)
        import_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        cols_import = ("num", "manufacturer", "subproject", "kd", "article", "name_rus", "name_eng", "qty", "note")
        self.tree_import = ttk.Treeview(import_frame, columns=cols_import, show="headings", height=15)
        self.tree_import.heading("num", text="№")
        self.tree_import.heading("manufacturer", text="Производитель")
        self.tree_import.heading("subproject", text="Подпроект")
        self.tree_import.heading("kd", text="КД")
        self.tree_import.heading("article", text="Артикул")
        self.tree_import.heading("name_rus", text="Наименование (рус)")
        self.tree_import.heading("name_eng", text="Наименование (анг)")
        self.tree_import.heading("qty", text="Количество")
        self.tree_import.heading("note", text="Примечание")
        
        for col in cols_import:
            if col == "num":
                self.tree_import.column(col, width=50, anchor="center")
            elif col in ("manufacturer", "subproject", "kd"):
                self.tree_import.column(col, width=120, anchor="w")
            elif col == "article":
                self.tree_import.column(col, width=120, anchor="w")
            elif col in ("name_rus", "name_eng"):
                self.tree_import.column(col, width=250, anchor="w")
            elif col == "qty":
                self.tree_import.column(col, width=70, anchor="center")
            else:
                self.tree_import.column(col, width=150, anchor="w")
        
        sb_import = ttk.Scrollbar(import_frame, orient=tk.VERTICAL, command=self.tree_import.yview)
        self.tree_import.configure(yscroll=sb_import.set)
        self.tree_import.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_import.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree_import.bind("<Double-1>", lambda e: self.edit_import_item())
    
    def select_file(self):
        filepath = filedialog.askopenfilename(
            title="Выберите Excel файл",
            filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")]
        )
        if not filepath:
            return
        
        self.file_path = filepath
        self.lbl_file.config(text=filepath)
        self.load_file_data(filepath)
        
        # Поднимаем окно на передний план после выбора файла
        self.lift()
        self.focus_force()
        self.attributes('-topmost', True)
        self.after(100, lambda: self.attributes('-topmost', False))
    
    def load_file_data(self, filepath):
        """Загрузка данных из файла с обработкой повторяющихся заголовков"""
        for item in self.tree_file.get_children():
            self.tree_file.delete(item)
        
        self.file_data = []
        
        try:
            wb = openpyxl.load_workbook(filepath, data_only=True)
            ws = wb.active
            
            # Читаем первую строку для определения заголовков
            first_row = None
            for row in ws.iter_rows(min_row=1, max_row=1, values_only=True):
                first_row = row
                break
            
            # Определяем индексы колонок по заголовкам
            num_idx = None
            name_idx = None
            qty_idx = None
            note_idx = None
            
            if first_row:
                headers = [str(h).strip().lower() if h else '' for h in first_row]
                
                for i, h in enumerate(headers):
                    if '№' in h or 'номер' in h or 'num' in h:
                        num_idx = i
                    elif 'наименование' in h or 'name' in h or 'описание' in h:
                        name_idx = i
                    elif 'количество' in h or 'qty' in h or 'кол' in h:
                        qty_idx = i
                    elif 'примечание' in h or 'note' in h:
                        note_idx = i
            
            # Если не нашли по заголовкам, используем стандартные позиции
            if name_idx is None:
                name_idx = 0
            if qty_idx is None:
                qty_idx = 2
            if note_idx is None:
                note_idx = 3
            
            # Читаем все строки, пропуская заголовки
            row_num = 0
            for row in ws.iter_rows(min_row=1, values_only=True):
                # Пропускаем строки-заголовки (повторяющиеся)
                if is_header_row(row):
                    # Обновляем индексы колонок если заголовок изменился
                    if row:
                        headers = [str(h).strip().lower() if h else '' for h in row]
                        for i, h in enumerate(headers):
                            if '№' in h or 'номер' in h or 'num' in h:
                                num_idx = i
                            elif 'наименование' in h or 'name' in h or 'описание' in h:
                                name_idx = i
                            elif 'количество' in h or 'qty' in h or 'кол' in h:
                                qty_idx = i
                            elif 'примечание' in h or 'note' in h:
                                note_idx = i
                    continue
                
                # Пропускаем пустые строки
                if not row or all(cell is None or str(cell).strip() == '' for cell in row):
                    continue
                
                # Проверяем, что есть хотя бы наименование или номер
                name_val = row[name_idx] if name_idx < len(row) else None
                num_val = row[num_idx] if num_idx is not None and num_idx < len(row) else None
                
                if not name_val and not num_val:
                    continue
                
                # Проверяем, что наименование не пустое
                name_str = str(name_val).strip() if name_val else ""
                if not name_str:
                    continue
                
                row_num += 1
                num = str(num_val).strip() if num_val else str(row_num)
                qty = row[qty_idx] if qty_idx < len(row) else ""
                note = row[note_idx] if note_idx is not None and note_idx < len(row) else ""
                
                self.tree_file.insert("", tk.END, values=(num, name_str, qty or "", note or ""))
                self.file_data.append({
                    'num': num,
                    'name': name_str,
                    'qty': qty if qty else "",
                    'note': str(note) if note else ""
                })
                
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось прочитать файл:\n{e}")
            import traceback
            traceback.print_exc()
    
    def show_transfer_dialog(self):
        if not self.file_data:
            messagebox.showwarning("Внимание", "Сначала выберите файл!")
            return
        
        kd, subproject, manufacturer = parse_filename(self.file_path)
        
        dialog = TransferSettingsDialog(self, self.db_manager, self.file_data, 
                                        default_kd=kd, default_subproject=subproject, 
                                        default_manufacturer=manufacturer)
        self.wait_window(dialog)
        
        if dialog.result:
            self.import_data = dialog.result
            self.update_import_table()
    
    def update_import_table(self):
        for item in self.tree_import.get_children():
            self.tree_import.delete(item)
        
        for idx, item in enumerate(self.import_data, 1):
            self.tree_import.insert("", tk.END, values=(
                idx,
                item.get('manufacturer', ''),
                item.get('subproject', ''),
                item.get('kd', ''),
                item.get('article', ''),
                item.get('name_rus', ''),
                item.get('name_eng', ''),
                item.get('qty', ''),
                item.get('note', '')
            ))
    
    def edit_import_item(self):
        selected = self.tree_import.selection()
        if not selected:
            return
        
        idx = self.tree_import.index(selected[0])
        if idx >= len(self.import_data):
            return
        
        item = self.import_data[idx]
        dialog = ImportItemEditDialog(self, item, self.db_manager)
        self.wait_window(dialog)
        
        if dialog.result:
            self.import_data[idx] = dialog.result
            self.update_import_table()
    
    def transfer_to_purchases(self):
        """Перенос данных в закупки"""
        if not self.import_data:
            messagebox.showwarning("Внимание", "Нет данных для переноса!")
            return
        
        # Возвращаем данные в главное окно для переноса в закупки
        self.result = self.import_data
        self._force_close = True
        self.destroy()


class TransferSettingsDialog(tk.Toplevel):
    def __init__(self, parent, db_manager, file_data, default_kd="", default_subproject="", default_manufacturer=""):
        super().__init__(parent)
        self.title("Настройки переноса")
        self.geometry("500x300")
        self.resizable(False, False)
        self.db_manager = db_manager
        self.file_data = file_data
        self.result = None
        
        self.default_kd = default_kd
        self.default_subproject = default_subproject
        self.default_manufacturer = default_manufacturer
        
        self.create_widgets()
        self.grab_set()
    
    def create_widgets(self):
        ttk.Label(self, text="Производитель:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.combo_manufacturer = ttk.Combobox(self, width=40, state="readonly")
        self.combo_manufacturer.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        self.load_manufacturers()
        
        ttk.Label(self, text="Подпроект:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.combo_subproject = ttk.Combobox(self, width=40, state="readonly")
        self.combo_subproject.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        self.load_subprojects()
        
        ttk.Label(self, text="КД:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        self.combo_kd = ttk.Combobox(self, width=40, state="readonly")
        self.combo_kd.grid(row=2, column=1, sticky="ew", padx=10, pady=5)
        self.load_kd()
        
        self.grid_columnconfigure(1, weight=1)
        
        if self.default_manufacturer:
            self.combo_manufacturer.set(self.default_manufacturer)
        if self.default_subproject:
            self.combo_subproject.set(self.default_subproject)
        if self.default_kd:
            self.combo_kd.set(self.default_kd)
        
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frame, text="OK", command=self.ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self.destroy).pack(side=tk.LEFT, padx=5)
    
    def load_manufacturers(self):
        manufacturers = self.db_manager.get_manufacturers()
        self.combo_manufacturer['values'] = [m['name'] for m in manufacturers]
    
    def load_subprojects(self):
        subprojects = self.db_manager.get_subprojects()
        self.combo_subproject['values'] = [s['name'] for s in subprojects]
    
    def load_kd(self):
        kd_list = self.db_manager.get_kd_directory()
        self.combo_kd['values'] = [k['kd_number'] for k in kd_list]
    
    def ok(self):
        manufacturer = self.combo_manufacturer.get()
        subproject = self.combo_subproject.get()
        kd = self.combo_kd.get()
        
        if not manufacturer:
            messagebox.showwarning("Внимание", "Выберите производителя!")
            return
        
        result = []
        for item in self.file_data:
            if not item['name']:
                continue
            
            processed = self.process_item(item, manufacturer, subproject, kd)
            if processed:
                result.append(processed)
        
        if not result:
            messagebox.showwarning("Внимание", "Не удалось обработать ни одну позицию!")
            return
        
        self.result = result
        self.destroy()
    
    def process_item(self, item, manufacturer, subproject, kd):
        """Обработка позиции с извлечением артикула по правилам производителя"""
        name = item['name']
        qty = item['qty']
        note = item['note']
        
        name_upper = name.upper()
        manufacturer_upper = manufacturer.upper()
        
        article = ""
        name_rus = name
        
        if manufacturer_upper == 'MISUMI':
            article, name_rus = extract_misumi_article(name)
            
        elif manufacturer_upper == 'FESTO':
            # Для FESTO артикул ВСЕГДА цифровой (6+ цифр)
            # Примеры:
            # "Пневмоцилиндр 1463495 DSBC-80-160-PPVA" → артикул: 1463495
            # "Дроссель 193144_GRLA-1_8-QS-6-D" → артикул: 193144
            # "Датчик 543863_SME-8M-DS-24V-K-50-OE" → артикул: 543863
            match = re.search(r'(\d{6,})', name)
            if match:
                article = match.group(1)
                # Убираем артикул из наименования
                name_rus = name[:match.start()] + name[match.end():]
                # Заменяем подчёркивания на пробелы и чистим
                name_rus = name_rus.replace('_', ' ')
                name_rus = re.sub(r'\s+', ' ', name_rus).strip()
                name_rus = name_rus.strip(' -_,.')
                # Убираем название производителя из наименования
                name_rus = re.sub(r'\bFESTO\b', '', name_rus, flags=re.IGNORECASE).strip()
                name_rus = re.sub(r'\s+', ' ', name_rus).strip()
            else:
                article = ""
                name_rus = name
                
        elif manufacturer_upper == 'HIWIN':
            # Для HIWIN артикул буквенно-цифровой, например RGR30R1400H
            match = re.search(r'([A-Z]{2,}\d+[A-Z0-9]*)', name)
            if match:
                article = match.group(1)
                name_rus = name[:match.start()] + name[match.end():]
                name_rus = name_rus.strip(' -_,.')
                name_rus = re.sub(r'\s+', ' ', name_rus).strip()
                name_rus = re.sub(r'\bHIWIN\b', '', name_rus, flags=re.IGNORECASE).strip()
                name_rus = re.sub(r'\s+', ' ', name_rus).strip()
            else:
                article = ""
                name_rus = name
                
        elif manufacturer_upper in ('TURCK', 'TURK'):
            # Для TURCK артикул буквенно-цифровой с дефисами и точками
            # Пример: WIM45-UNTL-LIU5X2-0.3-RS4
            match = re.search(r'([A-Z]{2,}[\d\-A-Z\.]+)', name)
            if match:
                article = match.group(1)
                name_rus = name[:match.start()] + name[match.end():]
                name_rus = name_rus.strip(' -_,.')
                name_rus = re.sub(r'\s+', ' ', name_rus).strip()
                name_rus = re.sub(r'\bTURCK\b', '', name_rus, flags=re.IGNORECASE).strip()
                name_rus = re.sub(r'\s+', ' ', name_rus).strip()
            else:
                article = ""
                name_rus = name
                
        elif manufacturer_upper == 'KIPP':
            # Для KIPP артикул формата XXXXX-XXXXX (цифры-цифры)
            # Пример: 06914-140081
            match = re.search(r'(\d{5,}-\d+)', name)
            if match:
                article = match.group(1)
                name_rus = name[:match.start()] + name[match.end():]
                name_rus = name_rus.strip(' -_,.')
                name_rus = re.sub(r'\s+', ' ', name_rus).strip()
                name_rus = re.sub(r'\bKIPP\b', '', name_rus, flags=re.IGNORECASE).strip()
                name_rus = re.sub(r'\s+', ' ', name_rus).strip()
            else:
                article = ""
                name_rus = name
                
        elif manufacturer_upper == 'NORELEM':
            # Для NORELEM артикул формата XXXXX-XXXXX (цифры-цифры)
            # Пример: 02028-206012
            match = re.search(r'^(\d{5,}-\d+)', name)
            if match:
                article = match.group(1)
                name_rus = name[match.end():]
                name_rus = name_rus.strip(' -_,.')
                name_rus = re.sub(r'\s+', ' ', name_rus).strip()
                name_rus = re.sub(r'\bNORELEM\b', '', name_rus, flags=re.IGNORECASE).strip()
                name_rus = re.sub(r'\s+', ' ', name_rus).strip()
            else:
                article = ""
                name_rus = name
                
        elif manufacturer_upper == 'SICK':
            # Для SICK артикул в скобках или буквенно-цифровой
            match = re.search(r'\(([A-Z0-9\-]+)\)', name)
            if match:
                article = match.group(1)
                name_rus = name[:match.start()] + name[match.end():]
                name_rus = name_rus.strip(' -_,.')
                name_rus = re.sub(r'\s+', ' ', name_rus).strip()
            else:
                match = re.search(r'([A-Z]{2,}\d+[\-A-Z0-9]*)', name)
                if match:
                    article = match.group(1)
                    name_rus = name[:match.start()] + name[match.end():]
                    name_rus = name_rus.strip(' -_,.')
                    name_rus = re.sub(r'\s+', ' ', name_rus).strip()
                else:
                    article = ""
                    name_rus = name
                    
        elif manufacturer_upper == 'IFM':
            # Для IFM артикул буквенно-цифровой, например E20005, IE5338
            match = re.search(r'([A-Z]\d{4,})', name)
            if match:
                article = match.group(1)
                name_rus = name[:match.start()] + name[match.end():]
                name_rus = name_rus.strip(' -_,.')
                name_rus = re.sub(r'\s+', ' ', name_rus).strip()
                name_rus = re.sub(r'\bIFM\b', '', name_rus, flags=re.IGNORECASE).strip()
                name_rus = re.sub(r'\s+', ' ', name_rus).strip()
            else:
                article = ""
                name_rus = name
                
        elif manufacturer_upper == 'SIEMENS':
            # Для Siemens артикул длинный буквенно-цифровой с дефисами
            # Пример: 6ES7516-3FN02-0AB0
            match = re.search(r'(\d[A-Z0-9]{4,}(?:\-[A-Z0-9]+)+)', name)
            if match:
                article = match.group(1)
                name_rus = name[:match.start()] + name[match.end():]
                name_rus = name_rus.strip(' -_,.')
                name_rus = re.sub(r'\s+', ' ', name_rus).strip()
                name_rus = re.sub(r'\bSIEMENS\b', '', name_rus, flags=re.IGNORECASE).strip()
                name_rus = re.sub(r'\s+', ' ', name_rus).strip()
            else:
                article = ""
                name_rus = name
                
        elif manufacturer_upper == 'BLICKLE':
            # Для Blickle артикул буквенно-цифровой, например SPO 75/15K
            match = re.search(r'([A-Z]{2,}\s*\d+[\dA-Z\/\-]*)', name)
            if match:
                article = match.group(1).strip()
                name_rus = name[:match.start()] + name[match.end():]
                name_rus = name_rus.strip(' -_,.')
                name_rus = re.sub(r'\s+', ' ', name_rus).strip()
                name_rus = re.sub(r'\bBLICKLE\b', '', name_rus, flags=re.IGNORECASE).strip()
                name_rus = re.sub(r'\s+', ' ', name_rus).strip()
            else:
                article = ""
                name_rus = name
        else:
            # Универсальный поиск - ищем цифровой артикул 4+ цифр
            match = re.search(r'(\d{4,})', name)
            if match:
                article = match.group(1)
                name_rus = name[:match.start()] + name[match.end():]
                name_rus = name_rus.strip(' -_,.')
                name_rus = re.sub(r'\s+', ' ', name_rus).strip()
            else:
                article = ""
                name_rus = name
        
        # Перевод на английский
        name_eng = self.translate_name(name_rus)
        
        return {
            'manufacturer': manufacturer,
            'subproject': subproject,
            'kd': kd,
            'article': article,
            'name_rus': name_rus,
            'name_eng': name_eng,
            'qty': qty,
            'note': note
        }
    
    def translate_name(self, name_rus):
        """Перевод наименования на английский"""
        if not name_rus:
            return ""
        
        # Сначала пробуем через Google Translate
        if HAS_TRANSLATOR:
            try:
                translator = GoogleTranslator(source='ru', target='en')
                translated = translator.translate(name_rus)
                if translated and translated != name_rus:
                    return translated
            except Exception as e:
                print(f"Google Translate error: {e}")
        
        # Если Google Translate не сработал, используем локальный словарь
        return translate_name_local(name_rus)


class ImportItemEditDialog(tk.Toplevel):
    def __init__(self, parent, item_data, db_manager):
        super().__init__(parent)
        self.title("Редактировать позицию")
        self.geometry("700x400")
        self.resizable(False, False)
        self.db_manager = db_manager
        self.result = None
        
        self.create_widgets(item_data)
        self.grab_set()
    
    def create_widgets(self, item_data):
        ttk.Label(self, text="Производитель:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.combo_manufacturer = ttk.Combobox(self, width=40)
        self.combo_manufacturer.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        self.load_manufacturers()
        self.combo_manufacturer.set(item_data.get('manufacturer', ''))
        
        ttk.Label(self, text="Подпроект:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.combo_subproject = ttk.Combobox(self, width=40)
        self.combo_subproject.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        self.load_subprojects()
        self.combo_subproject.set(item_data.get('subproject', ''))
        
        ttk.Label(self, text="КД:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        self.combo_kd = ttk.Combobox(self, width=40)
        self.combo_kd.grid(row=2, column=1, sticky="ew", padx=10, pady=5)
        self.load_kd()
        self.combo_kd.set(item_data.get('kd', ''))
        
        ttk.Label(self, text="Артикул:").grid(row=3, column=0, sticky="w", padx=10, pady=5)
        self.entry_article = ttk.Entry(self, width=50)
        self.entry_article.grid(row=3, column=1, sticky="ew", padx=10, pady=5)
        self.entry_article.insert(0, item_data.get('article', ''))
        
        ttk.Label(self, text="Наименование (рус):").grid(row=4, column=0, sticky="w", padx=10, pady=5)
        self.entry_name_rus = ttk.Entry(self, width=50)
        self.entry_name_rus.grid(row=4, column=1, sticky="ew", padx=10, pady=5)
        self.entry_name_rus.insert(0, item_data.get('name_rus', ''))
        
        ttk.Label(self, text="Наименование (анг):").grid(row=5, column=0, sticky="w", padx=10, pady=5)
        self.entry_name_eng = ttk.Entry(self, width=50)
        self.entry_name_eng.grid(row=5, column=1, sticky="ew", padx=10, pady=5)
        self.entry_name_eng.insert(0, item_data.get('name_eng', ''))
        
        ttk.Label(self, text="Количество:").grid(row=6, column=0, sticky="w", padx=10, pady=5)
        self.entry_qty = ttk.Entry(self, width=20)
        self.entry_qty.grid(row=6, column=1, sticky="w", padx=10, pady=5)
        self.entry_qty.insert(0, str(item_data.get('qty', '')))
        
        ttk.Label(self, text="Примечание:").grid(row=7, column=0, sticky="w", padx=10, pady=5)
        self.entry_note = ttk.Entry(self, width=50)
        self.entry_note.grid(row=7, column=1, sticky="ew", padx=10, pady=5)
        self.entry_note.insert(0, item_data.get('note', ''))
        
        self.grid_columnconfigure(1, weight=1)
        
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=8, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frame, text="Сохранить", command=self.save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self.destroy).pack(side=tk.LEFT, padx=5)
    
    def load_manufacturers(self):
        manufacturers = self.db_manager.get_manufacturers()
        self.combo_manufacturer['values'] = [m['name'] for m in manufacturers]
    
    def load_subprojects(self):
        subprojects = self.db_manager.get_subprojects()
        self.combo_subproject['values'] = [s['name'] for s in subprojects]
    
    def load_kd(self):
        kd_list = self.db_manager.get_kd_directory()
        self.combo_kd['values'] = [k['kd_number'] for k in kd_list]
    
    def save(self):
        try:
            qty = int(self.entry_qty.get()) if self.entry_qty.get() else 0
        except:
            messagebox.showwarning("Ошибка", "Некорректное количество!")
            return
        
        self.result = {
            'manufacturer': self.combo_manufacturer.get(),
            'subproject': self.combo_subproject.get(),
            'kd': self.combo_kd.get(),
            'article': self.entry_article.get(),
            'name_rus': self.entry_name_rus.get(),
            'name_eng': self.entry_name_eng.get(),
            'qty': qty,
            'note': self.entry_note.get()
        }
        self.destroy()