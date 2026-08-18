# SQLite 连接与建表
import sqlite3
from contextlib import contextmanager

from . import config


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db():
    """初始化数据库表结构"""
    config.ensure_dirs()
    conn = get_connection()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS upload_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            md5 TEXT NOT NULL,
            file_name TEXT NOT NULL,
            total_size INTEGER NOT NULL,
            chunk_size INTEGER NOT NULL,
            total_chunks INTEGER NOT NULL,
            uploaded_chunks TEXT NOT NULL DEFAULT '[]',
            target_path TEXT NOT NULL,
            temp_dir TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'uploading',
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_upload_tasks_md5 ON upload_tasks(md5);
        """
    )
    conn.commit()
    conn.close()


@contextmanager
def db():
    """数据库上下文管理器，自动提交/回滚"""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
