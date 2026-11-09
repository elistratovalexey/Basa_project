import tkinter as tk
from tkinter import ttk, messagebox


class SupplierDialog(tk.Toplevel):
    def __init__(self, parent, db_manager):
        super().__init__(parent)
        self.title("Справочник поставщиков")
        self.geometry("700x450")
        from dialogs.window_geometry import restore_geometry, track_geometry
        restore_geometry(self, "КЛЮЧ", "ШИРИНАxВЫСОТА")
        track_geometry(self, "КЛЮЧ")
        self.resizable(True, True)
        self.db_manager = db_manager

        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        columns = ("id", "name")
        self.tree = ttk.Treeview(left_frame, columns=columns, show="headings", height=15)
        self.tree.heading("id", text="ID")
        self.tree.heading("name", text="Поставщик")
        self.tree.column("id", width=60, anchor="center")
        self.tree.column("name", width=400, anchor="w")

        scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        right_frame = ttk.LabelFrame(main_frame, text="Добавить/Редактировать", padding=10)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, expand=False)

        ttk.Label(right_frame, text="Поставщик:").pack(anchor="w", pady=(0, 5))
        self.entry_name = ttk.Entry(right_frame, width=40)
        self.entry_name.pack(fill=tk.X, pady=(0, 20))

        btn_frame = ttk.Frame(right_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="Добавить", command=self.add_record).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="Редактировать", command=self.edit_record).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="Удалить выбранное", command=self.delete_record).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="Закрыть", command=self.destroy).pack(fill=tk.X, pady=(20, 2))

        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.load_suppliers()
        self.grab_set()

    def load_suppliers(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for r in self.db_manager.get_suppliers():
            self.tree.insert("", tk.END, values=(r['id'], r['name'] or ""))

    def on_select(self, event):
        selected = self.tree.selection()
        if selected:
            values = self.tree.item(selected[0])['values']
            self.entry_name.delete(0, tk.END)
            self.entry_name.insert(0, values[1])

    def add_record(self):
        name = self.entry_name.get().strip()
        if not name:
            messagebox.showwarning("Ошибка", "Введите название поставщика!")
            return
        # Передаём словарь, как ожидает database.py
        success = self.db_manager.add_supplier({'name': name})
        if not success:
            messagebox.showwarning("Ошибка", "Такой поставщик уже существует!")
            return
        self.entry_name.delete(0, tk.END)
        self.load_suppliers()

    def edit_record(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите запись!")
            return
        # Берём ID из первой колонки
        supplier_id = self.tree.item(selected[0])['values'][0]
        new_name = self.entry_name.get().strip()
        if not new_name:
            messagebox.showwarning("Ошибка", "Введите название поставщика!")
            return
        # Передаём id и словарь
        self.db_manager.update_supplier(supplier_id, {'name': new_name})
        self.load_suppliers()

    def delete_record(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите запись!")
            return
        if messagebox.askyesno("Подтверждение", "Удалить поставщика?"):
            supplier_id = self.tree.item(selected[0])['values'][0]
            self.db_manager.delete_supplier(supplier_id)
            self.load_suppliers()
