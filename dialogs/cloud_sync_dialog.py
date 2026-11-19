# -*- coding: utf-8 -*-
"""Окно «Облако Mail.ru»: настройки WebDAV, статус, синхронизация, копии, диагностика.

Потоковая модель: сеть — в фоновых потоках, живая БД изменяется только в GUI-потоке
(через self.after(0, ...)). Журнал потокобезопасен: логи WebDAV-клиента идут сюда же.
Учётные данные (логин/пароль/папка) — единые для синхронизации БД и обновления программы.
"""
import os
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

from cloud_sync import (WebDavError, save_config, load_config, apply_ops,
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
        self.sm = getattr(app, "sync_manager", None)
        if self.sm is None:
            messagebox.showerror("Облако", "Менеджер синхронизации не инициализирован.\n"
                                           "Проверьте наличие cloud_sync.py.", parent=parent)
            self.after(10, self.destroy)
            return
        self.sm.log = self.say            # логи WebDAV-клиента — в журнал окна

        self.title("Облако Mail.ru — синхронизация базы")
        self.geometry("840x680")
        self.resizable(False, False)
        try:
            from dialogs.window_geometry import restore_geometry, track_geometry
            restore_geometry(self, "cloud_sync_dialog", "840x680")
            track_geometry(self, "cloud_sync_dialog")
        except Exception:
            pass
        self.transient(parent)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        tab_cfg = ttk.Frame(nb, padding=10)
        tab_run = ttk.Frame(nb, padding=10)
        nb.add(tab_cfg, text="  Подключение  ")
        nb.add(tab_run, text="  Синхронизация  ")
        tab_pub = ttk.Frame(nb, padding=10)
        nb.add(tab_pub, text="  Публикация версии  ")

        # ================= Вкладка «Подключение» =================
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
                       "Эти же данные использует обновление программы (⬆ Обновление).\n"
                       "Пароль хранится в cloud_config.json (права 600) и НЕ попадает в git."
                  ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 2))

        self.lbl_source = ttk.Label(tab_cfg, foreground="#0066cc", justify="left", text="")
        self.lbl_source.grid(row=5, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self.auto_var = tk.BooleanVar(value=bool(cfg.get("auto", True)))
        ttk.Checkbutton(tab_cfg, text="Автосинхронизация",
                        variable=self.auto_var).grid(row=6, column=0, sticky="w", pady=4)
        f = ttk.Frame(tab_cfg)
        f.grid(row=6, column=1, sticky="w")
        ttk.Label(f, text="каждые").pack(side=tk.LEFT)
        self.interval_min_var = tk.StringVar(value=str(cfg.get("interval_min", 15)))
        ttk.Entry(f, textvariable=self.interval_min_var, width=5).pack(side=tk.LEFT, padx=4)
        ttk.Label(f, text="мин · пауза после правки").pack(side=tk.LEFT)
        self.debounce_sec_var = tk.StringVar(value=str(cfg.get("debounce_sec", 120)))
        ttk.Entry(f, textvariable=self.debounce_sec_var, width=5).pack(side=tk.LEFT, padx=4)
        ttk.Label(f, text="с").pack(side=tk.LEFT)

        num_rows = [
            ("keep_remote", "Хранить копий в облаке:", cfg.get("keep_remote", 10), 7),
            ("timeout_sec", "Таймаут запроса, с:", cfg.get("timeout_sec", 300), 8),
            ("retries", "Повторов при сбое:", cfg.get("retries", 4), 9),
            ("backup_every_min", "Копия в облако каждые, мин (0 = каждый раз):",
             cfg.get("backup_every_min", 60), 10),
        ]
        for key, label, val, row in num_rows:
            ttk.Label(tab_cfg, text=label).grid(row=row, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=str(val))
            ttk.Entry(tab_cfg, textvariable=var, width=6).grid(row=row, column=1, sticky="w", padx=6)
            setattr(self, f"{key}_var", var)

        bf = ttk.Frame(tab_cfg)
        bf.grid(row=11, column=0, columnspan=2, pady=12, sticky="w")
        ttk.Button(bf, text="Сохранить", command=self.save_cfg).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Проверить связь", command=self.test_connection).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Полная диагностика", command=self.run_diagnostics).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Открыть папку настроек",
                   command=self.open_config_dir).pack(side=tk.LEFT, padx=4)

        # ================= Вкладка «Синхронизация» =================
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
        ttk.Button(bar, text="Очистить журнал",
                   command=self._clear_log).pack(side=tk.RIGHT, padx=4)

        ttk.Label(tab_run, text="Журнал:").pack(anchor="w", pady=(10, 2))
        self.txt = tk.Text(tab_run, height=18, wrap=tk.WORD, state="disabled",
                           font=("Consolas", 9))
        self.txt.pack(fill="both", expand=True)
        self._build_publish_tab(tab_pub)

        self._show_source()
        self.refresh_state()
        self.update_idletasks()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda e: self._on_close())
        self._safe_grab()

    # ------------------------------------------------------------------
    # Служебное
    # ------------------------------------------------------------------
    def _safe_grab(self, attempts=10):
        try:
            if self.winfo_exists() and self.winfo_viewable():
                self.grab_set()
            elif attempts > 0:
                self.after(60, lambda a=attempts - 1: self._safe_grab(a))
        except tk.TclError:
            if attempts > 0:
                self.after(60, lambda a=attempts - 1: self._safe_grab(a))

    def _on_close(self):
        try:
            self.sm.log = print
        except Exception:
            pass
        self.destroy()

    def say(self, msg):
        """Потокобезопасный вывод в журнал (можно вызывать из worker-потоков)."""
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

    def _clear_log(self):
        try:
            self.txt.config(state="normal")
            self.txt.delete("1.0", tk.END)
            self.txt.config(state="disabled")
        except Exception:
            pass

    def _show_source(self):
        cfg = self.sm.cfg or {}
        self.lbl_source.config(
            text=f"Источник учётных данных: {cfg.get('_source', '—')}\n"
                 f"Файл настроек: {cfg.get('_config_file', '—')}")

    def open_config_dir(self):
        path = (self.sm.cfg or {}).get("_config_file") or ""
        folder = os.path.dirname(path) if path else None
        if not folder or not os.path.isdir(folder):
            messagebox.showinfo("Папка", "Папка настроек не найдена.", parent=self)
            return
        try:
            from utils import open_path
            open_path(folder)
        except Exception as e:
            messagebox.showinfo("Папка", f"{folder}\n\n{e}", parent=self)

    def refresh_state(self):
        d = self.sm.state.data
        self.lbl_state.config(text=(
            f"Устройство: {d.get('device')} ({d.get('device_id')})\n"
            f"Последняя синхронизация: {d.get('last_sync') or 'ещё не выполнялась'}\n"
            f"Последняя ошибка: {d.get('last_error') or 'нет'}"))

    def _num_var(self, key, default):
        """Значение из виджета с любым из возможных имён; иначе default."""
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
        try:
            path = save_config(self.sm.app_dir, cfg)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить настройки:\n{e}", parent=self)
            return
        self.sm.cfg = load_config()          # перечитать с учётом переменных окружения
        self._show_source()
        self.say(f"Настройки сохранены: {path}")
        self.say(f"Таймаут {cfg['timeout_sec']} с, повторов {cfg['retries']}, "
                 f"пауза после правки {cfg['debounce_sec']} с, "
                 f"копия в облако каждые {cfg['backup_every_min']} мин")
        if hasattr(self.app, "restart_sync_timer"):
            try:
                self.app.restart_sync_timer()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Проверки связи
    # ------------------------------------------------------------------
    def test_connection(self):
        self.save_cfg()

        def work():
            t0 = time.time()
            try:
                cfg = self.sm.cfg
                self.say(f"Логин: {cfg.get('user') or '—'} · источник: {cfg.get('_source')}")
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
                msg = f"{type(e).__name__}: {e}"      # фиксируем СРАЗУ (замыкание на e недопустимо)
                dt = time.time() - t0
                self.say(f"Ошибка связи ({dt:.1f} с): {msg}")
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

                t1 = time.time()
                c.delete(self.sm.rpath("_dav_test.txt"))
                self.say(f"[diag] DELETE: {time.time() - t1:.1f} с")
                self.say(f"[diag] Итого {time.time() - t0:.1f} с — WebDAV полностью рабочий")
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                self.say(f"[diag] ошибка ({time.time() - t0:.1f} с): {msg}")
                self.say("[diag] подсказка: «таймаут» → увеличьте таймаут/повторы; "
                         "401/403 → пароль приложения; «сеть недоступна» → прокси/фаервол/DNS")
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------
    # Синхронизация
    # ------------------------------------------------------------------
    def sync_now(self, push_only=False):
        if self.sm.busy:
            messagebox.showinfo("Облако", "Синхронизация уже выполняется.", parent=self)
            return
        self.sm.busy = True
        self.say("— Старт синхронизации —")
        try:
            local_hash = self.sm.prepare()          # GUI-поток: снимок живой БД
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
                msg = str(e)
                self.after(0, lambda m=msg: self._fail(m))
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                self.after(0, lambda m=msg: self._fail(m))
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
        try:
            self.sm.log_sync("sync", stamp or "no-push")
        except Exception:
            pass
        self.refresh_state()
        if hasattr(self.app, "update_sync_label"):
            try:
                self.app.update_sync_label()
            except Exception:
                pass

    def _fail(self, err):
        self.sm.busy = False
        try:
            self.sm.state.data["last_error"] = err
            self.sm.state.save()
        except Exception:
            pass
        self.say(f"ОШИБКА: {err}")
        low = str(err).lower()
        if "таймаут" in low or "timeout" in low:
            self.say("Подсказка: увеличьте «Таймаут запроса, с» до 300–600 и "
                     "«Повторов при сбое» до 4, затем запустите «Полную диагностику» — "
                     "она покажет, на каком шаге (PUT/GET/PROPFIND) обрывается связь.")
        elif "401" in low or "403" in low or "доступ запрещён" in low:
            self.say("Подсказка: проверьте логин и пароль приложения Mail.ru "
                     "(Настройки аккаунта → Пароли для внешних приложений).")
        elif "не заданы логин" in low:
            self.say("Подсказка: заполните поля на вкладке «Подключение» и нажмите «Сохранить».")
        self.refresh_state()
        if hasattr(self.app, "update_sync_label"):
            try:
                self.app.update_sync_label()
            except Exception:
                pass
    # ==================================================================
    # Вкладка «Публикация версии»
    # ==================================================================
    def _build_publish_tab(self, tab):
        ttk.Label(tab, text="Публикация обновления программы в облако",
                  font=("Arial", 10, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        ttk.Label(tab, text="Что публикуем:").grid(row=1, column=0, sticky="w", pady=4)
        self.pub_kind = tk.StringVar(value="win")
        kf = ttk.Frame(tab)
        kf.grid(row=1, column=1, columnspan=2, sticky="w")
        ttk.Radiobutton(kf, text="Windows-exe (dist\\BasaProject)", value="win",
                        variable=self.pub_kind, command=self._pub_autodetect).pack(side=tk.LEFT)
        ttk.Radiobutton(kf, text="Исходники (.py)", value="src",
                        variable=self.pub_kind, command=self._pub_autodetect).pack(side=tk.LEFT, padx=12)

        ttk.Label(tab, text="Папка сборки:").grid(row=2, column=0, sticky="w", pady=4)
        self.pub_dir = tk.StringVar()
        ttk.Entry(tab, textvariable=self.pub_dir, width=52).grid(row=2, column=1, sticky="w", padx=6)
        ttk.Button(tab, text="Обзор…", command=self._pub_browse).grid(row=2, column=2, sticky="w")

        ttk.Label(tab, text="Версия:").grid(row=3, column=0, sticky="w", pady=4)
        self.pub_version = tk.StringVar()
        vf = ttk.Frame(tab)
        vf.grid(row=3, column=1, columnspan=2, sticky="w", padx=6)
        ttk.Entry(vf, textvariable=self.pub_version, width=14).pack(side=tk.LEFT)
        self.lbl_pub_found = ttk.Label(vf, text="", foreground="gray")
        self.lbl_pub_found.pack(side=tk.LEFT, padx=8)

        ttk.Label(tab, text="Что нового:").grid(row=4, column=0, sticky="nw", pady=4)
        self.pub_notes = tk.Text(tab, width=52, height=5, wrap=tk.WORD)
        self.pub_notes.grid(row=4, column=1, columnspan=2, sticky="w", padx=6)

        ttk.Label(tab, foreground="gray", justify="left",
                  text="Версия берётся из version.json внутри сборки. Она должна быть БОЛЬШЕ\n"
                       "установленной у пользователей и совпадать с версией внутри exe —\n"
                       "иначе обновление будет предлагаться по кругу.\n"
                       "Данные (база, настройки) обновление не затрагивает."
                  ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 4))

        bf = ttk.Frame(tab)
        bf.grid(row=6, column=0, columnspan=3, sticky="w", pady=8)
        self.btn_publish = ttk.Button(bf, text="Опубликовать", command=self._pub_run)
        self.btn_publish.pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Что уже в облаке", command=self._pub_show).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Открыть окно обновления",
                   command=self._pub_open_update).pack(side=tk.LEFT, padx=4)

        self._pub_autodetect()

    def _updater(self):
        from app_update import AppUpdater
        up = AppUpdater(log=self.say)
        up.cfg = dict(self.sm.cfg)          # те же учётные данные, что у синхронизации
        return up

    def _pub_default_dir(self, kind):
        try:
            from paths import INSTALL_DIR
        except Exception:
            INSTALL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if kind == "win":
            for cand in (os.path.join(INSTALL_DIR, "dist", "BasaProject"),
                         os.path.join(os.getcwd(), "dist", "BasaProject")):
                if os.path.exists(os.path.join(cand, "BasaProject.exe")):
                    return cand
            return os.path.join(INSTALL_DIR, "dist", "BasaProject")
        return INSTALL_DIR

    def _pub_autodetect(self):
        kind = self.pub_kind.get()
        if not self.pub_dir.get() or not os.path.isdir(self.pub_dir.get()):
            self.pub_dir.set(self._pub_default_dir(kind))
        try:
            found = self._updater().detect_version(self.pub_dir.get(), kind)
        except Exception:
            found = ""
        if found:
            self.pub_version.set(found)
            self.lbl_pub_found.config(text=f"найдена в сборке: {found}")
        else:
            self.lbl_pub_found.config(text="версия не найдена — укажите вручную")

    def _pub_browse(self):
        d = filedialog.askdirectory(title="Папка сборки", parent=self,
                                    initialdir=self.pub_dir.get() or None)
        if d:
            self.pub_dir.set(os.path.normpath(d))
            self._pub_autodetect()

    def _pub_run(self):
        if getattr(self, "_pub_busy", False):
            messagebox.showinfo("Публикация", "Публикация уже выполняется.", parent=self)
            return
        folder = self.pub_dir.get().strip()
        kind = self.pub_kind.get()
        version = self.pub_version.get().strip()
        notes = self.pub_notes.get("1.0", tk.END).strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("Внимание", "Укажите существующую папку сборки.", parent=self)
            return
        if not version:
            messagebox.showwarning("Внимание", "Укажите версию (например 1.9.97).", parent=self)
            return
        if not messagebox.askyesno(
                "Подтверждение",
                f"Опубликовать {version} ({'Windows-exe' if kind == 'win' else 'исходники'})?\n\n"
                f"Папка: {folder}\n"
                "После этого пользователи увидят обновление в «⬆ Обновление».", parent=self):
            return
        self._pub_busy = True
        self.btn_publish.config(state="disabled")
        self.say(f"— Публикация {version} ({kind}) —")

        def work():
            try:
                man = self._updater().publish(folder, kind, version, notes)
                self.after(0, lambda: self._pub_done(man))
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                self.after(0, lambda m=msg: self._pub_fail(m))
        threading.Thread(target=work, daemon=True).start()

    def _pub_done(self, man):
        self._pub_busy = False
        self.btn_publish.config(state="normal")
        arts = ", ".join((man.get("artifacts") or {}).keys())
        self.say(f"— Готово: {man.get('version')} [{arts}] —")
        messagebox.showinfo("Публикация",
                            f"Версия {man.get('version')} опубликована.\n"
                            f"Артефакты: {arts}\n\n"
                            "Проверьте: «⬆ Обновление» → «Проверить обновление».", parent=self)

    def _pub_fail(self, err):
        self._pub_busy = False
        self.btn_publish.config(state="normal")
        self.say(f"ОШИБКА публикации: {err}")
        messagebox.showerror("Публикация", err, parent=self)

    def _pub_show(self):
        def work():
            try:
                info = self._updater().published_info()
                man = info.get("manifest") or {}
                self.say("В облаке update/: " +
                         (", ".join(f["name"] for f in info["files"]) or "пусто"))
                if man:
                    self.say(f"Манифест: версия {man.get('version')} от {man.get('date')}")
                    for k, v in (man.get("artifacts") or {}).items():
                        self.say(f"  {k}: {v.get('file')} · {int(v.get('size', 0)) / 1048576:.1f} МБ")
                    self.say(f"  Что нового: {man.get('notes') or '—'}")
                else:
                    self.say("Манифест version.json отсутствует — обновлений ещё не публиковали.")
            except Exception as e:
                self.say(f"Ошибка чтения update/: {type(e).__name__}: {e}")
        threading.Thread(target=work, daemon=True).start()

    def _pub_open_update(self):
        if hasattr(self.app, "open_update_dialog"):
            try:
                self.app.open_update_dialog()
            except Exception as e:
                messagebox.showerror("Обновление", str(e), parent=self)
        else:
            messagebox.showinfo("Обновление", "Кнопка «⬆ Обновление» не найдена в приложении.",
                                parent=self)
            
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