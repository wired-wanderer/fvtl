"""
process_scanner.py — FH6 ビニールツール プロセス・メモリスキャナー

FH6プロセスのPIDを特定し、CLiveryGroupをメモリからスキャンして返す。

スキャン戦略:
  1. psutil で "forzahorizon6.e" のPIDを取得
  2. vtableバイト列（8バイト LE）をprivate writableリージョンから検索
  3. ヒット候補を4段階バリデーション
  4. 有効なCLiveryGroupのアドレスを返す
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field

import psutil

from memory_io import ProcessMemory, MemoryRegion

# ---------------------------------------------------------------------------
# 既知の定数（要キャリブレーション）
# ---------------------------------------------------------------------------

PROCESS_NAME        = "forzahorizon6.e"   # 15文字truncate
LAYER_SIZE          = 0x140               # 1レイヤーのバイトサイズ

# FH6.exe メモリレイアウト
BASE_ADDR           = 0x140000000         # ASLRなし固定ベースアドレス

# vtable: BASE_ADDR + オフセット = 絶対アドレス
# 旧: 0x140000000 + 0x68227c0 = 0x1468227c0
# 新: 0x140000000 + 0x6822840 = 0x146822840
VTABLE_OFFSET       = 0x6822840
VTABLE_ADDR         = BASE_ADDR + VTABLE_OFFSET   # = 0x146822840

# RTTI descriptor: BASE_ADDR + オフセット
# descriptor + 0x10 から update_code が読める
# 旧オフセット: 0x9E31AA0  新オフセット: 0x9E31C30
DESCRIPTOR_OFFSET   = 0x9E31C30
DESCRIPTOR_ADDR     = BASE_ADDR + DESCRIPTOR_OFFSET   # = 0x149E31C30

# update_code: RTTIディスクリプタ内の型識別文字列
# 旧: b"837518648815"  新: b"97723390891367"
UPDATE_CODE         = b"97723390891367"

# CLiveryGroup オフセット
OFF_VTABLE          = 0x00
OFF_LIVERY_COUNT    = 0x5A   # u16
OFF_TABLE_BEGIN     = 0x78   # ptr
OFF_TABLE_END       = 0x80   # ptr
OFF_TABLE_CAPACITY  = 0x88   # ptr

# スキャン範囲ヒント（Windowsプロセス仮想アドレス空間）
# mapsの観察から: 匿名rw-p領域はこの範囲に集中している
WINE_ADDR_MIN = 0x0000000100000000
WINE_ADDR_MAX = 0x0000000500000000


# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------

@dataclass
class CLiveryGroup:
    """見つかったCLiveryGroupの情報"""
    group_address: int          # CLiveryGroup構造体のアドレス
    table_address: int          # layer_table_begin のアドレス
    layer_count:   int          # (table_end - table_begin) // 8 から計算
    livery_count:  int          # +0x5A の値（参考値）


@dataclass
class ScanResult:
    """スキャン結果のサマリー"""
    pid:          int
    groups:       list[CLiveryGroup] = field(default_factory=list)
    scan_time_s:  float = 0.0
    pages_read:   int   = 0
    candidates:   int   = 0   # vtableヒット数（バリデーション前）


# ---------------------------------------------------------------------------
# PID 検索
# ---------------------------------------------------------------------------

def find_fh6_pid() -> int | None:
    """
    "forzahorizon6.e" という名前のプロセスを探してPIDを返す。
    見つからなければ None。
    """
    for proc in psutil.process_iter(["pid", "name"]):
        name = proc.info.get("name", "") or ""
        if name.startswith(PROCESS_NAME):
            return proc.info["pid"]
    return None


# ---------------------------------------------------------------------------
# アドレスバリデーション
# ---------------------------------------------------------------------------

def _is_valid_ptr(pm: ProcessMemory, addr: int) -> bool:
    """アドレスが非ゼロかつprivate writableリージョン内にあるか"""
    return addr != 0 and pm.is_private_writable(addr)


def _validate_livery_group(pm: ProcessMemory, addr: int) -> CLiveryGroup | None:
    """
    addr を CLiveryGroup として4段階バリデーションする。
    有効なら CLiveryGroup を返し、無効なら None を返す。

    バリデーション:
      1. addr がprivate writableリージョン内にある
      2. layer_table_begin != 0
      3. layer_table_end >= layer_table_begin
      4. (end - begin) % 8 == 0
    """
    try:
        # 1. structを一括読み取り（+0x00 〜 +0x8F、0x90バイト）
        raw = pm.read(addr, 0x90)
    except OSError:
        return None

    def u16_at(off: int) -> int:
        return struct.unpack_from("<H", raw, off)[0]

    def ptr_at(off: int) -> int:
        return struct.unpack_from("<Q", raw, off)[0]

    table_begin    = ptr_at(OFF_TABLE_BEGIN)
    table_end      = ptr_at(OFF_TABLE_END)
    table_capacity = ptr_at(OFF_TABLE_CAPACITY)
    livery_count   = u16_at(OFF_LIVERY_COUNT)

    # 2. layer_table_begin が有効なアドレス
    if table_begin == 0:
        return None

    if not pm.is_private_writable(table_begin):
        return None

    # 3. end >= begin
    if table_end < table_begin:
        return None

    # 4. アラインメントチェック
    size = table_end - table_begin
    if size % 8 != 0:
        return None

    # layer_table はポインタ配列（8バイト/エントリ）
    ptr_count = size // 8

    # 容量チェック（capacity >= end は正常、逆は壊れている）
    if table_capacity < table_end:
        return None

    # レイヤーが0個または異常に多い場合は除外
    if ptr_count == 0 or ptr_count > 10000:
        return None

    return CLiveryGroup(
        group_address = addr,
        table_address = table_begin,
        layer_count   = ptr_count,
        livery_count  = livery_count,
    )


# ---------------------------------------------------------------------------
# メインスキャナー
# ---------------------------------------------------------------------------

class ProcessScanner:
    """
    FH6プロセスからCLiveryGroupをスキャンするクラス。
    """

    def __init__(
        self,
        verbose: bool = False,
        wine_range_only: bool = True,
    ) -> None:
        self.verbose        = verbose
        self.wine_range_only = wine_range_only

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"[Scanner] {msg}")

    def _target_regions(self, pm: ProcessMemory) -> list[MemoryRegion]:
        """スキャン対象リージョンを絞り込む"""
        regions = pm.private_writable_regions()

        if self.wine_range_only:
            # Windowsプロセス仮想アドレス空間の匿名領域に絞る
            regions = [
                r for r in regions
                if WINE_ADDR_MIN <= r.start < WINE_ADDR_MAX
                and r.name == ""   # 匿名リージョンのみ
            ]
            self._log(
                f"スキャン対象: {len(regions)} リージョン "
                f"({sum(r.size for r in regions) // 1024 // 1024} MB)"
            )

        return regions

    def scan(self, pm: ProcessMemory) -> ScanResult:
        """
        CLiveryGroupをスキャンして ScanResult を返す。
        pm は既にopen済みであること。
        """
        result = ScanResult(pid=pm.pid)
        pm.load_maps()   # 最新のmapsを取得

        # vtableをリトルエンディアン8バイトのパターンに変換
        vtable_pattern = struct.pack("<Q", VTABLE_ADDR)
        self._log(f"vtableパターン: {vtable_pattern.hex()} ({VTABLE_ADDR:#x})")

        regions = self._target_regions(pm)
        start_time = time.monotonic()

        seen: set[int] = set()

        for hit_addr in pm.scan_pattern(vtable_pattern, regions):
            result.candidates += 1

            # vtableは+0x00にあるので、hit_addr = group_address
            group_addr = hit_addr
            if group_addr in seen:
                continue
            seen.add(group_addr)

            self._log(f"vtableヒット: {group_addr:#x} (候補 #{result.candidates})")

            group = _validate_livery_group(pm, group_addr)
            if group is not None:
                self._log(
                    f"  → 有効! layer_count={group.layer_count} "
                    f"livery_count={group.livery_count} "
                    f"table={group.table_address:#x}"
                )
                result.groups.append(group)
            else:
                self._log(f"  → バリデーション失敗")

        result.scan_time_s = time.monotonic() - start_time
        self._log(
            f"スキャン完了: {result.scan_time_s:.2f}秒 "
            f"候補={result.candidates} 有効={len(result.groups)}"
        )
        return result

    def scan_for_layer_count(
        self, pm: ProcessMemory, expected_count: int
    ) -> CLiveryGroup | None:
        """
        特定のレイヤー数を持つCLiveryGroupを探す。
        エクスポート前にレイヤー数が分かっている場合に使う。
        """
        result = self.scan(pm)
        for group in result.groups:
            if group.layer_count == expected_count:
                return group
        return None


# ---------------------------------------------------------------------------
# スタンドアロン動作確認（scan コマンド相当）
# ---------------------------------------------------------------------------

def main() -> None:
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="FH6 CLiveryGroup スキャナー")
    parser.add_argument("--pid",     type=int,  help="PIDを直接指定（省略時は自動検索）")
    parser.add_argument("--verbose", action="store_true", help="詳細ログを表示")
    parser.add_argument("--all-regions", action="store_true",
                        help="全リージョンをスキャン（遅い）")
    args = parser.parse_args()

    # PID解決
    pid = args.pid
    if pid is None:
        print(f"[*] '{PROCESS_NAME}' を検索中...")
        pid = find_fh6_pid()
        if pid is None:
            print(f"[!] プロセスが見つかりません: {PROCESS_NAME}")
            print("    FH6が起動しているか確認してください。")
            sys.exit(1)
    print(f"[*] PID: {pid}")

    scanner = ProcessScanner(
        verbose=args.verbose,
        wine_range_only=not args.all_regions,
    )

    with ProcessMemory(pid) as pm:
        result = scanner.scan(pm)

    # 結果表示
    print(f"\n{'='*60}")
    print(f"スキャン結果")
    print(f"{'='*60}")
    print(f"  スキャン時間  : {result.scan_time_s:.2f} 秒")
    print(f"  vtableヒット数: {result.candidates}")
    print(f"  有効グループ数: {len(result.groups)}")
    print()

    if not result.groups:
        print("[!] CLiveryGroupが見つかりませんでした。")
        print("    vtableアドレス (0x{:x}) のキャリブレーションが必要かもしれません。".format(VTABLE_ADDR))
        sys.exit(1)

    for i, g in enumerate(result.groups):
        print(f"  [{i}] group_address = {g.group_address:#018x}")
        print(f"       table_address  = {g.table_address:#018x}")
        print(f"       layer_count    = {g.layer_count}")
        print(f"       livery_count   = {g.livery_count}")
        print()


if __name__ == "__main__":
    main()
