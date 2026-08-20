import os
import asyncio
import time

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


BOT_TOKEN = os.getenv("BOT_TOKEN")

# برای نگه داشتن تایمرهای فعال
active_timers = {}


def format_time(seconds):
    seconds = int(seconds)

    days = seconds // 86400
    seconds %= 86400

    hours = seconds // 3600
    seconds %= 3600

    minutes = seconds // 60
    seconds %= 60

    return (
        f"⏱️ زمان اجرای بات\n\n"
        f"روز: {days}\n"
        f"ساعت: {hours:02d}\n"
        f"دقیقه: {minutes:02d}\n"
        f"ثانیه: {seconds:02d}"
    )


async def uptime_counter(message):
    start_time = time.monotonic()
    last_second = -1

    try:
        while True:
            elapsed = int(time.monotonic() - start_time)

            # فقط وقتی ثانیه تغییر کرده پیام را ادیت کن
            if elapsed != last_second:
                last_second = elapsed

                try:
                    await message.edit_text(format_time(elapsed))
                except Exception as e:
                    print(f"Edit error: {e}")

            # کمی بیشتر از یک ثانیه صبر نمی‌کنیم؛
            # زمان واقعی با monotonic محاسبه می‌شود.
            await asyncio.sleep(0.2)

    except asyncio.CancelledError:
        print("Timer stopped.")
        raise


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # اگر قبلاً برای این چت تایمر فعال است،
    # تایمر جدید ایجاد نکن
    if chat_id in active_timers:
        await update.message.reply_text(
            "⏱️ تایمر این چت از قبل در حال اجراست."
        )
        return

    # فقط یک پیام ساخته می‌شود
    message = await update.message.reply_text(
        format_time(0)
    )

    # تایمر را در پس‌زمینه اجرا می‌کنیم
    task = asyncio.create_task(
        uptime_counter(message)
    )

    active_timers[chat_id] = task

    # وقتی Task تمام شد، از لیست حذف شود
    def cleanup(_):
        active_timers.pop(chat_id, None)

    task.add_done_callback(cleanup)


def main():
    if not BOT_TOKEN:
        raise ValueError(
            "BOT_TOKEN تنظیم نشده است!"
        )

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(
        CommandHandler("start", start)
    )

    print("Bot is running...")

    app.run_polling()


if __name__ == "__main__":
    main()
