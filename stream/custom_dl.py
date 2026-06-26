import asyncio
import logging
from typing import Any, AsyncGenerator, Dict

from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.types import Message

from stream.exceptions import FileNotFound
from stream.file_properties import get_fname, get_fsize, get_media

logger = logging.getLogger(__name__)


class ByteStreamer:
    def __init__(self, client: Client, bin_channel: int) -> None:
        self.client = client
        self.chat_id = int(bin_channel)

    async def get_message(self, message_id: int) -> Message:
        for attempt in range(3):
            try:
                msg = await self.client.get_messages(self.chat_id, message_id)
                if msg and msg.media:
                    return msg
                raise FileNotFound(f"Message {message_id} has no media")
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except FileNotFound:
                raise
            except Exception as e:
                if attempt == 2:
                    raise FileNotFound(f"Cannot get message {message_id}: {e}") from e
                await asyncio.sleep(1)

    async def get_file_info(self, message_id: int) -> Dict[str, Any]:
        try:
            msg = await self.get_message(message_id)
        except Exception as e:
            return {"message_id": message_id, "error": str(e)}

        media = get_media(msg)
        if not media:
            return {"message_id": message_id, "error": "no media"}

        media_type = type(media).__name__.lower()
        fname = get_fname(msg)
        mime = getattr(media, "mime_type", None)
        if not mime:
            mime_map = {
                "photo": "image/jpeg", "voice": "audio/ogg",
                "video": "video/mp4", "audio": "audio/mpeg",
                "animation": "video/mp4", "videonote": "video/mp4",
                "sticker": "image/webp",
            }
            mime = mime_map.get(media_type, "application/octet-stream")

        return {
            "message_id": message_id,
            "file_size": get_fsize(msg),
            "file_name": fname,
            "mime_type": mime,
            "unique_id": getattr(media, "file_unique_id", None),
            "media_type": media_type,
        }

    async def stream_file(
        self, message_id: int, offset: int = 0, limit: int = 0
    ) -> AsyncGenerator[bytes, None]:
        try:
            msg = await self.get_message(message_id)
        except Exception as e:
            raise FileNotFound(str(e))

        chunk_offset = offset // (1024 * 1024)
        chunk_limit = 0
        if limit > 0:
            chunk_limit = ((limit + (1024 * 1024) - 1) // (1024 * 1024)) + 1

        while True:
            try:
                async for chunk in self.client.stream_media(msg, offset=chunk_offset, limit=chunk_limit):
                    yield chunk
                return
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception as e:
                raise FileNotFound(f"Stream error: {e}") from e
