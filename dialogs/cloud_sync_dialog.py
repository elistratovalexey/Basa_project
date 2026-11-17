# -*- coding: utf-8 -*-
"""Окно «Облако Mail.ru»: настройки WebDAV, статус, синхронизация, копии."""
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from cloud_sync import (SyncManager, WebDavError, load_config, save_config,
                        apply_ops, make_snapshot, DEFAULT_URL)


class CloudSyncDialog(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.sm = app.sync_manager
        self.title("Облако Mail.ru — синхронизация базы")
        self.geometry("760x560")
        self.resizable(False, False)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        tab_cfg = ttk.Frame(nb, padding=10)
        tab_run = ttk.Frame(nb, padding=10)
        nb.add(tab_cfg, text="Подключение")
        nb.add(tab_run, text="Синхронизация")

        # ---------- вкладка подключения ----------
        cfg = self.sm.cfg
        self.vars = {}
        rows = [("url", "Адрес WebDAV:", cfg.get("url", DEFAULT_URL), 52, False),
                ("user", "Логин (почта):", cfg.get("user", ""), 40, False),
                ("password", "Пароль приложения:", cfg.get("password", ""), 40, True),
                ("remote_dir", "Папка в облаке:", cfg.get("remote_dir", "BasaProject"), 40, False)]
        for i, (key, label, val, width, secret) in enumerate(rows):
            ttk.Label(tab_cfg, text=label).grid(row=i, column=0, sticky="w", pady=5)
            v = tk.StringVar(value=val)
            ttk.Entry(tab_cfg, textvariable=v, width=width,
                      show="•" if secret else "").grid(row=i, column=1, sticky="w", padx=6)
            self.vars[key] = v

        ttk.Label(tab_cfg, foreground="gray", justify="left",
                  text="Mail.ru: Настройки аккаунта → Пароли для внешних приложений.\n"
                       "Обычный пароль от почты не подойдёт при включённой 2FA.\n"
                       "Пароль хранится в cloud_config.json (права 600) и НЕ попадает в git."
                  ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 4))

        self.auto_var = tk.BooleanVar(value=bool(cfg.get("auto", True)))
        ttk.Checkbutton(tab_cfg, text="Автосинхронизация", variable=self.auto_var)\
            .grid(row=5, column=0, sticky="w", pady=4)
        f = ttk.Frame(tab_cfg); f.grid(row=5, column=1, sticky="w")
        ttk.Label(f, text="каждые").pack(side=tk.LEFT)
        self.interval_var = tk.StringVar(value=str(cfg.get("interval_min", 15)))
        ttk.Entry(f, textvariable=self.interval_var, width=5).pack(side=tk.LEFT, padx=4)
        ttk.Label(f, text="мин · задержка после правки").pack(side=tk.LEFT)
        self.debounce_var = tk.StringVar(value=str(cfg.get("debounce_sec", 45)))
        ttk.Entry(f, textvariable=self.debounce_var, width=5).pack(side=tk.LEFT, padx=4)
        ttk.Label(f, text="с").pack(side=tk.LEFT)

        ttk.Label(tab_cfg, text="Хранить копий в облаке:").grid(row=6, column=0, sticky="w", pady=4)
        self.keep_var = tk.StringVar(value=str(cfg.get("keep_remote", 10)))
        ttk.Entry(tab_cfg, textvariable=self.keep_var, width=5).grid(row=6, column=1, sticky="w", padx=6)

        bf = ttk.Frame(tab_cfg); bf.grid(row=7, column=0, columnspan=2, pady=12, sticky="w")
        ttk.Button(bf, text="Сохранить", command=self.save_cfg).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Проверить связь", command=self.test_connection).pack(side=tk.LEFT, padx=4)

        # ---------- вкладка синхронизации ----------
        self.lbl_state = ttk.Label(tab_run, text="", justify="left", foreground="#0066cc")
        self.lbl_state.pack(anchor="w", pady=(0, 8))
        bar = ttk.Frame(tab_run); bar.pack(fill="x")
        ttk.Button(bar, text="Синхронизировать сейчас", command=self.sync_now).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Только выгрузить", command=lambda: self.sync_now(push_only=True)).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Копии в облаке", command=self.show_backups).pack(side=tk.LEFT, padx=4)

        ttk.Label(tab_run, text="Журнал:").pack(anchor="w", pady=(10, 2))
        self.txt = tk.Text(tab_run, height=16, wrap=tk.WORD, state="disabled")
        self.txt.pack(fill="both", expand=True)

        self.refresh_state()
        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    # ---------- утилиты ----------
    def say(self, msg):
        self.txt.config(state="normal")
        self.txt.insert(tk.END, msg + "\n")
        self.txt.see(tk.END)
        self.txt.config(state="disabled")
        print("[sync]", msg)

    def refresh_state(self):
        d = self.sm.state.data
        self.lbl_state.config(text=(
            f"Устройство: {d.get('device')} ({d.get('device_id')})\n"
            f"Последняя синхронизация: {d.get('last_sync') or 'ещё не выполнялась'}\n"
            f"Последняя ошибка: {d.get('last_error') or 'нет'}"))

    def save_cfg(self):
        cfg = dict(self.sm.cfg)
        for k, v in self.vars.items():
            cfg[k] = v.get().strip()
        cfg["auto"] = self.auto_var.get()
        for k, var, default in (("interval_min", self.interval_var, 15),
                                ("debounce_sec", self.debounce_var, 45),
                                ("keep_remote", self.keep_var, 10)):
            try:
                cfg[k] = max(1, int(var.get()))
            except ValueError:
                cfg[k] = default
        save_config(self.sm.app_dir, cfg)
        self.sm.cfg = cfg
        self.say("Настройки сохранены.")
        if hasattr(self.app, "restart_sync_timer"):
            self.app.restart_sync_timer()

    def test_connection(self):
        self.save_cfg()

        def work():
            try:
                c = self.sm.client()
                c.ensure_dir(self.sm.remote_dir)
                items = c.list_dir(self.sm.remote_dir)
                self.after(0, lambda: self.say(f"Связь OK. Файлов в папке: {len(items)}"))
            except Exception as e:
                self.after(0, lambda e=e: self.say(f"Ошибка связи: {e}")) 
        threading.Thread(target=work, daemon=True).start()

    # ---------- синхронизация ----------
    def sync_now(self, push_only=False):
        if self.sm.busy:
            messagebox.showinfo("Облако", "Синхронизация уже выполняется.")
            return
        self.sm.busy = True
        self.say("— Старт синхронизации —")
        try:
            local_hash = self.sm.prepare()          # GUI-поток: снимок живой БД
        except Exception as e:
            self.sm.busy = False
            self.say(f"Не удалось сделать снимок: {e}")
            return

        def work():
            try:
                res = self.sm.worker(local_hash)
                if push_only:
                    res["ops"] = []
                self.after(0, lambda: self._apply(res))
            except WebDavError as e:
                self.after(0, lambda e=e: self._fail(str(e)))  
            except Exception as e:
                self.after(0, lambda e=e: self._fail(f"{type(e).__name__}: {e}"))
        threading.Thread(target=work, daemon=True).start()

    def _apply(self, res):
        """GUI-поток: применяем чужие правки к живой БД, затем публикуем снимок."""
        try:
            if res.get("message"):
                self.say(res["message"])
            ops, conflicts = res.get("ops", []), res.get("conflicts", [])
            if ops:
                backup = self.sm.safety_backup()
                self.say(f"Аварийная копия: {os.path.basename(backup)}")
                n = apply_ops(self.sm.conn, ops)
                self.say(f"Применено изменений из облака: {n}")
                self.sm.log_sync("merge", f"ops={n}, conflicts={len(conflicts)}")
                if conflicts:
                    self.say(f"Спорных строк: {len(conflicts)} — выбран более свежий вариант:")
                    for c in conflicts[:10]:
                        self.say(f"  · {c['table']} {c['key']}")
                if hasattr(self.app, "reload_after_sync"):
                    self.app.reload_after_sync()
            if res.get("push"):
                make_snapshot(self.sm.conn, self.sm.snap_local)
                snap = self.sm.snap_local

                def publish():
                    try:
                        stamp = self.sm.publish(snap)
                        self.after(0, lambda: self._done(stamp))
                    except Exception as e:
                        self.after(0, lambda e=e: self._fail(str(e)))  
                threading.Thread(target=publish, daemon=True).start()
            else:
                self._done(None)
        except Exception as e:
            self._fail(f"{type(e).__name__}: {e}")

    def _done(self, stamp):
        self.sm.busy = False
        if stamp:
            self.say(f"Выгружено в облако. Копия: projects_{stamp}.db.gz")
        self.say("— Готово —")
        self.sm.log_sync("sync", stamp or "no-push")
        self.refresh_state()
        if hasattr(self.app, "update_sync_label"):
            self.app.update_sync_label()

    def _fail(self, err):
        self.sm.busy = False
        self.sm.state.data["last_error"] = err
        self.sm.state.save()
        self.say(f"ОШИБКА: {err}")
        self.refresh_state()

    def show_backups(self):
        def work():
            try:
                items = self.sm.client().list_dir(self.sm.rpath("backups"))
                items.sort(key=lambda f: f["name"], reverse=True)
                lines = [f"{i['name']}  ·  {i['size'] // 1024} КБ" for i in items]
                self.after(0, lambda: self.say("Копии в облаке:\n" + "\n".join(lines or ["пусто"])))
            except Exception as e:
                self.after(0, lambda: self.say(f"Ошибка списка: {e}"))
        threading.Thread(target=work, daemon=True).start()