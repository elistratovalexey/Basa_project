# -*- coding: utf-8 -*-
"""Окно «Облако Mail.ru»: настройки WebDAV, статус, синхронизация, копии, диагностика.

Сеть — в фоновых потоках, живая БД — только в GUI-потоке. Журнал потокобезопасен.
"""
import os
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

from cloud_sync import (WebDavError, save_config, apply_ops,
                        make_snapshot, DEFAULT_URL)


class CloudSyncDialog(tk.Toplevel):
    # совместимость с разными именами виджетов (старая/новая разметка)
    _VAR_ALIASES = {
        "interval_min": ("interval_min_var", "interval_var"),
        "debounce_sec": ("debounce_sec_var", "debounce_var"),
        "keep_remote": ("keep_remote_var", "keep_var"),
        "timeout_sec": ("timeout_sec_var",),
        "retries": ("retries_var",),
        "backup_every_min": ("backup_every_min_var",),
    }

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.sm = app.sync_manager
        self.sm.log = self.say
        self.title("Облако Mail.ru — синхронизация базы")
        self.geometry("830x660")
        self.resizable(False, False)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        tab_cfg = ttk.Frame(nb, padding=10)
        tab_run = ttk.Frame(nb, padding=10)
        nb.add(tab_cfg, text="  Подключение  ")
        nb.add(tab_run, text="  Синхронизация  ")

        # ================= Подключение =================
        cfg = self.sm.cfg
        self.vars = {}
        rows = [
            ("url", "Адрес WebDAV:", cfg.get("url", DEFAULT_URL), 52, False),
            ("user", "Логин (почта):", cfg.get("user", ""), 40, False),
            ("password", "Пароль приложения:", cfg.get("password", ""), 40, True),
            ("remote_dir", "Папка в облаке:", cfg.get("remote_dir", "BasaProject"), 40, False),
        ]
        for i, (key, label, val, width, secret) in enumerate(rows):
            ttk.Label(tab_cfg, text=label).grid(row=i, column=0, sticky="w", pady=5)
            v = tk.StringVar(value=val)
            ttk.Entry(tab_cfg, textvariable=v, width=width,
                      show="•" if secret else "").grid(row=i, column=1, sticky="w", padx=6)
            self.vars[key] = v

        ttk.Label(tab_cfg, foreground="gray", justify="left",
                  text="Mail.ru: Настройки аккаунта → Пароли для внешних приложений.\n"
                       "При включённой 2FA обычный пароль от почты не подойдёт.\n"
                       "Пароль хранится в cloud_config.json (права 600) и НЕ попадает в git."
                  ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 4))

        self.auto_var = tk.BooleanVar(value=bool(cfg.get("auto", True)))
        ttk.Checkbutton(tab_cfg, text="Автосинхронизация",
                        variable=self.auto_var).grid(row=5, column=0, sticky="w", pady=4)
        f = ttk.Frame(tab_cfg)
        f.grid(row=5, column=1, sticky="w")
        ttk.Label(f, text="каждые").pack(side=tk.LEFT)
        self.interval_min_var = tk.StringVar(value=str(cfg.get("interval_min", 15)))
        ttk.Entry(f, textvariable=self.interval_min_var, width=5).pack(side=tk.LEFT, padx=4)
        ttk.Label(f, text="мин · пауза после правки").pack(side=tk.LEFT)
        self.debounce_sec_var = tk.StringVar(value=str(cfg.get("debounce_sec", 120)))
        ttk.Entry(f, textvariable=self.debounce_sec_var, width=5).pack(side=tk.LEFT, padx=4)
        ttk.Label(f, text="с").pack(side=tk.LEFT)

        num_rows = [
            ("keep_remote", "Хранить копий в облаке:", cfg.get("keep_remote", 10), 6),
            ("timeout_sec", "Таймаут запроса, с:", cfg.get("timeout_sec", 300), 7),
            ("retries", "Повторов при сбое:", cfg.get("retries", 4), 8),
            ("backup_every_min", "Копия в облако каждые, мин (0 = каждый раз):",
             cfg.get("backup_every_min", 60), 9),
        ]
        for key, label, val, row in num_rows:
            ttk.Label(tab_cfg, text=label).grid(row=row, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=str(val))
            ttk.Entry(tab_cfg, textvariable=var, width=6).grid(row=row, column=1, sticky="w", padx=6)
            setattr(self, f"{key}_var", var)

        bf = ttk.Frame(tab_cfg)
        bf.grid(row=10, column=0, columnspan=2, pady=12, sticky="w")
        ttk.Button(bf, text="Сохранить", command=self.save_cfg).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Проверить связь", command=self.test_connection).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Полная диагностика", command=self.run_diagnostics).pack(side=tk.LEFT, padx=4)

        # ================= Синхронизация =================
        self.lbl_state = ttk.Label(tab_run, text="", justify="left", foreground="#0066cc")
        self.lbl_state.pack(anchor="w", pady=(0, 8))
        bar = ttk.Frame(tab_run)
        bar.pack(fill="x")
        ttk.Button(bar, text="Синхронизировать сейчас",
                   command=self.sync_now).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Только выгрузить",
                   command=lambda: self.sync_now(push_only=True)).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Копии в облаке",
                   command=self.show_backups).pack(side=tk.LEFT, padx=4)

        ttk.Label(tab_run, text="Журнал:").pack(anchor="w", pady=(10, 2))
        self.txt = tk.Text(tab_run, height=18, wrap=tk.WORD, state="disabled",
                           font=("Consolas", 9))
        self.txt.pack(fill="both", expand=True)

        self.refresh_state()
        self.update_idletasks()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        try:
            self.grab_set()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    def _on_close(self):
        try:
            self.sm.log = print
        except Exception:
            pass
        self.destroy()

    def say(self, msg):
        """Потокобезопасный вывод (можно вызывать из worker-потоков)."""
        def _put():
            try:
                if self.winfo_exists():
                    self.txt.config(state="normal")
                    self.txt.insert(tk.END, str(msg) + "\n")
                    self.txt.see(tk.END)
                    self.txt.config(state="disabled")
            except Exception:
                pass
        try:
            self.after(0, _put)
        except Exception:
            _put()
        print("[sync]", msg)

    def refresh_state(self):
        d = self.sm.state.data
        self.lbl_state.config(text=(
            f"Устройство: {d.get('device')} ({d.get('device_id')})\n"
            f"Последняя синхронизация: {d.get('last_sync') or 'ещё не выполнялась'}\n"
            f"Последняя ошибка: {d.get('last_error') or 'нет'}"))

    def _num_var(self, key, default):
        for name in self._VAR_ALIASES.get(key, (f"{key}_var",)):
            var = getattr(self, name, None)
            if var is not None:
                try:
                    return int(var.get())
                except (ValueError, tk.TclError):
                    return default
        return default

    def save_cfg(self):
        cfg = dict(self.sm.cfg)
        for k, v in self.vars.items():
            cfg[k] = v.get().strip()
        cfg["auto"] = self.auto_var.get()
        for key, default, minimum in (("interval_min", 15, 1), ("debounce_sec", 120, 10),
                                      ("keep_remote", 10, 1), ("timeout_sec", 300, 30),
                                      ("retries", 4, 1), ("backup_every_min", 60, 0)):
            cfg[key] = max(minimum, self._num_var(key, cfg.get(key, default)))
        save_config(self.sm.app_dir, cfg)
        self.sm.cfg = cfg
        self.say(f"Настройки сохранены: таймаут {cfg['timeout_sec']} с, "
                 f"повторов {cfg['retries']}, пауза после правки {cfg['debounce_sec']} с")
        if hasattr(self.app, "restart_sync_timer"):
            self.app.restart_sync_timer()

    # ------------------------------------------------------------------
    def test_connection(self):
        self.save_cfg()

        def work():
            t0 = time.time()
            try:
                c = self.sm.client()
                self.say(f"1/3 MKCOL {self.sm.remote_dir} …")
                c.ensure_dir(self.sm.remote_dir)
                self.say(f"2/3 PROPFIND (список файлов) … {time.time() - t0:.1f} с")
                items = c.list_dir(self.sm.remote_dir)
                self.say("3/3 HEAD projects.db.gz …")
                meta = c.head(self.sm.rpath("projects.db.gz"))
                size = f"{meta['size'] / 1048576:.1f} МБ" if meta else "ещё не выгружен"
                self.say(f"Связь OK за {time.time() - t0:.1f} с. "
                         f"Файлов в папке: {len(items)}; projects.db.gz: {size}")
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                self.say(f"Ошибка связи ({time.time() - t0:.1f} с): {msg}")
        threading.Thread(target=work, daemon=True).start()

    def run_diagnostics(self):
        """Полный цикл PUT → GET → DELETE тестового файла с замером времени."""
        self.save_cfg()

        def work():
            t0 = time.time()
            try:
                c = self.sm.client()
                c.ensure_dir(self.sm.remote_dir)
                self.say(f"[diag] папка доступна ({time.time() - t0:.1f} с)")

                tmp = os.path.join(tempfile.gettempdir(), "basa_dav_test.txt")
                with open(tmp, "w", encoding="utf-8") as fh:
                    fh.write("test " + time.strftime("%d.%m.%Y %H:%M:%S"))

                t1 = time.time()
                c.put(self.sm.rpath("_dav_test.txt"), tmp)
                self.say(f"[diag] PUT тестового файла: {time.time() - t1:.1f} с")

                t1 = time.time()
                dst = tmp + ".down"
                c.get(self.sm.rpath("_dav_test.txt"), dst)
                ok = False
                try:
                    with open(dst, encoding="utf-8") as fh:
                        ok = fh.read().startswith("test")
                except OSError:
                    ok = False
                self.say(f"[diag] GET тестового файла: {time.time() - t1:.1f} с, "
                         f"содержимое совпало: {ok}")

                c.delete(self.sm.rpath("_dav_test.txt"))
                self.say(f"[diag] DELETE выполнен. Итого {time.time() - t0:.1f} с — "
                         f"WebDAV полностью рабочий")
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                self.say(f"[diag] ошибка ({time.time() - t0:.1f} с): {msg}")
                self.say("[diag] подсказка: «таймаут» → увеличьте таймаут/повторы; "
                         "401/403 → пароль приложения; «сеть недоступна» → прокси/фаервол/DNS")
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------
    def sync_now(self, push_only=False):
        if self.sm.busy:
            messagebox.showinfo("Облако", "Синхронизация уже выполняется.")
            return
        self.sm.busy = True
        self.say("— Старт синхронизации —")
        try:
            local_hash = self.sm.prepare()
        except Exception as e:
            self.sm.busy = False
            self.say(f"Не удалось сделать снимок: {type(e).__name__}: {e}")
            return

        def work():
            try:
                res = self.sm.worker(local_hash)
                if push_only:
                    res["ops"] = []
                    res["conflicts"] = []
                self.after(0, lambda: self._apply(res))
            except WebDavError as e:
                msg = str(e)                      # фиксируем СРАЗУ (замыкание на e недопустимо)
                self.after(0, lambda m=msg: self._fail(m))
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                self.after(0, lambda m=msg: self._fail(m))
        threading.Thread(target=work, daemon=True).start()

    def _apply(self, res):
        """GUI-поток: применяем чужие правки, затем публикуем снимок."""
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
                    for cf in conflicts[:10]:
                        self.say(f"  · {cf['table']} {cf['key']}")
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
                        msg = f"{type(e).__name__}: {e}"
                        self.after(0, lambda m=msg: self._fail(m))
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
        low = err.lower()
        if "таймаут" in low or "timeout" in low:
            self.say("Подсказка: увеличьте «Таймаут запроса, с» до 300–600 и "
                     "«Повторов при сбое» до 4, затем запустите «Полную диагностику» — "
                     "она покажет, на каком шаге (PUT/GET/PROPFIND) обрывается связь.")
        elif "401" in err or "403" in err or "доступ запрещён" in low:
            self.say("Подсказка: проверьте логин и пароль приложения Mail.ru "
                     "(Настройки аккаунта → Пароли для внешних приложений).")
        self.refresh_state()

    def show_backups(self):
        def work():
            try:
                items = self.sm.client().list_dir(self.sm.rpath("backups"))
                items.sort(key=lambda fi: fi["name"], reverse=True)
                lines = [f"{fi['name']}  ·  {fi['size'] // 1024} КБ" for fi in items]
                self.say("Копии в облаке:\n" + "\n".join(lines or ["пусто"]))
            except Exception as e:
                self.say(f"Ошибка списка копий: {type(e).__name__}: {e}")
        threading.Thread(target=work, daemon=True).start()