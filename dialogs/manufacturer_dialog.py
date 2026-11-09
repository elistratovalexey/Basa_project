import tkinter as tk
from tkinter import ttk, messagebox


class ManufacturerDialog(tk.Toplevel):
    def __init__(self, parent, db_manager):
        super().__init__(parent)
        self.title("Справочник производителей")
        self.geometry("900x500")
        self.resizable(True, True)
        self.db_manager = db_manager

        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        columns = ("id", "name")
        self.tree = ttk.Treeview(left_frame, columns=columns, show="headings", height=15)
        self.tree.heading("id", text="ID")
        self.tree.heading("name", text="Производитель")
        self.tree.column("id", width=80, anchor="center")
        self.tree.column("name", width=500, anchor="w")
        scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        right_frame = ttk.LabelFrame(main_frame, text="Добавить/Редактировать", padding=10)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, expand=False)
        ttk.Label(right_frame, text="Производитель:").pack(anchor="w", pady=(0, 5))
        self.entry_manufacturer = ttk.Entry(right_frame, width=40)
        self.entry_manufacturer.pack(fill=tk.X, pady=(0, 20))

        btn_frame = ttk.Frame(right_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="Добавить", command=self.add_record).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="Редактировать", command=self.edit_record).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="Удалить выбранное", command=self.delete_record).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="Закрыть", command=self.destroy).pack(fill=tk.X, pady=(20, 2))

        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.load_manufacturers()
        self.grab_set()

    def load_manufacturers(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for r in self.db_manager.get_manufacturers():
            self.tree.insert("", tk.END, values=(r['id'], r['name'] or ""))

    def on_select(self, event):
        selected = self.tree.selection()
        if selected:
            values = self.tree.item(selected[0])['values']
            self.entry_manufacturer.delete(0, tk.END)
            self.entry_manufacturer.insert(0, values[1])

    def add_record(self):
        name = self.entry_manufacturer.get().strip()
        if not name:
            messagebox.showwarning("Ошибка", "Введите название производителя!")
            return
        self.db_manager.add_manufacturer(name)
        self.entry_manufacturer.delete(0, tk.END)
        self.load_manufacturers()

    def edit_record(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите запись для редактирования!")
            return
        old_name = self.tree.item(selected[0])['values'][1]
        new_name = self.entry_manufacturer.get().strip()
        if not new_name:
            messagebox.showwarning("Ошибка", "Введите название производителя!")
            return
        old_name = str(old_name)
        if new_name == old_name:
            return
        if not self.db_manager.rename_manufacturer(old_name, new_name):
            messagebox.showwarning("Ошибка", f"Производитель «{new_name}» уже существует!")
            return
        self.load_manufacturers()

    def delete_record(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите запись!")
            return
        if messagebox.askyesno("Подтверждение", "Удалить запись?"):
            record_id = self.tree.item(selected[0])['values'][0]
            cursor = self.db_manager.conn.cursor()
            cursor.execute('DELETE FROM manufacturers WHERE id=?', (record_id,))
            self.db_manager.conn.commit()
            self.load_manufacturers()