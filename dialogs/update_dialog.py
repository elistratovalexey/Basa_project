# -*- coding: utf-8 -*-
"""Окно «Обновление программы»: проверка, скачивание, установка, откат."""
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from app_update import AppUpdater, current_version, artifact_kind


class UpdateDialog(tk.Toplevel):
    def __init__(self, parent, app=None):
        super().__init__(parent)
        self.app = app
        self.up = AppUpdater(log=self.say)
        self.info = None
        self.busy = False
        self.need_restart = False

        self.title("Обновление программы")
        self.geometry("760x560")
        self.resizable(False, False)
        self.transient(parent)

        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        self.lbl_ver = ttk.Label(top, font=("Arial", 10, "bold"),
                                 text=f"Установлена версия: {current_version()}   "
                                      f"тип: {'Windows exe' if artifact_kind() == 'win' else 'исходники'}")
        self.lbl_ver.pack(side=tk.LEFT)
        ttk.Button(top, text="Проверить обновление", command=self.check).pack(side=tk.RIGHT)

        self.lbl_new = ttk.Label(self, padding=(10, 0), foreground="#0066cc", text="")
        self.lbl_new.pack(fill="x")

        nf = ttk.LabelFrame(self, text="Что нового", padding=6)
        nf.pack(fill="both", expand=True, padx=10, pady=6)
        self.txt_notes = tk.Text(nf, height=6, wrap=tk.WORD, state="disabled")
        self.txt_notes.pack(fill="both", expand=True)

        bf = ttk.Frame(self, padding=(10, 0))
        bf.pack(fill="x")
        self.btn_install = ttk.Button(bf, text="Скачать и установить",
                                      command=self.download_and_install, state="disabled")
        self.btn_install.pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Откатиться на скачанную версию",
                   command=self.rollback).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Закрыть", command=self._close).pack(side=tk.RIGHT, padx=4)

        lf = ttk.LabelFrame(self, text="Журнал", padding=6)
        lf.pack(fill="both", expand=True, padx=10, pady=8)
        self.txt = tk.Text(lf, height=10, wrap=tk.WORD, state="disabled", font=("Consolas", 9))
        self.txt.pack(fill="both", expand=True)

        self.bind("<Escape>", lambda e: self._close())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(200, self.check)
        try:
            self.grab_set()
        except tk.TclError:
            pass

    # ---------- утилиты ----------
    def say(self, msg):
        def put():
            try:
                if self.winfo_exists():
                    self.txt.config(state="normal")
                    self.txt.insert(tk.END, str(msg) + "\n")
                    self.txt.see(tk.END)
                    self.txt.config(state="disabled")
            except Exception:
                pass
        try:
            self.after(0, put)
        except Exception:
            put()
        print("[update]", msg)

    def _notes(self, text):
        self.txt_notes.config(state="normal")
        self.txt_notes.delete("1.0", tk.END)
        self.txt_notes.insert("1.0", text or "—")
        self.txt_notes.config(state="disabled")

    def _close(self):
        if self.need_restart and self.app is not None:
            if messagebox.askyesno("Перезапуск", "Закрыть программу сейчас, чтобы обновление применилось?",
                                   parent=self):
                self.destroy()
                try:
                    self.app.on_close()
                except Exception:
                    pass
                return
        self.destroy()

    # ---------- проверка ----------
    def check(self):
        if self.busy:
            return
        self.busy = True
        self.btn_install.config(state="disabled")
        self.say("Проверяю update/version.json в облаке…")

        def work():
            try:
                info = self.up.check()
                self.after(0, lambda: self._show(info))
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                self.after(0, lambda m=msg: self._fail(m))
        threading.Thread(target=work, daemon=True).start()

    def _show(self, info):
        self.busy = False
        self.info = info
        if info.get("error"):
            self.lbl_new.config(text=info["error"], foreground="red")
            self.say(info["error"])
            return
        self._notes(info.get("notes"))
        if info.get("available"):
            self.lbl_new.config(
                text=f"Доступна версия {info['version']} от {info['date']} "
                     f"({info['size'] / 1048576:.1f} МБ)", foreground="#0a0")
            self.btn_install.config(state="normal")
            self.say(f"Доступна {info['version']} (текущая {info['current']})")
        else:
            self.lbl_new.config(text=f"Установлена последняя версия ({info['current']})",
                                foreground="#0066cc")
            self.say("Обновлений нет")

    def _fail(self, err):
        self.busy = False
        self.say(f"ОШИБКА: {err}")
        self.lbl_new.config(text="Ошибка проверки обновлений", foreground="red")
        messagebox.showerror("Обновление", err, parent=self)

    # ---------- скачивание + установка ----------
    def download_and_install(self):
        if not self.info or not self.info.get("available") or self.busy:
            return
        if not messagebox.askyesno(
                "Подтверждение",
                f"Обновить программу до {self.info['version']}?\n\n"
                "Данные (база, настройки, журнал) не затрагиваются.\n"
                "Программа будет перезапущена.", parent=self):
            return
        self.busy = True
        self.btn_install.config(state="disabled")
        info = self.info

        def work():
            try:
                archive = self.up.download(info)
                mode, msg = self.up.install(archive, info)
                self.after(0, lambda: self._installed(mode, msg))
            except Exception as e:
                m = f"{type(e).__name__}: {e}"
                self.after(0, lambda x=m: self._fail(x))
        threading.Thread(target=work, daemon=True).start()

    def _installed(self, mode, msg):
        self.busy = False
        self.say(msg)
        if mode == "restart":
            self.need_restart = True
            messagebox.showinfo("Обновление", msg + "\n\nНажмите OK — программа закроется.", parent=self)
            self.destroy()
            if self.app is not None:
                try:
                    self.app.on_close()
                except Exception:
                    pass
        else:
            if messagebox.askyesno("Перезапуск", msg + "\n\nПерезапустить сейчас?", parent=self):
                try:
                    self.up.relaunch()
                except Exception as e:
                    messagebox.showerror("Ошибка", str(e), parent=self)
                self.destroy()
                if self.app is not None:
                    try:
                        self.app.on_close()
                    except Exception:
                        pass

    # ---------- откат ----------
    def rollback(self):
        items = self.up.cached_versions()
        if not items:
            messagebox.showinfo("Откат", "Нет скачанных архивов в кэше обновлений.", parent=self)
            return
        win = tk.Toplevel(self)
        win.title("Выберите версию для отката")
        win.geometry("520x320")
        win.transient(self)
        tree = ttk.Treeview(win, columns=("file", "mb"), show="headings", height=10)
        tree.heading("file", text="Архив")
        tree.heading("mb", text="МБ")
        tree.column("file", width=380)
        tree.column("mb", width=80, anchor="center")
        tree.pack(fill="both", expand=True, padx=8, pady=8)
        for it in items:
            tree.insert("", tk.END, values=(it["file"], f"{it['size'] / 1048576:.1f}"))

        def do():
            sel = tree.selection()
            if not sel:
                return
            name = tree.item(sel[0])["values"][0]
            it = next(x for x in items if x["file"] == name)
            ver = name.replace("BasaProject-", "").replace("-win.zip", "").replace("-src.zip", "")
            info = {"version": ver, "file": name, "sha256": "", "size": it["size"]}
            win.destroy()
            if not messagebox.askyesno("Откат", f"Установить версию {ver} из кэша?", parent=self):
                return

            def work():
                try:
                    mode, msg = self.up.install(it["path"], info)
                    self.after(0, lambda: self._installed(mode, msg))
                except Exception as e:
                    m = f"{type(e).__name__}: {e}"
                    self.after(0, lambda x=m: self._fail(x))
            threading.Thread(target=work, daemon=True).start()

        bf = ttk.Frame(win)
        bf.pack(pady=8)
        ttk.Button(bf, text="Установить", command=do).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text="Отмена", command=win.destroy).pack(side=tk.LEFT, padx=5)
        win.grab_set()