"""
fh6vinyl.py — FH6 ビニールツール CLI エントリポイント

使い方:
  python fh6vinyl.py export -o my_vinyl.fhv
  python fh6vinyl.py import-fhv -i my_vinyl.fhv
  python fh6vinyl.py import-shapes -i shapes.json
  python fh6vinyl.py scan
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vinyl_manager import VinylManager


def cmd_export(args: argparse.Namespace) -> None:
    mgr = VinylManager(pid=args.pid, verbose=args.verbose)
    mgr.export(args.output)


def cmd_import_fhv(args: argparse.Namespace) -> None:
    mgr = VinylManager(pid=args.pid, verbose=args.verbose)
    mgr.import_fhv(args.input, strict=args.strict)


def cmd_import_shapes(args: argparse.Namespace) -> None:
    mgr = VinylManager(pid=args.pid, verbose=args.verbose)
    mgr.import_shapes(
        args.input,
        canvas_w  = args.canvas_w,
        canvas_h  = args.canvas_h,
        strict    = args.strict,
        save_fhv  = args.save_fhv,
    )


def cmd_scan(args: argparse.Namespace) -> None:
    mgr = VinylManager(pid=args.pid, verbose=True)
    mgr.scan()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fh6vinyl",
        description="FH6 ビニールデータ Linux ツール",
    )
    parser.add_argument("--pid",     type=int,  help="PIDを直接指定（省略時は自動検索）")
    parser.add_argument("--verbose", action="store_true", help="詳細ログを表示")

    sub = parser.add_subparsers(dest="command", required=True)

    # export
    p_exp = sub.add_parser("export", help="メモリ → .fhv エクスポート")
    p_exp.add_argument("-o", "--output", required=True, help="出力ファイル (.fhv)")
    p_exp.set_defaults(func=cmd_export)

    # import-fhv
    p_ifhv = sub.add_parser("import-fhv", help=".fhv → メモリ インポート")
    p_ifhv.add_argument("-i", "--input",  required=True, help="入力ファイル (.fhv)")
    p_ifhv.add_argument("--strict", action="store_true", help="レイヤー数不一致時にエラー")
    p_ifhv.set_defaults(func=cmd_import_fhv)

    # import-shapes
    p_ish = sub.add_parser("import-shapes", help="shapes JSON → メモリ インポート")
    p_ish.add_argument("-i", "--input",    required=True,  help="入力ファイル (shapes JSON)")
    p_ish.add_argument("--canvas-w",       type=float, default=1920.0,  help="キャンバス幅px (デフォルト: 799)")
    p_ish.add_argument("--canvas-h",       type=float, default=1080.0, help="キャンバス高さpx (デフォルト: 1075)")
    p_ish.add_argument("--strict",         action="store_true", help="レイヤー数不一致時にエラー")
    p_ish.add_argument("--save-fhv",       help="変換後を .fhv として保存するパス（任意）")
    p_ish.set_defaults(func=cmd_import_shapes)

    # scan
    p_sc = sub.add_parser("scan", help="CLiveryGroup スキャンのみ（デバッグ用）")
    p_sc.set_defaults(func=cmd_scan)

    return parser


def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()

    try:
        args.func(args)
    except RuntimeError as e:
        print(f"\n[!] エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[*] 中断しました")
        sys.exit(0)


if __name__ == "__main__":
    main()
