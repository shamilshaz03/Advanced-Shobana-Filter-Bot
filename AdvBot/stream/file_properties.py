from datetime import datetime
from typing import Any, Optional
from pyrogram.types import Message


def get_media(message: Message) -> Optional[Any]:
    for attr in ("document", "video", "audio", "photo", "animation",
                 "sticker", "voice", "video_note"):
        media = getattr(message, attr, None)
        if media:
            return media
    return None


def get_hash(message: Message) -> str:
    media = get_media(message)
    uid = getattr(media, "file_unique_id", None) if media else None
    return uid[:6] if uid else ""


def get_fsize(message: Message) -> int:
    media = get_media(message)
    return int(getattr(media, "file_size", 0) or 0)


def get_fname(message: Message) -> str:
    media = get_media(message)
    fname = getattr(media, "file_name", None) if media else None
    if not fname:
        ext_map = {
            "photo": "jpg", "audio": "mp3", "voice": "ogg",
            "video": "mp4", "animation": "mp4",
            "video_note": "mp4", "sticker": "webp",
        }
        ext = "bin"
        if media:
            for attr, extension in ext_map.items():
                if getattr(message, attr, None) is not None:
                    ext = extension
                    break
        fname = f"File_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}"
    return fname
