"""データベース初期化テスト"""

import sqlite3
import tempfile
from pathlib import Path

from src.database.models import init_db, get_connection


def test_init_db_creates_tables():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = init_db(db_path)

    # テーブル存在確認
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = [t[0] for t in tables]

    assert "properties" in table_names
    assert "land_prices" in table_names
    assert "transaction_prices" in table_names
    assert "saved_searches" in table_names
    assert "notification_log" in table_names
    assert "model_metadata" in table_names

    conn.close()
    Path(db_path).unlink(missing_ok=True)


def test_wal_mode_enabled():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = init_db(db_path)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"

    conn.close()
    Path(db_path).unlink(missing_ok=True)
