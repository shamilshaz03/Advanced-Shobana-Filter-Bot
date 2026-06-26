# plugins/start.py
import asyncio
import random
import time

from pyrogram import Client, filters, enums
from pyrogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
)

from database.ia_filterdb import Media
from database.users_chats_db import db
from info import PICS, LOG_CHANNEL, ADMINS, BOT_START_TIME
from Script import script
from utils import temp


@Client.on_message(filters.command("start") & filters.incoming)
async def start(client: Client, message: Message):
    uid = message.from_user.id
    name = message.from_user.first_name or "User"
    if not await db.is_user_exist(uid):
        await db.add_user(uid, name)
        if LOG_CHANNEL:
            try:
                await client.send_message(
                    LOG_CHANNEL,
                    script.LOG_TEXT_P.format(uid, name),
                    parse_mode=enums.ParseMode.HTML,
                )
            except Exception:
                pass

    buttons = [
        [InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{temp.U_NAME}?startgroup=true")],
        [InlineKeyboardButton("📖 Help", callback_data="help"),
         InlineKeyboardButton("ℹ About", callback_data="about")],
    ]
    pic = random.choice(PICS) if PICS else None
    try:
        if pic:
            await message.reply_photo(
                photo=pic,
                caption=script.START_TXT.format(message.from_user.mention),
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=enums.ParseMode.HTML,
            )
        else:
            await message.reply_text(
                script.START_TXT.format(message.from_user.mention),
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=enums.ParseMode.HTML,
            )
    except Exception:
        await message.reply_text(
            script.START_TXT.format(message.from_user.mention),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=enums.ParseMode.HTML,
        )


@Client.on_callback_query(filters.regex(r"^help$"))
async def help_cb(client: Client, q: CallbackQuery):
    page = 0
    total = len(script.HELP_PAGES)
    await _edit_help(q, page, total)
    await q.answer()


@Client.on_callback_query(filters.regex(r"^helppage_(\d+)$"))
async def help_page_cb(client: Client, q: CallbackQuery):
    page = int(q.data.split("_")[-1])
    page = max(0, min(page, len(script.HELP_PAGES) - 1))
    await _edit_help(q, page, len(script.HELP_PAGES))
    await q.answer()


async def _edit_help(q: CallbackQuery, page: int, total: int):
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"helppage_{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{total}", callback_data="noop"))
    if page < total - 1:
        nav.append(InlineKeyboardButton("Next ▶", callback_data=f"helppage_{page + 1}"))
    rows = [nav, [InlineKeyboardButton("🏠 Home", callback_data="home")]]
    try:
        await q.message.edit_text(
            script.HELP_TXT.format(q.from_user.mention) + "\n\n" + script.HELP_PAGES[page],
            parse_mode=enums.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(rows),
            disable_web_page_preview=True,
        )
    except Exception:
        pass


@Client.on_callback_query(filters.regex(r"^about$"))
async def about_cb(client: Client, q: CallbackQuery):
    try:
        await q.message.edit_text(
            script.ABOUT_TXT,
            parse_mode=enums.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Home", callback_data="home")]]),
            disable_web_page_preview=True,
        )
    except Exception:
        pass
    await q.answer()


@Client.on_callback_query(filters.regex(r"^home$"))
async def home_cb(client: Client, q: CallbackQuery):
    buttons = [
        [InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{temp.U_NAME}?startgroup=true")],
        [InlineKeyboardButton("📖 Help", callback_data="help"),
         InlineKeyboardButton("ℹ About", callback_data="about")],
    ]
    try:
        if q.message.photo:
            await q.message.edit_caption(
                caption=script.START_TXT.format(q.from_user.mention),
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=enums.ParseMode.HTML,
            )
        else:
            await q.message.edit_text(
                script.START_TXT.format(q.from_user.mention),
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=enums.ParseMode.HTML,
            )
    except Exception:
        pass
    await q.answer()


@Client.on_callback_query(filters.regex(r"^noop$"))
async def noop_cb(client: Client, q: CallbackQuery):
    await q.answer()


@Client.on_message(filters.command("stats") & filters.incoming)
async def stats(client: Client, message: Message):
    if message.from_user.id not in ADMINS:
        return
    try:
        total_files = await Media.count_documents()
        total_users = await db.total_users_count()
        total_chats = await db.total_chat_count()
        db_size = await db.get_db_size()
        size_mb = round(db_size / (1024 * 1024), 2)
        await message.reply_text(
            script.STATUS_TXT.format(total_files, total_users, total_chats,
                                     f"{size_mb} MB", "N/A"),
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception as e:
        await message.reply_text(f"Error fetching stats: {e}")


@Client.on_message(filters.command("ping") & filters.incoming)
async def ping(client: Client, message: Message):
    import time as t
    start = t.monotonic()
    m = await message.reply_text("🏓")
    ms = round((t.monotonic() - start) * 1000, 2)
    uptime = int(t.time() - BOT_START_TIME)
    h, rem = divmod(uptime, 3600)
    mm, ss = divmod(rem, 60)
    await m.edit_text(
        f"🏓 <b>Pong!</b> <code>{ms}ms</code>\n"
        f"⏱ Uptime: <code>{h}h {mm}m {ss}s</code>",
        parse_mode=enums.ParseMode.HTML,
    )
