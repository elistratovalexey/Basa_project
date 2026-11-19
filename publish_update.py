# -*- coding: utf-8 -*-
"""Публикует обновление программы в облако Mail.ru: <папка>/update/.

Учётные данные берутся из настроек синхронизации базы («Облако → Подключение»).
Для CI их можно переопределить переменными MAILRU_USER / MAILRU_APP_PASSWORD.

Примеры:
  python publish_update.py --win dist/BasaProject --notes "Частично получено, Остаток"
  python publish_update.py --src . --notes "Правки статусов"
  python publish_update.py --win dist/BasaProject --src . --version 1.9.152
  python publish_update.py --info          # показать, откуда берутся логин/пароль
"""
import argparse
import json
import os
import sys
import zipfile
from datetime import datetime

from app_update import AppUpdater, current_version, sha256_file
from cloud_sync import load_config, credentials_info

SKIP_DIRS = {"venv", "venv_win", ".git", "__pycache__", "build", "dist", "logs",
             "backups", "cloud_sync", "update", ".github", "app"}
SKIP_FILES = {"projects.db", "config.json", "cloud_config.json", "window_geometry.json",
              "translation_cache.json", "sync_state.json", "portable.txt"}
SRC_EXT = (".py", ".txt", ".spec", ".sh", ".bat", ".iss", ".yml")


def make_zip(src_dir, zip_path, kind):
    src_dir = os.path.abspath(src_dir)
    if not os.path.isdir(src_dir):
        raise SystemExit(f"Папка не найдена: {src_dir}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fn in files:
                if fn in SKIP_FILES:
                    continue
                if kind == "src" and not (fn.endswith(SRC_EXT) or fn == "VERSION"):
                    continue
                full = os.path.join(root, fn)
                z.write(full, os.path.relpath(full, src_dir))
    return zip_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--win", help="папка dist/BasaProject с exe")
    ap.add_argument("--src", help="папка с исходниками")
    ap.add_argument("--version", default=None)
    ap.add_argument("--notes", default="")
    ap.add_argument("--channel", default="stable")
    ap.add_argument("--user", default=None, help="переопределить логин (необязательно)")
    ap.add_argument("--password", default=None, help="переопределить пароль (необязательно)")
    ap.add_argument("--remote-dir", default=None, help="переопределить папку в облаке")
    ap.add_argument("--info", action="store_true", help="показать источник учётных данных")
    a = ap.parse_args()

    if a.info:
        ci = credentials_info()
        print("Источник :", ci["source"])
        print("Файл     :", ci["file"])
        print("Логин    :", ci["user"])
        print("Пароль   :", "задан" if ci["has_password"] else "НЕ задан")
        print("WebDAV   :", ci["url"])
        print("Папка    :", ci["remote_dir"])
        return

    if not a.win and not a.src:
        ap.error("укажите --win и/или --src (или --info)")

    up = AppUpdater(log=print)
    # учётные данные — из настроек синхронизации; аргументы/env могут переопределить
    if a.user:
        up.cfg["user"] = a.user
    if a.password:
        up.cfg["password"] = a.password
    if a.remote_dir:
        up.cfg["remote_dir"] = a.remote_dir

    ci = up.credentials_info()
    print(f"Учётные данные: {ci['user']} · источник: {ci['source']}")
    print(f"Публикация в: {up.remote_update_dir}")

    version = a.version or current_version()
    c = up.client()
    c.ensure_dir(up.remote_update_dir)

    man_path = os.path.join(up.upd_dir, "version.json")
    man = {"version": version, "artifacts": {}}
    try:
        c.get(up.rpath("version.json"), man_path)
        with open(man_path, encoding="utf-8") as f:
            old = json.load(f)
        if old.get("version") == version:
            man = old
    except Exception:
        pass

    man["version"] = version
    man["date"] = datetime.now().strftime("%d.%m.%Y")
    man["notes"] = a.notes or man.get("notes", "")
    man["channel"] = a.channel
    man.setdefault("artifacts", {})

    for kind, folder in (("win", a.win), ("src", a.src)):
        if not folder:
            continue
        name = f"BasaProject-{version}-{kind}.zip"
        local = os.path.join(up.upd_dir, name)
        print(f"Упаковка {kind}: {folder} -> {name}")
        make_zip(folder, local, kind)
        digest = sha256_file(local)
        size = os.path.getsize(local)
        print(f"  {size / 1048576:.1f} МБ, sha256 {digest[:16]}…")
        c.put(up.rpath(name), local)
        man["artifacts"][kind] = {"file": name, "sha256": digest, "size": size}
        print(f"  загружено: {up.rpath(name)}")

    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
    c.put(up.rpath("version.json"), man_path)
    print(f"Манифест обновлён: версия {version}")
    print("Готово. В программе: «⬆ Обновление» → Проверить обновление.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ОШИБКА публикации: {type(e).__name__}: {e}")
        sys.exit(1)