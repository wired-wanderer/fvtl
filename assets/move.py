#!/usr/bin/env python3

from pathlib import Path
import shutil

# このスクリプトを置いた場所を基準にする
BASE_DIR = Path(__file__).resolve().parent

# フォルダ名からプレフィックス辞書を作成
prefix_map = {}

for d in BASE_DIR.iterdir():
    if d.is_dir() and "_" in d.name:
        prefix = d.name.split("_", 1)[0]
        prefix_map[prefix] = d

print(f"Found {len(prefix_map)} categories.")

moved = 0
skipped = 0

for f in BASE_DIR.iterdir():
    if not f.is_file():
        continue

    if "_" not in f.stem:
        skipped += 1
        continue

    prefix = f.stem.split("_", 1)[0]

    dest_dir = prefix_map.get(prefix)

    if dest_dir is None:
        print(f"[SKIP] {f.name} (no matching folder)")
        skipped += 1
        continue

    dest = dest_dir / f.name

    print(f"[MOVE] {f.name} -> {dest_dir.name}/")
    shutil.move(str(f), str(dest))
    moved += 1

print()
print(f"Moved   : {moved}")
print(f"Skipped : {skipped}")