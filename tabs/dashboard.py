# -*- coding: utf-8 -*-
"""Вкладка «Сегодня»: плитки-счётчики + расшифровка."""
import tkinter as tk
from tkinter import ttk, messagebox
from tabs.base import BaseTab

TILES = [
    ("overdue", "🔴 Просроченные поставки", "#c0392b"),
    ("soon", "🟡 Поставка ≤ 7 дней", "#b7950b"),
    ("pay_week", "💸 Оплаты на неделе", "#1f618d"),
    ("unpaid_inv", "🧾 Неоплаченные счета", "#7d3c98"),
    ("no_confirm", "📨 Нет подтверждения > 5 дн.", "#a04000"),
    ("price_requests", "📩 Запросы цены без ответа", "#117864"),
]


class DashboardTab(BaseTab):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        self.data = {}
        self.current_key = "overdue"
        self.create_ui()

    def create_ui(self):
        top = ttk.Frame(self.parent)
        top.pack(fill="x", pady=5)
        ttk.Button(top, text="Обновить", command=self.refresh).pack(side=tk.LEFT, padx=5)
        self.all_projects = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Все проекты (иначе — текущий)", variable=self.all_projects,
                        command=self.refresh).pack(side=tk.LEFT, padx=10)
        ttk.Button(top, text="Проверить напоминания", command=self.check_reminders).pack(side=tk.LEFT, padx=5)
        self.lbl_stamp = ttk.Label(top, text="", foreground="gray")
        self.lbl_stamp.pack(side=tk.RIGHT, padx=10)

        tiles = ttk.Frame(self.parent)
        tiles.pack(fill="x", pady=5)
        self.tile_labels = {}
        for i, (key, title, color) in enumerate(TILES):
            box = tk.Frame(tiles, bd=1, relief="solid", bg="white", cursor="hand2")
            box.grid(row=i // 3, column=i % 3, sticky="nsew", padx=4, pady=4)
            tiles.grid_columnconfigure(i % 3, weight=1)
            lbl_t = tk.Label(box, text=title, bg="white", fg=color, font=("Arial", 10, "bold"))
            lbl_t.pack(anchor="w", padx=8, pady=(6, 0))
            lbl_n = tk.Label(box, text="0", bg="white", fg=color, font=("Arial", 20, "bold"))
            lbl_n.pack(anchor="w", padx=8, pady=(0, 6))
            for w in (box, lbl_t, lbl_n):
                w.bind("<Button-1>", lambda e, k=key: self.show(k))
            self.tile_labels[key] = lbl_n

        det = ttk.LabelFrame(self.parent, text="Расшифровка", padding=6)
        det.pack(fill="both", expand=True, pady=5)
        self.tree = ttk.Treeview(det, columns=("c1", "c2", "c3", "c4", "c5", "c6"),
                                 show="headings", height=14)
        for c in ("c1", "c2", "c3", "c4", "c5", "c6"):
            self.tree.heading(c, text="")
            self.tree.column(c, width=150, anchor="w")
        sb = ttk.Scrollbar(det, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        self.tree.pack(side=tk.LEFT, fill="both", expand=True)
        sb.pack(side=tk.RIGHT, fill="y")
        self.tree.bind("<Double-1>", self.open_selected)

    def check_reminders(self):
        try:
            from reminders import run_once
            n = run_once(self.app, force=True)
            messagebox.showinfo("Напоминания", f"Отправлено напоминаний: {n}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def refresh(self):
        from datetime import datetime
        proj = None if self.all_projects.get() else (self.app.current_project or None)
        try:
            self.data = self.db_manager.get_dashboard(proj)
        except Exception as e:
            messagebox.showerror("Ошибка дашборда", str(e))
            return
        for key, _, _ in TILES:
            self.tile_labels[key].config(text=str(len(self.data.get(key, []))))
        self.lbl_stamp.config(text="обновлено " + datetime.now().strftime("%d.%m.%Y %H:%M"))
        self.show(self.current_key)

    def show(self, key):
        self.current_key = key
        rows = self.data.get(key, [])
        for i in self.tree.get_children():
            self.tree.delete(i)
        if key in ("unpaid_inv", "pay_week"):
            cols = ["Проект", "Поставщик", "Спецификация", "Сумма", "Валюта", "Дата оплаты"]
        elif key == "price_requests":
            cols = ["№", "Проект", "Поставщик", "Инвойс", "Статус", "Дата заказа"]
        elif key == "no_confirm":
            cols = ["№", "Проект", "Поставщик", "Статус", "Дата заказа", "Дней"]
        else:
            cols = ["№", "Проект", "Поставщик", "Инвойс", "Дата", "Дней"]
        for i, c in enumerate(cols, start=1):
            self.tree.heading(f"c{i}", text=c)
        for r in rows:
            self.tree.insert("", tk.END, values=[r.get(c, "") for c in cols])

    def open_selected(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        rows = self.data.get(self.current_key, [])
        if idx >= len(rows):
            return
        row = rows[idx]
        if row.get("spec_id"):
            # НОВОЕ: открываем счёт на редактирование (вся информация)
            from dialogs.spec_edit_dialog import SpecEditDialog
            SpecEditDialog(self.root, self.db_manager, row["spec_id"], on_saved=self.refresh)
        elif row.get("batch_id"):
            from dialogs.order_status_dialog import OrderStatusDialog
            OrderStatusDialog(self.root, self.db_manager, row["batch_id"])
            self.refresh()