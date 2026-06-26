# 🎬 Advanced Shobana Filter Bot

Fully integrated auto-filter bot combining **ShobanaFilterBot** (Pyrogram) with
**FileToLink** HTTP streaming — packaged as a single deployable service.

---

## ✨ What's New vs Stock ShobanaFilterBot

| Feature | Stock | This Bot |
|---|---|---|
| Language filter | ❌ | ✅ |
| Quality filter (1080p etc.) | ❌ | ✅ |
| Season filter | ❌ | ✅ |
| Episode filter | ❌ | ✅ |
| Pagination (10/page, ALL results) | Partial | ✅ |
| Filter state persists across pages | ❌ | ✅ |
| 🌐 Stream button after send | ❌ | ✅ |
| ⬇️ Download button after send | ❌ | ✅ |
| Built-in HTTP stream server | ❌ | ✅ |
| Health-check endpoint at `/` | ❌ | ✅ (returns 200) |

---

## 🚀 Koyeb Deployment (Recommended)

### 1 — Push repo to GitHub

### 2 — Create Koyeb app
- **Source**: GitHub repo, branch `main`
- **Builder**: Dockerfile  
- **Service type**: Web service
- **Port**: `8080`
- **Health check path**: `/` (returns 200 OK)

### 3 — Set environment variables in Koyeb dashboard

#### Required
| Variable | Example |
|---|---|
| `BOT_TOKEN` | `123456:ABC-xyz` |
| `API_ID` | `12345678` |
| `API_HASH` | `abc123...` |
| `DATABASE_URI` | `mongodb+srv://...` |
| `DATABASE_NAME` | `ShobanaBot` |
| `CHANNELS` | `-1001234567890` |
| `ADMINS` | `123456789` |
| `LOG_CHANNEL` | `-1009876543210` |

#### For Stream/Download buttons
| Variable | Example |
|---|---|
| `BIN_CHANNEL` | `-1001122334455` |
| `STREAM_SERVER_URL` | `https://myapp.koyeb.app` |

> **BIN_CHANNEL** is a private Telegram channel where files are temporarily forwarded
> for HTTP streaming. Add the bot as admin there.  
> **STREAM_SERVER_URL** is your Koyeb app's public URL — set it after first deploy.

#### Optional
| Variable | Default | Description |
|---|---|---|
| `ENABLE_STREAM_BUTTONS` | `True` | Show stream/download buttons |
| `FILE_AUTO_DELETE_SECONDS` | `60` | Auto-delete sent files after N seconds |
| `PROTECT_CONTENT` | `False` | Protect files from forwarding |
| `SPELL_CHECK_REPLY` | `True` | Reply if no results found |
| `P_TTI_SHOW_OFF` | `False` | Send files to user's PM |
| `KEEP_ALIVE_URL` | *(empty)* | URL to ping every 111s |
| `AUTH_CHANNEL` | *(empty)* | Force-subscribe channel IDs |
| `PICS` | *(url)* | Space-separated photo URLs for /start |
| `DATABASE_URI2`–`5` | *(empty)* | Additional MongoDB shards |

---

## 🐳 Local Docker

```bash
docker build -t advshobana .
docker run -e BOT_TOKEN=... -e API_ID=... -e API_HASH=... \
           -e DATABASE_URI=... -e CHANNELS=... \
           -e BIN_CHANNEL=... -e STREAM_SERVER_URL=http://localhost:8080 \
           -p 8080:8080 advshobana
```

---

## 🔍 How the search/filter flow works

```
User types "Avengers" in group
  → Bot fetches ALL matching files (up to 200) from DB
  → Shows paginated results (10 per page) with filter buttons:
       [🌍 Language]  [🎬 Quality]
       [📺 Season]    [🎞 Episode]
  → User taps a filter → results narrow, page resets to 1
  → User taps a file  → bot sends the file
  → Bot copies file to BIN_CHANNEL → generates stream URLs
  → Sends [🌐 Stream] [⬇️ Download] buttons as reply
```

---

## 🌐 Stream URL format

```
Player:   https://your-app.koyeb.app/watch/{msg_id}/{filename}
Download: https://your-app.koyeb.app/dl/{msg_id}/{filename}
Health:   https://your-app.koyeb.app/              ← returns 200 OK
```

---

## ⚙️ File structure

```
AdvancedShobanaBot/
├── bot.py                  ← Entry point (starts web server first, then bot)
├── info.py                 ← All configuration / env vars
├── utils.py                ← temp class + humanbytes
├── Script.py               ← Message templates
├── Procfile                ← web: python3 bot.py
├── Dockerfile
├── requirements.txt
├── database/
│   ├── ia_filterdb.py      ← File search DB (unchanged)
│   ├── users_chats_db.py   ← Users/groups DB (unchanged)
│   ├── filters_mdb.py      ← Manual filters DB (unchanged)
│   ├── connections_mdb.py  ← PM connections (unchanged)
│   └── sql_store.py        ← PostgreSQL fallback (unchanged)
├── plugins/
│   ├── search.py           ← ★ Auto-filter + all callbacks + stream buttons
│   ├── start.py            ← /start, /ping, /stats
│   ├── filters.py          ← /filter, /filters, /del, /delall
│   ├── admin.py            ← Admin commands
│   ├── broadcast.py        ← Broadcast
│   ├── banned.py           ← Ban/unban
│   └── Extra/              ← Extra utility plugins
├── stream/
│   ├── __init__.py         ← aiohttp web_server() factory
│   ├── stream_routes.py    ← HTTP routes (/  /health  /watch/  /dl/)
│   ├── custom_dl.py        ← ByteStreamer (Pyrogram stream_media)
│   ├── file_properties.py  ← File metadata helpers
│   └── exceptions.py       ← FileNotFound, InvalidHash
└── template/
    ├── req.html            ← Vidstack cinema player
    └── dl.html             ← Download page
```

---

## Credits

- [ShobanaFilterBot](https://github.com/mn-bots/ShobanaFilterBot) — auto-filter base  
- [FileToLink](https://github.com/fyaz05/FileToLink) — HTTP streaming server
