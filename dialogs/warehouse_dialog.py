# -*- coding: utf-8 -*-
"""СКЛАД: остатки по ячейкам хранения. Не зависит от выбранного проекта.
Штрихкоды: ячейки — EAN-13 префикс 200+id, позиции — EAN-13 префикс 201+id
(совпадают с Android-приложением)."""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

def _num(v, d=0.0):
    try:
        return float(str(v).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return d

def _ean13(body12):
    """Контрольная цифра EAN-13 для 12 цифр."""
    s = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(body12))
    return body12 + str((10 - s % 10) % 10)

class WarehouseDialog(tk.Toplevel):
    def __init__(self, parent, db_manager):
        super().__init__(parent)
        self.db = db_manager
        self.parent_app = parent if hasattr(parent, "log_action") else getattr(parent, "app", None)
        self._row_id = {}
        self._current_id = None
        self._cells = {}
        self.title("СКЛАД — остатки по ячейкам хранения")
        self.geometry("1280x760")
        try:
            from dialogs.window_geometry import restore_geometry, track_geometry
            restore_geometry(self, "warehouse_dialog", "1280x760")
            track_geometry(self, "warehouse_dialog")
        except Exception:
            pass
        self.transient(parent)
        self._ensure_item_barcodes()
        self.create_ui()
        self.refresh_dicts()
        self.load_items()
        self._safe_grab()

    def _safe_grab(self, attempts=10):
        try:
            if self.winfo_exists() and self.winfo_viewable():
                self.grab_set()
            elif attempts > 0:
                self.after(60, lambda a=attempts - 1: self._safe_grab(a))
        except tk.TclError:
            if attempts > 0:
                self.after(60, lambda a=attempts - 1: self._safe_grab(a))

    def _log(self, msg):
        try:
            if self.parent_app is not None and hasattr(self.parent_app, "log_action"):
                self.parent_app.log_action(msg)
        except Exception:
            pass

    # ==================================================================
    # Штрихкоды позиций (создание колонки + автозаполнение)
    # ==================================================================
    def _ensure_item_barcodes(self):
        try:
            cols = [r[1] for r in self.db.conn.execute("PRAGMA table_info(warehouse_items)")]
            if "barcode" not in cols:
                self.db.conn.execute("ALTER TABLE warehouse_items ADD COLUMN barcode TEXT DEFAULT ''")
            for r in self.db.conn.execute(
                    "SELECT id FROM warehouse_items WHERE barcode IS NULL OR barcode=''").fetchall():
                self.db.conn.execute("UPDATE warehouse_items SET barcode=? WHERE id=?",
                                     (_ean13("201" + str(r["id"]).zfill(9)), r["id"]))
            self.db.conn.commit()
        except Exception as e:
            print(f"[warehouse] barcode: {e}")

    def _item_barcode(self, wid):
        row = self.db.conn.execute("SELECT barcode FROM warehouse_items WHERE id=?",
                                   (wid,)).fetchone()
        bc = (row["barcode"] or "") if row else ""
        if not bc:
            bc = _ean13("201" + str(wid).zfill(9))
            self.db.conn.execute("UPDATE warehouse_items SET barcode=? WHERE id=?", (bc, wid))
            self.db.conn.commit()
        return bc

    def regen_item_barcode(self):
        if self._current_id is None:
            messagebox.showwarning("Внимание", "Выберите позицию в таблице!", parent=self)
            return
        bc = _ean13("201" + str(self._current_id).zfill(9))
        self.db.conn.execute("UPDATE warehouse_items SET barcode=? WHERE id=?",
                             (bc, self._current_id))
        self.db.conn.commit()
        self.lbl_item_bc.config(text=bc)
        self._log(f"Склад: позиция #{self._current_id} — штрихкод {bc}")
        keep = self._current_id
        self.load_items()
        for iid, rid in self._row_id.items():
            if rid == keep:
                self.tree.selection_set(iid)
                self.tree.see(iid)
                self.on_select()
                break

    # ==================================================================
    def create_ui(self):
        flt = ttk.Frame(self, padding=(10, 8))
        flt.pack(fill="x")
        ttk.Label(flt, text="СКЛАД", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=(0, 14))
        ttk.Label(flt, text="Ячейка:").pack(side=tk.LEFT)
        self.c_f_cell = ttk.Combobox(flt, width=18, state="readonly")
        self.c_f_cell.pack(side=tk.LEFT, padx=4)
        self.c_f_cell.bind("<<ComboboxSelected>>", lambda e: self.load_items())
        ttk.Label(flt, text="Наименование:").pack(side=tk.LEFT, padx=(10, 0))
        self.c_f_name = ttk.Combobox(flt, width=28, state="readonly")
        self.c_f_name.pack(side=tk.LEFT, padx=4)
        self.c_f_name.bind("<<ComboboxSelected>>", lambda e: self.load_items())
        ttk.Label(flt, text="Поиск / штрихкод:").pack(side=tk.LEFT, padx=(10, 0))
        self.e_search = ttk.Entry(flt, width=20)
        self.e_search.pack(side=tk.LEFT, padx=4)
        self.e_search.bind("<Return>", lambda e: self.scan_or_search())
        ttk.Button(flt, text="Найти", command=self.scan_or_search).pack(side=tk.LEFT, padx=2)
        ttk.Button(flt, text="Сброс", command=self.reset_filters).pack(side=tk.LEFT, padx=2)
        ttk.Button(flt, text="Экспорт в Excel", command=self.export).pack(side=tk.RIGHT, padx=4)

        self.lbl_sum = ttk.Label(self, padding=(12, 0), foreground="#0a58ca",
                                 font=("Arial", 9, "bold"))
        self.lbl_sum.pack(fill="x")

        tf = ttk.LabelFrame(self, text="Остатки  ·  двойной клик по строке — загрузить в форму",
                            padding=6)
        tf.pack(fill="both", expand=True, padx=10, pady=6)
        cols = ("cell", "barcode", "item_bc", "name", "qty", "descr", "upd")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", height=14)
        for c, t, w in (("cell", "Ячейка хранения", 120), ("barcode", "Штрихкод ячейки", 130),
                        ("item_bc", "Штрихкод позиции", 130), ("name", "Наименование", 340),
                        ("qty", "Кол-во", 80), ("descr", "Описание", 300), ("upd", "Изменено", 130)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w,
                             anchor="center" if c in ("qty", "barcode", "item_bc", "upd") else "w")
        vs = ttk.Scrollbar(tf, orient=tk.VERTICAL, command=self.tree.yview)
        hs = ttk.Scrollbar(tf, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscroll=vs.set, xscroll=hs.set)
        self.tree.pack(side=tk.LEFT, fill="both", expand=True)
        vs.pack(side=tk.RIGHT, fill="y")
        hs.pack(side=tk.BOTTOM, fill="x")
        self.tree.tag_configure("zero", foreground="#999999")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", lambda e: self.on_select())

        card = ttk.LabelFrame(self, text="Позиция склада", padding=10)
        card.pack(fill="x", padx=10, pady=6)
        ttk.Label(card, text="Ячейка хранения:").grid(row=0, column=0, sticky="w")
        self.c_cell = ttk.Combobox(card, width=20, state="readonly")
        self.c_cell.grid(row=0, column=1, sticky="w", padx=4)
        ttk.Button(card, text="+", width=2, command=self.open_cells).grid(row=0, column=2, sticky="w")
        ttk.Label(card, text="Кол-во:").grid(row=0, column=3, sticky="w", padx=(16, 4))
        self.e_qty = ttk.Entry(card, width=12)
        self.e_qty.grid(row=0, column=4, sticky="w")
        self.e_qty.insert(0, "0")
        self.lbl_cell_bc = ttk.Label(card, text="", foreground="gray")
        self.lbl_cell_bc.grid(row=0, column=5, sticky="w", padx=14)
        self.c_cell.bind("<<ComboboxSelected>>", self._show_cell_barcode)

        ttk.Label(card, text="Наименование:").grid(row=1, column=0, sticky="w", pady=6)
        self.c_name = ttk.Combobox(card, width=52)
        self.c_name.grid(row=1, column=1, columnspan=2, sticky="ew", padx=4)
        ttk.Button(card, text="+", width=2, command=self.open_names).grid(row=1, column=2, sticky="e")
        ttk.Label(card, text="Описание:").grid(row=2, column=0, sticky="nw")
        self.e_descr = tk.Text(card, width=90, height=3)
        self.e_descr.grid(row=2, column=1, columnspan=5, sticky="ew", pady=4)

        ttk.Label(card, text="Штрихкод позиции:").grid(row=3, column=0, sticky="w", pady=4)
        self.lbl_item_bc = ttk.Label(card, text="—", foreground="#0a58ca",
                                     font=("Arial", 10, "bold"))
        self.lbl_item_bc.grid(row=3, column=1, sticky="w", padx=4)
        ttk.Button(card, text="🔄 Сгенерировать", command=self.regen_item_barcode)\
            .grid(row=3, column=2, columnspan=2, sticky="w", padx=4)
        card.grid_columnconfigure(1, weight=1)

        bf = ttk.Frame(self, padding=(10, 0, 10, 10))
        bf.pack(fill="x")
        for t, c in (("Добавить", self.add_item), ("Сохранить", self.save_item),
                     ("Удалить", self.delete_item), ("Очистить форму", self.clear_form),
                     ("База ячеек", self.open_cells), ("База наименований", self.open_names)):
            ttk.Button(bf, text=t, command=c).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Закрыть", command=self.destroy).pack(side=tk.RIGHT, padx=4)
        self.bind("<Escape>", lambda e: self.destroy())

    # ==================================================================
    def refresh_dicts(self):
        self._cells = {"— не указана —": 0}
        for r in self.db.get_storage_cells():
            self._cells[r["code"]] = r["id"]
        vals = list(self._cells.keys())
        self.c_cell["values"] = vals
        self.c_f_cell["values"] = ["Все"] + vals[1:]
        if not self.c_cell.get():
            self.c_cell.set("— не указана —")
        if not self.c_f_cell.get():
            self.c_f_cell.set("Все")
        names = [r["name"] for r in self.db.get_warehouse_names()]
        self.c_name["values"] = names
        self.c_f_name["values"] = ["Все"] + names
        if not self.c_f_name.get():
            self.c_f_name.set("Все")

    def _show_cell_barcode(self, event=None):
        cid = self._cells.get(self.c_cell.get(), 0)
        bc = ""
        if cid:
            row = self.db.conn.execute("SELECT barcode FROM storage_cells WHERE id=?",
                                       (cid,)).fetchone()
            bc = row["barcode"] if row else ""
        self.lbl_cell_bc.config(text=f"штрихкод ячейки: {bc}" if bc else "")

    def reset_filters(self):
        self.c_f_cell.set("Все")
        self.c_f_name.set("Все")
        self.e_search.delete(0, tk.END)
        self.load_items()

    def scan_or_search(self):
        """Сканер: 13 цифр → ячейка или позиция по штрихкоду, иначе текстовый поиск."""
        txt = self.e_search.get().strip()
        if txt.isdigit():
            if len(txt) == 13:
                cell = self.db.find_cell_by_barcode(txt)
                if cell:
                    self.c_f_cell.set(cell["code"])
                    self.e_search.delete(0, tk.END)
                    self.load_items()
                    return
            item = self.db.conn.execute(
                "SELECT * FROM warehouse_items WHERE barcode=?", (txt,)).fetchone()
            if item:
                self.c_f_name.set("Все")
                cid = item["cell_id"] or 0
                code = next((c for c, i in self._cells.items() if i == cid), "Все")
                self.c_f_cell.set(code if cid else "Все")
                self.e_search.delete(0, tk.END)
                self.load_items()
                for iid, rid in self._row_id.items():
                    if rid == item["id"]:
                        self.tree.selection_set(iid)
                        self.tree.see(iid)
                        self.on_select()
                        break
                return
        self.load_items()

    def load_items(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        self._row_id = {}
        cell = self.c_f_cell.get()
        name = self.c_f_name.get()
        cid = self._cells.get(cell, 0) if cell not in ("", "Все") else None
        rows = self.db.get_warehouse_items(
            cell_id=cid, name=None if name in ("", "Все") else name,
            search=self.e_search.get().strip() or None)
        total = 0.0
        for r in rows:
            q = _num(r["qty"])
            total += q
            keys = r.keys()
            item_bc = (r["barcode"] or "") if "barcode" in keys else ""
            iid = self.tree.insert("", tk.END, tags=("zero",) if q <= 0 else (), values=(
                r["cell_code"] or "", r["cell_barcode"] or "", item_bc, r["name"] or "",
                f"{q:g}", r["description"] or "", r["updated_at"] or ""))
            self._row_id[iid] = r["id"]
        s = self.db.warehouse_stats()
        self.lbl_sum.config(
            text=f"Показано {len(rows)} позиций · количество {total:g} · "
                 f"всего на складе {s['n']} позиций в {s['cells']} ячейках")

    def on_select(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        wid = self._row_id.get(sel[-1])
        v = self.tree.item(sel[-1])["values"]
        self._current_id = wid
        self.c_cell.set(v[0] if v[0] in self._cells else "— не указана —")
        self.c_name.set(v[3])
        self.e_qty.delete(0, tk.END)
        self.e_qty.insert(0, str(v[4]))
        self.e_descr.delete("1.0", tk.END)
        self.e_descr.insert("1.0", v[5] or "")
        self.lbl_item_bc.config(text=v[2] or "—")
        self._show_cell_barcode()

    def clear_form(self):
        self._current_id = None
        self.c_cell.set("— не указана —")
        self.c_name.set("")
        self.e_qty.delete(0, tk.END)
        self.e_qty.insert(0, "0")
        self.e_descr.delete("1.0", tk.END)
        self.lbl_cell_bc.config(text="")
        self.lbl_item_bc.config(text="—")

    # ==================================================================
    def _collect(self):
        return (self._cells.get(self.c_cell.get(), 0), self.c_name.get().strip(),
                _num(self.e_qty.get()), self.e_descr.get("1.0", tk.END).strip())

    def add_item(self):
        cid, name, qty, descr = self._collect()
        if not name:
            messagebox.showwarning("Внимание", "Укажите наименование!", parent=self)
            return
        wid = self.db.add_warehouse_item(cid, name, qty, descr)
        try:
            bc = _ean13("201" + str(wid).zfill(9))
            self.db.conn.execute("UPDATE warehouse_items SET barcode=? WHERE id=?", (bc, wid))
            self.db.conn.commit()
        except Exception as e:
            print(f"[warehouse] barcode: {e}")
        self.db.add_warehouse_name(name)
        self._log(f"Склад: добавлено «{name}» × {qty:g}")
        self.refresh_dicts()
        self.load_items()
        self.clear_form()

    def save_item(self):
        if self._current_id is None:
            messagebox.showwarning("Внимание", "Выберите позицию в таблице!", parent=self)
            return
        cid, name, qty, descr = self._collect()
        if not name:
            messagebox.showwarning("Внимание", "Укажите наименование!", parent=self)
            return
        self.db.update_warehouse_item(self._current_id, cid, name, qty, descr)
        self._item_barcode(self._current_id)
        self.db.add_warehouse_name(name)
        self._log(f"Склад: позиция #{self._current_id} обновлена")
        self.refresh_dicts()
        self.load_items()

    def delete_item(self):
        if self._current_id is None:
            messagebox.showwarning("Внимание", "Выберите позицию!", parent=self)
            return
        if messagebox.askyesno("Подтверждение", "Удалить позицию со склада?", parent=self):
            self.db.delete_warehouse_item(self._current_id)
            self._log(f"Склад: позиция #{self._current_id} удалена")
            self.load_items()
            self.clear_form()

    def open_cells(self):
        from dialogs.storage_cells_dialog import StorageCellsDialog
        dlg = StorageCellsDialog(self, self.db, on_changed=self.refresh_dicts)
        self.wait_window(dlg)
        self.refresh_dicts()
        self.load_items()

    def open_names(self):
        from dialogs.warehouse_names_dialog import WarehouseNamesDialog
        dlg = WarehouseNamesDialog(self, self.db, on_changed=self.refresh_dicts)
        self.wait_window(dlg)
        self.refresh_dicts()

    def export(self):
        try:
            import openpyxl
            from openpyxl.styles import Font
        except ImportError:
            messagebox.showerror("Нет библиотеки", "pip install openpyxl", parent=self)
            return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx",
                                            initialfile="Склад.xlsx", parent=self)
        if not path:
            return
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Склад"
        ws.append(["Ячейка хранения", "Штрихкод ячейки", "Штрихкод позиции",
                   "Наименование", "Кол-во", "Описание", "Изменено"])
        for c in ws[1]:
            c.font = Font(bold=True)
        for iid in self.tree.get_children():
            ws.append(list(self.tree.item(iid)["values"]))
        ws2 = wb.create_sheet("Ячейки")
        ws2.append(["Номер ячейки", "Штрихкод", "Примечание"])
        for r in self.db.get_storage_cells():
            ws2.append([r["code"], r["barcode"], r["note"]])
        for col, w in (("A", 18), ("B", 18), ("C", 18), ("D", 50), ("E", 12), ("F", 50), ("G", 20)):
            ws.column_dimensions[col].width = w
        ws.freeze_panes = "A2"
        try:
            wb.save(path)
            messagebox.showinfo("Успех", f"Сохранено (2 листа):\n{path}", parent=self)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e), parent=self)
