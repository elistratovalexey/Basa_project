# -*- coding: utf-8 -*-
"""Поднять базовую версию: python bump_version.py minor|major|1.10"""
import pathlib
import sys

p = pathlib.Path(__file__).resolve().parent / "VERSION"
cur = p.read_text(encoding="utf-8").strip() if p.exists() else "1.9"
major, minor = (cur.split(".") + ["0"])[:2]
major, minor = int(major), int(minor)

arg = sys.argv[1] if len(sys.argv) > 1 else "minor"
if arg == "major":
    major, minor = major + 1, 0
elif arg == "minor":
    minor += 1
else:
    major, minor = (arg.split(".") + ["0"])[:2]
    major, minor = int(major), int(minor)

new = f"{major}.{minor}"
p.write_text(new + "\n", encoding="utf-8")
print(f"VERSION: {cur} -> {new}")
print("Закоммитьте файл VERSION — сборка подхватит новую базу автоматически.")