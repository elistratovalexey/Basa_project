# -*- coding: utf-8 -*-
"""Сквозной поиск Ctrl+K: артикул, инвойс, поставщик, проект — всё сразу."""
import tkinter as tk
from tkinter import ttk, messagebox


class GlobalSearchDialog(tk.Toplevel):
    def __init__(self, parent, db_manager, app=None):
        super().__init__(parent)
        self.db = db_manager
        self.app = app
        self.results = []
        self._by_iid = {}
        self._job = None

        self.title("Сквозной поиск — Ctrl+K")
        self.geometry("1250x680")
        try:
            from dialogs.window_geometry import restore_geometry, track_geometry
            restore_geometry(self, "global_search", "1250x680")
            track_geometry(self, "global_search")
        except Exception:
            pass

        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Найти:", font=("Arial", 10, "bold")).pack(side=tk.LEFT)
        self.entry = ttk.Entry(top, width=60, font=("Arial", 11))
        self.entry.pack(side=tk.LEFT, padx=8, fill="x", expand=True)
        ttk.Button(top, text="Найти", command=self.do_search).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Очистить", command=self.clear).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Закрыть", command=self.destroy).pack(side=tk.RIGHT, padx=4)

        hint = ttk.Label(self, padding=(10, 0), foreground="gray",
                         text="Артикул, наименование, инвойс, поставщик, проект, номер поставки, ИНН, телефон… "
                              "Enter — открыть первый результат, двойной клик — перейти к записи, Esc — закрыть.")
        hint.pack(fill="x")
        self.lbl_counts = ttk.Label(self, padding=(10, 4), foreground="#0066cc", text="")
        self.lbl_counts.pack(fill="x")

        tbl = ttk.Frame(self, padding=(8, 0))
        tbl.pack(fill="both", expand=True)
        cols = ("kind", "project", "ref", "title", "subtitle", "extra")
        self.tree = ttk.Treeview(tbl, columns=cols, show="headings", height=18)
        for c, t, w in (("kind", "Тип", 120), ("project", "Проект", 140), ("ref", "№ / ID", 80),
                        ("title", "Артикул / Наименование / Инвойс", 400),
                        ("subtitle", "Производитель / Сумма", 200), ("extra", "Дополнительно", 280)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center" if c == "ref" else "w")
        sb = ttk.Scrollbar(tbl, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        self.tree.pack(side=tk.LEFT, fill="both", expand=True)
        sb.pack(side=tk.RIGHT, fill="y")

        prev = ttk.LabelFrame(self, text="Подробности", padding=6)
        prev.pack(fill="x", padx=8, pady=6)
        self.txt = tk.Text(prev, height=5, wrap=tk.WORD)
        self.txt.pack(fill="x")
        self.txt.config(state="disabled")

        bf = ttk.Frame(self, padding=(8, 0, 8, 8))
        bf.pack(fill="x")
        ttk.Button(bf, text="Открыть / перейти", command=self.open_selected).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Копировать артикул/название", command=self.copy_title).pack(side=tk.LEFT, padx=4)

        self.entry.bind("<KeyRelease>", self._on_type)
        self.entry.bind("<Return>", lambda e: self.open_selected(first=True))
        self.entry.bind("<Down>", lambda e: self._focus_tree())
        self.tree.bind("<Double-1>", lambda e: self.open_selected())
        self.tree.bind("<Return>", lambda e: self.open_selected())
        self.tree.bind("<<TreeviewSelect>>", self._show_preview)
        self.bind("<Escape>", lambda e: self.destroy())

        self.after(120, self.entry.focus_set)
        self._safe_grab()

    def _safe_grab(self, attempts=10):
        try:
            if self.winfo_exists() and self.winfo_viewable():
                self.grab_set()
            elif attempts > 0:
                self.after(50, lambda a=attempts - 1: self._safe_grab(a))
        except tk.TclError:
            pass

    # ---------------- поиск ----------------
    def _on_type(self, event=None):
        if event and event.keysym in ("Return", "Down", "Up", "Escape"):
            return
        if self._job:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
        self._job = self.after(300, self.do_search)

    def clear(self):
        self.entry.delete(0, tk.END)
        for i in self.tree.get_children():
            self.tree.delete(i)
        self.results = []
        self._by_iid = {}
        self.lbl_counts.config(text="")
        self._set_preview("")
        self.entry.focus_set()

    def do_search(self):
        self._job = None
        q = self.entry.get().strip()
        for i in self.tree.get_children():
            self.tree.delete(i)
        self._by_iid = {}
        if len(q) < 2:
            self.lbl_counts.config(text="Введите минимум 2 символа")
            return
        try:
            self.results = self.db.search_everything(q)
        except Exception as e:
            messagebox.showerror("Ошибка поиска", str(e))
            return
        counts = {}
        for r in self.results:
            iid = self.tree.insert("", tk.END, values=(
                r["kind"], r["project"], r["ref"], r["title"], r["subtitle"], r["extra"]))
            self._by_iid[iid] = r
            counts[r["kind"]] = counts.get(r["kind"], 0) + 1
        if self.results:
            self.lbl_counts.config(text=f"Найдено {len(self.results)}: " +
                                   " · ".join(f"{k} — {v}" for k, v in counts.items()))
            kids = self.tree.get_children()
            self.tree.selection_set(kids[0])
            self.tree.see(kids[0])
            self._show_preview()
        else:
            self.lbl_counts.config(text="Ничего не найдено")
            self._set_preview("")

    def _focus_tree(self):
        kids = self.tree.get_children()
        if kids:
            self.tree.focus_set()
            self.tree.selection_set(kids[0])
            self.tree.see(kids[0])
        return "break"

    def _current(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return self._by_iid.get(sel[0])

    def _set_preview(self, text):
        self.txt.config(state="normal")
        self.txt.delete("1.0", tk.END)
        self.txt.insert("1.0", text)
        self.txt.config(state="disabled")

    def _show_preview(self, event=None):
        r = self._current()
        if not r:
            return
        self._set_preview(
            f'Тип: {r["kind"]}\nПроект: {r["project"] or "—"}\n'
            f'№ / ID: {r["ref"]}\n{r["title"]}\n{r["subtitle"]}\n{r["extra"]}')

    def copy_title(self):
        r = self._current()
        if not r:
            return
        self.clipboard_clear()
        self.clipboard_append(r["title"])

    # ---------------- переход к записи ----------------
    def open_selected(self, first=False):
        if first and not self.tree.selection():
            kids = self.tree.get_children()
            if kids:
                self.tree.selection_set(kids[0])
        r = self._current()
        if not r:
            return
        p = r["payload"]
        t = p.get("type")
        try:
            if t == "project":
                self._goto_project(p["project"])
            elif t == "purchase":
                self._goto_purchase(p["project"], p["number"])
            elif t == "order":
                self._open_order(p["batch_id"], p.get("project"))
            elif t == "spec":
                self._open_spec(p["spec_id"])
            elif t == "payments":
                self._open_payments(p["spec_id"])
            elif t == "supplier":
                self._open_suppliers()
            elif t == "nomenclature":
                self._nomenclature_to_purchase(p)
            else:
                messagebox.showinfo("Запись", r["title"])
        except Exception as e:
            messagebox.showerror("Не удалось открыть", f"{type(e).__name__}: {e}")

    def _select_tab(self, title):
        nb = getattr(self.app, "notebook", None)
        if nb is None:
            return
        for tid in nb.tabs():
            if nb.tab(tid, "text").strip() == title:
                nb.select(tid)
                return

    def _goto_project(self, name):
        if not name or self.app is None:
            return
        combo = getattr(self.app, "combo_projects", None)
        if combo is not None and name in list(combo["values"]):
            combo.set(name)
            self.app.on_project_select()
        self.destroy()

    def _goto_purchase(self, project, number):
        if self.app is None:
            return
        if project:
            combo = getattr(self.app, "combo_projects", None)
            if combo is not None and project in list(combo["values"]):
                combo.set(project)
                self.app.on_project_select()
        self._select_tab("Закупки")
        tree = getattr(self.app, "purchase_tree", None)
        if tree is not None:
            for iid in tree.get_children():
                vals = tree.item(iid)["values"]
                if vals and str(vals[0]) == str(number):
                    tree.selection_set(iid)
                    tree.see(iid)
                    tree.focus_set()
                    break
        self.destroy()

    def _open_order(self, batch_id, project=None):
        from dialogs.order_dialog import OrderDialog
        holidays = getattr(self.app, "russian_holidays", set()) if self.app else set()
        OrderDialog(self, self.db, batch_id=batch_id,
                    russian_holidays=holidays, project_name=project or "")

    def _open_spec(self, spec_id):
        try:
            from dialogs.spec_edit_dialog import SpecEditDialog
            SpecEditDialog(self, self.db, spec_id)
            return
        except ImportError:
            pass
        self._open_payments(spec_id)

    def _open_payments(self, spec_id):
        from dialogs.payment_schedule_dialog import PaymentScheduleDialog
        row = self.db.conn.execute(
            "SELECT total FROM purchase_specifications WHERE id=?", (spec_id,)).fetchone()
        total = row["total"] if row else 0
        PaymentScheduleDialog(self, self.db, spec_id, total)

    def _open_suppliers(self):
        from dialogs.supplier_dialog import SupplierDialog
        SupplierDialog(self, self.db)

    def _nomenclature_to_purchase(self, p):
        if self.app is None or not getattr(self.app, "current_project", None):
            messagebox.showinfo("Номенклатура",
                                f'{p["article"]}\n{p["name"]}\n{p["name_eng"]}\n{p["manufacturer"]}')
            return
        from dialogs.purchase_dialog import PurchaseDialog
        tab = getattr(self.app, "purchases_tab", None)
        num = getattr(self.app, "purchase_counter", 1)
        data = {"article": p["article"], "name": p["name"], "name_eng": p["name_eng"],
                "manufacturer": p["manufacturer"], "quantity": 1}
        dlg = PurchaseDialog(self, "Добавить закупку из номенклатуры", num, data,
                             db_manager=self.db, project_name=self.app.current_project)
        self.wait_window(dlg)
        if dlg.result and tab is not None:
            pid = self.db.get_project_id(self.app.current_project)
            if pid:
                self.db.add_purchase(pid, dlg.result)
                tab.load_purchases()
                if hasattr(self.app, "log_action"):
                    self.app.log_action(f"Закупка №{dlg.result['number']} добавлена из поиска")