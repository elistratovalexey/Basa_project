import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    from docx import Document
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False


class SpecImportDialog(tk.Toplevel):
    def __init__(self, parent, db_manager, project_name):
        super().__init__(parent)
        self.title("Импорт в Спецификацию закупок")
        self.geometry("700x400")
        self.db_manager = db_manager
        self.project_name = project_name
        self.imported_items = []
        
        ttk.Label(self, text="Выберите файл (PDF, Excel, Word):").pack(pady=10)
        
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(btn_frame, text="Выбрать файл", command=self.select_file).pack(side=tk.LEFT, padx=5)
        self.lbl_file = ttk.Label(btn_frame, text="Файл не выбран")
        self.lbl_file.pack(side=tk.LEFT, padx=10)
        
        # Таблица предпросмотра
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        cols = ("supplier", "name", "quantity", "price", "currency", "total", "delivery_term")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=12)
        self.tree.heading("supplier", text="Поставщик")
        self.tree.heading("name", text="Наименование")
        self.tree.heading("quantity", text="Кол-во")
        self.tree.heading("price", text="Цена")
        self.tree.heading("currency", text="Валюта")
        self.tree.heading("total", text="Сумма")
        self.tree.heading("delivery_term", text="Срок")
        
        for col in cols:
            self.tree.column(col, width=100, anchor="w")
        
        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Кнопки
        btn_frame2 = ttk.Frame(self)
        btn_frame2.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(btn_frame2, text="Импортировать", command=self.do_import).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame2, text="Отмена", command=self.destroy).pack(side=tk.RIGHT, padx=5)
        
        self.grab_set()
    
    def select_file(self):
        filepath = filedialog.askopenfilename(
            title="Выберите файл",
            filetypes=[("Все поддерживаемые", "*.pdf *.xlsx *.xls *.docx"),
                       ("PDF", "*.pdf"), ("Excel", "*.xlsx *.xls"), ("Word", "*.docx")])
        if not filepath:
            return
        
        self.lbl_file.config(text=filepath)
        self.parse_file(filepath)
    
    def parse_file(self, filepath):
        self.imported_items = []
        ext = os.path.splitext(filepath)[1].lower()
        
        try:
            if ext in ('.xlsx', '.xls') and HAS_OPENPYXL:
                self.parse_excel(filepath)
            elif ext == '.pdf' and HAS_PDFPLUMBER:
                self.parse_pdf(filepath)
            elif ext == '.docx' and HAS_DOCX:
                self.parse_docx(filepath)
            else:
                messagebox.showerror("Ошибка", f"Не удалось прочитать файл формата {ext}")
                return
        except Exception as e:
            messagebox.showerror("Ошибка парсинга", f"{e}")
            return
        
        self.show_preview()
    
    def parse_excel(self, filepath):
        wb = openpyxl.load_workbook(filepath, data_only=True)
        ws = wb.active
        
        # Пропускаем заголовки
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row and any(cell is not None for cell in row):
                try:
                    # Пытаемся распарсить числа, игнорируя ошибки
                    quantity = 0
                    price = 0
                    total = 0
                    
                    if row[2]:
                        try:
                            quantity = float(str(row[2]).replace(',', '.').replace(' ', ''))
                        except:
                            quantity = 0
                    
                    if row[3]:
                        try:
                            price = float(str(row[3]).replace(',', '.').replace(' ', ''))
                        except:
                            price = 0
                    
                    if row[5]:
                        try:
                            total = float(str(row[5]).replace(',', '.').replace(' ', ''))
                        except:
                            total = 0
                    
                    self.imported_items.append({
                        'supplier': str(row[0] or ''),
                        'name': str(row[1] or ''),
                        'quantity': quantity,
                        'price': price,
                        'currency': str(row[4] or 'RUB'),
                        'total': total,
                        'delivery_term': str(row[6] or ''),
                    })
                except Exception as e:
                    print(f"Пропущена строка: {e}")
                    continue

    def parse_pdf(self, filepath):
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table[1:]:  # пропуск заголовка
                        if row and any(cell for cell in row):
                            self.imported_items.append({
                                'supplier': str(row[0] or ''),
                                'name': str(row[1] or ''),
                                'quantity': float(row[2] or 0) if row[2] else 0,
                                'price': float(row[3] or 0) if row[3] else 0,
                                'currency': 'RUB',
                                'total': float(row[4] or 0) if row[4] else 0,
                                'delivery_term': str(row[5] or ''),
                            })
    
    def parse_docx(self, filepath):
        doc = Document(filepath)
        for table in doc.tables:
            for i, row in enumerate(table.rows):
                if i == 0:
                    continue
                cells = [cell.text.strip() for cell in row.cells]
                if len(cells) >= 5 and any(cells):
                    self.imported_items.append({
                        'supplier': cells[0] if len(cells) > 0 else '',
                        'name': cells[1] if len(cells) > 1 else '',
                        'quantity': float(cells[2]) if len(cells) > 2 and cells[2] else 0,
                        'price': float(cells[3]) if len(cells) > 3 and cells[3] else 0,
                        'currency': cells[4] if len(cells) > 4 else 'RUB',
                        'total': float(cells[5]) if len(cells) > 5 and cells[5] else 0,
                        'delivery_term': cells[6] if len(cells) > 6 else '',
                    })
    
    def show_preview(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for item in self.imported_items:
            self.tree.insert("", tk.END, values=(
                item.get('supplier', ''), item.get('name', ''),
                item.get('quantity', 0), item.get('price', 0),
                item.get('currency', 'RUB'), item.get('total', 0),
                item.get('delivery_term', '')
            ))
    
    def do_import(self):
        if not self.imported_items:
            messagebox.showwarning("Внимание", "Нет данных для импорта!")
            return
        
        project_id = self.db_manager.get_project_id(self.project_name)
        if not project_id:
            messagebox.showerror("Ошибка", "Проект не найден!")
            return
        
        count = 0
        for item in self.imported_items:
            self.db_manager.add_purchase_spec(project_id, {
                'supplier': item.get('supplier', ''),
                'name': item.get('name', ''),
                'quantity': item.get('quantity', 0),
                'price': item.get('price', 0),
                'total': item.get('total', 0),
                'currency': item.get('currency', 'RUB'),
                'delivery_term': item.get('delivery_term', ''),
                'delivery_unit': 'Календарные дни',
                'payment_date': '',
                'delivery_date': '',
                'fully_paid': 0,
                'received': 0,
                'note': '',
            })
            count += 1
        
        messagebox.showinfo("Успех", f"Импортировано {count} позиций!")
        self.destroy()