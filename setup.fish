#!/usr/bin/env fish
# setup.fish — .venv作成と依存関係インストール

set SCRIPT_DIR (dirname (realpath (status filename)))
set VENV_DIR $SCRIPT_DIR/.venv

echo "=== FH6 Vinyl Tool セットアップ ==="

# Python確認
if not command -q python3
    echo "[!] python3 が見つかりません"
    exit 1
end

set py_ver (python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "[*] Python $py_ver を使用"

# .venv作成
if test -d $VENV_DIR
    echo "[*] 既存の .venv を使用: $VENV_DIR"
else
    echo "[*] .venv を作成中..."
    python3 -m venv $VENV_DIR
    if test $status -ne 0
        echo "[!] venv作成に失敗しました"
        exit 1
    end
    echo "[✓] .venv 作成完了"
end

# pip install
echo "[*] 依存関係をインストール中..."
$VENV_DIR/bin/pip install --upgrade pip -q
$VENV_DIR/bin/pip install -r $SCRIPT_DIR/requirements.txt

if test $status -ne 0
    echo "[!] インストールに失敗しました"
    exit 1
end

echo "[✓] セットアップ完了"
echo ""
echo "起動するには:"
echo "  fish run.fish"
