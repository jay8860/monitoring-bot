import sqlite3
from datetime import datetime, date, timedelta
import os

DB_NAME = "monitoring.db"

def get_connection():
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # Groups table to track active groups
    c.execute('''CREATE TABLE IF NOT EXISTS groups (
                    group_id INTEGER PRIMARY KEY,
                    title TEXT
                )''')
    
    # Users table - keyed by (user_id, group_id) to allow independent stats per group
    # Note: SQLite doesn't strictly enforce composite PKs easily in migration without drop, 
    # but for new init it's fine. If reusing existing DB, logic handles it.
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER,
                    group_id INTEGER,
                    full_name TEXT,
                    streak INTEGER DEFAULT 0,
                    last_submission_date TEXT,
                    total_submissions INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, group_id)
                )''')
    
    # Submissions table
    c.execute('''CREATE TABLE IF NOT EXISTS submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    group_id INTEGER,
                    timestamp TEXT,
                    FOREIGN KEY(user_id, group_id) REFERENCES users(user_id, group_id)
                )''')

    conn.commit()
    conn.close()

def register_group(group_id, title):
    """Registers or updates a group's title."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO groups (group_id, title) VALUES (?, ?)", (group_id, title))
    conn.commit()
    conn.close()

def get_all_active_groups():
    """Returns list of (group_id, title)."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT group_id, title FROM groups")
    results = c.fetchall()
    conn.close()
    return results

def add_user_if_not_exists(user_id, group_id, full_name):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id = ? AND group_id = ?", (user_id, group_id))
    if c.fetchone() is None:
        c.execute("INSERT INTO users (user_id, group_id, full_name, streak, total_submissions) VALUES (?, ?, ?, 0, 0)", 
                  (user_id, group_id, full_name))
        conn.commit()
    else:
        # Update name if it changed
        c.execute("UPDATE users SET full_name = ? WHERE user_id = ? AND group_id = ?", (full_name, user_id, group_id))
        conn.commit()
    conn.close()

def log_submission(user_id, group_id):
    """
    Logs a submission and updates streaks for a specific group.
    """
    conn = get_connection()
    c = conn.cursor()
    
    today_str = date.today().isoformat()
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()
    
    # Check if already submitted today in THIS group
    c.execute("SELECT id FROM submissions WHERE user_id = ? AND group_id = ? AND date(timestamp) = ?", 
              (user_id, group_id, today_str))
    if c.fetchone():
        # Get current streak
        c.execute("SELECT streak FROM users WHERE user_id = ? AND group_id = ?", (user_id, group_id))
        streak = c.fetchone()[0]
        conn.close()
        return 'already_submitted', streak

    # Record submission
    now_str = datetime.now().isoformat()
    c.execute("INSERT INTO submissions (user_id, group_id, timestamp) VALUES (?, ?, ?)", (user_id, group_id, now_str))
    
    # Update user stats
    c.execute("SELECT streak, last_submission_date, total_submissions FROM users WHERE user_id = ? AND group_id = ?", 
              (user_id, group_id))
    row = c.fetchone()
    
    # Handle edge case where user might not exist yet (though add_user should be called first)
    if not row:
         conn.close()
         return 'error', 0

    current_streak = row[0]
    last_date = row[1]
    total_submissions = row[2] + 1
    
    today_date = date.today()
    # Check for Monday -> Saturday skip (Sunday optional)
    is_monday = (today_date.weekday() == 0) # 0 is Monday
    saturday_str = (today_date - timedelta(days=2)).isoformat() if is_monday else None

    new_streak = 1
    if last_date == yesterday_str:
        new_streak = current_streak + 1
    elif is_monday and last_date == saturday_str:
        # User submitted on Saturday, skipped Sunday, submitting on Monday -> Streak continues
        new_streak = current_streak + 1
    elif last_date == today_str:
        new_streak = current_streak
    else:
        new_streak = 1
        
    c.execute("UPDATE users SET streak = ?, last_submission_date = ?, total_submissions = ? WHERE user_id = ? AND group_id = ?",
              (new_streak, today_str, total_submissions, user_id, group_id))
    
    conn.commit()
    conn.close()
    return 'new_submission', new_streak

def get_submitted_today_count(group_id):
    conn = get_connection()
    c = conn.cursor()
    today_str = date.today().isoformat()
    c.execute("SELECT COUNT(DISTINCT user_id) FROM submissions WHERE group_id = ? AND date(timestamp) = ?", (group_id, today_str))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_all_users(group_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id, full_name, streak FROM users WHERE group_id = ?", (group_id,))
    users = [{'user_id': r[0], 'full_name': r[1], 'streak': r[2]} for r in c.fetchall()]
    conn.close()
    return users

def get_submitted_users_today(group_id):
    # Wrapper for backward compatibility or simple usage
    return get_submitted_users_by_date(group_id, date.today().isoformat())

def get_submitted_users_by_date(group_id, date_str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT DISTINCT user_id FROM submissions WHERE group_id = ? AND date(timestamp) = ?", (group_id, date_str))
    ids = [r[0] for r in c.fetchall()]
    conn.close()
    return set(ids)

def get_top_performing_users(group_id, limit=5):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT full_name, streak FROM users WHERE group_id = ? AND streak > 0 ORDER BY streak DESC LIMIT ?", (group_id, limit))
    results = c.fetchall()
    conn.close()
    return results

def get_submissions_between_dates(group_id, start_date_str, end_date_str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT user_id, date(timestamp) 
        FROM submissions 
        WHERE group_id = ? AND date(timestamp) >= ? AND date(timestamp) <= ?
    """, (group_id, start_date_str, end_date_str))
    results = c.fetchall()
    conn.close()
    return results
