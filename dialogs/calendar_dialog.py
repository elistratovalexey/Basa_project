import tkinter as tk
from tkinter import ttk, messagebox
import calendar
from datetime import datetime, date


class CalendarDialog(tk.Toplevel):
    """Диалог выбора даты БЕЗ внешних зависимостей (tkcalendar не нужен).

    Использование (не изменилось):
        dialog = CalendarDialog(self, "14.08.2026")   # или None
        self.wait_window(dialog)
        if dialog.result:            # "ДД.ММ.ГГГГ" или None
            ...
    """

    MONTH_NAMES = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                   "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
    WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    def __init__(self, parent, current_date=None, title="Выберите дату"):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.result = None

        # Разбор переданной даты
        self.selected = self._parse_date(current_date) or date.today()
        self.view_year = self.selected.year
        self.view_month = self.selected.month

        self._build_ui()
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # Служебное
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_date(s):
        if not s:
            return None
        s = str(s).strip()
        for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None

    def _on_close(self):
        self.result = None
        self.destroy()

    def _finish(self, d):
        self.result = d.strftime("%d.%m.%Y")
        self.destroy()

    # ------------------------------------------------------------------
    # Интерфейс
    # ------------------------------------------------------------------
    def _build_ui(self):
        main = ttk.Frame(self, padding=10)
        main.pack()

        # --- Шапка: навигация по месяцам ---
        nav = ttk.Frame(main)
        nav.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(nav, text="◀", width=3, command=self._prev_month).pack(side=tk.LEFT)
        self.lbl_month = ttk.Label(nav, text="", font=("Arial", 10, "bold"), anchor="center")
        self.lbl_month.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(nav, text="▶", width=3, command=self._next_month).pack(side=tk.RIGHT)

        # --- Строка дней недели ---
        wd = ttk.Frame(main)
        wd.pack(fill=tk.X)
        for i, name in enumerate(self.WEEKDAYS):
            ttk.Label(wd, text=name, width=4, anchor="center",
                      foreground=("red" if i >= 5 else "black")
                      ).grid(row=0, column=i, padx=1, pady=2)

        # --- Сетка дней ---
        self.grid_frame = ttk.Frame(main)
        self.grid_frame.pack(fill=tk.BOTH, expand=True)

        # --- Ручной ввод + кнопки ---
        entry_row = ttk.Frame(main)
        entry_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(entry_row, text="Дата:").pack(side=tk.LEFT)
        self.entry_date = ttk.Entry(entry_row, width=12)
        self.entry_date.pack(side=tk.LEFT, padx=5)
        self.entry_date.insert(0, self.selected.strftime("%d.%m.%Y"))
        ttk.Button(entry_row, text="ОК", command=self._on_ok_entry).pack(side=tk.LEFT, padx=5)
        ttk.Button(entry_row, text="Сегодня", command=self._on_today).pack(side=tk.LEFT, padx=5)
        ttk.Button(entry_row, text="Отмена", command=self._on_close).pack(side=tk.RIGHT, padx=5)

        self._render_month()

    # ------------------------------------------------------------------
    # Навигация
    # ------------------------------------------------------------------
    def _prev_month(self):
        self.view_month -= 1
        if self.view_month < 1:
            self.view_month = 12
            self.view_year -= 1
        self._render_month()

    def _next_month(self):
        self.view_month += 1
        if self.view_month > 12:
            self.view_month = 1
            self.view_year += 1
        self._render_month()

    def _on_today(self):
        self.selected = date.today()
        self.view_year = self.selected.year
        self.view_month = self.selected.month
        self.entry_date.delete(0, tk.END)
        self.entry_date.insert(0, self.selected.strftime("%d.%m.%Y"))
        self._render_month()

    def _on_ok_entry(self):
        d = self._parse_date(self.entry_date.get())
        if not d:
            messagebox.showwarning("Внимание", "Формат даты: ДД.ММ.ГГГГ", parent=self)
            return
        self._finish(d)

    def _on_day_click(self, day):
        self._finish(date(self.view_year, self.view_month, day))

    # ------------------------------------------------------------------
    # Отрисовка месяца
    # ------------------------------------------------------------------
    def _render_month(self):
        for w in self.grid_frame.winfo_children():
            w.destroy()
        self.lbl_month.config(text=f"{self.MONTH_NAMES[self.view_month - 1]} {self.view_year}")

        cal = calendar.Calendar(firstweekday=0)   # неделя с понедельника
        row = 0
        for week in cal.monthdayscalendar(self.view_year, self.view_month):
            for col, day in enumerate(week):
                if day == 0:
                    ttk.Label(self.grid_frame, text="", width=4).grid(row=row, column=col, padx=1, pady=1)
                    continue
                btn = tk.Button(self.grid_frame, text=str(day), width=4, relief="flat",
                                command=lambda d=day: self._on_day_click(d))
                is_sel = (self.selected is not None
                          and day == self.selected.day
                          and self.view_month == self.selected.month
                          and self.view_year == self.selected.year)
                if is_sel:
                    btn.config(bg="#1976D2", fg="white", font=("Arial", 9, "bold"))
                elif col >= 5:
                    btn.config(fg="red", bg="white")
                else:
                    btn.config(bg="white")
                btn.grid(row=row, column=col, padx=1, pady=1)
            row += 1


if __name__ == "__main__":
    # Самопроверка: python3 dialogs/calendar_dialog.py
    root = tk.Tk()
    root.withdraw()
    dlg = CalendarDialog(root, "14.08.2026")
    root.wait_window(dlg)
    print("Выбрано:", dlg.result)
    root.destroy()