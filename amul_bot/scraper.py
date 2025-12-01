"""
Scraper module for Amul Product Alert Bot.
Handles Selenium WebDriver operations and stock checking.
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
from selenium.common.exceptions import TimeoutException

from config import Config, USER_AGENTS, URLS_TO_CHECK
from database import get_pincode_data, expire_subscriptions
from utils import app_logger, user_activity_logger, send_consolidated_alert


# --- Global State ---
product_status_seen: Dict[Tuple[str, str], str] = {}


def setup_driver() -> Optional[webdriver.Chrome]:
    """Initialize and configure Chrome WebDriver."""
    app_logger.info("Setting up new WebDriver instance for the cycle...")
    
    if not Config.CHROME_BINARY_PATH or not Config.CHROMEDRIVER_PATH:
        app_logger.error("Chrome or Chromedriver paths not found in environment variables.")
        return None
    
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument("window-size=1920,1080")
    options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
    options.binary_location = Config.CHROME_BINARY_PATH
    options.add_experimental_option('excludeSwitches', ['enable-logging'])

    service = Service(executable_path=Config.CHROMEDRIVER_PATH)
    
    try:
        driver = webdriver.Chrome(service=service, options=options)
        return driver
    except Exception as e:
        app_logger.error(f"Failed to set up WebDriver: {e}", exc_info=True)
        return None


def check_product_stock(
    driver: webdriver.Chrome, 
    url: str, 
    pincode_to_check: str, 
    current_browser_pincode: Optional[str]
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Check stock status for a product at a specific pincode.
    
    Returns:
        Tuple of (product_title, status, updated_browser_pincode)
        status is either "stock" or "sold"
    """
    app_logger.info(f"Checking URL: {url} for target PINCODE: {pincode_to_check}")
    
    try:
        wait = WebDriverWait(driver, 25)
        driver.get(url)
        
        # Change pincode if needed
        if pincode_to_check != current_browser_pincode:
            current_browser_pincode = _change_pincode(driver, wait, pincode_to_check, current_browser_pincode)
        
        # Extract product title from URL
        product_slug = url.strip().split('/')[-1]
        product_title = product_slug.replace('-', ' ').title()
        
        # Check if sold out
        is_sold_out = _check_sold_out(driver)
        current_status = "sold" if is_sold_out else "stock"
        
        return product_title, current_status, current_browser_pincode
        
    except Exception as e:
        app_logger.error(f"Error checking {url}: {e}", exc_info=True)
        return None, None, current_browser_pincode


def _change_pincode(
    driver: webdriver.Chrome, 
    wait: WebDriverWait, 
    new_pincode: str, 
    current_pincode: Optional[str]
) -> str:
    """Change the pincode on the Amul website."""
    app_logger.info(f"Pincode mismatch. Changing from '{current_pincode}' to '{new_pincode}'.")
    
    try:
        # Try clicking location changer button
        location_changer_selector = (By.CSS_SELECTOR, "div.location_pin_wrap > div[role='button']")
        location_changer = WebDriverWait(driver, 3).until(
            EC.element_to_be_clickable(location_changer_selector)
        )
        driver.execute_script("arguments[0].click();", location_changer)
        wait.until(EC.visibility_of_element_located((By.ID, "locationWidgetModal")))
    except TimeoutException:
        app_logger.info("Initial pincode entry form found.")
    
    # Enter new pincode
    pincode_input = wait.until(EC.visibility_of_element_located((By.ID, "search")))
    old_input_element = pincode_input
    
    pincode_input.clear()
    pincode_input.send_keys(new_pincode)
    
    # Select from suggestions
    suggestion_xpath = f"//p[contains(@class, 'item-name') and text()='{new_pincode}']"
    suggestion = wait.until(EC.element_to_be_clickable((By.XPATH, suggestion_xpath)))
    
    time.sleep(0.5)
    driver.execute_script("arguments[0].click();", suggestion)
    
    # Wait for page to update
    wait.until(EC.staleness_of(old_input_element))
    
    return new_pincode


def _check_sold_out(driver: webdriver.Chrome) -> bool:
    """Check if the product is sold out."""
    try:
        WebDriverWait(driver, 2).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "div.alert.alert-danger"))
        )
        return True
    except TimeoutException:
        return False


async def run_scraper_cycle() -> None:
    """Run one complete scraper cycle for all pincodes."""
    pincode_to_chat_ids = get_pincode_data()
    unique_pincodes = list(pincode_to_chat_ids.keys())
    
    if not unique_pincodes:
        app_logger.info("No active subscribers to check. Skipping cycle.")
        return

    app_logger.info(f"--- Starting check cycle for {len(unique_pincodes)} pincodes ---")
    
    driver = setup_driver()
    if not driver:
        app_logger.error("Could not start driver. Skipping cycle.")
        return
    
    current_browser_pincode: Optional[str] = None
    
    try:
        for pincode in unique_pincodes:
            all_in_stock_products: List[Tuple[str, str]] = []
            all_sold_out_products: List[Tuple[str, str]] = []
            has_status_changed = False
            
            app_logger.info(f"--- Processing all URLs for pincode: {pincode} ---")
            
            for url in URLS_TO_CHECK:
                title, current_status, new_pincode = check_product_stock(
                    driver, url, pincode, current_browser_pincode
                )
                current_browser_pincode = new_pincode
                
                if title and current_status:
                    key = (url, pincode)
                    last_status = product_status_seen.get(key)
                    
                    if current_status != last_status:
                        has_status_changed = True
                        product_status_seen[key] = current_status
                    
                    if current_status == "stock":
                        all_in_stock_products.append((title, url))
                    else:
                        all_sold_out_products.append((title, url))
                
                await asyncio.sleep(random.uniform(3, Config.RETRY_DELAY_SECONDS))
            
            # Send alerts if status changed
            if has_status_changed:
                app_logger.info(f"Detected status changes for {pincode}. Sending consolidated alert.")
                chat_ids = pincode_to_chat_ids.get(pincode, [])
                for chat_id in chat_ids:
                    send_consolidated_alert(chat_id, pincode, all_in_stock_products, all_sold_out_products)
            else:
                app_logger.info(f"No status changes detected for {pincode}. No alert will be sent.")
                
    finally:
        if driver:
            driver.quit()


async def check_subscriptions_expiry() -> None:
    """Check and expire outdated subscriptions."""
    app_logger.info("Running daily subscription expiry check...")
    expired_count = expire_subscriptions()
    user_activity_logger.info(f"{expired_count} subscriptions expired.")


async def scheduler() -> None:
    """Main scheduler loop for running scraper cycles."""
    await check_subscriptions_expiry()
    next_expiry_check = time.time() + Config.EXPIRY_CHECK_INTERVAL_SECONDS
    
    while True:
        await run_scraper_cycle()
        
        # Check for expired subscriptions once per day
        if time.time() > next_expiry_check:
            await check_subscriptions_expiry()
            next_expiry_check = time.time() + Config.EXPIRY_CHECK_INTERVAL_SECONDS
        
        app_logger.info(f"Scraper cycle finished. Waiting for {Config.CHECK_INTERVAL_SECONDS} seconds.")
        await asyncio.sleep(Config.CHECK_INTERVAL_SECONDS)
