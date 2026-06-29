"""
structures.py — FH6 ビニールツール データ構造定義

メモリ上のレイヤー構造体とJSONフォーマットの両方を表現する。

確定済みオフセット（debug_layers.py で検証済み）:
  +0x18  position_x  float   ゲーム座標（中心=0、範囲約±1119）
  +0x1C  position_y  float   ゲーム座標（中心=0、範囲約±716）
  +0x28  scale_x     float   ゲーム値そのまま
  +0x2C  scale_y     float   ゲーム値そのまま
  +0x50  rotation    float   度数 (0〜360)
  +0x70  skew        float   傾き
  +0x74  color_r     u8
  +0x75  color_g     u8
  +0x76  color_b     u8
  +0x77  color_a     u8      255×(透明度/100)
  +0x78  mask        u8
  +0x7A  shape_id    u16     楕円=102

座標系:
  ゲーム座標は中心(0,0)、X範囲約±1119.5、Y範囲約±716.0
  JSONのキャンバス座標(ピクセル)からの変換が必要
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import ClassVar

# ---------------------------------------------------------------------------
# レイヤー構造体オフセット
# ---------------------------------------------------------------------------

LAYER_SIZE      = 0x140

OFF_POSITION_X  = 0x18
OFF_POSITION_Y  = 0x1C
OFF_SCALE_X     = 0x28
OFF_SCALE_Y     = 0x2C
OFF_ROTATION    = 0x50
OFF_SKEW        = 0x70
OFF_COLOR_R     = 0x74
OFF_COLOR_G     = 0x75
OFF_COLOR_B     = 0x76
OFF_COLOR_A     = 0x77
OFF_MASK        = 0x78
OFF_SHAPE_ID    = 0x7A

# shape_id マッピング（確定済み）
SHAPE_ELLIPSE   = 102
SHAPE_RECT      = 1     # 未確認、仮値

# ゲーム座標空間（検証済み）
# キャンバスは1920x1080相当、原点(0,0)=中央、Y軸は上が+
# 左上端=-960,+540 / 右下端=+960,-540
GAME_X_MAX      = 960.0
GAME_Y_MAX      = 540.0


# ---------------------------------------------------------------------------
# LayerRecord — メモリ上のレイヤー1枚
# ---------------------------------------------------------------------------

@dataclass
class LayerRecord:
    """
    CLiveryGroup内の1レイヤーを表すデータクラス。
    メモリの値をそのまま保持する（単位変換なし）。
    """
    position_x: float = 0.0
    position_y: float = 0.0
    scale_x:    float = 1.0
    scale_y:    float = 1.0
    rotation:   float = 0.0    # 度数 (0〜360)
    skew:       float = 0.0    # 傾き
    color_r:    int   = 255
    color_g:    int   = 255
    color_b:    int   = 255
    color_a:    int   = 255
    mask:       int   = 0
    shape_id:   int   = SHAPE_ELLIPSE

    # メモリポインタ（読み取り時に記録、書き戻し時に使用）
    _ptr: int = field(default=0, repr=False, compare=False)

    @classmethod
    def from_bytes(cls, data: bytes, ptr: int = 0) -> "LayerRecord":
        """生バイト列からLayerRecordを生成"""
        assert len(data) >= LAYER_SIZE, f"データが短すぎます: {len(data)} < {LAYER_SIZE}"

        def f32(off): return struct.unpack_from("<f", data, off)[0]
        def u8(off):  return struct.unpack_from("<B", data, off)[0]
        def u16(off): return struct.unpack_from("<H", data, off)[0]

        return cls(
            position_x = f32(OFF_POSITION_X),
            position_y = f32(OFF_POSITION_Y),
            scale_x    = f32(OFF_SCALE_X),
            scale_y    = f32(OFF_SCALE_Y),
            rotation   = f32(OFF_ROTATION),
            skew       = f32(OFF_SKEW),
            color_r    = u8(OFF_COLOR_R),
            color_g    = u8(OFF_COLOR_G),
            color_b    = u8(OFF_COLOR_B),
            color_a    = u8(OFF_COLOR_A),
            mask       = u8(OFF_MASK),
            shape_id   = u16(OFF_SHAPE_ID),
            _ptr       = ptr,
        )

    def to_patch(self) -> list[tuple[int, bytes]]:
        """
        メモリへの書き込みパッチリストを返す。
        [(オフセット, バイト列), ...] の形式。
        _ptr + オフセット が実際のアドレス。
        """
        patches = [
            (OFF_POSITION_X, struct.pack("<f", self.position_x)),
            (OFF_POSITION_Y, struct.pack("<f", self.position_y)),
            (OFF_SCALE_X,    struct.pack("<f", self.scale_x)),
            (OFF_SCALE_Y,    struct.pack("<f", self.scale_y)),
            (OFF_ROTATION,   struct.pack("<f", self.rotation)),
            (OFF_SKEW,       struct.pack("<f", self.skew)),
            (OFF_COLOR_R,    struct.pack("<B", self.color_r)),
            (OFF_COLOR_G,    struct.pack("<B", self.color_g)),
            (OFF_COLOR_B,    struct.pack("<B", self.color_b)),
            (OFF_COLOR_A,    struct.pack("<B", self.color_a)),
            (OFF_MASK,       struct.pack("<B", self.mask)),
            (OFF_SHAPE_ID,   struct.pack("<H", self.shape_id)),
        ]
        return patches

    def to_dict(self) -> dict:
        """JSONシリアライズ用の辞書に変換"""
        return {
            "position_x": round(self.position_x, 4),
            "position_y": round(self.position_y, 4),
            "scale_x":    round(self.scale_x,    4),
            "scale_y":    round(self.scale_y,    4),
            "rotation":   round(self.rotation,   4),
            "skew":       round(self.skew,        4),
            "color":      [self.color_r, self.color_g, self.color_b, self.color_a],
            "mask":       self.mask,
            "shape_id":   self.shape_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LayerRecord":
        """辞書からLayerRecordを生成（JSONインポート用）"""
        color = d.get("color", [255, 255, 255, 255])
        return cls(
            position_x = float(d.get("position_x", 0.0)),
            position_y = float(d.get("position_y", 0.0)),
            scale_x    = float(d.get("scale_x",    1.0)),
            scale_y    = float(d.get("scale_y",    1.0)),
            rotation   = float(d.get("rotation",   0.0)),
            skew       = float(d.get("skew",        0.0)),
            color_r    = int(color[0]),
            color_g    = int(color[1]),
            color_b    = int(color[2]),
            color_a    = int(color[3]),
            mask       = int(d.get("mask",          0)),
            shape_id   = int(d.get("shape_id",      SHAPE_ELLIPSE)),
        )


# ---------------------------------------------------------------------------
# CoordConverter — JSON座標 ↔ ゲーム座標変換
# ---------------------------------------------------------------------------

@dataclass
class CoordConverter:
    """
    入力JSONのキャンバス座標をゲーム座標に変換する。

    ゲーム座標系（検証済み）:
      中心 (0, 0) = キャンバス中央
      X範囲: -960.0 〜 +960.0   左がマイナス、右がプラス
      Y範囲: -540.0 〜 +540.0   下がマイナス、上がプラス  ← Y軸反転に注意
      (1920x1080相当、16:9)

    JSON座標系:
      左上 (0, 0)
      X範囲: 0 〜 canvas_w
      Y範囲: 0 〜 canvas_h      上がゼロ、下が大きい  ← 通常の画像座標
      cx, cy はシェイプの中心座標
    """
    canvas_w: float = 799.0
    canvas_h: float = 1075.0
    game_x_max: float = GAME_X_MAX
    game_y_max: float = GAME_Y_MAX

    def json_to_game_pos(self, cx: float, cy: float) -> tuple[float, float]:
        """JSON中心座標 → ゲーム座標
        
        KFPSの実測から確定:
          game_x = cx        （そのままコピー）
          game_y = -cy       （Y符号反転のみ）
        正規化や倍率変換は不要。
        """
        return cx, -cy

    def game_to_json_pos(self, gx: float, gy: float) -> tuple[float, float]:
        """ゲーム座標 → JSON中心座標"""
        return gx, -gy

    def json_to_game_scale(self, w: float, h: float) -> tuple[float, float]:
        """JSONピクセルサイズ → ゲームスケール値
        
        KFPSの実測から確定: 除数=63.0（全2500シェイプで誤差ゼロ）
          scale_x = w / 63.0
          scale_y = h / 63.0
        """
        return w / 63.0, h / 63.0

    def game_to_json_scale(self, sx: float, sy: float) -> tuple[float, float]:
        """ゲームスケール値 → JSONピクセルサイズ"""
        return sx * 63.0, sy * 63.0


# ---------------------------------------------------------------------------
# VinylFile — .fhv ファイル全体
# ---------------------------------------------------------------------------

@dataclass
class VinylFile:
    """
    .fhv ファイルの全データを保持するクラス。
    JSONシリアライズ/デシリアライズの起点。
    """
    FHV_VERSION: ClassVar[int] = 1

    game:         str = "fh6"
    update_code:  str = "97723390891367"
    canvas_w:     float = 799.0
    canvas_h:     float = 1075.0
    layers:       list[LayerRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "fhv_version":  self.FHV_VERSION,
            "game":         self.game,
            "update_code":  self.update_code,
            "canvas":       {"width": self.canvas_w, "height": self.canvas_h},
            "layer_count":  len(self.layers),
            "layers":       [l.to_dict() for l in self.layers],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VinylFile":
        canvas = d.get("canvas", {})
        layers = [LayerRecord.from_dict(l) for l in d.get("layers", [])]
        return cls(
            game        = d.get("game", "fh6"),
            update_code = d.get("update_code", ""),
            canvas_w    = float(canvas.get("width",  799.0)),
            canvas_h    = float(canvas.get("height", 1075.0)),
            layers      = layers,
        )