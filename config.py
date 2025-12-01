"""
Configuration module for Amul Product Alert Bot.
"""

import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

class Config:
    # --- Telegram ---
    BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "")
    ADMIN_GROUP_ID: str = os.environ.get("ADMIN_GROUP_ID", "")
    LOG_GROUP_ID: str = os.environ.get("LOG_GROUP_ID", "")
    
    # --- Database ---
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "")
    
    # --- Chrome/Selenium ---
    CHROME_BINARY_PATH: str = os.environ.get("GOOGLE_CHROME_BIN", "")
    CHROMEDRIVER_PATH: str = os.environ.get("CHROMEDRIVER_PATH", "")
    
    # --- Timing ---
    CHECK_INTERVAL_SECONDS: int = int(os.environ.get("CHECK_INTERVAL_SECONDS", "30")) 
    EXPIRY_CHECK_INTERVAL_SECONDS: int = int(os.environ.get("EXPIRY_CHECK_INTERVAL_SECONDS", "86400"))
    RETRY_DELAY_SECONDS: int = int(os.environ.get("RETRY_DELAY_SECONDS", "5"))
    
    @classmethod
    def validate(cls) -> bool:
        required = ["BOT_TOKEN", "DATABASE_URL", "ADMIN_GROUP_ID"]
        missing = [var for var in required if not getattr(cls, var)]
        if missing:
            print(f"FATAL: Missing vars: {', '.join(missing)}")
            return False
        return True

USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
]

# TARGET URL (Category Page)
CATEGORY_URL: str = "https://shop.amul.com/en/browse/protein"