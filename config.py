import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
WEBAPP_URL = os.getenv("WEBAPP_URL", "http://localhost:8080")

DB_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_RECORD_LIMIT = 10000

NOTIFICATION_HOUR = 6
GIFT_REMINDER_DAYS_BEFORE = 7
