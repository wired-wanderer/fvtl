#!/usr/bin/env fish
# run.fish — FH6 Vinyl Tool GUI 起動スクリプト
#
# やること:
#   1. ptrace_scope を 0 に緩める（sudo必要）
#   2. .venv を activate
#   3. gui.py を起動
#   4. 終了後に ptrace_scope を元の値に戻す
#   5. .venv を deactivate

set SCRIPT_DIR (dirname (realpath (status filename)))  
set VENV_DIR $SCRIPT_DIR/.venv  
set PTRACE_PATH /proc/sys/kernel/yama/ptrace_scope

# .venv 確認

if not test -f $VENV_DIR/bin/activate.fish  
echo "[!] .venv が見つかりません。先に setup.fish を実行してください:"  
echo " fish setup.fish"  
exit 1  
end

# 現在の ptrace_scope を保存

set ORIG_PTRACE (cat $PTRACE_PATH)  
echo "[*] 現在の ptrace_scope: $ORIG_PTRACE"

# ptrace_scope を 0 に設定

if test $ORIG_PTRACE -ne 0  
echo "[*] ptrace_scope を 0 に設定します（sudo が必要です）"  
echo 0 | sudo tee $PTRACE_PATH > /dev/null

if test $status -ne 0
    echo "[!] ptrace_scope の変更に失敗しました"
    exit 1
end

echo "[✓] ptrace_scope = 0"

else  
echo "[✓] ptrace_scope は既に 0 です"  
end

# クリーンアップ関数（手動 + SIGINT）

function _cleanup  
echo ""  
echo "[*] クリーンアップ中..."

if test $ORIG_PTRACE -ne 0
    echo $ORIG_PTRACE | sudo tee $PTRACE_PATH > /dev/null
    echo "[✓] ptrace_scope を $ORIG_PTRACE に復元しました"
end

if functions -q deactivate
    deactivate
end

end

# Ctrl+C対応のみ

function on_exit --on-signal INT --on-signal TERM  
_cleanup  
end

# .venv activate

source $VENV_DIR/bin/activate.fish  
echo "[✓] .venv を activate しました"

# GUI 起動

echo "[*] FH6 Vinyl Tool を起動します..."  
cd $SCRIPT_DIR  
python gui.py

# 正常終了時もクリーンアップ

_cleanup