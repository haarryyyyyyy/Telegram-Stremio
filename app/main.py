import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Database
from app.indexer.resolver import MetadataResolver
from app.indexer.pipeline import IngestionPipeline
from app.indexer.crawler import ChannelCrawler, ReindexManager
from app.stremio.catalog import CatalogManager
from app.stremio.routes import stremio_router
from app.dashboard.routes import dashboard_router
from app.streamer.pyro_worker import BotPoolManager
from app.streamer.multiplexer import StreamMultiplexer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("telegram_stremio_v2")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize MongoDB connection & indexes
    logger.info("Connecting to MongoDB and initializing indexes...")
    db = Database(uri=settings.mongo_uri)
    await db.init_indexes()
    app.state.db = db
    app.state.storage = db

    # Load persistent settings from DB or seed from .env
    saved_settings = await db.get_settings()
    if not saved_settings:
        saved_settings = {
            "bot_tokens": settings.telegram_bot_tokens,
            "tmdb_api_key": settings.tmdb_api_key,
            "tvdb_api_key": settings.tvdb_api_key,
            "channels": settings.telegram_channels,
            "base_url": settings.base_url,
        }
        await db.save_settings(saved_settings)

    active_tmdb_key = saved_settings.get("tmdb_api_key") or settings.tmdb_api_key
    active_tvdb_key = saved_settings.get("tvdb_api_key") or settings.tvdb_api_key
    active_bot_tokens = saved_settings.get("bot_tokens") or settings.telegram_bot_tokens
    active_channels = saved_settings.get("channels") or settings.telegram_channels

    # 2. Initialize TMDB/TVDB Resolver & Ingestion Pipeline
    logger.info("Initializing Metadata Resolver & Ingestion Pipeline...")
    resolver = MetadataResolver(tmdb_api_key=active_tmdb_key, tvdb_api_key=active_tvdb_key)
    pipeline = IngestionPipeline(storage=db, resolver=resolver)
    app.state.resolver = resolver
    app.state.pipeline = pipeline

    # 3. Initialize Catalog Manager
    logger.info("Initializing Stremio Catalog Manager...")
    catalog_mgr = CatalogManager(db=db, spotlight_interval_seconds=900)
    app.state.catalog_manager = catalog_mgr

    # 4. Initialize Multi-Bot Pool & DC Pre-warming
    bot_pool = BotPoolManager(
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        bot_tokens=active_bot_tokens,
    )
    app.state.bot_pool = bot_pool

    if active_bot_tokens and settings.telegram_api_id and settings.telegram_api_hash:
        logger.info(f"Starting BotPoolManager with {len(active_bot_tokens)} bot tokens...")
        try:
            await bot_pool.start_all(prewarm=True)
            workers = bot_pool.get_workers()
            if workers:
                app.state.multiplexer = StreamMultiplexer(bots=workers, prefetch_window=8)
                logger.info(f"Multi-bot StreamMultiplexer active with {len(workers)} workers")

                # 5. Initialize Channel Crawler & Real-time Live Listener
                crawler = ChannelCrawler(client=bot_pool.clients[0], pipeline=pipeline)
                crawler.setup_listener(chat_ids=active_channels or None)
                reindexer = ReindexManager(crawler=crawler)
                app.state.crawler = crawler
                app.state.reindexer = reindexer
                logger.info("Channel Crawler & Real-time message listener initialized")
        except Exception as e:
            logger.error(f"Error starting Telegram bot clients: {e}")
    else:
        logger.warning("No bot tokens active yet - add bots directly in the Dashboard at /admin!")

    yield

    # Graceful shutdown
    if bot_pool:
        logger.info("Stopping all Telegram bot clients...")
        await bot_pool.stop_all()
    logger.info("Shutdown complete.")


def create_app(skip_lifespan_init: bool = False) -> FastAPI:
    app_kwargs = {
        "title": "Telegram Stremio V2",
        "description": "Blazing-fast multi-bot Telegram streaming engine with 15m spotlight and zero-URL matching.",
        "version": "2.0.0",
    }
    if not skip_lifespan_init:
        app_kwargs["lifespan"] = lifespan

    app = FastAPI(**app_kwargs)

    # Enable CORS for Stremio desktop and web apps
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Root redirect to Admin Dashboard
    @app.get("/", include_in_schema=False)
    async def root_redirect():
        return RedirectResponse(url="/admin")

    # Mount routers
    app.include_router(dashboard_router, prefix="/admin")
    app.include_router(dashboard_router, prefix="/dashboard")
    app.include_router(stremio_router)

    return app


app = create_app()
