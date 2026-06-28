#!/usr/bin/env bash
# run.sh — FH6 Vinyl Tool GUI 起動スクリプト
#
# やること:
#   1. ptrace_scope を 0 に緩める（sudo必要）
#   2. .venv を activate
#   3. gui.py を起動
#   4. 終了後に ptrace_scope を元の値に戻す
#   5. .venv を deactivate

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
PTRACE_PATH="/proc/sys/kernel/yama/ptrace_scope"

# .venv 確認
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "[!] .venv が見つかりません。先に setup.sh を実行してください:"
    echo "    bash setup.sh"
    exit 1
fi

# 現在の ptrace_scope を保存
ORIG_PTRACE=$(cat "$PTRACE_PATH")
echo "[*] 現在の ptrace_scope: $ORIG_PTRACE"

# クリーンアップ関数（EXIT で必ず呼ばれる）
cleanup() {
    echo ""
    echo "[*] クリーンアップ中..."

    # ptrace_scope を元に戻す
    if [ "$ORIG_PTRACE" -ne 0 ]; then
        echo "$ORIG_PTRACE" | sudo tee "$PTRACE_PATH" > /dev/null
        echo "[✓] ptrace_scope を $ORIG_PTRACE に復元しました"
    fi

    # deactivate
    deactivate 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# ptrace_scope を 0 に設定
if [ "$ORIG_PTRACE" -ne 0 ]; then
    echo "[*] ptrace_scope を 0 に設定します（sudo が必要です）"
    echo 0 | sudo tee "$PTRACE_PATH" > /dev/null
    echo "[✓] ptrace_scope = 0"
else
    echo "[✓] ptrace_scope は既に 0 です"
fi

# .venv activate
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
echo "[✓] .venv を activate しました"

# GUI 起動
echo "[*] FH6 Vinyl Tool を起動します..."
echo ""
cd "$SCRIPT_DIR"
python gui.py
