import tkinter as tk
from tkinter import ttk, messagebox


class SubprojectDialog(tk.Toplevel):
    def __init__(self, parent, db_manager, project_name=None):
        super().__init__(parent)
        self.project_name = project_name or ""
        self.db_manager = db_manager
        self.current_id = None
        self.current_project = None

        title = f"Справочник подпроектов — {self.project_name}" if self.project_name else "Справочник подпроектов (все)"
        self.title(title)
        self.geometry("1000x550")
        self.resizable(True, True)

        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        columns = ("id", "name", "project_name")
        self.tree = ttk.Treeview(left_frame, columns=columns, show="headings", height=15)
        self.tree.heading("id", text="ID")
        self.tree.heading("name", text="Подпроект")
        self.tree.heading("project_name", text="Проект")
        self.tree.column("id", width=60, anchor="center")
        self.tree.column("name", width=350, anchor="w")
        self.tree.column("project_name", width=200, anchor="w")

        scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        right_frame = ttk.LabelFrame(main_frame, text="Добавить/Редактировать", padding=10)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, expand=False)

        ttk.Label(right_frame, text="Подпроект:").pack(anchor="w", pady=(0, 5))
        self.entry_subproject = ttk.Entry(right_frame, width=40)
        self.entry_subproject.pack(fill=tk.X, pady=(0, 20))

        ttk.Label(right_frame, text="Проект (пусто = общий):").pack(anchor="w", pady=(0, 5))
        self.combo_project = ttk.Combobox(right_frame, width=38)
        self.combo_project.pack(fill=tk.X, pady=(0, 10))
        self.combo_project['values'] = [''] + [p['name'] for p in self.db_manager.get_all_projects()]

        btn_frame = ttk.Frame(right_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="Добавить", command=self.add_record).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="Редактировать", command=self.edit_record).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="Удалить выбранное", command=self.delete_record).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="Закрыть", command=self.destroy).pack(fill=tk.X, pady=(20, 2))

        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.load_subprojects()
        self.grab_set()

    def load_subprojects(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        records = self.db_manager.get_subprojects(self.project_name if self.project_name else None)
        for r in records:
            self.tree.insert("", tk.END, values=(r['id'], r['name'] or "", r['project_name'] or ""))

    def on_select(self, event):
        selected = self.tree.selection()
        if selected:
            values = self.tree.item(selected[0])['values']
            self.current_id = values[0]
            self.current_project = values[2] or ""
            self.entry_subproject.delete(0, tk.END)
            self.entry_subproject.insert(0, values[1])
            self.combo_project.set(self.current_project)

    def add_record(self):
        name = self.entry_subproject.get().strip()
        project = self.combo_project.get().strip()
        if not name:
            messagebox.showwarning("Ошибка", "Введите название подпроекта!")
            return
        try:
            self.db_manager.add_subproject(name, project)
            self.entry_subproject.delete(0, tk.END)
            self.combo_project.set('')
            self.load_subprojects()
        except Exception as e:
            if 'UNIQUE' in str(e).upper() or 'unique' in str(e):
                messagebox.showwarning("Ошибка", f"Такой подпроект уже существует в проекте '{project or '(общий)'}'!")
            else:
                messagebox.showerror("Ошибка", f"Не удалось добавить подпроект:\n{e}")

    def edit_record(self):
        if self.current_id is None:
            messagebox.showwarning("Внимание", "Выберите запись для редактирования!")
            return
        new_name = self.entry_subproject.get().strip()
        new_project = self.combo_project.get().strip()
        if not new_name:
            messagebox.showwarning("Ошибка", "Введите название подпроекта!")
            return
        try:
            # Используем ID для обновления
            c = self.db_manager.conn.cursor()
            c.execute("UPDATE subprojects SET name=?, project_name=? WHERE id=?", 
                      (new_name, new_project, self.current_id))
            self.db_manager.conn.commit()
            self.load_subprojects()
        except Exception as e:
            if 'UNIQUE' in str(e).upper() or 'unique' in str(e):
                messagebox.showwarning("Ошибка", "Такая запись уже существует!")
            else:
                messagebox.showerror("Ошибка", f"Не удалось обновить подпроект:\n{e}")

    def delete_record(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите запись!")
            return
        if messagebox.askyesno("Подтверждение", "Удалить запись?"):
            try:
                # Используем ID для удаления
                c = self.db_manager.conn.cursor()
                c.execute("DELETE FROM subprojects WHERE id=?", (self.current_id,))
                self.db_manager.conn.commit()
                self.current_id = None
                self.entry_subproject.delete(0, tk.END)
                self.combo_project.set('')
                self.load_subprojects()
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось удалить подпроект:\n{e}")