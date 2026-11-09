import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
from datetime import datetime

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False


class OrderExportDialog(tk.Toplevel):
    def __init__(self, parent, db_manager):
        super().__init__(parent)
        self.title("Экспорт заказов в Excel")
        self.geometry("600x400")
        self.resizable(False, False)
        self.db_manager = db_manager
        self.result = None

        ttk.Label(self, text="Экспорт заказов в Excel",
                  font=("Arial", 12, "bold")).pack(pady=10)

        proj_frame = ttk.Frame(self)
        proj_frame.pack(fill=tk.X, padx=20, pady=5)
        ttk.Label(proj_frame, text="Проект:").pack(side=tk.LEFT, padx=(0, 10))
        self.combo_project = ttk.Combobox(proj_frame, width=30, state="readonly")
        self.combo_project.pack(side=tk.LEFT, fill=tk.X, expand=True)
        projects = self.db_manager.get_order_projects()
        self.combo_project['values'] = ['Все'] + projects
        self.combo_project.set('Все')

        mfr_frame = ttk.Frame(self)
        mfr_frame.pack(fill=tk.X, padx=20, pady=5)
        ttk.Label(mfr_frame, text="Производитель:").pack(side=tk.LEFT, padx=(0, 10))
        self.combo_manufacturer = ttk.Combobox(mfr_frame, width=30, state="readonly")
        self.combo_manufacturer.pack(side=tk.LEFT, fill=tk.X, expand=True)
        c = self.db_manager.conn.cursor()
        c.execute("SELECT DISTINCT manufacturer FROM orders WHERE manufacturer IS NOT NULL AND manufacturer != '' ORDER BY manufacturer")
        manufacturers = ['Все'] + [row[0] for row in c.fetchall()]
        self.combo_manufacturer['values'] = manufacturers
        self.combo_manufacturer.set('Все')

        recv_frame = ttk.Frame(self)
        recv_frame.pack(fill=tk.X, padx=20, pady=5)
        ttk.Label(recv_frame, text="Получено:").pack(side=tk.LEFT, padx=(0, 10))
        self.combo_received = ttk.Combobox(recv_frame, width=30, state="readonly",
                                           values=["Все", "Получено", "Не получено"])
        self.combo_received.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.combo_received.set('Все')

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=20, pady=15)

        info_frame = ttk.Frame(self)
        info_frame.pack(fill=tk.X, padx=20, pady=5)
        self.lbl_info = ttk.Label(info_frame, text="", foreground="blue")
        self.lbl_info.pack()
        self._update_info()

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=15)
        ttk.Button(btn_frame, text="Экспорт", command=self.do_export).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self.destroy).pack(side=tk.LEFT, padx=5)

        self.combo_project.bind("<<ComboboxSelected>>", lambda e: self._update_info())
        self.combo_manufacturer.bind("<<ComboboxSelected>>", lambda e: self._update_info())
        self.combo_received.bind("<<ComboboxSelected>>", lambda e: self._update_info())
        self.grab_set()

    def _update_info(self):
        project = self.combo_project.get()
        manufacturer = self.combo_manufacturer.get()
        received = self.combo_received.get()
        c = self.db_manager.conn.cursor()
        query = "SELECT COUNT(DISTINCT order_batch_id) as cnt FROM orders WHERE 1=1"
        params = []
        if project != 'Все':
            query += " AND project_name = ?"
            params.append(project)
        if manufacturer != 'Все':
            query += " AND manufacturer = ?"
            params.append(manufacturer)
        if received == 'Получено':
            query += " AND received = 1"
        elif received == 'Не получено':
            query += " AND (received = 0 OR received IS NULL)"
        c.execute(query, params)
        count = c.fetchone()['cnt']
        self.lbl_info.config(text=f"Будет экспортировано заказов: {count}")

    def do_export(self):
        project = self.combo_project.get()
        manufacturer = self.combo_manufacturer.get()
        received = self.combo_received.get()
        directory = filedialog.askdirectory(title="Выберите папку для сохранения")
        if not directory:
            return
        today = datetime.now().strftime("%d.%m.%Y")
        filename_parts = ["Заказы", today]
        if project != 'Все':
            filename_parts.append(project)
        if manufacturer != 'Все':
            filename_parts.append(manufacturer)
        filename = "_".join(filename_parts) + ".xlsx"
        full_path = os.path.join(directory, filename)
        if os.path.exists(full_path):
            if not messagebox.askyesno("Файл существует", f"Перезаписать?\n{full_path}"):
                return
        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Заказы"
            ws['A1'] = f"Дата отчета: {today}"
            ws['A1'].font = Font(bold=True, size=12)

            headers = [
                "№ заказа", "Дата заказа", "Проект", "Производитель",
                "Подпроект", "КД", "Дата оплаты", "Доставка", "Ед. доставки",
                "Min дата поставки", "Max дата поставки", "Номер инвойса",
                "Поставщик", "Номер поставки", "Получено", "Дата получения", "Дата списания"
            ]
            for col_idx, header in enumerate(headers, start=1):
                cell = ws.cell(row=3, column=col_idx, value=header)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
                cell.alignment = Alignment(horizontal="center", wrap_text=True)

            c = self.db_manager.conn.cursor()
            query = '''SELECT order_batch_id, 
                              MAX(order_date) as order_date, 
                              MAX(project_name) as project_name, 
                              MAX(payment_date) as payment_date,
                              MAX(manufacturer) as manufacturer,
                              MAX(subproject) as subproject,
                              MAX(kd) as kd,
                              MAX(delivery_days) as delivery_days, 
                              MAX(delivery_unit_order) as delivery_unit_order, 
                              MAX(min_delivery_date) as min_delivery_date, 
                              MAX(max_delivery_date) as max_delivery_date,
                              MAX(invoice_number) as invoice_number,
                              MAX(supplier) as supplier,
                              MAX(delivery_number) as delivery_number,
                              MAX(received) as received,
                              MAX(receipt_date) as receipt_date,
                              MAX(write_off_date) as write_off_date
                       FROM orders 
                       WHERE 1=1'''
            params = []
            if project != 'Все':
                query += " AND project_name = ?"
                params.append(project)
            if manufacturer != 'Все':
                query += " AND manufacturer = ?"
                params.append(manufacturer)
            if received == 'Получено':
                query += " AND received = 1"
            elif received == 'Не получено':
                query += " AND (received = 0 OR received IS NULL)"
            query += " GROUP BY order_batch_id ORDER BY order_batch_id DESC"
            c.execute(query, params)
            rows = c.fetchall()

            row_num = 4
            for r in rows:
                received_mark = "✓" if r['received'] else ""
                values = [
                    r['order_batch_id'], r['order_date'] or "",
                    r['project_name'] or "", r['manufacturer'] or "",
                    r['subproject'] or "", r['kd'] or "",
                    r['payment_date'] or "", r['delivery_days'] or 0,
                    r['delivery_unit_order'] or "", r['min_delivery_date'] or "",
                    r['max_delivery_date'] or "", r['invoice_number'] or "",
                    r['supplier'] or "", r['delivery_number'] or "",
                    received_mark, r['receipt_date'] or "", r['write_off_date'] or ""
                ]
                for col_idx, val in enumerate(values, start=1):
                    ws.cell(row=row_num, column=col_idx, value=val)
                row_num += 1

            for col_idx in range(1, len(headers) + 1):
                max_len = 0
                for r in range(1, row_num):
                    v = ws.cell(row=r, column=col_idx).value
                    if v is not None:
                        max_len = max(max_len, len(str(v)))
                col_letter = get_column_letter(col_idx)
                ws.column_dimensions[col_letter].width = min(max(max_len + 2, 10), 40)

            wb.save(full_path)
            self.result = full_path
            messagebox.showinfo("Успех", f"Экспортировано {len(rows)} заказов.\nФайл сохранён:\n{full_path}")
            self.destroy()
        except PermissionError:
            messagebox.showerror("Ошибка доступа", f"Файл открыт в другой программе:\n{full_path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось создать файл:\n{e}")
            traceback.print_exc()