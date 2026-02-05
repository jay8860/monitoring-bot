import logging
import pytz
import os
import asyncio
from datetime import time, datetime
import database
import reports
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from dotenv import load_dotenv
from ultralytics import YOLO
import random
import messages

# Load environment variables
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# Silence httpx (telegram polling) logs
logging.getLogger("httpx").setLevel(logging.WARNING)

# Removed GLOBAL GROUP_CHAT_ID as we now support multiple groups

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! Monitoring Bot is active.\n✅ Ready to track inspections.")

# Load model (globally to cache it)
model = YOLO('yolov8n.pt')

async def register_group_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Middleware-like handler to register groups whenever a message is received.
    """
    if update.effective_chat.type in ['group', 'supergroup']:
        chat_id = update.effective_chat.id
        title = update.effective_chat.title
        database.register_group(chat_id, title)

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Register/Update group
    await register_group_middleware(update, context)
    
    # If generic photo outside a group (DM), ignore or handle differently.
    # For now, we only log inspection if it's in a known group context or we treat DM as separate context?
    # Logic: Submissions usually happen in groups.
    if update.effective_chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("Please send photos in the monitoring group.")
        return

    group_id = update.effective_chat.id
    user = update.message.from_user
    full_name = user.full_name
    
    # --- Person Detection Start ---
    # Download photo
    photo_file = await update.message.photo[-1].get_file()
    file_path = f"temp_{user.id}_{datetime.now().timestamp()}.jpg"
    await photo_file.download_to_drive(file_path)
    
    # Run Inference
    results = await asyncio.to_thread(model, file_path, verbose=False)
    
    # Count persons (captured for metadata)
    person_count = 0
    for r in results:
        for cls in r.boxes.cls:
            if int(cls) == 0:
                person_count += 1
                
    # Cleanup
    if os.path.exists(file_path):
        os.remove(file_path)
    # --- Person Detection End ---

    # Register/Update user (specific to this group)
    database.add_user_if_not_exists(user.id, group_id, full_name)
    
    # Log submission
    status, streak = database.log_submission(user.id, group_id)
    
    # Reply logic
    if status == 'new_submission':
        msg = f"Received submission from {full_name}. ✅\nStreak: {streak} days."
        await update.message.reply_text(msg, reply_to_message_id=update.message.id)
        
    elif status == 'already_submitted':
        # Silencing duplicate replies to declutter group
        # await update.message.reply_text(f"{full_name}, you have already submitted today.", reply_to_message_id=update.message.id)
        pass

# Scheduled Jobs
async def send_daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    groups = database.get_all_active_groups()
    msg = random.choice(messages.MOTIVATIONAL_QUOTES)
    
    for group_id, title in groups:
        try:
            await context.bot.send_message(chat_id=group_id, text=msg, parse_mode='Markdown')
        except Exception as e:
            logging.error(f"Failed to send reminder to {title} ({group_id}): {e}")

async def report_2pm(context: ContextTypes.DEFAULT_TYPE):
    groups = database.get_all_active_groups()
    
    for group_id, title in groups:
        try:
            count = database.get_submitted_today_count(group_id)
            msg = f"📊 *2 PM Status Update*\n\n{count} members have submitted their report today.\nPlease submit ASAP if you haven't yet."
            await context.bot.send_message(chat_id=group_id, text=msg, parse_mode='Markdown')
        except Exception as e:
            logging.error(f"Failed to send 2pm report to {title} ({group_id}): {e}")

async def report_6pm(context: ContextTypes.DEFAULT_TYPE):
    groups = database.get_all_active_groups()
    
    for group_id, title in groups:
        try:
            # 1. Stats
            count = database.get_submitted_today_count(group_id)
            
            # 2. Daily Summary (Max/Min)
            summary_msg = reports.get_daily_stats(group_id)
            
            full_msg = f"🌇 *Daily Final Report*\n\nTotal Submissions: {count}\n\n{summary_msg}"
            
            await context.bot.send_message(chat_id=group_id, text=full_msg, parse_mode='Markdown')
            
            # 3. Missing Report Excel
            file_path = reports.generate_missing_workers_excel(group_id)
            if file_path:
                await context.bot.send_document(
                    chat_id=group_id, 
                    document=open(file_path, 'rb'),
                    caption="📄 List of members who did not submit today."
                )
                try:
                    os.remove(file_path)
                except:
                    pass
        except Exception as e:
            logging.error(f"Failed to send 6pm report to {title} ({group_id}): {e}")

async def report_weekly(context: ContextTypes.DEFAULT_TYPE):
    """Sends the weekly attendance report (Mon-Sun) to ALL groups"""
    groups = database.get_all_active_groups()
    
    for group_id, title in groups:
        try:
            report_msg = reports.generate_weekly_report(group_id)
            await context.bot.send_message(chat_id=group_id, text=report_msg, parse_mode='Markdown')
        except Exception as e:
             logging.error(f"Failed to send weekly report to {title} ({group_id}): {e}")

async def manual_report_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only works in groups
    if update.effective_chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("This command only works in groups.")
        return

    # Register in case it's new
    await register_group_middleware(update, context)
    group_id = update.effective_chat.id

    count = database.get_submitted_today_count(group_id)
    summary_msg = reports.get_daily_stats(group_id)
    full_msg = f"📊 *Current Report*\n\nTotal Submissions: {count}\n\n{summary_msg}"
    
    await update.message.reply_text(full_msg, parse_mode='Markdown')
    
    file_path = reports.generate_missing_workers_excel(group_id)
    if file_path:
        await context.bot.send_document(
            chat_id=group_id, 
            document=open(file_path, 'rb'),
            caption="📄 Missing Submissions List"
        )
        try:
            os.remove(file_path)
        except:
            pass

async def missing_report_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only works in groups
    if update.effective_chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("This command only works in groups.")
        return

    await register_group_middleware(update, context)
    group_id = update.effective_chat.id
    
    # Parse date argument
    target_date = None
    if context.args:
        try:
            date_str = context.args[0]
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            await update.message.reply_text("Invalid date format. Use YYYY-MM-DD.\nExample: /missing 2023-10-27")
            return
    else:
        target_date = datetime.now().date()
        
    date_label = target_date.isoformat()
    
    file_path = reports.generate_missing_workers_excel(group_id, target_date)
    if file_path:
        await context.bot.send_document(
            chat_id=group_id, 
            document=open(file_path, 'rb'),
            caption=f"📄 Missing Submissions List ({date_label})"
        )
        try:
            os.remove(file_path)
        except:
            pass
    else:
        await update.message.reply_text(f"Everyone has submitted for {date_label}! ✅")

async def send_saturday_report(context: ContextTypes.DEFAULT_TYPE):
    """
    Sends 'Past 7 Days' stats and 'Low Attendance' Excel on Saturday 8 AM.
    """
    groups = database.get_all_active_groups()
    
    for group_id, title in groups:
        try:
            # 1. Past 7 Days Stats
            stats_msg = reports.get_past_week_stats(group_id)
            await context.bot.send_message(chat_id=group_id, text=stats_msg, parse_mode='Markdown')
            
            # 2. Low Attendance Excel
            file_path = reports.generate_low_attendance_excel(group_id)
            if file_path:
                await context.bot.send_document(
                    chat_id=group_id, 
                    document=open(file_path, 'rb'),
                    caption="📄 Low Attendance Alert (< 3 days Mon-Fri)"
                )
                try: os.remove(file_path)
                except: pass
            else:
                await context.bot.send_message(chat_id=group_id, text="✅ Everyone has good attendance this week (> 3 days)!")
                
        except Exception as e:
            logging.error(f"Failed to send Saturday report to {title} ({group_id}): {e}")

async def weekly_report_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("This command only works in groups.")
        return
        
    await register_group_middleware(update, context)
    group_id = update.effective_chat.id
    
    stats_msg = reports.get_past_week_stats(group_id)
    await update.message.reply_text(stats_msg, parse_mode='Markdown')

async def fortnightly_report_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("This command only works in groups.")
        return
    
    await register_group_middleware(update, context)
    group_id = update.effective_chat.id
    
    today = datetime.now().date()
    # "Fortnightly" = Last 15 days
    start_date = today - timedelta(days=14) 
    
    await update.message.reply_text(f"⏳ Generating Fortnightly Report ({start_date} to {today})...")
    
    file_path = reports.generate_attendance_register(group_id, start_date, today)
    
    if file_path:
        await context.bot.send_document(
            chat_id=group_id,
            document=open(file_path, 'rb'),
            caption=f"📅 Fortnightly Attendance Register\n({start_date} to {today})"
        )
        try: os.remove(file_path)
        except: pass
    else:
        await update.message.reply_text("No data found for this period.")

async def monthly_report_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("This command only works in groups.")
        return
    
    await register_group_middleware(update, context)
    group_id = update.effective_chat.id
    
    today = datetime.now().date()
    # "Monthly" = Last 30 days
    start_date = today - timedelta(days=29) 
    
    await update.message.reply_text(f"⏳ Generating Monthly Report ({start_date} to {today})...")
    
    file_path = reports.generate_attendance_register(group_id, start_date, today)
    
    if file_path:
        await context.bot.send_document(
            chat_id=group_id,
            document=open(file_path, 'rb'),
            caption=f"📅 Monthly Attendance Register\n({start_date} to {today})"
        )
        try: os.remove(file_path)
        except: pass
    else:
        await update.message.reply_text("No data found for this period.")

def main():
    if not TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not found in .env file")
        # return

    database.init_db()
    
    application = ApplicationBuilder().token(TOKEN if TOKEN else "DUMMY_TOKEN").build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("report", manual_report_handler))
    application.add_handler(CommandHandler("missing", missing_report_handler))
    application.add_handler(CommandHandler("weekly", weekly_report_handler))
    application.add_handler(CommandHandler("fortnightly", fortnightly_report_handler))
    application.add_handler(CommandHandler("monthly", monthly_report_handler))
    
    # Handles photos
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    
    # Capture text to register groups even if they don't send photos immediately
    async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await register_group_middleware(update, context)
            
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_handler))

    # Job Queue
    job_queue = application.job_queue
    tz = pytz.timezone('Asia/Kolkata')
    
    # 8:00 AM - Reminder
    job_queue.run_daily(send_daily_reminder, time(hour=8, minute=0, tzinfo=tz))

    # 2:00 PM - Status
    job_queue.run_daily(report_2pm, time(hour=14, minute=0, tzinfo=tz)) 
    
    # 6:00 PM - Daily Final Report
    job_queue.run_daily(report_6pm, time(hour=18, minute=0, tzinfo=tz))

    # Sunday 8:00 PM - Weekly Report
    # days=(6,) means Sunday (Mon=0)
    job_queue.run_daily(report_weekly, time(hour=20, minute=0, tzinfo=tz), days=(6,))
    
    # Saturday 8:00 AM - Stats & Low Attendance Report
    # days=(5,) means Saturday
    job_queue.run_daily(send_saturday_report, time(hour=8, minute=0, tzinfo=tz), days=(5,))

    print("Monitoring Bot is running (Multi-Group Mode)...")
    
    if TOKEN:
        application.run_polling()
    else:
        print("No token provided, polling skipped.")

if __name__ == '__main__':
    main()
