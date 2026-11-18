# -*- coding: utf-8 -*-
"""Единый источник версии программы.

  MAJOR.MINOR — файл VERSION (правится вручную на вехе)
  PATCH       — число коммитов git (растёт само)
  дата/sha    — из git; в собранном exe — из version.json (создаётся при сборке)

Использование:
    from version import VERSION, BUILD_DATE, FULL_VERSION
    python version.py            # печать полной версии
    python version.py --json     # JSON для сборочных скриптов
"""
import json
import os
import subprocess
import sys
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN = bool(getattr(sys, "frozen", False))
BUNDLE_DIR = getattr(sys, "_MEIPASS", _HERE) if FROZEN else _HERE
INSTALL_DIR = os.path.dirname(sys.executable) if FROZEN else _HERE
DEFAULT_BASE = "1.9"


def _read_base():
    for d in (BUNDLE_DIR, INSTALL_DIR, _HERE):
        p = os.path.join(d, "VERSION")
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    s = f.read().strip()
                if s and s[0].isdigit():
                    return s
            except OSError:
                pass
    return DEFAULT_BASE


def _git(*args):
    try:
        r = subprocess.run(("git",) + args, cwd=_HERE, capture_output=True,
                           text=True, timeout=5)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ""


def _read_json():
    for d in (BUNDLE_DIR, INSTALL_DIR, _HERE):
        p = os.path.join(d, "version.json")
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


def compute():
    """Собирает словарь с версией. Приоритет — version.json (снят при сборке)."""
    data = _read_json()
    base = str(data.get("base") or _read_base())
    parts = base.split(".")
    while len(parts) < 2:
        parts.append("0")
    base = ".".join(parts[:2])

    if data:
        build = str(data.get("build") or 0)
        date = data.get("date") or datetime.now().strftime("%d.%m.%Y")
        sha = data.get("sha") or ""
        channel = data.get("channel") or "build"
        built_at = data.get("built_at") or ""
    else:
        build = _git("rev-list", "--count", "HEAD") or "0"
        sha = _git("rev-parse", "--short", "HEAD")
        date = (_git("log", "-1", "--format=%cd", "--date=format:%d.%m.%Y")
                or datetime.now().strftime("%d.%m.%Y"))
        channel = "dev" if _git("status", "--porcelain") else "git"
        built_at = ""

    version = f"{base}.{build}"
    tail = f"от {date}" + (f", {sha}" if sha else "")
    return {
        "base": base,
        "build": int(build) if build.isdigit() else 0,
        "version": version,
        "date": date,
        "sha": sha,
        "channel": channel,
        "built_at": built_at,
        "full": f"{version} ({tail})",
    }


INFO = compute()
VERSION = INFO["version"]
BUILD_DATE = INFO["date"]
BUILD_NUMBER = INFO["build"]
GIT_SHA = INFO["sha"]
CHANNEL = INFO["channel"]
FULL_VERSION = INFO["full"]
VERSION_INFO = INFO


def write_version_json(path="version.json", channel="build"):
    """Вызывается сборкой (basa.spec / CI): фиксирует версию в файл."""
    info = compute()
    info["channel"] = channel
    info["built_at"] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    return info


if __name__ == "__main__":
    if "--json" in sys.argv:
        print(json.dumps(compute(), ensure_ascii=False))
    elif "--write" in sys.argv:
        print(write_version_json()["full"])
    else:
        print(FULL_VERSION)