#  Advanced Shobana Filter Bot - Search, Filter, Pagination & Stream/Download
import asyncio
import logging
import re
from urllib.parse import quote

from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
)

from database.ia_filterdb import get_search_results
from database.users_chats_db import db
from info import (
    ADMINS, AUTH_GROUPS, P_TTI_SHOW_OFF, PROTECT_CONTENT,
    CUSTOM_FILE_CAPTION, SPELL_CHECK_REPLY,
    BIN_CHANNEL, STREAM_SERVER_URL, ENABLE_STREAM_BUTTONS,
    FILE_AUTO_DELETE_SECONDS,
)
from Script import script
from utils import temp, humanbytes

logger = logging.getLogger(__name__)
FILES_PER_PAGE = 10

# ─── Language / Quality / Season / Episode detection ─────────────────────────
LANGUAGE_LIST = [
    'Malayalam', 'Hindi', 'Tamil', 'Telugu', 'Kannada', 'Bengali',
    'English', 'Punjabi', 'Marathi', 'Gujarati', 'Odia',
    'HindiDub', 'TamilDub', 'TeluguDub', 'MalayalamDub',
    'Korean', 'Japanese', 'Chinese', 'French', 'Arabic', 'Russian',
]
QUALITY_LIST = [
    '4K', '2160p', '1080p', '720p', '480p', '360p',
    'HDRip', 'BluRay', 'WEB-DL', 'WEBRip', 'DVDRip',
    'HDTV', 'CAMRip', 'HQ', 'HD', 'SD',
]


def _extract_lang(name: str):
    for lang in LANGUAGE_LIST:
        if re.search(rf'\b{re.escape(lang)}\b', name, re.IGNORECASE):
            return lang
    return None


def _extract_qual(name: str):
    for qual in QUALITY_LIST:
        if re.search(rf'\b{re.escape(qual)}\b', name, re.IGNORECASE):
            return qual
    return None


def _extract_season(name: str):
    for pat in (r'S(\d{1,2})(?:E\d|$|\s)', r'Season[\s.\-_]?(\d{1,2})'):
        m = re.search(pat, name, re.IGNORECASE)
        if m:
            return f"S{int(m.group(1)):02d}"
    return None


def _extract_ep(name: str):
    for pat in (r'E(\d{1,3})', r'EP[\s.\-_]?(\d{1,3})', r'Episode[\s.\-_]?(\d{1,3})'):
        m = re.search(pat, name, re.IGNORECASE)
        if m:
            return f"E{int(m.group(1)):02d}"
    return None


# ─── Filter state store ───────────────────────────────────────────────────────
# Key: (chat_id, msg_id)
FILTER_STATES: dict = {}

MAX_STATES = 500
PRUNE_COUNT = 50


def _save_state(chat_id: int, msg_id: int, state: dict):
    key = (chat_id, msg_id)
    FILTER_STATES[key] = state
    if len(FILTER_STATES) > MAX_STATES:
        for k in list(FILTER_STATES.keys())[:PRUNE_COUNT]:
            FILTER_STATES.pop(k, None)


def _get_state(chat_id: int, msg_id: int):
    return FILTER_STATES.get((chat_id, msg_id))


# ─── URL helpers ──────────────────────────────────────────────────────────────
def _stream_url(bin_msg_id: int, fname: str) -> str:
    enc = quote(fname.replace('/', '_'), safe='')
    return f"{STREAM_SERVER_URL}/watch/{bin_msg_id}/{enc}"


def _dl_url(bin_msg_id: int, fname: str) -> str:
    enc = quote(fname.replace('/', '_'), safe='')
    return f"{STREAM_SERVER_URL}/dl/{bin_msg_id}/{enc}"


# ─── Filter helpers ───────────────────────────────────────────────────────────
def _apply(files, lang=None, qual=None, season=None, ep=None):
    out = files
    if lang:
        out = [f for f in out if _extract_lang(f.file_name or '') == lang]
    if qual:
        out = [f for f in out if _extract_qual(f.file_name or '') == qual]
    if season:
        out = [f for f in out if _extract_season(f.file_name or '') == season]
    if ep:
        out = [f for f in out if _extract_ep(f.file_name or '') == ep]
    return out


def _uniq(it):
    seen = set()
    return [x for x in it if not (x in seen or seen.add(x))]


# ─── Keyboard builder ─────────────────────────────────────────────────────────
def _build_kb(state: dict, msg_id: int, chat_id: int) -> InlineKeyboardMarkup:
    lang = state.get('lang')
    qual = state.get('qual')
    season = state.get('season')
    ep = state.get('ep')
    page = state.get('page', 0)

    filtered = _apply(state['all_files'], lang, qual, season, ep)
    total = len(filtered)
    total_pages = max(1, (total + FILES_PER_PAGE - 1) // FILES_PER_PAGE)
    page = min(page, total_pages - 1)
    page_files = filtered[page * FILES_PER_PAGE:(page + 1) * FILES_PER_PAGE]

    rows = []

    # ── File buttons ──
    for i, f in enumerate(page_files):
        fname = f.file_name or 'Unknown'
        label = (fname[:55] + '…') if len(fname) > 55 else fname
        abs_idx = page * FILES_PER_PAGE + i
        rows.append([InlineKeyboardButton(
            f"📄 {label}",
            callback_data=f"sf|{chat_id}|{msg_id}|{abs_idx}"
        )])

    # ── Filter buttons ──
    lang_lbl = f"🌍 {lang} ✅" if lang else "🌍 Language"
    qual_lbl = f"🎬 {qual} ✅" if qual else "🎬 Quality"
    rows.append([
        InlineKeyboardButton(lang_lbl, callback_data=f"flang|{chat_id}|{msg_id}"),
        InlineKeyboardButton(qual_lbl, callback_data=f"fqual|{chat_id}|{msg_id}"),
    ])
    season_lbl = f"📺 {season} ✅" if season else "📺 Season"
    ep_lbl = f"🎞 {ep} ✅" if ep else "🎞 Episode"
    rows.append([
        InlineKeyboardButton(season_lbl, callback_data=f"fseason|{chat_id}|{msg_id}"),
        InlineKeyboardButton(ep_lbl, callback_data=f"fep|{chat_id}|{msg_id}"),
    ])

    # ── Pagination ──
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀", callback_data=f"page|{chat_id}|{msg_id}|{page - 1}"))
        nav.append(InlineKeyboardButton(
            f"{page + 1}/{total_pages}",
            callback_data=f"pginfo|{chat_id}|{msg_id}"
        ))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("▶", callback_data=f"page|{chat_id}|{msg_id}|{page + 1}"))
        rows.append(nav)

    # ── Summary ──
    active = " | ".join(x for x in [lang, qual, season, ep] if x) or "All"
    rows.append([InlineKeyboardButton(
        f"🔎 {total} result{'s' if total != 1 else ''} [{active}]",
        callback_data=f"pginfo|{chat_id}|{msg_id}"
    )])

    return InlineKeyboardMarkup(rows)


# ─── File sender with Stream/Download buttons ─────────────────────────────────
async def _send_file(client: Client, chat_id: int, reply_to_id: int, file_doc):
    fname = file_doc.file_name or 'Unknown'
    fsize = file_doc.file_size or 0
    ftype = file_doc.file_type or 'document'
    file_id = file_doc.file_id

    caption = ""
    if CUSTOM_FILE_CAPTION:
        try:
            caption = CUSTOM_FILE_CAPTION.format(
                file_name=fname,
                file_size=humanbytes(fsize),
                file_caption=file_doc.caption or '',
            )
        except Exception:
            caption = f"📂 <code>{fname}</code>"
    else:
        caption = f"📂 <code>{fname}</code>"

    kw = dict(
        chat_id=chat_id,
        caption=caption,
        parse_mode=enums.ParseMode.HTML,
        protect_content=PROTECT_CONTENT,
        reply_to_message_id=reply_to_id,
    )

    sent = None
    try:
        if ftype == 'video':
            sent = await client.send_video(video=file_id, **kw)
        elif ftype == 'audio':
            sent = await client.send_audio(audio=file_id, **kw)
        else:
            sent = await client.send_document(document=file_id, **kw)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        try:
            sent = await client.send_document(document=file_id, **kw)
        except Exception as err:
            logger.error(f"Re-send failed: {err}")
            return
    except Exception as e:
        logger.error(f"Send failed: {e}")
        return

    # Stream / Download buttons
    if sent and ENABLE_STREAM_BUTTONS and BIN_CHANNEL and STREAM_SERVER_URL:
        bin_msg = None
        try:
            bin_msg = await client.copy_message(
                chat_id=BIN_CHANNEL,
                from_chat_id=chat_id,
                message_id=sent.id,
            )
        except Exception as e:
            logger.warning(f"BIN_CHANNEL copy failed: {e}")

        if bin_msg:
            markup = InlineKeyboardMarkup([[
                InlineKeyboardButton("🌐 Stream", url=_stream_url(bin_msg.id, fname)),
                InlineKeyboardButton("⬇️ Download", url=_dl_url(bin_msg.id, fname)),
            ]])
            try:
                await client.send_message(
                    chat_id=chat_id,
                    text=f"<b>🎬 {fname}</b>",
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=markup,
                    reply_to_message_id=sent.id,
                )
            except Exception as e:
                logger.warning(f"Stream button send failed: {e}")

    # Auto-delete
    if sent and FILE_AUTO_DELETE_SECONDS and FILE_AUTO_DELETE_SECONDS > 0:
        asyncio.create_task(_auto_del(client, chat_id, sent.id, FILE_AUTO_DELETE_SECONDS))


async def _auto_del(client, chat_id, msg_id, delay):
    await asyncio.sleep(delay)
    try:
        await client.delete_messages(chat_id, msg_id)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Auto-filter handler (text messages in groups)
# ─────────────────────────────────────────────────────────────────────────────
SKIP_COMMANDS = [
    "start", "help", "about", "settings", "connect", "disconnect",
    "connections", "filter", "filters", "del", "delall", "stats",
    "broadcast", "ban", "unban", "logs", "users", "chats", "ping",
    "movies", "series", "imdb", "search", "deletefiles", "channel",
]


@Client.on_message(
    filters.text & filters.group & ~filters.via_bot & ~filters.bot
    & ~filters.command(SKIP_COMMANDS)
)
async def auto_filter(client: Client, message: Message):
    if message.from_user and message.from_user.id in temp.BANNED_USERS:
        return
    if message.chat.id in temp.BANNED_CHATS:
        return
    if AUTH_GROUPS and message.chat.id not in AUTH_GROUPS:
        return

    query = (message.text or '').strip()
    if len(query) < 2:
        return

    chat_id = message.chat.id

    # Fetch ALL results (up to 200 for pagination)
    try:
        result = await get_search_results(query, max_results=200, offset=0)
        files = result[0]
        total = result[2]
    except Exception as e:
        logger.error(f"get_search_results error: {e}")
        return

    if not files:
        if SPELL_CHECK_REPLY:
            await message.reply_text(
                script.SPOLL_NOT_FND,
                parse_mode=enums.ParseMode.HTML,
            )
        return

    # Send placeholder to get the message id first
    try:
        placeholder = await message.reply_text(
            f"♻️ Searching <b>{query}</b>...",
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"placeholder send failed: {e}")
        return

    state = {
        'query': query,
        'all_files': files,
        'lang': None, 'qual': None, 'season': None, 'ep': None,
        'page': 0,
    }
    _save_state(chat_id, placeholder.id, state)

    markup = _build_kb(state, placeholder.id, chat_id)
    try:
        await placeholder.edit_text(
            f"<b>🔍 Results for:</b> <code>{query}</code>\n"
            f"📂 Found <b>{len(files)}</b> file(s). Tap to send:",
            parse_mode=enums.ParseMode.HTML,
            reply_markup=markup,
        )
    except Exception as e:
        logger.error(f"edit results failed: {e}")


# ─── Callbacks ────────────────────────────────────────────────────────────────

# Select file
@Client.on_callback_query(filters.regex(r"^sf\|"))
async def cb_sf(client: Client, q: CallbackQuery):
    parts = q.data.split("|")
    if len(parts) < 4:
        return await q.answer("Invalid", show_alert=True)
    _, chat_id, msg_id, idx = parts[0], int(parts[1]), int(parts[2]), int(parts[3])

    state = _get_state(chat_id, msg_id)
    if not state:
        return await q.answer("⚠️ Session expired. Search again.", show_alert=True)

    filtered = _apply(state['all_files'], state.get('lang'), state.get('qual'),
                      state.get('season'), state.get('ep'))
    if idx >= len(filtered):
        return await q.answer("File not found.", show_alert=True)

    file_doc = filtered[idx]
    await q.answer("📤 Sending...")
    target = q.from_user.id if P_TTI_SHOW_OFF else q.message.chat.id
    reply_to = q.message.id if not P_TTI_SHOW_OFF else None

    asyncio.create_task(_send_file(client, target, reply_to, file_doc))


# Language list
@Client.on_callback_query(filters.regex(r"^flang\|"))
async def cb_flang(client: Client, q: CallbackQuery):
    _, chat_id, msg_id = q.data.split("|")
    chat_id, msg_id = int(chat_id), int(msg_id)
    state = _get_state(chat_id, msg_id)
    if not state:
        return await q.answer("⚠️ Session expired.", show_alert=True)

    langs = _uniq([_extract_lang(f.file_name or '') for f in state['all_files']])
    langs = [l for l in langs if l]
    if not langs:
        return await q.answer("No language tags found in results.", show_alert=True)

    rows = [[InlineKeyboardButton(
        ("✅ " if state.get('lang') == l else "") + l,
        callback_data=f"slang|{chat_id}|{msg_id}|{l}"
    )] for l in langs]
    if state.get('lang'):
        rows.append([InlineKeyboardButton("❌ Clear", callback_data=f"slang|{chat_id}|{msg_id}|__clear__")])
    rows.append([InlineKeyboardButton("« Back", callback_data=f"back|{chat_id}|{msg_id}")])
    try:
        await q.message.edit_reply_markup(InlineKeyboardMarkup(rows))
    except MessageNotModified:
        pass
    await q.answer()


@Client.on_callback_query(filters.regex(r"^slang\|"))
async def cb_slang(client: Client, q: CallbackQuery):
    parts = q.data.split("|", 4)
    chat_id, msg_id, val = int(parts[1]), int(parts[2]), parts[3]
    state = _get_state(chat_id, msg_id)
    if not state:
        return await q.answer("⚠️ Session expired.", show_alert=True)
    state['lang'] = None if val == "__clear__" else val
    state['page'] = 0
    _save_state(chat_id, msg_id, state)
    try:
        await q.message.edit_reply_markup(_build_kb(state, msg_id, chat_id))
    except MessageNotModified:
        pass
    await q.answer(f"Language: {val if val != '__clear__' else 'cleared'}")


# Quality list
@Client.on_callback_query(filters.regex(r"^fqual\|"))
async def cb_fqual(client: Client, q: CallbackQuery):
    _, chat_id, msg_id = q.data.split("|")
    chat_id, msg_id = int(chat_id), int(msg_id)
    state = _get_state(chat_id, msg_id)
    if not state:
        return await q.answer("⚠️ Session expired.", show_alert=True)

    pool = _apply(state['all_files'], lang=state.get('lang'))
    quals = _uniq([_extract_qual(f.file_name or '') for f in pool])
    quals = [q_ for q_ in quals if q_]
    if not quals:
        return await q.answer("No quality tags found.", show_alert=True)

    rows = [[InlineKeyboardButton(
        ("✅ " if state.get('qual') == qv else "") + qv,
        callback_data=f"squal|{chat_id}|{msg_id}|{qv}"
    )] for qv in quals]
    if state.get('qual'):
        rows.append([InlineKeyboardButton("❌ Clear", callback_data=f"squal|{chat_id}|{msg_id}|__clear__")])
    rows.append([InlineKeyboardButton("« Back", callback_data=f"back|{chat_id}|{msg_id}")])
    try:
        await q.message.edit_reply_markup(InlineKeyboardMarkup(rows))
    except MessageNotModified:
        pass
    await q.answer()


@Client.on_callback_query(filters.regex(r"^squal\|"))
async def cb_squal(client: Client, q: CallbackQuery):
    parts = q.data.split("|", 4)
    chat_id, msg_id, val = int(parts[1]), int(parts[2]), parts[3]
    state = _get_state(chat_id, msg_id)
    if not state:
        return await q.answer("⚠️ Session expired.", show_alert=True)
    state['qual'] = None if val == "__clear__" else val
    state['page'] = 0
    _save_state(chat_id, msg_id, state)
    try:
        await q.message.edit_reply_markup(_build_kb(state, msg_id, chat_id))
    except MessageNotModified:
        pass
    await q.answer(f"Quality: {val if val != '__clear__' else 'cleared'}")


# Season list
@Client.on_callback_query(filters.regex(r"^fseason\|"))
async def cb_fseason(client: Client, q: CallbackQuery):
    _, chat_id, msg_id = q.data.split("|")
    chat_id, msg_id = int(chat_id), int(msg_id)
    state = _get_state(chat_id, msg_id)
    if not state:
        return await q.answer("⚠️ Session expired.", show_alert=True)

    pool = _apply(state['all_files'], lang=state.get('lang'), qual=state.get('qual'))
    seasons = sorted(set(s for f in pool if (s := _extract_season(f.file_name or ''))))
    if not seasons:
        return await q.answer("No season info found.", show_alert=True)

    rows = [[InlineKeyboardButton(
        ("✅ " if state.get('season') == s else "") + s,
        callback_data=f"sseason|{chat_id}|{msg_id}|{s}"
    )] for s in seasons]
    if state.get('season'):
        rows.append([InlineKeyboardButton("❌ Clear", callback_data=f"sseason|{chat_id}|{msg_id}|__clear__")])
    rows.append([InlineKeyboardButton("« Back", callback_data=f"back|{chat_id}|{msg_id}")])
    try:
        await q.message.edit_reply_markup(InlineKeyboardMarkup(rows))
    except MessageNotModified:
        pass
    await q.answer()


@Client.on_callback_query(filters.regex(r"^sseason\|"))
async def cb_sseason(client: Client, q: CallbackQuery):
    parts = q.data.split("|", 4)
    chat_id, msg_id, val = int(parts[1]), int(parts[2]), parts[3]
    state = _get_state(chat_id, msg_id)
    if not state:
        return await q.answer("⚠️ Session expired.", show_alert=True)
    state['season'] = None if val == "__clear__" else val
    state['ep'] = None
    state['page'] = 0
    _save_state(chat_id, msg_id, state)
    try:
        await q.message.edit_reply_markup(_build_kb(state, msg_id, chat_id))
    except MessageNotModified:
        pass
    await q.answer(f"Season: {val if val != '__clear__' else 'cleared'}")


# Episode list
@Client.on_callback_query(filters.regex(r"^fep\|"))
async def cb_fep(client: Client, q: CallbackQuery):
    _, chat_id, msg_id = q.data.split("|")
    chat_id, msg_id = int(chat_id), int(msg_id)
    state = _get_state(chat_id, msg_id)
    if not state:
        return await q.answer("⚠️ Session expired.", show_alert=True)

    pool = _apply(state['all_files'], lang=state.get('lang'), qual=state.get('qual'),
                  season=state.get('season'))
    eps = sorted(set(e for f in pool if (e := _extract_ep(f.file_name or ''))))
    if not eps:
        return await q.answer("No episode info found.", show_alert=True)

    rows, row = [], []
    for ep in eps:
        row.append(InlineKeyboardButton(
            ("✅ " if state.get('ep') == ep else "") + ep,
            callback_data=f"sep|{chat_id}|{msg_id}|{ep}"
        ))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if state.get('ep'):
        rows.append([InlineKeyboardButton("❌ Clear", callback_data=f"sep|{chat_id}|{msg_id}|__clear__")])
    rows.append([InlineKeyboardButton("« Back", callback_data=f"back|{chat_id}|{msg_id}")])
    try:
        await q.message.edit_reply_markup(InlineKeyboardMarkup(rows))
    except MessageNotModified:
        pass
    await q.answer()


@Client.on_callback_query(filters.regex(r"^sep\|"))
async def cb_sep(client: Client, q: CallbackQuery):
    parts = q.data.split("|", 4)
    chat_id, msg_id, val = int(parts[1]), int(parts[2]), parts[3]
    state = _get_state(chat_id, msg_id)
    if not state:
        return await q.answer("⚠️ Session expired.", show_alert=True)
    state['ep'] = None if val == "__clear__" else val
    state['page'] = 0
    _save_state(chat_id, msg_id, state)
    try:
        await q.message.edit_reply_markup(_build_kb(state, msg_id, chat_id))
    except MessageNotModified:
        pass
    await q.answer(f"Episode: {val if val != '__clear__' else 'cleared'}")


# Pagination
@Client.on_callback_query(filters.regex(r"^page\|"))
async def cb_page(client: Client, q: CallbackQuery):
    parts = q.data.split("|")
    chat_id, msg_id, new_page = int(parts[1]), int(parts[2]), int(parts[3])
    state = _get_state(chat_id, msg_id)
    if not state:
        return await q.answer("⚠️ Session expired.", show_alert=True)
    state['page'] = new_page
    _save_state(chat_id, msg_id, state)
    try:
        await q.message.edit_reply_markup(_build_kb(state, msg_id, chat_id))
    except MessageNotModified:
        pass
    await q.answer(f"Page {new_page + 1}")


@Client.on_callback_query(filters.regex(r"^pginfo\|"))
async def cb_pginfo(client: Client, q: CallbackQuery):
    parts = q.data.split("|")
    chat_id, msg_id = int(parts[1]), int(parts[2])
    state = _get_state(chat_id, msg_id)
    if not state:
        return await q.answer("Session expired", show_alert=True)
    filtered = _apply(state['all_files'], state.get('lang'), state.get('qual'),
                      state.get('season'), state.get('ep'))
    total_pages = max(1, (len(filtered) + FILES_PER_PAGE - 1) // FILES_PER_PAGE)
    await q.answer(
        f"Page {state.get('page', 0) + 1}/{total_pages} • {len(filtered)} files",
        show_alert=True,
    )


# Back to results
@Client.on_callback_query(filters.regex(r"^back\|"))
async def cb_back(client: Client, q: CallbackQuery):
    parts = q.data.split("|")
    chat_id, msg_id = int(parts[1]), int(parts[2])
    state = _get_state(chat_id, msg_id)
    if not state:
        return await q.answer("⚠️ Session expired.", show_alert=True)
    try:
        await q.message.edit_reply_markup(_build_kb(state, msg_id, chat_id))
    except MessageNotModified:
        pass
    await q.answer()
