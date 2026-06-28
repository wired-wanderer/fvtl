#!/usr/bin/env bash
# setup.sh — .venv作成と依存関係インストール

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "=== FH6 Vinyl Tool セットアップ ==="

# Python確認
if ! command -v python3 &>/dev/null; then
    echo "[!] python3 が見つかりません"
    exit 1
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "[*] Python $PY_VER を使用"

# .venv作成
if [ -d "$VENV_DIR" ]; then
    echo "[*] 既存の .venv を使用: $VENV_DIR"
else
    echo "[*] .venv を作成中..."
    python3 -m venv "$VENV_DIR"
    echo "[✓] .venv 作成完了"
fi

# pip install
echo "[*] 依存関係をインストール中..."
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

echo "[✓] セットアップ完了"
echo ""
echo "起動するには:"
echo "  bash run.sh"
