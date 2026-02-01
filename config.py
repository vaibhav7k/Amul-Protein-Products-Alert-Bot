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
    
    # --- Timezone ---
    BOT_TIMEZONE: str = os.environ.get("BOT_TIMEZONE", "Asia/Kolkata")
    
    # --- Timing ---
    CHECK_INTERVAL_SECONDS: int = int(os.environ.get("CHECK_INTERVAL_SECONDS", "30"))  # 5 minutes
    EXPIRY_CHECK_INTERVAL_SECONDS: int = int(os.environ.get("EXPIRY_CHECK_INTERVAL_SECONDS", "86400"))
    RETRY_DELAY_SECONDS: int = int(os.environ.get("RETRY_DELAY_SECONDS", "5"))
    
    @classmethod
    def validate(cls) -> bool:
        """Validate all required configuration on startup."""
        required = ["BOT_TOKEN", "DATABASE_URL", "ADMIN_GROUP_ID"]
        missing = [var for var in required if not getattr(cls, var)]
        if missing:
            print(f"FATAL: Missing required environment variables: {', '.join(missing)}")
            return False
        
    # ✅ Add this validation
        try:
            admin_id = int(cls.ADMIN_GROUP_ID)
            if admin_id > 0:
                print(f"FATAL: ADMIN_GROUP_ID must be negative (group ID). Got: {admin_id}")
                return False
        except ValueError:
            print(f"FATAL: ADMIN_GROUP_ID must be a valid integer. Got: {cls.ADMIN_GROUP_ID}")
            return False

        # Validate Chrome paths exist
        from pathlib import Path
        if cls.CHROME_BINARY_PATH:
            chrome_path = Path(cls.CHROME_BINARY_PATH)
            if not chrome_path.exists():
                print(f"FATAL: Chrome binary not found at: {cls.CHROME_BINARY_PATH}")
                print(f"       Please verify GOOGLE_CHROME_BIN in .env")
                return False
        
        if cls.CHROMEDRIVER_PATH:
            driver_path = Path(cls.CHROMEDRIVER_PATH)
            if not driver_path.exists():
                print(f"FATAL: ChromeDriver not found at: {cls.CHROMEDRIVER_PATH}")
                print(f"       Please verify CHROMEDRIVER_PATH in .env")
                return False
        
        return True

USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
]

# TARGET URL (Category Page)
CATEGORY_URL: str = "https://shop.amul.com/en/browse/protein"