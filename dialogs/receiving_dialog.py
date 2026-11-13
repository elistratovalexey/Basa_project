# -*- coding: utf-8 -*-
"""Приёмка: ожидаемые позиции, частичное получение, QR батча."""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime


class ReceivingDialog(tk.Toplevel):
    def __init__(self, parent, db_manager, project_name=None):
        super().__init__(parent)
        self.db = db_manager
        self.title("Приёмка товара")
        self.geometry("1250x680")
        self.project_name = project_name

        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=6)
        ttk.Label(top, text="Проект:").pack(side=tk.LEFT)
        self.combo_proj = ttk.Combobox(top, width=18, state="readonly",
                                       values=["Все"] + self.db.get_order_projects())
        self.combo_proj.set(project_name or "Все")
        self.combo_proj.pack(side=tk.LEFT, padx=5)
        ttk.Label(top, text="Поставщик:").pack(side=tk.LEFT, padx=(10, 0))
        self.combo_sup = ttk.Combobox(top, width=20, state="readonly",
                                      values=["Все"] + [s["name"] for s in self.db.get_suppliers()])
        self.combo_sup.set("Все")
        self.combo_sup.pack(side=tk.LEFT, padx=5)
        ttk.Label(top, text="Инвойс:").pack(side=tk.LEFT, padx=(10, 0))
        self.entry_inv = ttk.Entry(top, width=14)
        self.entry_inv.pack(side=tk.LEFT, padx=5)
        self.only_pending = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Только ожидаемые", variable=self.only_pending,
                        command=self.load).pack(side=tk.LEFT, padx=10)
        ttk.Button(top, text="Показать", command=self.load).pack(side=tk.LEFT, padx=5)

        cols = ("id", "batch", "article", "name", "qty", "got", "sup", "inv", "proj", "date")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=18)
        for c, t, w in (("id", "ID", 50), ("batch", "Заказ", 70), ("article", "Артикул", 140),
                        ("name", "Наименование", 300), ("qty", "Заказано", 80), ("got", "Принято", 80),
                        ("sup", "Поставщик", 150), ("inv", "Инвойс", 110), ("proj", "Проект", 120),
                        ("date", "Дата приёма", 100)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center" if c in ("id", "batch", "qty", "got", "date") else "w")
        self.tree.pack(fill="both", expand=True, padx=8, pady=5)
        sb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        sb.place(in_=self.tree, relx=1.0, rely=0, relheight=1.0, anchor="ne")

        form = ttk.LabelFrame(self, text="Приём выбранной позиции", padding=8)
        form.pack(fill="x", padx=8, pady=6)
        ttk.Label(form, text="Принято, шт.:").grid(row=0, column=0, sticky="w")
        self.entry_qty = ttk.Entry(form, width=10)
        self.entry_qty.grid(row=0, column=1, padx=6)
        ttk.Label(form, text="Дата:").grid(row=0, column=2, sticky="w", padx=(12, 0))
        self.entry_date = ttk.Entry(form, width=12)
        self.entry_date.grid(row=0, column=3, padx=6)
        self.entry_date.insert(0, datetime.now().strftime("%d.%m.%Y"))
        ttk.Label(form, text="Недостача / брак:").grid(row=0, column=4, sticky="w", padx=(12, 0))
        self.entry_note = ttk.Entry(form, width=32)
        self.entry_note.grid(row=0, column=5, padx=6)
        ttk.Button(form, text="Принять", command=self.accept_one).grid(row=0, column=6, padx=8)

        bf = ttk.Frame(self)
        bf.pack(fill="x", padx=8, pady=8)
        ttk.Button(bf, text="Принять весь заказ", command=self.accept_batch).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text="QR этикетка заказа", command=self.make_qr).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text="Закрыть", command=self.destroy).pack(side=tk.RIGHT, padx=5)

        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.load()
        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def load(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        proj = None if self.combo_proj.get() == "Все" else self.combo_proj.get()
        sup = None if self.combo_sup.get() == "Все" else self.combo_sup.get()
        inv = self.entry_inv.get().strip() or None
        try:
            rows = self.db.get_receiving_rows(proj, sup, inv, self.only_pending.get())
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
            return
        for r in rows:
            self.tree.insert("", tk.END, values=(
                r["id"], r["order_batch_id"], r["article"] or "", r["name"] or "",
                r["quantity"], r["qty_received"], r["supplier"] or "",
                r["invoice_number"] or "", r["project_name"] or "", r["receipt_date"] or ""))

    def on_select(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        v = self.tree.item(sel[0])["values"]
        self.entry_qty.delete(0, tk.END)
        self.entry_qty.insert(0, str(v[4]))

    def accept_one(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите позицию!")
            return
        v = self.tree.item(sel[0])["values"]
        try:
            qty = float(self.entry_qty.get().replace(",", "."))
        except ValueError:
            messagebox.showwarning("Ошибка", "Некорректное количество!")
            return
        date = self.entry_date.get().strip() or datetime.now().strftime("%d.%m.%Y")
        self.db.receive_order_item(v[0], qty, date, self.entry_note.get().strip())
        self.load()

    def accept_batch(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите любую строку заказа!")
            return
        batch = self.tree.item(sel[0])["values"][1]
        if not messagebox.askyesno("Подтверждение", f"Принять полностью заказ №{batch}?"):
            return
        date = self.entry_date.get().strip() or datetime.now().strftime("%d.%m.%Y")
        self.db.receive_batch(batch, date)
        self.load()

    def make_qr(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите строку заказа!")
            return
        v = self.tree.item(sel[0])["values"]
        try:
            import qrcode
        except ImportError:
            messagebox.showerror("Нет библиотеки", "Установите: pip install qrcode[pil]")
            return
        path = filedialog.asksaveasfilename(defaultextension=".png",
                                            initialfile=f"QR_order_{v[1]}.png")
        if not path:
            return
        img = qrcode.make(f"ORDER:{v[1]}|PROJ:{v[8]}|SUP:{v[6]}|INV:{v[7]}")
        img.save(path)
        messagebox.showinfo("QR", f"Сохранено:\n{path}")