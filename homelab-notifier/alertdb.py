import os, sqlite3, time

DB_PATH = os.getenv("ALERT_DB", "/data/alerts.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,            -- scrutiny | watchtower | beszel
    message TEXT NOT NULL,           -- final Telegram HTML
    raw TEXT,                        -- original payload, for debugging
    received_at INTEGER NOT NULL,
    expires_at INTEGER,              -- NULL = never expires
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | delivered | expired
    attempts INTEGER NOT NULL DEFAULT 0,
    next_try_at INTEGER NOT NULL,
    delivered_at INTEGER,
    last_error TEXT
);
CREATE INDEX IF NOT EXISTS alerts_pending ON alerts (status, next_try_at);
"""

MAX_BACKOFF = 3600  # seconds


def connect():
    # One short-lived connection per call: safe across threads and across the inbox/notifier containers
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def init():
    with connect() as conn:
        conn.executescript(SCHEMA)


def enqueue(source: str, message: str, raw: str = "", ttl: int | None = None) -> int:
    now = int(time.time())
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO alerts (source, message, raw, received_at, expires_at, next_try_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (source, message, raw, now, now + ttl if ttl else None, now),
        )
        return cur.lastrowid


def expire_old():
    now = int(time.time())
    with connect() as conn:
        conn.execute(
            "UPDATE alerts SET status = 'expired' "
            "WHERE status = 'pending' AND expires_at IS NOT NULL AND expires_at <= ?",
            (now,),
        )


def due(limit: int = 20):
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM alerts WHERE status = 'pending' AND next_try_at <= ? ORDER BY id LIMIT ?",
            (int(time.time()), limit),
        ).fetchall()


def mark_delivered(alert_id: int):
    with connect() as conn:
        conn.execute(
            "UPDATE alerts SET status = 'delivered', delivered_at = ?, last_error = NULL WHERE id = ?",
            (int(time.time()), alert_id),
        )


def mark_failed(alert_id: int, error: str):
    with connect() as conn:
        row = conn.execute("SELECT attempts FROM alerts WHERE id = ?", (alert_id,)).fetchone()
        attempts = (row["attempts"] if row else 0) + 1
        backoff = min(60 * 2 ** (attempts - 1), MAX_BACKOFF)
        conn.execute(
            "UPDATE alerts SET attempts = ?, next_try_at = ?, last_error = ? WHERE id = ?",
            (attempts, int(time.time()) + backoff, error[:500], alert_id),
        )


def purge(days: int = 30):
    cutoff = int(time.time()) - days * 86400
    with connect() as conn:
        conn.execute(
            "DELETE FROM alerts WHERE status IN ('delivered', 'expired') AND received_at < ?",
            (cutoff,),
        )
