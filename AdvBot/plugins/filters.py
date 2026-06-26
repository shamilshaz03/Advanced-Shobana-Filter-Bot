# plugins/filters.py - Manual filter add/view/delete
import logging
from pyrogram import Client, filters, enums
from pyrogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
)
from database.filters_mdb import (
    add_filter, find_filter, get_filters, delete_filter, del_all
)
from info import ADMINS

logger = logging.getLogger(__name__)


async def _is_admin(client, chat_id, user_id):
    if user_id in ADMINS:
        return True
    try:
        m = await client.get_chat_member(chat_id, user_id)
        return m.status in [enums.ChatMemberStatus.ADMINISTRATOR,
                             enums.ChatMemberStatus.OWNER]
    except Exception:
        return False


@Client.on_message(filters.command(["filter", "add"]) & filters.group)
async def cmd_add_filter(client: Client, msg: Message):
    if not msg.from_user:
        return
    if not await _is_admin(client, msg.chat.id, msg.from_user.id):
        return await msg.reply_text("Only admins can add filters.")
    if not msg.reply_to_message:
        return await msg.reply_text("Reply to a message with /filter <keyword>")
    args = msg.text.split(None, 1)
    if len(args) < 2:
        return await msg.reply_text("Usage: /filter <keyword>")

    keyword = args[1].strip().lower()
    reply = msg.reply_to_message
    reply_text = reply.text or reply.caption or ''
    file_id = (
        getattr(reply.document, 'file_id', '') or
        getattr(reply.video, 'file_id', '') or
        getattr(reply.audio, 'file_id', '') or
        getattr(reply.photo, 'file_id', '') or ''
    )
    await add_filter(msg.chat.id, keyword, reply_text, '', file_id, '')
    await msg.reply_text(
        f"✅ Filter added for: <code>{keyword}</code>",
        parse_mode=enums.ParseMode.HTML,
    )


@Client.on_message(filters.command(["filters", "viewfilters"]) & filters.group)
async def cmd_list_filters(client: Client, msg: Message):
    kws = await get_filters(msg.chat.id)
    if not kws:
        return await msg.reply_text("No filters in this group.")
    text = f"<b>Filters ({len(kws)}):</b>\n" + "\n".join(f"• <code>{k}</code>" for k in kws[:50])
    if len(kws) > 50:
        text += f"\n…and {len(kws)-50} more"
    await msg.reply_text(text, parse_mode=enums.ParseMode.HTML)


@Client.on_message(filters.command("del") & filters.group)
async def cmd_del_filter(client: Client, msg: Message):
    if not msg.from_user or not await _is_admin(client, msg.chat.id, msg.from_user.id):
        return
    args = msg.text.split(None, 1)
    if len(args) < 2:
        return await msg.reply_text("Usage: /del <keyword>")
    await delete_filter(msg, args[1].strip().lower(), msg.chat.id)


@Client.on_message(filters.command("delall") & filters.group)
async def cmd_delall(client: Client, msg: Message):
    if not msg.from_user or not await _is_admin(client, msg.chat.id, msg.from_user.id):
        return
    prompt = await msg.reply_text(
        "⚠️ Delete ALL filters in this group?",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Yes", callback_data=f"delafilters|{msg.chat.id}"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancelda"),
        ]]),
    )


@Client.on_callback_query(filters.regex(r"^delafilters\|"))
async def confirm_delall(client, q: CallbackQuery):
    chat_id = int(q.data.split("|")[1])
    try:
        title = (await client.get_chat(chat_id)).title or str(chat_id)
    except Exception:
        title = str(chat_id)
    m = await q.message.edit_text("Deleting…")
    await del_all(m, chat_id, title)


@Client.on_callback_query(filters.regex(r"^cancelda$"))
async def cancel_delall(client, q: CallbackQuery):
    await q.message.delete()
    await q.answer("Cancelled")
