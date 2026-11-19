# -*- coding: utf-8 -*-
"""Публикует обновление в облако Mail.ru: BasaProject/update/.

Примеры:
  python publish_update.py --win dist/BasaProject --notes "Частично получено, Остаток"
  python publish_update.py --src . --notes "Правки статусов"
  python publish_update.py --win dist/BasaProject --src . --version 1.9.152
"""
import argparse
import json
import os
import sys
import zipfile
from datetime import datetime

from app_update import AppUpdater, current_version, sha256_file
from cloud_sync import load_config

SKIP = {"venv", "venv_win", ".git", "__pycache__", "build", "dist", "logs",
        "backups", "cloud_sync", "update", ".github", "app"}
SKIP_FILES = {"projects.db", "config.json", "cloud_config.json", "window_geometry.json",
              "translation_cache.json", "sync_state.json", "portable.txt"}


def make_zip(src_dir, zip_path, kind):
    src_dir = os.path.abspath(src_dir)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        if kind == "win":
            for root, dirs, files in os.walk(src_dir):
                dirs[:] = [d for d in dirs if d not in SKIP]
                for fn in files:
                    full = os.path.join(root, fn)
                    z.write(full, os.path.relpath(full, src_dir))
        else:
            for root, dirs, files in os.walk(src_dir):
                dirs[:] = [d for d in dirs if d not in SKIP]
                for fn in files:
                    if fn in SKIP_FILES:
                        continue
                    if not fn.endswith((".py", ".txt", ".spec", ".sh", ".bat", ".iss")) and fn != "VERSION":
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
    a = ap.parse_args()
    if not a.win and not a.src:
        ap.error("укажите --win и/или --src")

    version = a.version or current_version()
    up = AppUpdater(log=print)
    c = up.client()
    c.ensure_dir(up.remote_update_dir)

    # читаем существующий манифест, чтобы не потерять второй артефакт
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