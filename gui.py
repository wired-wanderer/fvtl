"""
gui.py — FH6 Vinyl Tool GUI v3
プレビュー機能付き
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QSettings
from PyQt6.QtGui import QColor, QFont, QIntValidator, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QFileDialog, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QProgressBar, QPushButton,
    QSizePolicy, QTabWidget, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget, QComboBox, QFrame, QSplitter,
)

from generate_tab import GenerateTab

from vinyl_preview import VinylPreviewPanel

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------

STRINGS: dict[str, dict[str, str]] = {
    "ja": {
        "app_title":            "FH6 Vinyl Tool",
        "tab_export":           "⬆  Export",
        "tab_import":           "⬇  Import",
        "tab_settings":         "⚙  設定",
        "tab_generate":         "🖼  Generate",
        "gen_desc":             "画像をドラッグ&ドロップするか選択してください。",
        "gen_drop_hint":        "ここに画像をドラッグ&ドロップ\n(PNG / JPG / BMP / WEBP / GIF)",
        "gen_browse":           "画像を選択...",
        "gen_profile":          "プロファイル",
        "gen_profile_default":  "(デフォルト)",
        "gen_stop_at":          "目標レイヤー数",
        "gen_backend":          "Backend",
        "gen_run":              "生成開始",
        "gen_running":          "生成中...",
        "gen_progress":         "[{step}/{total}] {msg}",
        "gen_done":             "完了: {n} レイヤー",
        "log_gen_start":        "生成開始: {name}",
        "log_gen_bin_missing":  "geometrizeバイナリが見つかりません: {path}",
        "log_gen_converting":   "shapes形式JSONをfhvに変換中...",
        "log_gen_saved":        "保存先: {path}",
        "log_gen_failed":       "生成失敗 (code={code})",        
        "export_desc":          "ゲーム内でビニールエディタを開いた状態でエクスポートしてください。",
        "filename_label":       "ファイル名（省略時: 年月日時分秒.fhv）",
        "filename_hint":        "例: my_vinyl  →  my_vinyl.fhv",
        "btn_export":           "⬆  Export",
        "exporting":            "エクスポート中...",
        "preview_label":        "プレビュー",
        "preview_export":       "Exportするとプレビューが表示されます",
        "preview_select":       "ファイルを選択するとプレビューが表示されます",
        "import_desc":          "ゲーム内でビニールエディタを開き、指定レイヤー数を用意してからインポートしてください。",
        "btn_refresh":          "↺ 更新",
        "col_filename":         "ファイル名",
        "col_layers":           "レイヤー数",
        "no_files":             "（ファイルがありません）",
        "layer_hint_none":      "ファイルを選択するとレイヤー数が表示されます。",
        "layer_hint":           "FH6内のビニールエディタにシンプルサークルを {n} 個配置してください。",
        "btn_import":           "⬇  Import",
        "importing":            "インポート中...",
        "folder_output":        "Output",
        "folder_generate":      "Generate",
        "folder_editor":        "Editor",
        "settings_language":    "言語 / Language",
        "settings_outdir":      "vinyl フォルダ",
        "btn_browse":           "参照...",
        "settings_calibration": "オフセット キャリブレーション",
        "calib_desc":           "FH6のアップデートでツールが動かなくなった場合、ここでオフセットを再検出できます。読み取り専用で、ゲームへの書き込みは行いません。",
        "calib_prepare":        "FH6内のバイナルエディターに2000〜3000枚のバイナル表示させておいてください。",
        "calib_count_label":    "正確なレイヤー枚数（分かる場合。任意・2000〜3000）",
        "calib_count_hint":     "例: 2500（空欄でも可、分かる場合は入力すると高速化します）",
        "calib_btn":            "キャリブレーション実行",
        "calib_running":        "キャリブレーション実行中...",
        "calib_invalid_count":  "レイヤー枚数は2000〜3000の範囲で入力してください（空欄も可）。",
        "calib_already_running":"キャリブレーションは既に実行中です。",
        "calib_not_found":      "calibrator.py が見つかりません: {path}",
        "calib_start":          "キャリブレーションを開始します...",
        "calib_progress_fmt":   "スキャン中... {scanned}/{total} MB（候補 {n} 件）",
        "calib_success":        "キャリブレーション完了。結果を保存しました: {path}",
        "calib_failed":         "キャリブレーション失敗 (code={code})",
        "calib_failed_generic": "キャリブレーションに失敗しました。ログを確認してください。",
        "log_label":            "ログ",
        "btn_clear_log":        "ログをクリア",
        "log_startup":          "FH6 Vinyl Tool 起動",
        "log_open_editor":      "ビニールエディタを開いてから操作してください",
        "log_export_start":     "エクスポート開始",
        "log_connecting":       "FH6プロセスに接続中...",
        "log_group_found":      "CLiveryGroup発見: {n} レイヤー",
        "log_group_notfound":   "CLiveryGroupが見つかりません。ビニールエディタを開いてください。",
        "log_saved":            "保存完了: {path}",
        "log_png_saved":        "プレビュー画像を生成: {path}",
        "log_png_failed":       "プレビュー画像の生成に失敗しました",
        "log_import_start":     "インポート開始: {name}",
        "log_loaded":           "{n} レイヤーを読み込みました",
        "log_layer_mismatch":   "レイヤー数不一致: ファイル={f} / メモリ={m}",
        "log_layer_guide":      "ゲーム内のレイヤー数をファイルと同じ枚数にしてください。",
        "log_written":          "{n} レイヤーを書き込みました",
        "log_error":            "エラー: {e}",
    },
    "en": {
        "app_title":            "FH6 Vinyl Tool",
        "tab_export":           "⬆  Export",
        "tab_import":           "⬇  Import",
        "tab_settings":         "⚙  Settings",
        "tab_generate":         "🖼  Generate",
        "gen_desc":             "Drag & drop an image, or select one.",
        "gen_drop_hint":        "Drag & drop an image here\n(PNG / JPG / BMP / WEBP / GIF)",
        "gen_browse":           "Select image...",
        "gen_profile":          "Profile",
        "gen_profile_default":  "(Default)",
        "gen_stop_at":          "Target layer count",
        "gen_backend":          "Backend",
        "gen_run":              "Start generating",
        "gen_running":          "Generating...",
        "gen_progress":         "[{step}/{total}] {msg}",
        "gen_done":             "Done: {n} layers",
        "log_gen_start":        "Generation started: {name}",
        "log_gen_bin_missing":  "geometrize binary not found: {path}",
        "log_gen_converting":   "Converting shapes JSON to fhv...",
        "log_gen_saved":        "Saved to: {path}",
        "log_gen_failed":       "Generation failed (code={code})",        
        "export_desc":          "Open the vinyl editor in-game before exporting.",
        "filename_label":       "File name (default: YYYYMMDDHHmmss.fhv)",
        "filename_hint":        "e.g. my_vinyl  →  my_vinyl.fhv",
        "btn_export":           "⬆  Export",
        "exporting":            "Exporting...",
        "preview_label":        "Preview",
        "preview_export":       "Preview will appear after export.",
        "preview_select":       "Select a file to see the preview.",
        "import_desc":          "Open the vinyl editor in-game and prepare the required layers before importing.",
        "btn_refresh":          "↺ Refresh",
        "col_filename":         "File name",
        "col_layers":           "Layers",
        "no_files":             "(No files found)",
        "layer_hint_none":      "Select a file to see the layer count.",
        "layer_hint":           "Place {n} simple circles in the FH6 vinyl editor.",
        "btn_import":           "⬇  Import",
        "importing":            "Importing...",
        "folder_output":        "Output",
        "folder_generate":      "Generate",
        "folder_editor":        "Editor",
        "settings_language":    "Language / 言語",
        "settings_outdir":      "Vinyl folder",
        "btn_browse":           "Browse...",
        "settings_calibration": "Offset Calibration",
        "calib_desc":           "If the tool stops working after an FH6 update, you can re-detect the offsets here. Read-only — nothing is written to the game.",
        "calib_prepare":        "Please display about 2000-3000 vinyls in the FH6 vinyl editor.",
        "calib_count_label":    "Exact layer count (optional, 2000-3000)",
        "calib_count_hint":     "e.g. 2500 (leave blank if unknown; entering it speeds things up)",
        "calib_btn":            "Run calibration",
        "calib_running":        "Calibrating...",
        "calib_invalid_count":  "Enter a layer count between 2000 and 3000 (or leave it blank).",
        "calib_already_running":"Calibration is already running.",
        "calib_not_found":      "calibrator.py not found: {path}",
        "calib_start":          "Starting calibration...",
        "calib_progress_fmt":   "Scanning... {scanned}/{total} MB ({n} candidates)",
        "calib_success":        "Calibration complete. Result saved: {path}",
        "calib_failed":         "Calibration failed (code={code})",
        "calib_failed_generic": "Calibration failed. Check the log for details.",
        "log_label":            "Log",
        "btn_clear_log":        "Clear log",
        "log_startup":          "FH6 Vinyl Tool started",
        "log_open_editor":      "Please open the vinyl editor before operating.",
        "log_export_start":     "Export started",
        "log_connecting":       "Connecting to FH6 process...",
        "log_group_found":      "CLiveryGroup found: {n} layers",
        "log_group_notfound":   "CLiveryGroup not found. Please open the vinyl editor.",
        "log_saved":            "Saved: {path}",
        "log_png_saved":        "Preview image generated: {path}",
        "log_png_failed":       "Failed to generate preview image",
        "log_import_start":     "Import started: {name}",
        "log_loaded":           "Loaded {n} layers",
        "log_layer_mismatch":   "Layer count mismatch: file={f} / memory={m}",
        "log_layer_guide":      "Please set the in-game layer count to match the file.",
        "log_written":          "Written {n} layers",
        "log_error":            "Error: {e}",
    },
}


class I18n:
    _lang: str = "ja"

    @classmethod
    def set(cls, lang: str) -> None:
        cls._lang = lang if lang in STRINGS else "ja"

    @classmethod
    def t(cls, key: str, **kw) -> str:
        s = STRINGS[cls._lang].get(key, key)
        return s.format(**kw) if kw else s


class AppSettings:
    _s = QSettings("fh6vinyl", "FH6VinylTool")

    @classmethod
    def get(cls, key, default=None):
        return cls._s.value(key, default)

    @classmethod
    def set(cls, key, value) -> None:
        cls._s.setValue(key, value)
        cls._s.sync()


BASE_DIR = Path(__file__).parent

def get_vinyl_dir() -> Path:
    return Path(AppSettings.get("vinyl_dir", str(BASE_DIR / "vinyl")))

def get_sub_dir(sub: str) -> Path:
    p = get_vinyl_dir() / sub
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------

class WorkerSignals(QObject):
    log      = pyqtSignal(str, str)
    done     = pyqtSignal(bool, str)   # (success, saved_path)
    progress = pyqtSignal(int, int, int)   # (scanned_mb, total_mb, candidates) -1,-1,-1 = 不明(indeterminate)


class ExportWorker(QThread):
    def __init__(self, signals: WorkerSignals, out_dir: Path, stem: str) -> None:
        super().__init__()
        self.signals = signals
        self.out_dir = out_dir   # vinyl/output/<stem>/ フォルダ
        self.stem    = stem

    def run(self) -> None:
        try:
            from vinyl_manager import VinylManager
            from memory_io import ProcessMemory
            from process_scanner import ProcessScanner
            from serializer import MemoryReader, FhvSerializer
            from vinyl_renderer import render_vinyl_to_file

            mgr = VinylManager(verbose=False)
            self.signals.log.emit(I18n.t("log_connecting"), "info")

            with ProcessMemory(mgr.pid) as pm:
                scanner = ProcessScanner(verbose=False)
                result  = scanner.scan(pm)
                if not result.groups:
                    self.signals.log.emit(I18n.t("log_group_notfound"), "error")
                    self.signals.done.emit(False, "")
                    return
                group = result.groups[0]
                self.signals.log.emit(I18n.t("log_group_found", n=group.layer_count), "info")
                reader = MemoryReader(pm)
                vinyl  = reader.to_vinyl_file(group)

            # <vinyl_dir>/output/<stem>/ フォルダを作成
            self.out_dir.mkdir(parents=True, exist_ok=True)
            fhv_path = self.out_dir / f"{self.stem}.fhv"
            png_path = self.out_dir / f"{self.stem}.png"

            FhvSerializer.save(vinyl, fhv_path)
            self.signals.log.emit(I18n.t("log_saved", path=fhv_path.name), "success")

            # プレビューPNGを同時生成
            ok = render_vinyl_to_file(
                [l.to_dict() for l in vinyl.layers],
                png_path,
                output_size=1024,
            )
            if ok:
                self.signals.log.emit(I18n.t("log_png_saved", path=png_path.name), "success")
            else:
                self.signals.log.emit(I18n.t("log_png_failed"), "error")

            self.signals.done.emit(True, str(fhv_path))

        except Exception as e:
            self.signals.log.emit(I18n.t("log_error", e=e), "error")
            self.signals.done.emit(False, "")


class ImportWorker(QThread):
    def __init__(self, signals: WorkerSignals, fhv_path: Path) -> None:
        super().__init__()
        self.signals  = signals
        self.fhv_path = fhv_path

    def run(self) -> None:
        try:
            from vinyl_manager import VinylManager
            from memory_io import ProcessMemory
            from process_scanner import ProcessScanner
            from serializer import FhvSerializer, MemoryWriter

            mgr = VinylManager(verbose=False)
            self.signals.log.emit(I18n.t("log_import_start", name=self.fhv_path.name), "info")

            vinyl = FhvSerializer.load_any(self.fhv_path)   # ← load → load_any
            self.signals.log.emit(I18n.t("log_loaded", n=len(vinyl.layers)), "info")
            self.signals.log.emit(I18n.t("log_connecting"), "info")

            with ProcessMemory(mgr.pid) as pm:
                scanner = ProcessScanner(verbose=False)
                result  = scanner.scan(pm)
                if not result.groups:
                    self.signals.log.emit(I18n.t("log_group_notfound"), "error")
                    self.signals.done.emit(False, "")
                    return

                matched = [g for g in result.groups if g.layer_count == len(vinyl.layers)]
                group   = matched[0] if matched else result.groups[0]

                if group.layer_count != len(vinyl.layers):
                    self.signals.log.emit(
                        I18n.t("log_layer_mismatch", f=len(vinyl.layers), m=group.layer_count), "error")
                    self.signals.log.emit(I18n.t("log_layer_guide"), "error")
                    self.signals.done.emit(False, "")
                    return

                self.signals.log.emit(I18n.t("log_group_found", n=group.layer_count), "info")
                writer = MemoryWriter(pm)
                count  = writer.write_all_layers(vinyl.layers, group)

            self.signals.log.emit(I18n.t("log_written", n=count), "success")
            self.signals.done.emit(True, "")

        except Exception as e:
            self.signals.log.emit(I18n.t("log_error", e=e), "error")
            self.signals.done.emit(False, "")


class CalibrationWorker(QThread):
    """
    calibrator.py auto をサブプロセスとして実行するワーカー。
    - 読み取り専用（calibrator.py自体がゲームへの書き込みを行わない）
    - calibrator.py の対話プロンプト（Enter確認 / 任意のレイヤー枚数）には
      起動直後にstdinへまとめて書き込むことで応答する
    """

    def __init__(self, signals: WorkerSignals, exact_count: int | None) -> None:
        super().__init__()
        self.signals     = signals
        self.exact_count = exact_count
        self.proc: subprocess.Popen | None = None

    def run(self) -> None:
        script = BASE_DIR / "calibrator.py"
        if not script.exists():
            self.signals.log.emit(I18n.t("calib_not_found", path=str(script)), "error")
            self.signals.done.emit(False, "")
            return

        lang_flag = "-jp" if I18n._lang == "ja" else "-en"
        cmd = [sys.executable, str(script), "auto", lang_flag]

        try:
            self.proc = subprocess.Popen(
                cmd,
                cwd=str(BASE_DIR),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as e:
            self.signals.log.emit(I18n.t("log_error", e=e), "error")
            self.signals.done.emit(False, "")
            return

        # calibrator.py 側の入力待ち順序:
        #   1. input(auto_ready_prompt)          → 準備OKのEnter
        #   2. prompt_optional_exact_count()     → 正確なレイヤー枚数（空欄可）
        # パイプはバッファされるので、起動直後にまとめて書き込んでおけばよい。
        count_line = str(self.exact_count) if self.exact_count else ""
        try:
            assert self.proc.stdin is not None
            self.proc.stdin.write("\n")
            self.proc.stdin.write(f"{count_line}\n")
            self.proc.stdin.flush()
            self.proc.stdin.close()
        except Exception:
            pass

        # calibrator.py の "スキャン中... 123/456 MB, 候補=2" 形式の行を検出する。
        # このパターンに一致する行は大量に流れるため、ログには出さずプログレスバーへ変換する。
        # 例(ja): "[12:34:56]   スキャン中... 123/456 MB, 候補=2"
        # 例(en): "[12:34:56]   Scanning... 123/456 MB, candidates=2"
        progress_re = re.compile(r"(\d+)\s*/\s*(\d+)\s*MB.*?[=＝]\s*(\d+)")

        try:
            assert self.proc.stdout is not None
            for raw_line in self.proc.stdout:
                line = raw_line.rstrip("\n").rstrip("\r")
                if not line:
                    continue
                m = progress_re.search(line)
                if m:
                    scanned, total, n = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    self.signals.progress.emit(scanned, total, n)
                    continue
                self.signals.log.emit(f"[calibrator] {line}", "info")
        except Exception as e:
            self.signals.log.emit(I18n.t("log_error", e=e), "error")

        code = self.proc.wait()

        if code == 0:
            saved_path = self._find_latest_result()
            self.signals.done.emit(True, saved_path)
        else:
            self.signals.log.emit(I18n.t("calib_failed", code=code), "error")
            self.signals.done.emit(False, "")

    def _find_latest_result(self) -> str:
        """calibrator.py の RESULTS_DIR (= <calibrator.py>/results) から最新結果を探す"""
        results_dir = BASE_DIR / "results"
        files = sorted(results_dir.glob("*_result.json"),
                        key=lambda p: p.name, reverse=True)
        return str(files[0]) if files else ""

    def cancel(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


# ---------------------------------------------------------------------------
# LogWidget
# ---------------------------------------------------------------------------

class LogWidget(QTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setFont(QFont("Noto Sans Mono CJK JP, monospace", 11))
        self.setStyleSheet("""
            QTextEdit {
                background: #0d1117; color: #c9d1d9;
                border: 1px solid #21262d; border-radius: 6px; padding: 8px;
            }
        """)

    def append_log(self, msg: str, level: str = "info") -> None:
        colors   = {"info": "#8b949e", "success": "#3fb950", "error": "#f85149"}
        prefixes = {"info": "  ",      "success": "✓ ",      "error": "✗ "}
        color    = colors.get(level, "#c9d1d9")
        prefix   = prefixes.get(level, "  ")
        ts       = datetime.now().strftime("%H:%M:%S")

        cur = self.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#484f58"))
        cur.setCharFormat(fmt)
        cur.insertText(f"[{ts}] ")
        fmt.setForeground(QColor(color))
        cur.setCharFormat(fmt)
        cur.insertText(f"{prefix}{msg}\n")
        self.setTextCursor(cur)
        self.ensureCursorVisible()

    def clear_log(self) -> None:
        self.clear()


# ---------------------------------------------------------------------------
# スタイルヘルパー
# ---------------------------------------------------------------------------

def btn_style(bg="#21262d", hover="#30363d", color="#c9d1d9", size=13, bold=False) -> str:
    w = "700" if bold else "400"
    return f"""
        QPushButton {{
            background:{bg}; color:{color};
            border:1px solid #30363d; border-radius:6px;
            font-size:{size}px; font-weight:{w}; padding:4px 14px;
        }}
        QPushButton:hover {{ background:{hover}; }}
        QPushButton:disabled {{ background:#161b22; color:#484f58; }}
    """

def section_label(text: str) -> QLabel:
    lb = QLabel(text)
    lb.setStyleSheet("color:#484f58;font-size:11px;font-weight:600;margin-top:4px;")
    return lb

def divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet("color:#21262d;")
    return f


# ---------------------------------------------------------------------------
# Export タブ
# ---------------------------------------------------------------------------

class ExportTab(QWidget):
    def __init__(self, log: LogWidget, win: "MainWindow") -> None:
        super().__init__()
        self.log    = log
        self.win    = win
        self.worker = None
        self._build()

    def _build(self) -> None:
        # 左右分割: 左=操作, 右=プレビュー
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background:#21262d; width:1px; }")
        outer.addWidget(splitter)

        # --- 左ペイン ---
        left = QWidget()
        lay  = QVBoxLayout(left)
        lay.setContentsMargins(24, 20, 16, 24)
        lay.setSpacing(12)

        self.desc = QLabel(I18n.t("export_desc"))
        self.desc.setStyleSheet("color:#8b949e;font-size:13px;")
        self.desc.setWordWrap(True)
        lay.addWidget(self.desc)

        lay.addWidget(divider())

        self.fn_label = section_label(I18n.t("filename_label"))
        lay.addWidget(self.fn_label)

        fn_row = QHBoxLayout()
        self.fn_edit = QLineEdit()
        self.fn_edit.setPlaceholderText(I18n.t("filename_hint"))
        self.fn_edit.setStyleSheet("""
            QLineEdit {
                background:#0d1117; color:#c9d1d9;
                border:1px solid #30363d; border-radius:6px;
                padding:6px 10px; font-size:13px;
            }
            QLineEdit:focus { border-color:#1f6feb; }
        """)
        fn_row.addWidget(self.fn_edit)
        fhv_lb = QLabel(".fhv")
        fhv_lb.setStyleSheet("color:#484f58;font-size:13px;")
        fn_row.addWidget(fhv_lb)
        lay.addLayout(fn_row)

        lay.addStretch()

        self.export_btn = QPushButton(I18n.t("btn_export"))
        self.export_btn.setFixedHeight(48)
        self.export_btn.setStyleSheet(btn_style("#238636","#2ea043","#fff",15,True))
        self.export_btn.clicked.connect(self._do_export)
        lay.addWidget(self.export_btn)

        splitter.addWidget(left)

        # --- 右ペイン（プレビュー）---
        right = QWidget()
        rlay  = QVBoxLayout(right)
        rlay.setContentsMargins(16, 20, 24, 24)
        rlay.setSpacing(6)

        self.preview_panel = VinylPreviewPanel(I18n.t("preview_label"))
        rlay.addWidget(self.preview_panel)

        splitter.addWidget(right)
        splitter.setSizes([260, 340])

    def retranslate(self) -> None:
        self.desc.setText(I18n.t("export_desc"))
        self.fn_label.setText(I18n.t("filename_label"))
        self.fn_edit.setPlaceholderText(I18n.t("filename_hint"))
        self.export_btn.setText(I18n.t("btn_export"))
        self.preview_panel.set_title(I18n.t("preview_label"))

    def _do_export(self) -> None:
        raw  = self.fn_edit.text().strip()
        stem = (raw.removesuffix(".fhv") if raw else
                datetime.now().strftime("%Y%m%d%H%M%S"))

        # vinyl/output/<stem>/ フォルダの中に <stem>.fhv と <stem>.png を保存
        out_dir = get_sub_dir("output") / stem

        self.export_btn.setEnabled(False)
        self.export_btn.setText(I18n.t("exporting"))
        self.log.append_log(I18n.t("log_export_start"), "info")

        signals = WorkerSignals()
        signals.log.connect(self.log.append_log)
        signals.done.connect(self._on_done)

        self.worker = ExportWorker(signals, out_dir, stem)
        self.worker.start()

    def _on_done(self, ok: bool, saved_path: str) -> None:
        self.export_btn.setEnabled(True)
        self.export_btn.setText(I18n.t("btn_export"))
        if ok and saved_path:
            # 同名のPNGを直接読み込む（再レンダリング不要で高速）
            png_path = Path(saved_path).with_suffix(".png")
            if png_path.exists():
                self.preview_panel.load_png(png_path)
            else:
                self.preview_panel.load_fhv(saved_path)
        self.win.import_tab.refresh_table()


# ---------------------------------------------------------------------------
# Import タブ
# ---------------------------------------------------------------------------

class ImportTab(QWidget):
    def __init__(self, log: LogWidget) -> None:
        super().__init__()
        self.log         = log
        self.worker      = None
        self.current_sub = "output"
        self._build()

    def _build(self) -> None:
        outer    = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background:#21262d; width:1px; }")
        outer.addWidget(splitter)

        # --- 左ペイン ---
        left = QWidget()
        lay  = QVBoxLayout(left)
        lay.setContentsMargins(24, 20, 16, 24)
        lay.setSpacing(10)

        self.desc = QLabel(I18n.t("import_desc"))
        self.desc.setStyleSheet("color:#8b949e;font-size:13px;")
        self.desc.setWordWrap(True)
        lay.addWidget(self.desc)

        lay.addWidget(divider())

        # フォルダ切り替えボタン
        folder_row = QHBoxLayout()
        folder_row.setSpacing(6)
        self.folder_btns: dict[str, QPushButton] = {}
        for sub, lk in zip(["output","generate","editor"],
                            ["folder_output","folder_generate","folder_editor"]):
            b = QPushButton(I18n.t(lk))
            b.setCheckable(True)
            b.setFixedHeight(30)
            b.clicked.connect(lambda _, s=sub: self._switch_folder(s))
            self.folder_btns[sub] = b
            folder_row.addWidget(b)
        self.folder_btns["output"].setChecked(True)
        self._update_folder_styles()
        lay.addLayout(folder_row)

        # テーブル
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([I18n.t("col_filename"), I18n.t("col_layers")])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 80)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("""
            QTableWidget {
                background:#0d1117; color:#c9d1d9;
                border:1px solid #21262d; border-radius:6px;
                gridline-color:#21262d; font-size:13px;
            }
            QTableWidget::item:selected { background:#1f6feb; color:#fff; }
            QTableWidget::item:hover:!selected { background:#161b22; }
            QHeaderView::section {
                background:#161b22; color:#8b949e;
                border:none; border-bottom:1px solid #21262d;
                padding:6px; font-size:12px;
            }
        """)
        self.table.itemSelectionChanged.connect(self._on_select)
        lay.addWidget(self.table, 1)

        ref_btn = QPushButton(I18n.t("btn_refresh"))
        ref_btn.setFixedHeight(26)
        ref_btn.setStyleSheet("QPushButton{background:transparent;color:#58a6ff;border:none;font-size:12px;}"
                              "QPushButton:hover{color:#79c0ff;}")
        ref_btn.clicked.connect(self.refresh_table)
        lay.addWidget(ref_btn, 0, Qt.AlignmentFlag.AlignRight)

        # レイヤーヒント
        self.hint = QLabel(I18n.t("layer_hint_none"))
        self.hint.setStyleSheet("""
            QLabel {
                background:#161b22; color:#e3b341;
                border:1px solid #bb8009; border-radius:6px;
                padding:10px 14px; font-size:13px;
            }
        """)
        self.hint.setWordWrap(True)
        self.hint.setVisible(False)
        lay.addWidget(self.hint)

        self.import_btn = QPushButton(I18n.t("btn_import"))
        self.import_btn.setFixedHeight(48)
        self.import_btn.setEnabled(False)
        self.import_btn.setStyleSheet(btn_style("#1f6feb","#388bfd","#fff",15,True))
        self.import_btn.clicked.connect(self._do_import)
        lay.addWidget(self.import_btn)

        splitter.addWidget(left)

        # --- 右ペイン（プレビュー）---
        right = QWidget()
        rlay  = QVBoxLayout(right)
        rlay.setContentsMargins(16, 20, 24, 24)
        rlay.setSpacing(6)

        self.preview_panel = VinylPreviewPanel(I18n.t("preview_label"))
        rlay.addWidget(self.preview_panel)

        splitter.addWidget(right)
        splitter.setSizes([300, 300])

        self.refresh_table()

    def _update_folder_styles(self) -> None:
        for sub, b in self.folder_btns.items():
            if b.isChecked():
                b.setStyleSheet(btn_style("#1f6feb","#388bfd","#fff",12))
            else:
                b.setStyleSheet(btn_style("#21262d","#30363d","#8b949e",12))

    def _switch_folder(self, sub: str) -> None:
        self.current_sub = sub
        for s, b in self.folder_btns.items():
            b.setChecked(s == sub)
        self._update_folder_styles()
        self.preview_panel.clear()
        self.refresh_table()

    def _find_import_files(self, folder: Path) -> list[Path]:
        """
        output: <folder>/<stem>/<stem>.fhv の構成
        generate/editor: <folder>/*.fhv または *.json(shapes形式) の構成（直下）
        .fhv / .json 両対応で探す。
        """
        patterns = ("*.fhv", "*.json")
        direct = [p for pat in patterns for p in folder.glob(pat)]
        nested = [p for pat in patterns for p in folder.glob(f"*/{pat}")]
        return sorted(direct + nested, reverse=True)
    
    def _migrated_dir_for(self, f: Path) -> Path:
        return get_vinyl_dir() / "output" / f.stem

    def _is_shapes_format(self, f: Path) -> bool:
        if f.suffix != ".json":
            return False
        try:
            with f.open(encoding="utf-8") as fp:
                d = json.load(fp)
            return "shapes" in d
        except Exception:
            return False

    def _ensure_shapes_migrated(self, f: Path) -> Path:
        """
        shapes形式JSONを初回検出時に output/<stem>/ へ正規化する。
          - 未配置なら移動
          - プレビューPNG・レイヤー数キャッシュ(.layers.txt)が無ければ生成
        既に正規化済みなら何もせずパスを返す（再変換しない）。
        """
        target_dir  = self._migrated_dir_for(f)
        target_json = target_dir / f.name
        count_txt   = target_dir / f"{f.stem}.layers.txt"
        png_path    = target_dir / f"{f.stem}.png"

        if f.parent == target_dir and count_txt.exists() and png_path.exists():
            return f  # 正規化済み

        from serializer import FhvSerializer
        from vinyl_renderer import render_vinyl_to_file

        vinyl = FhvSerializer.load_any(f)
        target_dir.mkdir(parents=True, exist_ok=True)

        if f.parent != target_dir:
            f = f.replace(target_json)
            self.log.append_log(f"shapes形式を正規化: output/{f.parent.name}/ へ移動 ({f.name})", "info")

        if not png_path.exists():
            render_vinyl_to_file(
                [l.to_dict() for l in vinyl.layers], png_path, output_size=1024,
            )

        if not count_txt.exists():
            count_txt.write_text(str(len(vinyl.layers)), encoding="utf-8")

        return f

    def _layer_count_for(self, f: Path) -> str:
        """レイヤー数表示用。キャッシュ優先、無ければフォールバックで変換。"""
        count_txt = f.with_name(f"{f.stem}.layers.txt")
        if count_txt.exists():
            try:
                return count_txt.read_text(encoding="utf-8").strip()
            except Exception:
                pass

        try:
            with f.open(encoding="utf-8") as fp:
                d = json.load(fp)
            if "layers" in d or "fhv_version" in d:
                return str(d.get("layer_count", len(d.get("layers", []))))
        except Exception:
            pass

        try:
            from serializer import FhvSerializer
            vinyl = FhvSerializer.load_any(f)
            return str(len(vinyl.layers))
        except Exception:
            return "?"    

    def refresh_table(self) -> None:
        self.table.setRowCount(0)
        self.hint.setVisible(False)
        self.import_btn.setEnabled(False)
        self.preview_panel.clear()

        folder = get_vinyl_dir() / self.current_sub
        folder.mkdir(parents=True, exist_ok=True)
        files = self._find_import_files(folder)

        if not files:
            self.table.setRowCount(1)
            item = QTableWidgetItem(I18n.t("no_files"))
            item.setForeground(QColor("#484f58"))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(0, 0, item)
            self.table.setItem(0, 1, QTableWidgetItem(""))
            return

        for f in files:
            if self._is_shapes_format(f):
                try:
                    f = self._ensure_shapes_migrated(f)
                except Exception as e:
                    self.log.append_log(f"shapes正規化失敗: {f.name}: {e}", "error")

            row = self.table.rowCount()
            self.table.insertRow(row)

            name_item = QTableWidgetItem(f.stem)
            name_item.setData(Qt.ItemDataRole.UserRole, f)
            self.table.setItem(row, 0, name_item)

            layer_item = QTableWidgetItem(self._layer_count_for(f))
            layer_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            layer_item.setForeground(QColor("#58a6ff"))
            self.table.setItem(row, 1, layer_item)

    def _on_select(self) -> None:
        rows = self.table.selectedItems()
        if not rows:
            self.hint.setVisible(False)
            self.import_btn.setEnabled(False)
            self.preview_panel.clear()
            return

        f = self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        if not f:
            self.hint.setVisible(False)
            self.import_btn.setEnabled(False)
            self.preview_panel.clear()
            return

        try:
            n_text = self._layer_count_for(f)
            self.hint.setText(I18n.t("layer_hint", n=n_text))
            self.hint.setVisible(True)
            self.import_btn.setEnabled(True)

            png_path = f.with_suffix(".png")
            if png_path.exists():
                self.preview_panel.load_png(png_path)
            else:
                from serializer import FhvSerializer
                vinyl = FhvSerializer.load_any(f)
                self.preview_panel.load_layers(
                    [l.to_dict() for l in vinyl.layers], label=f.name
                )
        except Exception:
            self.hint.setVisible(False)
            self.import_btn.setEnabled(False)
            self.preview_panel.clear()

    def _do_import(self) -> None:
        rows = self.table.selectedItems()
        if not rows:
            return
        f = self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        if not f:
            return

        self.import_btn.setEnabled(False)
        self.import_btn.setText(I18n.t("importing"))

        signals = WorkerSignals()
        signals.log.connect(self.log.append_log)
        signals.done.connect(self._on_done)

        self.worker = ImportWorker(signals, f)
        self.worker.start()

    def _on_done(self, ok: bool, _: str) -> None:
        self.import_btn.setEnabled(True)
        self.import_btn.setText(I18n.t("btn_import"))

    def retranslate(self) -> None:
        self.desc.setText(I18n.t("import_desc"))
        self.table.setHorizontalHeaderLabels([I18n.t("col_filename"), I18n.t("col_layers")])
        for sub, lk in zip(["output","generate","editor"],
                            ["folder_output","folder_generate","folder_editor"]):
            self.folder_btns[sub].setText(I18n.t(lk))
        self._update_folder_styles()
        self.import_btn.setText(I18n.t("btn_import"))
        self.preview_panel.set_title(I18n.t("preview_label"))
        self.refresh_table()


# ---------------------------------------------------------------------------
# Settings タブ
# ---------------------------------------------------------------------------

class SettingsTab(QWidget):
    def __init__(self, win: "MainWindow") -> None:
        super().__init__()
        self.win         = win
        self.calib_worker: CalibrationWorker | None = None
        self.calib_signals: WorkerSignals | None = None
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 24)
        lay.setSpacing(14)

        self.lang_label = section_label(I18n.t("settings_language"))
        lay.addWidget(self.lang_label)

        self.lang_combo = QComboBox()
        self.lang_combo.addItem("日本語", "ja")
        self.lang_combo.addItem("English", "en")
        idx = self.lang_combo.findData(AppSettings.get("language","ja"))
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        self.lang_combo.setStyleSheet("""
            QComboBox {
                background:#0d1117; color:#c9d1d9;
                border:1px solid #30363d; border-radius:6px;
                padding:6px 10px; font-size:13px;
            }
            QComboBox::drop-down { border:none; width:24px; }
            QComboBox QAbstractItemView {
                background:#161b22; color:#c9d1d9;
                border:1px solid #30363d; selection-background-color:#1f6feb;
            }
        """)
        self.lang_combo.currentIndexChanged.connect(self._on_lang)
        lay.addWidget(self.lang_combo)

        lay.addWidget(divider())

        self.dir_label = section_label(I18n.t("settings_outdir"))
        lay.addWidget(self.dir_label)

        dir_row = QHBoxLayout()
        self.dir_edit = QLineEdit(str(get_vinyl_dir()))
        self.dir_edit.setReadOnly(True)
        self.dir_edit.setStyleSheet("""
            QLineEdit {
                background:#0d1117; color:#8b949e;
                border:1px solid #30363d; border-radius:6px;
                padding:6px 10px; font-size:12px;
            }
        """)
        dir_row.addWidget(self.dir_edit)
        self.browse_btn = QPushButton(I18n.t("btn_browse"))
        self.browse_btn.setFixedWidth(80)
        self.browse_btn.setStyleSheet(btn_style())
        self.browse_btn.clicked.connect(self._browse)
        dir_row.addWidget(self.browse_btn)
        lay.addLayout(dir_row)

        lay.addWidget(divider())

        # --- キャリブレーション ---
        self.calib_label = section_label(I18n.t("settings_calibration"))
        lay.addWidget(self.calib_label)

        self.calib_desc = QLabel(I18n.t("calib_desc"))
        self.calib_desc.setStyleSheet("color:#8b949e;font-size:12px;")
        self.calib_desc.setWordWrap(True)
        lay.addWidget(self.calib_desc)

        self.calib_prepare = QLabel(I18n.t("calib_prepare"))
        self.calib_prepare.setStyleSheet("""
            color:#d29922; font-size:12px; font-weight:600;
            background:#2b2111; border:1px solid #3f2f10; border-radius:6px;
            padding:8px 10px;
        """)
        self.calib_prepare.setWordWrap(True)
        lay.addWidget(self.calib_prepare)

        self.calib_count_label = QLabel(I18n.t("calib_count_label"))
        self.calib_count_label.setStyleSheet("color:#8b949e;font-size:11px;margin-top:4px;")
        lay.addWidget(self.calib_count_label)

        self.calib_count_edit = QLineEdit()
        self.calib_count_edit.setPlaceholderText(I18n.t("calib_count_hint"))
        self.calib_count_edit.setValidator(QIntValidator(0, 999999, self))
        self.calib_count_edit.setStyleSheet("""
            QLineEdit {
                background:#0d1117; color:#c9d1d9;
                border:1px solid #30363d; border-radius:6px;
                padding:6px 10px; font-size:13px;
            }
            QLineEdit:focus { border-color:#1f6feb; }
        """)
        lay.addWidget(self.calib_count_edit)

        self.calib_btn = QPushButton(I18n.t("calib_btn"))
        self.calib_btn.setFixedHeight(36)
        self.calib_btn.setStyleSheet(btn_style("#8957e5", "#a371f7", "#fff", 13, True))
        self.calib_btn.clicked.connect(self._do_calibration)
        lay.addWidget(self.calib_btn)

        self.calib_progress = QProgressBar()
        self.calib_progress.setFixedHeight(22)
        self.calib_progress.setTextVisible(True)
        self.calib_progress.setStyleSheet("""
            QProgressBar {
                background:#0d1117; color:#c9d1d9;
                border:1px solid #30363d; border-radius:6px;
                text-align:center; font-size:11px;
            }
            QProgressBar::chunk { background:#8957e5; border-radius:6px; }
        """)
        self.calib_progress.setVisible(False)
        lay.addWidget(self.calib_progress)

        lay.addStretch()

    def _do_calibration(self) -> None:
        if self.calib_worker is not None and self.calib_worker.isRunning():
            self.win.log.append_log(I18n.t("calib_already_running"), "error")
            return

        text = self.calib_count_edit.text().strip()
        exact_count: int | None = None
        if text:
            try:
                n = int(text)
            except ValueError:
                n = -1
            if not (2000 <= n <= 3000):
                self.win.log.append_log(I18n.t("calib_invalid_count"), "error")
                return
            exact_count = n

        self.calib_btn.setEnabled(False)
        self.calib_btn.setText(I18n.t("calib_running"))
        self.win.log.append_log(I18n.t("calib_start"), "info")

        self.calib_progress.setVisible(True)
        self.calib_progress.setRange(0, 0)   # 実際のMB数が分かるまでは不確定(バウンシング)表示
        self.calib_progress.setFormat("")

        self.calib_signals = WorkerSignals()
        self.calib_signals.log.connect(self.win.log.append_log)
        self.calib_signals.done.connect(self._on_calib_done)
        self.calib_signals.progress.connect(self._on_calib_progress)

        self.calib_worker = CalibrationWorker(self.calib_signals, exact_count)
        self.calib_worker.start()

    def _on_calib_progress(self, scanned: int, total: int, n: int) -> None:
        if total > 0:
            self.calib_progress.setRange(0, total)
            self.calib_progress.setValue(min(scanned, total))
        self.calib_progress.setFormat(I18n.t("calib_progress_fmt", scanned=scanned, total=total, n=n))

    def _on_calib_done(self, ok: bool, path: str) -> None:
        self.calib_btn.setEnabled(True)
        self.calib_btn.setText(I18n.t("calib_btn"))
        self.calib_progress.setVisible(False)
        self.calib_progress.setFormat("")
        if ok:
            self.win.log.append_log(I18n.t("calib_success", path=path or "?"), "success")
        else:
            self.win.log.append_log(I18n.t("calib_failed_generic"), "error")

    def _on_lang(self) -> None:
        lang = self.lang_combo.currentData()
        AppSettings.set("language", lang)
        I18n.set(lang)
        self.win.retranslate()

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "", str(get_vinyl_dir()))
        if d:
            AppSettings.set("vinyl_dir", d)
            self.dir_edit.setText(d)
            self.win.import_tab.refresh_table()

    def retranslate(self) -> None:
        self.lang_label.setText(I18n.t("settings_language"))
        self.dir_label.setText(I18n.t("settings_outdir"))
        self.browse_btn.setText(I18n.t("btn_browse"))
        self.calib_label.setText(I18n.t("settings_calibration"))
        self.calib_desc.setText(I18n.t("calib_desc"))
        self.calib_prepare.setText(I18n.t("calib_prepare"))
        self.calib_count_label.setText(I18n.t("calib_count_label"))
        self.calib_count_edit.setPlaceholderText(I18n.t("calib_count_hint"))
        is_running = self.calib_worker is not None and self.calib_worker.isRunning()
        self.calib_btn.setText(I18n.t("calib_running") if is_running else I18n.t("calib_btn"))


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        I18n.set(AppSettings.get("language","ja"))
        self.setWindowTitle(I18n.t("app_title"))
        self.setMinimumSize(700, 700)
        self.resize(1100, 930)
        self._apply_theme()
        self._build()

    def _apply_theme(self) -> None:
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background:#0d1117; color:#c9d1d9;
                font-family:"Noto Sans CJK JP","Noto Sans JP",sans-serif;
                font-size:13px;
            }
            QTabWidget::pane {
                border:1px solid #21262d; border-radius:6px; background:#161b22;
            }
            QTabBar::tab {
                background:#0d1117; color:#8b949e;
                padding:8px 20px; border:1px solid #21262d; border-bottom:none;
                border-top-left-radius:6px; border-top-right-radius:6px;
                font-size:13px; font-weight:600; min-width:90px;
            }
            QTabBar::tab:selected {
                background:#161b22; color:#f0f6fc; border-bottom:2px solid #1f6feb;
            }
            QTabBar::tab:hover:!selected { color:#c9d1d9; background:#161b22; }
        """)

    def _build(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(16,16,16,16)
        lay.setSpacing(10)

        self.title_label = QLabel(I18n.t("app_title"))
        self.title_label.setStyleSheet("color:#f0f6fc;font-size:18px;font-weight:700;")
        lay.addWidget(self.title_label)

        self.log = LogWidget()

        self.tabs = QTabWidget()
        self.export_tab   = ExportTab(self.log, self)
        self.import_tab   = ImportTab(self.log)
        self.generate_tab = GenerateTab(self.log, self)   # ← 追加
        self.settings_tab = SettingsTab(self)

        self.tabs.addTab(self.export_tab,   I18n.t("tab_export"))
        self.tabs.addTab(self.generate_tab, I18n.t("tab_generate"))  # ← 追加
        self.tabs.addTab(self.import_tab,   I18n.t("tab_import"))
        self.tabs.addTab(self.settings_tab, I18n.t("tab_settings"))
        lay.addWidget(self.tabs, 3)

        self.log_label = QLabel(I18n.t("log_label"))
        self.log_label.setStyleSheet("color:#484f58;font-size:11px;font-weight:600;")
        lay.addWidget(self.log_label)
        lay.addWidget(self.log, 1)

        self.clear_btn = QPushButton(I18n.t("btn_clear_log"))
        self.clear_btn.setFixedHeight(26)
        self.clear_btn.setStyleSheet(
            "QPushButton{background:transparent;color:#484f58;border:none;font-size:11px;}"
            "QPushButton:hover{color:#8b949e;}")
        self.clear_btn.clicked.connect(self.log.clear_log)
        lay.addWidget(self.clear_btn, 0, Qt.AlignmentFlag.AlignRight)

        self.log.append_log(I18n.t("log_startup"), "success")
        self.log.append_log(I18n.t("log_open_editor"), "info")

    def retranslate(self) -> None:
        self.setWindowTitle(I18n.t("app_title"))
        self.title_label.setText(I18n.t("app_title"))
        self.tabs.setTabText(0, I18n.t("tab_export"))
        self.tabs.setTabText(1, I18n.t("tab_generate"))   # ← 追加
        self.tabs.setTabText(2, I18n.t("tab_import"))
        self.tabs.setTabText(3, I18n.t("tab_settings"))
        self.log_label.setText(I18n.t("log_label"))
        self.clear_btn.setText(I18n.t("btn_clear_log"))
        self.export_tab.retranslate()
        self.generate_tab.retranslate()   # ← 追加
        self.import_tab.retranslate()
        self.settings_tab.retranslate()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("FH6 Vinyl Tool")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
