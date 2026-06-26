#  Advanced Shobana Filter Bot + FileToLink Streaming
import logging
import logging.config
import os
import sys
import asyncio

# ── logging setup ─────────────────────────────────────────────────────────────
logging.config.fileConfig('logging.conf')
logging.getLogger().setLevel(logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)

import tgcrypto
from pyrogram import Client, __version__
from pyrogram.types import BotCommand
from pyrogram.raw.all import layer
from pyrogram import utils as pyroutils

pyroutils.MIN_CHAT_ID = -999999999999
pyroutils.MIN_CHANNEL_ID = -100999999999999

from database.ia_filterdb import Media
from database.users_chats_db import db
from info import (
    SESSION, API_ID, API_HASH, BOT_TOKEN, LOG_STR, LOG_CHANNEL,
    KEEP_ALIVE_URL, DEFAULT_AUTH_CHANNELS,
    BIN_CHANNEL, STREAM_SERVER_URL, STREAM_PORT, ENABLE_STREAM_BUTTONS,
)
from utils import temp
from Script import script
from os import environ
import aiohttp
from aiohttp import web as webserver

from stream import web_server
from stream.stream_routes import set_stream_globals

BOT_COMMANDS = [
    BotCommand("start", "Start the bot"),
    BotCommand("movies", "Latest added movies"),
    BotCommand("series", "Latest added series"),
    BotCommand("stats", "Database statistics"),
    BotCommand("ping", "Check bot response"),
    BotCommand("filter", "Add a manual filter"),
    BotCommand("filters", "List manual filters"),
    BotCommand("del", "Delete a filter"),
    BotCommand("delall", "Delete all filters"),
]


async def preload_auth_channels():
    try:
        if not await db.get_auth_channels():
            await db.set_auth_channels(DEFAULT_AUTH_CHANNELS)
    except Exception as e:
        logging.warning(f"preload_auth_channels: {e}")


async def keep_alive():
    if not KEEP_ALIVE_URL:
        return
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await session.get(KEEP_ALIVE_URL, timeout=aiohttp.ClientTimeout(total=10))
            except Exception:
                pass
            await asyncio.sleep(111)


class Bot(Client):

    def __init__(self):
        super().__init__(
            name=SESSION,
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=50,
            plugins={"root": "plugins"},
            sleep_threshold=5,
        )

    async def start(self):
        # Load banned lists before super().start() loads handlers
        try:
            b_users, b_chats = await db.get_banned()
            temp.BANNED_USERS = b_users
            temp.BANNED_CHATS = b_chats
        except Exception as e:
            logging.warning(f"Failed to load banned lists: {e}")

        await super().start()

        try:
            await asyncio.gather(Media.ensure_indexes(), db.ensure_indexes())
        except Exception as e:
            logging.warning(f"ensure_indexes: {e}")

        me = await self.get_me()
        temp.ME = me.id
        temp.U_NAME = me.username
        temp.B_NAME = me.first_name
        self.username = '@' + (me.username or '')

        await preload_auth_channels()

        logging.info(
            f"Bot @{me.username} started | "
            f"Pyrogram {__version__} Layer {layer}"
        )
        logging.info(LOG_STR)

        try:
            await self.set_bot_commands(BOT_COMMANDS)
        except Exception as e:
            logging.warning(f"set_bot_commands failed: {e}")

        if LOG_CHANNEL:
            try:
                await self.send_message(LOG_CHANNEL, script.RESTART_TXT)
            except Exception:
                pass

        # Initialise stream globals
        if BIN_CHANNEL and STREAM_SERVER_URL and ENABLE_STREAM_BUTTONS:
            set_stream_globals(self, BIN_CHANNEL)
            logging.info(f"Stream server ready: {STREAM_SERVER_URL}")

        asyncio.create_task(keep_alive(), name="keep_alive")

    async def stop(self, *args):
        await super().stop()
        logging.info("Bot stopped.")


# ── entry point ───────────────────────────────────────────────────────────────
async def main():
    port = int(environ.get("PORT", "8080"))

    # Start the aiohttp web server FIRST so Koyeb health-check passes
    runner = webserver.AppRunner(await web_server())
    await runner.setup()
    site = webserver.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Web server listening on 0.0.0.0:{port}")

    bot = Bot()
    await bot.start()

    try:
        from pyrogram import idle
        await idle()
    finally:
        await bot.stop()
        await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
