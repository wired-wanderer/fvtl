"""
generate_tab.py — FH6 Vinyl Tool: Generateタブ

forza-painter-geometrize-linux バイナリを呼び出して画像からvinyl形状を
自動生成し、出力されたshapes形式JSONを自動でfhv化する。

出力先: <vinylフォルダ>/generate/<画像ファイル名>_<レイヤー数>/
  ├─ <画像ファイル名>_<レイヤー数>.fhv
  └─ <画像ファイル名>_<レイヤー数>.png   （透過プレビュー）

Importタブの「Generate」フォルダから即座に拾えるよう、
vinylフォルダ配下に出力する。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QPixmap, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QSplitter, QSizePolicy, QFileDialog,
)

from serializer import FhvSerializer
from vinyl_renderer import render_vinyl_to_file
from vinyl_preview import VinylPreviewPanel

SUPPORTED_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif")

BASE_DIR       = Path(__file__).parent
GEOMETRIZE_BIN = BASE_DIR / "bin" / "forza-painter-geometrize-linux"
SETTINGS_DIR   = GEOMETRIZE_BIN.parent / "settings"

PROGRESS_RE = re.compile(r"^\[(\d+)/(\d+)\]\s*(.*)$")


# ---------------------------------------------------------------------------
# プロファイルiniのstopAt上書き
# ---------------------------------------------------------------------------

def build_override_settings(profile: str, stop_at: int, work_dir: Path) -> Path:
    """
    選択中のプロファイルiniをコピーし、stopAt行だけ上書きした
    一時settingsファイルを作成して、そのパスを返す。
    """
    if profile:
        src = SETTINGS_DIR / f"{profile}.ini"
    else:
        src = SETTINGS_DIR / "_default.ini"

    lines: list[str] = []
    if src.exists():
        lines = src.read_text(encoding="utf-8").splitlines()

    replaced = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("stopAt") and "=" in stripped:
            new_lines.append(f"stopAt = {stop_at}")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f"stopAt = {stop_at}")

    save_at_idx = next((i for i, l in enumerate(new_lines) if l.strip().startswith("saveAt")), None)
    if save_at_idx is not None:
        save_line = new_lines[save_at_idx]
        _, _, values = save_line.partition("=")
        existing = [v.strip() for v in values.split(",") if v.strip()]
        if str(stop_at) not in existing:
            existing.append(str(stop_at))
            new_lines[save_at_idx] = "saveAt = " + ",".join(existing)

    work_dir.mkdir(parents=True, exist_ok=True)
    out_path = work_dir / "_override.ini"
    out_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# 目標レイヤー数呼び出し
# ---------------------------------------------------------------------------

def read_stop_at(profile: str) -> int | None:
    """
    プロファイルiniから stopAt の値だけを読み取る。
    見つからなければ None を返す。
    """
    if profile:
        src = SETTINGS_DIR / f"{profile}.ini"
    else:
        src = SETTINGS_DIR / "_default.ini"

    if not src.exists():
        return None

    for line in src.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("stopAt") and "=" in stripped:
            _, _, value = stripped.partition("=")
            try:
                return int(value.strip())
            except ValueError:
                return None
    return None


# ---------------------------------------------------------------------------
# 画像ドロップ受付プレビュー
# ---------------------------------------------------------------------------

class ImageDropZone(QLabel):
    fileDropped = pyqtSignal(Path)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(240, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._idle()

    def _idle(self) -> None:
        self.setStyleSheet(
            "QLabel { border: 2px dashed #30363d; border-radius: 8px; "
            "color: #484f58; background: #0d1117; font-size: 12px; }"
        )

    def _active(self) -> None:
        self.setStyleSheet(
            "QLabel { border: 2px dashed #1f6feb; border-radius: 8px; "
            "color: #58a6ff; background: #0d1117; font-size: 12px; }"
        )

    def set_hint(self, text: str) -> None:
        self.setText(text)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            path = Path(event.mimeData().urls()[0].toLocalFile())
            if path.suffix.lower() in SUPPORTED_EXTS:
                self._active()
                event.acceptProposedAction()
                return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._idle()

    def dropEvent(self, event: QDropEvent) -> None:
        self._idle()
        urls = event.mimeData().urls()
        if not urls:
            return
        path = Path(urls[0].toLocalFile())
        if path.suffix.lower() not in SUPPORTED_EXTS:
            return
        self.show_image(path)
        self.fileDropped.emit(path)

    def show_image(self, path: Path) -> None:
        pm = QPixmap(str(path))
        if pm.isNull():
            return
        scaled = pm.scaled(
            max(1, self.width() - 16), max(1, self.height() - 16),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)


# ---------------------------------------------------------------------------
# GenerateSignals / GenerateWorker
# ---------------------------------------------------------------------------

class GenerateSignals(QObject):
    log      = pyqtSignal(str, str)          # message, level
    progress = pyqtSignal(int, int, str)     # step, total, message
    done     = pyqtSignal(bool, dict)        # (success, result_dict)


class GenerateWorker(QThread):
    def __init__(
        self,
        signals: GenerateSignals,
        image_path: Path,
        out_root: Path,
        profile: str,
        backend: str,
        stop_at: int,          # ← 追加
    ) -> None:
        super().__init__()
        self.signals    = signals
        self.image_path = image_path
        self.out_root   = out_root   # <vinylフォルダ>/generate
        self.profile    = profile
        self.backend    = backend
        self.stop_at    = stop_at   # ← 追加
        self._proc: subprocess.Popen | None = None

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def run(self) -> None:
        try:
            from gui import I18n
            t = I18n.t

            if not GEOMETRIZE_BIN.exists():
                self.signals.log.emit(t("log_gen_bin_missing", path=str(GEOMETRIZE_BIN)), "error")
                self.signals.done.emit(False, {})
                return

            self.signals.log.emit(t("log_gen_start", name=self.image_path.name), "info")

            work_dir = self.out_root / "_tmp"
            work_dir.mkdir(parents=True, exist_ok=True)
            stem = self.image_path.stem
            tmp_base = work_dir / stem

            settings_path = build_override_settings(self.profile, self.stop_at, work_dir)

            cmd = [
                str(GEOMETRIZE_BIN), "--backend", self.backend,
                "--settings", str(settings_path),
                "--output", str(tmp_base),
            ]
            cmd.append(str(self.image_path))

            self._proc = subprocess.Popen(
                cmd, cwd=str(GEOMETRIZE_BIN.parent),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )

            for line in self._proc.stdout:  # type: ignore[union-attr]
                line = line.rstrip()
                if not line:
                    continue
                m = PROGRESS_RE.match(line)
                if m:
                    step, total, msg = int(m.group(1)), int(m.group(2)), m.group(3)
                    self.signals.progress.emit(step, total, msg)
                else:
                    self.signals.log.emit(line, "info")

            ret = self._proc.wait()
            if ret != 0:
                self.signals.log.emit(t("log_gen_failed", code=ret), "error")
                self.signals.done.emit(False, {})
                return

            shapes_json = tmp_base.with_suffix(".json")
            if not shapes_json.exists():
                self.signals.log.emit(t("log_gen_failed", code="no_output"), "error")
                self.signals.done.emit(False, {})
                return

            self.signals.log.emit(t("log_gen_converting"), "info")
            vinyl = FhvSerializer.load_any(shapes_json)
            layer_count = len(vinyl.layers)

            out_dir = self.out_root / f"{stem}_{layer_count}"
            out_dir.mkdir(parents=True, exist_ok=True)
            fhv_path = out_dir / f"{stem}_{layer_count}.fhv"
            png_path = out_dir / f"{stem}_{layer_count}.png"

            FhvSerializer.save(vinyl, fhv_path)
            render_vinyl_to_file(
                [l.to_dict() for l in vinyl.layers],
                png_path, output_size=1024, background=(0, 0, 0, 0),
            )

            self.signals.log.emit(t("log_gen_saved", path=str(out_dir)), "success")
            self.signals.done.emit(True, {
                "fhv": fhv_path, "png": png_path,
                "layer_count": layer_count, "out_dir": out_dir,
            })

        except Exception as e:
            self.signals.log.emit(t("log_error", e=e), "error")
            self.signals.done.emit(False, {})


# ---------------------------------------------------------------------------
# GenerateTab
# ---------------------------------------------------------------------------

class GenerateTab(QWidget):
    def __init__(self, log, win) -> None:
        super().__init__()
        self.log    = log
        self.win    = win
        self.worker: GenerateWorker | None = None
        self._image_path: Path | None = None
        self._build()

    def _build(self) -> None:
        from gui import I18n, btn_style, section_label, divider  # 既存ヘルパー流用

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background:#21262d; width:1px; }")
        outer.addWidget(splitter)

        # --- 左ペイン: ドロップゾーン + 設定 + 実行 ---
        left = QWidget()
        lay  = QVBoxLayout(left)
        lay.setContentsMargins(24, 20, 16, 24)
        lay.setSpacing(12)

        self.desc = QLabel(I18n.t("gen_desc"))
        self.desc.setStyleSheet("color:#8b949e;font-size:13px;")
        self.desc.setWordWrap(True)
        lay.addWidget(self.desc)

        self.drop_zone = ImageDropZone()
        self.drop_zone.set_hint(I18n.t("gen_drop_hint"))
        self.drop_zone.fileDropped.connect(self._on_image_dropped)
        lay.addWidget(self.drop_zone, 1)

        self.browse_btn = QPushButton(I18n.t("gen_browse"))
        self.browse_btn.setStyleSheet(btn_style())
        self.browse_btn.clicked.connect(self._browse_image)
        lay.addWidget(self.browse_btn)

        lay.addWidget(divider())

        self.profile_label = section_label(I18n.t("gen_profile"))
        lay.addWidget(self.profile_label)
        self.profile_combo = QComboBox()
        self._reload_profiles()
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)  # ← 追加
        lay.addWidget(self.profile_combo)

        self.stop_at_label = section_label(I18n.t("gen_stop_at"))
        lay.addWidget(self.stop_at_label)
        self.stop_at_spin = QSpinBox()
        self.stop_at_spin.setRange(10, 3000)
        self.stop_at_spin.setValue(2500)
        self.stop_at_spin.setSingleStep(100)
        lay.addWidget(self.stop_at_spin)

        self.backend_label = section_label(I18n.t("gen_backend"))
        lay.addWidget(self.backend_label)
        self.backend_combo = QComboBox()
        self.backend_combo.addItems(["opencl", "vulkan"])
        lay.addWidget(self.backend_combo)

        lay.addStretch()

        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet("color:#58a6ff;font-size:11px;")
        self.progress_label.setWordWrap(True)
        lay.addWidget(self.progress_label)

        self.run_btn = QPushButton(I18n.t("gen_run"))
        self.run_btn.setFixedHeight(48)
        self.run_btn.setStyleSheet(btn_style("#238636", "#2ea043", "#fff", 15, True))
        self.run_btn.setEnabled(False)
        self.run_btn.clicked.connect(self._on_run_clicked)
        lay.addWidget(self.run_btn)

        splitter.addWidget(left)

        # --- 右ペイン: 生成結果プレビュー ---
        right = QWidget()
        rlay  = QVBoxLayout(right)
        rlay.setContentsMargins(16, 20, 24, 24)
        rlay.setSpacing(6)

        self.result_preview = VinylPreviewPanel(I18n.t("preview_label"))
        rlay.addWidget(self.result_preview)

        splitter.addWidget(right)
        splitter.setSizes([300, 300])

        self._on_profile_changed()   # ← 追加：全ウィジェット作成後に初期値を反映

    # ------------------------------------------------------------------

    def _reload_profiles(self) -> None:
        from gui import I18n
        self.profile_combo.clear()
        self.profile_combo.addItem(I18n.t("gen_profile_default"), "")
        if SETTINGS_DIR.exists():
            for ini in sorted(SETTINGS_DIR.glob("*.ini")):
                if ini.stem == "_default":
                    continue
                self.profile_combo.addItem(ini.stem, ini.stem)

    def _on_profile_changed(self) -> None:
        profile = self.profile_combo.currentData()
        stop_at = read_stop_at(profile)
        if stop_at is not None:
            clamped = max(self.stop_at_spin.minimum(), min(self.stop_at_spin.maximum(), stop_at))
            self.stop_at_spin.setValue(clamped)                

    def _browse_image(self) -> None:
        exts = " ".join(f"*{e}" for e in SUPPORTED_EXTS)
        path, _ = QFileDialog.getOpenFileName(self, "", "", f"Images ({exts})")
        if path:
            p = Path(path)
            self.drop_zone.show_image(p)
            self._on_image_dropped(p)

    def _on_image_dropped(self, path: Path) -> None:
        self._image_path = path
        self.run_btn.setEnabled(True)

    def _on_run_clicked(self) -> None:
        from gui import I18n, get_sub_dir

        if not self._image_path:
            return

        self.run_btn.setEnabled(False)
        self.run_btn.setText(I18n.t("gen_running"))
        self.progress_label.setText("")

        signals = GenerateSignals()
        signals.log.connect(self.log.append_log)
        signals.progress.connect(self._on_progress)
        signals.done.connect(self._on_done)

        out_root = get_sub_dir("generate")   # <vinylフォルダ>/generate
        profile  = self.profile_combo.currentData()
        backend  = self.backend_combo.currentText()

        self.worker = GenerateWorker(
            signals, self._image_path, out_root, profile, backend,
            self.stop_at_spin.value(),   # ← 追加
        )
        self.worker.start()

    def _on_progress(self, step: int, total: int, msg: str) -> None:
        from gui import I18n
        self.progress_label.setText(I18n.t("gen_progress", step=step, total=total, msg=msg))

    def _on_done(self, ok: bool, result: dict) -> None:
        from gui import I18n
        self.run_btn.setEnabled(True)
        self.run_btn.setText(I18n.t("gen_run"))
        if ok and result:
            self.progress_label.setText(I18n.t("gen_done", n=result["layer_count"]))
            self.result_preview.load_png(result["png"])

    def retranslate(self) -> None:
        from gui import I18n
        self.desc.setText(I18n.t("gen_desc"))
        self.drop_zone.set_hint(I18n.t("gen_drop_hint"))
        self.browse_btn.setText(I18n.t("gen_browse"))
        self.profile_label.setText(I18n.t("gen_profile"))
        self.stop_at_label.setText(I18n.t("gen_stop_at"))
        self.backend_label.setText(I18n.t("gen_backend"))
        self.run_btn.setText(I18n.t("gen_run"))
        self.result_preview.set_title(I18n.t("preview_label"))
        self._reload_profiles()