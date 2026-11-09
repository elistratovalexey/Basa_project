import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os

SORT_OPTIONS = {
    "name": "По названию",
    "contract_date": "Дата договора (новые сверху)",
    "id": "По порядку создания",
}


class SettingsDialog(tk.Toplevel):
    """Настройки: папка базы данных и сортировка проектов.

    После закрытия окна self.result == True, если настройки изменены.
    Вызывающий код должен дождаться закрытия: root.wait_window(dialog).
    """

    def __init__(self, parent, config_manager):
        super().__init__(parent)
        self.title("Настройки")
        self.geometry("640x200")
        from dialogs.window_geometry import restore_geometry, track_geometry
        restore_geometry(self, "КЛЮЧ", "ШИРИНАxВЫСОТА")
        track_geometry(self, "КЛЮЧ")
        self.transient(parent)
        self.config_manager = config_manager
        self.result = False
        self.db_changed = False

        frame_db = ttk.Frame(self)
        frame_db.pack(fill="x", padx=10, pady=10)
        ttk.Label(frame_db, text="Папка базы:").pack(side=tk.LEFT, padx=(0, 10))
        self.entry_db = ttk.Entry(frame_db)
        self.entry_db.pack(side=tk.LEFT, fill="x", expand=True, padx=(0, 5))
        self._initial_dir = os.path.dirname(config_manager.get("db_path", "projects.db")) or "."
        self.entry_db.insert(0, self._initial_dir)
        ttk.Button(frame_db, text="Обзор", command=self.browse).pack(side=tk.LEFT)

        frame_sort = ttk.Frame(self)
        frame_sort.pack(fill="x", padx=10, pady=5)
        ttk.Label(frame_sort, text="Сортировка проектов:").pack(side=tk.LEFT, padx=(0, 10))
        self.combo_sort = ttk.Combobox(frame_sort, state="readonly", width=32,
                                       values=list(SORT_OPTIONS.values()))
        self.combo_sort.pack(side=tk.LEFT)
        current_sort = config_manager.get("sort_by", "name")
        self.combo_sort.set(SORT_OPTIONS.get(current_sort, SORT_OPTIONS["name"]))

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=15)
        ttk.Button(btn_frame, text="Сохранить", command=self.save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self.destroy).pack(side=tk.LEFT, padx=5)
        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()

    def browse(self):
        directory = filedialog.askdirectory(initialdir=self.entry_db.get(), parent=self)
        if directory:
            self.entry_db.delete(0, tk.END)
            self.entry_db.insert(0, directory)

    def save(self):
        db_dir = self.entry_db.get().strip()
        if not db_dir:
            messagebox.showwarning("Ошибка", "Укажите директорию!", parent=self)
            return
        if not os.path.isabs(db_dir):
            db_dir = os.path.abspath(db_dir)
        if not os.path.exists(db_dir):
            if messagebox.askyesno("Подтверждение", f"Создать {db_dir}?", parent=self):
                try:
                    os.makedirs(db_dir)
                except OSError as e:
                    messagebox.showerror("Ошибка", f"Не удалось создать папку:\n{e}", parent=self)
                    return
            else:
                return
        from config import DEFAULT_DB_NAME, CONFIG_NAME
        new_db = os.path.join(db_dir, DEFAULT_DB_NAME)
        old_db = self.config_manager.get("db_path", "")
        self.db_changed = os.path.normcase(os.path.abspath(new_db)) != os.path.normcase(os.path.abspath(old_db or ""))

        sort_key = next((k for k, v in SORT_OPTIONS.items() if v == self.combo_sort.get()), "name")
        self.config_manager.config["sort_by"] = sort_key
        self.config_manager.config["sort_by_display"] = SORT_OPTIONS[sort_key]
        self.config_manager.set("db_path", new_db)
        # Копия конфигурации рядом с базой (для переноса базы на другой ПК)
        self.config_manager.save_config(os.path.join(db_dir, CONFIG_NAME))
        self.result = True
        messagebox.showinfo("Успех", f"Сохранено!\nБД: {new_db}", parent=self)
        self.destroy()
