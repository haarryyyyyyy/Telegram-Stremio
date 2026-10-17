# ⚡ Telegram Stremio V2

A high-performance, from-scratch rebuild of the Telegram-Stremio streaming and catalog engine. Designed for instantaneous playback (<300ms time-to-first-byte), concurrent multi-bot chunk striping, flawless regional title resolution, and zero-URL administrative workflows.

---

## 🌟 Key Features & Improvements over V1

1. **Instant Playback via Multi-Bot Chunk Striping (<300ms TTFB)**:
   - Eliminates the 10–15s initial stream startup delay of V1.
   - Boot-time **Telegram DC Pre-warming** (DCs 1, 2, 4, 5) establishes and imports MTProto authorizations *before* the first playback request arrives.
   - Concurrently downloads striped 1MB chunks across **all available bots simultaneously**, yielding ordered bytes immediately to Stremio.

2. **Full Channel Re-Indexing & Live Ingestion**:
   - Built specifically to re-index entire Telegram media archives from scratch.
   - Flood-safe batching with live progress telemetry (`scanned`, `auto-matched`, `unmatched`).
   - Background `@client.on_message` listener automatically detects and indexes newly posted media in real time.

3. **Regional Alias & Multi-Part Resolution**:
   - Resolves regional language dubs & alternate titles (e.g. Telugu *Sakhi* $\rightarrow$ TMDB ID 19169 *Alaipayuthey*; *Vidudhala* $\rightarrow$ *Viduthalai*).
   - Intelligently keeps multi-part movies (*Viduthalai Part 1*, *Baahubali Chapter 2*) in the movie catalog rather than falsely splitting them into TV series.
   - Accurately parses Anime with absolute episode numbering (*One Piece - 1080* $\rightarrow$ Episode 1080).

4. **1-Click Unmatched Media Queue (Zero Telegram URLs)**:
   - Any skipped or ambiguous media is routed to the Unmatched Queue in the Admin Dashboard.
   - Search TMDB in real time directly from the dashboard and click **"Match & Index"** — no copying or pasting of Telegram message links required.

5. **BingeCat-Style Dynamic Catalogs**:
   - **🌟 15m Spotlight**: Automatically rotates featured titles every 15 minutes using an in-memory rotating window algorithm.
   - **🎬 Personalized Recommendations**: Recommends movies and series based on the user's recent watch history.
   - **Multi-Quality Grouping**: 4K, 1080p, and 720p releases are consolidated under a single movie card.

6. **Clean Single-VM Architecture**:
   - Stripped away multi-node clustering and distributed sync locks for maximum throughput and reliability on a single server or VM.

---

## 🚀 Quickstart

### Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended)
- MongoDB instance (local or Atlas)
- Free TMDB API Key from [themoviedb.org](https://www.themoviedb.org/settings/api)
- Telegram `API_ID` & `API_HASH` from [my.telegram.org](https://my.telegram.org)
- One or more Telegram Bot Tokens from [@BotFather](https://t.me/BotFather)

### 1. Configure Environment
Copy `.env.example` to `.env` and fill in your credentials:
```bash
cp .env.example .env
```

### 2. Install Dependencies
```bash
uv sync
```

### 3. Run Test Suite
```bash
uv run pytest
```
*(All 23 unit and integration tests will run and pass)*

### 4. Start Server
```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 🖥️ Admin Dashboard & 1-Click Matcher
Navigate to `http://localhost:8000/admin` in your browser:
- **Unmatched Queue**: Live TMDB search and 1-click match buttons.
- **Channel Re-Index**: Enter channel IDs or leave blank to scan all configured channels with real-time counters.
- **Stremio Tokens**: Generate tokens with 1-click **"Install to Stremio"** deep links (`stremio://...`).
- **Telemetry**: View total indexed media, active bot counts, and live stream metrics.

---

## 📁 Project Structure

```
telegram-stremio-v2/
├── app/
│   ├── core/
│   │   ├── config.py         # Environment configuration & parser
│   │   └── database.py       # MongoDB storage & unique conflict-proof indexes
│   ├── dashboard/
│   │   ├── html.py           # Responsive Tailwind/Alpine dashboard UI
│   │   └── routes.py         # Admin APIs (match, reindex, search, tokens)
│   ├── indexer/
│   │   ├── parser.py         # Filename/caption parser (prefix strip, anime, multipart)
│   │   ├── resolver.py       # TMDB & regional alias metadata resolver
│   │   ├── pipeline.py       # Ingestion pipeline & unmatched queue router
│   │   └── crawler.py        # Channel re-indexer & real-time message listener
│   ├── streamer/
│   │   ├── multiplexer.py    # Concurrency engine: striped multi-bot chunk streaming
│   │   └── pyro_worker.py    # Pyrofork bot workers with DC pre-warming (1, 2, 4, 5)
│   ├── stremio/
│   │   ├── catalog.py        # 15m spotlight, recommendations, multi-quality deduplication
│   │   └── routes.py         # Stremio manifest, catalog, stream, and HTTP 206 range routes
│   └── main.py               # FastAPI application lifecycle & server entrypoint
├── tests/                    # Comprehensive TDD test suite (23 tests passing)
├── .env.example              # Sample environment template
└── pyproject.toml            # Project dependencies & tool configurations
```
