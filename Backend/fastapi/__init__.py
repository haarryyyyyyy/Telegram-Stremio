try:
    import sys
    import uvicorn

    from Backend.config import Telegram
    from Backend.fastapi.main import app

    #----- Uvicorn server bound to the FastAPI app
    Port = Telegram.PORT
    loop_engine = "uvloop" if sys.platform != "win32" else "asyncio"
    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=Port,
        loop=loop_engine,
        http="httptools",
        timeout_keep_alive=60,
        timeout_graceful_shutdown=5,
    )
    server = uvicorn.Server(config)
except ImportError:
    server = None
