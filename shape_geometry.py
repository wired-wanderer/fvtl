"""
shape_geometry.py — 形状ジオメトリ(頂点/インデックス)の読み込みとキャッシュ

assets/<folder>/<X_NN>.json のフォーマット:
  {
    "Info": {"Type": ..., "TypeIndex": ...},
    "Vertices": [{"X": float, "Y": float}, ...],
    "Indices": [int, ...],            // 3個ずつで1三角形
    "VerticesAlpha": "base64..."      // 各頂点のアルファ値（任意）
  }

頂点座標は形状ローカル座標系（中心付近が原点、±64程度の範囲）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass
class ShapeGeometry:
    vertices: list[tuple[float, float]]   # [(x, y), ...]
    indices:  list[int]                    # 3個ずつで1三角形
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y


@lru_cache(maxsize=512)
def load_shape_geometry(json_path: str) -> ShapeGeometry | None:
    """
    形状JSONを読み込んでShapeGeometryを返す。
    結果はキャッシュされる（同じパスへの再読み込みはコストゼロ）。
    """
    try:
        with open(json_path, encoding="utf-8") as f:
            d = json.load(f)

        verts_raw = d.get("Vertices", [])
        indices   = d.get("Indices", [])

        vertices = [(float(v["X"]), float(v["Y"])) for v in verts_raw]
        if not vertices:
            return None

        xs = [v[0] for v in vertices]
        ys = [v[1] for v in vertices]

        return ShapeGeometry(
            vertices=vertices,
            indices=indices,
            min_x=min(xs), min_y=min(ys),
            max_x=max(xs), max_y=max(ys),
        )
    except Exception:
        return None


def get_geometry_for_shape_id(shape_id: int) -> ShapeGeometry | None:
    """shape_idから形状JSONを探してジオメトリを返す"""
    from shape_map import shape_id_to_json
    path = shape_id_to_json(shape_id)
    if path is None:
        return None
    return load_shape_geometry(str(path))
