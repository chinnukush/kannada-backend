import asyncio
from collections import defaultdict
from asyncio import create_task, sleep as asleep
from urllib.parse import urlparse
from Backend.logger import LOGGER
from Backend import db
from Backend.helper.utils import clean_filename
from Backend.config import Telegram
from Backend.helper.custom_filter import CustomFilters
from Backend.helper.encrypt import decode_string
from Backend.helper.metadata import metadata
from Backend.helper.pyro import clean_filename, get_readable_file_size, remove_urls
from Backend.pyrofork import StreamBot
from pyrogram import filters, Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from os import path as ospath
#from pyrogram.errors import FloodWait
from pyrogram.enums.parse_mode import ParseMode
from themoviedb import aioTMDb
from asyncio import Queue, create_task
from os import execl as osexecl
from asyncio import create_subprocess_exec, gather
from sys import executable
from aiofiles import open as aiopen
from pyrogram import enums, Client, filters
import asyncio
import random
import string
from passlib.context import CryptContext
from datetime import datetime, timedelta
from pyrogram.errors import FloodWait, UserNotParticipant
from Backend.pyrofork.plugins.send_file import send_file


# Temporary stores
movie_updates = {}
pending_posts = {}

async def schedule_post(bot, tmdb_id):
    await asyncio.sleep(Telegram.POST_DELAY)  # configurable delay
    info = movie_updates.get(tmdb_id)
    if not info:
        return

    # Build caption with quotes and rich metadata
    if info["media_type"] == "tv":
        post_url = f"https://hari-moviez.vercel.app/ser/{tmdb_id}"
        caption = (
            f"\"📺 {info['title']}\n"
            f"🗓️ Season {info.get('season_number')} Episode {info.get('episode_number')}\n"
            f"📅 Release Year: {info.get('year')}\n"
            f"⭐ Rating: {info.get('rate')}/10\n"
            f"🎭 Genres: {', '.join(info.get('genres', []))}\n"
            f"🌐 Languages: {', '.join(info.get('languages', []))}\n\n"
            f"📝 Plot: {info.get('description')}\n\n"
            f"🔗 [Open Post]({post_url})\""
        )
    else:
        post_url = f"https://hari-moviez.vercel.app/mov/{tmdb_id}"
        caption = (
            f"\"🎬 {info['title']}\n"
            f"📅 Release Year: {info.get('year')}\n"
            f"⭐ Rating: {info.get('rate')}/10\n"
            f"🎭 Genres: {', '.join(info.get('genres', []))}\n"
            f"🌐 Languages: {', '.join(info.get('languages', []))}\n\n"
            f"📝 Plot: {info.get('description')}\n\n"
            f"🔗 [Open Post]({post_url})\""
        )

    # Send poster if available
    if info.get("poster"):
        await bot.send_photo(
            chat_id=Telegram.UPDATE_CHANNEL,
            photo=info["poster"],
            caption=caption,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("📌 Open Post", url=post_url)]]
            )
        )
    else:
        await bot.send_message(
            chat_id=Telegram.UPDATE_CHANNEL,
            text=caption,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("📌 Open Post", url=post_url)]]
            ),
            disable_web_page_preview=True
        )

    # Clear after posting
    movie_updates.pop(tmdb_id, None)
    pending_posts.pop(tmdb_id, None)



#--------------------------------------------------
# --- Force Subscribe Check ---
async def check_fsub(bot: Client, user_id: int) -> bool:
    for channel in Telegram.FORCE_SUB_CHANNEL:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status in ("kicked", "left"):
                return False
        except UserNotParticipant:
            return False
        except Exception as e:
            LOGGER.error(f"FSUB check failed for {channel}: {e}")
            continue
    return True


@StreamBot.on_message(filters.command("start") & filters.private)
async def start(bot: Client, message: Message):
    LOGGER.info(f"Received command: {message.text}")
    command_part = message.text.split("start ", 1)[-1]

    # --- Case 1: Plain /start ---
    if not command_part.startswith("file_"):
        await message.reply_text("ʜɪɪ 👋 ɪ ᴀᴍ ʜᴇʀᴇ ᴛᴏ ᴘʀᴏᴠɪᴅᴇ ᴅɪʀᴇᴄᴛ ᴅᴏᴡɴʟᴏᴀᴅ ʟɪɴᴋꜱ ғᴏʀ ᴍᴏᴠɪᴇꜱ & ꜱᴇʀɪᴇꜱ ғʀᴏᴍ https://hari-moviez.vercel.app 📥.")
        return

    # --- Case 2: Deep-link /start file_xxx ---
    usr_cmd = command_part[len("file_"):].strip()

    # Force Subscribe check
    is_subscribed = await check_fsub(bot, message.from_user.id)
    if not is_subscribed:
        buttons = []
        for channel in Telegram.FORCE_SUB_CHANNEL:
            invite = await bot.create_chat_invite_link(channel)
            buttons.append([InlineKeyboardButton("📢 ɪᴏɪɴ ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ 📢", url=invite.invite_link)])

        await message.reply_text(
            "<b>⚠️ ᴛᴏ ᴀᴄᴄᴇꜱꜱ ғɪʟᴇꜱ, ʏᴏᴜ ᴍᴜꜱᴛ ɪᴏɪɴ ᴏᴜʀ ᴄʜᴀɴɴᴇʟ.</b>\n\n"
            "<b>ᴀғᴛᴇʀ ɪᴏɪɴɪɴɢ, ᴛʜᴇ ʙᴏᴛ ᴡɪʟʟ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ꜱᴇɴᴅ ʏᴏᴜʀ ғɪʟᴇ.</b>",
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )
        pending_requests[message.from_user.id] = usr_cmd
        return

    # Already subscribed → send file immediately
    await send_file(bot, message, usr_cmd)


# --- Auto-send after user joins FORCE_SUB_CHANNEL ---
@StreamBot.on_chat_member_updated()
async def member_update(bot: Client, event):
    if not event.new_chat_member or not event.new_chat_member.user:
        return

    user_id = event.new_chat_member.user.id
    if user_id in pending_requests:
        usr_cmd = pending_requests.pop(user_id)
        try:
            msg = await bot.send_message(user_id, "📥 ᴛʜᴀɴᴋꜱ ғᴏʀ ɪᴏɪɴɪɴɢ! ᴘʀᴇᴘᴀʀɪɴɢ ʏᴏᴜʀ ғɪʟᴇ.....")
            await send_file(bot, msg, usr_cmd)
        except Exception as e:
            LOGGER.error(f"Error sending file after join for {user_id}: {e}")


async def delete_messages_after_delay(messages):    
    await asyncio.sleep(300)
    for msg in messages:
        try:
            await msg.delete()
        except Exception as e:
            LOGGER.error(f"Error deleting message {msg.id}: {e}")
        await asyncio.sleep(2)
        

tmdb = aioTMDb(key=Telegram.TMDB_API, language="en-US", region="US")
# Initialize database connection

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def generate_password(length=10):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

@StreamBot.on_message(filters.command("user") & filters.private & CustomFilters.owner)
async def create_user(bot: Client, message: Message):
    try:
        args = message.text.split()
        if len(args) != 3:
            await message.reply_text("❌ Usage: `/user <username> <expiry_days>`", parse_mode=ParseMode.MARKDOWN)
            return

        username = args[1]
        expiry_days = int(args[2])

        users_collection = db.db["auth_users"]  # Use the Tracking database

        # Check if username already exists
        existing_user = await users_collection.find_one({"username": username})
        if existing_user:
            await message.reply_text(f"❌ User `{username}` already exists!", parse_mode=ParseMode.MARKDOWN)
            return

        password = generate_password()
        hashed_password = pwd_ctx.hash(password)
        expires_at = datetime.utcnow() + timedelta(days=expiry_days)

        user_data = {
            "username": username,
            "password": hashed_password,
            "expires_at": expires_at
        }
        await users_collection.insert_one(user_data)

        await message.reply_text(
            f"✅ User created!\n\n"
            f"👤 Username: `{username}`\n"
            f"🔑 Password: `{password}`\n"
            f"🕒 Expires in: `{expiry_days}` days\n"
            f"📅 Expiry Date: `{expires_at.strftime('%Y-%m-%d %H:%M:%S')} UTC`",
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:
        LOGGER.error(f"Error in /user command: {e}")
        await message.reply_text("❌ An error occurred while creating the user.")

@StreamBot.on_message(filters.command('restart') & filters.private & CustomFilters.owner)
async def restart(bot: Client, message: Message):
    try:
        # Notify the user that the bot is restarting
        
        restart_message = await message.reply_text(
    '<blockquote>⚙️ Restarting Backend API... \n\n✨ Please wait as we bring everything back online! 🚀</blockquote>',
        quote=True,
        parse_mode=enums.ParseMode.HTML
        )
        LOGGER.info("Restart initiated by owner.")

        # Run the update script
        proc1 = await create_subprocess_exec('python3', 'update.py')
        await gather(proc1.wait())

        # Save restart message details for notification after restart
        async with aiopen(".restartmsg", "w") as f:
            await f.write(f"{restart_message.chat.id}\n{restart_message.id}\n")

        # Restart the bot process
        osexecl(executable, executable, "-m", "Backend")

    except Exception as e:
        LOGGER.error(f"Error during restart: {e}")
        await message.reply_text("**❌ Failed to restart. Check logs for details.**")


@StreamBot.on_message(filters.command('log') & filters.private & CustomFilters.owner)
async def start(bot: Client, message: Message):
    try:
        path = ospath.abspath('log.txt')
        return await message.reply_document(
        document=path, quote=True, disable_notification=True
        )
    except Exception as e:
        print(f"An error occurred: {e}")




# Global queue for processing file updates
file_queue = Queue()

from asyncio import Lock

# Global lock for database access
db_lock = Lock()

async def process_file():
    while True:
        metadata_info, hash, channel, msg_id, size, title = await file_queue.get()

        # Acquire the lock before updating the database
        async with db_lock:
            updated_id = await db.insert_media(metadata_info, hash=hash, channel=channel, msg_id=msg_id, size=size, name=title)

            if updated_id:
                LOGGER.info(f"{metadata_info['media_type']} updated with ID: {updated_id}")
            else:
                LOGGER.info("Update failed due to validation errors.")

        file_queue.task_done()



# Start the file processing tasks (adjust the number of workers as needed)
for _ in range(1):  # Two concurrent workers
    create_task(process_file())

@StreamBot.on_message(
    filters.channel
    & (
        filters.document
        | filters.video
    )
)

# ---------------- AUTH_CHANNEL Listener ----------------
@Client.on_message(filters.channel & filters.chat(Telegram.AUTH_CHANNEL))
async def file_receive_handler(bot: Client, message: Message):
    try:
        file = message.video or message.document
        title = message.caption if (Telegram.USE_CAPTION and message.caption) else file.file_name or file.file_id

        metadata_info = await metadata(clean_filename(title), file)
        if metadata_info is None:
            return

        tmdb_id = metadata_info.get("tmdb_id")
        media_type = metadata_info.get("media_type", "movie")
        poster = metadata_info.get("poster", None)

        # Store info for grouping
        movie_updates[tmdb_id] = {
            "title": metadata_info.get("title", title),
            "media_type": media_type,
            "poster": poster,
            "season_number": metadata_info.get("season_number"),
            "episode_number": metadata_info.get("episode_number"),
            "year": metadata_info.get("year"),
            "rate": metadata_info.get("rate"),
            "genres": metadata_info.get("genres", []),
            "languages": metadata_info.get("languages", []),
            "description": metadata_info.get("description", "")
        }

        # Schedule post if not already pending
        if tmdb_id not in pending_posts:
            pending_posts[tmdb_id] = asyncio.create_task(schedule_post(bot, tmdb_id))

    except FloodWait as e:
        await asyncio.sleep(e.value)
        await message.reply_text(f"Got Floodwait of {e.value}s")


@Client.on_message(filters.command('caption') & filters.private & CustomFilters.owner)
async def toggle_caption(bot: Client, message: Message):
    try:
        Telegram.USE_CAPTION = not Telegram.USE_CAPTION
        await message.reply_text(f"Now Bot Uses {'Caption' if Telegram.USE_CAPTION else 'Filename'}")
    except Exception as e:
        print(f"An error occurred: {e}")

@Client.on_message(filters.command('tmdb') & filters.private & CustomFilters.owner)
async def toggle_tmdb(bot: Client, message: Message):
    try:
        Telegram.USE_TMDB = not Telegram.USE_TMDB
        await message.reply_text(f"Now Bot Uses {'TMDB' if Telegram.USE_TMDB else 'IMDB'}")
    except Exception as e:
        print(f"An error occurred: {e}")

@Client.on_message(filters.command('set') & filters.private & CustomFilters.owner)
async def set_id(bot: Client, message: Message):

    url_part = message.text.split()[1:]  # Skip the command itself

    try:
        if len(url_part) == 1:

            Telegram.USE_DEFAULT_ID = url_part[0]  # Get the first element
            await message.reply_text(f"Now Bot Uses Default URL: {Telegram.USE_DEFAULT_ID}")
        else:
            # Remove the default ID
            Telegram.USE_DEFAULT_ID = None
            await message.reply_text("Removed default ID.")
    except Exception as e:
        await message.reply_text(f"An error occurred: {e}")





@Client.on_message(filters.command('delete') & filters.private & CustomFilters.owner)
async def delete(bot: Client, message: Message):
    try:
        split_text = message.text.split()
        if len(split_text) != 2:
            return await message.reply_text("Use this format: /delete https://domain/ser/3123")
        
        url = split_text[1]
        parsed_url = urlparse(url)
        path_parts = parsed_url.path.split('/')
        
        if len(path_parts) >= 3 and path_parts[-2] in ('ser', 'mov') and path_parts[-1].isdigit():
            media_type = path_parts[-2]
            tmdb_id = path_parts[-1]
            delete = await db.delete_document(media_type, int(tmdb_id))
            if delete:
                return await message.reply_text(f"{media_type} with ID {tmdb_id} has been deleted successfully.")
            else:
                return await message.reply_text(f"ID {tmdb_id} wasn't found in the database.")
        else:
            return await message.reply_text("The URL format is incorrect.")
    
    except Exception as e:
        await message.reply_text(f"An error occurred: {str(e)}")
        
