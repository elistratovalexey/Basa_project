# -*- coding: utf-8 -*-
"""Статус заказа, подтверждение, отгрузка, трек, ETA."""
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime


class OrderStatusDialog(tk.Toplevel):
    def __init__(self, parent, db_manager, batch_id):
        super().__init__(parent)
        self.db = db_manager
        self.batch_id = batch_id
        self.title(f"Статус заказа №{batch_id}")
        self.geometry("460x330")
        self.resizable(False, False)
        st = self.db.get_order_status(batch_id)

        ttk.Label(self, text=f"Проект: {st.get('project_name','')}   "
                             f"Поставщик: {st.get('supplier','')}",
                  font=("Arial", 9, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=8)

        ttk.Label(self, text="Статус:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.combo_status = ttk.Combobox(self, values=self.db.ORDER_STATUSES, width=22, state="readonly")
        self.combo_status.grid(row=1, column=1, sticky="w", padx=5)
        self.combo_status.set(st.get("status") or "Размещён")

        self.entries = {}
        rows = [("Дата подтверждения", "confirm_date"), ("Дата отгрузки", "ship_date"),
                ("Трек / номер отправления", "tracking"), ("ETA (обещанная дата)", "eta_date"),
                ("Дата списания", "write_off_date")]
        for i, (title, key) in enumerate(rows, start=2):
            ttk.Label(self, text=title + ":").grid(row=i, column=0, sticky="w", padx=10, pady=5)
            e = ttk.Entry(self, width=24)
            e.grid(row=i, column=1, sticky="w", padx=5)
            e.insert(0, st.get(key) or "")
            self.entries[key] = e
            ttk.Button(self, text="📅", width=3,
                       command=lambda en=e: self.pick(en)).grid(row=i, column=2, padx=4)

        bf = ttk.Frame(self)
        bf.grid(row=len(rows) + 2, column=0, columnspan=3, pady=14)
        ttk.Button(bf, text="Сохранить", command=self.save).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text="Сегодня в ETA", command=self.eta_today).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text="Закрыть", command=self.destroy).pack(side=tk.LEFT, padx=5)

        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def pick(self, entry):
        try:
            from dialogs.calendar_dialog import CalendarDialog
            d = CalendarDialog(self, entry.get() or None)
            self.wait_window(d)
            if d.result:
                entry.delete(0, tk.END)
                entry.insert(0, d.result)
        except Exception:
            entry.delete(0, tk.END)
            entry.insert(0, datetime.now().strftime("%d.%m.%Y"))

    def eta_today(self):
        e = self.entries["eta_date"]
        e.delete(0, tk.END)
        e.insert(0, datetime.now().strftime("%d.%m.%Y"))

    def save(self):
        try:
            self.db.set_order_status(
                self.batch_id,
                status=self.combo_status.get(),
                confirm_date=self.entries["confirm_date"].get().strip(),
                ship_date=self.entries["ship_date"].get().strip(),
                tracking=self.entries["tracking"].get().strip(),
                eta_date=self.entries["eta_date"].get().strip(),
                write_off_date=self.entries["write_off_date"].get().strip(),
            )
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
            return
        messagebox.showinfo("Успех", "Статус заказа обновлён")
        self.destroy()