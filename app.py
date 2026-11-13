import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, scrolledtext
import os
import holidays
import traceback
import logging
from datetime import datetime
import config as cfg
from config import (
    VERSION, BUILD_DATE, DEFAULT_DB_NAME, CURRENCIES, BACKUP_KEEP,
    ConfigManager, setup_paths
)
from utils import open_path
from database import DatabaseManager
from tabs import (FinancesTab, SpecificationTab, PurchasesTab, PurchaseSpecTab,
                  DeadlinesTab, DashboardTab, BudgetTab, PlanFactTab)
from settings_dialog import SettingsDialog
from dialogs.window_geometry import restore_geometry, track_geometry
import terminal_log
terminal_log.install(os.path.join(cfg.APP_DIR, "logs"))

# =================================================================
# ГЛОБАЛЬНАЯ ЗАЩИТА от "TclError: grab failed: window not viewable".
# Диалоги, открытые двойным кликом, иногда вызывают grab_set() раньше,
# чем окно успевает отрисоваться. Патчим Toplevel.grab_set один раз:
# он повторяет попытку, пока окно не станет видимым, и молча пропускает
# grab, если окно уже уничтожено или родитель свёрнут.
# =================================================================
_original_toplevel_grab_set = tk.Toplevel.grab_set


def _safe_toplevel_grab_set(self, _attempts=8):
    def _try(attempts=_attempts):
        try:
            if self.winfo_exists() and self.winfo_viewable():
                _original_toplevel_grab_set(self)
            elif attempts > 0:
                self.after(60, lambda: _try(attempts - 1))
        except tk.TclError:
            if attempts > 0:
                try:
                    self.after(60, lambda: _try(attempts - 1))
                except tk.TclError:
                    pass
    _try()


tk.Toplevel.grab_set = _safe_toplevel_grab_set

class ProjectManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Управление проектами v{VERSION}")
        self.root.geometry("1300x950")
        self.root.minsize(1200, 800)
        restore_geometry(self.root, "main_window", "1300x950")
        track_geometry(self.root, "main_window")

        self.config_manager = ConfigManager(cfg.LOCAL_CONFIG_FILE)
        self.db_manager = self._open_database(self.config_manager.get("db_path", DEFAULT_DB_NAME))
        self.setup_logging()
        self.root.report_callback_exception = self.on_tk_exception
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.current_project = None
        self.russian_holidays = holidays.Russia()
        self.payment_counter = 1
        self.spec_counter = 1
        self.purchase_counter = 1
        self.current_purchase_spec_id = None

        self._log_history = []
        self.log_window = None
        self.log_text_popup = None

        self.create_widgets()
        self.load_projects()
        self.log_action(f"Программа запущена v{VERSION}")
        self.log_action(f"База данных: {cfg.get_db_path()}")
        self.make_backup(silent=True)
        self.update_datetime()
        if self.combo_projects["values"]:
            self.combo_projects.set(self.combo_projects["values"][0])
            self.on_project_select()
            
        try:
            from reminders import start_reminders
            start_reminders(self, interval_min=60)
        except Exception as e:
            print(f"Напоминания не запущены: {e}")

    def _open_database(self, db_path):
        path = setup_paths(db_path)
        local_db = os.path.join(cfg.APP_DIR, DEFAULT_DB_NAME)
        if not os.path.isdir(os.path.dirname(path)) and os.path.exists(local_db):
            print(f"Папка {os.path.dirname(path)} недоступна, используется {local_db}")
            path = setup_paths(local_db)
        try:
            return DatabaseManager(path)
        except Exception as e:
            messagebox.showwarning(
                "База данных недоступна",
                f"Не удалось открыть базу:\n{path}\n\n{e}\n\n"
                "Проверьте, подключён ли сетевой диск, или выберите другую папку.")
            folder = filedialog.askdirectory(title="Папка с базой projects.db")
            if not folder:
                raise
            path = setup_paths(os.path.join(folder, DEFAULT_DB_NAME))
            self.config_manager.set("db_path", path)
            return DatabaseManager(path)

    def setup_logging(self):
        self.logger = logging.getLogger('ProjectManager')
        self.logger.setLevel(logging.DEBUG)
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)
        formatter = logging.Formatter('[%(asctime)s] %(message)s', '%d.%m.%Y %H:%M:%S')
        file_handler = None
        for log_file in (cfg.get_log_file(), os.path.join(cfg.APP_DIR, cfg.LOG_NAME)):
            try:
                file_handler = logging.FileHandler(log_file, encoding='utf-8')
                break
            except OSError:
                file_handler = None
        if file_handler:
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

    def log_action(self, message):
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logger.info(message)
        self._log_history.append(log_entry)
        if len(self._log_history) > 1000:
            self._log_history = self._log_history[-1000:]
        try:
            self.log_text.config(state="normal")
            self.log_text.insert(tk.END, log_entry + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state="disabled")
        except Exception:
            pass
        popup = getattr(self, 'log_text_popup', None)
        if popup is not None and popup.winfo_exists():
            try:
                popup.config(state="normal")
                popup.insert(tk.END, log_entry + "\n")
                popup.see(tk.END)
                popup.config(state="disabled")
            except Exception:
                pass

    def on_tk_exception(self, exc_type, exc_value, exc_tb):
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            self.logger.error("ОШИБКА:\n" + tb_text)
        except Exception:
            print(tb_text)
        messagebox.showerror("Ошибка", f"{exc_type.__name__}: {exc_value}\n\n"
                             f"Подробности записаны в журнал:\n{cfg.get_log_file()}")

    def make_backup(self, silent=False):
        target = self.db_manager.backup(cfg.get_backup_dir(), keep=BACKUP_KEEP)
        if target:
            self.log_action(f"Резервная копия БД: {target}")
            if not silent:
                messagebox.showinfo("Резервная копия", f"Создана копия базы:\n{target}")
        elif not silent:
            messagebox.showerror("Резервная копия", "Не удалось создать резервную копию (см. консоль)")

    def on_close(self):
        try:
            self.save_window_geometry()
        except Exception:
            pass
        try:
            self.save_current_project_data()
        except Exception as e:
            print(f"Ошибка сохранения при выходе: {e}")
        try:
            self.db_manager.close()
        except Exception:
            pass
        try:
            terminal_log.session_end()
        except Exception:
            pass
        self.root.destroy()

    def save_window_geometry(self):
        try:
            self.config_manager.set("main_window_geometry", self.root.geometry())
        except Exception as e:
            print(f"Ошибка сохранения геометрии: {e}")

    def restore_window_geometry(self):
        try:
            g = self.config_manager.get("main_window_geometry")
            if g:
                self.root.geometry(g)
        except Exception as e:
            print(f"Ошибка восстановления геометрии: {e}")

    def calculate_dates(self):
        if hasattr(self, "deadlines_tab"):
            self.deadlines_tab.calculate_dates()

    def update_datetime(self):
        now = datetime.now()
        self.lbl_datetime.config(text=now.strftime("%d.%m.%Y %H:%M:%S"))
        self.root.after(1000, self.update_datetime)

    def paste_from_clipboard(self, event):
        widget = event.widget
        try:
            clipboard_data = self.root.clipboard_get()
            try:
                start = widget.index(tk.SEL_FIRST)
                end = widget.index(tk.SEL_LAST)
                widget.delete(start, end)
            except:
                pass
            widget.insert(tk.INSERT, clipboard_data)
            return "break"
        except Exception:
            return None

    def create_widgets(self):
        style = ttk.Style()
        style.configure("TNotebook.Tab", padding=[12, 6], font=("Arial", 9, "bold"),
                        background="#1976D2", foreground="black", borderwidth=1, relief="raised")
        style.map("TNotebook.Tab",
                  background=[("selected", "#0D47A1"), ("!selected", "#42A5F5")],
                  foreground=[("selected", "black"), ("!selected", "black")],
                  relief=[("selected", "sunken"), ("!selected", "raised")])
        style.configure('Orders.TButton', background='#FF6B00', foreground='black',
                        font=('Arial', 10, 'bold'))
        style.map('Orders.TButton',
                  background=[('active', '#FF8533'), ('pressed', '#CC5500')],
                  foreground=[('active', 'black'), ('pressed', 'black')])

        frame_top = ttk.Frame(self.root)
        frame_top.pack(fill="x", padx=10, pady=5)
        ttk.Label(frame_top, text=f"Версия: {VERSION} (от {BUILD_DATE})",
                  font=("Arial", 9, "italic")).pack(side=tk.LEFT)
        self.lbl_datetime = ttk.Label(frame_top, text="", font=("Arial", 9, "bold"))
        self.lbl_datetime.pack(side=tk.RIGHT)
        ttk.Button(frame_top, text="Сохранить проект", command=self.save_current_project).pack(side=tk.RIGHT, padx=10)
        ttk.Button(frame_top, text="📄 Лог терминала", command=self.open_terminal_log).pack(side=tk.RIGHT, padx=5)
        ttk.Button(frame_top, text="📋 Журнал (окно)", command=self.toggle_log_window).pack(side=tk.RIGHT, padx=5)

        frame_project = ttk.LabelFrame(self.root, text="Проект", padding=10)
        frame_project.pack(fill="x", padx=10, pady=5)
        nav_frame = ttk.Frame(frame_project)
        nav_frame.grid(row=0, column=0, columnspan=6, sticky="w", pady=5)
        ttk.Button(nav_frame, text="◀ Пред", command=self.prev_project).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav_frame, text="След ▶", command=self.next_project).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav_frame, text="Добавить", command=self.add_project).pack(side=tk.LEFT, padx=10)
        ttk.Button(nav_frame, text="Переименовать", command=self.rename_project).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav_frame, text="Сменить папку", command=self.change_project_dir).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav_frame, text="Удалить", command=self.delete_project).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav_frame, text="Резервная копия БД",
                   command=lambda: self.make_backup(silent=False)).pack(side=tk.LEFT, padx=10)

        ttk.Label(frame_project, text="Проект:").grid(row=1, column=0, sticky="w", pady=5)
        self.combo_projects = ttk.Combobox(frame_project, state="readonly", width=40)
        self.combo_projects.grid(row=1, column=1, sticky="w", padx=5)
        self.combo_projects.bind("<<ComboboxSelected>>", self.on_project_select)
        ttk.Button(frame_project, text="Открыть папку", command=self.open_project_dir).grid(row=1, column=2, padx=5)
        ttk.Button(frame_project, text="Настройки", command=self.open_settings).grid(row=1, column=3, padx=5)
        ttk.Label(frame_project, text="Адрес доставки:").grid(row=2, column=0, sticky="w", pady=5)
        self.entry_delivery_address = ttk.Entry(frame_project, width=60)
        self.entry_delivery_address.grid(row=2, column=1, columnspan=3, sticky="ew", padx=5)

        frame_log = ttk.LabelFrame(self.root, text="Журнал", padding=5)
        frame_log.pack(side=tk.BOTTOM, fill="x", padx=10, pady=(0, 5))
        self.log_text = scrolledtext.ScrolledText(frame_log, height=4, state="disabled", wrap=tk.WORD)
        self.log_text.pack(fill="x")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)

        # --- v1.9: Дашборд (первая вкладка) ---
        frame_dash = ttk.Frame(self.notebook)
        self.notebook.add(frame_dash, text="Сегодня")
        self.dashboard_tab = DashboardTab(self, frame_dash)

        tab_finances = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab_finances, text="  Финансы  ")
        self.finances_tab = FinancesTab(self, tab_finances)

        tab_spec = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab_spec, text="  Спецификация  ")
        self.specification_tab = SpecificationTab(self, tab_spec)

        tab_purchases = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab_purchases, text="  Закупки  ")
        self.purchases_tab = PurchasesTab(self, tab_purchases)

        tab_purchase_spec = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab_purchase_spec, text="  Спецификация Закупок  ")
        self.purchase_spec_tab = PurchaseSpecTab(self, tab_purchase_spec)

        tab_deadlines = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab_deadlines, text="  Сроки  ")
        self.deadlines_tab = DeadlinesTab(self, tab_deadlines)
        tab_pf = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab_pf, text="  План-Факт  ")
        self.plan_fact_tab = PlanFactTab(self, tab_pf)

        # --- v1.9: Бюджет (после «Сроки») ---
        frame_budget = ttk.Frame(self.notebook)
        self.notebook.add(frame_budget, text="Бюджет")
        self.budget_tab = BudgetTab(self, frame_budget)        

        for cls in ("TEntry", "Entry", "TCombobox"):
            for seq in ("<Control-v>", "<Control-V>"):
                self.root.bind_class(cls, seq, self.paste_from_clipboard)

    def open_terminal_log(self):
        p = terminal_log.get_path()
        if p and os.path.exists(p):
            open_path(p)
        else:
            messagebox.showinfo("Лог терминала", "Файл лога терминала не найден")

    def toggle_log_window(self):
        win = getattr(self, 'log_window', None)
        if win is not None and win.winfo_exists():
            win.destroy()
            self.log_window = None
            self.log_text_popup = None
            return
        self.log_window = tk.Toplevel(self.root)
        self.log_window.title("Журнал действий")
        self.log_window.geometry("1000x420")
        self.log_text_popup = scrolledtext.ScrolledText(
            self.log_window, state="disabled", wrap=tk.WORD, font=("Consolas", 9))
        self.log_text_popup.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_text_popup.config(state="normal")
        for line in self._log_history:
            self.log_text_popup.insert(tk.END, line + "\n")
        self.log_text_popup.config(state="disabled")
        self.log_text_popup.see(tk.END)
        self.log_window.protocol("WM_DELETE_WINDOW", self._close_log_window)

    def _close_log_window(self):
        try:
            if getattr(self, 'log_window', None) is not None:
                self.log_window.destroy()
        except Exception:
            pass
        self.log_window = None
        self.log_text_popup = None

    def open_settings(self):
        self.save_current_project_data()
        dialog = SettingsDialog(self.root, self.config_manager)
        self.root.wait_window(dialog)
        if not dialog.result:
            return
        if dialog.db_changed:
            old_manager = self.db_manager
            try:
                self.db_manager = self._open_database(self.config_manager.get("db_path", DEFAULT_DB_NAME))
            except Exception as e:
                self.db_manager = old_manager
                messagebox.showerror("Ошибка", f"Не удалось открыть новую базу:\n{e}")
                return
            old_manager.close()
            self.setup_logging()
            self.log_action(f"База данных изменена: {cfg.get_db_path()}")
        self.current_project = None
        self.load_projects()
        values = self.combo_projects["values"]
        if values:
            self.combo_projects.set(values[0])
        else:
            self.combo_projects.set("")
        self.on_project_select()

    def save_current_project_data(self):
        if not self.current_project or not self.db_manager.get_project(self.current_project):
            return
        data = {
            "contract_date": self.entry_contract_date.get(),
            "contract_amount": self.entry_contract_amount.get(),
            "contract_currency": self.combo_contract_currency.get(),
            "del_term": self.entry_del_term.get(),
            "del_unit": self.combo_del_unit.get(),
            "del_base_date": self.del_base_var.get(),
            "confirmation_date": self.entry_confirmation_date.get(),
            "work_start": self.entry_work_start.get(),
            "work_term": self.entry_work_term.get(),
            "work_unit": self.combo_work_unit.get(),
            "delivery_address": self.entry_delivery_address.get(),
        }
        self.db_manager.update_project(self.current_project, data)

    def prev_project(self):
        if not self.current_project:
            return
        names = list(self.combo_projects["values"])
        if self.current_project in names:
            idx = names.index(self.current_project)
            if idx > 0:
                self.combo_projects.set(names[idx - 1])
                self.on_project_select()

    def next_project(self):
        if not self.current_project:
            return
        names = list(self.combo_projects["values"])
        if self.current_project in names:
            idx = names.index(self.current_project)
            if idx < len(names) - 1:
                self.combo_projects.set(names[idx + 1])
                self.on_project_select()

    def delete_project(self):
        if not self.current_project:
            messagebox.showwarning("Внимание", "Выберите проект!")
            return
        if messagebox.askyesno("Подтверждение",
                               f"Удалить '{self.current_project}'?\n\n"
                               "Будут удалены платежи, спецификации и закупки проекта.\n"
                               "Перед удалением будет сделана резервная копия базы."):
            self.make_backup(silent=True)
            deleted = self.current_project
            self.db_manager.delete_project(deleted)
            self.log_action(f"Удалён проект: {deleted}")
            self.current_project = None
            self.load_projects()
            if self.combo_projects["values"]:
                self.combo_projects.set(self.combo_projects["values"][0])
                self.on_project_select()

    def rename_project(self):
        if not self.current_project:
            messagebox.showwarning("Внимание", "Выберите проект!")
            return
        new_name = simpledialog.askstring("Переименовать проект", "Новое название:",
                                          initialvalue=self.current_project)
        if not new_name:
            return
        new_name = new_name.strip()
        if not new_name or new_name == self.current_project:
            return
        if self.db_manager.get_project(new_name):
            messagebox.showerror("Ошибка", "Проект с таким названием уже существует!")
            return
        self.save_current_project_data()
        old_name = self.current_project
        if self.db_manager.rename_project(old_name, new_name):
            self.current_project = new_name
            self.load_projects()
            self.combo_projects.set(new_name)
            self.on_project_select()
            self.log_action(f"Проект переименован: {old_name} → {new_name}")
        else:
            messagebox.showerror("Ошибка", "Не удалось переименовать проект")

    def change_project_dir(self):
        if not self.current_project:
            messagebox.showwarning("Внимание", "Выберите проект!")
            return
        data = self.db_manager.get_project(self.current_project)
        initial = data["path"] if data and data["path"] and os.path.isdir(data["path"]) else None
        folder = filedialog.askdirectory(title="Папка проекта", initialdir=initial)
        if folder:
            self.db_manager.update_project_path(self.current_project, folder)
            self.log_action(f"Папка проекта {self.current_project}: {folder}")

    def add_project(self):
        name = simpledialog.askstring("Проект", "Название:")
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if self.db_manager.get_project(name):
            messagebox.showerror("Ошибка", "Уже существует!")
            return
        folder = filedialog.askdirectory(title="Директория")
        if not folder:
            return
        if self.db_manager.add_project(name, folder):
            self.save_current_project_data()
            self.load_projects()
            self.combo_projects.set(name)
            self.on_project_select()
            self.log_action(f"Создан проект: {name}")

    def load_projects(self, sort_by=None):
        if sort_by is None:
            sort_by = self.config_manager.get("sort_by", "name")
        projects = self.db_manager.get_all_projects(sort_by)
        names = [p["name"] for p in projects]
        self.combo_projects["values"] = names

    def on_project_select(self, event=None):
        name = self.combo_projects.get()
        if not name:
            return
        if self.current_project and self.current_project != name:
            self.save_current_project_data()
        self.current_project = name
        data = self.db_manager.get_project(name)
        if not data:
            return
        data = dict(data)
        self.entry_contract_date.delete(0, tk.END)
        self.entry_contract_date.insert(0, data.get("contract_date", "") or "")
        self.entry_contract_amount.delete(0, tk.END)
        self.entry_contract_amount.insert(0, data.get("contract_amount", "") or "")
        self.combo_contract_currency.set(data.get("contract_currency", "") or CURRENCIES[0])
        self.entry_delivery_address.delete(0, tk.END)
        self.entry_delivery_address.insert(0, data.get("delivery_address", "") or "")
        self.finances_tab.load_payments()
        self.specification_tab.load_specifications()
        if hasattr(self, "plan_fact_tab"):
            self.plan_fact_tab.load_records()       
        self.purchases_tab.load_purchases()
        if hasattr(self, "dashboard_tab"):
            self.dashboard_tab.refresh()
        if hasattr(self, "budget_tab"):
            self.budget_tab.load_budget()
        self.entry_del_term.delete(0, tk.END)
        self.entry_del_term.insert(0, data.get("del_term", "") or "")
        self.combo_del_unit.set(data.get("del_unit", "") or "Календарные дни")
        del_base = data.get("del_base_date") or "От даты договора"
        self.del_base_var.set(del_base)
        self.entry_confirmation_date.delete(0, tk.END)
        self.entry_confirmation_date.insert(0, data.get("confirmation_date", "") or "")
        self.entry_work_start.delete(0, tk.END)
        self.entry_work_start.insert(0, data.get("work_start", "") or "")
        self.entry_work_term.delete(0, tk.END)
        self.entry_work_term.insert(0, data.get("work_term", "") or "")
        self.combo_work_unit.set(data.get("work_unit", "") or "Календарные дни")
        self.deadlines_tab.calculate_dates()
        self.current_purchase_spec_id = None
        self.purchase_spec_tab.load_specs()
        self.purchase_spec_tab.load_purchase_spec_items()
        self.log_action(f"Выбран проект: {name}")

    def open_project_dir(self):
        if not self.current_project:
            return
        data = self.db_manager.get_project(self.current_project)
        path = data["path"] if data else ""
        if not path or not os.path.exists(path):
            if messagebox.askyesno("Папка не найдена",
                                   f"Папка проекта не найдена:\n{path}\n\nУказать новую папку?"):
                self.change_project_dir()
            return
        open_path(path)

    def save_current_project(self):
        if not self.current_project:
            return
        self.save_current_project_data()
        self.log_action(f"Сохранен проект: {self.current_project}")
        messagebox.showinfo("Успех", "Сохранено!")

    def __del__(self):
        if hasattr(self, 'db_manager') and self.db_manager:
            self.db_manager.close()
        if hasattr(self, 'logger'):
            for handler in self.logger.handlers[:]:
                handler.close()
                self.logger.removeHandler(handler)


if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = ProjectManagerApp(root)
        app.restore_window_geometry()
        root.mainloop()
    except Exception as e:
        messagebox.showerror("Ошибка", f"{e}")
        traceback.print_exc()