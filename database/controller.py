"""
Database controller that manages multiple SQLite database files.
Each file is limited to 10,000 records. When the limit is reached,
a new database file is created. Query results are merged transparently.
"""

import os
import glob
import sqlite3
from typing import Optional

import config

os.makedirs(config.DB_DIR, exist_ok=True)

SCHEMA_BIRTHDAYS = """
CREATE TABLE IF NOT EXISTS birthdays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    full_name TEXT NOT NULL,
    date_of_birth TEXT NOT NULL,
    relationship TEXT NOT NULL DEFAULT 'friend',
    gift_required INTEGER NOT NULL DEFAULT 0,
    congratulation_text TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

SCHEMA_CONGRATS = """
CREATE TABLE IF NOT EXISTS congratulation_texts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

SCHEMA_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    username TEXT DEFAULT '',
    full_name TEXT DEFAULT '',
    timezone TEXT DEFAULT 'UTC',
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

SCHEMA_ADS = """
CREATE TABLE IF NOT EXISTS advertisements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL,
    message TEXT NOT NULL,
    sent INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _db_files() -> list[str]:
    """Return sorted list of existing DB files."""
    pattern = os.path.join(config.DB_DIR, "birth_*.db")
    files = sorted(glob.glob(pattern))
    if not files:
        first = os.path.join(config.DB_DIR, "birth_001.db")
        _init_db(first)
        files = [first]
    return files


def _init_db(path: str):
    """Initialize a new database file with all schemas."""
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_BIRTHDAYS)
    conn.executescript(SCHEMA_CONGRATS)
    conn.executescript(SCHEMA_USERS)
    conn.executescript(SCHEMA_ADS)
    conn.commit()
    conn.close()


def _get_current_db() -> str:
    """Return the current (latest) DB file, creating a new one if limit reached."""
    files = _db_files()
    latest = files[-1]
    conn = sqlite3.connect(latest)
    total = 0
    for table in ("birthdays", "congratulation_texts", "users", "advertisements"):
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        total += row[0]
    conn.close()
    if total >= config.DB_RECORD_LIMIT:
        idx = len(files) + 1
        new_path = os.path.join(config.DB_DIR, f"birth_{idx:03d}.db")
        _init_db(new_path)
        return new_path
    return latest


def _conn(path: Optional[str] = None) -> sqlite3.Connection:
    p = path or _get_current_db()
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    return conn


# ── User operations ──────────────────────────────────────────────

def upsert_user(telegram_id: int, username: str = "", full_name: str = "", timezone: str = "UTC") -> dict:
    existing = get_user(telegram_id)
    if existing:
        db_path = existing["_db"]
        conn = _conn(db_path)
        conn.execute(
            "UPDATE users SET username=?, full_name=?, timezone=? WHERE telegram_id=?",
            (username, full_name, timezone, telegram_id),
        )
        conn.commit()
        conn.close()
        return get_user(telegram_id)
    conn = _conn()
    conn.execute(
        "INSERT INTO users (telegram_id, username, full_name, timezone) VALUES (?, ?, ?, ?)",
        (telegram_id, username, full_name, timezone),
    )
    conn.commit()
    conn.close()
    return get_user(telegram_id)


def get_user(telegram_id: int) -> Optional[dict]:
    for f in _db_files():
        conn = _conn(f)
        row = conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        conn.close()
        if row:
            d = dict(row)
            d["_db"] = f
            return d
    return None


def get_all_users() -> list[dict]:
    results = []
    for f in _db_files():
        conn = _conn(f)
        rows = conn.execute("SELECT * FROM users").fetchall()
        conn.close()
        results.extend(dict(r) for r in rows)
    return results


def set_admin(telegram_id: int, is_admin: bool = True):
    user = get_user(telegram_id)
    if not user:
        return
    conn = _conn(user["_db"])
    conn.execute("UPDATE users SET is_admin=? WHERE telegram_id=?", (int(is_admin), telegram_id))
    conn.commit()
    conn.close()


def is_admin(telegram_id: int) -> bool:
    if telegram_id in config.ADMIN_IDS:
        return True
    user = get_user(telegram_id)
    return bool(user and user["is_admin"])


# ── Birthday operations ──────────────────────────────────────────

def add_birthday(user_id: int, full_name: str, date_of_birth: str,
                 relationship: str = "friend", gift_required: bool = False,
                 congratulation_text: str = "", notes: str = "") -> int:
    conn = _conn()
    cur = conn.execute(
        """INSERT INTO birthdays
           (user_id, full_name, date_of_birth, relationship, gift_required, congratulation_text, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, full_name, date_of_birth, relationship, int(gift_required), congratulation_text, notes),
    )
    conn.commit()
    bid = cur.lastrowid
    conn.close()
    return bid


def get_birthdays(user_id: int) -> list[dict]:
    results = []
    for f in _db_files():
        conn = _conn(f)
        rows = conn.execute(
            "SELECT * FROM birthdays WHERE user_id=? ORDER BY date_of_birth", (user_id,)
        ).fetchall()
        conn.close()
        for r in rows:
            d = dict(r)
            d["_db"] = f
            results.append(d)
    results.sort(key=lambda x: x["date_of_birth"])
    return results


def get_birthday_by_id(birthday_id: int, user_id: int) -> Optional[dict]:
    for f in _db_files():
        conn = _conn(f)
        row = conn.execute(
            "SELECT * FROM birthdays WHERE id=? AND user_id=?", (birthday_id, user_id)
        ).fetchone()
        conn.close()
        if row:
            d = dict(row)
            d["_db"] = f
            return d
    return None


def update_birthday(birthday_id: int, user_id: int, **kwargs) -> bool:
    rec = get_birthday_by_id(birthday_id, user_id)
    if not rec:
        return False
    allowed = {"full_name", "date_of_birth", "relationship", "gift_required", "congratulation_text", "notes"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    if "gift_required" in updates:
        updates["gift_required"] = int(updates["gift_required"])
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [birthday_id, user_id]
    conn = _conn(rec["_db"])
    conn.execute(f"UPDATE birthdays SET {set_clause} WHERE id=? AND user_id=?", values)
    conn.commit()
    conn.close()
    return True


def delete_birthday(birthday_id: int, user_id: int) -> bool:
    rec = get_birthday_by_id(birthday_id, user_id)
    if not rec:
        return False
    conn = _conn(rec["_db"])
    conn.execute("DELETE FROM birthdays WHERE id=? AND user_id=?", (birthday_id, user_id))
    conn.commit()
    conn.close()
    return True


def search_birthdays(user_id: int, query: str) -> list[dict]:
    results = []
    for f in _db_files():
        conn = _conn(f)
        rows = conn.execute(
            "SELECT * FROM birthdays WHERE user_id=? AND full_name LIKE ? ORDER BY date_of_birth",
            (user_id, f"%{query}%"),
        ).fetchall()
        conn.close()
        for r in rows:
            d = dict(r)
            d["_db"] = f
            results.append(d)
    return results


def get_all_birthdays() -> list[dict]:
    """Get all birthdays across all users (admin)."""
    results = []
    for f in _db_files():
        conn = _conn(f)
        rows = conn.execute("SELECT * FROM birthdays ORDER BY date_of_birth").fetchall()
        conn.close()
        results.extend(dict(r) for r in rows)
    results.sort(key=lambda x: x["date_of_birth"])
    return results


# ── Congratulation text operations ───────────────────────────────

def add_congrats_text(user_id: int, title: str, body: str) -> int:
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO congratulation_texts (user_id, title, body) VALUES (?, ?, ?)",
        (user_id, title, body),
    )
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return cid


def get_congrats_texts(user_id: int) -> list[dict]:
    results = []
    for f in _db_files():
        conn = _conn(f)
        rows = conn.execute(
            "SELECT * FROM congratulation_texts WHERE user_id=? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
        conn.close()
        for r in rows:
            d = dict(r)
            d["_db"] = f
            results.append(d)
    return results


def get_congrats_text_by_id(text_id: int, user_id: int) -> Optional[dict]:
    for f in _db_files():
        conn = _conn(f)
        row = conn.execute(
            "SELECT * FROM congratulation_texts WHERE id=? AND user_id=?", (text_id, user_id)
        ).fetchone()
        conn.close()
        if row:
            d = dict(row)
            d["_db"] = f
            return d
    return None


def update_congrats_text(text_id: int, user_id: int, **kwargs) -> bool:
    rec = get_congrats_text_by_id(text_id, user_id)
    if not rec:
        return False
    allowed = {"title", "body"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [text_id, user_id]
    conn = _conn(rec["_db"])
    conn.execute(f"UPDATE congratulation_texts SET {set_clause} WHERE id=? AND user_id=?", values)
    conn.commit()
    conn.close()
    return True


def delete_congrats_text(text_id: int, user_id: int) -> bool:
    rec = get_congrats_text_by_id(text_id, user_id)
    if not rec:
        return False
    conn = _conn(rec["_db"])
    conn.execute("DELETE FROM congratulation_texts WHERE id=? AND user_id=?", (text_id, user_id))
    conn.commit()
    conn.close()
    return True


def search_congrats_texts(user_id: int, query: str) -> list[dict]:
    results = []
    for f in _db_files():
        conn = _conn(f)
        rows = conn.execute(
            "SELECT * FROM congratulation_texts WHERE user_id=? AND (title LIKE ? OR body LIKE ?) ORDER BY created_at DESC",
            (user_id, f"%{query}%", f"%{query}%"),
        ).fetchall()
        conn.close()
        for r in rows:
            d = dict(r)
            d["_db"] = f
            results.append(d)
    return results


# ── Advertisement operations ─────────────────────────────────────

def add_advertisement(admin_id: int, message: str) -> int:
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO advertisements (admin_id, message) VALUES (?, ?)",
        (admin_id, message),
    )
    conn.commit()
    aid = cur.lastrowid
    conn.close()
    return aid


def get_pending_ads() -> list[dict]:
    results = []
    for f in _db_files():
        conn = _conn(f)
        rows = conn.execute("SELECT * FROM advertisements WHERE sent=0").fetchall()
        conn.close()
        for r in rows:
            d = dict(r)
            d["_db"] = f
            results.append(d)
    return results


def mark_ad_sent(ad_id: int, db_path: str):
    conn = _conn(db_path)
    conn.execute("UPDATE advertisements SET sent=1 WHERE id=?", (ad_id,))
    conn.commit()
    conn.close()


# ── Statistics ───────────────────────────────────────────────────

def get_user_stats(user_id: int) -> dict:
    from datetime import datetime, date
    birthdays = get_birthdays(user_id)
    total = len(birthdays)
    gifts_needed = sum(1 for b in birthdays if b["gift_required"])
    today = date.today()
    nearest = None
    nearest_gift = None
    for b in birthdays:
        parts = b["date_of_birth"].split("-")
        if len(parts) == 3:
            month, day = int(parts[1]), int(parts[2])
            this_year = date(today.year, month, day)
            if this_year < today:
                this_year = date(today.year + 1, month, day)
            if nearest is None or this_year < nearest[1]:
                nearest = (b, this_year)
            if b["gift_required"] and (nearest_gift is None or this_year < nearest_gift[1]):
                nearest_gift = (b, this_year)
    return {
        "total": total,
        "gifts_needed": gifts_needed,
        "nearest": nearest[0] if nearest else None,
        "nearest_date": nearest[1].isoformat() if nearest else None,
        "nearest_gift": nearest_gift[0] if nearest_gift else None,
        "nearest_gift_date": nearest_gift[1].isoformat() if nearest_gift else None,
    }


def get_admin_stats() -> dict:
    users = get_all_users()
    birthdays = get_all_birthdays()
    from datetime import date
    today = date.today()
    total_birthdays = len(birthdays)
    gifts_needed = sum(1 for b in birthdays if b["gift_required"])
    nearest = None
    nearest_gift = None
    for b in birthdays:
        parts = b["date_of_birth"].split("-")
        if len(parts) == 3:
            month, day = int(parts[1]), int(parts[2])
            try:
                this_year = date(today.year, month, day)
            except ValueError:
                continue
            if this_year < today:
                this_year = date(today.year + 1, month, day)
            if nearest is None or this_year < nearest[1]:
                nearest = (b, this_year)
            if b["gift_required"] and (nearest_gift is None or this_year < nearest_gift[1]):
                nearest_gift = (b, this_year)
    return {
        "total_users": len(users),
        "total_birthdays": total_birthdays,
        "gifts_needed": gifts_needed,
        "nearest": nearest[0] if nearest else None,
        "nearest_date": nearest[1].isoformat() if nearest else None,
        "nearest_gift": nearest_gift[0] if nearest_gift else None,
        "nearest_gift_date": nearest_gift[1].isoformat() if nearest_gift else None,
    }
