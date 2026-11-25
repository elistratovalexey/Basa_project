# -*- coding: utf-8 -*-
"""Вкладка «Переписка»: письма проекта из почты Mail.ru + тип (направление)."""
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from tabs.base import BaseTab


class CorrespondenceTab(BaseTab):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        self._row_id = {}
        self._busy = False
        self.create_ui()

    def create_ui(self):
        top = ttk.Frame(self.parent)
        top.pack(fill="x", pady=4)
        ttk.Button(top, text="Проверка", command=self.check_mail).pack(side=tk.LEFT, padx=3)
        ttk.Button(top, text="Настройка почты", command=self.open_settings).pack(side=tk.LEFT, padx=3)
        ttk.Button(top, text="Удалить из списка", command=self.delete_msg).pack(side=tk.LEFT, padx=3)
        ttk.Button(top, text="Сохранить текст в файл", command=self.save_body).pack(side=tk.LEFT, padx=3)
        self.lbl_state = ttk.Label(top, text="", foreground="#0066cc")
        self.lbl_state.pack(side=tk.RIGHT, padx=8)

        flt = ttk.Frame(self.parent)
        flt.pack(fill="x", pady=2)
        ttk.Label(flt, text="Направление (тип работ):").pack(side=tk.LEFT, padx=(4, 4))
        self.c_type = ttk.Combobox(flt, width=24, state="readonly")
        self.c_type.pack(side=tk.LEFT)
        self.c_type.bind("<<ComboboxSelected>>", lambda e: self.load_messages())
        ttk.Label(flt, text="Поток:").pack(side=tk.LEFT, padx=(12, 4))
        self.c_dir = ttk.Combobox(flt, width=13, state="readonly",
                                  values=["Все", "Входящее", "Исходящее"])
        self.c_dir.set("Все")
        self.c_dir.pack(side=tk.LEFT)
        self.c_dir.bind("<<ComboboxSelected>>", lambda e: self.load_messages())
        ttk.Label(flt, text="Поиск:").pack(side=tk.LEFT, padx=(12, 4))
        self.e_search = ttk.Entry(flt, width=24)
        self.e_search.pack(side=tk.LEFT)
        self.e_search.bind("<Return>", lambda e: self.load_messages())
        ttk.Button(flt, text="Сброс", command=self.reset_filters).pack(side=tk.LEFT, padx=8)
        self.lbl_count = ttk.Label(flt, text="", foreground="gray")
        self.lbl_count.pack(side=tk.LEFT, padx=8)

        # --- Письма ---
        tf = ttk.LabelFrame(self.parent, text="Письма проекта", padding=6)
        tf.pack(fill="both", expand=True, padx=6, pady=4)
        cols = ("date", "sender", "to", "subject", "type", "dir", "att")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", height=10)
        for c, t, w in (("date", "Дата", 120), ("sender", "От кого", 200),
                        ("to", "Кому", 180), ("subject", "Тема", 380),
                        ("type", "Направление (тип)", 150), ("dir", "Поток", 90),
                        ("att", "📎", 40)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center" if c in ("date", "dir", "att") else "w")
        vs = ttk.Scrollbar(tf, orient=tk.VERTICAL, command=self.tree.yview)
        hs = ttk.Scrollbar(tf, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscroll=vs.set, xscroll=hs.set)
        self.tree.pack(side=tk.LEFT, fill="both", expand=True)
        vs.pack(side=tk.RIGHT, fill="y")
        hs.pack(side=tk.BOTTOM, fill="x")
        self.tree.tag_configure("out", foreground="#0a58ca")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", self.on_double_click)

        # --- Назначение типа ---
        af = ttk.Frame(self.parent)
        af.pack(fill="x", padx=6)
        ttk.Label(af, text="Направление письма:").pack(side=tk.LEFT, padx=(4, 4))
        self.c_set_type = ttk.Combobox(af, width=24, state="readonly")
        self.c_set_type.pack(side=tk.LEFT)
        ttk.Button(af, text="Присвоить выбранным",
                   command=self.apply_type).pack(side=tk.LEFT, padx=6)
        ttk.Label(af, text="Заметка:").pack(side=tk.LEFT, padx=(12, 4))
        self.e_note = ttk.Entry(af, width=40)
        self.e_note.pack(side=tk.LEFT)
        ttk.Button(af, text="Сохранить заметку", command=self.save_note).pack(side=tk.LEFT, padx=6)

        # --- Текст письма ---
        bf = ttk.LabelFrame(self.parent, text="Текст письма", padding=6)
        bf.pack(fill="both", expand=True, padx=6, pady=4)
        self.lbl_head = ttk.Label(bf, text="", foreground="#0066cc", justify="left")
        self.lbl_head.pack(fill="x", pady=(0, 4))
        inner = ttk.Frame(bf)
        inner.pack(fill="both", expand=True)
        self.txt = tk.Text(inner, wrap=tk.WORD, height=12, state="disabled", font=("Arial", 10))
        ts = ttk.Scrollbar(inner, orient=tk.VERTICAL, command=self.txt.yview)
        self.txt.configure(yscroll=ts.set)
        self.txt.pack(side=tk.LEFT, fill="both", expand=True)
        ts.pack(side=tk.RIGHT, fill="y")
        self.lbl_att = ttk.Label(bf, text="", foreground="gray")
        self.lbl_att.pack(fill="x", pady=(4, 0))

    # ==================================================================
    def _pid(self):
        return self.db_manager.get_project_id(self.app.current_project or "")

    def _types(self):
        try:
            return self.db_manager.get_work_types()
        except Exception:
            return []

    def reset_filters(self):
        self.c_type.set("Все")
        self.c_dir.set("Все")
        self.e_search.delete(0, tk.END)
        self.load_messages()

    def load_messages(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        self._row_id = {}
        types = self._types()
        self.c_type["values"] = ["Все"] + types
        self.c_set_type["values"] = types
        if not self.c_type.get():
            self.c_type.set("Все")
        pid = self._pid()
        if not pid:
            self.lbl_count.config(text="Выберите проект")
            self._show_body(None)
            return
        wt = self.c_type.get()
        wt = None if wt in ("", "Все") else wt
        dr = self.c_dir.get()
        dr = None if dr in ("", "Все") else dr
        rows = self.db_manager.get_mail_messages(pid, wt, dr, self.e_search.get().strip() or None)
        for r in rows:
            iid = self.tree.insert("", tk.END, tags=("out",) if r["direction"] == "Исходящее" else (),
                                   values=(r["date_sent"] or r["date_iso"], r["sender"],
                                           r["recipients"], r["subject"], r["work_type"] or "—",
                                           r["direction"], "📎" if r["attachments"] else ""))
            self._row_id[iid] = r["id"]
        st = self.db_manager.mail_stats(pid)
        self.lbl_count.config(text=f"показано {len(rows)} · всего {st['total']} "
                                   f"(вх. {st['in']} / исх. {st['out']})")
        self._show_body(None)

    # Обратная совместимость с app.on_project_select
    def load_records(self):
        self.load_messages()

    def refresh(self):
        self.load_messages()

    # ==================================================================
    def on_select(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        msg = self.db_manager.get_mail_body(self._row_id[sel[-1]])
        self._show_body(msg)
        self.c_set_type.set(msg.get("work_type") or "")
        self.e_note.delete(0, tk.END)
        self.e_note.insert(0, msg.get("note") or "")

    def _show_body(self, msg):
        self.txt.config(state="normal")
        self.txt.delete("1.0", tk.END)
        if msg:
            self.lbl_head.config(
                text=f'{msg.get("date_sent") or ""} · {msg.get("sender") or ""}\n'
                     f'Кому: {msg.get("recipients") or "—"}   Тема: {msg.get("subject") or ""}')
            self.txt.insert("1.0", msg.get("body") or "(пустое письмо)")
            att = msg.get("attachments") or ""
            self.lbl_att.config(text=f"Вложения: {att}" if att else "Вложений нет")
        else:
            self.lbl_head.config(text="")
            self.lbl_att.config(text="")
        self.txt.config(state="disabled")

    def on_double_click(self, event):
        """Двойной клик по колонке «Направление» — быстрый выбор типа."""
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#5":
            return
        self.c_set_type.focus_set()
        try:
            self.c_set_type.tk.call("ttk::combobox::Post", self.c_set_type)
        except tk.TclError:
            pass
        return "break"

    def apply_type(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите письмо!")
            return
        t = self.c_set_type.get().strip()
        if not t:
            messagebox.showwarning("Внимание", "Выберите направление (тип работ)!")
            return
        for iid in sel:
            self.db_manager.set_mail_work_type(self._row_id[iid], t)
        self.app.log_action(f"Переписка: тип «{t}» присвоен {len(sel)} письмам")
        self.load_messages()

    def save_note(self):
        sel = self.tree.selection()
        if not sel:
            return
        self.db_manager.set_mail_note(self._row_id[sel[-1]], self.e_note.get().strip())
        self.lbl_state.config(text="✓ заметка сохранена")

    def delete_msg(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите письмо!")
            return
        if not messagebox.askyesno("Подтверждение",
                                   f"Удалить {len(sel)} писем из списка проекта?\n"
                                   "В почтовом ящике они останутся."):
            return
        for iid in sel:
            self.db_manager.delete_mail_message(self._row_id[iid])
        self.load_messages()

    def save_body(self):
        sel = self.tree.selection()
        if not sel:
            return
        from tkinter import filedialog
        msg = self.db_manager.get_mail_body(self._row_id[sel[-1]])
        path = filedialog.asksaveasfilename(defaultextension=".txt",
                                            initialfile=(msg.get("subject") or "письмо")[:60] + ".txt")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(f'Дата: {msg.get("date_sent")}\nОт: {msg.get("sender")}\n'
                        f'Кому: {msg.get("recipients")}\nТема: {msg.get("subject")}\n\n'
                        f'{msg.get("body") or ""}')
            messagebox.showinfo("Готово", f"Сохранено:\n{path}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    # ==================================================================
    def open_settings(self):
        try:
            from dialogs.mail_settings_dialog import MailSettingsDialog
        except ImportError as e:
            messagebox.showerror("Ошибка", f"Модуль настроек недоступен:\n{e}")
            return
        MailSettingsDialog(self.root, self.db_manager)

    def check_mail(self):
        if self._busy:
            messagebox.showinfo("Почта", "Проверка уже выполняется.")
            return
        cfg = self.db_manager.get_mail_settings()
        if not cfg.get("email") or not cfg.get("password"):
            messagebox.showwarning("Почта", "Сначала заполните «Настройка почты».")
            self.open_settings()
            return
        projects = [{"id": p["id"], "name": p["name"]} for p in self.db_manager.get_all_projects()]
        if not int(cfg.get("all_projects", 1)):
            pid = self._pid()
            projects = [p for p in projects if p["id"] == pid]
        if not projects:
            messagebox.showwarning("Почта", "Нет проектов для сопоставления.")
            return
        self._busy = True
        self.lbl_state.config(foreground="#0066cc", text="Проверка почты…")
        types = self._types()

        def say(m):
            self.root.after(0, lambda: self.lbl_state.config(text=str(m)[:90]))

        def work():
            try:
                from mail_client import MailClient, guess_work_type
                c = MailClient(cfg, log=lambda m: print(m))
                c.connect()
                folders = [(cfg.get("inbox") or "INBOX", "Входящее")]
                if int(cfg.get("check_sent", 1)):
                    sent = c.sent_folder()
                    if sent:
                        folders.append((sent, "Исходящее"))
                added = 0
                for folder, direction in folders:
                    say(f"Читаю {folder}…")
                    for m in c.fetch(folder, direction, projects,
                                     int(cfg.get("limit_msgs", 200)), progress=say):
                        if self.db_manager.mail_exists(m["project_id"], m["folder"], m["uid"]):
                            continue
                        m["work_type"] = guess_work_type(m["subject"], m["body"], types,
                                                         cfg.get("default_type") or "")
                        if self.db_manager.add_mail_message(m):
                            added += 1
                c.close()
                self.root.after(0, lambda: self._done(added))
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                self.root.after(0, lambda m=msg: self._fail(m))
        threading.Thread(target=work, daemon=True).start()

    def _done(self, added):
        self._busy = False
        self.lbl_state.config(foreground="#198754", text=f"✓ Новых писем: {added}")
        self.app.log_action(f"Переписка: проверка почты, новых писем {added}")
        self.load_messages()

    def _fail(self, err):
        self._busy = False
        self.lbl_state.config(foreground="#b02a37", text="Ошибка проверки")
        self.app.log_action(f"Переписка: ошибка почты — {err}")
        messagebox.showerror("Почта", err)
