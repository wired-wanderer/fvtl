"""
serializer.py — FH6 ビニールツール シリアライザー

JSON(.fhv) ↔ メモリ上のLayerRecord の変換と、
入力JSON(shapes形式) → LayerRecord の変換を担当する。

対応するJSONフォーマット:
  shapes形式（既存Windowsツール互換）:
    {"shapes": [{"type": 16, "data": [cx, cy, w, h, rot°], "color": [R,G,B,A]}, ...]}

  .fhv形式（本ツール独自、ゲーム座標で保存）:
    {"fhv_version": 1, "layers": [{"position_x": ..., ...}, ...]}
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

from structures import (
    LayerRecord, VinylFile, CoordConverter,
    LAYER_SIZE, SHAPE_ELLIPSE, SHAPE_RECT,
    OFF_POSITION_X, OFF_POSITION_Y, OFF_SCALE_X, OFF_SCALE_Y,
    OFF_ROTATION, OFF_SKEW, OFF_COLOR_R, OFF_MASK, OFF_SHAPE_ID,
)
from memory_io import ProcessMemory
from process_scanner import CLiveryGroup


# ---------------------------------------------------------------------------
# shapes形式のtype → shape_id マッピング
# 確定: type=16(楕円) → shape_id=102
# 未確認のtypeはKFPSエクスポートで確認するまでtypeの値をそのまま使う
# ---------------------------------------------------------------------------

SHAPE_TYPE_MAP: dict[int, int] = {
    16: SHAPE_ELLIPSE,  # 楕円（確定: 102）
}


# ---------------------------------------------------------------------------
# MemoryReader — メモリからVinylFileを読み取る
# ---------------------------------------------------------------------------

class MemoryReader:
    """CLiveryGroupからレイヤーデータを読み取る"""

    def __init__(self, pm: ProcessMemory) -> None:
        self.pm = pm

    def read_layer(self, layer_ptr: int) -> LayerRecord:
        """レイヤーポインタから1枚のLayerRecordを読み取る"""
        raw = self.pm.read(layer_ptr, LAYER_SIZE)
        return LayerRecord.from_bytes(raw, ptr=layer_ptr)

    def read_all_layers(self, group: CLiveryGroup) -> list[LayerRecord]:
        """CLiveryGroup内の全レイヤーを読み取る"""
        # ポインタテーブルを読む
        ptr_table_raw = self.pm.read(group.table_address, group.layer_count * 8)
        layers = []
        for i in range(group.layer_count):
            layer_ptr = struct.unpack_from("<Q", ptr_table_raw, i * 8)[0]
            if layer_ptr == 0:
                continue
            try:
                layer = self.read_layer(layer_ptr)
                layers.append(layer)
            except OSError as e:
                print(f"[!] layer[{i}] 読み取り失敗 (ptr={layer_ptr:#x}): {e}")
        return layers

    def to_vinyl_file(self, group: CLiveryGroup) -> VinylFile:
        """CLiveryGroupをVinylFileに変換（エクスポート用）"""
        layers = self.read_all_layers(group)
        return VinylFile(layers=layers)


# ---------------------------------------------------------------------------
# MemoryWriter — VinylFileをメモリに書き込む
# ---------------------------------------------------------------------------

class MemoryWriter:
    """LayerRecordをメモリに書き込む"""

    def __init__(self, pm: ProcessMemory) -> None:
        self.pm = pm

    def write_layer(self, layer: LayerRecord) -> None:
        """
        LayerRecordをメモリに書き込む。
        layer._ptr が書き込み先アドレス。
        フィールドごとにパッチを適用する（構造体全体の上書きは危険なため）。
        """
        if layer._ptr == 0:
            raise ValueError("layer._ptr が未設定です（インポート時はwrite_layer_to_ptr を使うこと）")

        for offset, data in layer.to_patch():
            self.pm.write(layer._ptr + offset, data)

    def write_layer_to_ptr(self, layer: LayerRecord, ptr: int) -> None:
        """指定ポインタにLayerRecordを書き込む"""
        for offset, data in layer.to_patch():
            self.pm.write(ptr + offset, data)

    def write_all_layers(
        self,
        layers: list[LayerRecord],
        group: CLiveryGroup,
        strict: bool = False,
    ) -> int:
        """
        全レイヤーをメモリに書き込む。

        layers の数と group.layer_count が異なる場合:
          strict=True  → ValueError を送出
          strict=False → 少ない方の枚数だけ書き込み（警告を表示）

        Returns:
          実際に書き込んだレイヤー数
        """
        # 既存ポインタテーブルを読む
        ptr_table_raw = self.pm.read(group.table_address, group.layer_count * 8)
        ptrs = [
            struct.unpack_from("<Q", ptr_table_raw, i * 8)[0]
            for i in range(group.layer_count)
        ]

        n_src  = len(layers)
        n_dst  = len(ptrs)

        if n_src != n_dst:
            msg = (
                f"レイヤー数不一致: インポート={n_src} / メモリ={n_dst}\n"
                f"  メモリ上のレイヤー数に合わせて書き込みます。"
            )
            if strict:
                raise ValueError(msg)
            print(f"[!] {msg}")

        write_count = min(n_src, n_dst)
        for i in range(write_count):
            ptr = ptrs[i]
            if ptr == 0:
                print(f"[!] layer[{i}] のポインタが0、スキップ")
                continue
            self.write_layer_to_ptr(layers[i], ptr)

        return write_count


# ---------------------------------------------------------------------------
# ShapesConverter — 入力JSON(shapes形式) → LayerRecord リスト
# ---------------------------------------------------------------------------

class ShapesConverter:
    """
    既存ツール出力の shapes[] 形式JSONを LayerRecord リストに変換する。

    shapes[].data の意味:
      type=16 (楕円): [cx, cy, width, height, rotation°]
      type=1  (矩形): [x, y, width, height]

    座標変換:
      JSONキャンバス座標(ピクセル) → ゲーム座標（CoordConverterを使用）
    """

    def __init__(self, converter: CoordConverter | None = None, verbose: bool = False) -> None:
        self.conv    = converter or CoordConverter()
        self.verbose = verbose

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"[ShapesConverter] {msg}")

    def convert(self, shapes_data: dict) -> list[LayerRecord]:
        """shapes辞書からLayerRecordリストに変換"""
        shapes = shapes_data.get("shapes", [])
        layers: list[LayerRecord] = []

        for i, shape in enumerate(shapes):
            stype = shape.get("type", 16)
            data  = shape.get("data", [])
            color = shape.get("color", [255, 255, 255, 255])

            shape_id = SHAPE_TYPE_MAP.get(stype, stype)  # 未知のtypeはそのままshape_idに使用
            r, g, b, a = (
                int(color[0]) if len(color) > 0 else 255,
                int(color[1]) if len(color) > 1 else 255,
                int(color[2]) if len(color) > 2 else 255,
                int(color[3]) if len(color) > 3 else 255,
            )

            if stype == 1:
                # 背景矩形はスキップ（キャンバス全体を覆うため不要）
                self._log(f"shapes[{i}] type=1 (背景矩形) をスキップ")
                continue

            elif stype == 16 and len(data) >= 5:
                # 楕円: [cx, cy, width, height, rotation°]
                cx, cy, w, h, rot = (
                    float(data[0]), float(data[1]),
                    float(data[2]), float(data[3]),
                    float(data[4]),
                )
                gx, gy   = self.conv.json_to_game_pos(cx, cy)
                sx, sy   = self.conv.json_to_game_scale(w, h)
                game_rot = (360.0 - rot) % 360.0  # Y反転による回転反転

                layers.append(LayerRecord(
                    position_x = gx,
                    position_y = gy,
                    scale_x    = sx,
                    scale_y    = sy,
                    rotation   = game_rot,
                    skew       = 0.0,
                    color_r    = r,
                    color_g    = g,
                    color_b    = b,
                    color_a    = a,
                    mask       = 0,
                    shape_id   = shape_id,
                ))

            else:
                print(f"[!] shapes[{i}] type={stype} は未対応、スキップ")

        return layers


# ---------------------------------------------------------------------------
# FhvSerializer — .fhv ファイルの読み書き
# ---------------------------------------------------------------------------

class FhvSerializer:
    """VinylFile ↔ .fhv (JSON) ファイルの変換"""

    @staticmethod
    def load_any(path: str | Path, converter: CoordConverter | None = None) -> VinylFile:
        """
        .fhv形式 / shapes形式(既存Windowsツール互換) を自動判別して読み込み、
        どちらも統一的に VinylFile として返す。
        """
        path = Path(path)
        with path.open(encoding="utf-8") as f:
            data = json.load(f)

        if "shapes" in data:
            layers = ShapesConverter(converter).convert(data)
            return VinylFile(layers=layers)

        if "layers" in data or "fhv_version" in data:
            version = data.get("fhv_version", 0)
            if version != VinylFile.FHV_VERSION:
                print(f"[!] fhv_version={version} は未対応です（対応: {VinylFile.FHV_VERSION}）")
            return VinylFile.from_dict(data)

        raise ValueError(f"未対応のJSON形式です: {path.name}")
    
    @staticmethod
    def save(vinyl: VinylFile, path: str | Path) -> None:
        """VinylFileを.fhvファイルに保存"""
        path = Path(path)
        with path.open("w", encoding="utf-8") as f:
            json.dump(vinyl.to_dict(), f, ensure_ascii=False, indent=2)
        print(f"[*] 保存: {path}  ({len(vinyl.layers)} レイヤー)")

    @staticmethod
    def load(path: str | Path) -> VinylFile:
        """.fhvファイルからVinylFileを読み込む"""
        path = Path(path)
        with path.open(encoding="utf-8") as f:
            data = json.load(f)

        version = data.get("fhv_version", 0)
        if version != VinylFile.FHV_VERSION:
            print(f"[!] fhv_version={version} は未対応です（対応: {VinylFile.FHV_VERSION}）")

        return VinylFile.from_dict(data)

    @staticmethod
    def load_shapes(path: str | Path) -> dict:
        """shapes形式のJSONを読み込む（既存ツール互換）"""
        path = Path(path)
        with path.open(encoding="utf-8") as f:
            return json.load(f)
