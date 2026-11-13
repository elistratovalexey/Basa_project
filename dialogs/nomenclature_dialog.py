import tkinter as tk
from tkinter import ttk, messagebox


class NomenclatureDialog(tk.Toplevel):
    def __init__(self, parent, db_manager):
        super().__init__(parent)
        self.title("Справочник номенклатуры")
        self.geometry("1400x650")
        from dialogs.window_geometry import restore_geometry, track_geometry
        restore_geometry(self, "nomenclature_dialog", "1400x650")
        track_geometry(self, "nomenclature_dialog")
        self.resizable(True, True)
        self.db_manager = db_manager

        top_frame = ttk.Frame(self)
        top_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        columns = ("id", "manufacturer", "article", "name_rus", "name_eng")
        self.tree = ttk.Treeview(top_frame, columns=columns, show="headings", height=18)
        self.tree.heading("id", text="ID")
        self.tree.heading("manufacturer", text="Производитель")
        self.tree.heading("article", text="Артикул")
        self.tree.heading("name_rus", text="Наименование (рус)")
        self.tree.heading("name_eng", text="Наименование (анг)")
        self.tree.column("id", width=60, anchor="center")
        self.tree.column("manufacturer", width=180, anchor="w")
        self.tree.column("article", width=150, anchor="w")
        self.tree.column("name_rus", width=450, anchor="w")
        self.tree.column("name_eng", width=450, anchor="w")

        scrollbar = ttk.Scrollbar(top_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        bottom_frame = ttk.LabelFrame(self, text="Добавить/Редактировать запись", padding=10)
        bottom_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
        fields_frame = ttk.Frame(bottom_frame)
        fields_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(fields_frame, text="Производитель:").grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.entry_manufacturer = ttk.Entry(fields_frame, width=25)
        self.entry_manufacturer.grid(row=0, column=1, sticky="ew", padx=(0, 15))

        ttk.Label(fields_frame, text="Артикул:").grid(row=0, column=2, sticky="w", padx=(0, 5))
        self.entry_article = ttk.Entry(fields_frame, width=25)
        self.entry_article.grid(row=0, column=3, sticky="ew", padx=(0, 15))

        ttk.Label(fields_frame, text="Наим. рус:").grid(row=0, column=4, sticky="w", padx=(0, 5))
        self.entry_name_rus = ttk.Entry(fields_frame, width=35)
        self.entry_name_rus.grid(row=0, column=5, sticky="ew", padx=(0, 15))

        ttk.Label(fields_frame, text="Наим. анг:").grid(row=0, column=6, sticky="w", padx=(0, 5))
        self.entry_name_eng = ttk.Entry(fields_frame, width=35)
        self.entry_name_eng.grid(row=0, column=7, sticky="ew")

        fields_frame.grid_columnconfigure(1, weight=1)
        fields_frame.grid_columnconfigure(3, weight=1)
        fields_frame.grid_columnconfigure(5, weight=1)
        fields_frame.grid_columnconfigure(7, weight=1)

        btn_frame = ttk.Frame(bottom_frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Добавить", command=self.add_record).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Редактировать", command=self.edit_record).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Удалить выбранное", command=self.delete_record).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Закрыть", command=self.destroy).pack(side=tk.RIGHT, padx=5)

        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.load_nomenclature()
        self.grab_set()

    def load_nomenclature(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for r in self.db_manager.get_nomenclature():
            self.tree.insert("", tk.END, values=(
                r['id'], r['manufacturer'] or "", r['article'] or "",
                r['name_rus'] or "", r['name_eng'] or ""
            ))

    def on_select(self, event):
        selected = self.tree.selection()
        if selected:
            values = self.tree.item(selected[0])['values']
            self.entry_manufacturer.delete(0, tk.END)
            self.entry_manufacturer.insert(0, values[1])
            self.entry_article.delete(0, tk.END)
            self.entry_article.insert(0, values[2])
            self.entry_name_rus.delete(0, tk.END)
            self.entry_name_rus.insert(0, values[3])
            self.entry_name_eng.delete(0, tk.END)
            self.entry_name_eng.insert(0, values[4])

    def add_record(self):
        if not self.entry_manufacturer.get() or not self.entry_article.get():
            messagebox.showwarning("Ошибка", "Производитель и Артикул обязательны!")
            return
        self.db_manager.add_nomenclature({
            "manufacturer": self.entry_manufacturer.get(),
            "article": self.entry_article.get(),
            "name_rus": self.entry_name_rus.get(),
            "name_eng": self.entry_name_eng.get()
        })
        self.entry_manufacturer.delete(0, tk.END)
        self.entry_article.delete(0, tk.END)
        self.entry_name_rus.delete(0, tk.END)
        self.entry_name_eng.delete(0, tk.END)
        self.load_nomenclature()

    def edit_record(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите запись для редактирования!")
            return
        old_article = self.tree.item(selected[0])['values'][2]
        self.db_manager.conn.cursor().execute('''UPDATE nomenclature SET
            manufacturer=?, article=?, name_rus=?, name_eng=? WHERE article=?''',
            (self.entry_manufacturer.get(), self.entry_article.get(),
             self.entry_name_rus.get(), self.entry_name_eng.get(), old_article))
        self.db_manager.conn.commit()
        self.load_nomenclature()

    def delete_record(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите запись!")
            return
        if messagebox.askyesno("Подтверждение", "Удалить запись?"):
            record_id = self.tree.item(selected[0])['values'][0]
            cursor = self.db_manager.conn.cursor()
            cursor.execute('DELETE FROM nomenclature WHERE id=?', (record_id,))
            self.db_manager.conn.commit()
            self.load_nomenclature()