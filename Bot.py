import os, json, asyncio, threading
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CallbackQueryHandler,
                          CommandHandler, ContextTypes)
import watcher, highlights, tiktok, live

load_dotenv()
OWNER = int(os.getenv("OWNER_CHAT_ID"))
STREAMERS = [s.strip() for s in os.getenv("STREAMERS").split(",")]
DATA = os.getenv("DATA_DIR", ".")
os.makedirs(DATA, exist_ok=True)
SEEN = os.path.join(DATA, "seen.json")
seen = set(json.load(open(SEEN))) if os.path.exists(SEEN) else set()
clip_store = {}
main_loop = None

def build_clips(vod):
    video = highlights.download_vod(vod["url"], f"{vod['id']}.mp4")
    chat = highlights.chat_spikes(highlights.download_chat(vod["id"]))
    loud = highlights.loudness(video)
    out = []
    for i, start in enumerate(highlights.pick_moments(chat, loud)):
        n = highlights.clip_length(chat, loud, start)
        out.append(highlights.make_clip(video, start, f"{vod['id']}_{i}.mp4", n))
    return out

async def send_clip(bot, path, name):
    if tiktok.AUTO:
        tiktok.upload(path, f"{name} moment #clips")
        return
    key = str(len(clip_store))
    clip_store[key] = (path, name)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("Approve", callback_data=f"ok|{key}"),
        InlineKeyboardButton("Skip", callback_data="no")]])
    with open(path, "rb") as f:
        await bot.send_video(OWNER, f, caption=name, reply_markup=kb)

async def check_streams(context: ContextTypes.DEFAULT_TYPE):
    token = watcher.twitch_token()
    for name in STREAMERS:
        try:
            if live.is_live(name, token):
                continue  # wait until the stream ends
            vod = watcher.latest_vod(name, token)
            if not vod or vod["id"] in seen:
                continue
            seen.add(vod["id"])
            json.dump(list(seen), open(SEEN, "w"))
            await context.bot.send_message(OWNER, f"New VOD from {name}, clipping...")
            loop = asyncio.get_running_loop()
            clips = await loop.run_in_executor(None, build_clips, vod)
            for path in clips:
                await send_clip(context.bot, path, name)
        except Exception as e:
            await context.bot.send_message(OWNER, f"Error with {name}: {e}")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data.startswith("ok|"):
        item = clip_store.get(q.data.split("|")[1])
        if not item:
            await q.edit_message_caption("Clip expired, bot was restarted")
            return
        path, name = item
        try:
            tiktok.upload(path, f"{name} moment #clips")
            await q.edit_message_caption("Sent to TikTok")
        except Exception as e:
            await q.edit_message_caption(f"TikTok failed: {e}")
    else:
        await q.edit_message_caption("Skipped")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Clip bot is running.")

def send_live_clip(path, login):
    asyncio.run_coroutine_threadsafe(
        send_clip(app.bot, path, f"Live moment from {login}"), main_loop)

async def start_live(app_):
    global main_loop
    main_loop = asyncio.get_running_loop()
    if os.getenv("LIVE_MODE", "false").lower() == "true":
        for name in STREAMERS:
            threading.Thread(target=live.watch,
                             args=(name, send_live_clip), daemon=True).start()

app = (ApplicationBuilder().token(os.getenv("TELEGRAM_TOKEN"))
       .post_init(start_live).build())
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button))
app.job_queue.run_repeating(check_streams, interval=600, first=5)
app.run_polling()
