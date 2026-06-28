# FH6 Vinyl Tool for Linux (FVTL)

> 🚧 **Status:** Early Development / Experimental
>
> This project is currently under active development. Features may change without notice.

---
# English

## Overview

**FH6 Vinyl Tool for Linux (FVTL)** is a native Linux application for working with **Forza Horizon 6** vinyl data while running the game through Proton.

The project is currently in an early experimental stage. The goal is to provide Linux users with a complete toolkit for managing and editing vinyl data entirely on Linux.

---

## Current Features

* Import vinyl data
* Export vinyl data
* Native Linux support

---

## Planned Features

* Built-in vinyl editor
* Generate vinyl data from images
* Vinyl management tools
* Performance improvements
* Additional editing features

---

## Installation

Clone the repository.

```bash
git clone https://github.com/wired-wanderer/fvtl.git
cd FVTL
```

### Bash

```bash
sh setup.sh
```

### Fish

```fish
fish setup.fish
```

### What does the setup script do?

The setup script automatically:

* Creates a Python virtual environment (`.venv`)
* Installs all required Python packages from `requirements.txt`

This only needs to be run once.

---

## Running FVTL

### Bash

```bash
sh run.sh
```

### Fish

```fish
fish run.fish
```

### What does the run script do?

When starting FVTL, the script automatically:

* Activates the Python virtual environment
* Temporarily adjusts `ptrace_scope` so FVTL can access the running game
* Launches FVTL

When FVTL exits, it automatically:

* Deactivates the virtual environment
* Restores the original `ptrace_scope` value

No manual activation of `.venv` or modification of `ptrace_scope` is normally required.

---

## About this Project

There are currently very few native Linux tools for working with Forza Horizon 6 vinyl data.

FVTL aims to provide a Linux-first solution for managing and editing vinyl data without requiring Windows.

This project is inspired by tools such as **KFPS** and **ForzaPainter**.

However, to avoid licensing concerns and to gain a deeper understanding of the implementation, all source code has been written from scratch.

---

## Disclaimer

This is an unofficial community project.

It is not affiliated with or endorsed by Playground Games, Turn 10 Studios, or Microsoft.

The developer assumes no responsibility for any issues caused by the use of this tool, including but not limited to game account bans, data loss, or system damage.

This tool is provided strictly for educational and experimental purposes and is used at your own risk.

---

# 日本語

## 概要

**FH6 Vinyl Tool for Linux (FVTL)** は、Proton上で動作する **Forza Horizon 6** のバイナルデータを扱うためのLinux向けツールです。

現在はテスト版ですが、Linux上で完結するバイナル管理ツールを目指して開発しています。

---

## 現在の機能

* バイナルデータのインポート
* バイナルデータのエクスポート
* Linuxネイティブ環境で動作

---

## 今後実装予定

* バイナルデータエディター
* 画像からバイナルデータを生成する機能
* バイナル管理機能
* パフォーマンス改善
* その他便利な編集機能

---

## インストール

リポジトリを取得します。

```bash
git clone https://github.com/wired-wanderer/fvtl.git
cd FVTL
```

### Bash

```bash
sh setup.sh
```

### Fish

```fish
fish setup.fish
```

### setupスクリプトについて

セットアップスクリプトは以下を自動で実行します。

* Python仮想環境 (`.venv`) を作成
* `requirements.txt` から必要なPythonライブラリをインストール

初回のみ実行してください。

---

## 起動方法

### Bash

```bash
sh run.sh
```

### Fish

```fish
fish run.fish
```

### runスクリプトについて

起動スクリプトは以下を自動で実行します。

起動時

* Python仮想環境 (`.venv`) を有効化
* `ptrace_scope` を一時的に変更してFH6へアクセスできるよう設定
* FVTLを起動

終了時

* Python仮想環境を終了
* `ptrace_scope` を元の値へ復元

そのため、通常は手動で `.venv` を有効化したり `ptrace_scope` を変更する必要はありません。

---

## このプロジェクトについて

Linux向けには、Forza Horizon 6のバイナルデータを扱えるツールがほとんど存在しません。

FVTLは、Windowsを使わずLinuxだけでバイナルデータを管理・編集できる環境を目指して開発しています。

このプロジェクトは **KFPS** や **ForzaPainter** からアイディアや設計思想の影響を受けています。

ただし、ライセンスへの配慮と実装への理解を深めるため、ソースコードはすべて一から実装しています。

---

## 注意

このツールは非公式のファンプロジェクトです。

Playground Games、Turn 10 Studios、および Microsoft とは一切関係ありません。

本ツールの使用によって発生したいかなる問題（ゲームアカウントのBAN、データ損失、システム障害等）について、開発者は一切の責任を負いません。

本ツールはすべて自己責任で使用してください。

---

## License

MIT License
