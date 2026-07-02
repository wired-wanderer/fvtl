#!/usr/bin/env python3
"""
calibrator.py — FH6 CLiveryGroup オフセット自動キャリブレーター

FH6のアップデートで CLiveryGroup 関連のRTTIオフセット
(vtable_offset, descriptor_offset, update_code) がズレたときに、
現在の値を再発見して results/ フォルダにJSONで保存する。

読み取り専用。ゲームプロセスへの書き込みは一切行わない。

使い方:
  python calibrator.py auto            # 自動キャリブレーション（2000〜3000枚のレイヤーを用意して実行）

言語:
  デフォルトはOSのロケール設定(LC_ALL / LC_MESSAGES / LANG)から自動判定する。
  -jp を付けると強制的に日本語、-en を付けると強制的に英語で出力する。

    python calibrator.py auto -jp
    python calibrator.py auto -en
"""

from __future__ import annotations

import json
import os
import struct
import sys
import time
from pathlib import Path

import numpy as np
import psutil

from memory_io import ProcessMemory, MemoryRegion

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

PROCESS_NAMES = ("forzahorizon6.exe", "forzahorizon6.e")

# CLiveryGroup 構造体レイアウト（要キャリブレーション対象そのものではなく、
# 「レイアウトが妥当かどうか」を検証するための固定オフセット）
LIVERY_COUNT_OFFSET          = 0x5A   # u16: レイヤー枚数
LAYER_TABLE_START_OFFSET     = 0x78   # ptr: レイヤーポインタ配列の先頭
LAYER_TABLE_END_OFFSET       = 0x80   # ptr: 同・末尾
LAYER_TABLE_CAPACITY_OFFSET  = 0x88   # ptr: 同・確保容量
GROUP_HEADER_SCAN_SIZE        = 0x300  # 候補ヘッダーを読む範囲
LAYER_RECORD_SIZE             = 0x140  # 1レイヤー分の構造体サイズ

AUTO_COUNT_MIN = 2000
AUTO_COUNT_MAX = 3000

SCAN_CHUNK_SIZE = 64 * 1024 * 1024  # 64MBずつ読む（numpyオーバーヘッド削減のため大きめ）

RESULTS_DIR = Path(__file__).parent / "results"


# ---------------------------------------------------------------------------
# 国際化（i18n）
# ---------------------------------------------------------------------------

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "usage":                  "usage: python calibrator.py auto [-jp|-en]",
        "usage_auto":              "  auto   : automatic calibration (prepare ~2000-3000 layers)",
        "process_not_found":       "forzahorizon6.exe not found. Please open FH6 and the vinyl editor first.",
        "main_module_not_found":   "Could not find the FH6 main module.",
        "pe_header_not_found":     "PE header (MZ) not found. Check module_base.",
        "nt_header_not_found":     "NT header (PE) not found.",
        "auto_start":              "Starting automatic calibration.",
        "auto_prepare":            "Please display about {min}-{max} layers in the FH6 vinyl editor.",
        "auto_ready_prompt":       "Press Enter when ready... ",
        "process_found":           "FH6 process found: pid={pid}, module={name} base={base} size={size}",
        "scanning_struct":         "Scanning CLiveryGroup structure (layer count range specified)...",
        "candidate_count":         "Candidates: {n}",
        "no_candidates":           "No candidates found. Check the layer count and editor state.",
        "rtti_failed":             "Candidates found but RTTI tracing failed. Try again with a different layer count.",
        "scan_progress_mb":        "  Scanning... {scanned}/{total} MB, candidates={n}",
        "invalid_count":           "Enter a number from 1 to 3000.",
        "result_saved":            "Result saved: {path}",
        "update_code_line":        "update_code = {v}",
        "vtable_offset_line":      "vtable_offset = {v}",
        "descriptor_offset_line":  "descriptor_offset = {v}",
        "interrupted":             "Interrupted.",
        "failed":                  "Failed: {e}",
        "exact_count_prompt":      "If you know the exact layer count, enter it now for a much faster scan (or press Enter to skip): ",
    },
    "jp": {
        "usage":                  "使い方: python calibrator.py auto [-jp|-en]",
        "usage_auto":              "  auto   : 自動キャリブレーション（2000〜3000枚程度のレイヤーを用意）",
        "process_not_found":       "forzahorizon6.exe が見つかりません。FH6とビニールエディタを開いてください。",
        "main_module_not_found":   "FH6メインモジュールが見つかりません。",
        "pe_header_not_found":     "PEヘッダー(MZ)が見つかりません。module_baseを確認してください。",
        "nt_header_not_found":     "NTヘッダー(PE)が見つかりません。",
        "auto_start":              "自動キャリブレーションを開始します。",
        "auto_prepare":            "FH6のビニールエディタで {min}〜{max} 枚程度のレイヤーを表示させておいてください。",
        "auto_ready_prompt":       "準備ができたらEnterキーを押してください... ",
        "process_found":           "FH6プロセス発見: pid={pid}, module={name} base={base} size={size}",
        "scanning_struct":         "CLiveryGroup構造をスキャン中（枚数レンジ指定）...",
        "candidate_count":         "候補数: {n}",
        "no_candidates":           "候補が見つかりませんでした。レイヤー枚数やエディタの状態を確認してください。",
        "rtti_failed":             "候補は見つかりましたが、RTTI追跡に失敗しました。レイヤー枚数を変えて再試行してください。",
        "scan_progress_mb":        "  スキャン中... {scanned}/{total} MB, 候補={n}",
        "invalid_count":           "1〜3000の数値を入力してください。",
        "result_saved":            "結果を保存しました: {path}",
        "update_code_line":        "update_code = {v}",
        "vtable_offset_line":      "vtable_offset = {v}",
        "descriptor_offset_line":  "descriptor_offset = {v}",
        "interrupted":             "中断されました。",
        "failed":                  "失敗: {e}",
        "exact_count_prompt":      "正確なレイヤー枚数が分かる場合はここで入力すると大幅に高速化されます（不明なら空欄でEnter）: ",
    },
}

LANG = "en"  # detect_language() / main() の引数解析で確定させる


def detect_language() -> str:
    """
    OSのロケール設定から言語を自動判定する。
    LC_ALL > LC_MESSAGES > LANG の優先順で環境変数を確認し、
    "ja" で始まっていれば日本語、それ以外は英語とする。
    """
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if value.lower().startswith("ja"):
            return "jp"
        if value:
            return "en"
    return "en"


def t(key: str, **kwargs) -> str:
    """メッセージテーブルから現在の言語のテキストを取得しフォーマットする"""
    template = MESSAGES.get(LANG, MESSAGES["en"]).get(key, key)
    return template.format(**kwargs)


def log(key: str, **kwargs) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {t(key, **kwargs)}", flush=True)


def as_hex(value: int | None) -> str | None:
    """整数を "0x..." 表記へ。Noneはそのまま透過する。"""
    if value is None:
        return None
    return f"0x{int(value):x}"


def _bulk_read_best_effort(fd: int, addr: int, size: int) -> bytes:
    """
    大きな範囲を1回のシステムコールで読む（スキャン専用の緩い版）。
    途中に読めないページが混ざっていても例外にせず、読めた分だけ返す
    （ProcessMemory.readのような厳密なゼロ埋め保証はしない）。
    """
    try:
        os.lseek(fd, addr, os.SEEK_SET)
        return os.read(fd, size)
    except OSError:
        return b""


# ---------------------------------------------------------------------------
# プロセス発見
# ---------------------------------------------------------------------------

def locate_fh6_pid() -> int:
    for proc in psutil.process_iter(["pid", "name"]):
        name = (proc.info.get("name") or "").lower()
        if name in PROCESS_NAMES:
            return proc.info["pid"]
    raise RuntimeError(t("process_not_found"))


def locate_main_module(pm: ProcessMemory) -> MemoryRegion:
    """メインexeイメージのリージョンを返す（offset=0のもの）"""
    candidates = [
        r for r in pm.regions
        if r.name.lower().endswith(".exe") and r.offset == 0
    ]
    if not candidates:
        raise RuntimeError(t("main_module_not_found"))
    for r in candidates:
        if Path(r.name).name.lower() == "forzahorizon6.exe":
            return r
    return candidates[0]


def read_pe_size_of_image(pm: ProcessMemory, module_base: int) -> int:
    """
    メモリ上のPEヘッダーから SizeOfImage を直接読む。
    Wine環境では /proc/pid/maps のパス名がヘッダーページにしか
    付与されないことがあるため、maps由来のサイズ推定より確実。
    """
    dos_header = pm.read(module_base, 0x40)
    if len(dos_header) < 0x40 or dos_header[:2] != b"MZ":
        raise RuntimeError(t("pe_header_not_found"))

    e_lfanew = struct.unpack_from("<I", dos_header, 0x3C)[0]
    nt_header_addr = module_base + e_lfanew

    nt_sig = pm.read(nt_header_addr, 4)
    if nt_sig != b"PE\x00\x00":
        raise RuntimeError(t("nt_header_not_found"))

    # NTヘッダー + 0x50 = OptionalHeader.SizeOfImage（PE32/PE32+共通オフセット）
    size_of_image = pm.read_u32(nt_header_addr + 0x50)
    return size_of_image


def _within_bounds(value: float, limit: float = 2000.0) -> bool:
    """NaNを弾きつつ [-limit, limit] に収まっているかを判定する"""
    if value != value:  # NaN
        return False
    return -limit <= value <= limit


# ---------------------------------------------------------------------------
# 構造チェック
# ---------------------------------------------------------------------------

def _evaluate_layer(pm: ProcessMemory, ptr: int) -> int:
    """1レイヤー分の構造体を覗いて、もっともらしい値かどうかを点数化する"""
    if not ptr:
        return 0
    raw = pm.read(ptr, LAYER_RECORD_SIZE)
    if len(raw) < 0x7C:
        return 0

    points = 0
    px, py = struct.unpack_from("<ff", raw, 0x18)
    sx, sy = struct.unpack_from("<ff", raw, 0x28)
    rot = struct.unpack_from("<f", raw, 0x50)[0]
    shape = struct.unpack_from("<H", raw, 0x7A)[0]

    if _within_bounds(px) and _within_bounds(py):
        points += 2
    if _within_bounds(sx, 500) and _within_bounds(sy, 500) and (abs(sx) > 1e-5 or abs(sy) > 1e-5):
        points += 2
    if _within_bounds(rot, 1_000_000):
        points += 1
    if 0 <= shape <= 2000:
        points += 1
    return points


def _evaluate_table(pm: ProcessMemory, table: int, count: int) -> int:
    """レイヤーポインタ配列を間引きサンプリングして合計点を出す"""
    raw = pm.read(table, count * 8)
    if len(raw) != count * 8:
        return 0
    ptrs = struct.unpack(f"<{count}Q", raw)

    sample_count = min(count, 24)
    step = max(1, count // sample_count)
    total = 0
    for i in range(0, count, step):
        total += _evaluate_layer(pm, ptrs[i])
    return total


def _confirm_group(pm: ProcessMemory, group: int, expected_count: int) -> dict | None:
    """group候補が本当にCLiveryGroup構造として整合するか検証しスコアを返す"""
    if not pm.is_private_writable(group):
        return None

    raw = pm.read(group, GROUP_HEADER_SCAN_SIZE)
    if len(raw) < GROUP_HEADER_SCAN_SIZE:
        return None

    count = struct.unpack_from("<H", raw, LIVERY_COUNT_OFFSET)[0]
    if count != expected_count:
        return None

    table_begin = struct.unpack_from("<Q", raw, LAYER_TABLE_START_OFFSET)[0]
    table_end   = struct.unpack_from("<Q", raw, LAYER_TABLE_END_OFFSET)[0]
    table_cap   = struct.unpack_from("<Q", raw, LAYER_TABLE_CAPACITY_OFFSET)[0]

    if not (table_begin and table_end and table_cap):
        return None
    if table_end != table_begin + count * 8:
        return None
    if table_cap < table_end:
        return None
    if not pm.is_private_writable(table_begin):
        return None

    score = _evaluate_table(pm, table_begin, count)
    if score <= 0:
        return None

    vtable = struct.unpack_from("<Q", raw, 0)[0]
    return {"score": score, "group": group, "count": count, "table": table_begin, "vtable": vtable}


def scan_memory_for_group(pm: ProcessMemory, count_min: int, count_max: int) -> list[dict]:
    """
    RW private領域を1回だけ読み、numpyでu16値を一括判定する（高速版）。
    count_min〜count_max の範囲に収まる位置を group 候補として構造検証する。
    """
    candidates: list[dict] = []
    seen: set[int] = set()
    regions = pm.private_writable_regions()
    total_mb = sum(r.size for r in regions) / (1024 * 1024)
    scanned_mb = 0.0

    # スキャン専用の生fd（1回のos.readでまとめて読む。ページ単位ゼロ埋めはしない）
    scan_fd = os.open(f"/proc/{pm.pid}/mem", os.O_RDONLY)
    try:
        for region in regions:
            start, size = region.start, region.size
            for chunk_start in range(start, start + size, SCAN_CHUNK_SIZE):
                chunk_size = min(SCAN_CHUNK_SIZE, start + size - chunk_start)
                data = _bulk_read_best_effort(scan_fd, chunk_start, chunk_size)
                scanned_mb += len(data) / (1024 * 1024)
                if len(data) < 2:
                    continue

                arr = np.frombuffer(data, dtype=np.uint8)
                lo = arr[:-1].astype(np.uint32)
                hi = arr[1:].astype(np.uint32)
                values = lo | (hi << 8)
                hit_offsets = np.nonzero((values >= count_min) & (values <= count_max))[0]

                for off in hit_offsets.tolist():
                    count = int(values[off])
                    group = chunk_start + off - LIVERY_COUNT_OFFSET
                    if group in seen:
                        continue
                    seen.add(group)
                    result = _confirm_group(pm, group, count)  # 個別検証はProcessMemory.read（安全版）でOK
                    if result:
                        candidates.append(result)
                        candidates.sort(key=lambda c: c["score"], reverse=True)
                        del candidates[30:]

            log("scan_progress_mb", scanned=int(scanned_mb), total=int(total_mb), n=len(candidates))
    finally:
        os.close(scan_fd)

    return candidates


# ---------------------------------------------------------------------------
# RTTI追跡: vtable → COL → TypeDescriptor 階層 → update_code
# ---------------------------------------------------------------------------

def resolve_rtti(pm: ProcessMemory, module_base: int, module_size: int, group: int, vtable: int | None = None) -> dict | None:
    """
    MSVCのRTTIレイアウトを vtable から辿り、型を一意に識別するコードを取り出す。
      vtable[-1] = CompleteObjectLocator へのポインタ
      COL + 0x0C = TypeDescriptor の RVA
      COL + 0x10, +0x14 = ClassHierarchyDescriptor / self の RVA
    """
    def in_module(addr: int, size: int = 1) -> bool:
        return module_base <= addr and addr + size <= module_base + module_size

    vtable = vtable or pm.read_u64(group)
    if not vtable or not in_module(vtable, 8):
        return None

    col = pm.read_u64(vtable - 8)
    if not col or not in_module(col, 0x18):
        return None

    signature = pm.read_u32(col)
    if signature != 1:
        return None

    descriptor_rva       = pm.read_u32(col + 0x0C)
    class_descriptor_rva = pm.read_u32(col + 0x10)
    self_rva              = pm.read_u32(col + 0x14)

    descriptor = module_base + descriptor_rva
    if not in_module(descriptor, 0x20):
        return None
    direct_type_name = pm.read(descriptor + 0x10, 64).split(b"\x00", 1)[0].decode("ascii", "replace")

    update_code = ""
    base_address = col - int(self_rva)
    class_hierarchy = base_address + int(class_descriptor_rva)
    if in_module(class_hierarchy, 0x10):
        base_class_array_rva = struct.unpack_from("<i", pm.read(class_hierarchy + 0xC, 4))[0]
        base_class_array = base_address + int(base_class_array_rva)
        first_base_class_rva = struct.unpack_from("<i", pm.read(base_class_array, 4))[0]
        base_class_descriptor = base_address + int(first_base_class_rva)
        type_descriptor_rva = struct.unpack_from("<i", pm.read(base_class_descriptor, 4))[0]
        hierarchy_descriptor = base_address + int(type_descriptor_rva)
        if in_module(hierarchy_descriptor, 0x20):
            update_code = pm.read(hierarchy_descriptor + 0x10, 64).split(b"\x00", 1)[0].decode("ascii", "replace")

    return {
        "update_code":        update_code or direct_type_name,
        "direct_type_name":   direct_type_name,
        "vtable_offset":      vtable - module_base,
        "descriptor_offset":  descriptor_rva,
        "source_group":       as_hex(group),
    }


# ---------------------------------------------------------------------------
# 自動キャリブレーション
# ---------------------------------------------------------------------------

def ask_optional_layer_count() -> int | None:
    """
    既知の正確なレイヤー枚数があれば入力してもらう（任意）。
    分かっている場合は劇的に高速化できるため推奨。
    空欄ならNoneを返し、従来通り範囲(2000-3000)でスキャンする。
    """
    v = input(t("exact_count_prompt")).strip()
    if not v:
        return None
    try:
        n = int(v, 0)
        if AUTO_COUNT_MIN <= n <= AUTO_COUNT_MAX:
            return n
    except ValueError:
        pass
    print(t("invalid_count"))
    return None


def run_auto() -> dict:
    log("auto_start")
    log("auto_prepare", min=AUTO_COUNT_MIN, max=AUTO_COUNT_MAX)
    input(t("auto_ready_prompt"))

    exact_count = ask_optional_layer_count()

    pid = locate_fh6_pid()
    with ProcessMemory(pid) as pm:
        module = locate_main_module(pm)
        module_size = read_pe_size_of_image(pm, module.start)
        log("process_found", pid=pid, name=Path(module.name).name, base=as_hex(module.start), size=module_size)

        log("scanning_struct")
        if exact_count is not None:
            candidates = scan_memory_for_group(pm, exact_count, exact_count)
        else:
            candidates = scan_memory_for_group(pm, AUTO_COUNT_MIN, AUTO_COUNT_MAX)
        log("candidate_count", n=len(candidates))

        if not candidates:
            raise RuntimeError(t("no_candidates"))

        for cand in candidates[:10]:
            rtti = resolve_rtti(pm, module.start, module_size, cand["group"], cand["vtable"])
            if not rtti:
                continue
            return {
                "mode": "auto",
                "pid": pid,
                "module": {"name": Path(module.name).name, "base": as_hex(module.start), "size": module_size},
                "candidate": {
                    "group": as_hex(cand["group"]), "table": as_hex(cand["table"]),
                    "count": cand["count"], "score": cand["score"], "vtable": as_hex(cand["vtable"]),
                },
                "rtti": rtti,
                "confidence": "high" if rtti.get("update_code") else "low",
            }

        raise RuntimeError(t("rtti_failed"))


# ---------------------------------------------------------------------------
# 結果保存
# ---------------------------------------------------------------------------

def write_result_json(result: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d%H%M%S")
    path = RESULTS_DIR / f"{ts}_auto_result.json"
    result["created_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------

def main() -> int:
    global LANG
    LANG = detect_language()

    args = sys.argv[1:]
    if "-jp" in args:
        LANG = "jp"
        args = [a for a in args if a != "-jp"]
    elif "-en" in args:
        LANG = "en"
        args = [a for a in args if a != "-en"]

    if len(args) < 1 or args[0] != "auto":
        print(t("usage"))
        print()
        print(t("usage_auto"))
        return 1

    try:
        result = run_auto()
    except KeyboardInterrupt:
        print()
        log("interrupted")
        return 130
    except Exception as e:
        log("failed", e=e)
        return 1

    path = write_result_json(result)
    log("result_saved", path=path)
    log("update_code_line", v=result["rtti"].get("update_code"))
    log("vtable_offset_line", v=as_hex(result["rtti"].get("vtable_offset")))
    log("descriptor_offset_line", v=as_hex(result["rtti"].get("descriptor_offset")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
