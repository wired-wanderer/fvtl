"""
vinyl_preview.py — FH6 ビニールプレビューウィジェット

fhvファイルのレイヤーデータを読み取り、
Qt の QPainter で楕円を描画してプレビューする。

座標変換（fhv → ウィジェット座標）:
  fhv の pos_x は JSONのcxそのまま (0〜canvas_w)
  fhv の pos_y は JSONのcyを反転  (-canvas_h〜0)
  → widget_x = pos_x / canvas_w * widget_w
  → widget_y = (-pos_y) / canvas_h * widget_h

スケール変換:
  fhv の scale_x = w / 63.0
  → pixel_w = scale_x * 63.0 / canvas_w * widget_w
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QRectF, QSizeF, Qt, QPointF
from PyQt6.QtGui import (
    QBrush, QColor, QPainter, QPainterPath, QPen, QTransform,
)
from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget


SCALE_DIVISOR = 63.0   # fhv scale → px の係数
CANVAS_W      = 799.0
CANVAS_H      = 1075.0


class VinylPreviewWidget(QWidget):
    """
    fhv ファイルを読み込んでビニールをプレビュー描画するウィジェット。
    アスペクト比を保ったままリサイズに対応する。
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._layers: list[dict] = []
        self._canvas_w = CANVAS_W
        self._canvas_h = CANVAS_H
        self._loaded   = False
        self._label    = ""

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(160, 160)

    def load_fhv(self, path: Path | str) -> bool:
        """fhvファイルを読み込む。成功したらTrueを返す。"""
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)

            canvas = data.get("canvas", {})
            self._canvas_w = float(canvas.get("width",  CANVAS_W))
            self._canvas_h = float(canvas.get("height", CANVAS_H))
            self._layers   = data.get("layers", [])
            self._loaded   = True
            self._label    = Path(path).name
            self.update()
            return True
        except Exception as e:
            self.clear()
            return False

    def clear(self) -> None:
        """プレビューをクリアする。"""
        self._layers  = []
        self._loaded  = False
        self._label   = ""
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # 背景
        painter.fillRect(0, 0, w, h, QColor("#0d1117"))

        if not self._loaded or not self._layers:
            # 未ロード時のプレースホルダー
            painter.setPen(QColor("#30363d"))
            painter.drawRect(0, 0, w - 1, h - 1)
            painter.setPen(QColor("#484f58"))
            painter.drawText(
                QRectF(0, 0, w, h),
                Qt.AlignmentFlag.AlignCenter,
                "No preview",
            )
            return

        # キャンバスのアスペクト比を保ったまま描画領域を計算
        aspect   = self._canvas_w / self._canvas_h
        margin   = 8
        avail_w  = w - margin * 2
        avail_h  = h - margin * 2

        if avail_w / avail_h > aspect:
            draw_h = avail_h
            draw_w = draw_h * aspect
        else:
            draw_w = avail_w
            draw_h = draw_w / aspect

        off_x = (w - draw_w) / 2
        off_y = (h - draw_h) / 2

        # キャンバス枠
        painter.setPen(QPen(QColor("#21262d"), 1))
        painter.drawRect(QRectF(off_x, off_y, draw_w, draw_h))

        # スケール係数
        sx = draw_w / self._canvas_w
        sy = draw_h / self._canvas_h

        # レイヤーを描画（背面から）
        for layer in reversed(self._layers):
            self._draw_layer(painter, layer, off_x, off_y, sx, sy)

        # ファイル名ラベル
        painter.setPen(QColor("#484f58"))
        painter.setFont(self.font())
        painter.drawText(
            QRectF(margin, h - 20, w - margin * 2, 16),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            self._label,
        )

    def _draw_layer(
        self,
        painter: QPainter,
        layer: dict,
        off_x: float, off_y: float,
        sx: float, sy: float,
    ) -> None:
        """1レイヤーを描画する。"""
        shape_id  = layer.get("shape_id", 102)
        pos_x     = float(layer.get("position_x", 0))
        pos_y     = float(layer.get("position_y", 0))
        scale_x   = float(layer.get("scale_x",   1))
        scale_y   = float(layer.get("scale_y",   1))
        rotation  = float(layer.get("rotation",  0))
        color_arr = layer.get("color", [255, 255, 255, 255])

        r = int(color_arr[0])
        g = int(color_arr[1])
        b = int(color_arr[2])
        a = int(color_arr[3])

        # fhv座標 → ウィジェット座標
        # pos_x: 0〜canvas_w そのまま
        # pos_y: (-canvas_h)〜0 → Yを反転して 0〜canvas_h
        cx = off_x + pos_x * sx
        cy = off_y + (-pos_y) * sy

        # スケール値 → ピクセルサイズ
        pw = scale_x * SCALE_DIVISOR * sx
        ph = scale_y * SCALE_DIVISOR * sy

        color = QColor(r, g, b, a)
        painter.save()

        # 中心に移動して回転
        painter.translate(cx, cy)
        painter.rotate(rotation)

        if shape_id == 102:
            # 楕円
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawEllipse(QRectF(-pw / 2, -ph / 2, pw, ph))
        else:
            # 矩形（shape_id=1 等）
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawRect(QRectF(-pw / 2, -ph / 2, pw, ph))

        painter.restore()


class VinylPreviewPanel(QWidget):
    """
    プレビューウィジェット + ラベルをまとめたパネル。
    Export/Import タブから使う。
    """

    def __init__(self, title: str = "Preview", parent=None) -> None:
        super().__init__(parent)
        self._build(title)

    def _build(self, title: str) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color:#484f58;font-size:11px;font-weight:600;")
        lay.addWidget(self.title_label)

        self.preview = VinylPreviewWidget()
        self.preview.setStyleSheet("border-radius: 6px;")
        lay.addWidget(self.preview)

    def load_fhv(self, path: Path | str) -> bool:
        return self.preview.load_fhv(path)

    def clear(self) -> None:
        self.preview.clear()

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)
