"""
memory_io.py — FH6 ビニールツール メモリI/Oレイヤー

/proc/<pid>/mem と /proc/<pid>/maps への低レベルアクセスを提供する。

注意点:
- read_process_memory は4096バイトページ単位で読み、
  読めないページはゼロ埋めして必ず要求サイズを返す
- is_private_writable は base <= addr < end で判定する
  （リージョンのbaseとの一致ではなく範囲内チェック）
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

PAGE_SIZE = 4096


# ---------------------------------------------------------------------------
# MemoryRegion
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MemoryRegion:
    start:   int
    end:     int
    perms:   str   # e.g. "rwxp"
    offset:  int
    dev:     str
    inode:   int
    name:    str   # pathname or empty

    @property
    def is_private_writable(self) -> bool:
        return 'w' in self.perms and self.perms.endswith('p')

    @property
    def size(self) -> int:
        return self.end - self.start

    def contains(self, addr: int) -> bool:
        """アドレスがこのリージョンの範囲内か（base <= addr < end）"""
        return self.start <= addr < self.end


# ---------------------------------------------------------------------------
# ProcessMemory
# ---------------------------------------------------------------------------

class ProcessMemory:
    """
    /proc/<pid>/mem への読み書きと
    /proc/<pid>/maps のパースをまとめたクラス。
    """

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self._mem_path  = Path(f"/proc/{pid}/mem")
        self._maps_path = Path(f"/proc/{pid}/maps")
        self._regions:  list[MemoryRegion] | None = None
        self._mem_fd:   int | None = None

    # ------------------------------------------------------------------
    # コンテキストマネージャ
    # ------------------------------------------------------------------

    def __enter__(self) -> "ProcessMemory":
        self.open()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def open(self) -> None:
        """mem ファイルディスクリプタを開く（O_RDWR）"""
        self._mem_fd = os.open(str(self._mem_path), os.O_RDWR)

    def close(self) -> None:
        if self._mem_fd is not None:
            os.close(self._mem_fd)
            self._mem_fd = None

    # ------------------------------------------------------------------
    # maps パース
    # ------------------------------------------------------------------

    def load_maps(self) -> list[MemoryRegion]:
        """
        /proc/<pid>/maps を読み込み MemoryRegion リストを返す。
        毎回再読み込みする（スキャン前に呼ぶこと）。
        """
        regions: list[MemoryRegion] = []
        text = self._maps_path.read_text(errors="replace")
        for line in text.splitlines():
            parts = line.split(None, 5)
            if len(parts) < 5:
                continue
            addr_range, perms, offset, dev, inode = parts[:5]
            name = parts[5].strip() if len(parts) == 6 else ""
            start_s, end_s = addr_range.split("-")
            regions.append(MemoryRegion(
                start  = int(start_s, 16),
                end    = int(end_s,   16),
                perms  = perms,
                offset = int(offset, 16),
                dev    = dev,
                inode  = int(inode),
                name   = name,
            ))
        self._regions = regions
        return regions

    @property
    def regions(self) -> list[MemoryRegion]:
        if self._regions is None:
            self.load_maps()
        return self._regions  # type: ignore[return-value]

    def is_private_writable(self, addr: int) -> bool:
        """
        addr を含む private writable リージョンが存在するか。
        base <= addr < end で判定する（リージョン先頭との一致ではない）。
        """
        for r in self.regions:
            if r.contains(addr) and r.is_private_writable:
                return True
        return False

    def find_region(self, addr: int) -> MemoryRegion | None:
        """addr を含むリージョンを返す。なければ None。"""
        for r in self.regions:
            if r.contains(addr):
                return r
        return None

    def private_writable_regions(self) -> list[MemoryRegion]:
        """private writable なリージョン一覧を返す"""
        return [r for r in self.regions if r.is_private_writable]

    # ------------------------------------------------------------------
    # 読み書き
    # ------------------------------------------------------------------

    def read(self, addr: int, size: int) -> bytes:
        """
        addr から size バイト読む。
        4096バイトページ単位で読み、読めないページはゼロ埋めして
        必ず size バイトを返す。
        """
        assert self._mem_fd is not None, "open() を先に呼ぶこと"

        result = bytearray(size)
        read_pos = 0

        # ページ境界に合わせて読む
        page_start = addr & ~(PAGE_SIZE - 1)
        offset_in_first_page = addr - page_start

        current_page = page_start

        while read_pos < size:
            # このページで読む範囲
            page_offset = offset_in_first_page if current_page == page_start else 0
            want = min(PAGE_SIZE - page_offset, size - read_pos)

            try:
                os.lseek(self._mem_fd, current_page + page_offset, os.SEEK_SET)
                chunk = os.read(self._mem_fd, want)
                result[read_pos:read_pos + len(chunk)] = chunk
                read_pos += len(chunk)
                # os.read が短く返した場合は残りゼロ埋め済み
                if len(chunk) < want:
                    read_pos += want - len(chunk)  # ゼロ埋め分を進める
            except OSError:
                # 読めないページはゼロ埋め（result は bytearray(size) で初期化済み）
                read_pos += want

            current_page += PAGE_SIZE

        return bytes(result)

    def write(self, addr: int, data: bytes) -> None:
        """addr に data を書き込む。失敗時は OSError を送出。"""
        assert self._mem_fd is not None, "open() を先に呼ぶこと"
        os.lseek(self._mem_fd, addr, os.SEEK_SET)
        written = os.write(self._mem_fd, data)
        if written != len(data):
            raise OSError(f"書き込みバイト数不一致: {written} != {len(data)}")

    # ------------------------------------------------------------------
    # 便利なプリミティブ読み取り
    # ------------------------------------------------------------------

    def read_u8(self,  addr: int) -> int:
        return struct.unpack_from("<B", self.read(addr, 1))[0]

    def read_u16(self, addr: int) -> int:
        return struct.unpack_from("<H", self.read(addr, 2))[0]

    def read_u32(self, addr: int) -> int:
        return struct.unpack_from("<I", self.read(addr, 4))[0]

    def read_u64(self, addr: int) -> int:
        return struct.unpack_from("<Q", self.read(addr, 8))[0]

    def read_float(self, addr: int) -> float:
        return struct.unpack_from("<f", self.read(addr, 4))[0]

    def read_ptr(self, addr: int) -> int:
        """8バイトポインタを読む（リトルエンディアン）"""
        return self.read_u64(addr)

    def write_u8(self,    addr: int, v: int)   -> None: self.write(addr, struct.pack("<B", v))
    def write_u16(self,   addr: int, v: int)   -> None: self.write(addr, struct.pack("<H", v))
    def write_u32(self,   addr: int, v: int)   -> None: self.write(addr, struct.pack("<I", v))
    def write_u64(self,   addr: int, v: int)   -> None: self.write(addr, struct.pack("<Q", v))
    def write_float(self, addr: int, v: float) -> None: self.write(addr, struct.pack("<f", v))

    # ------------------------------------------------------------------
    # スキャンユーティリティ
    # ------------------------------------------------------------------

    def scan_pattern(
        self,
        pattern: bytes,
        regions: list[MemoryRegion] | None = None,
    ) -> Iterator[int]:
        """
        指定リージョン群からバイト列を検索し、ヒットしたアドレスを yield する。
        regions が None の場合は private_writable_regions() を使う。
        """
        targets = regions if regions is not None else self.private_writable_regions()

        for region in targets:
            start = region.start
            size  = region.size
            if size == 0:
                continue

            # 大きなリージョンはページ単位で少しずつ処理
            CHUNK = PAGE_SIZE * 256  # 1MB ずつ
            for chunk_start in range(start, start + size, CHUNK):
                chunk_size = min(CHUNK, start + size - chunk_start)
                data = self.read(chunk_start, chunk_size)

                offset = 0
                while True:
                    idx = data.find(pattern, offset)
                    if idx == -1:
                        break
                    yield chunk_start + idx
                    offset = idx + 1

    # ------------------------------------------------------------------
    # デバッグ
    # ------------------------------------------------------------------

    def dump_regions(self) -> None:
        """private writable リージョン一覧を表示（デバッグ用）"""
        print(f"[ProcessMemory] PID={self.pid} private writable regions:")
        for r in self.private_writable_regions():
            name = r.name or "(anonymous)"
            print(f"  {r.start:#018x}-{r.end:#018x}  {r.perms}  {r.size//1024:>8} KB  {name}")


# ---------------------------------------------------------------------------
# スタンドアロン動作確認
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("usage: memory_io.py <pid>")
        sys.exit(1)

    pid = int(sys.argv[1])
    with ProcessMemory(pid) as pm:
        pm.load_maps()
        pm.dump_regions()
        print(f"\ntotal private writable regions: {len(pm.private_writable_regions())}")
