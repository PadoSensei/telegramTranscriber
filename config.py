import os
from dotenv import load_dotenv

load_dotenv()

# 1. Get the string from environment (default to empty string if not found)
raw_ids = os.getenv("ALLOWED_IDS", "")

# 2. Split by comma, strip whitespace, and convert to integers
# This "list comprehension" handles the conversion safely
ALLOWED_IDS = [int(i.strip()) for i in raw_ids.split(",") if i.strip()]
