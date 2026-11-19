# -*- coding: utf-8 -*-
"""CLI-публикация обновления в облако Mail.ru.
То же, что кнопка «Облако → Публикация версии».

Учётные данные берутся из настроек синхронизации базы (cloud_config.json).
Переменные окружения MAILRU_USER / MAILRU_APP_PASSWORD переопределяют их (для CI).

Примеры:
  python publish_update.py --info
  python publish_update.py --win dist/BasaProject --notes "Что нового"
  python publish_update.py --src . --notes "Правки статусов"
  python publish_update.py --win dist/BasaProject --src . --version 1.9.97
"""
import argparse
import sys

from app_update import AppUpdater

try:
    from cloud_sync import credentials_info
except ImportError:
    credentials_info = None


def show_info(up):
    """Откуда берутся логин/пароль (пароль не печатаем)."""
    if credentials_info is not None:
        ci = credentials_info()
        print("Источник :", ci.get("source"))
        print("Файл     :", ci.get("file"))
        print("Логин    :", ci.get("user"))
        print("Пароль   :", "задан" if ci.get("has_password") else "НЕ задан")
        print("WebDAV   :", ci.get("url"))
        print("Папка    :", ci.get("remote_dir"))
    else:
        ci = up.credentials_info()
        print("Источник :", ci.get("source"))
        print("Файл     :", ci.get("file"))
        print("Логин    :", ci.get("user"))
    print("Обновления:", up.remote_update_dir)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--win", help="папка dist/BasaProject с BasaProject.exe")
    ap.add_argument("--src", help="папка с исходниками (app.py)")
    ap.add_argument("--version", default=None, help="по умолчанию — из сборки")
    ap.add_argument("--notes", default="", help="текст «Что нового»")
    ap.add_argument("--user", default=None)
    ap.add_argument("--password", default=None)
    ap.add_argument("--remote-dir", default=None)
    ap.add_argument("--info", action="store_true", help="показать источник учётных данных")
    a = ap.parse_args()

    up = AppUpdater(log=print)

    # понятная диагностика вместо AttributeError
    if not hasattr(up, "publish"):
        print("ОШИБКА: в app_update.py нет метода publish().\n"
              "Добавьте в класс AppUpdater блок «Публикация дистрибутива в облако»\n"
              "(методы detect_version, make_zip, publish, published_info).")
        sys.exit(1)

    if a.user:
        up.cfg["user"] = a.user
    if a.password:
        up.cfg["password"] = a.password
    if a.remote_dir:
        up.cfg["remote_dir"] = a.remote_dir

    if a.info:
        show_info(up)
        return

    if not a.win and not a.src:
        ap.error("укажите --win и/или --src (или --info)")

    ci = up.credentials_info()
    print(f"Учётные данные: {ci.get('user')} · источник: {ci.get('source')}")
    print(f"Публикация в: {up.remote_update_dir}")

    published = []
    for kind, folder in (("win", a.win), ("src", a.src)):
        if not folder:
            continue
        man = up.publish(folder, kind, a.version, a.notes)
        published.append(f"{kind} {man.get('version')}")

    print("Опубликовано:", ", ".join(published))
    print("Готово. В программе: «⬆ Обновление» → «Проверить обновление».")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ОШИБКА публикации: {type(e).__name__}: {e}")
        sys.exit(1)