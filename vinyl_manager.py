"""
vinyl_manager.py — FH6 ビニールツール ビジネスロジック統括

エクスポート・インポートの全フローを管理する。

フロー:
  エクスポート:
    FH6メモリ → CLiveryGroup検索 → レイヤー読み取り → .fhv保存

  インポート(.fhv):
    .fhv読み込み → レイヤー検証 → FH6メモリ書き込み

  インポート(shapes JSON):
    shapes JSON読み込み → 座標変換 → FH6メモリ書き込み
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from memory_io import ProcessMemory
from process_scanner import ProcessScanner, CLiveryGroup, find_fh6_pid
from structures import LayerRecord, VinylFile, CoordConverter
from serializer import (
    MemoryReader, MemoryWriter, ShapesConverter, FhvSerializer,
)


# ---------------------------------------------------------------------------
# VinylManager
# ---------------------------------------------------------------------------

class VinylManager:

    def __init__(self, pid: int | None = None, verbose: bool = False) -> None:
        self.verbose = verbose

        # PID解決
        if pid is not None:
            self.pid = pid
        else:
            self._log("FH6プロセスを検索中...")
            self.pid = find_fh6_pid()
            if self.pid is None:
                raise RuntimeError(
                    f"FH6プロセスが見つかりません。ゲームが起動しているか確認してください。"
                )
        self._log(f"PID: {self.pid}")

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"[VinylManager] {msg}")

    def _find_group(self, pm: ProcessMemory, layer_count: int | None = None) -> CLiveryGroup:
        """CLiveryGroupをスキャンして返す。複数見つかった場合は選択を促す。"""
        scanner = ProcessScanner(verbose=self.verbose)
        result  = scanner.scan(pm)

        if not result.groups:
            raise RuntimeError(
                "CLiveryGroupが見つかりませんでした。\n"
                "  - ビニールエディタを開いた状態でスキャンしてください。\n"
                "  - vtableアドレスのキャリブレーションが必要かもしれません。"
            )

        # レイヤー数フィルタ
        if layer_count is not None:
            matched = [g for g in result.groups if g.layer_count == layer_count]
            if matched:
                self._log(f"layer_count={layer_count} に一致するグループ: {len(matched)}個")
                return matched[0]
            else:
                print(f"[!] layer_count={layer_count} に一致するグループがありません。")
                print(f"    見つかったグループのlayer_count: {[g.layer_count for g in result.groups]}")

        # 複数グループがある場合
        if len(result.groups) == 1:
            return result.groups[0]

        print(f"\n複数のCLiveryGroupが見つかりました:")
        for i, g in enumerate(result.groups):
            print(f"  [{i}] address={g.group_address:#x}  layer_count={g.layer_count}")
        while True:
            try:
                idx = int(input("使用するグループ番号を入力: "))
                if 0 <= idx < len(result.groups):
                    return result.groups[idx]
            except (ValueError, EOFError):
                pass
            print("  有効な番号を入力してください。")

    # ------------------------------------------------------------------
    # エクスポート
    # ------------------------------------------------------------------

    def export(self, output_path: str | Path) -> VinylFile:
        """
        FH6メモリからビニールデータを読み取り .fhv ファイルに保存する。

        Returns:
          保存した VinylFile
        """
        output_path = Path(output_path)
        self._log(f"エクスポート開始 → {output_path}")

        with ProcessMemory(self.pid) as pm:
            group  = self._find_group(pm)
            reader = MemoryReader(pm)
            vinyl  = reader.to_vinyl_file(group)

        print(f"[*] {len(vinyl.layers)} レイヤーを読み取りました")
        FhvSerializer.save(vinyl, output_path)
        return vinyl

    # ------------------------------------------------------------------
    # インポート（.fhv）
    # ------------------------------------------------------------------

    def import_fhv(self, input_path: str | Path, strict: bool = False) -> int:
        """
        .fhv ファイルからビニールデータをFH6メモリに書き込む。

        Args:
          input_path: .fhv ファイルパス
          strict:     True = レイヤー数不一致時にエラー

        Returns:
          書き込んだレイヤー数
        """
        input_path = Path(input_path)
        self._log(f"インポート開始 (.fhv) ← {input_path}")

        vinyl = FhvSerializer.load(input_path)
        print(f"[*] {len(vinyl.layers)} レイヤーを読み込みました")

        with ProcessMemory(self.pid) as pm:
            group  = self._find_group(pm, layer_count=len(vinyl.layers))
            writer = MemoryWriter(pm)
            count  = writer.write_all_layers(vinyl.layers, group, strict=strict)

        print(f"[*] {count} レイヤーを書き込みました")
        return count

    # ------------------------------------------------------------------
    # インポート（shapes JSON）
    # ------------------------------------------------------------------

    def import_shapes(
        self,
        input_path: str | Path,
        canvas_w: float = 799.0,
        canvas_h: float = 1075.0,
        strict: bool = False,
        save_fhv: str | Path | None = None,
    ) -> int:
        """
        shapes形式JSONをFH6メモリに書き込む。

        Args:
          input_path: shapes JSON ファイルパス
          canvas_w:   元画像の幅（ピクセル）
          canvas_h:   元画像の高さ（ピクセル）
          strict:     True = レイヤー数不一致時にエラー
          save_fhv:   変換後のデータを .fhv として保存するパス（省略可）

        Returns:
          書き込んだレイヤー数
        """
        input_path = Path(input_path)
        self._log(f"インポート開始 (shapes) ← {input_path}")

        # shapes JSON → LayerRecord リスト
        shapes_data = FhvSerializer.load_shapes(input_path)
        conv        = CoordConverter(canvas_w=canvas_w, canvas_h=canvas_h)
        converter   = ShapesConverter(conv)
        layers      = converter.convert(shapes_data)

        print(f"[*] {len(layers)} レイヤーに変換しました")

        # .fhv として保存（オプション）
        if save_fhv is not None:
            vinyl = VinylFile(canvas_w=canvas_w, canvas_h=canvas_h, layers=layers)
            FhvSerializer.save(vinyl, save_fhv)

        # メモリに書き込み
        with ProcessMemory(self.pid) as pm:
            group  = self._find_group(pm, layer_count=len(layers))
            writer = MemoryWriter(pm)
            count  = writer.write_all_layers(layers, group, strict=strict)

        print(f"[*] {count} レイヤーを書き込みました")
        return count

    # ------------------------------------------------------------------
    # スキャンのみ（デバッグ用）
    # ------------------------------------------------------------------

    def scan(self) -> list[CLiveryGroup]:
        """CLiveryGroupをスキャンして一覧を返す"""
        with ProcessMemory(self.pid) as pm:
            scanner = ProcessScanner(verbose=True)
            result  = scanner.scan(pm)

        print(f"\n{'='*60}")
        print(f"スキャン結果: {len(result.groups)} グループ見つかりました")
        for i, g in enumerate(result.groups):
            print(f"  [{i}] address={g.group_address:#018x}  "
                  f"layer_count={g.layer_count}  "
                  f"table={g.table_address:#018x}")
        return result.groups
