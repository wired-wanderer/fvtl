"""
vinyl_preview.py — FH6 ビニールプレビューウィジェット v6

vinyl_renderer.py でPNGを生成し、それを表示するだけのシンプルな構成。
SVGマスク方式は廃止し、JSON頂点メッシュの直接ラスタライズに統一。
"""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt, QSize
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QBrush
from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from vinyl_renderer import render_vinyl


def _pil_to_qpixmap(pil_img) -> QPixmap:
    """PIL.Image(RGBA) → QPixmap 変換"""
    data = pil_img.convert("RGBA").tobytes("raw", "RGBA")
    qimg = QImage(data, pil_img.width, pil_img.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


class VinylPreviewWidget(QWidget):
    # クラス変数としてキャッシュ（毎フレーム作り直さない）
    _checker_brush: QBrush | None = None

    @classmethod
    def _get_checker_brush(cls, cell: int = 8) -> QBrush:
        if cls._checker_brush is not None:
            return cls._checker_brush

        tile = QPixmap(QSize(cell * 2, cell * 2))
        tile.fill(QColor("#ffffff"))
        p = QPainter(tile)
        p.fillRect(0, 0, cell, cell, QColor("#cccccc"))
        p.fillRect(cell, cell, cell, cell, QColor("#cccccc"))
        p.end()

        brush = QBrush(tile)
        cls._checker_brush = brush
        return brush
    
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._loaded  = False
        self._label   = ""
        self._error   = ""

        self.setMinimumSize(200, 140)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.setAutoFillBackground(True)
        p = self.palette()
        p.setColor(self.backgroundRole(), QColor("#0d1117"))
        self.setPalette(p)

    def load_fhv(self, path: Path | str) -> bool:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            layers = data.get("layers", [])

            img = render_vinyl(layers, output_size=1024)
            if img is None:
                self._error = "描画対象がありません"
                self.clear()
                return False

            self._pixmap = _pil_to_qpixmap(img)
            self._loaded = True
            self._label  = Path(path).name
            self._error  = ""
            self.update()
            return True

        except Exception as e:
            self._error = str(e)
            self.clear()
            return False

    def load_png(self, path: Path | str) -> bool:
        """
        事前生成済みのPNGを直接読み込む。
        Export時に同時生成されたプレビュー画像を使うことで
        毎回の再レンダリングを避け、表示を高速化する。
        """
        try:
            pm = QPixmap(str(path))
            if pm.isNull():
                self._error = "PNG読み込み失敗"
                self.clear()
                return False

            self._pixmap = pm
            self._loaded = True
            # ラベルは元のfhv名を表示したいので拡張子前の名前のみ
            self._label  = Path(path).stem
            self._error  = ""
            self.update()
            return True

        except Exception as e:
            self._error = str(e)
            self.clear()
            return False

    def clear(self) -> None:
        self._pixmap = None
        self._loaded = False
        self._label  = ""
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w = self.width()
        h = self.height()
        painter.fillRect(0, 0, w, h, QColor("#0d1117"))

        if not self._loaded or self._pixmap is None:
            painter.setPen(QPen(QColor("#30363d"), 1))
            painter.drawRect(1, 1, w - 2, h - 2)
            painter.setPen(QColor("#484f58"))
            msg = self._error if self._error else "No preview"
            painter.drawText(
                QRectF(8, 0, w - 16, h),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                msg,
            )
            return

        margin  = 12
        label_h = 18
        avail_w = w - margin * 2
        avail_h = h - margin * 2 - label_h

        pm = self._pixmap
        aspect = pm.width() / pm.height()

        if avail_w / avail_h > aspect:
            draw_h = avail_h
            draw_w = draw_h * aspect
        else:
            draw_w = avail_w
            draw_h = draw_w / aspect

        off_x = (w - draw_w) / 2.0
        off_y = margin + (avail_h - draw_h) / 2.0

        # 白背景の枠
        painter.setPen(QPen(QColor("#cccccc"), 1))
        painter.setBrush(self._get_checker_brush())
        painter.drawRect(QRectF(off_x, off_y, draw_w, draw_h))

        target = QRectF(off_x, off_y, draw_w, draw_h)
        painter.drawPixmap(target, pm, QRectF(0, 0, pm.width(), pm.height()))

        painter.setPen(QColor("#484f58"))
        painter.drawText(
            QRectF(off_x, off_y + draw_h + 2, draw_w, label_h),
            Qt.AlignmentFlag.AlignCenter,
            self._label,
        )


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

    def load_png(self, path: Path | str) -> bool:
        return self.preview.load_png(path)

    def clear(self) -> None:
        self.preview.clear()

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)
