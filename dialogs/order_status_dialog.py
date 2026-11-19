# -*- coding: utf-8 -*-
"""Статус заказа: статус берётся из справочника «База статусов артикула» (item_statuses),
даты подтверждения/отгрузки/ETA/списания, трек-номер."""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime

try:
    from dialogs.calendar_dialog import CalendarDialog
except Exception:
    CalendarDialog = None

# Системные статусы заказа: доливаются в справочник один раз при первом открытии
SYSTEM_ORDER_STATUSES = ["Запрос цены", "КП получено", "Размещён", "Подтверждён",
                         "Оплачен", "Отгружен", "Получен", "Списан"]
# Признаки того, что долливка уже выполнялась
_MARKERS = ("Запрос цены", "КП получено", "Размещён", "Подтверждён", "Оплачен", "Списан")


class OrderStatusDialog(tk.Toplevel):
    def __init__(self, parent, db_manager, batch_id):
        super().__init__(parent)
        self.db = db_manager
        self.batch_id = batch_id
        self.result = False

        self.title(f"Статус заказа №{batch_id}")
        self.geometry("680x380")
        self.resizable(False, False)
        try:
            from dialogs.window_geometry import restore_geometry, track_geometry
            restore_geometry(self, "order_status_dialog", "680x380")
            track_geometry(self, "order_status_dialog")
        except Exception:
            pass
        self.transient(parent)

        info = {}
        try:
            info = self.db.get_order_status(batch_id) or {}
        except Exception as e:
            print(f"[order_status] get_order_status: {e}")

        head = ttk.Frame(self, padding=(12, 10, 12, 0))
        head.pack(fill="x")
        ttk.Label(head, text=f"Проект: {info.get('project_name') or '—'}   "
                             f"Поставщик: {info.get('supplier') or '—'}",
                  font=("Arial", 10, "bold")).pack(side=tk.LEFT)

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        # --- Статус: список из Базы статусов артикула ---
        ttk.Label(body, text="Статус:").grid(row=0, column=0, sticky="w", pady=5)
        self.combo_status = ttk.Combobox(body, width=30)
        self.combo_status.grid(row=0, column=1, sticky="w", pady=5)
        self.combo_status.bind("<<ComboboxSelected>>", self._on_status_selected)
        ttk.Button(body, text="+", width=2,
                   command=self.add_status_inline).grid(row=0, column=2, padx=4)
        ttk.Button(body, text="База статусов артикула",
                   command=self.open_status_directory).grid(row=0, column=3, sticky="w", padx=6)

        self.entries = {}
        rows = [
            ("Дата подтверждения:", "confirm_date", 1),
            ("Дата отгрузки:", "ship_date", 2),
            ("Трек / номер отправления:", "tracking", 3),
            ("ETA (обещанная дата):", "eta_date", 4),
            ("Дата списания:", "write_off_date", 5),
        ]
        for label, key, row in rows:
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=5)
            e = ttk.Entry(body, width=32)
            e.grid(row=row, column=1, sticky="w", pady=5)
            e.insert(0, str(info.get(key) or ""))
            self.entries[key] = e
            if key != "tracking":
                ttk.Button(body, text="📅", width=3,
                           command=lambda en=e: self._pick_date(en)).grid(row=row, column=2, padx=4)

        ttk.Label(body, foreground="gray",
                  text="Статусы «Получен» и «Списан» автоматически отмечают приёмку/списание заказа."
                  ).grid(row=6, column=0, columnspan=4, sticky="w", pady=(8, 0))

        bf = ttk.Frame(self, padding=(12, 0, 12, 12))
        bf.pack(fill="x")
        ttk.Button(bf, text="Сохранить", command=self.save).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text="Сегодня в ETA", command=self.today_to_eta).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text="Закрыть", command=self.destroy).pack(side=tk.LEFT, padx=5)

        self._seed_directory_once()
        self.refresh_statuses(select=str(info.get("status") or ""))

        self.bind("<Escape>", lambda e: self.destroy())
        self.update_idletasks()
        self._safe_grab()

    # ==================================================================
    # Справочник статусов
    # ==================================================================
    def _statuses(self):
        try:
            return list(self.db.get_item_statuses())
        except Exception as e:
            print(f"[order_status] get_item_statuses: {e}")
            return []

    def _seed_directory_once(self):
        """Однократно добавляет системные статусы заказа в справочник артикулов."""
        vals = self._statuses()
        if any(m in vals for m in _MARKERS):
            return                      # уже доливали (или пользователь их добавил)
        added = 0
        for name in SYSTEM_ORDER_STATUSES:
            if name not in vals:
                try:
                    if self.db.add_item_status(name):
                        added += 1
                except Exception:
                    pass
        if added:
            print(f"[order_status] в справочник статусов добавлено: {added}")

    def refresh_statuses(self, select=None):
        vals = self._statuses()
        if not vals:
            vals = list(SYSTEM_ORDER_STATUSES)
        self.combo_status['values'] = vals
        current = select if select is not None else self.combo_status.get()
        if current and current not in vals:
            # сохранённый статус мог быть удалён из справочника — не теряем его
            self.combo_status['values'] = [current] + vals
        self.combo_status.set(current or "")

    def add_status_inline(self):
        name = simpledialog.askstring("Новый статус", "Название статуса:", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        try:
            if self.db.add_item_status(name):
                self.refresh_statuses(select=name)
            else:
                messagebox.showwarning("Внимание", "Такой статус уже есть.", parent=self)
                self.refresh_statuses(select=name)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось добавить статус:\n{e}", parent=self)

    def open_status_directory(self):
        try:
            from dialogs.item_status_dialog import ItemStatusesDialog
        except ImportError:
            messagebox.showerror("Ошибка", "dialogs/item_status_dialog.py не найден", parent=self)
            return
        keep = self.combo_status.get()
        ItemStatusesDialog(self, self.db,
                           on_changed=lambda: self.refresh_statuses(select=keep))
        self.refresh_statuses(select=keep)

    # ==================================================================
    # Даты
    # ==================================================================
    def _pick_date(self, entry):
        if CalendarDialog is None:
            entry.delete(0, tk.END)
            entry.insert(0, datetime.now().strftime("%d.%m.%Y"))
            return
        dlg = CalendarDialog(self, entry.get() or None)
        self.wait_window(dlg)
        if getattr(dlg, "result", None):
            entry.delete(0, tk.END)
            entry.insert(0, dlg.result)

    def today_to_eta(self):
        e = self.entries["eta_date"]
        e.delete(0, tk.END)
        e.insert(0, datetime.now().strftime("%d.%m.%Y"))

    def _on_status_selected(self, event=None):
        """Подставляем сегодняшнюю дату для «Получен»/«Списан», если поле пустое."""
        st = self.combo_status.get().strip()
        today = datetime.now().strftime("%d.%m.%Y")
        if st == "Получен":
            e = self.entries["confirm_date"]
            if not e.get().strip():
                e.insert(0, today)
        elif st == "Списан":
            e = self.entries["write_off_date"]
            if not e.get().strip():
                e.insert(0, today)

    # ==================================================================
    # Сохранение
    # ==================================================================
    @staticmethod
    def _norm_date(value, parent):
        v = (value or "").strip()
        if not v:
            return ""
        for fmt in ("%d.%m.%Y", "%d.%m.%y"):
            try:
                return datetime.strptime(v, fmt).strftime("%d.%m.%Y")
            except ValueError:
                continue
        messagebox.showwarning("Ошибка", f"Дата «{v}» должна быть в формате ДД.ММ.ГГГГ",
                               parent=parent)
        return None

    def save(self):
        status = self.combo_status.get().strip()
        dates = {}
        for key in ("confirm_date", "ship_date", "eta_date", "write_off_date"):
            v = self._norm_date(self.entries[key].get(), self)
            if v is None:
                return
            dates[key] = v
        tracking = self.entries["tracking"].get().strip()

        if not status and not any(dates.values()) and not tracking:
            messagebox.showwarning("Внимание", "Заполните статус или хотя бы одно поле.",
                                   parent=self)
            return
        try:
            self.db.set_order_status(
                self.batch_id,
                status=status or None,
                confirm_date=dates["confirm_date"] or None,
                ship_date=dates["ship_date"] or None,
                tracking=tracking or None,
                eta_date=dates["eta_date"] or None,
                write_off_date=dates["write_off_date"] or None,
            )
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить статус:\n{e}", parent=self)
            return

        # статус артикулов можно синхронизировать одной кнопкой в окне «Заказы»
        self.result = True
        owner = getattr(self.master, "log_action", None)
        if callable(owner):
            try:
                owner(f"Заказ {self.batch_id}: статус «{status or '—'}», ETA {dates['eta_date'] or '—'}")
            except Exception:
                pass
        self.destroy()

    # ==================================================================
    def _safe_grab(self, attempts=10):
        try:
            if self.winfo_exists() and self.winfo_viewable():
                self.grab_set()
            elif attempts > 0:
                self.after(60, lambda a=attempts - 1: self._safe_grab(a))
        except tk.TclError:
            if attempts > 0:
                self.after(60, lambda a=attempts - 1: self._safe_grab(a))