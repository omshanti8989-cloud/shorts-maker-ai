import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).resolve().parent / "users.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes the users and transactions tables."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            free_credits INTEGER DEFAULT 1,
            is_subscribed INTEGER DEFAULT 0,
            subscription_plan TEXT DEFAULT 'free',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            video_type TEXT,
            shorts_count INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def get_or_create_user(email):
    """Retrieves user by email or creates a new one with 1 free credit."""
    email = email.strip().lower()
    if not email:
        return None

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()

    if not user:
        cursor.execute(
            "INSERT INTO users (email, free_credits, is_subscribed) VALUES (?, 1, 0)",
            (email,)
        )
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
    else:
        # Update last active timestamp
        cursor.execute("UPDATE users SET last_active = ? WHERE email = ?", (datetime.now(), email))
        conn.commit()

    user_dict = dict(user)
    conn.close()
    return user_dict


def can_generate_video(email):
    """
    Checks if a user is permitted to generate a video.
    Returns: (allowed: bool, reason: str, user_dict)
    """
    user = get_or_create_user(email)
    if not user:
        return False, "Please enter your email to proceed.", None

    if user["is_subscribed"]:
        return True, "Active Pro Subscription", user

    if user["free_credits"] > 0:
        return True, f"{user['free_credits']} Free Video Credit Available", user

    return False, "You have used your 1 free video credit. Please subscribe to continue.", user


def use_credit(email, video_type="upload", shorts_count=1):
    """
    Deducts 1 free credit if user is not subscribed.
    Logs usage into usage_logs table.
    """
    email = email.strip().lower()
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return False

    if not user["is_subscribed"] and user["free_credits"] > 0:
        cursor.execute(
            "UPDATE users SET free_credits = free_credits - 1 WHERE email = ?",
            (email,)
        )

    cursor.execute(
        "INSERT INTO usage_logs (email, video_type, shorts_count) VALUES (?, ?, ?)",
        (email, video_type, shorts_count)
    )

    conn.commit()
    conn.close()
    return True


def activate_subscription(email, plan="pro"):
    """Upgrades a user to unlimited Pro access."""
    email = email.strip().lower()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET is_subscribed = 1, subscription_plan = ? WHERE email = ?",
        (plan, email)
    )
    conn.commit()
    conn.close()
    return True


def reset_user(email):
    """Helper for testing: resets credits to 1 and removes subscription."""
    email = email.strip().lower()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET free_credits = 1, is_subscribed = 0 WHERE email = ?",
        (email,)
    )
    conn.commit()
    conn.close()
    return True


# Auto-initialize database on load
init_db()
