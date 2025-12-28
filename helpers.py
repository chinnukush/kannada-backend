from pyrogram.errors import UserNotParticipant
from Backend.config import Telegram
from Backend.logger import LOGGER

async def check_fsub(bot, user_id: int) -> bool:
    """
    Check if user has joined all FORCE_SUB_CHANNEL(s).
    """
    for channel_id in Telegram.FORCE_SUB_CHANNEL:
        try:
            member = await bot.get_chat_member(channel_id, user_id)
            if member.status in ("kicked", "left"):
                return False
        except UserNotParticipant:
            return False
        except Exception as e:
            LOGGER.error(f"FSUB check failed for {channel_id}: {e}")
            return False
    return True
