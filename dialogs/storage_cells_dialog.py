# -*- coding: utf-8 -*-
"""База ячеек хранения: номер + штрихкод EAN-13 (генерируется автоматически)."""
import tkinter as tk
from tkinter import ttk, messagebox

L = ["0001101", "0011001", "0010011", "0111101", "0100011",
     "0110001", "0101111", "0111011", "0110111", "0001011"]
G = ["0100111", "0110011", "0011011", "0100001", "0011101",
     "0111001", "0000101", "0010001", "0001001", "0010111"]
R = ["1110010", "1100110", "1101100", "1000010", "1011100",
     "1001110", "1010000", "1000100", "1001000", "1110100"]
PARITY = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG",
          "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"]


def ean13_bits(code):
    """Последовательность модулей EAN-13 для отрисовки."""
    code = "".join(ch for ch in str(code) if ch.isdigit())
    if len(code) != 13:
        return ""
    bits = "101"
    par = PARITY[int(code[0])]
    for i in range(6):
        d = int(code[i + 1])
        bits += (L if par[i] == "L" else G)[d]
    bits += "01010"
    for i in range(6):
        bits += R[int(code[i + 7])]
    return bits + "101"


class StorageCellsDialog(tk.Toplevel):
    def __init__(self, parent, db, on_changed=None):
        super().__init__(parent)
        self.db = db
        self.on_changed = on_changed
        self.title("База ячеек хранения")
        self.geometry("880x560")
        self.transient(parent)

        top = ttk.Frame(self, padding=(10, 8))
        top.pack(fill="x")
        ttk.Label(top, text="Номер ячейки:").pack(side=tk.LEFT)
        self.e_code = ttk.Entry(top, width=18)
        self.e_code.pack(side=tk.LEFT, padx=6)
        ttk.Label(top, text="Примечание:").pack(side=tk.LEFT, padx=(12, 0))
        self.e_note = ttk.Entry(top, width=28)
        self.e_note.pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Добавить", command=self.add).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Сохранить изменения", command=self.save).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Удалить", command=self.delete).pack(side=tk.LEFT, padx=4)

        mid = ttk.Frame(self, padding=(10, 0))
        mid.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(mid, columns=("code", "barcode", "note"),
                                 show="headings", height=12)
        for c, t, w in (("code", "Номер ячейки", 180), ("barcode", "Штрихкод EAN-13", 180),
                        ("note", "Примечание", 260)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w" if c != "barcode" else "center")
        vs = ttk.Scrollbar(mid, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=vs.set)
        self.tree.pack(side=tk.LEFT, fill="both", expand=True)
        vs.pack(side=tk.RIGHT, fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.pick)

        bc = ttk.LabelFrame(self, text="Штрихкод выбранной ячейки", padding=8)
        bc.pack(fill="x", padx=10, pady=8)
        self.canvas = tk.Canvas(bc, height=90, bg="white", highlightthickness=0)
        self.canvas.pack(fill="x")
        bf = ttk.Frame(bc)
        bf.pack(fill="x", pady=(6, 0))
        ttk.Button(bf, text="Перегенерировать штрихкод",
                   command=self.regen).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Копировать номер", command=self.copy_code).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Закрыть", command=self.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Label(self, foreground="gray", padding=(10, 0, 10, 8),
                  text="Штрихкод создаётся автоматически при добавлении ячейки "
                       "(префикс 200 + номер + контрольная цифра EAN-13)."
                  ).pack(fill="x")

        self.bind("<Escape>", lambda e: self.destroy())
        self.reload()
        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def reload(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for r in self.db.get_storage_cells():
            self.tree.insert("", tk.END, iid=str(r["id"]),
                             values=(r["code"], r["barcode"] or "", r["note"] or ""))
        if self.on_changed:
            try:
                self.on_changed()
            except Exception:
                pass

    def pick(self, e=None):
        s = self.tree.selection()
        if not s:
            return
        v = self.tree.item(s[0])["values"]
        self.e_code.delete(0, tk.END)
        self.e_code.insert(0, v[0])
        self.e_note.delete(0, tk.END)
        self.e_note.insert(0, v[2] or "")
        self.draw_barcode(v[1])

    def draw_barcode(self, code):
        self.canvas.delete("all")
        bits = ean13_bits(code)
        if not bits:
            self.canvas.create_text(10, 40, anchor="w", text="Выберите ячейку")
            return
        m, h, x0, y0 = 3, 60, 20, 8
        for i, b in enumerate(bits):
            if b == "1":
                self.canvas.create_rectangle(x0 + i * m, y0, x0 + (i + 1) * m, y0 + h,
                                             fill="black", outline="")
        self.canvas.create_text(x0 + len(bits) * m / 2, y0 + h + 12,
                                text=str(code), font=("Consolas", 11))

    def add(self):
        ok, info = self.db.add_storage_cell(self.e_code.get(), self.e_note.get())
        if ok:
            self.e_code.delete(0, tk.END)
            self.e_note.delete(0, tk.END)
            self.reload()
            self.draw_barcode(info)
        else:
            messagebox.showwarning("Внимание", info, parent=self)

    def save(self):
        s = self.tree.selection()
        if not s:
            messagebox.showwarning("Внимание", "Выберите ячейку!", parent=self)
            return
        if self.db.update_storage_cell(int(s[0]), self.e_code.get(), self.e_note.get()):
            self.reload()
        else:
            messagebox.showwarning("Внимание", "Такой номер уже занят", parent=self)

    def delete(self):
        s = self.tree.selection()
        if not s:
            return
        if not messagebox.askyesno("Подтверждение", "Удалить ячейку?", parent=self):
            return
        ok, msg = self.db.delete_storage_cell(int(s[0]))
        if ok:
            self.reload()
            self.draw_barcode("")
        else:
            messagebox.showwarning("Внимание", msg, parent=self)

    def regen(self):
        s = self.tree.selection()
        if s:
            code = self.db.regenerate_barcode(int(s[0]))
            self.reload()
            self.draw_barcode(code)

    def copy_code(self):
        s = self.tree.selection()
        if s:
            self.clipboard_clear()
            self.clipboard_append(self.tree.item(s[0])["values"][1])
