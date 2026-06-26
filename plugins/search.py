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

try:
    from database.ia_filterdb import get_search_results
except Exception:  # pragma: no cover - allows import in lightweight test environments
    get_search_results = None

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


def _slugify(value) -> str:
    return re.sub(r'[^a-z0-9]+', '_', str(value).strip().lower()).strip('_')


def _parse_callback_data(data: str):
    if not data:
        return {}

    if '|' in data:
        parts = data.split('|')
        action = parts[0]
        if action == 'sf' and len(parts) >= 4:
            return {'action': 'sf', 'chat_id': int(parts[1]), 'msg_id': int(parts[2]), 'value': parts[3]}
        if action in {'page', 'pginfo', 'back'} and len(parts) >= 3:
            payload = {'action': action, 'chat_id': int(parts[1]), 'msg_id': int(parts[2])}
            if len(parts) >= 4:
                payload['value'] = parts[3]
            return payload
        if action in {'slang', 'squal', 'sseason', 'sep'} and len(parts) >= 4:
            return {'action': action, 'chat_id': int(parts[1]), 'msg_id': int(parts[2]), 'value': parts[3]}
        if action in {'stream', 'download'} and len(parts) >= 2:
            return {'action': action, 'value': parts[1]}
        return {'action': action}

    if data in {'prev', 'next', 'lang', 'quality', 'season', 'episode', 'back'}:
        return {'action': data}
    if data.startswith('lang_'):
        return {'action': 'lang', 'value': data.split('_', 1)[1]}
    if data.startswith('quality_'):
        return {'action': 'quality', 'value': data.split('_', 1)[1]}
    if data.startswith('season_'):
        return {'action': 'season', 'value': data.split('_', 1)[1]}
    if data.startswith('episode_'):
        return {'action': 'episode', 'value': data.split('_', 1)[1]}
    if data.startswith('page_'):
        return {'action': 'page', 'value': data.split('_', 1)[1]}
    if data.startswith('stream_'):
        return {'action': 'stream', 'value': data.split('_', 1)[1]}
    if data.startswith('download_'):
        return {'action': 'download', 'value': data.split('_', 1)[1]}
    return {'action': data}


# ─── Keyboard builder ─────────────────────────────────────────────────────────
def _build_filter_menu(state: dict, msg_id: int, chat_id: int, kind: str) -> InlineKeyboardMarkup:
    current = state.get(kind)
    if kind == 'lang':
        options = [l for l in _uniq([_extract_lang(f.file_name or '') for f in state['all_files']]) if l]
    elif kind == 'quality':
        options = [q for q in _uniq([_extract_qual(f.file_name or '') for f in _apply(state['all_files'], lang=state.get('lang'))]) if q]
    elif kind == 'season':
        options = sorted(set(s for f in _apply(state['all_files'], lang=state.get('lang'), qual=state.get('qual')) if (s := _extract_season(f.file_name or ''))))
    elif kind == 'episode':
        options = sorted(set(e for f in _apply(state['all_files'], lang=state.get('lang'), qual=state.get('qual'), season=state.get('season')) if (e := _extract_ep(f.file_name or ''))))
    else:
        options = []

    rows = []
    for value in options:
        rows.append([InlineKeyboardButton(
            ("✅ " if current == value else "") + value,
            callback_data=f"{kind}_{_slugify(value)}"
        )])
    if current:
        rows.append([InlineKeyboardButton("❌ Clear", callback_data=f"{kind}_clear")])
    rows.append([InlineKeyboardButton("« Back", callback_data="back")])
    return InlineKeyboardMarkup(rows)


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
        InlineKeyboardButton(lang_lbl, callback_data='lang'),
        InlineKeyboardButton(qual_lbl, callback_data='quality'),
    ])
    season_lbl = f"📺 {season} ✅" if season else "📺 Season"
    ep_lbl = f"🎞 {ep} ✅" if ep else "🎞 Episode"
    rows.append([
        InlineKeyboardButton(season_lbl, callback_data='season'),
        InlineKeyboardButton(ep_lbl, callback_data='episode'),
    ])

    # ── Pagination ──
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀", callback_data=f"page|{chat_id}|{msg_id}|{page - 1}"))
        nav.append(InlineKeyboardButton(
            f"{page + 1}/{total_pages}",
            callback_data=f"page|{chat_id}|{msg_id}|{page}"
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
        if get_search_results is None:
            raise RuntimeError("search backend unavailable")
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

async def _refresh_results_markup(client: Client, q: CallbackQuery, state: dict, chat_id: int, msg_id: int):
    try:
        await q.message.edit_reply_markup(_build_kb(state, msg_id, chat_id))
    except MessageNotModified:
        pass
    except Exception as e:
        logger.exception("Failed to refresh results for callback %s", q.data)
        await q.answer("Something went wrong while refreshing the results.", show_alert=True)
        raise


# Select file
@Client.on_callback_query(filters.regex(r"^sf\|"))
async def cb_sf(client: Client, q: CallbackQuery):
    try:
        payload = _parse_callback_data(q.data)
        logger.info("callback received: %s", q.data)
        if payload.get('action') != 'sf':
            return await q.answer("Invalid callback.", show_alert=True)

        chat_id = int(payload['chat_id'])
        msg_id = int(payload['msg_id'])
        idx = int(payload['value'])
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
    except Exception as e:
        logger.exception("Failed to handle file selection callback %s", q.data)
        await q.answer("Unable to send that file right now.", show_alert=True)


# Language actions
@Client.on_callback_query(filters.regex(r"^(?:lang|quality|season|episode)$"))
async def cb_show_filter_menu(client: Client, q: CallbackQuery):
    try:
        logger.info("callback received: %s", q.data)
        kind = q.data
        chat_id = q.message.chat.id
        msg_id = q.message.id
        state = _get_state(chat_id, msg_id)
        if not state:
            return await q.answer("⚠️ Session expired.", show_alert=True)
        menu = _build_filter_menu(state, msg_id, chat_id, kind)
        await q.message.edit_reply_markup(menu)
        await q.answer(f"Loading {kind} filters...", show_alert=False)
    except Exception as e:
        logger.exception("Failed to show filter menu for %s", q.data)
        await q.answer("Unable to open that filter menu right now.", show_alert=True)


@Client.on_callback_query(filters.regex(r"^(?:lang|quality|season|episode)_(.+)$"))
async def cb_apply_filter(client: Client, q: CallbackQuery):
    try:
        logger.info("callback received: %s", q.data)
        kind, value = q.data.split('_', 1)
        chat_id = q.message.chat.id
        msg_id = q.message.id
        state = _get_state(chat_id, msg_id)
        if not state:
            return await q.answer("⚠️ Session expired.", show_alert=True)

        if kind == 'lang':
            state['lang'] = None if value == 'clear' else value.replace('_', ' ')
        elif kind == 'quality':
            state['qual'] = None if value == 'clear' else value.replace('_', ' ')
        elif kind == 'season':
            state['season'] = None if value == 'clear' else value.replace('_', ' ')
        elif kind == 'episode':
            state['ep'] = None if value == 'clear' else value.replace('_', ' ')
        state['page'] = 0
        _save_state(chat_id, msg_id, state)
        await _refresh_results_markup(client, q, state, chat_id, msg_id)
        label = {
            'lang': 'Language',
            'quality': 'Quality',
            'season': 'Season',
            'episode': 'Episode',
        }[kind]
        await q.answer(f"{label}: {value.replace('_', ' ') if value != 'clear' else 'cleared'}")
    except Exception as e:
        logger.exception("Failed to apply filter callback %s", q.data)
        await q.answer("Unable to apply that filter.", show_alert=True)


# Pagination and info
@Client.on_callback_query(filters.regex(r"^(?:prev|next|page_\d+)$"))
async def cb_page(client: Client, q: CallbackQuery):
    try:
        logger.info("callback received: %s", q.data)
        payload = _parse_callback_data(q.data)
        if payload.get('action') not in {'page', 'prev', 'next'}:
            return await q.answer("Invalid callback.", show_alert=True)

        chat_id = q.message.chat.id
        msg_id = q.message.id
        state = _get_state(chat_id, msg_id)
        if not state:
            return await q.answer("⚠️ Session expired.", show_alert=True)

        filtered = _apply(state['all_files'], state.get('lang'), state.get('qual'),
                          state.get('season'), state.get('ep'))
        total_pages = max(1, (len(filtered) + FILES_PER_PAGE - 1) // FILES_PER_PAGE)
        if q.data == 'prev':
            state['page'] = max(0, state.get('page', 0) - 1)
        elif q.data == 'next':
            state['page'] = min(total_pages - 1, state.get('page', 0) + 1)
        else:
            state['page'] = max(0, min(total_pages - 1, int(payload.get('value', 1)) - 1))
        _save_state(chat_id, msg_id, state)
        await _refresh_results_markup(client, q, state, chat_id, msg_id)
        await q.answer(f"Page {state.get('page', 0) + 1}/{total_pages}")
    except Exception as e:
        logger.exception("Failed to handle pagination callback %s", q.data)
        await q.answer("Unable to change page right now.", show_alert=True)


@Client.on_callback_query(filters.regex(r"^back(?:\||$)"))
async def cb_back(client: Client, q: CallbackQuery):
    try:
        logger.info("callback received: %s", q.data)
        payload = _parse_callback_data(q.data)
        if payload.get('action') not in {'back', 'pginfo'}:
            return await q.answer("Invalid callback.", show_alert=True)

        chat_id = q.message.chat.id
        msg_id = q.message.id
        state = _get_state(chat_id, msg_id)
        if not state:
            return await q.answer("⚠️ Session expired.", show_alert=True)
        await _refresh_results_markup(client, q, state, chat_id, msg_id)
        await q.answer()
    except Exception as e:
        logger.exception("Failed to handle back callback %s", q.data)
        await q.answer("Unable to return to the results.", show_alert=True)


@Client.on_callback_query(filters.regex(r"^(?:stream|download)_"))
async def cb_stream_or_download(client: Client, q: CallbackQuery):
    try:
        logger.info("callback received: %s", q.data)
        payload = _parse_callback_data(q.data)
        if payload.get('action') not in {'stream', 'download'}:
            return await q.answer("Invalid callback.", show_alert=True)
        action = payload['action']
        await q.answer(f"Opening {action} link...", show_alert=False)
    except Exception as e:
        logger.exception("Failed to handle stream/download callback %s", q.data)
        await q.answer("Unable to open that link right now.", show_alert=True)
