import pandas as pd
from datetime import date, timedelta
import database
import os

def generate_missing_workers_excel(group_id, date_obj=None):
    if date_obj is None:
        date_obj = date.today()
    
    date_str = date_obj.isoformat()
    all_users = database.get_all_users(group_id) # list of dicts
    
    # Use generic date function
    submitted_ids = database.get_submitted_users_by_date(group_id, date_str) 
    
    missing_workers = []
    for user in all_users:
        if user['user_id'] not in submitted_ids:
            missing_workers.append({
                'Name': user['full_name'],
                'Telegram ID': user['user_id'],
                'Date': date_str
            })
            
    if not missing_workers:
        return None
        
    df = pd.DataFrame(missing_workers)
    filename = f"missing_report_g{group_id}_{date_str}.xlsx"
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

def get_past_week_stats(group_id):
    """
    Generates text stats for the past 7 days (including today).
    Useful for /weekly command which can be run any day.
    """
    today = date.today()
    start_date = today - timedelta(days=6) # 7 days inclusive
    
    start_str = start_date.isoformat()
    end_str = today.isoformat()
    
    submissions = database.get_submissions_between_dates(group_id, start_str, end_str)
    
    user_counts = {}
    for sub in submissions:
        uid = sub[0]
        user_counts[uid] = user_counts.get(uid, 0) + 1
        
    all_users = database.get_all_users(group_id)
    report_data = []
    for user in all_users:
        uid = user['user_id']
        name = user['full_name']
        count = user_counts.get(uid, 0)
        report_data.append({'Name': name, 'Visits': count})
        
    report_data.sort(key=lambda x: x['Visits'], reverse=True)
    
    msg = f"📅 *Past 7 Days Report ({start_str} to {end_str})*\n\n"
    for item in report_data:
        msg += f"- {item['Name']}: {item['Visits']} days\n"
        
    return msg

def generate_low_attendance_excel(group_id):
    """
    Generates Excel list of people with < 3 submissions in the last week (Mon-Sat).
    To be run on Saturday 8 AM.
    """
    # Logic: Last Mon to Last Sat (which is yesterday relative to Sunday, or today relative to Sat).
    # Assuming this runs on Saturday morning, we look at Mon (5 days ago) to Sat (today) - wait, if run at 8AM Sat, Sat is just starting.
    # Request says: "list on Saturday 8 AM also of people who have not done inspection less than three times in the last week Monday to Saturday"
    # Technically Mon-Sat implies including Saturday. But at 8 AM Saturday, Saturday isn't over.
    # Interpretation: List people who have done < 3 times from Monday to *Friday*? Or maybe previous week?
    # Logic: "last week Monday to Saturday".
    # Best approach: If run on Saturday AM, check Monday to Friday (5 days). If user attended < 3 times.
    # Alternatively, if meant for "end of week", maybe check Monday to Friday.
    
    today = date.today() # Saturday
    # Monday of this week
    monday = today - timedelta(days=today.weekday()) 
    # Check Mon -> Fri (5 days)
    # Or should we check Mon -> Sat (today)? But day just started.
    # Let's check Mon -> Fri to be safe as data is complete.
    
    # Actually, let's include Saturday but effectively it's 0 for Saturday so far.
    # Let's stick to Mon-Fri (5 days) or Mon-Today (6 days).
    # "less than three times in the last week" suggests looking at ~6 days.
    
    # Let's check Monday to Friday (5 days).
    friday = today - timedelta(days=1)
    
    start_str = monday.isoformat()
    end_str = friday.isoformat()
    
    submissions = database.get_submissions_between_dates(group_id, start_str, end_str)
    user_counts = {}
    for sub in submissions:
        uid = sub[0]
        user_counts[uid] = user_counts.get(uid, 0) + 1
        
    all_users = database.get_all_users(group_id)
    low_attendance = []
    
    for user in all_users:
        uid = user['user_id']
        count = user_counts.get(uid, 0)
        if count < 3:
            low_attendance.append({
                'Name': user['full_name'],
                'Telegram ID': user['user_id'],
                'Visits (Mon-Fri)': count
            })
            
    if not low_attendance:
        return None
        
    df = pd.DataFrame(low_attendance)
    filename = f"low_attendance_g{group_id}_{start_str}_to_{end_str}.xlsx"
    df.to_excel(filename, index=False)
    return filename

def generate_attendance_register(group_id, start_date, end_date):
    """
    Generates a Matrix Report (Attendance Register).
    Rows: Users
    Columns: Dates from start_date to end_date
    Values: 'P' (Present) or '' (Absent)
    Sorted by Attendance Percentage (Ascending) to show least active first.
    """
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()
    
    # 1. Get all submissions
    submissions = database.get_submissions_between_dates(group_id, start_str, end_str) # List of (user_id, date_str)
    
    # 2. Get all users
    all_users = database.get_all_users(group_id) # List of dicts
    
    # 3. Create Date Range
    delta = end_date - start_date
    date_list = [start_date + timedelta(days=i) for i in range(delta.days + 1)]
    date_columns = [d.isoformat() for d in date_list]
    
    # 4. Build Matrix Data
    # Structure: {'User ID': ..., 'Name': ..., 'Date1': 'P', 'Date2': '' ...}
    
    # Map submissions for quick lookup: {(user_id, date_str): True}
    submission_map = set()
    for sub in submissions:
        # sub is (user_id, date_str)
        submission_map.add((sub[0], sub[1]))
        
    matrix_data = []
    
    for user in all_users:
        uid = user['user_id']
        name = user['full_name']
        
        row = {
            'Name': name,
            # 'Telegram ID': uid 
        }
        
        present_count = 0
        total_days = len(date_columns)
        
        for d_str in date_columns:
            if (uid, d_str) in submission_map:
                row[d_str] = 'P'
                present_count += 1
            else:
                row[d_str] = '' # Empty for absent
                
        attendance_pct = (present_count / total_days) * 100 if total_days > 0 else 0
        
        row['Total Present'] = present_count
        row['Total Days'] = total_days
        row['Percentage'] = round(attendance_pct, 1)
        
        matrix_data.append(row)
        
    # 5. Create DataFrame
    if not matrix_data:
        return None
        
    df = pd.DataFrame(matrix_data)
    
    # 6. Sort by Percentage (low to high)
    df.sort_values(by='Percentage', ascending=True, inplace=True)
    
    # 7. Reorder columns to put Stats first or last? 
    # Let's keep Name, Percentage, Total Present, then Dates...
    cols = ['Name', 'Percentage', 'Total Present'] + date_columns
    df = df[cols]
    
    filename = f"attendance_register_g{group_id}_{start_str}_to_{end_str}.xlsx"
    df.to_excel(filename, index=False)
    
    return filename
