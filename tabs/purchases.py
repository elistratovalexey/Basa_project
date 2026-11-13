import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tabs.base import BaseTab
from dialogs.purchase_dialog import PurchaseDialog
from dialogs.nomenclature_search_dialog import NomenclatureSearchDialog
from dialogs.nomenclature_dialog import NomenclatureDialog
from dialogs.manufacturer_dialog import ManufacturerDialog
from dialogs.supplier_dialog import SupplierDialog
from dialogs.subproject_dialog import SubprojectDialog
from dialogs.kd_dialog import KDDialog
from dialogs.import_dialog import ImportFileDialog
from dialogs.order_dialog import OrderDialog
from utils import add_months, open_path
from datetime import datetime
import os
import re


class PurchasesTab(BaseTab):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        self.create_ui()

    def create_ui(self):
        frame_controls = ttk.Frame(self.parent)
        frame_controls.pack(fill="x", pady=5)
        ttk.Button(frame_controls, text="Добавить позицию", command=self.add_purchase).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_controls, text="Редактировать", command=self.edit_purchase).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_controls, text="Удалить", command=self.delete_purchase).pack(side=tk.LEFT, padx=5)
        # НОВОЕ: перенос выделенных позиций в другой проект
        ttk.Button(frame_controls, text="Сменить проект", command=self.change_purchase_project).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_controls, text="Создать заказ", command=self.create_order).pack(side=tk.LEFT, padx=10)
        ttk.Button(frame_controls, text="Приёмка", command=self.open_receiving).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_controls, text="История цен", command=self.open_price_history).pack(side=tk.LEFT, padx=5)      
        ttk.Button(frame_controls, text="В справочник номенклатуры",
                   command=self.add_to_nomenclature).pack(side=tk.LEFT, padx=10)
        ttk.Button(frame_controls, text="Поиск по номенклатуре", command=self.open_nomenclature_search).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_controls, text="Импорт из файла", command=self.show_import_dialog).pack(side=tk.LEFT, padx=10)
        ttk.Button(frame_controls, text="Вывод в EXCEL", command=self.export_purchases_to_excel).pack(side=tk.RIGHT, padx=5)
        btn_orders = ttk.Button(frame_controls, text="ЗАКАЗЫ", command=self.show_orders, style='Orders.TButton')
        btn_orders.pack(side=tk.RIGHT, padx=5)

        filter_frame = ttk.Frame(self.parent)
        filter_frame.pack(fill="x", pady=5)
        ttk.Label(filter_frame, text="Фильтр по производителю:").pack(side=tk.LEFT, padx=5)
        self.app.combo_filter_manufacturer = ttk.Combobox(filter_frame, width=25, state="readonly")
        self.app.combo_filter_manufacturer.pack(side=tk.LEFT, padx=5)
        self.app.combo_filter_manufacturer.bind("<<ComboboxSelected>>", lambda e: self.load_purchases())
        ttk.Label(filter_frame, text="Фильтр по подпроекту:").pack(side=tk.LEFT, padx=15)
        self.app.combo_filter_subproject = ttk.Combobox(filter_frame, width=25, state="readonly")
        self.app.combo_filter_subproject.pack(side=tk.LEFT, padx=5)
        self.app.combo_filter_subproject.bind("<<ComboboxSelected>>", lambda e: self.load_purchases())
        self.app.filter_empty_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(filter_frame, text="Только без галочек", variable=self.app.filter_empty_var,
                        command=self.load_purchases).pack(side=tk.LEFT, padx=15)
        ttk.Button(filter_frame, text="Сбросить фильтры", command=self.reset_filters).pack(side=tk.LEFT, padx=10)

        status_frame = ttk.LabelFrame(self.parent, text="Фильтр по статусу", padding=5)
        status_frame.pack(fill="x", pady=5)
        self.app.filter_ordered_var = tk.BooleanVar(value=False)
        self.app.filter_in_order_var = tk.BooleanVar(value=False)
        self.app.filter_received_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(status_frame, text="Только заказанные", variable=self.app.filter_ordered_var,
                        command=self.load_purchases).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(status_frame, text="Только в заказе", variable=self.app.filter_in_order_var,
                        command=self.load_purchases).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(status_frame, text="Только полученные", variable=self.app.filter_received_var,
                        command=self.load_purchases).pack(side=tk.LEFT, padx=10)

        frame_refs = ttk.Frame(self.parent)
        frame_refs.pack(fill="x", padx=10, pady=5)
        ttk.Label(frame_refs, text="Справочники:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(frame_refs, text="Справочник номенклатуры", command=self.open_nomenclature).pack(side=tk.LEFT, padx=3)
        ttk.Button(frame_refs, text="Справочник производителей", command=self.open_manufacturers).pack(side=tk.LEFT, padx=3)
        ttk.Button(frame_refs, text="Справочник поставщиков", command=self.open_suppliers).pack(side=tk.LEFT, padx=3)
        ttk.Button(frame_refs, text="Справочник подпроектов", command=self.open_subprojects).pack(side=tk.LEFT, padx=3)
        ttk.Button(frame_refs, text="Справочник КД", command=self.open_kd).pack(side=tk.LEFT, padx=3)

        frame_table = ttk.LabelFrame(self.parent, text="Закупки", padding=10)
        frame_table.pack(fill="both", expand=True)
        # НОВОЕ: колонка project между price_request и note —
        # номера колонок флагов (#9,#11,#12,#13) не сбиваются
        columns = ("number", "manufacturer", "subproject", "kd", "article", "name", "name_eng",
                   "quantity", "ordered", "order_date", "in_order", "received",
                   "price_request", "project", "note")
        self.app.purchase_tree = ttk.Treeview(frame_table, columns=columns, show="headings", height=10)
        self.app.purchase_tree.heading("number", text="№")
        self.app.purchase_tree.heading("manufacturer", text="Производитель")
        self.app.purchase_tree.heading("subproject", text="Подпроект")
        self.app.purchase_tree.heading("kd", text="КД")
        self.app.purchase_tree.heading("article", text="Артикул")
        self.app.purchase_tree.heading("name", text="Наименование (рус)")
        self.app.purchase_tree.heading("name_eng", text="Наименование (анг)")
        self.app.purchase_tree.heading("quantity", text="Кол-во")
        self.app.purchase_tree.heading("ordered", text="Заказано")
        self.app.purchase_tree.heading("order_date", text="Дата заказа")
        self.app.purchase_tree.heading("in_order", text="В заказ")
        self.app.purchase_tree.heading("received", text="Получено")
        self.app.purchase_tree.heading("price_request", text="Запрос цены")
        self.app.purchase_tree.heading("project", text="Проект")
        self.app.purchase_tree.heading("note", text="Примечание")
        self.app.purchase_tree.column("number", width=40, anchor="center")
        self.app.purchase_tree.column("manufacturer", width=100, anchor="w")
        self.app.purchase_tree.column("subproject", width=120, anchor="w")
        self.app.purchase_tree.column("kd", width=60, anchor="center")
        self.app.purchase_tree.column("article", width=120, anchor="w")
        self.app.purchase_tree.column("name", width=200, anchor="w")
        self.app.purchase_tree.column("name_eng", width=200, anchor="w")
        self.app.purchase_tree.column("quantity", width=60, anchor="center")
        self.app.purchase_tree.column("ordered", width=70, anchor="center")
        self.app.purchase_tree.column("order_date", width=90, anchor="center")
        self.app.purchase_tree.column("in_order", width=70, anchor="center")
        self.app.purchase_tree.column("received", width=70, anchor="center")
        self.app.purchase_tree.column("price_request", width=80, anchor="center")
        self.app.purchase_tree.column("project", width=120, anchor="w")
        self.app.purchase_tree.column("note", width=150, anchor="w")
        # НОВОЕ: индекс колонки "Проект" для клика-переноса
        self._project_col = f"#{columns.index('project') + 1}"
        scrollbar = ttk.Scrollbar(frame_table, orient=tk.VERTICAL, command=self.app.purchase_tree.yview)
        self.app.purchase_tree.configure(yscroll=scrollbar.set)
        self.app.purchase_tree.pack(side=tk.LEFT, fill="both", expand=True)
        scrollbar.pack(side=tk.RIGHT, fill="y")
        self.app.purchase_tree.bind("<Double-1>", lambda e: self.edit_purchase())
        self.app.purchase_tree.bind("<Button-1>", self.on_purchase_click)
    
    def open_receiving(self):
        from dialogs.receiving_dialog import ReceivingDialog
        ReceivingDialog(self.root, self.db_manager, self.app.current_project)
        self.load_purchases()

    def open_price_history(self):
        from dialogs.price_history_dialog import PriceHistoryDialog
        sel = self.app.purchase_tree.selection()
        art = ""
        if sel:
            vals = self.app.purchase_tree.item(sel[0])["values"]
            art = str(vals[4]) if len(vals) > 4 else ""
        PriceHistoryDialog(self.root, self.db_manager, art)       

    def on_purchase_click(self, event):
        tree = self.app.purchase_tree
        try:
            region = tree.identify_region(event.x, event.y)
            col = tree.identify_column(event.x)
            row_id = tree.identify_row(event.y)
        except Exception:
            return
        if region != "cell":
            return
        # НОВОЕ: клик по ячейке "Проект" = перенос этой позиции в другой проект
        if col == self._project_col:
            self.change_purchase_project(row_ids=[row_id])
            return "break"
        flag_map = {'#9': 'ordered', '#11': 'in_order', '#12': 'received', '#13': 'price_request'}
        field = flag_map.get(col)
        if not field or not row_id:
            return
        if not self.app.current_project:
            return "break"
        project_id = self.db_manager.get_project_id(self.app.current_project)
        if not project_id:
            return "break"
        try:
            vals = tree.item(row_id)['values']
        except Exception:
            return "break"
        if not vals:
            return "break"
        number = vals[0]
        full = self.db_manager.get_purchase_by_number(project_id, number)
        if not full:
            return "break"
        cur = 1 if full[field] else 0
        new = 0 if cur else 1
        self.db_manager.set_purchase_flag(project_id, number, field, new)
        self.app.log_action(f"Переключено {field}={new} у закупки №{number}")
        self.root.after_idle(self.load_purchases)
        return "break"

    def change_purchase_project(self, row_ids=None):
        """НОВОЕ: перенос выбранных (или одной) закупок в другой проект."""
        if not self.app.current_project:
            messagebox.showwarning("Внимание", "Выберите проект!")
            return
        from_project_id = self.db_manager.get_project_id(self.app.current_project)
        if not from_project_id:
            return
        if row_ids is None:
            row_ids = self.app.purchase_tree.selection()
        if not row_ids:
            messagebox.showwarning("Внимание", "Выберите позицию(и) для переноса!")
            return
        numbers = [self.app.purchase_tree.item(r)['values'][0] for r in row_ids]
        projects = self.db_manager.get_all_projects()
        targets = [p['name'] for p in projects if p['id'] != from_project_id]
        if not targets:
            messagebox.showinfo("Информация", "Нет других проектов для переноса.")
            return
        dialog = ProjectChoiceDialog(self.root, targets, count=len(numbers))
        self.root.wait_window(dialog)
        if not dialog.result:
            return
        target_id = next((p['id'] for p in projects if p['name'] == dialog.result), None)
        if not target_id:
            return
        moved = 0
        for number in numbers:
            new_num = self.db_manager.move_purchase(from_project_id, number, target_id)
            self.app.log_action(
                f"Закупка №{number} перенесена в проект '{dialog.result}' под №{new_num}")
            moved += 1
        self.load_purchases()
        messagebox.showinfo("Успех", f"Перенесено позиций: {moved} в проект '{dialog.result}'")

    def add_purchase(self):
        if not self.app.current_project:
            messagebox.showwarning("Внимание", "Выберите проект!")
            return
        dialog = PurchaseDialog(self.root, "Добавить закупку", self.app.purchase_counter,
                                db_manager=self.db_manager, project_name=self.app.current_project)
        self.root.wait_window(dialog)
        if dialog.result:
            purchase = dialog.result
            project_id = self.db_manager.get_project_id(self.app.current_project)
            if project_id:
                self.db_manager.add_purchase(project_id, purchase)
                self.load_purchases()
                self.app.purchase_counter += 1
                self.app.log_action(f"Закупка №{purchase['number']} добавлена")

    def edit_purchase(self):
        selected = self.app.purchase_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите запись!")
            return
        if not self.app.current_project:
            messagebox.showwarning("Внимание", "Выберите проект!")
            return
        project_id = self.db_manager.get_project_id(self.app.current_project)
        if not project_id:
            messagebox.showerror("Ошибка", "Не удалось получить ID проекта!")
            return
        number = self.app.purchase_tree.item(selected[0])["values"][0]
        full = self.db_manager.get_purchase_by_number(project_id, number)
        if not full:
            messagebox.showerror("Ошибка", f"Закупка №{number} не найдена в базе!")
            return
        if hasattr(full, 'keys'):
            full = dict(full)
        data = {
            "manufacturer": full.get("manufacturer") or "",
            "subproject": full.get("subproject") or "",
            "kd": full.get("kd") or "",
            "article": full.get("article") or "",
            "name": full.get("name") or "",
            "name_eng": full.get("name_eng") or "",
            "quantity": full.get("quantity") if full.get("quantity") is not None else "",
            "note": full.get("note") or "",
            "ordered": bool(full.get("ordered", 0)),
            "order_date": full.get("order_date") or "",
            "received": bool(full.get("received", 0)),
            "receipt_date": full.get("receipt_date") or "",
            "in_order": bool(full.get("in_order", 0)),
            "price_request": bool(full.get("price_request", 0)),
        }
        dialog = PurchaseDialog(self.root, "Редактировать закупку", number, data,
                                db_manager=self.db_manager, project_name=self.app.current_project)
        self.root.wait_window(dialog)
        if dialog.result and isinstance(dialog.result, dict) and dialog.result:
            # диалог не редактирует флаг "Запрос цены" — сохраняем текущее значение
            dialog.result.setdefault('price_request', full.get('price_request', 0))
            try:
                self.db_manager.update_purchase(project_id, number, dialog.result)
                self.load_purchases()
                self.app.log_action(f"Закупка №{number} отредактирована")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить:\n{e}")
                import traceback
                traceback.print_exc()

    def delete_purchase(self):
        selected = self.app.purchase_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите запись!")
            return
        number = self.app.purchase_tree.item(selected[0])["values"][0]
        if messagebox.askyesno("Подтверждение", f"Удалить запись №{number}?"):
            project_id = self.db_manager.get_project_id(self.app.current_project)
            if project_id:
                self.db_manager.delete_purchase(project_id, number)
                self.load_purchases()
                self.app.log_action(f"Закупка №{number} удалена")

    def load_purchases(self):
        for item in self.app.purchase_tree.get_children():
            self.app.purchase_tree.delete(item)
        if not self.app.current_project:
            return
        project_id = self.db_manager.get_project_id(self.app.current_project)
        if not project_id:
            return
        purchases = self.db_manager.get_purchases(project_id)
        filter_manufacturer = self.app.combo_filter_manufacturer.get()
        filter_subproject = self.app.combo_filter_subproject.get()
        filter_empty = self.app.filter_empty_var.get()
        filter_ordered = self.app.filter_ordered_var.get()
        filter_in_order = self.app.filter_in_order_var.get()
        filter_received = self.app.filter_received_var.get()
        for p in purchases:
            if filter_manufacturer and p["manufacturer"] != filter_manufacturer:
                continue
            if filter_subproject and p["subproject"] != filter_subproject:
                continue
            if filter_empty and (p["ordered"] or p["in_order"] or p["received"]):
                continue
            if filter_ordered and not p["ordered"]:
                continue
            if filter_in_order and not p["in_order"]:
                continue
            if filter_received and not p["received"]:
                continue
            ordered_mark = "✓" if p["ordered"] else ""
            in_order_mark = "✓" if p["in_order"] else ""
            received_mark = "✓" if p["received"] else ""
            price_request_mark = "✓" if p["price_request"] else ""
            # НОВОЕ: имя проекта из JOIN в get_purchases
            self.app.purchase_tree.insert("", tk.END, values=(
                p["number"], p["manufacturer"] or "", p["subproject"] or "",
                p["kd"] or "", p["article"] or "", p["name"] or "",
                p["name_eng"] or "", p["quantity"] or "",
                ordered_mark, p["order_date"] or "", in_order_mark, received_mark,
                price_request_mark, self.app.current_project or "", p["note"] or ""
            ))
        # Номер следующей закупки — по ВСЕМ позициям проекта (не по отфильтрованным)
        self.app.purchase_counter = self.db_manager.get_next_number("purchases", project_id)
        self.update_filter_combos(purchases)

    def update_filter_combos(self, purchases=None):
        if purchases is None:
            project_id = self.db_manager.get_project_id(self.app.current_project)
            if not project_id:
                return
            purchases = self.db_manager.get_purchases(project_id)
        manufacturers = sorted(set(p["manufacturer"] for p in purchases if p["manufacturer"]), key=str.upper)
        self.app.combo_filter_manufacturer['values'] = [''] + manufacturers
        subprojects = sorted(set(p["subproject"] for p in purchases if p["subproject"]), key=str.upper)
        self.app.combo_filter_subproject['values'] = [''] + subprojects

    def reset_filters(self):
        self.app.combo_filter_manufacturer.set('')
        self.app.combo_filter_subproject.set('')
        self.app.filter_empty_var.set(False)
        self.app.filter_ordered_var.set(False)
        self.app.filter_in_order_var.set(False)
        self.app.filter_received_var.set(False)
        self.load_purchases()

    def create_order(self):
        if not self.app.current_project:
            messagebox.showwarning("Внимание", "Выберите проект!")
            return
        project_id = self.db_manager.get_project_id(self.app.current_project)
        if not project_id:
            return
        purchases = self.db_manager.get_purchases(project_id)
        in_order_items = [p for p in purchases if p['in_order']]
        if not in_order_items:
            messagebox.showinfo("Информация", "Нет позиций с галочкой 'В заказ'")
            return
        today = datetime.now().strftime("%d.%m.%Y")
        batch_id = self.db_manager.get_next_order_batch_id()
        # если хотя бы одна позиция с флагом "Запрос цены" —
        # весь заказ помечается как запрос цены и получает номер Z-серии
        price_request_flag = 1 if any(p['price_request'] for p in in_order_items) else 0
        z_num = self.db_manager.get_next_price_request_num() if price_request_flag else 0
        from collections import defaultdict
        groups = defaultdict(lambda: {
            "quantity": 0, "manufacturer": "", "subproject": "", "kd": "",
            "name": "", "name_eng": "", "note": "",
        })
        for p in in_order_items:
            article = (p['article'] or "").strip()
            key = article if article else ("", (p['name'] or p['name_eng'] or "").strip().upper(), p['manufacturer'] or "")
            g = groups[key]
            g["quantity"] += (p['quantity'] or 0)
            if not g["manufacturer"]:
                g["manufacturer"] = p['manufacturer'] or ""
            if not g["subproject"]:
                g["subproject"] = p['subproject'] or ""
            if not g["kd"]:
                g["kd"] = p['kd'] or ""
            if not g["name"]:
                g["name"] = p['name'] or ""
            if not g["name_eng"]:
                g["name_eng"] = p['name_eng'] or ""
            if not g["note"]:
                g["note"] = p['note'] or ""
        created_count = 0
        for key, g in groups.items():
            article = key if isinstance(key, str) else ""
            self.db_manager.add_order({
                "order_date": today,
                "project_name": self.app.current_project,
                "order_batch_id": batch_id,
                "purchase_id": None,
                "manufacturer": g["manufacturer"],
                "subproject": g["subproject"],
                "kd": g["kd"],
                "article": article,
                "name": g["name"],
                "name_eng": g["name_eng"],
                "quantity": g["quantity"],
                "note": g["note"],
                "price_request": price_request_flag,
                "price_request_num": z_num,
            })
            created_count += 1
        for p in in_order_items:
            self.db_manager.update_purchase(project_id, p['number'], {
                "number": p['number'],
                "manufacturer": p['manufacturer'],
                "subproject": p['subproject'],
                "kd": p['kd'],
                "article": p['article'],
                "name": p['name'],
                "name_eng": p['name_eng'],
                "quantity": p['quantity'],
                "note": p['note'],
                "ordered": 1,
                "order_date": today,
                "received": p['received'],
                "receipt_date": p['receipt_date'],
                "in_order": 0,
                "price_request": p['price_request'],
            })
            self.app.log_action(f"Заказ #{batch_id}: {p['article']} - {p['name']}")
        order_label = f"Z{z_num}" if price_request_flag else f"№{batch_id}"
        messagebox.showinfo("Успех",
            f"Создан заказ {order_label}\n{created_count} уникальных артикулов из {len(in_order_items)} позиций")
        self.load_purchases()

    def show_orders(self):
        dialog = OrderDialog(self.root, self.db_manager,
                             russian_holidays=self.app.russian_holidays,
                             project_name=self.app.current_project)
        self.root.wait_window(dialog)

    def open_nomenclature_search(self):
        dialog = NomenclatureSearchDialog(self.root, self.db_manager)
        self.root.wait_window(dialog)

    def add_to_nomenclature(self):
        if not self.app.current_project:
            messagebox.showwarning("Внимание", "Выберите проект!")
            return
        project_id = self.db_manager.get_project_id(self.app.current_project)
        if not project_id:
            return
        purchases = self.db_manager.get_purchases(project_id)
        added_count = 0
        for p in purchases:
            if not p['article']:
                continue
            existing = self.db_manager.find_nomenclature_by_article(p['article'])
            if not existing:
                name_eng = p['name_eng'] if p['name_eng'] else ''
                self.db_manager.add_nomenclature({
                    "manufacturer": p['manufacturer'] or '',
                    "article": p['article'],
                    "name_rus": p['name'] or '',
                    "name_eng": name_eng
                })
                added_count += 1
                self.app.log_action(f"Добавлена позиция: {p['article']} - {p['name']}")
        if added_count > 0:
            messagebox.showinfo("Успех", f"Добавлено {added_count} новых позиций в справочник номенклатуры")
        else:
            messagebox.showinfo("Информация", "Все позиции уже есть в справочнике или нет артикулов")
        self.app.log_action(f"Добавлено {added_count} позиций в справочник номенклатуры")

    def open_nomenclature(self):
        dialog = NomenclatureDialog(self.root, self.db_manager)
        self.root.wait_window(dialog)

    def open_manufacturers(self):
        dialog = ManufacturerDialog(self.root, self.db_manager)
        self.root.wait_window(dialog)

    def open_suppliers(self):
        dialog = SupplierDialog(self.root, self.db_manager)
        self.root.wait_window(dialog)

    def open_subprojects(self):
        dialog = SubprojectDialog(self.root, self.db_manager, project_name=self.app.current_project)
        self.root.wait_window(dialog)

    def open_kd(self):
        dialog = KDDialog(self.root, self.db_manager, project_name=self.app.current_project)
        self.root.wait_window(dialog)

    def show_import_dialog(self):
        if not self.app.current_project:
            messagebox.showwarning("Внимание", "Сначала выберите проект!")
            return
        dialog = ImportFileDialog(self.root, self.db_manager)
        self.root.wait_window(dialog)
        if dialog.result:
            project_id = self.db_manager.get_project_id(self.app.current_project)
            if not project_id:
                messagebox.showwarning("Внимание", "Ошибка получения ID проекта!")
                return
            max_num = self.db_manager.get_next_number("purchases", project_id) - 1
            added_count = 0
            for idx, item in enumerate(dialog.result, 1):
                max_num += 1
                purchase = {
                    'number': max_num,
                    'manufacturer': item.get('manufacturer', ''),
                    'subproject': item.get('subproject', ''),
                    'kd': item.get('kd', ''),
                    'article': item.get('article', ''),
                    'name': item.get('name_rus', ''),
                    'name_eng': item.get('name_eng', ''),
                    'quantity': item.get('qty', 0),
                    'note': item.get('note', ''),
                    'ordered': 0,
                    'order_date': '',
                    'received': 0,
                    'receipt_date': '',
                    'in_order': 1,
                    'price_request': 0,
                }
                self.db_manager.add_purchase(project_id, purchase)
                self.app.log_action(f"Импортирована закупка №{max_num}: {item.get('article', '')} - {item.get('name_rus', '')}")
                added_count += 1
            self.app.purchase_counter = max_num + 1
            self.load_purchases()
            messagebox.showinfo("Успех", f"Импортировано {added_count} позиций!")

    def export_purchases_to_excel(self):
        """Экспорт таблицы закупок в Excel"""
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.utils import get_column_letter
        except ImportError:
            messagebox.showerror("Нет библиотеки",
                "Не установлен модуль openpyxl!\n\nУстановите командой:\npip install openpyxl")
            return
        if not self.app.current_project:
            messagebox.showwarning("Внимание", "Выберите проект!")
            return
        project_id = self.db_manager.get_project_id(self.app.current_project)
        if not project_id:
            messagebox.showerror("Ошибка", "Не удалось получить ID проекта!")
            return
        purchases = self.db_manager.get_purchases(project_id)
        if not purchases:
            messagebox.showwarning("Внимание", "В проекте нет закупок для экспорта!")
            return
        project_row = self.db_manager.get_project(self.app.current_project)
        initial_dir = project_row["path"] if project_row and project_row["path"] and os.path.isdir(project_row["path"]) else os.path.expanduser("~")
        directory = filedialog.askdirectory(title="Выберите папку для сохранения", initialdir=initial_dir)
        if not directory:
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_'
                            for c in self.app.current_project)
        safe_name = safe_name.strip().replace(' ', '_')[:50]
        filename = f"Закупки_{safe_name}_{timestamp}.xlsx"
        full_path = os.path.join(directory, filename)
        if os.path.exists(full_path):
            if not messagebox.askyesno("Файл существует", f"Перезаписать файл?\n{full_path}"):
                return
        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Закупки"
            bold_font = Font(bold=True, size=11)
            header_font = Font(bold=True, color="FFFFFF", size=11)
            header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
            center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
            thin_border = Border(left=Side(style='thin'), right=Side(style='thin'),
                                 top=Side(style='thin'), bottom=Side(style='thin'))
            ws['A1'] = "ПРОЕКТ:"
            ws['A1'].font = bold_font
            ws['B1'] = self.app.current_project
            ws['B1'].font = bold_font
            ws['A2'] = "Дата экспорта:"
            ws['A2'].font = bold_font
            ws['B2'] = datetime.now().strftime("%d.%m.%Y %H:%M")
            ws['B2'].font = bold_font
            headers = [
                "№", "Производитель", "Подпроект", "КД", "Артикул",
                "Наименование (рус)", "Наименование (анг)", "Кол-во",
                "Заказано", "Дата заказа", "В заказ", "Получено", "Запрос цены", "Примечание"
            ]
            for col_idx, header in enumerate(headers, start=1):
                cell = ws.cell(row=4, column=col_idx, value=header)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = center_align
                cell.border = thin_border
            row_num = 5
            for p in purchases:
                p_dict = dict(p) if hasattr(p, 'keys') else p
                ordered_mark = "✓" if p_dict.get("ordered") else ""
                in_order_mark = "✓" if p_dict.get("in_order") else ""
                received_mark = "✓" if p_dict.get("received") else ""
                price_request_mark = "✓" if p_dict.get("price_request") else ""
                values = [
                    p_dict.get("number", ""),
                    p_dict.get("manufacturer", "") or "",
                    p_dict.get("subproject", "") or "",
                    p_dict.get("kd", "") or "",
                    p_dict.get("article", "") or "",
                    p_dict.get("name", "") or "",
                    p_dict.get("name_eng", "") or "",
                    p_dict.get("quantity", 0) or 0,
                    ordered_mark,
                    p_dict.get("order_date", "") or "",
                    in_order_mark,
                    received_mark,
                    price_request_mark,
                    p_dict.get("note", "") or "",
                ]
                for col_idx, val in enumerate(values, start=1):
                    cell = ws.cell(row=row_num, column=col_idx, value=val)
                    cell.border = thin_border
                    if col_idx in (1, 4, 8, 9, 10, 11, 12, 13):
                        cell.alignment = Alignment(horizontal="center", vertical="center")
                    elif col_idx in (6, 7, 14):
                        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
                    else:
                        cell.alignment = Alignment(vertical="center")
                row_num += 1
            for col_idx in range(1, len(headers) + 1):
                max_len = len(str(headers[col_idx - 1]))
                for r in range(5, row_num):
                    v = ws.cell(row=r, column=col_idx).value
                    if v is not None:
                        max_len = max(max_len, len(str(v)))
                col_letter = get_column_letter(col_idx)
                ws.column_dimensions[col_letter].width = min(max(max_len + 3, 10), 50)
            ws.freeze_panes = "A5"
            wb.save(full_path)
            self.app.log_action(f"Экспорт закупок в Excel: {full_path}")
            result = messagebox.askyesno("Успех",
                f"Данные экспортированы в Excel!\n\nФайл: {filename}\nСтрок: {row_num - 5}\nПапка: {directory}\n\nОткрыть файл?")
            if result:
                try:
                    opened = open_path(full_path)
                    if not opened:
                        messagebox.showinfo("Информация", f"Не удалось автоматически открыть файл.\nОткройте вручную:\n{full_path}")
                except Exception as e:
                    print(f"Не удалось открыть файл автоматически: {e}")
                    messagebox.showinfo("Информация", f"Файл сохранён здесь:\n{full_path}")
        except PermissionError:
            error_msg = (f"Нет прав на запись в папку или файл открыт в другой программе:\n{full_path}\n\n"
                         f"Закройте файл в Excel/LibreOffice и попробуйте снова.")
            messagebox.showerror("Ошибка доступа", error_msg)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"✗ Исключение при экспорте:\n{tb}")
            messagebox.showerror("Ошибка экспорта", f"Не удалось создать файл Excel:\n{e}\n\nПодробности в терминале.")


class ProjectChoiceDialog(tk.Toplevel):
    """НОВОЕ: мини-диалог выбора целевого проекта для переноса закупок."""
    def __init__(self, parent, project_names, count=1):
        super().__init__(parent)
        self.title("Сменить проект")
        self.geometry("460x140")
        self.resizable(False, False)
        self.result = None
        ttk.Label(self, text=f"Перенести позиций: {count} — в проект:").pack(padx=10, pady=(12, 6))
        self.combo = ttk.Combobox(self, values=project_names, state="readonly", width=40)
        self.combo.pack(padx=10)
        btnf = ttk.Frame(self)
        btnf.pack(pady=12)
        ttk.Button(btnf, text="ОК", command=self._ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btnf, text="Отмена", command=self.destroy).pack(side=tk.LEFT, padx=5)
        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _ok(self):
        self.result = self.combo.get() or None
        self.destroy()