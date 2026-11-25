# -*- coding: utf-8 -*-
"""Настройка почты Mail.ru для вкладки «Переписка».
Пароль приложения сохраняется ЛОКАЛЬНО (mail_local.json) и в облако не уходит.
"""
import threading
import tkinter as tk
from tkinter import ttk, messagebox


class MailSettingsDialog(tk.Toplevel):
    def __init__(self, parent, mail_db, work_types=None):
        super().__init__(parent)
        self.db = mail_db
        self.cfg = mail_db.get_settings()
        self.title("Настройка почты — Mail.ru")
        self.geometry("700x600")
        self.resizable(False, False)
        self.transient(parent)

        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        self.v = {}
        rows = [("host", "IMAP сервер:", "imap.mail.ru"),
                ("port", "Порт:", "993"),
                ("email", "E-mail:", ""),
                ("password", "Пароль приложения:", ""),
                ("inbox", "Папка входящих:", "INBOX"),
                ("sent", "Папка отправленных (пусто = авто):", ""),
                ("limit_msgs", "Проверять последних писем:", "300"),
                ("interval_min", "Автопроверка почты, мин:", "30"),
                ("sync_interval_min", "Синхронизация с облаком, мин:", "60"),
                ("reply_sla_days", "Считать без ответа после, дн:", "2")]
        for i, (key, label, dflt) in enumerate(rows):
            ttk.Label(f, text=label).grid(row=i, column=0, sticky="w", pady=3)
            var = tk.StringVar(value=str(self.cfg.get(key) or dflt))
            ttk.Entry(f, textvariable=var, width=36,
                      show="•" if key == "password" else "").grid(row=i, column=1, sticky="w", padx=6)
            self.v[key] = var

        r = len(rows)
        self.b_ssl = tk.BooleanVar(value=bool(self.cfg.get("use_ssl", 1)))
        ttk.Checkbutton(f, text="SSL (993)", variable=self.b_ssl).grid(row=r, column=0, sticky="w")
        self.b_sent = tk.BooleanVar(value=bool(self.cfg.get("check_sent", 1)))
        ttk.Checkbutton(f, text="Проверять отправленные", variable=self.b_sent).grid(row=r, column=1, sticky="w")
        self.b_all = tk.BooleanVar(value=bool(self.cfg.get("all_projects", 1)))
        ttk.Checkbutton(f, text="Раскладывать по всем проектам", variable=self.b_all).grid(
            row=r + 1, column=0, columnspan=2, sticky="w")
        self.b_auto = tk.BooleanVar(value=bool(self.cfg.get("auto_check", 0)))
        ttk.Checkbutton(f, text="Автопроверка почты при запуске", variable=self.b_auto).grid(
            row=r + 2, column=0, columnspan=2, sticky="w")
        self.b_sync = tk.BooleanVar(value=bool(self.cfg.get("sync_auto", 1)))
        ttk.Checkbutton(f, text="Автосинхронизация переписки с облаком", variable=self.b_sync).grid(
            row=r + 3, column=0, columnspan=2, sticky="w")

        ttk.Label(f, text="Тип по умолчанию:").grid(row=r + 4, column=0, sticky="w", pady=4)
        self.c_type = ttk.Combobox(f, width=33, values=work_types or [])
        self.c_type.set(self.cfg.get("default_type") or "")
        self.c_type.grid(row=r + 4, column=1, sticky="w", padx=6)

        ttk.Label(f, foreground="gray", justify="left",
                  text="Mail.ru: Настройки аккаунта → Пароли для внешних приложений.\n"
                       "Обычный пароль от почты при включённой 2FA не подойдёт.\n"
                       "Письмо попадает в проект, если название проекта есть в теме\n"
                       "(в начале, середине или конце — регистр не важен).\n"
                       "Пароль хранится локально и НЕ синхронизируется в облако:\n"
                       "на каждом устройстве его нужно ввести один раз."
                  ).grid(row=r + 5, column=0, columnspan=2, sticky="w", pady=(10, 4))

        bf = ttk.Frame(self, padding=(12, 0, 12, 6))
        bf.pack(fill="x")
        ttk.Button(bf, text="Сохранить", command=self.save).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Проверить соединение", command=self.test).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Сбросить счётчики UID", command=self.reset_uid).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Закрыть", command=self.destroy).pack(side=tk.RIGHT, padx=4)
        self.lbl = ttk.Label(self, text="", foreground="#0066cc", padding=(12, 0, 12, 10),
                             wraplength=660, justify="left")
        self.lbl.pack(fill="x")
        self.bind("<Escape>", lambda e: self.destroy())
        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _collect(self):
        d = {k: v.get().strip() for k, v in self.v.items()}
        for k, dflt in (("port", 993), ("limit_msgs", 300), ("interval_min", 30),
                        ("sync_interval_min", 60), ("reply_sla_days", 2)):
            try:
                d[k] = int(d[k] or dflt)
            except ValueError:
                d[k] = dflt
        d["use_ssl"] = 1 if self.b_ssl.get() else 0
        d["check_sent"] = 1 if self.b_sent.get() else 0
        d["all_projects"] = 1 if self.b_all.get() else 0
        d["auto_check"] = 1 if self.b_auto.get() else 0
        d["sync_auto"] = 1 if self.b_sync.get() else 0
        d["default_type"] = self.c_type.get().strip()
        return d

    def save(self):
        data = self._collect()
        if not data["password"]:
            data.pop("password")        # не затирать сохранённый пустым полем
        self.db.save_settings(data)
        self.cfg = self.db.get_settings()
        self.lbl.config(foreground="#198754", text="✓ Настройки сохранены")

    def reset_uid(self):
        self.db.conn.execute("""UPDATE mail_settings SET
            uidvalidity_inbox='', uidvalidity_sent='', last_uid_inbox='', last_uid_sent='' WHERE id=1""")
        self.db.conn.commit()
        self.lbl.config(foreground="#0066cc",
                        text="Счётчики сброшены — следующая проверка перечитает последние письма заново.")

    def test(self):
        self.save()
        self.lbl.config(foreground="#0066cc", text="Проверяю соединение…")

        def work():
            try:
                from mail_client import MailClient
                c = MailClient(self.cfg, log=lambda m: None)
                c.connect()
                folders = c.folders()
                sent = c.sent_folder()
                c.close()
                msg = (f"✓ Соединение OK. Папок: {len(folders)}. "
                       f"Отправленные: {sent or 'не найдены'}")
                self.after(0, lambda: self.lbl.config(foreground="#198754", text=msg))
            except Exception as e:
                m = f"{type(e).__name__}: {e}"
                self.after(0, lambda x=m: self.lbl.config(foreground="#b02a37", text=x[:400]))
        threading.Thread(target=work, daemon=True).start()
