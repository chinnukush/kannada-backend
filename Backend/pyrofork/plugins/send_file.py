import asyncio
from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from Backend.logger import LOGGER
from Backend import db
from Backend.helper.encrypt import decode_string

async def send_file(bot: Client, message: Message, usr_cmd: str):
    parts = usr_cmd.split("_")
    try:
        if len(parts) == 2:
            tmdb_id, quality = parts
            tmdb_id = int(tmdb_id)
            quality_details = await db.get_quality_details(tmdb_id, quality)
        elif len(parts) == 3:
            tmdb_id, season, quality = parts
            tmdb_id = int(tmdb_id)
            season = int(season)
            quality_details = await db.get_quality_details(tmdb_id, quality, season)
        elif len(parts) == 4:
            tmdb_id, season, episode, quality = parts
            tmdb_id = int(tmdb_id)
            season = int(season)
            episode = int(episode)
            quality_details = await db.get_quality_details(tmdb_id, quality, season, episode)
        else:
            await message.reply_text("Invalid command format.")
            return
    except ValueError:
        await message.reply_text("Invalid command format.")
        return

    sent_messages = []
    for detail in quality_details:
        decoded_data = await decode_string(detail["id"])
        channel = f"-100{decoded_data['chat_id']}"
        msg_id = decoded_data["msg_id"]
        name = detail["name"]

        if "\\n" in name and name.endswith(".mkv"):
            name = name.rsplit(".mkv", 1)[0].replace("\\n", "\n")

        try:
            file = await bot.get_messages(int(channel), int(msg_id))
            media = file.document or file.video or file.audio or file.photo
            if media:
                sent_msg = await message.reply_cached_media(
                    file_id=media.file_id,
                    caption=name
                )
                sent_messages.append(sent_msg)
                await asyncio.sleep(1)
        except FloodWait as e:
            LOGGER.info(f"Sleeping for {e.value}s due to FloodWait")
            await asyncio.sleep(e.value)
        except Exception as e:
            LOGGER.error(f"Error retrieving/sending media: {e}")

    if sent_messages:
        warning_msg = await message.reply_text(
            "Forward these files to your saved messages. "
            "These files will be deleted from the bot within 5 minutes."
        )
        sent_messages.append(warning_msg)
        asyncio.create_task(delete_messages_after_delay(sent_messages))


async def delete_messages_after_delay(messages):
    await asyncio.sleep(300)
    for msg in messages:
        try:
            await msg.delete()
        except Exception as e:
            LOGGER.error(f"Error deleting message {msg.id}: {e}")
        await asyncio.sleep(2)
