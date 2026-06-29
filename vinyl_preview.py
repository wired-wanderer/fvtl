"""
vinyl_preview.py — FH6 ビニールプレビューウィジェット v2

座標系（fhv）:
  pos_x: 0 〜 canvas_w  （JSONのcxそのまま）
  pos_y: -canvas_h 〜 0  （JSONのcyを反転済み）

描画変換:
  widget_x = off_x + pos_x * sx
  widget_y = off_y + (-pos_y) * sy   ← pos_yは負なので-で正にする
  ellipse_w = scale_x * 63.0 * sx
  ellipse_h = scale_y * 63.0 * sy
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

SCALE_DIVISOR = 63.0


class VinylPreviewWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._layers: list[dict] = []
        self._canvas_w = 799.0
        self._canvas_h = 1075.0
        self._loaded   = False
        self._label    = ""
        self.setMinimumSize(180, 200)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        # 背景色を明示的に設定
        self.setAutoFillBackground(True)
        p = self.palette()
        p.setColor(self.backgroundRole(), QColor("#0d1117"))
        self.setPalette(p)

    def load_fhv(self, path: Path | str) -> bool:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            canvas = data.get("canvas", {})
            self._canvas_w = float(canvas.get("width",  799.0))
            self._canvas_h = float(canvas.get("height", 1075.0))
            self._layers   = data.get("layers", [])
            self._loaded   = True
            self._label    = Path(path).name
            self.update()
            return True
        except Exception:
            self.clear()
            return False

    def clear(self) -> None:
        self._layers = []
        self._loaded = False
        self._label  = ""
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # 背景
        painter.fillRect(0, 0, w, h, QColor("#0d1117"))

        if not self._loaded or not self._layers:
            painter.setPen(QPen(QColor("#30363d"), 1))
            painter.drawRect(1, 1, w - 2, h - 2)
            painter.setPen(QColor("#484f58"))
            painter.drawText(
                QRectF(0, 0, w, h),
                Qt.AlignmentFlag.AlignCenter,
                "No preview",
            )
            return

        # キャンバス描画領域（アスペクト比維持）
        margin  = 10
        avail_w = w - margin * 2
        avail_h = h - margin * 2 - 18   # 下部ラベル分
        aspect  = self._canvas_w / self._canvas_h

        if avail_w / avail_h > aspect:
            draw_h = avail_h
            draw_w = draw_h * aspect
        else:
            draw_w = avail_w
            draw_h = draw_w / aspect

        off_x = (w - draw_w) / 2
        off_y = margin

        # キャンバス枠
        painter.setPen(QPen(QColor("#30363d"), 1))
        painter.setBrush(QColor("#080c10"))
        painter.drawRect(QRectF(off_x, off_y, draw_w, draw_h))

        # クリッピング（キャンバス外にはみ出さない）
        painter.setClipRect(QRectF(off_x, off_y, draw_w, draw_h))

        # スケール係数
        sx = draw_w / self._canvas_w
        sy = draw_h / self._canvas_h

        # レイヤーを背面から描画
        for layer in reversed(self._layers):
            self._draw_layer(painter, layer, off_x, off_y, sx, sy)

        painter.setClipping(False)

        # ファイル名
        painter.setPen(QColor("#484f58"))
        painter.drawText(
            QRectF(margin, off_y + draw_h + 2, w - margin * 2, 16),
            Qt.AlignmentFlag.AlignCenter,
            self._label,
        )

    def _draw_layer(
        self,
        painter: QPainter,
        layer: dict,
        off_x: float, off_y: float,
        sx: float, sy: float,
    ) -> None:
        shape_id  = int(layer.get("shape_id", 102))
        pos_x     = float(layer.get("position_x", 0))
        pos_y     = float(layer.get("position_y", 0))
        scale_x   = float(layer.get("scale_x",   1))
        scale_y   = float(layer.get("scale_y",   1))
        rotation  = float(layer.get("rotation",  0))
        color_arr = layer.get("color", [255, 255, 255, 255])

        r = int(color_arr[0]) if len(color_arr) > 0 else 255
        g = int(color_arr[1]) if len(color_arr) > 1 else 255
        b = int(color_arr[2]) if len(color_arr) > 2 else 255
        a = int(color_arr[3]) if len(color_arr) > 3 else 255

        # fhv座標 → ウィジェット座標
        # pos_y は負値（-canvas_h〜0）なので -pos_y で正にする
        cx = off_x + pos_x * sx
        cy = off_y + (-pos_y) * sy

        # スケール → ピクセルサイズ
        pw = scale_x * SCALE_DIVISOR * sx
        ph = scale_y * SCALE_DIVISOR * sy

        color = QColor(r, g, b, a)

        painter.save()
        painter.translate(cx, cy)
        painter.rotate(rotation)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))

        if shape_id == 102:
            # 楕円
            painter.drawEllipse(QRectF(-pw / 2, -ph / 2, pw, ph))
        else:
            # 矩形（その他のshape_idは矩形で代替表示）
            painter.drawRect(QRectF(-pw / 2, -ph / 2, pw, ph))

        painter.restore()


class VinylPreviewPanel(QWidget):
    def __init__(self, title: str = "Preview", parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            "color:#484f58;font-size:11px;font-weight:600;"
        )
        lay.addWidget(self.title_label)

        self.preview = VinylPreviewWidget()
        lay.addWidget(self.preview)

    def load_fhv(self, path: Path | str) -> bool:
        return self.preview.load_fhv(path)

    def clear(self) -> None:
        self.preview.clear()

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)
