"""
Scraper module for Amul Product Alert Bot.
Handles Selenium WebDriver operations and stock checking on category pages.
"""

import time
import random
import asyncio
from typing import Optional, Tuple, Dict, List

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException

from config import Config, USER_AGENTS, CATEGORY_URL
from utils import app_logger, user_activity_logger, send_consolidated_alert


# --- Global Scraper Lock ---
# Prevents concurrent scraper cycles which could cause duplicate alerts
_scraper_lock = asyncio.Lock()


# --- Product Name Cleaning ---
def clean_product_name(title: str) -> str:
    """Clean up product names by removing unnecessary prefixes."""
    # Remove "Amul " prefix variations
    for prefix in ["Amul Protein ", "Amul "]:
        if title.startswith(prefix):
            title = title[len(prefix):]
    
    # Remove trailing "At Best Price" or similar
    title = title.replace(" - At Best Price", "").replace(" At Best Price", "")
    
    # Return cleaned title with max 50 chars for brevity
    return title.strip()[:50]


# --- Global State ---
# Product status is now persisted in database (product_status_cache table)
# No in-memory state needed - database provides persistence across bot restarts


def setup_driver() -> Optional[webdriver.Chrome]:
    """Initialize and configure Chrome WebDriver."""
    app_logger.info("Setting up new WebDriver instance...")
    
    if not Config.CHROME_BINARY_PATH or not Config.CHROMEDRIVER_PATH:
        app_logger.error("❌ Chrome paths not configured. Check GOOGLE_CHROME_BIN and CHROMEDRIVER_PATH in .env")
        return None
    
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument("window-size=1920,1080")
    options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
    # Suppress USB/Bluetooth errors in logs
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    # Path setup
    options.binary_location = Config.CHROME_BINARY_PATH
    service = Service(executable_path=Config.CHROMEDRIVER_PATH)
    
    try:
        driver = webdriver.Chrome(service=service, options=options)
        app_logger.info("✅ WebDriver initialized successfully")
        return driver
    except FileNotFoundError as e:
        app_logger.error(f"❌ WebDriver setup FAILED - File not found: {e}")
        app_logger.error(f"   Chrome Binary: {Config.CHROME_BINARY_PATH}")
        app_logger.error(f"   ChromeDriver: {Config.CHROMEDRIVER_PATH}")
        return None
    except Exception as e:
        app_logger.error(f"❌ WebDriver setup FAILED - {type(e).__name__}: {e}")
        import traceback
        app_logger.error(f"   Traceback: {traceback.format_exc()}")
        return None


def _wait_for_page_load(driver: webdriver.Chrome, timeout=10):
    """Wait for document.readyState to be complete."""
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except TimeoutException:
        pass


async def is_during_quiet_hours(chat_id: int) -> bool:
    """Check if current time is within user's quiet hours."""
    from datetime import datetime
    from async_db import get_quiet_hours
    from time_helpers import get_current_time_only, is_between_times
    
    quiet_start, quiet_end = await get_quiet_hours(chat_id)
    if not quiet_start or not quiet_end:
        return False
    
    now = get_current_time_only()
    start = datetime.strptime(quiet_start, "%H:%M:%S").time()
    end = datetime.strptime(quiet_end, "%H:%M:%S").time()
    
    return is_between_times(now, start, end)


def _change_pincode(
    driver: webdriver.Chrome, 
    wait: WebDriverWait, 
    new_pincode: str, 
    current_pincode: Optional[str]
) -> str:
    """
    Change the pincode using Robust JavaScript injection.
    """
    app_logger.info(f"Attempting to change pincode from '{current_pincode}' to '{new_pincode}'...")
    
    try:
        # STEP 1: OPEN MODAL
        # Check if modal is already visible first
        is_modal_open = False
        try:
            wait.until(EC.visibility_of_element_located((By.ID, "locationWidgetModal")))
            is_modal_open = True
            app_logger.info("Modal was already open.")
        except TimeoutException:
            pass

        if not is_modal_open:
            # Try to find the location button container
            try:
                # Broader selector to ensure we catch the wrapper even if inner div structure changes
                location_wrapper = wait.until(EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, ".location_pin_wrap")
                ))
                
                # Scroll to top to ensure no sticky headers block it
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(0.5)
                
                # Force Click
                driver.execute_script("arguments[0].click();", location_wrapper)
                
                # Wait for modal to appear
                wait.until(EC.visibility_of_element_located((By.ID, "locationWidgetModal")))
                time.sleep(1) # Animation buffer
                
            except TimeoutException:
                app_logger.error("STEP 1 FAILED: Could not click Location Button or Modal did not open.")
                # Fallback: Check if we can proceed anyway (maybe site layout changed)
                raise

        # STEP 2: FIND INPUT
        try:
            # Look for input specifically inside the modal
            # Selector targets: ID=locationWidgetModal -> input tag
            input_el = wait.until(EC.visibility_of_element_located(
                (By.CSS_SELECTOR, "#locationWidgetModal input")
            ))
        except TimeoutException:
            app_logger.error("STEP 2 FAILED: Modal opened, but input field not found.")
            raise

        # STEP 3: INJECT VALUE
        app_logger.info("Injecting pincode via JS...")
        try:
            # 1. Clear & Set Value
            driver.execute_script("arguments[0].value = arguments[1];", input_el, new_pincode)
            # 2. Trigger Events (Critical for React/Vue apps)
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", input_el)
            driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", input_el)
            
            time.sleep(2) # Wait for AJAX suggestions
            
        except Exception as e:
            app_logger.error(f"STEP 3 FAILED: JS Injection error: {e}")
            raise

        # STEP 4: SELECT SUGGESTION
        try:
            # Xpath looks for a paragraph containing the pincode inside the item list
            suggestion_xpath = f"//p[contains(@class, 'item-name') and contains(text(), '{new_pincode}')]"
            suggestion = wait.until(EC.element_to_be_clickable((By.XPATH, suggestion_xpath)))
            
            # Force click suggestion
            driver.execute_script("arguments[0].click();", suggestion)
            
        except TimeoutException:
            app_logger.error(f"STEP 4 FAILED: Suggestion for '{new_pincode}' not found. Pincode might be invalid.")
            # Close modal manually to reset state for next attempt
            driver.refresh()
            return current_pincode or "unknown"

        # STEP 5: CLEANUP
        try:
            # Wait for modal to vanish
            wait.until(EC.invisibility_of_element_located((By.ID, "locationWidgetModal")))
            # Wait for reload spinner or grid refresh
            time.sleep(2)
        except TimeoutException:
            pass # It's fine if it doesn't explicitly vanish as long as page reloads
            
        app_logger.info(f"Successfully changed pincode to {new_pincode}")
        return new_pincode

    except Exception as e:
        app_logger.error(f"Error in _change_pincode: {e}")
        # Panic recovery: Refresh page to clear any stuck overlays
        try:
            driver.refresh()
            _wait_for_page_load(driver)
            time.sleep(2)
        except:
            pass
        return current_pincode or "unknown"


def is_driver_healthy(driver: webdriver.Chrome) -> bool:
    """
    Check if WebDriver instance is still responsive.
    
    Returns:
        bool: True if driver is healthy, False if it needs restart
    """
    try:
        # Try a simple command to see if driver responds
        driver.execute_script("return true;")
        return True
    except Exception as e:
        app_logger.warning(f"⚠️ Driver health check failed: {type(e).__name__}")
        return False


def scrape_category_page(
    driver: webdriver.Chrome, 
    pincode: str,
    current_browser_pincode: Optional[str]
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]], str]:
    """
    Scrapes the protein category page.
    """
    wait = WebDriverWait(driver, 30) # 30s Timeout
    
    # 0. Health Check
    if not is_driver_healthy(driver):
        app_logger.error(f"❌ Driver is unhealthy. Forcing restart on next cycle.")
        return [], [], None  # None signals _do_scraper_cycle to restart driver
    
    # 1. Navigate
    if driver.current_url != CATEGORY_URL:
        app_logger.info("Navigating to category URL...")
        driver.get(CATEGORY_URL)
        _wait_for_page_load(driver)
        time.sleep(3) # Initial hydration wait

    # 2. Check/Change Pincode
    if pincode != current_browser_pincode:
        current_browser_pincode = _change_pincode(driver, wait, pincode, current_browser_pincode)
        
        if current_browser_pincode != pincode:
            app_logger.error(f"❌ Pincode mismatch - expected {pincode}, got {current_browser_pincode}. Restarting driver.")
            # Force driver restart by returning None for pincode
            return [], [], None

    # 3. Wait for Grid
    try:
        # Wait for the grid body
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.product-grid-body")))
        # Wait for at least one price element to ensure data is loaded
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".product-grid-price")))
    except TimeoutException:
        app_logger.warning(f"No product grid found for pincode {pincode}. Page might be empty.")
        return [], [], current_browser_pincode

    in_stock = []
    sold_out = []

    # 4. Extract Data
    product_cards = driver.find_elements(By.CSS_SELECTOR, "div.product-grid-body")
    app_logger.info(f"Found {len(product_cards)} products for pincode {pincode}")

    for card in product_cards:
        try:
            # Helper to safely get text/attribute
            name_el = card.find_element(By.CSS_SELECTOR, "div.product-grid-name a")
            title = name_el.text.strip()
            link = name_el.get_attribute("href")
            
            # Check Stock
            # If "Notify Me" exists -> Sold Out
            notify_btn = card.find_elements(By.CSS_SELECTOR, "a[title='Notify Me']")
            
            if notify_btn:
                sold_out.append((title, link))
            else:
                in_stock.append((title, link))

        except StaleElementReferenceException:
            continue
        except Exception:
            continue

    return in_stock, sold_out, current_browser_pincode


async def run_scraper_cycle() -> None:
    """Run one complete scraper cycle for all pincodes."""
    async with _scraper_lock:
        await _do_scraper_cycle()


async def _do_scraper_cycle() -> None:
    """Internal scraper implementation with lock held."""
    from async_db import (
        get_pincode_data,
        get_product_status,
        set_product_status,
        store_pending_alerts,
        has_cached_products_for_pincode,
    )
    
    driver = None
    try:
        pincode_to_chat_ids = await get_pincode_data()
        unique_pincodes = list(pincode_to_chat_ids.keys())
        
        if not unique_pincodes:
            app_logger.info("No active subscribers.")
            return
        
        app_logger.info(f"🔍 Found {len(unique_pincodes)} active pincodes with subscribers: {unique_pincodes}")

        driver = setup_driver()
        if not driver:
            app_logger.error("❌ Could not initialize WebDriver. Skipping this cycle.")
            return
        
        current_browser_pincode: Optional[str] = None
        
        for pincode in unique_pincodes:
            app_logger.info(f"--- Checking {pincode} ---")
            
            current_in_stock, current_sold_out, new_pincode = scrape_category_page(
                driver, pincode, current_browser_pincode
            )
            
            # If new_pincode is None, driver needs restart
            if new_pincode is None:
                app_logger.warning(f"Driver state compromised, restarting for next pincode...")
                if driver:
                    driver.quit()
                driver = setup_driver()
                if not driver:
                    app_logger.error("❌ Failed to restart WebDriver. Skipping cycle.")
                    return
                current_browser_pincode = None
                continue  # Skip this pincode, try next one with fresh driver
            
            current_browser_pincode = new_pincode
            
            # Clean product names and prepare lists
            clean_in_stock = [(clean_product_name(title), url) for title, url in current_in_stock]
            clean_sold_out = [(clean_product_name(title), url) for title, url in current_sold_out]
            
            # Check if this is the FIRST TIME we're scraping this pincode
            is_first_scrape = not await has_cached_products_for_pincode(pincode)
            app_logger.info(f"First-time scrape for {pincode}? {is_first_scrape}")
            
            # Change Detection Logic (using database for state)
            has_change = False
            
            # Check In Stock
            in_stock_count = len(clean_in_stock)
            stock_changes = 0
            for title, url in clean_in_stock:
                cached_status = await get_product_status(url, pincode)
                if cached_status != "stock":
                    # Alert on status change OR on first scrape
                    if is_first_scrape or cached_status != None:
                        has_change = True
                        stock_changes += 1
                        change_type = "first-discovery" if is_first_scrape else "status-change"
                        app_logger.debug(f"  In-stock {change_type}: {title[:30]}... (was: {cached_status}, now: stock)")
                    await set_product_status(url, pincode, "stock")
            
            # Check Sold Out
            sold_count = len(clean_sold_out)
            sold_changes = 0
            for title, url in clean_sold_out:
                cached_status = await get_product_status(url, pincode)
                if cached_status != "sold":
                    # Only alert if status changed (was stock before, now sold)
                    if cached_status == "stock":
                        has_change = True
                        sold_changes += 1
                        app_logger.debug(f"  Sold-out change detected: {title[:30]}... (was: {cached_status}, now: sold)")
                    await set_product_status(url, pincode, "sold")

            # Alert
            if has_change:
                app_logger.info(f"✅ Changes detected for {pincode}: {stock_changes} in-stock, {sold_changes} sold-out | {in_stock_count} total in stock, {sold_count} sold out")
                chat_ids = pincode_to_chat_ids.get(pincode, [])
                app_logger.info(f"   Notifying {len(chat_ids)} users: {chat_ids}")
                for chat_id in chat_ids:
                    # Check if user is in quiet hours
                    if await is_during_quiet_hours(chat_id):
                        # Store in pending_alerts instead of sending immediately
                        await store_pending_alerts(chat_id, pincode, clean_in_stock, clean_sold_out)
                        app_logger.info(f"   └─ User {chat_id} in quiet hours - alert queued")
                    else:
                        send_consolidated_alert(chat_id, pincode, clean_in_stock, clean_sold_out)
                        app_logger.info(f"   └─ User {chat_id} sent immediate alert")
            else:
                app_logger.info(f"📊 No changes for {pincode} (checked {in_stock_count} in-stock, {sold_count} sold-out products)")
            
            await asyncio.sleep(random.uniform(2, 5))
                
    except Exception as e:
        app_logger.error(f"❌ Unexpected error in scraper cycle: {type(e).__name__}: {e}")
        import traceback
        app_logger.error(f"   Traceback: {traceback.format_exc()}")
    finally:
        # Clean up old cache to keep database lean (keep 14 days of history)
        try:
            from async_db import clear_old_product_cache
            deleted_count = await clear_old_product_cache(days=14)
            if deleted_count > 0:
                app_logger.info(f"🧹 Cleaned up {deleted_count} old product cache entries")
        except Exception as e:
            app_logger.warning(f"⚠️ Error cleaning product cache: {e}")
        
        if driver:
            try:
                driver.quit()
            except Exception as e:
                app_logger.warning(f"⚠️ Error closing WebDriver: {e}")


async def check_subscriptions_expiry() -> None:
    """Check and expire subscriptions due date."""
    from async_db import expire_subscriptions
    
    try:
        expired_count = await expire_subscriptions()
        if expired_count > 0:
            user_activity_logger.info(f"✅ {expired_count} subscriptions expired and notified.")
    except Exception as e:
        app_logger.error(f"❌ Error checking subscription expiry: {e}", exc_info=True)


async def validate_db_connection_pool() -> None:
    """Periodically validate database connection pool health."""
    from async_db import validate_connection_pool
    
    while True:
        try:
            # Check pool health every 60 seconds
            is_healthy = await validate_connection_pool()
            if not is_healthy:
                app_logger.warning("⚠️ Connection pool was reinitialized due to health check failure")
            await asyncio.sleep(60)
        except Exception as e:
            app_logger.error(f"❌ Error in connection pool validation: {e}", exc_info=True)
            await asyncio.sleep(60)


async def scheduler() -> None:
    """Main scheduler loop - runs scraper cycles and subscription checks."""
    app_logger.info("🚀 Scheduler started")
    
    # Track all child tasks
    child_tasks = []
    
    try:
        # Validate config values before using them
        expiry_check_interval = Config.EXPIRY_CHECK_INTERVAL_SECONDS
        check_interval = Config.CHECK_INTERVAL_SECONDS
        retry_delay = Config.RETRY_DELAY_SECONDS
        
        if not isinstance(expiry_check_interval, int) or expiry_check_interval <= 0:
            app_logger.warning(f"Invalid EXPIRY_CHECK_INTERVAL_SECONDS: {expiry_check_interval}, using default 86400")
            expiry_check_interval = 86400
        if not isinstance(check_interval, int) or check_interval <= 0:
            app_logger.warning(f"Invalid CHECK_INTERVAL_SECONDS: {check_interval}, using default 300")
            check_interval = 300
        if not isinstance(retry_delay, int) or retry_delay <= 0:
            app_logger.warning(f"Invalid RETRY_DELAY_SECONDS: {retry_delay}, using default 5")
            retry_delay = 5
        
        await check_subscriptions_expiry()
        next_expiry_check = time.time() + expiry_check_interval
        
        # Start background digest tasks and store them
        child_tasks.append(asyncio.create_task(send_hourly_digests()))
        child_tasks.append(asyncio.create_task(send_daily_digests()))
        child_tasks.append(asyncio.create_task(check_expired_pauses()))
        child_tasks.append(asyncio.create_task(validate_db_connection_pool()))
        app_logger.info(f"✅ Started {len(child_tasks)} background tasks")
        
        while True:
            try:
                await run_scraper_cycle()
                
                if time.time() > next_expiry_check:
                    await check_subscriptions_expiry()
                    next_expiry_check = time.time() + expiry_check_interval
                
                app_logger.info(f"⏳ Next check in {check_interval}s...")
                await asyncio.sleep(check_interval)
            except asyncio.CancelledError:
                app_logger.info("⚠️ Scheduler interrupted, cancelling child tasks...")
                for task in child_tasks:
                    if not task.done():
                        task.cancel()
                raise
            except Exception as e:
                app_logger.error(f"❌ Scheduler error: {type(e).__name__}: {e}")
                await asyncio.sleep(retry_delay)
    finally:
        # Ensure all child tasks are cancelled on exit
        for task in child_tasks:
            if not task.done():
                task.cancel()
        try:
            await asyncio.gather(*child_tasks, return_exceptions=True)
        except Exception:
            pass
        app_logger.info("🛑 Scheduler stopped")


async def send_hourly_digests() -> None:
    """Send hourly digest to users who opted in."""
    from async_db import (
        get_users_by_alert_frequency,
        get_pending_alerts,
        mark_alerts_sent,
    )
    from utils import send_telegram_message
    
    while True:
        try:
            app_logger.info("📧 Starting hourly digest task...")
            hourly_users = await get_users_by_alert_frequency("hourly")
            
            for chat_id in hourly_users:
                try:
                    alerts = await get_pending_alerts(chat_id)
                    if alerts:
                        # Build message from pending alerts
                        message_parts = ["📊 *Hourly Digest* 📊"]
                        for product_title, product_url, status in alerts:
                            emoji = "✅" if status == "stock" else "❌"
                            message_parts.append(f"{emoji} [{product_title}]({product_url})")
                        
                        message = "\n".join(message_parts)
                        
                        # Retry logic with exponential backoff
                        sent = False
                        for attempt in range(3):
                            try:
                                if send_telegram_message(chat_id, message):
                                    await mark_alerts_sent(chat_id)
                                    app_logger.info(f"📧 Hourly digest sent to {chat_id}")
                                    sent = True
                                    break
                                else:
                                    # API returned False but no exception
                                    await asyncio.sleep(2 ** attempt)
                            except Exception as retry_error:
                                if attempt < 2:  # Not last attempt
                                    wait_time = 2 ** attempt
                                    app_logger.warning(f"Retry {attempt+1}/3 for user {chat_id} after {wait_time}s: {retry_error}")
                                    await asyncio.sleep(wait_time)
                                else:
                                    raise
                        
                        if not sent:
                            app_logger.error(f"Failed to send hourly digest to {chat_id} after 3 attempts")
                except Exception as e:
                    app_logger.error(f"Error sending hourly digest to {chat_id}: {e}")
            
            # Wait 1 hour before next digest
            await asyncio.sleep(3600)
        except Exception as e:
            app_logger.error(f"Error in hourly digest task: {e}")
            await asyncio.sleep(600)  # Retry after 10 min on error


async def send_daily_digests() -> None:
    """Send daily digest at 8 AM to users who opted in."""
    from datetime import datetime
    from async_db import (
        get_users_by_alert_frequency,
        get_pending_alerts,
        mark_alerts_sent,
    )
    from utils import send_telegram_message
    from time_helpers import get_current_time
    
    while True:
        try:
            now = get_current_time()
            # Check if we're between 8:00 and 8:05
            if now.hour == 8 and now.minute < 5:
                app_logger.info("📄 Starting daily digest task at 8 AM...")
                daily_users = await get_users_by_alert_frequency("daily")
                
                for chat_id in daily_users:
                    try:
                        alerts = await get_pending_alerts(chat_id)
                        if alerts:
                            # Build message from pending alerts
                            message_parts = ["📋 *Daily Digest* 📋"]
                            for product_title, product_url, status in alerts:
                                emoji = "✅" if status == "stock" else "❌"
                                message_parts.append(f"{emoji} [{product_title}]({product_url})")
                            
                            message = "\n".join(message_parts)
                            
                            # Retry logic with exponential backoff
                            sent = False
                            for attempt in range(3):
                                try:
                                    if send_telegram_message(chat_id, message):
                                        await mark_alerts_sent(chat_id)
                                        app_logger.info(f"📄 Daily digest sent to {chat_id}")
                                        sent = True
                                        break
                                    else:
                                        # API returned False but no exception
                                        await asyncio.sleep(2 ** attempt)
                                except Exception as retry_error:
                                    if attempt < 2:  # Not last attempt
                                        wait_time = 2 ** attempt
                                        app_logger.warning(f"Retry {attempt+1}/3 for user {chat_id} after {wait_time}s: {retry_error}")
                                        await asyncio.sleep(wait_time)
                                    else:
                                        raise
                            
                            if not sent:
                                app_logger.error(f"Failed to send daily digest to {chat_id} after 3 attempts")
                    except Exception as e:
                        app_logger.error(f"Error sending daily digest to {chat_id}: {e}")
                
                # Wait until after 8:05 to avoid duplicate sends
                await asyncio.sleep(600)
            else:
                # Check again in 1 minute
                await asyncio.sleep(60)
        except Exception as e:
            app_logger.error(f"Error in daily digest task: {e}")
            await asyncio.sleep(600)


async def check_expired_pauses() -> None:
    """Check and auto-resume users whose pause period has expired."""
    from datetime import date
    from async_db import (
        get_paused_users,
        get_pause_until_date,
        resume_user_subscription,
    )
    from utils import send_telegram_message
    
    while True:
        try:
            paused_users = await get_paused_users()
            today = date.today()
            
            for chat_id in paused_users:
                try:
                    pause_until = await get_pause_until_date(chat_id)
                    if pause_until and today >= pause_until:
                        await resume_user_subscription(chat_id)
                        app_logger.info(f"✅ Auto-resumed user {chat_id}")
                        
                        try:
                            send_telegram_message(
                                chat_id,
                                "✅ *Welcome Back!*\n\nYour subscription is active again. You'll start receiving alerts."
                            )
                        except:
                            pass
                except Exception as e:
                    app_logger.error(f"Error checking pause expiry for {chat_id}: {e}")
            
            # Check once per day at midnight
            await asyncio.sleep(86400)
        except Exception as e:
            app_logger.error(f"Error in pause expiry check: {e}")
            await asyncio.sleep(600)
