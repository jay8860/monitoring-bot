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

# Global variable to store the group chat ID
GROUP_CHAT_ID = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! Monitoring Bot is active.\n✅ Ready to track inspections.")

# Load model (globally to cache it)
model = YOLO('yolov8n.pt')

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GROUP_CHAT_ID
    user = update.message.from_user
    chat_id = update.effective_chat.id
    
    # Store group ID if this is a group
    if update.effective_chat.type in ['group', 'supergroup']:
        GROUP_CHAT_ID = chat_id
        
    full_name = user.full_name
    
    # --- Person Detection Start ---
    # Download photo
    photo_file = await update.message.photo[-1].get_file()
    file_path = f"temp_{user.id}.jpg"
    await photo_file.download_to_drive(file_path)
    
    # Run Inference
    # Run in thread to avoid blocking event loop
    results = await asyncio.to_thread(model, file_path, verbose=False)
    
    # Count persons (captured for metadata, but no warning enforced)
    person_count = 0
    for r in results:
        for cls in r.boxes.cls:
            if int(cls) == 0:
                person_count += 1
                
    # Cleanup
    if os.path.exists(file_path):
        os.remove(file_path)
    # --- Person Detection End ---

    # Register/Update user
    database.add_user_if_not_exists(user.id, full_name)
    
    # Log submission
    status, streak = database.log_submission(user.id)
    
    # Reply logic
    if status == 'new_submission':
        msg = f"Received submission from {full_name}. ✅\nStreak: {streak} days."
        await update.message.reply_text(msg, reply_to_message_id=update.message.id)
        
    elif status == 'already_submitted':
        await update.message.reply_text(f"{full_name}, you have already submitted today.", reply_to_message_id=update.message.id)

# Scheduled Jobs
async def send_daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    if GROUP_CHAT_ID:
        # Generic Reminder
        msg = random.choice(messages.MOTIVATIONAL_QUOTES)
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=msg, parse_mode='Markdown')

async def report_2pm(context: ContextTypes.DEFAULT_TYPE):
    if GROUP_CHAT_ID:
        count = database.get_submitted_today_count()
        msg = f"📊 *2 PM Status Update*\n\n{count} members have submitted their report today.\nPlease submit ASAP if you haven't yet."
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=msg, parse_mode='Markdown')

async def report_6pm(context: ContextTypes.DEFAULT_TYPE):
    if GROUP_CHAT_ID:
        # 1. Stats
        count = database.get_submitted_today_count()
        
        # 2. Daily Summary (Max/Min)
        summary_msg = reports.get_daily_stats()
        
        full_msg = f"🌇 *Daily Final Report*\n\nTotal Submissions: {count}\n\n{summary_msg}"
        
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=full_msg, parse_mode='Markdown')
        
        # 3. Missing Report Excel
        file_path = reports.generate_missing_workers_excel()
        if file_path:
            await context.bot.send_document(
                chat_id=GROUP_CHAT_ID, 
                document=open(file_path, 'rb'),
                caption="📄 List of members who did not submit today."
            )
            # Cleanup
            try:
                os.remove(file_path)
            except:
                pass

async def report_weekly(context: ContextTypes.DEFAULT_TYPE):
    """Sends the weekly attendance report (Mon-Sun)"""
    if GROUP_CHAT_ID:
        # Generate text report
        report_msg = reports.generate_weekly_report()
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=report_msg, parse_mode='Markdown')

async def manual_report_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Same as 6pm report but on demand
    count = database.get_submitted_today_count()
    summary_msg = reports.get_daily_stats()
    full_msg = f"📊 *Current Report*\n\nTotal Submissions: {count}\n\n{summary_msg}"
    
    await update.message.reply_text(full_msg, parse_mode='Markdown')
    
    file_path = reports.generate_missing_workers_excel()
    if file_path:
        await context.bot.send_document(
            chat_id=update.effective_chat.id, 
            document=open(file_path, 'rb'),
            caption="📄 Missing Submissions List"
        )
        try:
            os.remove(file_path)
        except:
            pass

def main():
    if not TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not found in .env file")
        # In a real scenario we might want to exit, but for dev we can just print
        # return

    database.init_db()
    
    application = ApplicationBuilder().token(TOKEN if TOKEN else "DUMMY_TOKEN").build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("report", manual_report_handler))
    
    # Handles photos
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    
    # Update group ID on any text message too (to ensure we capture it if bot is added and someone talks)
    async def update_group_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
        global GROUP_CHAT_ID
        if update.effective_chat.type in ['group', 'supergroup']:
            GROUP_CHAT_ID = update.effective_chat.id
            
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), update_group_id))

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
    
    print("Monitoring Bot is running...")
    
    # Only run polling if token exists, otherwise just stay up for checks (or allow it to fail gracefully in dev)
    if TOKEN:
        application.run_polling()
    else:
        print("No token provided, polling skipped.")

if __name__ == '__main__':
    main()
