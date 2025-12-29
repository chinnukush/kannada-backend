from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from Backend.helper.database import Database
from Backend.pyrofork import StreamBot

# Initialize DB (make sure you call db.connect() at startup)
db = Database()

@StreamBot.on_message(filters.text & filters.private)
async def media_search(bot: Client, message: Message):
    query = message.text.strip()

    # Search in DB (both movies and series)
    results = await db.search_documents(query, page=1, page_size=5)

    if results["total_count"] > 0:
        buttons = []
        for media in results["results"]:
            tmdb_id = media["tmdb_id"]
            title = media["title"]
            media_type = media.get("media_type", "movie")  # "movie" or "tv"

            # Build link (same pattern for both types)
            link = f"https://hkspot-k66q4fh4n-kushals-projects-dc9c420d.vercel.app/id/{tmdb_id}"

            # Add button
            buttons.append([InlineKeyboardButton(f"{title} ({media_type})", url=link)])

        await message.reply_text(
            f"📺 Found {results['total_count']} result(s) for **{query}**:",
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )
    else:
        await message.reply_text("❌ This movie/series is not available.")
