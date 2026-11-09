import tkinter as tk
from tkinter import ttk, messagebox


class KDDialog(tk.Toplevel):
    def __init__(self, parent, db_manager, project_name=None):
        super().__init__(parent)
        self.project_name = project_name or ""
        self.db_manager = db_manager
        self.current_id = None

        title = f"Справочник КД — {self.project_name}" if self.project_name else "Справочник КД (все)"
        self.title(title)
        self.geometry("1000x550")
        self.resizable(True, True)

        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        columns = ("id", "kd_number", "kd_name", "project_name")
        self.tree = ttk.Treeview(left_frame, columns=columns, show="headings", height=15)
        self.tree.heading("id", text="ID")
        self.tree.heading("kd_number", text="Номер КД")
        self.tree.heading("kd_name", text="Наименование КД")
        self.tree.heading("project_name", text="Проект")
        self.tree.column("id", width=60, anchor="center")
        self.tree.column("kd_number", width=100, anchor="w")
        self.tree.column("kd_name", width=350, anchor="w")
        self.tree.column("project_name", width=200, anchor="w")

        scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        right_frame = ttk.LabelFrame(main_frame, text="Добавить/Редактировать КД", padding=10)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, expand=False)

        ttk.Label(right_frame, text="Номер КД:").pack(anchor="w", pady=(0, 5))
        self.entry_kd_number = ttk.Entry(right_frame, width=40)
        self.entry_kd_number.pack(fill=tk.X, pady=(0, 20))

        ttk.Label(right_frame, text="Наименование:").pack(anchor="w", pady=(0, 5))
        self.entry_name = ttk.Entry(right_frame, width=40)
        self.entry_name.pack(fill=tk.X, pady=(0, 20))

        ttk.Label(right_frame, text="Проект (пусто = общий):").pack(anchor="w", pady=(0, 5))
        self.combo_project = ttk.Combobox(right_frame, width=38)
        self.combo_project.pack(fill=tk.X, pady=(0, 10))
        self.combo_project['values'] = [''] + self._get_projects()
        if project_name:
            self.combo_project.set(project_name)

        btn_frame = ttk.Frame(right_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="Добавить", command=self.add_record).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="Редактировать", command=self.edit_record).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="Удалить выбранное", command=self.delete_record).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="Закрыть", command=self.destroy).pack(fill=tk.X, pady=(20, 2))

        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.load_kd()
        self.grab_set()

    def _get_projects(self):
        """Получить список проектов"""
        try:
            c = self.db_manager.conn.cursor()
            c.execute("SELECT DISTINCT name FROM projects ORDER BY name")
            return [row[0] for row in c.fetchall()]
        except:
            return []

    def load_kd(self):
        """Загрузить список КД"""
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        try:
            c = self.db_manager.conn.cursor()
            
            if self.project_name:
                c.execute('''SELECT id, kd_number, kd_name, project_name 
                            FROM kd_directory 
                            WHERE project_name=? OR project_name IS NULL OR project_name=''
                            ORDER BY kd_number''', (self.project_name,))
            else:
                c.execute("SELECT id, kd_number, kd_name, project_name FROM kd_directory ORDER BY kd_number")
            
            rows = c.fetchall()
            print(f"Загружено {len(rows)} записей КД")
            
            for row in rows:
                self.tree.insert("", tk.END, values=(
                    row[0], 
                    row[1] or "", 
                    row[2] or "", 
                    row[3] or ""
                ))
                
        except Exception as e:
            print(f"Ошибка загрузки КД: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Ошибка", f"Не удалось загрузить КД:\n{e}")

    def on_select(self, event):
        """При выборе записи - заполнить форму"""
        selected = self.tree.selection()
        if selected:
            values = self.tree.item(selected[0])['values']
            self.current_id = values[0]
            self.entry_kd_number.delete(0, tk.END)
            self.entry_kd_number.insert(0, values[1])
            self.entry_name.delete(0, tk.END)
            self.entry_name.insert(0, values[2])
            self.combo_project.set(values[3] if len(values) > 3 else "")

    def add_record(self):
        """Добавить новую запись КД"""
        kd_number = self.entry_kd_number.get().strip()
        kd_name = self.entry_name.get().strip()
        project = self.combo_project.get().strip()
        
        if not kd_number or not kd_name:
            messagebox.showwarning("Ошибка", "Введите номер КД и наименование!")
            return
        
        try:
            c = self.db_manager.conn.cursor()
            c.execute('''INSERT INTO kd_directory (kd_number, kd_name, project_name) 
                        VALUES (?, ?, ?)''', (kd_number, kd_name, project if project else None))
            self.db_manager.conn.commit()
            self.entry_kd_number.delete(0, tk.END)
            self.entry_name.delete(0, tk.END)
            self.combo_project.set('')
            self.load_kd()
            messagebox.showinfo("Успех", "КД добавлен!")
        except Exception as e:
            if 'UNIQUE' in str(e).upper() or 'unique' in str(e):
                messagebox.showwarning("Ошибка", f"Такой номер КД уже существует в проекте '{project or '(общий)'}'!")
            else:
                messagebox.showerror("Ошибка", f"Не удалось добавить КД:\n{e}")

    def edit_record(self):
        """Редактировать выбранную запись КД"""
        if self.current_id is None:
            messagebox.showwarning("Внимание", "Выберите запись для редактирования!")
            return
        
        kd_number = self.entry_kd_number.get().strip()
        kd_name = self.entry_name.get().strip()
        project = self.combo_project.get().strip()
        
        if not kd_number or not kd_name:
            messagebox.showwarning("Ошибка", "Введите номер КД и наименование!")
            return
        
        try:
            c = self.db_manager.conn.cursor()
            c.execute('''UPDATE kd_directory 
                        SET kd_number=?, kd_name=?, project_name=? 
                        WHERE id=?''', (kd_number, kd_name, project if project else None, self.current_id))
            self.db_manager.conn.commit()
            self.load_kd()
            messagebox.showinfo("Успех", "КД обновлён!")
        except Exception as e:
            if 'UNIQUE' in str(e).upper() or 'unique' in str(e):
                messagebox.showwarning("Ошибка", "Такая запись уже существует!")
            else:
                messagebox.showerror("Ошибка", f"Не удалось обновить КД:\n{e}")

    def delete_record(self):
        """Удалить выбранную запись КД"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите запись!")
            return
        
        if messagebox.askyesno("Подтверждение", "Удалить запись КД?"):
            try:
                c = self.db_manager.conn.cursor()
                c.execute("DELETE FROM kd_directory WHERE id=?", (self.current_id,))
                self.db_manager.conn.commit()
                self.current_id = None
                self.entry_kd_number.delete(0, tk.END)
                self.entry_name.delete(0, tk.END)
                self.combo_project.set('')
                self.load_kd()
                messagebox.showinfo("Успех", "КД удалён!")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось удалить КД:\n{e}")