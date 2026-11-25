# -*- coding: utf-8 -*-
"""Настройка почты Mail.ru для вкладки «Переписка»."""
import tkinter as tk
from tkinter import ttk, messagebox


class MailSettingsDialog(tk.Toplevel):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.cfg = db.get_mail_settings()
        self.title("Настройка почты — Mail.ru")
        self.geometry("660x520")
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
                ("limit_msgs", "Проверять последних писем:", "200"),
                ("interval_min", "Автопроверка каждые, мин:", "30")]
        for i, (key, label, dflt) in enumerate(rows):
            ttk.Label(f, text=label).grid(row=i, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=str(self.cfg.get(key) or dflt))
            ttk.Entry(f, textvariable=var, width=38,
                      show="•" if key == "password" else "").grid(row=i, column=1, sticky="w", padx=6)
            self.v[key] = var

        r = len(rows)
        self.b_ssl = tk.BooleanVar(value=bool(self.cfg.get("use_ssl", 1)))
        ttk.Checkbutton(f, text="SSL (порт 993)", variable=self.b_ssl).grid(row=r, column=0, sticky="w")
        self.b_sent = tk.BooleanVar(value=bool(self.cfg.get("check_sent", 1)))
        ttk.Checkbutton(f, text="Проверять отправленные", variable=self.b_sent).grid(row=r, column=1, sticky="w")
        self.b_all = tk.BooleanVar(value=bool(self.cfg.get("all_projects", 1)))
        ttk.Checkbutton(f, text="Раскладывать по всем проектам", variable=self.b_all).grid(row=r + 1, column=0, columnspan=2, sticky="w")
        self.b_auto = tk.BooleanVar(value=bool(self.cfg.get("auto_check", 0)))
        ttk.Checkbutton(f, text="Автопроверка при запуске", variable=self.b_auto).grid(row=r + 2, column=0, columnspan=2, sticky="w")

        ttk.Label(f, text="Тип по умолчанию:").grid(row=r + 3, column=0, sticky="w", pady=4)
        self.c_type = ttk.Combobox(f, width=35, values=db.get_work_types())
        self.c_type.set(self.cfg.get("default_type") or "")
        self.c_type.grid(row=r + 3, column=1, sticky="w", padx=6)

        ttk.Label(f, foreground="gray", justify="left",
                  text="Mail.ru: Настройки аккаунта → Пароли для внешних приложений.\n"
                       "Обычный пароль от почты при включённой 2FA не подойдёт.\n"
                       "Письмо попадает в проект, если название проекта есть в теме\n"
                       "(в начале, середине или конце — регистр не важен).\n"
                       "Пароль хранится в базе и попадает в облачную синхронизацию."
                  ).grid(row=r + 4, column=0, columnspan=2, sticky="w", pady=(10, 4))

        bf = ttk.Frame(self, padding=(12, 0, 12, 12))
        bf.pack(fill="x")
        ttk.Button(bf, text="Сохранить", command=self.save).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Проверить соединение", command=self.test).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Закрыть", command=self.destroy).pack(side=tk.RIGHT, padx=4)
        self.lbl = ttk.Label(self, text="", foreground="#0066cc", padding=(12, 0, 12, 8))
        self.lbl.pack(fill="x")
        self.bind("<Escape>", lambda e: self.destroy())
        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _collect(self):
        d = {k: v.get().strip() for k, v in self.v.items()}
        for k in ("port", "limit_msgs", "interval_min"):
            try:
                d[k] = int(d[k] or 0)
            except ValueError:
                d[k] = 993 if k == "port" else 30
        d["use_ssl"] = 1 if self.b_ssl.get() else 0
        d["check_sent"] = 1 if self.b_sent.get() else 0
        d["all_projects"] = 1 if self.b_all.get() else 0
        d["auto_check"] = 1 if self.b_auto.get() else 0
        d["default_type"] = self.c_type.get().strip()
        return d

    def save(self):
        self.db.save_mail_settings(self._collect())
        self.cfg = self.db.get_mail_settings()
        self.lbl.config(foreground="#198754", text="✓ Настройки сохранены")

    def test(self):
        import threading
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
                msg = f"✓ Соединение OK. Папок: {len(folders)}. Отправленные: {sent or 'не найдены'}"
                self.after(0, lambda: self.lbl.config(foreground="#198754", text=msg))
            except Exception as e:
                m = f"{type(e).__name__}: {e}"
                self.after(0, lambda: self.lbl.config(foreground="#b02a37", text=m[:150]))
        threading.Thread(target=work, daemon=True).start()
