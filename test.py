import os
from cs50 import SQL
from dotenv import load_dotenv

load_dotenv()

raw_url = os.environ.get("DATABASE_URL")
if raw_url and raw_url.startswith("postgres://"):
    raw_url = raw_url.replace("postgres://", "postgresql://", 1)

db = SQL(raw_url)

print(db.execute("SELECT * FROM subscriptions"))