import re
import os
import logging
from urllib.parse import quote

from aiohttp import web

from stream.exceptions import FileNotFound

routes = web.RouteTableDef()
logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024
RANGE_REGEX = re.compile(r"^bytes=(?P<start>\d*)-(?P<end>\d*)$")

# Globals set by bot.py after bot start
_bot_client = None
_bin_channel = None
_streamer = None


def set_stream_globals(client, bin_channel):
    global _bot_client, _bin_channel, _streamer
    from stream.custom_dl import ByteStreamer
    _bot_client = client
    _bin_channel = int(bin_channel)
    _streamer = ByteStreamer(client, bin_channel)
    logger.info(f"ByteStreamer initialised for channel {bin_channel}")


def parse_range(range_header: str, file_size: int):
    if not range_header:
        return 0, file_size - 1
    m = RANGE_REGEX.fullmatch(range_header)
    if not m:
        raise web.HTTPBadRequest(text="Invalid Range header")
    start_s, end_s = m.group("start"), m.group("end")
    if start_s:
        start = int(start_s)
        end = int(end_s) if end_s else file_size - 1
    else:
        suffix = int(end_s)
        if suffix <= 0:
            raise web.HTTPRequestRangeNotSatisfiable(
                headers={"Content-Range": f"bytes */{file_size}"})
        start = max(file_size - suffix, 0)
        end = file_size - 1
    if not (0 <= start <= end < file_size):
        raise web.HTTPRequestRangeNotSatisfiable(
            headers={"Content-Range": f"bytes */{file_size}"})
    return start, end


async def _serve(request, message_id: int, disposition="attachment"):
    if not _streamer:
        raise web.HTTPServiceUnavailable(text="Streamer not ready")

    info = await _streamer.get_file_info(message_id)
    if "error" in info:
        raise web.HTTPNotFound(text="File not found")

    file_size = int(info.get("file_size") or 0)
    if file_size <= 0:
        raise web.HTTPNotFound(text="Empty file")

    range_hdr = request.headers.get("Range", "")
    start, end = parse_range(range_hdr, file_size)
    content_length = end - start + 1
    mime = info.get("mime_type") or "application/octet-stream"
    fname = info.get("file_name") or f"file_{message_id}"
    disp = request.query.get("disposition", disposition)

    headers = {
        "Content-Type": mime,
        "Content-Length": str(content_length),
        "Content-Disposition": f"{disp}; filename*=UTF-8''{quote(fname, safe='')}",
        "Accept-Ranges": "bytes",
        "Cache-Control": "public, max-age=86400",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Expose-Headers": "Content-Length,Content-Range,Content-Disposition",
    }
    if range_hdr:
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

    if request.method == "HEAD":
        return web.Response(status=206 if range_hdr else 200, headers=headers)

    async def body():
        skipped = start % CHUNK_SIZE if start > 0 else 0
        sent = 0
        try:
            async for chunk in _streamer.stream_file(message_id, offset=start, limit=content_length):
                if skipped > 0:
                    if len(chunk) <= skipped:
                        skipped -= len(chunk)
                        continue
                    chunk = chunk[skipped:]
                    skipped = 0
                remaining = content_length - sent
                if len(chunk) > remaining:
                    chunk = chunk[:remaining]
                if chunk:
                    yield chunk
                    sent += len(chunk)
                if sent >= content_length:
                    break
        except Exception as e:
            logger.debug(f"Stream body error: {e}")

    return web.Response(
        status=206 if range_hdr else 200,
        body=body(),
        headers=headers,
    )


# ── Health / root ─────────────────────────────────────────────────────────────
@routes.get("/", allow_head=True)
async def health(request):
    """Health check endpoint - must return 200 for Koyeb."""
    return web.Response(
        text="OK - Advanced Shobana Filter Bot is running",
        content_type="text/plain",
        headers={"Access-Control-Allow-Origin": "*"},
    )


@routes.get("/health", allow_head=True)
async def health2(request):
    return web.json_response(
        {"status": "ok", "streamer": "active" if _streamer else "inactive"},
        headers={"Access-Control-Allow-Origin": "*"},
    )


# ── CORS preflight ────────────────────────────────────────────────────────────
@routes.options(r"/{path:.+}")
async def preflight(request):
    return web.Response(headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Access-Control-Allow-Headers": "Range, Content-Type",
        "Access-Control-Max-Age": "86400",
    })


# ── Stream player ─────────────────────────────────────────────────────────────
@routes.get(r"/watch/{msg_id:\d+}", allow_head=True)
@routes.get(r"/watch/{msg_id:\d+}/{name:.+}", allow_head=True)
async def watch(request):
    msg_id = int(request.match_info["msg_id"])
    if not _streamer:
        raise web.HTTPServiceUnavailable(text="Streamer not ready")

    info = await _streamer.get_file_info(msg_id)
    if "error" in info:
        raise web.HTTPNotFound(text="File not found")

    fname = info.get("file_name") or f"file_{msg_id}"
    from info import STREAM_SERVER_URL
    src = f"{STREAM_SERVER_URL}/dl/{msg_id}/{quote(fname.replace('/', '_'), safe='')}"

    tmpl_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "template", "req.html")
    try:
        with open(tmpl_path, encoding="utf-8") as f:
            raw = f.read()
        try:
            from jinja2 import Environment
            html = Environment(autoescape=True).from_string(raw).render(
                heading=f"▶ {fname}",
                file_name=fname,
                src=f"{src}?disposition=inline",
            )
        except ImportError:
            html = raw.replace("{{ heading }}", f"▶ {fname}") \
                      .replace("{{ file_name }}", fname) \
                      .replace("{{ src }}", f"{src}?disposition=inline")
    except FileNotFoundError:
        html = f"<html><body><video controls src='{src}?disposition=inline' style='width:100%;'></video></body></html>"

    return web.Response(text=html, content_type="text/html",
                        headers={"Access-Control-Allow-Origin": "*"})


# ── Download ──────────────────────────────────────────────────────────────────
@routes.get(r"/dl/{msg_id:\d+}", allow_head=True)
@routes.get(r"/dl/{msg_id:\d+}/{name:.+}", allow_head=True)
async def download(request):
    try:
        msg_id = int(request.match_info["msg_id"])
        return await _serve(request, msg_id, "attachment")
    except web.HTTPException:
        raise
    except Exception as e:
        raise web.HTTPInternalServerError(text=str(e))
