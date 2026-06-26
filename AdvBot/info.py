import re
from os import environ
from Script import script
from time import time

id_pattern = re.compile(r'^.\d+$')

def is_enabled(value, default):
    if not value:
        return default
    if str(value).lower() in ["true", "yes", "1", "enable", "y"]:
        return True
    elif str(value).lower() in ["false", "no", "0", "disable", "n"]:
        return False
    return default

def parse_size_to_bytes(value, default=0):
    if not value:
        return default
    raw = str(value).strip().lower()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([kmgtp]?b?)?", raw)
    if not m:
        return default
    number = float(m.group(1))
    unit = (m.group(2) or "b").rstrip("b")
    scale = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4, "p": 1024**5}
    return int(number * scale.get(unit, 1))

SESSION = environ.get('SESSION', 'Media_search')
API_ID = int(environ.get('API_ID', '0'))
API_HASH = environ.get('API_HASH', '')
BOT_TOKEN = environ.get('BOT_TOKEN', '')

KEEP_ALIVE_URL = environ.get("KEEP_ALIVE_URL", "")
HYPER_MODE = is_enabled(environ.get('HYPER_MODE', ''), False)
BOT_START_TIME = time()
CACHE_TIME = int(environ.get('CACHE_TIME', 300))
USE_CAPTION_FILTER = is_enabled(environ.get('USE_CAPTION_FILTER', ''), False)
PICS = (environ.get('PICS', 'https://graph.org/file/2ed90a79eb533d86f8a0f.jpg')).split()

ADMINS = [int(a) if id_pattern.search(a) else a for a in environ.get('ADMINS', '').split() if a]
CHANNELS = [int(c) if id_pattern.search(c) else c for c in environ.get('CHANNELS', '').split() if c]
auth_users = [int(u) if id_pattern.search(u) else u for u in environ.get('AUTH_USERS', '').split() if u]
AUTH_USERS = (auth_users + ADMINS) if auth_users else []
auth_grp = environ.get('AUTH_GROUP', '')
DEFAULT_AUTH_CHANNELS = [int(x) for x in environ.get("AUTH_CHANNEL", "").split() if x.lstrip('-').isdigit()]
AUTH_GROUPS = [int(c) for c in auth_grp.split() if c.lstrip('-').isdigit()] if auth_grp else None

DATABASE_URI = environ.get('DATABASE_URI', "")
DATABASE_NAME = environ.get('DATABASE_NAME', "Cluster0")
COLLECTION_NAME = environ.get('COLLECTION_NAME', 'mn_files')
DATABASE_URI2 = environ.get('DATABASE_URI2', "")
DATABASE_URI3 = environ.get('DATABASE_URI3', "")
DATABASE_URI4 = environ.get('DATABASE_URI4', "")
DATABASE_URI5 = environ.get('DATABASE_URI5', "")
DATABASE_NAME2 = environ.get('DATABASE_NAME2', DATABASE_NAME)
DATABASE_NAME3 = environ.get('DATABASE_NAME3', DATABASE_NAME)
DATABASE_NAME4 = environ.get('DATABASE_NAME4', DATABASE_NAME)
DATABASE_NAME5 = environ.get('DATABASE_NAME5', DATABASE_NAME)
POSTGRES_URI = environ.get('POSTGRES_URI', '')

FILE_AUTO_DELETE_SECONDS = int(environ.get('FILE_AUTO_DELETE_SECONDS', 60))
DELETE_USER_SEARCH_MESSAGE = is_enabled(environ.get('DELETE_USER_SEARCH_MESSAGE', ''), False)

LOG_CHANNEL = int(environ.get('LOG_CHANNEL', '0'))
SUPPORT_CHAT = environ.get('SUPPORT_CHAT', '')
P_TTI_SHOW_OFF = is_enabled(environ.get('P_TTI_SHOW_OFF', ''), False)
IMDB = is_enabled(environ.get('IMDB', ''), False)
SINGLE_BUTTON = is_enabled(environ.get('SINGLE_BUTTON', 'True'), True)
CUSTOM_FILE_CAPTION = environ.get("CUSTOM_FILE_CAPTION", script.CUSTOM_FILE_CAPTION)
BATCH_FILE_CAPTION = environ.get("BATCH_FILE_CAPTION", "📂 <em>{file_name}</em>\n♻ {file_size}")
IMDB_TEMPLATE = environ.get("IMDB_TEMPLATE", "🏷 <a href={url}>{title}</a>\n📅 {year}\n⭐ {rating}/10\n🎭 {genres}")
LONG_IMDB_DESCRIPTION = is_enabled(environ.get("LONG_IMDB_DESCRIPTION", ''), False)
SPELL_CHECK_REPLY = is_enabled(environ.get("SPELL_CHECK_REPLY", "True"), True)
MAX_LIST_ELM = environ.get("MAX_LIST_ELM", None)
INDEX_REQ_CHANNEL = int(environ.get('INDEX_REQ_CHANNEL', str(LOG_CHANNEL)))
FILE_STORE_CHANNEL = [int(c) for c in environ.get('FILE_STORE_CHANNEL', '').split() if c.lstrip('-').isdigit()]
MELCOW_NEW_USERS = is_enabled(environ.get('MELCOW_NEW_USERS', "True"), True)
PROTECT_CONTENT = is_enabled(environ.get('PROTECT_CONTENT', ''), False)
PUBLIC_FILE_STORE = is_enabled(environ.get('PUBLIC_FILE_STORE', "True"), True)

# ─── FileToLink / Stream Server Settings ─────────────────────────────────────
BIN_CHANNEL = int(environ.get('BIN_CHANNEL', '0'))
STREAM_SERVER_URL = environ.get('STREAM_SERVER_URL', '').rstrip('/')
STREAM_PORT = int(environ.get('PORT', '8080'))
ENABLE_STREAM_BUTTONS = is_enabled(environ.get('ENABLE_STREAM_BUTTONS', 'True'), True)

LOG_STR = (
    f"Advanced Shobana Filter Bot Started\n"
    f"Stream URL : {STREAM_SERVER_URL or 'Not set'}\n"
    f"BIN_CHANNEL: {BIN_CHANNEL or 'Not set'}\n"
)
