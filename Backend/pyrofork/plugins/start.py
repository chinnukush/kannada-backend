from asyncio import create_task, sleep as asleep
from urllib.parse import urlparse
from Backend.logger import LOGGER
from Backend import db
from Backend.config import Telegram
from Backend.helper.custom_filter import CustomFilters
from Backend.helper.encrypt import decode_string
from Backend.helper.metadata import metadata
from Backend.helper.pyro import clean_filename, get_readable_file_size, remove_urls
from Backend.pyrofork import StreamBot
from pyrogram import filters, Client
from pyrogram.types import Message
from os import path as ospath
from pyrogram.errors import FloodWait, UserNotParticipant
from pyrogram.enums.parse_mode import ParseMode
from themoviedb import aioTMDb
from asyncio import Queue, create_task
from os import execl as osexecl
from asyncio import create_subprocess_exec, gather
from sys import executable
from aiofiles import open as aiopen
from pyrogram import enums


pending_requests = {}  # user_id -> usr_cmd

async def check_fsub(bot: Client, user_id: int, channel_id: str) -> bool:
    try:
        member = await bot.get_chat_member(channel_id, user_id)
        if member.status in ("kicked", "left"):
            return False
        return True
    except UserNotParticipant:
        return False
    except Exception as e:
        LOGGER.error(f"FSUB check failed: {e}")
        return False


tmdb = aioTMDb(key=Telegram.TMDB_API, language="en-US", region="US")
# Initialize database connection
import random
import string
from passlib.context import CryptContext
from datetime import datetime, timedelta

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




async def delete_messages_after_delay(messages):
    await asleep(300)  
    for msg in messages:
        try:
            await msg.delete()
        except Exception as e:
            LOGGER.error(f"Error deleting message {msg.id}: {e}")
        await asleep(2)  

# ----------------- START COMMAND -----------------
@StreamBot.on_message(filters.command('start') & filters.private)
async def start(bot: Client, message: Message):
    LOGGER.info(f"Received command: {message.text}")
    command_part = message.text.split('start ')[-1]

    if command_part.startswith("file_"):
        usr_cmd = command_part[len("file_"):].strip()

        # --- Force Subscribe Check ---
        channel_id = Telegram.FSUB_CHANNEL[0]  # first channel
        is_subscribed = await check_fsub(bot, message.from_user.id, channel_id)

        if not is_subscribed:
            invite_link = await bot.create_chat_invite_link(channel_id)
            pending_requests[message.from_user.id] = usr_cmd
            await message.reply_text(
                f"⚠️ To access files, you must join our channel first:\n\n"
                f"👉 [Join Channel]({invite_link.invite_link})\n\n"
                f"After joining, the bot will automatically send your file.",
                disable_web_page_preview=True,
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # --- Continue with your existing file sending logic ---
        await send_file(bot, message, usr_cmd)

    else:
        await message.reply_text(
            "ɪ ᴀᴍ ʜᴇʀᴇ ᴛᴏ ᴘʀᴏᴠɪᴅᴇ ᴅɪʀᴇᴄᴛ ᴅᴏᴡɴʟᴏᴀᴅ ʟɪɴᴋꜱ ғᴏʀ ᴍᴏᴠɪᴇꜱ & ꜱᴇʀɪᴇꜱ ғʀᴏᴍ https://hk-movies.vercel.app 📥 ɪᴜꜱᴛ ꜱᴇɴᴅ ᴀ ғɪʟᴇ ʟɪɴᴋ ᴛᴏ ɢᴇᴛ ꜱᴛᴀʀᴛᴇᴅ!"
        )
# -------------------------------------------------

# ----------------- MEMBER UPDATE -----------------
@StreamBot.on_chat_member_updated()
async def member_update(bot: Client, event):
    if not event.new_chat_member or not event.new_chat_member.user:
        return

    user_id = event.new_chat_member.user.id
    if user_id not in pending_requests:
        return

    usr_cmd = pending_requests.pop(user_id)

    try:
        msg = await bot.send_message(user_id, "📥 Thanks for joining! Preparing your file...")
        await send_file(bot, msg, usr_cmd)
    except Exception as e:
        LOGGER.error(f"Error sending file after join for {user_id}: {e}")
        await bot.send_message(user_id, "❌ Failed to send your file. Please try again.")
# -------------------------------------------------

# ----------------- FILE RECEIVE HANDLER -----------------
@StreamBot.on_message(filters.channel & (filters.document | filters.video))
async def file_receive_handler(bot: Client, message: Message):
    if str(message.chat.id) in Telegram.FSUB_CHANNEL:
        try:
            if message.video or message.document:
                file = message.video or message.document
                if Telegram.USE_CAPTION:
                    title = message.caption.replace("\n", "\\n")
                else:
                    title = file.file_name or file.file_id
                msg_id = message.id
                hash = file.file_unique_id[:6]
                size = get_readable_file_size(file.file_size)
                channel = str(message.chat.id).replace("-100","")

                metadata_info = await metadata(clean_filename(title), file)
                if metadata_info is None:
                    return

                title = remove_urls(title)
                if not title.endswith('.mkv'):
                    title += '.mkv'
                await file_queue.put((metadata_info, hash, int(channel), msg_id, size, title))

            else:
                await message.reply_text("Not supported")
        except FloodWait as e:
            LOGGER.info(f"Sleeping for {str(e.value)}s")
            await asleep(e.value)
            await message.reply_text(text=f"Got Floodwait of {str(e.value)}s",
                                disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
    else:
        await message.reply(text="Channel is not in FSUB_CHANNEL")
# -------------------------------------------------

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
        
