from logging import FileHandler, StreamHandler, INFO, Formatter, basicConfig, error as log_error, info as log_info
from os import path as ospath, environ
from pathlib import Path
from subprocess import run as srun
from dotenv import load_dotenv
from datetime import datetime
import pytz
import shutil

IST = pytz.timezone("Asia/Kolkata")

class ISTFormatter(Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, IST)
        return dt.strftime(datefmt or "%d-%b-%y %I:%M:%S %p")

log_file = "log.txt"
if ospath.exists(log_file):
    with open(log_file, "w") as f:
        f.truncate(0)

file_handler = FileHandler(log_file)
stream_handler = StreamHandler()
formatter = ISTFormatter("[%(asctime)s] [%(levelname)s] - %(message)s", "%d-%b-%y %I:%M:%S %p")
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)
basicConfig(handlers=[file_handler, stream_handler], level=INFO)

# ── Load config.env as the base (for DATABASE URI, etc.) ─────────────────────
load_dotenv("config.env")


def _fetch_upstream_from_db() -> tuple[str | None, str]:
    try:
        from pymongo import MongoClient
        raw_uris = environ.get("DATABASE", "")          
        uris = [u.strip() for u in raw_uris.replace(",", " ").split() if u.strip()]
        if not uris:
            log_info("update.py: No DATABASE found — skipping DB settings lookup.")
            return None, "master"

        tracking_uri = uris[0]
        client = MongoClient(tracking_uri, serverSelectionTimeoutMS=5000)
        doc = client["dbFyvio"]["settings"].find_one({"_id": "app_settings"})
        client.close()

        if doc:
            repo   = (doc.get("upstream_repo")   or "").strip() or None
            branch = (doc.get("upstream_branch") or "").strip() or "master"
            return repo, branch

    except Exception as exc:
        log_error(f"update.py: DB lookup failed ({exc}) — falling back to config.env.")

    return None, "master"


# ── Priority: DB value  >  config.env value ──────────────────────────────────
db_repo, db_branch = _fetch_upstream_from_db()

raw_repo = db_repo or environ.get("UPSTREAM_REPO", "").strip()
if not raw_repo or "weebzone" in raw_repo.lower():
    UPSTREAM_REPO = "https://github.com/haarryyyyyyy/Telegram-Stremio.git"
else:
    UPSTREAM_REPO = raw_repo

UPSTREAM_BRANCH = db_branch or environ.get("UPSTREAM_BRANCH", "").strip() or "master"

# ── Git update ────────────────────────────────────────────────────────────────
if UPSTREAM_REPO:
    if not Path(".git").exists():
        srun(f"git init -q && git remote add origin {UPSTREAM_REPO} && git fetch origin {UPSTREAM_BRANCH} -q && git checkout -B {UPSTREAM_BRANCH} origin/{UPSTREAM_BRANCH} -q", shell=True)
    else:
        srun(f"git remote set-url origin {UPSTREAM_REPO}", shell=True)

    update_cmd = f"git fetch origin {UPSTREAM_BRANCH} -q && git reset --hard origin/{UPSTREAM_BRANCH} -q"
    update = srun(update_cmd, shell=True)

    log_info(f"UPSTREAM_REPO: {UPSTREAM_REPO} | UPSTREAM_BRANCH: {UPSTREAM_BRANCH}")

    if update.returncode == 0:
        log_info("Successfully updated with latest commits!!")
        commit_check = srun(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
        if commit_check.returncode == 0:
            log_info(f"Latest commit ID: {commit_check.stdout.strip()}")

        # ── Automatically install / sync any new libraries ────────────────────
        log_info("Syncing updated dependencies...")
        uv_bin = shutil.which("uv")
        synced = False
        if uv_bin:
            if ospath.exists("pyproject.toml") and ospath.exists("uv.lock"):
                res = srun([uv_bin, "sync"], capture_output=True, text=True)
                if res.returncode == 0:
                    log_info("Dependencies synced successfully with uv.")
                    synced = True
                else:
                    log_info(f"uv sync note: {res.stderr.strip() if res.stderr else res.stdout.strip()}")
            if not synced and ospath.exists("requirements.txt"):
                res = srun([uv_bin, "pip", "install", "-r", "requirements.txt", "--quiet"], capture_output=True, text=True)
                if res.returncode == 0:
                    log_info("Dependencies installed successfully with uv pip.")
                    synced = True
                else:
                    log_info(f"uv pip note: {res.stderr.strip() if res.stderr else res.stdout.strip()}")

        if not synced and ospath.exists("requirements.txt"):
            import sys
            res = srun([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "--quiet"], capture_output=True, text=True)
            if res.returncode == 0:
                log_info("Dependencies installed successfully with pip.")
            else:
                log_error(f"pip install note: {res.stderr.strip() if res.stderr else res.stdout.strip()}")
    else:
        log_error("❌ Update failed! Retry or ask for support.")
