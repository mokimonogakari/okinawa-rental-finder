#!/bin/bash
# リモート環境 (Claude Code on the Web) 用セットアップスクリプト
# ローカル環境では既にvenvがあるためスキップ

# リモート環境のみで実行
if [ "$CLAUDE_CODE_REMOTE" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR" || exit 1

# venvが無ければ作成
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate

# 依存関係が既にインストール済みか確認
if ! python3 -c "import scrapy" 2>/dev/null; then
  pip install -e '.[dev]' --quiet
fi

exit 0
