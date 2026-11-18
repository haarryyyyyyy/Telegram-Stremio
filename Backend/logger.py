import time
from datetime import datetime
from logging import ERROR, INFO, FileHandler, Filter, Formatter, StreamHandler, basicConfig, getLogger

import pytz

IST = pytz.timezone("Asia/Kolkata")


#----- Formatter that renders timestamps in IST
class ISTFormatter(Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, IST)
        return dt.strftime(datefmt or "%d-%b-%y %I:%M:%S %p")


#----- Root logging configuration
formatter = ISTFormatter("[%(asctime)s] [%(levelname)s] - %(message)s", "%d-%b-%y %I:%M:%S %p")
file_handler = FileHandler("log.txt")
stream_handler = StreamHandler()
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)

basicConfig(handlers=[file_handler, stream_handler], level=INFO)

#----- asyncio warns "socket.send() raised exception." on every write to a closed socket, hundreds per second
#----- when a connection dies mid-stream. Keep the first one and drop repeats for a minute.
class ThrottleClosedSocketWarning(Filter):
    def __init__(self, every: float = 60):
        super().__init__()
        self.every, self.last = every, None

    def filter(self, record):
        if record.getMessage() != "socket.send() raised exception.":
            return True
        now = time.monotonic()
        if self.last is None or now - self.last >= self.every:
            self.last = now
            return True
        return False


getLogger("asyncio").addFilter(ThrottleClosedSocketWarning())
getLogger("httpx").setLevel(ERROR)
getLogger("pyrogram").setLevel(ERROR)
getLogger("fastapi").setLevel(ERROR)

LOGGER = getLogger(__name__)
LOGGER.setLevel(INFO)
LOGGER.info("Logger initialized with IST timezone.")
