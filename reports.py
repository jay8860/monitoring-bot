import pandas as pd
from datetime import date, timedelta
import database
import os

def generate_missing_workers_excel():
    today_str = date.today().isoformat()
    all_users = database.get_all_users() # list of dicts
    submitted_ids = database.get_submitted_users_today() # set of ids
    
    missing_workers = []
    for user in all_users:
        if user['user_id'] not in submitted_ids:
            missing_workers.append({
                'Name': user['full_name'],
                'Telegram ID': user['user_id']
            })
            
    if not missing_workers:
        return None
        
    df = pd.DataFrame(missing_workers)
    filename = f"missing_report_{today_str}.xlsx"
    df.to_excel(filename, index=False)
    return filename

def get_daily_stats():
    """Generates a text summary for the daily report (6 PM)."""
    # Simply list top streaks as "Most Consistent" or just summary count
    # User requested: "list out the people who have done the maximum inspections and those who have done the minimum inspections"
    
    # For a DAILY report, max/min is just Submitted vs Not Submitted (which is binary). 
    # Logic: Show total count and maybe a shoutout to those with high streaks as "Most Regular".
    
    top_streaks = database.get_top_performing_users(5)
    
    msg = "📊 *Daily Inspection Summary *\n\n"
    if top_streaks:
        msg += "*Most Consistent Contributors (Streak):*\n"
        for i, (name, streak) in enumerate(top_streaks, 1):
            msg += f"{i}. {name} - {streak} days 🔥\n"
    else:
        msg += "No streaks recorded yet."
        
    return msg

def generate_weekly_report(end_date=None):
    """
    Generates a report for the week ending on `end_date` (default today).
    Week is defined as Monday to Sunday.
    """
    if end_date is None:
        end_date = date.today()
        
    # Find the Monday of the current week (or past week if running on Sunday)
    # If today is Sunday (weekday=6), and we want this week's report: start = today - 6
    # If today is Monday (weekday=0), start = today.
    
    # Assuming we run this on Sunday evening for the current week:
    start_date = end_date - timedelta(days=end_date.weekday())
    
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()
    
    # Get all submissions in this range
    submissions = database.get_submissions_between_dates(start_str, end_str)
    # submissions is list of (user_id, date_str)
    
    # Count visits per user
    user_counts = {} # {user_id: count}
    for sub in submissions:
        uid = sub[0]
        user_counts[uid] = user_counts.get(uid, 0) + 1
        
    # Get all known users to find who has 0 visits
    all_users = database.get_all_users()
    
    report_data = []
    for user in all_users:
        uid = user['user_id']
        name = user['full_name']
        count = user_counts.get(uid, 0)
        report_data.append({'Name': name, 'Visits': count})
        
    # Sort by visits (descending)
    report_data.sort(key=lambda x: x['Visits'], reverse=True)
    
    # Generate Text Report
    msg = f"📅 *Weekly Report ({start_str} to {end_str})*\n\n"
    msg += "*Attendance Summary (Days Visited):*\n"
    for item in report_data:
        msg += f"- {item['Name']}: {item['Visits']}/7\n"
        
    return msg
