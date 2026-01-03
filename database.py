import sqlite3
from datetime import datetime, date, timedelta
import os

DB_NAME = "monitoring.db"

def get_connection():
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    full_name TEXT,
                    streak INTEGER DEFAULT 0,
                    last_submission_date TEXT,
                    total_submissions INTEGER DEFAULT 0
                )''')
    
    # Submissions table
    c.execute('''CREATE TABLE IF NOT EXISTS submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    timestamp TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )''')

    conn.commit()
    conn.close()

def add_user_if_not_exists(user_id, full_name):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if c.fetchone() is None:
        c.execute("INSERT INTO users (user_id, full_name, streak, total_submissions) VALUES (?, ?, 0, 0)", (user_id, full_name))
        conn.commit()
    else:
        # Update name if it changed (optional, but good for display)
        c.execute("UPDATE users SET full_name = ? WHERE user_id = ?", (full_name, user_id))
        conn.commit()
    conn.close()

def log_submission(user_id):
    """
    Logs a submission and updates streaks.
    Returns (status, streak) where:
    - status: 'new_submission', 'already_submitted', 'missed_streak'
    - streak: current streak count
    """
    conn = get_connection()
    c = conn.cursor()
    
    today_str = date.today().isoformat()
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()
    
    # Check if already submitted today
    c.execute("SELECT id FROM submissions WHERE user_id = ? AND date(timestamp) = ?", (user_id, today_str))
    if c.fetchone():
        # Get current streak to return
        c.execute("SELECT streak FROM users WHERE user_id = ?", (user_id,))
        streak = c.fetchone()[0]
        conn.close()
        return 'already_submitted', streak

    # Record submission
    now_str = datetime.now().isoformat()
    c.execute("INSERT INTO submissions (user_id, timestamp) VALUES (?, ?)", (user_id, now_str))
    
    # Update user stats
    c.execute("SELECT streak, last_submission_date, total_submissions FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    current_streak = row[0]
    last_date = row[1]
    total_submissions = row[2] + 1
    
    new_streak = 1
    if last_date == yesterday_str:
        new_streak = current_streak + 1
    elif last_date == today_str:
        # Should be caught by the check above, but purely defensive
        new_streak = current_streak
    else:
        # Streak broken or first time
        new_streak = 1
        
    c.execute("UPDATE users SET streak = ?, last_submission_date = ?, total_submissions = ? WHERE user_id = ?",
              (new_streak, today_str, total_submissions, user_id))
    
    conn.commit()
    conn.close()
    return 'new_submission', new_streak

def get_submitted_today_count():
    conn = get_connection()
    c = conn.cursor()
    today_str = date.today().isoformat()
    c.execute("SELECT COUNT(DISTINCT user_id) FROM submissions WHERE date(timestamp) = ?", (today_str,))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_all_users():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id, full_name, streak FROM users")
    users = [{'user_id': r[0], 'full_name': r[1], 'streak': r[2]} for r in c.fetchall()]
    conn.close()
    return users

def get_submitted_users_today():
    conn = get_connection()
    c = conn.cursor()
    today_str = date.today().isoformat()
    c.execute("SELECT DISTINCT user_id FROM submissions WHERE date(timestamp) = ?", (today_str,))
    ids = [r[0] for r in c.fetchall()]
    conn.close()
    return set(ids)

def get_top_performing_users(limit=5):
    """Returns top users by streak for report display."""
    conn = get_connection()
    c = conn.cursor()
    # Get top streaks greater than 0
    c.execute("SELECT full_name, streak FROM users WHERE streak > 0 ORDER BY streak DESC LIMIT ?", (limit,))
    results = c.fetchall()
    conn.close()
    return results

def get_submissions_between_dates(start_date_str, end_date_str):
    """
    Returns a list of (user_id, date_str) for submissions in range [start, end].
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT user_id, date(timestamp) 
        FROM submissions 
        WHERE date(timestamp) >= ? AND date(timestamp) <= ?
    """, (start_date_str, end_date_str))
    results = c.fetchall()
    conn.close()
    return results
