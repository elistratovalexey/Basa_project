# -*- coding: utf-8 -*-
"""Вкладка «Переписка»: письма проекта из Mail.ru, треды, статусы, риски,
привязка к заказам, извлечённые данные, вложения → импорт КП, обмен с облаком.
"""
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from tabs.base import BaseTab
from mail_db import MAIL_STATUSES


class CorrespondenceTab(BaseTab):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        self.mail_db = getattr(app, "mail_db", None)
        self._row_id = {}
        self._busy = False
        self.create_ui()

    # ==================================================================
    def create_ui(self):
        top = ttk.Frame(self.parent)
        top.pack(fill="x", pady=3)
        for t, c in (("Проверка почты", self.check_mail),
                     ("Синхронизация", self.sync_cloud),
                     ("Настройка почты", self.open_settings),
                     ("Разобрать", self.parse_selected),
                     ("В заказ…", self.link_order_dialog),
                     ("Отметить отвеченным", self.mark_replied),
                     ("Удалить из списка", self.delete_msg)):
            ttk.Button(top, text=t, command=c).pack(side=tk.LEFT, padx=2)
        self.lbl_state = ttk.Label(top, text="", foreground="#0066cc")
        self.lbl_state.pack(side=tk.RIGHT, padx=8)

        top2 = ttk.Frame(self.parent)
        top2.pack(fill="x", pady=2)
        ttk.Button(top2, text="Правила разбора", command=self.open_rules).pack(side=tk.LEFT, padx=2)
        ttk.Button(top2, text="Сохранить текст", command=self.save_body).pack(side=tk.LEFT, padx=2)
        self.lbl_summary = ttk.Label(top2, text="", font=("Arial", 9, "bold"), foreground="#0a58ca")
        self.lbl_summary.pack(side=tk.LEFT, padx=12)

        if self.mail_db is None:
            ttk.Label(self.parent, foreground="#b02a37", justify="left",
                      text="База переписки не подключена.\n"
                           "В app.py должно быть: self.mail_db = MailDatabase()\n"
                           "и вкладка создаётся после этого.").pack(padx=10, pady=10)
            return

        flt = ttk.Frame(self.parent)
        flt.pack(fill="x", pady=2)
        ttk.Label(flt, text="Направление:").pack(side=tk.LEFT, padx=(4, 3))
        self.c_type = ttk.Combobox(flt, width=20, state="readonly")
        self.c_type.pack(side=tk.LEFT)
        self.c_type.bind("<<ComboboxSelected>>", lambda e: self.load_messages())
        ttk.Label(flt, text="Поток:").pack(side=tk.LEFT, padx=(10, 3))
        self.c_dir = ttk.Combobox(flt, width=12, state="readonly",
                                  values=["Все", "Входящее", "Исходящее"])
        self.c_dir.set("Все")
        self.c_dir.pack(side=tk.LEFT)
        self.c_dir.bind("<<ComboboxSelected>>", lambda e: self.load_messages())
        ttk.Label(flt, text="Статус:").pack(side=tk.LEFT, padx=(10, 3))
        self.c_status = ttk.Combobox(flt, width=13, state="readonly", values=["Все"] + MAIL_STATUSES)
        self.c_status.set("Все")
        self.c_status.pack(side=tk.LEFT)
        self.c_status.bind("<<ComboboxSelected>>", lambda e: self.load_messages())
        self.v_wait = tk.BooleanVar(value=False)
        ttk.Checkbutton(flt, text="Без ответа", variable=self.v_wait,
                        command=self.load_messages).pack(side=tk.LEFT, padx=8)
        self.v_risk = tk.BooleanVar(value=False)
        ttk.Checkbutton(flt, text="⚠ Риски", variable=self.v_risk,
                        command=self.load_messages).pack(side=tk.LEFT, padx=4)
        self.v_threads = tk.BooleanVar(value=True)
        ttk.Checkbutton(flt, text="Треды", variable=self.v_threads,
                        command=self.load_messages).pack(side=tk.LEFT, padx=4)
        ttk.Label(flt, text="Поиск:").pack(side=tk.LEFT, padx=(10, 3))
        self.e_search = ttk.Entry(flt, width=20)
        self.e_search.pack(side=tk.LEFT)
        self.e_search.bind("<Return>", lambda e: self.load_messages())
        ttk.Button(flt, text="Сброс", command=self.reset_filters).pack(side=tk.LEFT, padx=6)

        # --- письма ---
        tf = ttk.LabelFrame(self.parent, text="Письма проекта", padding=6)
        tf.pack(fill="both", expand=True, padx=6, pady=4)
        cols = ("date", "sender", "subject", "type", "status", "flags", "link", "att", "thread")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", height=9)
        for c, t, w in (("date", "Дата", 115), ("sender", "От кого", 180),
                        ("subject", "Тема", 340), ("type", "Направление", 130),
                        ("status", "Статус", 105), ("flags", "⚑", 50),
                        ("link", "🔗 заказ", 80), ("att", "📎", 40), ("thread", "▸", 45)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w" if c in ("sender", "subject", "type") else "center")
        vs = ttk.Scrollbar(tf, orient=tk.VERTICAL, command=self.tree.yview)
        hs = ttk.Scrollbar(tf, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscroll=vs.set, xscroll=hs.set)
        self.tree.pack(side=tk.LEFT, fill="both", expand=True)
        vs.pack(side=tk.RIGHT, fill="y")
        hs.pack(side=tk.BOTTOM, fill="x")
        self.tree.tag_configure("new", font=("Arial", 9, "bold"))
        self.tree.tag_configure("risk", background="#f8d7da")
        self.tree.tag_configure("wait", background="#fff3cd")
        self.tree.tag_configure("closed", foreground="#888888")
        self.tree.tag_configure("out", foreground="#0a58ca")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        # --- действия над выбранным ---
        af = ttk.Frame(self.parent)
        af.pack(fill="x", padx=6)
        ttk.Label(af, text="Направление:").pack(side=tk.LEFT, padx=(4, 3))
        self.c_set_type = ttk.Combobox(af, width=20, state="readonly")
        self.c_set_type.pack(side=tk.LEFT)
        ttk.Button(af, text="Присвоить", command=self.apply_type).pack(side=tk.LEFT, padx=4)
        ttk.Label(af, text="Статус:").pack(side=tk.LEFT, padx=(10, 3))
        self.c_set_status = ttk.Combobox(af, width=13, state="readonly", values=MAIL_STATUSES)
        self.c_set_status.pack(side=tk.LEFT)
        ttk.Button(af, text="Применить", command=self.apply_status).pack(side=tk.LEFT, padx=4)
        self.v_needs = tk.BooleanVar(value=False)
        ttk.Checkbutton(af, text="Требует ответа", variable=self.v_needs,
                        command=self.apply_needs).pack(side=tk.LEFT, padx=8)
        ttk.Label(af, text="Заметка:").pack(side=tk.LEFT, padx=(8, 3))
        self.e_note = ttk.Entry(af, width=30)
        self.e_note.pack(side=tk.LEFT)
        ttk.Button(af, text="Сохранить", command=self.save_note).pack(side=tk.LEFT, padx=4)

        # --- низ: текст / вложения / извлечено / цепочка ---
        nb = ttk.Notebook(self.parent)
        nb.pack(fill="both", expand=True, padx=6, pady=4)
        t_text = ttk.Frame(nb, padding=6)
        t_att = ttk.Frame(nb, padding=6)
        t_ext = ttk.Frame(nb, padding=6)
        t_thread = ttk.Frame(nb, padding=6)
        nb.add(t_text, text="  Текст письма  ")
        nb.add(t_att, text="  Вложения  ")
        nb.add(t_ext, text="  Извлечено  ")
        nb.add(t_thread, text="  Цепочка  ")

        self.lbl_head = ttk.Label(t_text, text="", foreground="#0066cc", justify="left")
        self.lbl_head.pack(fill="x", pady=(0, 4))
        inner = ttk.Frame(t_text)
        inner.pack(fill="both", expand=True)
        self.txt = tk.Text(inner, wrap=tk.WORD, height=12, state="disabled", font=("Arial", 10))
        ts = ttk.Scrollbar(inner, orient=tk.VERTICAL, command=self.txt.yview)
        self.txt.configure(yscroll=ts.set)
        self.txt.pack(side=tk.LEFT, fill="both", expand=True)
        ts.pack(side=tk.RIGHT, fill="y")

        self.att_tree = ttk.Treeview(t_att, columns=("name", "size", "mime", "state"),
                                     show="headings", height=8)
        for c, t, w in (("name", "Файл", 380), ("size", "Размер", 90),
                        ("mime", "Тип", 160), ("state", "Доступен", 120)):
            self.att_tree.heading(c, text=t)
            self.att_tree.column(c, width=w, anchor="w" if c in ("name", "mime") else "center")
        self.att_tree.pack(fill="both", expand=True)
        ab = ttk.Frame(t_att)
        ab.pack(fill="x", pady=4)
        ttk.Button(ab, text="Открыть", command=self.open_attachment).pack(side=tk.LEFT, padx=3)
        ttk.Button(ab, text="Сохранить как…", command=self.save_attachment).pack(side=tk.LEFT, padx=3)
        ttk.Button(ab, text="Вложение → КП заказа", command=self.att_to_order).pack(side=tk.LEFT, padx=3)
        self.att_tree.bind("<Double-1>", lambda e: self.open_attachment())

        self.ext_tree = ttk.Treeview(t_ext, columns=("kind", "value", "extra"),
                                     show="headings", height=8)
        for c, t, w in (("kind", "Что найдено", 130), ("value", "Значение", 260), ("extra", "Пояснение", 220)):
            self.ext_tree.heading(c, text=t)
            self.ext_tree.column(c, width=w, anchor="w")
        self.ext_tree.pack(fill="both", expand=True)
        eb = ttk.Frame(t_ext)
        eb.pack(fill="x", pady=4)
        ttk.Button(eb, text="Обещанную дату → ETA заказа", command=self.apply_promise).pack(side=tk.LEFT, padx=3)
        ttk.Button(eb, text="Трек → в заказ", command=self.apply_tracking).pack(side=tk.LEFT, padx=3)

        self.th_tree = ttk.Treeview(t_thread, columns=("date", "sender", "subject", "dir"),
                                    show="headings", height=8)
        for c, t, w in (("date", "Дата", 120), ("sender", "От кого", 200),
                        ("subject", "Тема", 400), ("dir", "Поток", 100)):
            self.th_tree.heading(c, text=t)
            self.th_tree.column(c, width=w, anchor="w" if c != "dir" else "center")
        self.th_tree.pack(fill="both", expand=True)
        self.th_tree.bind("<<TreeviewSelect>>", self.on_thread_select)

        self.load_messages()

    # ==================================================================
    def _pid(self):
        return self.db_manager.get_project_id(self.app.current_project or "")

    def _types(self):
        try:
            return self.db_manager.get_work_types()
        except Exception:
            return []

    def _sel_id(self):
        sel = self.tree.selection()
        return self._row_id.get(sel[-1]) if sel else None

    def reset_filters(self):
        self.c_type.set("Все")
        self.c_dir.set("Все")
        self.c_status.set("Все")
        self.v_wait.set(False)
        self.v_risk.set(False)
        self.e_search.delete(0, tk.END)
        self.load_messages()

    def load_messages(self):
        if self.mail_db is None:
            return
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
            self.lbl_summary.config(text="Выберите проект")
            self._clear_bottom()
            return
        wt = self.c_type.get()
        dr = self.c_dir.get()
        stt = self.c_status.get()
        rows = self.mail_db.get_messages(
            pid,
            work_type=None if wt in ("", "Все") else wt,
            direction=None if dr in ("", "Все") else dr,
            status=None if stt in ("", "Все") else stt,
            search=self.e_search.get().strip() or None,
            only_unanswered=self.v_wait.get(),
            only_risk=self.v_risk.get(),
            threads=self.v_threads.get())
        for r in rows:
            flags = ("⚠" if r["risk_flag"] else "") + ("✉" if r["needs_reply"] and not r["replied_at"] else "")
            tags = []
            if r["status"] == "Новое":
                tags.append("new")
            if r["risk_flag"]:
                tags.append("risk")
            elif r["needs_reply"] and not r["replied_at"] and r["direction"] == "Входящее":
                tags.append("wait")
            if r["status"] == "Закрыто":
                tags.append("closed")
            if r["direction"] == "Исходящее":
                tags.append("out")
            iid = self.tree.insert("", tk.END, tags=tuple(tags), values=(
                r["date_sent"] or r["date_iso"], r["sender"], r["subject"],
                r["work_type"] or "—", r["status"], flags,
                f'№{r["order_batch_id"]}' if r["order_batch_id"] else "",
                r["att_count"] or "", f'▸{r["thread_n"]}' if (r["thread_n"] or 1) > 1 else ""))
            self._row_id[iid] = r["id"]
        s = self.mail_db.stats(pid)
        self.lbl_summary.config(
            text=(f"Писем {s['n']} · новых {s['new']} · без ответа {s['wait']} · ⚠ {s['risk']} · "
                  f"привязано {s['linked']} · показано {len(rows)} · "
                  f"БД {self.mail_db.db_size_mb():.1f} МБ"))
        self._clear_bottom()

    def refresh(self):
        self.load_messages()

    def _clear_bottom(self):
        self.lbl_head.config(text="")
        self.txt.config(state="normal")
        self.txt.delete("1.0", tk.END)
        self.txt.config(state="disabled")
        for tv in (self.att_tree, self.ext_tree, self.th_tree):
            for i in tv.get_children():
                tv.delete(i)

    # ==================================================================
    def on_select(self, event=None):
        mid = self._sel_id()
        if not mid:
            return
        m = self.mail_db.get_message(mid)
        self.lbl_head.config(
            text=f'{m.get("date_sent") or ""} · {m.get("sender") or ""}\n'
                 f'Кому: {m.get("recipients") or "—"}   Тема: {m.get("subject") or ""}')
        self.txt.config(state="normal")
        self.txt.delete("1.0", tk.END)
        self.txt.insert("1.0", self.mail_db.get_body(mid) or "(пустое письмо)")
        self.txt.config(state="disabled")
        self.c_set_type.set(m.get("work_type") or "")
        self.c_set_status.set(m.get("status") or "Новое")
        self.v_needs.set(bool(m.get("needs_reply")))
        self.e_note.delete(0, tk.END)
        self.e_note.insert(0, m.get("note") or "")

        for i in self.att_tree.get_children():
            self.att_tree.delete(i)
        for a in self.mail_db.get_attachments(mid):
            local = a["local_path"] or ""
            state = "локально" if local and os.path.exists(local) else (
                "в облаке" if a["remote_path"] else "нет файла")
            self.att_tree.insert("", tk.END, iid=str(a["id"]), values=(
                a["name"], f'{(a["size"] or 0) / 1024:.0f} КБ', a["mime"], state))

        for i in self.ext_tree.get_children():
            self.ext_tree.delete(i)
        for e in self.mail_db.get_extracted(mid):
            self.ext_tree.insert("", tk.END, values=(e["kind"], e["value"], e["extra"]))

        for i in self.th_tree.get_children():
            self.th_tree.delete(i)
        for t in self.mail_db.get_thread(m["project_id"], m["thread_id"]):
            self.th_tree.insert("", tk.END, iid=str(t["id"]), values=(
                t["date_sent"] or t["date_iso"], t["sender"], t["subject"], t["direction"]))

    def on_thread_select(self, event=None):
        sel = self.th_tree.selection()
        if not sel:
            return
        mid = int(sel[0])
        m = self.mail_db.get_message(mid)
        self.txt.config(state="normal")
        self.txt.delete("1.0", tk.END)
        self.txt.insert("1.0", self.mail_db.get_body(mid) or "")
        self.txt.config(state="disabled")
        self.lbl_head.config(text=f'{m.get("date_sent")} · {m.get("sender")} · {m.get("subject")}')

    # ==================================================================
    def apply_type(self):
        mid = self._sel_id()
        t = self.c_set_type.get().strip()
        if not mid or not t:
            messagebox.showwarning("Внимание", "Выберите письмо и направление!")
            return
        for iid in self.tree.selection():
            self.mail_db.set_field(self._row_id[iid], "work_type", t)
        self.app.log_action(f"Переписка: направление «{t}» присвоено {len(self.tree.selection())} письмам")
        self.load_messages()

    def apply_status(self):
        mid = self._sel_id()
        s = self.c_set_status.get().strip()
        if not mid or not s:
            return
        for iid in self.tree.selection():
            self.mail_db.set_status(self._row_id[iid], s)
        self.load_messages()

    def apply_needs(self):
        mid = self._sel_id()
        if mid:
            self.mail_db.set_field(mid, "needs_reply", 1 if self.v_needs.get() else 0)
            self.load_messages()

    def mark_replied(self):
        mid = self._sel_id()
        if not mid:
            messagebox.showwarning("Внимание", "Выберите письмо!")
            return
        for iid in self.tree.selection():
            self.mail_db.mark_replied(self._row_id[iid])
        self.load_messages()

    def save_note(self):
        mid = self._sel_id()
        if mid:
            self.mail_db.set_field(mid, "note", self.e_note.get().strip())
            self.lbl_state.config(foreground="#198754", text="✓ заметка сохранена")

    def delete_msg(self):
        sel = self.tree.selection()
        if not sel:
            return
        if not messagebox.askyesno("Подтверждение",
                                   f"Удалить {len(sel)} писем из списка?\nВ ящике они останутся."):
            return
        for iid in sel:
            self.mail_db.delete_message(self._row_id[iid])
        self.load_messages()

    def save_body(self):
        mid = self._sel_id()
        if not mid:
            return
        m = self.mail_db.get_message(mid)
        path = filedialog.asksaveasfilename(defaultextension=".txt",
                                            initialfile=(m.get("subject") or "письмо")[:50] + ".txt")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(f'Дата: {m.get("date_sent")}\nОт: {m.get("sender")}\n'
                        f'Кому: {m.get("recipients")}\nТема: {m.get("subject")}\n\n'
                        f'{self.mail_db.get_body(mid)}')
            messagebox.showinfo("Готово", f"Сохранено:\n{path}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    # ==================================================================
    def parse_selected(self):
        mid = self._sel_id()
        if not mid:
            messagebox.showwarning("Внимание", "Выберите письмо!")
            return
        try:
            from mail_extract import apply_to_message
            m = self.mail_db.get_message(mid)
            m["body"] = self.mail_db.get_body(mid)
            info = apply_to_message(self.mail_db, self.db_manager, mid, m, self._types())
            self.load_messages()
            self.on_select()
            found = ", ".join(f"{k}: {v}" for k, v in info["counts"].items()) or "ничего"
            msg = f"Направление: {info['type']}\nНайдено: {found}"
            if info["batch_id"]:
                msg += f"\nПривязано к заказу №{info['batch_id']} ({info['link_how']})"
            if info["risk"]:
                msg += f"\n⚠ Риски: {info['risk']}"
            if info["promise_shift"]:
                msg += f"\nСрок: {info['promise_shift']}"
            messagebox.showinfo("Разбор письма", msg)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def link_order_dialog(self):
        mid = self._sel_id()
        if not mid:
            messagebox.showwarning("Внимание", "Выберите письмо!")
            return
        pid = self._pid()
        batches = [b for b in self.db_manager.get_order_batches()
                   if (b["project_name"] or "") == (self.app.current_project or "")]
        if not batches:
            messagebox.showinfo("Заказы", "В проекте нет заказов.")
            return
        win = tk.Toplevel(self.root)
        win.title("Привязать письмо к заказу")
        win.geometry("560x160")
        win.transient(self.root)
        ttk.Label(win, text="Заказ:").pack(padx=10, pady=(12, 4), anchor="w")
        mapping = {}
        for b in batches:
            lbl = (f'№{b["order_batch_id"]} · {b["supplier"] or "—"} · '
                   f'{b["invoice_number"] or "без инвойса"} · {b["order_date"] or ""}')
            mapping[lbl] = b["order_batch_id"]
        combo = ttk.Combobox(win, values=list(mapping.keys()), width=64, state="readonly")
        combo.pack(padx=10)
        combo.current(0)

        def do():
            b = mapping.get(combo.get())
            if b:
                inv = next((x["invoice_number"] or "" for x in batches if x["order_batch_id"] == b), "")
                self.mail_db.link_order(mid, b, inv)
                self.app.log_action(f"Переписка: письмо привязано к заказу №{b}")
            win.destroy()
            self.load_messages()
        bf = ttk.Frame(win)
        bf.pack(pady=10)
        ttk.Button(bf, text="Привязать", command=do).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text="Отмена", command=win.destroy).pack(side=tk.LEFT, padx=5)
        win.grab_set()

    def _linked_batch(self):
        mid = self._sel_id()
        if not mid:
            messagebox.showwarning("Внимание", "Выберите письмо!")
            return None, None
        m = self.mail_db.get_message(mid)
        if not m.get("order_batch_id"):
            messagebox.showwarning("Внимание", "Письмо не привязано к заказу.\nНажмите «В заказ…».")
            return None, None
        return mid, m["order_batch_id"]

    def apply_promise(self):
        mid, batch = self._linked_batch()
        if not batch:
            return
        rows = [e for e in self.mail_db.get_extracted(mid) if e["kind"] in ("promise", "date")]
        if not rows:
            messagebox.showinfo("Дата", "В письме не найдено дат.")
            return
        val = rows[0]["value"]
        if messagebox.askyesno("ETA", f"Записать в заказ №{batch} обещанную дату {val}?"):
            self.db_manager.set_order_status(batch, eta_date=val)
            self.app.log_action(f"Переписка: ETA заказа №{batch} = {val} (из письма)")
            messagebox.showinfo("Готово", "ETA заказа обновлён.")

    def apply_tracking(self):
        mid, batch = self._linked_batch()
        if not batch:
            return
        rows = [e for e in self.mail_db.get_extracted(mid) if e["kind"] == "track"]
        if not rows:
            messagebox.showinfo("Трек", "В письме не найдено трек-номеров.")
            return
        val = rows[0]["value"]
        if messagebox.askyesno("Трек", f"Записать трек {val} в заказ №{batch}?"):
            self.db_manager.set_order_status(batch, tracking=val)
            messagebox.showinfo("Готово", "Трек записан в заказ.")

    # ==================================================================
    def _att_store(self):
        from mail_client import AttachmentStore
        return AttachmentStore(self.mail_db, log=print)

    def _selected_att(self):
        sel = self.att_tree.selection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите вложение!")
            return None
        mid = self._sel_id()
        atts = {str(a["id"]): dict(a) for a in self.mail_db.get_attachments(mid)}
        return atts.get(sel[0])

    def open_attachment(self):
        a = self._selected_att()
        if not a:
            return
        try:
            path = self._att_store().ensure_local(a)
            if not path:
                messagebox.showwarning("Файл", "Файл недоступен локально и в облаке.")
                return
            from utils import open_path
            open_path(path)
            self.on_select()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def save_attachment(self):
        a = self._selected_att()
        if not a:
            return
        try:
            path = self._att_store().ensure_local(a)
            if not path:
                messagebox.showwarning("Файл", "Файл недоступен.")
                return
            dst = filedialog.asksaveasfilename(initialfile=a["name"])
            if dst:
                import shutil
                shutil.copy2(path, dst)
                messagebox.showinfo("Готово", f"Сохранено:\n{dst}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def att_to_order(self):
        """Вложение (КП/прайс) → существующий импортёр сопоставления с позициями заказа."""
        a = self._selected_att()
        if not a:
            return
        mid, batch = self._linked_batch()
        if not batch:
            return
        ext = os.path.splitext(a["name"])[1].lower()
        if ext not in (".xlsx", ".xls", ".pdf"):
            messagebox.showinfo("Формат", "Импорт КП поддерживает Excel и PDF.")
            return
        try:
            from dialogs.order_file_parser import parse_file_to_rows_with_text
            from dialogs.file_import_dialog import FileImportMatchDialog
        except ImportError as e:
            messagebox.showerror("Ошибка", f"Модули импорта КП недоступны:\n{e}")
            return
        try:
            path = self._att_store().ensure_local(a)
            if not path:
                messagebox.showwarning("Файл", "Вложение недоступно.")
                return
            rows, text = parse_file_to_rows_with_text(path)
            if not rows:
                messagebox.showwarning("Пусто", "В файле не найдено строк.")
                return
            items = self.db_manager.get_order_items(batch)
            if not items:
                messagebox.showwarning("Заказ", f"В заказе №{batch} нет позиций.")
                return
            dlg = FileImportMatchDialog(self.root, items, rows, self.db_manager, text)
            dlg.parent = self.app
            self.root.wait_window(dlg)
            self.app.log_action(f"Переписка: вложение «{a['name']}» → КП заказа №{batch}")
            messagebox.showinfo("Готово", "Сопоставление выполнено. Проверьте цены/сроки в заказе.")
        except Exception as e:
            messagebox.showerror("Ошибка импорта", str(e))

    # ==================================================================
    def open_settings(self):
        if self.mail_db is None:
            return
        try:
            from dialogs.mail_settings_dialog import MailSettingsDialog
        except ImportError as e:
            messagebox.showerror("Ошибка", f"Модуль настроек недоступен:\n{e}")
            return
        MailSettingsDialog(self.root, self.mail_db, self._types())

    def open_rules(self):
        if self.mail_db is None:
            return
        MailRulesDialog(self.root, self.mail_db, self._types())

    # ==================================================================
    def check_mail(self):
        if self.mail_db is None or self._busy:
            return
        cfg = self.mail_db.get_settings()
        if not cfg.get("email") or not cfg.get("password"):
            messagebox.showwarning("Почта", "Заполните «Настройка почты» (нужен пароль приложения).")
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
            self.root.after(0, lambda x=str(m): self.lbl_state.config(text=x[:90]))

        def work():
            try:
                from mail_client import MailClient, AttachmentStore
                from mail_extract import apply_to_message
                c = MailClient(cfg, log=print)
                c.connect()
                store = AttachmentStore(self.mail_db, log=print)
                folders = [(cfg.get("inbox") or "INBOX", "inbox", "Входящее")]
                if int(cfg.get("check_sent", 1)):
                    sent = c.sent_folder()
                    if sent:
                        folders.append((sent, "sent", "Исходящее"))
                added = 0
                for folder, key, direction in folders:
                    say(f"Читаю {folder}…")
                    found, last_uid, uv = c.fetch_new(
                        folder, key, direction, projects, self.mail_db,
                        int(cfg.get("limit_msgs", 300)), progress=say)
                    for m in found:
                        atts = m.pop("attachments", [])
                        mid = self.mail_db.add_message(m, m.get("body", ""))
                        if not mid:
                            continue
                        if atts:
                            store.store(mid, atts)
                        try:
                            apply_to_message(self.mail_db, self.db_manager, mid, m, types)
                        except Exception as e:
                            print(f"[mail] разбор: {e}")
                        added += 1
                    if uv:
                        self.mail_db.conn.execute(
                            f"UPDATE mail_settings SET uidvalidity_{key}=?, last_uid_{key}=? WHERE id=1",
                            (uv, last_uid or ""))
                        self.mail_db.conn.commit()
                c.close()
                from datetime import datetime as _dt
                self.mail_db.conn.execute("UPDATE mail_settings SET last_check=? WHERE id=1",
                                          (_dt.now().strftime("%d.%m.%Y %H:%M:%S"),))
                self.mail_db.conn.commit()
                self.root.after(0, lambda: self._done(added))
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                self.root.after(0, lambda x=msg: self._fail(x))
        threading.Thread(target=work, daemon=True).start()

    def _done(self, added):
        self._busy = False
        self.lbl_state.config(foreground="#198754", text=f"✓ Новых писем: {added}")
        self.app.log_action(f"Переписка: проверка почты, новых {added}")
        self.load_messages()

    def _fail(self, err):
        self._busy = False
        self.lbl_state.config(foreground="#b02a37", text="Ошибка проверки")
        self.app.log_action(f"Переписка: ошибка почты — {err}")
        messagebox.showerror("Почта", err)

    def sync_cloud(self):
        if self.mail_db is None or self._busy:
            return
        self._busy = True
        self.lbl_state.config(foreground="#0066cc", text="Синхронизация переписки…")

        def work():
            try:
                from mail_sync import MailSync
                s = MailSync(self.mail_db, log=lambda m: self.root.after(
                    0, lambda x=str(m): self.lbl_state.config(text=x[:90])))
                added, updated, size = s.sync()
                self.root.after(0, lambda: self._sync_done(added, updated, size))
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                self.root.after(0, lambda x=msg: self._fail(x))
        threading.Thread(target=work, daemon=True).start()

    def _sync_done(self, added, updated, size):
        self._busy = False
        self.lbl_state.config(foreground="#198754",
                              text=f"✓ Облако: +{added}, обновлено {updated}, {size / 1048576:.1f} МБ")
        self.app.log_action(f"Переписка: синхронизация (+{added}, обновлено {updated})")
        self.load_messages()


class MailRulesDialog(tk.Toplevel):
    """Правила разбора: ключевое слово → направление / действие / приоритет."""

    def __init__(self, parent, mail_db, types):
        super().__init__(parent)
        self.db = mail_db
        self.title("Правила разбора почты")
        self.geometry("760x480")
        self.transient(parent)
        self.tree = ttk.Treeview(self, columns=("kw", "type", "act", "pr"),
                                 show="headings", height=14)
        for c, t, w in (("kw", "Ключевое слово", 220), ("type", "Направление", 170),
                        ("act", "Действие", 150), ("pr", "Приоритет", 90)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w" if c != "pr" else "center")
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)
        f = ttk.Frame(self)
        f.pack(fill="x", padx=8)
        ttk.Label(f, text="Слово:").grid(row=0, column=0, sticky="w")
        self.e_kw = ttk.Entry(f, width=24)
        self.e_kw.grid(row=0, column=1, padx=4)
        ttk.Label(f, text="Направление:").grid(row=0, column=2, sticky="w")
        self.c_type = ttk.Combobox(f, width=20, values=[""] + types)
        self.c_type.grid(row=0, column=3, padx=4)
        ttk.Label(f, text="Действие:").grid(row=1, column=0, sticky="w", pady=4)
        self.c_act = ttk.Combobox(f, width=22,
                                  values=["", "invoice", "offer", "packing", "tracking",
                                          "shipping", "payment", "customs", "design", "risk"])
        self.c_act.grid(row=1, column=1, padx=4)
        ttk.Label(f, text="Приоритет:").grid(row=1, column=2, sticky="w")
        self.e_pr = ttk.Entry(f, width=8)
        self.e_pr.grid(row=1, column=3, sticky="w", padx=4)
        self.e_pr.insert(0, "10")
        bf = ttk.Frame(self)
        bf.pack(pady=8)
        for t, c in (("Добавить / обновить", self.add), ("Удалить", self.delete),
                     ("Закрыть", self.destroy)):
            ttk.Button(bf, text=t, command=c).pack(side=tk.LEFT, padx=4)
        ttk.Label(self, foreground="gray",
                  text="Действие risk помечает письмо ⚠. Остальные — подсказки для разбора."
                  ).pack(pady=(0, 8))
        self.tree.bind("<<TreeviewSelect>>", self.pick)
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
        for r in self.db.get_rules():
            self.tree.insert("", tk.END, iid=str(r["id"]),
                             values=(r["keyword"], r["work_type"], r["action"], r["priority"]))

    def pick(self, e=None):
        s = self.tree.selection()
        if not s:
            return
        v = self.tree.item(s[0])["values"]
        self.e_kw.delete(0, tk.END)
        self.e_kw.insert(0, v[0])
        self.c_type.set(v[1] or "")
        self.c_act.set(v[2] or "")
        self.e_pr.delete(0, tk.END)
        self.e_pr.insert(0, str(v[3]))

    def add(self):
        try:
            pr = int(self.e_pr.get() or 10)
        except ValueError:
            pr = 10
        if self.db.add_rule(self.e_kw.get(), self.c_type.get(), self.c_act.get(), pr):
            self.reload()
        else:
            messagebox.showwarning("Внимание", "Пустое ключевое слово", parent=self)

    def delete(self):
        s = self.tree.selection()
        if s and messagebox.askyesno("Подтверждение", "Удалить правило?", parent=self):
            self.db.delete_rule(int(s[0]))
            self.reload()
