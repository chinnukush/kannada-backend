from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from Backend.pyrofork import StreamBot   # ✅ Import the bot client
from Backend.helper.database import db   # ✅ Import the db instance

@StreamBot.on_message(filters.text & filters.private)
async def media_search(bot, message):
    query = message.text.strip()

    results = await db.search_documents(query, page=1, page_size=5)

    if results["total_count"] > 0:
        buttons = []
        for media in results["results"]:
            tmdb_id = media["tmdb_id"]
            title = media["title"]
            media_type = media.get("media_type", "movie")

            link = f"https://hari-moviez.vercel.app//id/{tmdb_id}"
            buttons.append([InlineKeyboardButton(f"{title} ({media_type})", url=link)])

        await message.reply_text(
            f"📺 Found {results['total_count']} result(s) for **{query}**:",
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )
    else:
        await message.reply_text("❌ This movie/series is not available.")
