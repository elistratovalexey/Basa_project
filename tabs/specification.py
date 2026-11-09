import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tabs.base import BaseTab
from dialogs.specification_dialog import SpecificationDialog
from utils import parse_number_or_zero, format_money
import os
import re

try:
    from dialogs.order_file_parser import parse_file_to_rows_with_text
except ImportError:
    pass


class SpecificationTab(BaseTab):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        self.create_ui()

    def create_ui(self):
        frame_spec = ttk.LabelFrame(self.parent, text="Спецификация", padding=10)
        frame_spec.pack(fill="both", expand=True)

        columns = ("number", "name", "quantity", "price", "currency", "total")
        self.app.spec_tree = ttk.Treeview(frame_spec, columns=columns, show="headings", height=8)
        self.app.spec_tree.heading("number", text="№")
        self.app.spec_tree.heading("name", text="Наименование")
        self.app.spec_tree.heading("quantity", text="Кол-во")
        self.app.spec_tree.heading("price", text="Цена, включая НДС 22%")
        self.app.spec_tree.heading("currency", text="Валюта")
        self.app.spec_tree.heading("total", text="Сумма, включая НДС 22%")
        self.app.spec_tree.column("number", width=40, anchor="center")
        self.app.spec_tree.column("name", width=300, anchor="w")
        self.app.spec_tree.column("quantity", width=70, anchor="center")
        self.app.spec_tree.column("price", width=110, anchor="e")
        self.app.spec_tree.column("currency", width=80, anchor="center")
        self.app.spec_tree.column("total", width=110, anchor="e")

        scrollbar = ttk.Scrollbar(frame_spec, orient=tk.VERTICAL, command=self.app.spec_tree.yview)
        self.app.spec_tree.configure(yscroll=scrollbar.set)
        self.app.spec_tree.pack(side=tk.LEFT, fill="both", expand=True)
        scrollbar.pack(side=tk.RIGHT, fill="y")

        btn_frame = ttk.Frame(frame_spec)
        btn_frame.pack(pady=5)
        ttk.Button(btn_frame, text="Добавить", command=self.add_specification).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Редактировать", command=self.edit_specification).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Удалить", command=self.delete_specification).pack(side=tk.LEFT, padx=5)
        # === НОВАЯ КНОПКА ИМПОРТА ===
        ttk.Button(btn_frame, text="Импорт из файла (Word/Excel/PDF)", 
                   command=self.import_from_file).pack(side=tk.LEFT, padx=5)

        self.app.spec_tree.bind("<Double-1>", lambda e: self.edit_specification())
        self.app.lbl_spec_totals = ttk.Label(frame_spec, text="", font=("Arial", 10, "bold"), foreground="darkblue")
        self.app.lbl_spec_totals.pack(pady=5)

    def import_from_file(self):
        """Импорт позиций из Word/Excel/PDF файла"""
        if not self.app.current_project:
            messagebox.showwarning("Внимание", "Выберите проект!")
            return

        filepath = filedialog.askopenfilename(
            title="Выберите файл (Word, Excel или PDF)",
            filetypes=[
                ("Все поддерживаемые", "*.docx *.xlsx *.xls *.pdf"),
                ("Word", "*.docx"),
                ("Excel", "*.xlsx *.xls"),
                ("PDF", "*.pdf"),
                ("Все файлы", "*.*")
            ])
        if not filepath:
            return

        try:
            file_rows, full_text = parse_file_to_rows_with_text(filepath)
        except Exception as e:
            messagebox.showerror("Ошибка парсинга", f"Не удалось прочитать файл:\n{e}")
            return

        if not file_rows:
            messagebox.showwarning("Пустой файл", "Файл не содержит таблиц с данными")
            return

        print(f"=== ИМПОРТ ИЗ ФАЙЛА: {os.path.basename(filepath)} ===")
        print(f"Получено строк: {len(file_rows)}")
        for i, r in enumerate(file_rows[:3]):
            print(f"  Строка {i}: {r}")

        # === ОПРЕДЕЛЯЕМ: первая строка - заголовок или данные? ===
        first_row_text = ' '.join([str(c).upper() for c in file_rows[0] if c])
        is_header = any(word in first_row_text for word in 
                       ['НАИМЕН', 'ТОВАР', 'DESCRIPTION', 'NAME', 'PRODUCT',
                        'ЦЕНА', 'PRICE', 'СУММ', 'TOTAL', 'AMOUNT', 'КОЛИЧ', 'QUANT'])
        
        print(f"Первая строка - заголовок? {is_header}")

        # === СЛУЧАЙ 1: Нормализованная структура (Word) - фиксированные индексы ===
        # Индексы: 0-номер, 1-артикул, 2-наименование, 3-кол-во, 4-ед, 5-цена, 6-сумма, 10-валюта
        if not is_header and len(file_rows[0]) >= 7:
            print("Используем нормализованную структуру (фиксированные индексы)")
            data_rows = file_rows  # Все строки - данные
            use_fixed_indices = True
        else:
            # === СЛУЧАЙ 2: Сырая таблица (Excel/PDF) - определяем колонки по заголовку ===
            print("Определяем колонки по заголовку")
            header = file_rows[0]
            data_rows = file_rows[1:]  # Пропускаем заголовок
            use_fixed_indices = False
            
            col_map = {'number': -1, 'name': -1, 'quantity': -1,
                       'price': -1, 'currency': -1, 'total': -1}
            
            for i, cell in enumerate(header):
                if not cell:
                    continue
                cell_upper = str(cell).upper().strip().replace(' ', '').replace('\n', '')
                print(f"  Колонка {i}: '{cell}' -> '{cell_upper}'")
                
                if cell_upper in ['№', 'N', 'NUM', 'НОМЕР', 'SIRA', 'NO.', 'NO', 'POS']:
                    col_map['number'] = i
                elif any(word in cell_upper for word in ['НАИМЕН', 'ТОВАР', 'DESCRIPTION', 'ОПИСАНИЕ',
                                                          'NAME', 'PRODUCT', 'ITEM', 'УСЛУГА']):
                    col_map['name'] = i
                elif any(word in cell_upper for word in ['КОЛИЧ', 'QUANT', 'QTY', 'КОЛ-ВО',
                                                          'ADET', 'MIKTAR', 'QUANTITY']):
                    col_map['quantity'] = i
                elif any(word in cell_upper for word in ['ЦЕНА', 'PRICE', 'FİYAT', 'FIYAT', 'СТОИМ']):
                    col_map['price'] = i
                elif any(word in cell_upper for word in ['ВАЛЮТ', 'CURRENCY', 'CUR']):
                    col_map['currency'] = i
                elif any(word in cell_upper for word in ['СУММ', 'TOTAL', 'ИТОГО', 'TOPLAM',
                                                          'AMOUNT', 'SUM', 'СНДС']):
                    col_map['total'] = i
            
            print(f"Карта колонок: {col_map}")

        # === Определяем валюту из полного текста/заголовков ===
        detected_currency = 'RUB'
        search_text = full_text.upper() if full_text else ''
        header_text = ' '.join([str(c).upper() for c in (file_rows[0] if is_header else [])])
        combined = search_text + ' ' + header_text
        
        if 'ЕВРО' in combined or 'EURO' in combined or ' €' in combined:
            detected_currency = 'EUR'
        elif 'ДОЛЛАР' in combined or 'USD' in combined or '$' in combined:
            detected_currency = 'USD'
        elif 'ЮАНЬ' in combined or 'CNY' in combined or '¥' in combined:
            detected_currency = 'CNY'
        elif 'ЛИРА' in combined or 'TRY' in combined:
            detected_currency = 'TRY'
        elif 'РУБ' in combined or 'RUB' in combined or '₽' in combined:
            detected_currency = 'RUB'
        
        print(f"Определена валюта: {detected_currency}")

        # === Импорт строк ===
        items_added = 0
        project_id = self.db_manager.get_project_id(self.app.current_project)
        if not project_id:
            messagebox.showerror("Ошибка", "Не удалось найти проект!")
            return

        current_number = self.db_manager.get_next_number("specifications", project_id)

        for row_idx, row in enumerate(data_rows):
            if not row or len(row) < 2:
                continue

            row_text = ' '.join([str(c) for c in row if c]).upper()
            
            # Пропускаем служебные строки
            if any(word in row_text for word in ['ИТОГО', 'TOTAL:', 'GRAND TOTAL', 
                                                   'ОБЩАЯ СУММА', 'НАИМЕНОВАНИЙ', 'ВСЕГО К']):
                print(f"  Строка {row_idx}: пропуск служебной строки")
                continue

            if use_fixed_indices:
                # Нормализованная структура: извлекаем по фиксированным индексам
                number = str(row[0]).strip() if len(row) > 0 and row[0] else str(current_number)
                name = str(row[2]).strip() if len(row) > 2 and row[2] else ""
                quantity = str(row[3]).strip() if len(row) > 3 and row[3] else "1"
                unit = str(row[4]).strip() if len(row) > 4 and row[4] else ""
                price = str(row[5]).strip() if len(row) > 5 and row[5] else "0"
                total = str(row[6]).strip() if len(row) > 6 and row[6] else "0"
                # Валюта из индекса 10 (если есть), иначе из detected_currency
                currency = str(row[10]).strip() if len(row) > 10 and row[10] else detected_currency
            else:
                # Сырая таблица: извлекаем по col_map
                number = str(current_number)
                name = ""
                quantity = "1"
                price = "0"
                currency = detected_currency
                total = "0"

                if col_map['number'] >= 0 and col_map['number'] < len(row) and row[col_map['number']]:
                    number = str(row[col_map['number']]).strip()
                if col_map['name'] >= 0 and col_map['name'] < len(row) and row[col_map['name']]:
                    name = str(row[col_map['name']]).strip()
                if col_map['quantity'] >= 0 and col_map['quantity'] < len(row) and row[col_map['quantity']]:
                    quantity = str(row[col_map['quantity']]).strip()
                if col_map['price'] >= 0 and col_map['price'] < len(row) and row[col_map['price']]:
                    price = str(row[col_map['price']]).strip()
                if col_map['total'] >= 0 and col_map['total'] < len(row) and row[col_map['total']]:
                    total = str(row[col_map['total']]).strip()
                if col_map['currency'] >= 0 and col_map['currency'] < len(row) and row[col_map['currency']]:
                    cur_val = str(row[col_map['currency']]).strip().upper()
                    if cur_val in ['RUB', 'USD', 'EUR', 'CNY', 'TRY', 'РУБ']:
                        currency = 'RUB' if cur_val == 'РУБ' else cur_val

            # Номер всегда продолжает нумерацию проекта: номер из файла мог
            # совпасть с уже существующим, а редактирование/удаление идёт по
            # паре (проект, номер) — изменились бы сразу две записи
            number = str(current_number)

            # Если имя пустое - пропускаем
            if not name:
                print(f"  Строка {row_idx}: пропуск (нет наименования), row={row}")
                continue

            # Парсим числовые значения (очищаем от пробелов, символов валют, апострофов)
            # Разбор чисел: «1 234,56», «1.234,56», «1,234.56», «12 500 ₽» и т.п.
            # (раньше «1,234.56» превращалось в ошибку и цена становилась 0)
            parse_num = parse_number_or_zero

            qty_val = parse_num(quantity)
            price_val = parse_num(price)
            total_val = parse_num(total)

            if total_val == 0 and qty_val > 0 and price_val > 0:
                total_val = qty_val * price_val
            if qty_val == 0:
                qty_val = 1

            qty_str = str(qty_val).replace('.', ',').rstrip('0').rstrip(',')
            price_str = format_money(price_val)
            total_str = format_money(total_val)

            print(f"  ✓ Строка {row_idx}: №{number}, '{name[:40]}', кол-во={qty_str}, цена={price_str}, валюта={currency}")

            spec_data = {
                'number': number,
                'name': name,
                'quantity': qty_str,
                'price': price_str,
                'currency': currency,
                'total': total_str,
            }

            self.db_manager.add_specification(project_id, spec_data)
            items_added += 1
            current_number += 1

        self.app.spec_counter = current_number
        self.load_specifications()

        print(f"=== ИТОГО Импортировано: {items_added} ===")

        if items_added == 0:
            messagebox.showwarning("Внимание",
                f"Не удалось импортировать ни одной позиции из файла:\n"
                f"{os.path.basename(filepath)}\n\n"
                f"Проверьте вывод в терминале для диагностики.")
        else:
            messagebox.showinfo("Успех",
                f"Импортировано {items_added} позиций из файла:\n"
                f"{os.path.basename(filepath)}")

        self.app.log_action(f"Импортировано {items_added} позиций из {os.path.basename(filepath)}")
        
    def add_specification(self):
        if not self.app.current_project:
            messagebox.showwarning("Внимание", "Выберите проект!")
            return
        dialog = SpecificationDialog(self.root, "Добавить", self.app.spec_counter)
        self.root.wait_window(dialog)
        if dialog.result:
            spec = dialog.result
            project_id = self.db_manager.get_project_id(self.app.current_project)
            if project_id:
                self.db_manager.add_specification(project_id, spec)
                self.load_specifications()
                self.app.spec_counter += 1
                self.app.log_action(f"Спецификация №{spec['number']} добавлена")

    def edit_specification(self):
        selected = self.app.spec_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите запись!")
            return
        item = self.app.spec_tree.item(selected[0])
        values = item["values"]
        dialog = SpecificationDialog(self.root, "Редактировать", values[0], {
            "name": values[1], "quantity": values[2], "price": values[3], "currency": values[4]
        })
        self.root.wait_window(dialog)
        if dialog.result:
            project_id = self.db_manager.get_project_id(self.app.current_project)
            if project_id:
                self.db_manager.update_specification(project_id, values[0], dialog.result)
                self.load_specifications()

    def delete_specification(self):
        selected = self.app.spec_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите запись!")
            return
        number = self.app.spec_tree.item(selected[0])["values"][0]
        if messagebox.askyesno("Подтверждение", f"Удалить запись №{number}?"):
            project_id = self.db_manager.get_project_id(self.app.current_project)
            if project_id:
                self.db_manager.delete_specification(project_id, number)
                self.load_specifications()

    def load_specifications(self):
        for item in self.app.spec_tree.get_children():
            self.app.spec_tree.delete(item)
        if not self.app.current_project:
            self.update_spec_totals()
            return
        project_id = self.db_manager.get_project_id(self.app.current_project)
        if not project_id:
            self.update_spec_totals()
            return
        specs = self.db_manager.get_specifications(project_id)
        for s in specs:
            qty = parse_number_or_zero(s["quantity"])
            price = parse_number_or_zero(s["price"])
            total = qty * price
            total_str = format_money(total)
            self.app.spec_tree.insert("", tk.END, values=(
                s["number"], s["name"] or "", s["quantity"] or "",
                s["price"] or "", s["currency"] or "", total_str
            ))
        self.app.spec_counter = self.db_manager.get_next_number("specifications", project_id)
        self.update_spec_totals()

    def update_spec_totals(self):
        if not self.app.current_project:
            if hasattr(self.app, 'lbl_spec_totals'):
                self.app.lbl_spec_totals.config(text="")
            return
        project_id = self.db_manager.get_project_id(self.app.current_project)
        if not project_id:
            self.app.lbl_spec_totals.config(text="")
            return
        specs = self.db_manager.get_specifications(project_id)
        totals = {}
        vat_totals = {}
        for s in specs:
            currency = s["currency"] or "Не указана"
            qty = parse_number_or_zero(s["quantity"])
            price = parse_number_or_zero(s["price"])
            total = qty * price
            vat = total * 0.22 / 1.22
            if currency not in totals:
                totals[currency] = 0
                vat_totals[currency] = 0
            totals[currency] += total
            vat_totals[currency] += vat
        if not totals:
            self.app.lbl_spec_totals.config(text="")
            return
        parts = []
        for currency in totals:
            total = totals[currency]
            vat = vat_totals[currency]
            total_str = format_money(total)
            vat_str = format_money(vat)
            parts.append(f"Итого ({currency}): {total_str} | НДС 22%: {vat_str}")
        self.app.lbl_spec_totals.config(text=" | ".join(parts))