import os
import asyncio

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = await update.message.reply_text("1")

    number = 1

    while True:
        await asyncio.sleep(1)

        number += 1

        try:
            await message.edit_text(str(number))
        except Exception as e:
            print(f"Bot stopped: {e}")
            break


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN تنظیم نشده!")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
