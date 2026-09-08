import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
DISCORD_GUILD_ID = int(os.getenv("DISCORD_GUILD_ID") or 0)
DB_PATH = BASE_DIR / "data" / "database" / "wiki.db"
RAW_DATA_DIR = BASE_DIR / "data" / "raw"
SCHEMA_PATH = BASE_DIR / "data" / "schema.sql"
