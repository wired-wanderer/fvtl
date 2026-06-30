"""
vinyl_renderer.py — fhv全体をゲーム座標系で合成描画してPNGに変換する

座標系（fhv）:
  position_x: JSONのcxそのまま (0〜canvas_w)
  position_y: JSONのcyを反転した負値 (-canvas_h〜0)
  scale_x/y:  w/h を 63.0 で割った値（KFPS実測の変換係数）
  rotation:   度数 (0〜360)

形状ジオメトリ（shape_geometry.py 経由）:
  頂点はローカル座標系（だいたい ±64 程度の範囲）
  shape_geometryのwidth/heightを基準にレイヤーのscaleを適用する

合成順序:
  1. 各レイヤーの形状をワールド座標（fhv座標系）に変換
  2. 全レイヤーのバウンディングボックスを計算
  3. 余白を除いた範囲でCanvasサイズを決定し描画
  4. PNGとして保存またはQImageとして返す
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from shape_geometry import get_geometry_for_shape_id, ShapeGeometry

SCALE_DIVISOR = 1.0   # fhv scale → ピクセル変換係数（実機計測で調整）


@dataclass
class TransformedShape:
    """ワールド座標に変換済みの三角形メッシュ"""
    triangles: list[tuple[tuple[float, float], tuple[float, float], tuple[float, float]]]
    color: tuple[int, int, int, int]


def _transform_layer(layer: dict) -> TransformedShape | None:
    """
    レイヤー1枚分の形状をワールド座標（fhv座標系）に変換する。

    変換の流れ:
      1. shape_geometryのローカル頂点を取得
      2. ローカル座標を shape の width/height で正規化（-0.5〜0.5）
      3. レイヤーのscale_x/y * SCALE_DIVISOR を掛けてピクセルサイズに
      4. rotationで回転
      5. position_x, -position_y を加算してワールド座標に配置
         （position_yは負値なので-を掛けて正値にする）
    """
    shape_id = int(layer.get("shape_id", 102))
    geom = get_geometry_for_shape_id(shape_id)
    if geom is None or geom.width <= 0 or geom.height <= 0:
        return None

    pos_x   = float(layer.get("position_x", 0))
    pos_y   = -float(layer.get("position_y", 0))   # 正値に反転
    scale_x = float(layer.get("scale_x", 1)) * SCALE_DIVISOR
    scale_y = float(layer.get("scale_y", 1)) * SCALE_DIVISOR
    rot_deg = float(layer.get("rotation", 0))
    skew    = -float(layer.get("skew", 0))          # Y軸反転に合わせて符号反転
    rot     = math.radians(-rot_deg)                # Y軸反転に合わせて回転方向も反転
    cos_r   = math.cos(rot)
    sin_r   = math.sin(rot)

    color_arr = layer.get("color", [255, 255, 255, 255])
    r = int(color_arr[0]) if len(color_arr) > 0 else 255
    g = int(color_arr[1]) if len(color_arr) > 1 else 255
    b = int(color_arr[2]) if len(color_arr) > 2 else 255
    a = int(color_arr[3]) if len(color_arr) > 3 else 255

    # ローカル座標を正規化してからレイヤーサイズを適用する関数
    cx_local = (geom.min_x + geom.max_x) / 2.0
    cy_local = (geom.min_y + geom.max_y) / 2.0

    def to_world(lx: float, ly: float) -> tuple[float, float]:
        # 形状ローカル中心を原点に
        nx = lx - cx_local
        ny = ly - cy_local
        # レイヤーのピクセルサイズを適用
        sx = nx * scale_x
        sy = ny * scale_y
        # skew（X方向の剪断変形、Yに応じてXがずれる）
        sx = sx + sy * skew
        # 回転
        rx = sx * cos_r - sy * sin_r
        ry = sx * sin_r + sy * cos_r
        # ワールド座標へ平行移動
        return pos_x + rx, pos_y + ry

    triangles = []
    idx = geom.indices
    verts = geom.vertices
    for i in range(0, len(idx) - 2, 3):
        i0, i1, i2 = idx[i], idx[i+1], idx[i+2]
        if max(i0, i1, i2) >= len(verts):
            continue
        p0 = to_world(*verts[i0])
        p1 = to_world(*verts[i1])
        p2 = to_world(*verts[i2])
        triangles.append((p0, p1, p2))

    return TransformedShape(triangles=triangles, color=(r, g, b, a))


def calc_bbox(layers: list[dict]) -> tuple[float, float, float, float] | None:
    """全レイヤーのワールド座標バウンディングボックスを計算する"""
    min_x = min_y =  math.inf
    max_x = max_y = -math.inf
    found = False

    for layer in layers:
        shape = _transform_layer(layer)
        if shape is None:
            continue
        for tri in shape.triangles:
            for x, y in tri:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
                found = True

    if not found:
        return None
    return min_x, min_y, max_x, max_y


def render_vinyl(
    layers: list[dict],
    output_size: int = 1024,
    padding_ratio: float = 0.04,
    background: tuple[int, int, int, int] = (255, 255, 255, 255),
) -> Image.Image | None:
    """
    fhvのレイヤーリストをゲーム座標系で合成描画してPIL Imageを返す。
    バウンディングボックスでトリムし、余白(padding_ratio)を付けて出力する。

    Args:
      layers:        fhvのlayers配列
      output_size:   出力画像の長辺サイズ（px）
      padding_ratio: バウンディングボックスに対する余白の割合
      background:    背景色 RGBA

    Returns:
      PIL.Image (RGBA) または None（描画対象がない場合）
    """
    bbox = calc_bbox(layers)
    if bbox is None:
        return None

    min_x, min_y, max_x, max_y = bbox
    bb_w = max_x - min_x
    bb_h = max_y - min_y

    if bb_w <= 0 or bb_h <= 0:
        return None

    pad = max(bb_w, bb_h) * padding_ratio
    min_x -= pad; max_x += pad
    min_y -= pad; max_y += pad
    bb_w = max_x - min_x
    bb_h = max_y - min_y

    # アスペクト比を保って出力サイズを決定
    if bb_w >= bb_h:
        img_w = output_size
        img_h = int(output_size * bb_h / bb_w)
    else:
        img_h = output_size
        img_w = int(output_size * bb_w / bb_h)
    img_w = max(1, img_w)
    img_h = max(1, img_h)

    scale = img_w / bb_w

    def tx(x: float) -> float:
        return (x - min_x) * scale

    def ty(y: float) -> float:
        return (y - min_y) * scale

    img = Image.new("RGBA", (img_w, img_h), background)

    # 描画順序: JSON記述順で先頭=最背面、末尾=最前面
    # そのままの順で描画すれば後に書かれたものが上に重なる
    for layer in layers:
        shape = _transform_layer(layer)
        if shape is None:
            continue
        r, g, b, a = shape.color
        if a <= 0:
            continue

        # このレイヤー専用の透明バッファに不透明色で描画
        layer_buf = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
        layer_draw = ImageDraw.Draw(layer_buf)
        for (x0, y0), (x1, y1), (x2, y2) in shape.triangles:
            p0 = (tx(x0), ty(y0))
            p1 = (tx(x1), ty(y1))
            p2 = (tx(x2), ty(y2))
            layer_draw.polygon([p0, p1, p2], fill=(r, g, b, 255))

        # レイヤー全体にアルファを適用してから合成
        if a < 255:
            alpha_band = layer_buf.getchannel("A").point(lambda v: v * a // 255)
            layer_buf.putalpha(alpha_band)

        img = Image.alpha_composite(img, layer_buf)

    return img


def render_vinyl_to_file(
    layers: list[dict],
    output_path: str | Path,
    output_size: int = 1024,
    padding_ratio: float = 0.04,
    background: tuple[int, int, int, int] = (255, 255, 255, 255),
) -> bool:
    """render_vinylの結果をPNGファイルに保存する。成功したらTrue。"""
    img = render_vinyl(layers, output_size, padding_ratio, background)
    if img is None:
        return False
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)
    return True


if __name__ == "__main__":
    import sys
    import json as jsonlib

    if len(sys.argv) < 2:
        print("usage: vinyl_renderer.py <fhv_path> [output.png]")
        sys.exit(1)

    fhv_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else "preview.png"

    with open(fhv_path, encoding="utf-8") as f:
        data = jsonlib.load(f)

    layers = data.get("layers", [])
    print(f"レイヤー数: {len(layers)}")

    ok = render_vinyl_to_file(layers, out_path)
    if ok:
        print(f"保存完了: {out_path}")
    else:
        print("描画失敗: 有効なレイヤーがありません")
        sys.exit(1)
