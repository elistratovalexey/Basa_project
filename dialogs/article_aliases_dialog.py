# -*- coding: utf-8 -*-
"""Алиасы артикулов: связь кодов поставщиков с канонической номенклатурой + поиск дублей."""
import tkinter as tk
from tkinter import ttk, messagebox


class ArticleAliasesDialog(tk.Toplevel):
    def __init__(self, parent, db_manager, article=""):
        super().__init__(parent)
        self.db = db_manager
        self.title("Алиасы артикулов поставщиков")
        self.geometry("1150x620")
        self.current_nom_id = None

        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Поиск по номенклатуре:").pack(side=tk.LEFT)
        self.entry_search = ttk.Entry(top, width=30)
        self.entry_search.pack(side=tk.LEFT, padx=6)
        self.entry_search.insert(0, article)
        ttk.Button(top, text="Найти", command=self.load_nomenclature).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Показать все", command=self.show_all).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Найти дубли", command=self.open_duplicates).pack(side=tk.RIGHT, padx=4)

        body = ttk.Frame(self, padding=(8, 0))
        body.pack(fill="both", expand=True)

        left = ttk.LabelFrame(body, text="Номенклатура (канонические записи)", padding=6)
        left.pack(side=tk.LEFT, fill="both", expand=True)
        self.tree_nom = ttk.Treeview(left, columns=("id", "article", "man", "name"),
                                     show="headings", height=18)
        for c, t, w in (("id", "ID", 50), ("article", "Артикул", 150),
                        ("man", "Производитель", 130), ("name", "Наименование", 260)):
            self.tree_nom.heading(c, text=t)
            self.tree_nom.column(c, width=w, anchor="center" if c == "id" else "w")
        sb1 = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.tree_nom.yview)
        self.tree_nom.configure(yscroll=sb1.set)
        self.tree_nom.pack(side=tk.LEFT, fill="both", expand=True)
        sb1.pack(side=tk.RIGHT, fill="y")

        right = ttk.LabelFrame(body, text="Алиасы выбранной записи", padding=6)
        right.pack(side=tk.LEFT, fill="both", expand=True, padx=(8, 0))
        self.tree_alias = ttk.Treeview(right, columns=("id", "alias", "sup", "note"),
                                       show="headings", height=14)
        for c, t, w in (("id", "ID", 50), ("alias", "Алиас (код поставщика)", 180),
                        ("sup", "Поставщик", 140), ("note", "Примечание", 160)):
            self.tree_alias.heading(c, text=t)
            self.tree_alias.column(c, width=w, anchor="center" if c == "id" else "w")
        self.tree_alias.pack(fill="both", expand=True)

        form = ttk.Frame(right)
        form.pack(fill="x", pady=6)
        ttk.Label(form, text="Алиас:").grid(row=0, column=0, sticky="w")
        self.entry_alias = ttk.Entry(form, width=20)
        self.entry_alias.grid(row=0, column=1, padx=4)
        ttk.Label(form, text="Поставщик:").grid(row=0, column=2, sticky="w", padx=(8, 0))
        self.entry_sup = ttk.Entry(form, width=18)
        self.entry_sup.grid(row=0, column=3, padx=4)
        ttk.Button(form, text="Добавить", command=self.add_alias).grid(row=0, column=4, padx=6)
        ttk.Button(form, text="Удалить алиас", command=self.delete_alias).grid(row=1, column=1, pady=6, sticky="w")

        self.lbl_hint = ttk.Label(self, padding=8, foreground="#0066cc",
                                  text="Пример: 153048 = 153 048 (автоматически) и QSL-1/8-8 (алиас вручную).")
        self.lbl_hint.pack(fill="x")
        ttk.Button(self, text="Закрыть", command=self.destroy).pack(pady=(0, 8))

        self.tree_nom.bind("<<TreeviewSelect>>", self.on_select_nom)
        self.entry_search.bind("<Return>", lambda e: self.load_nomenclature())
        self.load_nomenclature()
        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def show_all(self):
        self.entry_search.delete(0, tk.END)
        self.load_nomenclature()

    def load_nomenclature(self):
        for i in self.tree_nom.get_children():
            self.tree_nom.delete(i)
        q = self.entry_search.get().strip()
        if q:
            rows = self.db.search_nomenclature(q, 'article')
            if not rows:
                rows = self.db.search_nomenclature(q, 'name')
        else:
            rows = self.db.get_nomenclature()[:400]
        for r in rows:
            self.tree_nom.insert("", tk.END, values=(
                r["id"], r["article"] or "", r["manufacturer"] or "", r["name_rus"] or r["name_eng"] or ""))
        kids = self.tree_nom.get_children()
        if kids:
            self.tree_nom.selection_set(kids[0])
            self.on_select_nom()

    def on_select_nom(self, event=None):
        sel = self.tree_nom.selection()
        if not sel:
            return
        self.current_nom_id = self.tree_nom.item(sel[0])["values"][0]
        for i in self.tree_alias.get_children():
            self.tree_alias.delete(i)
        for a in self.db.get_aliases(self.current_nom_id):
            self.tree_alias.insert("", tk.END, values=(a["id"], a["alias"], a["supplier"] or "", a["note"] or ""))

    def add_alias(self):
        if not self.current_nom_id:
            messagebox.showwarning("Внимание", "Выберите запись номенклатуры слева!")
            return
        ok, err = self.db.add_alias(self.current_nom_id, self.entry_alias.get(), self.entry_sup.get())
        if ok:
            self.entry_alias.delete(0, tk.END)
            self.on_select_nom()
        else:
            messagebox.showwarning("Не добавлено", err)

    def delete_alias(self):
        sel = self.tree_alias.selection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите алиас!")
            return
        self.db.delete_alias(self.tree_alias.item(sel[0])["values"][0])
        self.on_select_nom()

    def open_duplicates(self):
        DuplicatesDialog(self, self.db, on_merged=self.load_nomenclature)


class DuplicatesDialog(tk.Toplevel):
    def __init__(self, parent, db_manager, on_merged=None):
        super().__init__(parent)
        self.db = db_manager
        self.on_merged = on_merged
        self.groups = []
        self.title("Дубли номенклатуры")
        self.geometry("950x520")

        ttk.Label(self, padding=8, text="Группы записей, совпадающих после нормализации артикула "
                                        "(регистр, пробелы и разделители ignored).").pack(fill="x")
        cols = ("key", "ids", "articles")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=15)
        for c, t, w in (("key", "Норм. артикул", 160), ("ids", "ID записей", 140),
                        ("articles", "Артикулы / наименования", 560)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=8)

        bf = ttk.Frame(self, padding=8)
        bf.pack(fill="x")
        ttk.Label(bf, text="Оставить запись:").pack(side=tk.LEFT)
        self.combo_keep = ttk.Combobox(bf, width=45, state="readonly")
        self.combo_keep.pack(side=tk.LEFT, padx=6)
        self.rewrite = tk.BooleanVar(value=True)
        ttk.Checkbutton(bf, text="Переписать артикул в закупках и заказах",
                        variable=self.rewrite).pack(side=tk.LEFT, padx=10)
        ttk.Button(bf, text="Объединить", command=self.merge).pack(side=tk.LEFT, padx=6)
        ttk.Button(bf, text="Закрыть", command=self.destroy).pack(side=tk.RIGHT, padx=6)

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
        self.groups = self.db.find_duplicate_groups()
        for g in self.groups:
            key = self.db.compact_article(g[0]["article"])
            ids = ", ".join(str(r["id"]) for r in g)
            arts = " | ".join(f'{r["article"]} ({r["manufacturer"] or "—"})' for r in g)
            self.tree.insert("", tk.END, values=(key, ids, arts))
        if not self.groups:
            messagebox.showinfo("Дубли", "Дублей не найдено — справочник чистый.")

    def on_select(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        if idx >= len(self.groups):
            return
        g = self.groups[idx]
        vals = [f'{r["id"]} — {r["article"]} · {r["name_rus"] or ""}' for r in g]
        self.combo_keep['values'] = vals
        self.combo_keep.current(0)

    def merge(self):
        sel = self.tree.selection()
        if not sel or not self.combo_keep.get():
            messagebox.showwarning("Внимание", "Выберите группу и запись, которую оставляем!")
            return
        g = self.groups[self.tree.index(sel[0])]
        keep_id = int(self.combo_keep.get().split(" — ")[0])
        drop_ids = [r["id"] for r in g if r["id"] != keep_id]
        if not messagebox.askyesno("Подтверждение",
                                   f"Объединить {len(drop_ids)} записей в ID {keep_id}?\n"
                                   "Старые артикулы станут алиасами."):
            return
        n = self.db.merge_nomenclature(keep_id, drop_ids, rewrite_refs=self.rewrite.get())
        messagebox.showinfo("Готово", f"Объединено записей: {n}")
        self.load()
        if self.on_merged:
            try:
                self.on_merged()
            except Exception:
                pass