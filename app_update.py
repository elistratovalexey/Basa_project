# -*- coding: utf-8 -*-
"""Обновление программы из папки update/ в облаке Mail.ru (WebDAV).

Windows (frozen exe): скачиваем zip -> staging -> updater.bat ждёт закрытия
процесса, копирует файлы поверх папки установки и запускает новый exe.
Linux/исходники: бэкап текущих файлов -> копирование -> перезапуск.
Данные пользователя (paths.DATA_DIR / LOCAL_DIR) не трогаются.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime

from cloud_sync import WebDavClient, WebDavError, load_config

FROZEN = bool(getattr(sys, "frozen", False))
IS_WIN = sys.platform.startswith("win")


def _dirs():
    try:
        from paths import INSTALL_DIR, LOCAL_DIR, BACKUP_DIR
    except Exception:
        INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
        LOCAL_DIR = INSTALL_DIR
        BACKUP_DIR = os.path.join(INSTALL_DIR, "backups")
    upd = os.path.join(LOCAL_DIR, "update")
    os.makedirs(upd, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    return INSTALL_DIR, LOCAL_DIR, BACKUP_DIR, upd


def current_version():
    try:
        from version import VERSION
        return VERSION
    except Exception:
        try:
            from config import VERSION
            return VERSION
        except Exception:
            return "0.0.0"


def _vt(v):
    """'1.9.152' -> (1, 9, 152) для сравнения."""
    out = []
    for part in str(v or "0").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits or 0))
    while len(out) < 3:
        out.append(0)
    return tuple(out[:3])


def artifact_kind():
    return "win" if (FROZEN and IS_WIN) else "src"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class AppUpdater:
    def __init__(self, app_dir=None, log=print):
        self.log = log
        self.install_dir, self.local_dir, self.backup_dir, self.upd_dir = _dirs()
        self.app_dir = app_dir or self.install_dir
        self.cfg = load_config()          # было load_config(self.app_dir)

    # ---------- клиент ----------
    def client(self):
        if not self.cfg.get("user") or not self.cfg.get("password"):
            raise WebDavError(
                "Нет учётных данных облака.\n"
                "Откройте «☁ Облако → Подключение», заполните логин и пароль приложения,\n"
                "нажмите «Сохранить» — обновление программы использует те же данные.\n"
                f"Файл настроек: {self.cfg.get('_config_file')}")
        return WebDavClient(self.cfg.get("url"), self.cfg["user"], self.cfg["password"],
                            timeout=max(300, int(self.cfg.get("timeout_sec", 300))),
                            retries=int(self.cfg.get("retries", 4)),
                            log=self.log)

    def credentials_info(self):
        return {"user": self.cfg.get("user") or "—",
                "source": self.cfg.get("_source"),
                "file": self.cfg.get("_config_file"),
                "update_dir": self.remote_update_dir}
    @property
    def remote_update_dir(self):
        base = (self.cfg.get("remote_dir") or "BasaProject").strip("/")
        return f"{base}/update"

    def rpath(self, name):
        return f"{self.remote_update_dir}/{name}"

    # ---------- проверка ----------
    def check(self):
        """Читает манифест. Возвращает dict: available, version, notes, artifact..."""
        c = self.client()
        local_manifest = os.path.join(self.upd_dir, "version.json")
        try:
            c.ensure_dir(self.remote_update_dir)
            etag = c.get(self.rpath("version.json"), local_manifest)
            if etag is None and not os.path.exists(local_manifest):
                return {"available": False, "error": "В облаке нет update/version.json"}
        except WebDavError as e:
            return {"available": False, "error": str(e)}
        try:
            with open(local_manifest, "r", encoding="utf-8") as f:
                man = json.load(f)
        except Exception as e:
            return {"available": False, "error": f"Манифест повреждён: {e}"}

        kind = artifact_kind()
        art = (man.get("artifacts") or {}).get(kind)
        if not art:
            return {"available": False, "error": f"В манифесте нет артефакта '{kind}'",
                    "manifest": man}
        cur, new = current_version(), str(man.get("version") or "0.0.0")
        return {
            "available": _vt(new) > _vt(cur),
            "current": cur,
            "version": new,
            "date": man.get("date") or "",
            "notes": man.get("notes") or "",
            "kind": kind,
            "file": art.get("file"),
            "sha256": (art.get("sha256") or "").lower(),
            "size": int(art.get("size") or 0),
            "manifest": man,
        }

    # ---------- скачивание ----------
    def download(self, info):
        name = info["file"]
        dest = os.path.join(self.upd_dir, name)
        if os.path.exists(dest) and info["sha256"] and sha256_file(dest) == info["sha256"]:
            self.log(f"Архив уже скачан и проверен: {name}")
            return dest
        c = self.client()
        self.log(f"Скачивание {name} ({info['size'] / 1048576:.1f} МБ)…")
        c.get(self.rpath(name), dest)
        if info["sha256"]:
            actual = sha256_file(dest)
            if actual != info["sha256"]:
                try:
                    os.remove(dest)
                except OSError:
                    pass
                raise WebDavError(f"SHA-256 не совпал!\nожидалось {info['sha256'][:16]}…\n"
                                  f"получено  {actual[:16]}…\nОбновление отменено.")
            self.log("SHA-256 подтверждён")
        return dest

    # ---------- распаковка ----------
    def _unpack(self, archive, info):
        staging = os.path.join(self.upd_dir, "staging", info["version"])
        if os.path.isdir(staging):
            shutil.rmtree(staging, ignore_errors=True)
        os.makedirs(staging, exist_ok=True)
        with zipfile.ZipFile(archive) as z:
            for m in z.namelist():
                # защита от zip-slip
                target = os.path.realpath(os.path.join(staging, m))
                if not target.startswith(os.path.realpath(staging)):
                    raise WebDavError(f"Небезопасный путь в архиве: {m}")
            z.extractall(staging)
        # если внутри одна вложенная папка — поднимаем её
        entries = [e for e in os.listdir(staging) if not e.startswith("__MACOSX")]
        if len(entries) == 1 and os.path.isdir(os.path.join(staging, entries[0])):
            inner = os.path.join(staging, entries[0])
            if artifact_kind() == "win" and os.path.exists(os.path.join(inner, "BasaProject.exe")):
                staging = inner
            elif artifact_kind() == "src" and os.path.exists(os.path.join(inner, "app.py")):
                staging = inner
        if artifact_kind() == "win":
            if not os.path.exists(os.path.join(staging, "BasaProject.exe")):
                raise WebDavError("В архиве нет BasaProject.exe")
        else:
            if not os.path.exists(os.path.join(staging, "app.py")):
                raise WebDavError("В архиве нет app.py")
        return staging

    # ---------- установка ----------
    def install(self, archive, info):
        """Готовит обновление. Возвращает ('restart'|'relaunch', сообщение)."""
        staging = self._unpack(archive, info)
        if artifact_kind() == "win":
            return self._install_windows(staging, info)
        return self._install_source(staging, info)

    def _install_windows(self, staging, info):
        if not os.access(self.install_dir, os.W_OK):
            raise WebDavError(f"Нет прав на запись в папку программы:\n{self.install_dir}\n"
                              "Перенесите программу в C:\\BasaProject или запустите от администратора.")
        bat = os.path.join(self.upd_dir, "do_update.bat")
        pid = os.getpid()
        exe = os.path.join(self.install_dir, "BasaProject.exe")
        script = f"""@echo off
chcp 65001 >nul
title Обновление База проектов {info['version']}
echo Ждём закрытия программы...
:wait
tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto wait
)
echo Копирую новые файлы...
robocopy "{staging}" "{self.install_dir}" /E /XF portable.txt /R:2 /W:2 /NFL /NDL /NJH /NJS
echo Запускаю программу...
start "" "{exe}"
del "%~f0"
"""
        with open(bat, "w", encoding="utf-8") as f:
            f.write(script)
        DETACHED = 0x00000008 | 0x00000200
        subprocess.Popen(["cmd", "/c", bat], creationflags=DETACHED, close_fds=True)
        self.log("Updater запущен — закройте программу")
        return "restart", (f"Обновление {info['version']} подготовлено.\n"
                           "Программа будет закрыта, файлы обновлены и она запустится снова.")

    # файлы/папки, которые НЕЛЬЗЯ перезаписывать при обновлении из исходников
    _SKIP = {"projects.db", "config.json", "cloud_config.json", "window_geometry.json",
             "translation_cache.json", "sync_state.json", "portable.txt",
             "venv", "venv_win", ".git", "logs", "backups", "cloud_sync", "update",
             "__pycache__", "build", "dist", ".github", "app"}

    def _install_source(self, staging, info):
        # 1) бэкап текущей программной части
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = os.path.join(self.backup_dir, f"app_{current_version()}_{stamp}.zip")
        with zipfile.ZipFile(backup, "w", zipfile.ZIP_DEFLATED) as z:
            for root, dirs, files in os.walk(self.install_dir):
                dirs[:] = [d for d in dirs if d not in self._SKIP]
                for fn in files:
                    if fn in self._SKIP or not fn.endswith((".py", ".txt", ".spec", ".sh", ".bat")):
                        continue
                    full = os.path.join(root, fn)
                    z.write(full, os.path.relpath(full, self.install_dir))
        self.log(f"Бэкап текущей версии: {os.path.basename(backup)}")

        # 2) копирование новых файлов
        copied = 0
        for root, dirs, files in os.walk(staging):
            dirs[:] = [d for d in dirs if d not in self._SKIP]
            rel = os.path.relpath(root, staging)
            dst_root = self.install_dir if rel == "." else os.path.join(self.install_dir, rel)
            os.makedirs(dst_root, exist_ok=True)
            for fn in files:
                if fn in self._SKIP:
                    continue
                shutil.copy2(os.path.join(root, fn), os.path.join(dst_root, fn))
                copied += 1
        self.log(f"Обновлено файлов: {copied}")

        # 3) зависимости могли измениться
        req_new = os.path.join(staging, "requirements.txt")
        if os.path.exists(req_new):
            self.log("Проверьте зависимости: pip install -r requirements.txt")

        return "relaunch", (f"Обновление {info['version']} установлено ({copied} файлов).\n"
                            f"Бэкап: {os.path.basename(backup)}\n"
                            "Нужен перезапуск программы.")

    def relaunch(self):
        """Перезапуск после обновления из исходников."""
        app_py = os.path.join(self.install_dir, "app.py")
        subprocess.Popen([sys.executable, app_py], cwd=self.install_dir, close_fds=True)

    # ==================================================================
    # Публикация дистрибутива в облако (используется GUI и CLI)
    # ==================================================================
    _PUB_SKIP_DIRS = {"venv", "venv_win", ".git", "__pycache__", "build", "dist",
                      "logs", "backups", "cloud_sync", "update", ".github", "app"}
    _PUB_SKIP_FILES = {"projects.db", "config.json", "cloud_config.json",
                       "window_geometry.json", "translation_cache.json",
                       "sync_state.json", "portable.txt",
                       "unins000.exe", "unins000.dat"}
    _SRC_EXT = (".py", ".txt", ".spec", ".sh", ".bat", ".iss", ".yml")

    def detect_version(self, src_dir, kind):
        """Версия сборки: version.json в корне или в _internal (PyInstaller onedir)."""
        src_dir = os.path.abspath(src_dir or "")
        if not os.path.isdir(src_dir):
            return ""
        for rel in ("version.json", os.path.join("_internal", "version.json")):
            p = os.path.join(src_dir, rel)
            if os.path.isfile(p):
                try:
                    with open(p, encoding="utf-8") as f:
                        v = json.load(f).get("version")
                    if v:
                        return str(v)
                except Exception:
                    pass
        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d not in self._PUB_SKIP_DIRS]
            if "version.json" in files:
                try:
                    with open(os.path.join(root, "version.json"), encoding="utf-8") as f:
                        v = json.load(f).get("version")
                    if v:
                        return str(v)
                except Exception:
                    pass
        if kind == "src":
            return current_version()
        # указали папку запущенной установленной программы — её версия и есть версия сборки
        try:
            from paths import INSTALL_DIR
            if os.path.normcase(src_dir) == os.path.normcase(os.path.abspath(INSTALL_DIR)):
                return current_version()
        except Exception:
            pass
        return ""
    
    def make_zip(self, src_dir, zip_path, kind):
        src_dir = os.path.abspath(src_dir)
        if not os.path.isdir(src_dir):
            raise WebDavError(f"Папка не найдена: {src_dir}")
        if kind == "win" and not os.path.exists(os.path.join(src_dir, "BasaProject.exe")):
            raise WebDavError(f"В папке нет BasaProject.exe:\n{src_dir}")
        if kind == "src" and not os.path.exists(os.path.join(src_dir, "app.py")):
            raise WebDavError(f"В папке нет app.py:\n{src_dir}")
        n = 0
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for root, dirs, files in os.walk(src_dir):
                dirs[:] = [d for d in dirs if d not in self._PUB_SKIP_DIRS]
                for fn in files:
                    if fn in self._PUB_SKIP_FILES:
                        continue
                    if kind == "src" and not (fn.endswith(self._SRC_EXT) or fn == "VERSION"):
                        continue
                    full = os.path.join(root, fn)
                    z.write(full, os.path.relpath(full, src_dir))
                    n += 1
        self.log(f"Упаковано файлов: {n}")
        return zip_path

    def publish(self, src_dir, kind, version=None, notes=""):
        """Упаковывает и загружает дистрибутив + манифест в <папка>/update/."""
        src_dir = os.path.abspath(src_dir)
        found = self.detect_version(src_dir, kind)
        version = (version or found or "").strip()
        if not version:
            raise WebDavError("Не определена версия. Укажите её вручную (например 1.9.97).")
        if found and version != found:
            self.log(f"ВНИМАНИЕ: в сборке версия {found}, публикуете {version}. "
                     "Если они разойдутся, программа будет предлагать обновление по кругу.")

        c = self.client()
        c.ensure_dir(self.remote_update_dir)

        name = f"BasaProject-{version}-{kind}.zip"
        local = os.path.join(self.upd_dir, name)
        self.log(f"Упаковка {kind}: {src_dir}")
        self.make_zip(src_dir, local, kind)
        digest = sha256_file(local)
        size = os.path.getsize(local)
        self.log(f"Архив {name}: {size / 1048576:.1f} МБ, sha256 {digest[:16]}…")

        # сохраняем прежний манифест, чтобы не потерять второй артефакт
        man_path = os.path.join(self.upd_dir, "version.json")
        man = {"version": version, "artifacts": {}}
        try:
            if c.get(self.rpath("version.json"), man_path) is not None:
                with open(man_path, encoding="utf-8") as f:
                    old = json.load(f)
                if old.get("version") == version:
                    man = old
        except Exception as e:
            self.log(f"Прежний манифест не прочитан ({e}) — создаём новый")

        man["version"] = version
        man["date"] = datetime.now().strftime("%d.%m.%Y")
        man["notes"] = notes or man.get("notes", "")
        man["channel"] = man.get("channel") or "stable"
        man.setdefault("artifacts", {})
        man["artifacts"][kind] = {"file": name, "sha256": digest, "size": size}

        self.log(f"Загрузка {name} …")
        c.put(self.rpath(name), local)
        with open(man_path, "w", encoding="utf-8") as f:
            json.dump(man, f, ensure_ascii=False, indent=2)
        c.put(self.rpath("version.json"), man_path)
        self.log(f"Опубликовано: версия {version} ({kind})")
        return man

    def published_info(self):
        """Что сейчас лежит в update/ — для кнопки «Что уже в облаке»."""
        c = self.client()
        files = c.list_dir(self.remote_update_dir)
        man = None
        p = os.path.join(self.upd_dir, "published_version.json")
        try:
            if c.get(self.rpath("version.json"), p) is not None:
                with open(p, encoding="utf-8") as f:
                    man = json.load(f)
        except Exception:
            pass
        return {"files": files, "manifest": man}
    
    # ---------- откат ----------
    def cached_versions(self):
        """Скачанные архивы — из них можно откатиться."""
        out = []
        for fn in sorted(os.listdir(self.upd_dir), reverse=True):
            if fn.endswith(".zip"):
                out.append({"file": fn, "path": os.path.join(self.upd_dir, fn),
                            "size": os.path.getsize(os.path.join(self.upd_dir, fn))})
        return out

    def rollback_source_backups(self):
        return sorted((f for f in os.listdir(self.backup_dir)
                       if f.startswith("app_") and f.endswith(".zip")), reverse=True)