import pandas as pd
from datetime import date, timedelta
import database
import os

def generate_missing_workers_excel(group_id):
    today_str = date.today().isoformat()
    all_users = database.get_all_users(group_id) # list of dicts
    submitted_ids = database.get_submitted_users_today(group_id) # set of ids
    
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
    # Include group_id in filename to prevent collisions if running parallel (though asyncio is single threaded usually)
    filename = f"missing_report_g{group_id}_{today_str}.xlsx"
    df.to_excel(filename, index=False)
    return filename

def get_daily_stats(group_id):
    """Generates a text summary for the daily report (6 PM)."""
    top_streaks = database.get_top_performing_users(group_id, 5)
    
    msg = "📊 *Daily Inspection Summary *\n\n"
    if top_streaks:
        msg += "*Most Consistent Contributors (Streak):*\n"
        for i, (name, streak) in enumerate(top_streaks, 1):
            msg += f"{i}. {name} - {streak} days 🔥\n"
    else:
        msg += "No streaks recorded yet."
        
    return msg

def generate_weekly_report(group_id, end_date=None):
    """
    Generates a report for the week ending on `end_date` (default today).
    Week is defined as Monday to Sunday.
    """
    if end_date is None:
        end_date = date.today()
        
    start_date = end_date - timedelta(days=end_date.weekday())
    
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()
    
    # Get all submissions in this range for this GROUP
    submissions = database.get_submissions_between_dates(group_id, start_str, end_str)
    
    # Count visits per user
    user_counts = {} # {user_id: count}
    for sub in submissions:
        uid = sub[0]
        user_counts[uid] = user_counts.get(uid, 0) + 1
        
    # Get all known users in this GROUP
    all_users = database.get_all_users(group_id)
    
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
