import json
import os
import time
from datetime import datetime, timezone, timedelta

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATA_FILE = "size_data.json"
COOLDOWN_MINUTES = 60 * 2         # طول هر بازه (به دقیقه) — الان 2 ساعت. باید 1440 (شبانه‌روز) رو بدون باقیمونده تقسیم کنه
POINTS_PER_SIZE = 1
TIMEZONE = timezone(timedelta(hours=3, minutes=30))  # وقت ایران (UTC+3:30)

BASE_ADMIN_IDS = [7733000222]

ADMIN_COMMANDS = (
    "📋 دستورات ادمین:\n"
    "/addpoint <مقدار> — ریپلای کن، سایز اضافه کن\n"
    "/removepoint <مقدار> — ریپلای کن، سایز کم کن\n"
    "/resetpoint — ریپلای کن، سایز رو صفر کن\n"
    "/ban — ریپلای کن، بن کن\n"
    "/unban — ریپلای کن، رفع بن کن\n"
    "/addadmin — ریپلای کن، ادمین کن\n"
    "/resetcooldown — ریپلای کن، کولداون رو صفر کن"
)


# ---------------- ذخیره‌سازی ----------------

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"_admins": [], "chats": {}}


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_chat(data, chat_id):
    chats = data.setdefault("chats", {})
    return chats.setdefault(str(chat_id), {})


def get_user(chat_data, user_id, name=None):
    uid = str(user_id)
    if uid not in chat_data:
        chat_data[uid] = {"points": 0, "last_claim": 0, "banned": False, "name": name or uid}
    if name:
        chat_data[uid]["name"] = name
    return chat_data[uid]


def get_admin_ids(data):
    return set(BASE_ADMIN_IDS) | set(data.get("_admins", []))


def is_admin(user_id, data=None):
    if data is None:
        data = load_data()
    return user_id in get_admin_ids(data)


def clock(ts):
    return datetime.fromtimestamp(ts, tz=TIMEZONE).strftime("%H:%M")


# ---------------- منطق بازه‌های زمانی (اسلات) ----------------
# به‌جای شمردن "چند دقیقه از آخرین بار گذشته"، دنیا به بازه‌های ثابت
# COOLDOWN_MINUTES دقیقه‌ای تقسیم میشه (مثلاً 12:00-14:00, 14:00-16:00...)
# و هر کاربر توی هر بازه فقط یه‌بار میتونه پوینت بگیره.

def slot_start(ts):
    dt = datetime.fromtimestamp(ts, tz=TIMEZONE)
    minutes_since_midnight = dt.hour * 60 + dt.minute
    slot_index = minutes_since_midnight // COOLDOWN_MINUTES
    start_minutes = slot_index * COOLDOWN_MINUTES
    midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + timedelta(minutes=start_minutes)


def slot_end(ts):
    return slot_start(ts) + timedelta(minutes=COOLDOWN_MINUTES)


def resolve_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message

    if msg.reply_to_message:
        target = msg.reply_to_message.from_user
        if target is None:
            return None, None, "این پیام از یه کاربر عادی نیست، رو پیام خود شخص ریپلای کن."
        if target.is_bot:
            return None, None, "رو پیام خود بات ریپلای نکن، رو پیام خود شخص ریپلای کن."
        return target.id, (target.full_name or target.username or str(target.id)), None

    for a in context.args:
        if a.isdigit():
            return int(a), a, None

    return None, None, None


def extract_amount(context: ContextTypes.DEFAULT_TYPE, had_reply: bool):
    args = context.args
    idx = 0 if had_reply else 1
    if len(args) > idx and args[idx].lstrip("-").isdigit():
        return int(args[idx])
    return None


# ---------------- کلیم سایز ----------------

async def do_claim(update: Update, context: ContextTypes.DEFAULT_TYPE, user, chat_id, now, chat_send):
    data = load_data()
    chat_data = get_chat(data, chat_id)
    entry = get_user(chat_data, user.id, user.full_name or user.username or str(user.id))

    if entry.get("banned"):
        await chat_send("⛔ بن شدی، نمیتونی سایزتو بزرگ کنی.")
        return

    same_slot = entry["last_claim"] > 0 and slot_start(entry["last_claim"]) == slot_start(now)

    if same_slot:
        next_at = slot_end(now)
        text = f"⏳ الان ساعت {clock(now)}ه — ساعت {next_at.strftime('%H:%M')} دوباره بگو کیر"
    else:
        gained = POINTS_PER_SIZE
        entry["points"] += gained
        entry["last_claim"] = now
        save_data(data)

        next_at = slot_end(now)
        text = (
            f"کیر 🍆 +{gained} (سایزت: {entry['points']:,} سانت)\n"
            f"ساعت {next_at.strftime('%H:%M')} دوباره میتونی بگی کیر"
        )

    await chat_send(text)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(" بگو (کیر) تا سایزت بزرگ بشه ")


async def size_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async def send(text):
        await update.message.reply_text(text)

    # به‌جای زمانِ الانِ سرور، از زمانی که خودِ پیام فرستاده شده استفاده میکنیم
    # تا اگه بات خاموش بوده و پیام‌ها بعداً پردازش بشن، بر اساس ساعت واقعیِ ارسال حساب بشه
    sent_at = update.effective_message.date.timestamp()

    await do_claim(update, context, update.effective_user, update.effective_chat.id, sent_at, send)


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"آیدی شما: {update.effective_user.id}")


# ---------------- پنل ادمین ----------------

async def admin_cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(ADMIN_COMMANDS)


async def add_point(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not is_admin(update.effective_user.id, data):
        return
    uid, name, err = resolve_target(update, context)
    if err:
        await update.message.reply_text(err)
        return
    amount = extract_amount(context, had_reply=bool(update.message.reply_to_message))
    if uid is None or amount is None:
        await update.message.reply_text("🔹 شخص مورد نظر رو ریپلای کن:\n/addpoint <مقدار>")
        return

    chat_data = get_chat(data, update.effective_chat.id)
    entry = get_user(chat_data, uid, name)
    entry["points"] += amount
    save_data(data)
    await update.message.reply_text(f"✅ {entry['name']}: {amount}+ (مجموع: {entry['points']:,})")


async def remove_point(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not is_admin(update.effective_user.id, data):
        return
    uid, name, err = resolve_target(update, context)
    if err:
        await update.message.reply_text(err)
        return
    amount = extract_amount(context, had_reply=bool(update.message.reply_to_message))
    if uid is None or amount is None:
        await update.message.reply_text("🔹 شخص مورد نظر رو ریپلای کن:\n/removepoint <مقدار>")
        return

    chat_data = get_chat(data, update.effective_chat.id)
    entry = get_user(chat_data, uid, name)
    entry["points"] = max(0, entry["points"] - amount)
    save_data(data)
    await update.message.reply_text(f"✅ {entry['name']}: {amount}- (مجموع: {entry['points']:,})")


async def reset_point(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not is_admin(update.effective_user.id, data):
        return
    uid, name, err = resolve_target(update, context)
    if err:
        await update.message.reply_text(err)
        return
    if uid is None:
        await update.message.reply_text("🔹 شخص مورد نظر رو ریپلای کن:\n/resetpoint")
        return

    chat_data = get_chat(data, update.effective_chat.id)
    entry = get_user(chat_data, uid, name)
    entry["points"] = 0
    save_data(data)
    await update.message.reply_text(f"✅ سایز {entry['name']} صفر شد.")


async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not is_admin(update.effective_user.id, data):
        return
    uid, name, err = resolve_target(update, context)
    if err:
        await update.message.reply_text(err)
        return
    if uid is None:
        await update.message.reply_text("🔹 شخص مورد نظر رو ریپلای کن:\n/ban")
        return

    chat_data = get_chat(data, update.effective_chat.id)
    entry = get_user(chat_data, uid, name)
    entry["banned"] = True
    save_data(data)
    await update.message.reply_text(f"⛔ {entry['name']} بن شد.")


async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not is_admin(update.effective_user.id, data):
        return
    uid, name, err = resolve_target(update, context)
    if err:
        await update.message.reply_text(err)
        return
    if uid is None:
        await update.message.reply_text("🔹 شخص مورد نظر رو ریپلای کن:\n/unban")
        return

    chat_data = get_chat(data, update.effective_chat.id)
    entry = get_user(chat_data, uid, name)
    entry["banned"] = False
    save_data(data)
    await update.message.reply_text(f"✅ بن {entry['name']} برداشته شد.")


async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ادمین‌ها سراسری هستن (توی همه‌ی گروه‌ها)، نه مخصوص یه گروه
    data = load_data()
    if not is_admin(update.effective_user.id, data):
        return
    uid, name, err = resolve_target(update, context)
    if err:
        await update.message.reply_text(err)
        return
    if uid is None:
        await update.message.reply_text("🔹 شخص مورد نظر رو ریپلای کن:\n/addadmin")
        return

    admins = set(data.get("_admins", []))
    if uid in BASE_ADMIN_IDS or uid in admins:
        await update.message.reply_text(f"{name} از قبل ادمین بود.")
        return

    admins.add(uid)
    data["_admins"] = list(admins)
    save_data(data)
    await update.message.reply_text(f"✅ {name} ادمین شد.")


async def reset_cooldown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not is_admin(update.effective_user.id, data):
        return
    uid, name, err = resolve_target(update, context)
    if err:
        await update.message.reply_text(err)
        return
    if uid is None:
        await update.message.reply_text("🔹 شخص مورد نظر رو ریپلای کن:\n/resetcooldown")
        return

    chat_data = get_chat(data, update.effective_chat.id)
    entry = get_user(chat_data, uid, name)
    entry["last_claim"] = 0
    save_data(data)
    await update.message.reply_text(f"✅ {entry['name']} همین الان میتونه بگه کیر.")


# ---------------  لیدربورد ----------------

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    chat_data = get_chat(data, update.effective_chat.id)
    ranking = sorted(chat_data.items(), key=lambda kv: kv[1]["points"], reverse=True)

    lines = ["🏆 بزرگترین کیر گروه:\n"]
    medal = {0: "🥇", 1: "🥈", 2: "🥉"}
    for i, (uid, entry) in enumerate(ranking[:10]):
        prefix = medal.get(i, f"{i + 1}.")
        lines.append(f"{prefix} {entry['name']} — {entry['points']:,}")

    requester_id = str(update.effective_user.id)
    position = next((i for i, (uid, _) in enumerate(ranking) if uid == requester_id), None)

    if position is not None and position >= 10:
        entry = chat_data[requester_id]
        lines.append("...")
        lines.append(f"{position + 1}. {entry['name']} — {entry['points']:,} (رتبه‌ی شما)")
    elif position is None:
        lines.append("\nشما هنوز سایزی ندارید")

    await update.message.reply_text("\n".join(lines))


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is required")
    
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", my_id))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("admincmd", admin_cmd_list))

    app.add_handler(CommandHandler("addpoint", add_point))
    app.add_handler(CommandHandler("removepoint", remove_point))
    app.add_handler(CommandHandler("resetpoint", reset_point))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("resetcooldown", reset_cooldown))

    app.add_handler(MessageHandler(filters.Regex(r"^کیر$"), size_text))

    app.run_polling()


if __name__ == "__main__":
    main()
