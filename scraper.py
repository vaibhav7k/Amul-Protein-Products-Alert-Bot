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
from database import get_pincode_data, expire_subscriptions
from utils import app_logger, user_activity_logger, send_consolidated_alert


# --- Global State ---
# Key: (product_url, pincode), Value: 'stock' or 'sold'
product_status_seen: Dict[Tuple[str, str], str] = {}


def setup_driver() -> Optional[webdriver.Chrome]:
    """Initialize and configure Chrome WebDriver."""
    app_logger.info("Setting up new WebDriver instance...")
    
    if not Config.CHROME_BINARY_PATH or not Config.CHROMEDRIVER_PATH:
        app_logger.error("Chrome paths not found in config.")
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
        return driver
    except Exception as e:
        app_logger.error(f"Failed to set up WebDriver: {e}")
        return None


def _wait_for_page_load(driver: webdriver.Chrome, timeout=10):
    """Wait for document.readyState to be complete."""
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except TimeoutException:
        pass


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


def scrape_category_page(
    driver: webdriver.Chrome, 
    pincode: str,
    current_browser_pincode: Optional[str]
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]], str]:
    """
    Scrapes the protein category page.
    """
    wait = WebDriverWait(driver, 30) # 30s Timeout
    
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
            app_logger.warning(f"Skipping scrape: Pincode mismatch. Wanted {pincode}, got {current_browser_pincode}")
            return [], [], current_browser_pincode

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
    pincode_to_chat_ids = get_pincode_data()
    unique_pincodes = list(pincode_to_chat_ids.keys())
    
    if not unique_pincodes:
        app_logger.info("No active subscribers.")
        return

    driver = setup_driver()
    if not driver:
        return
    
    current_browser_pincode: Optional[str] = None
    
    try:
        for pincode in unique_pincodes:
            app_logger.info(f"--- Checking {pincode} ---")
            
            current_in_stock, current_sold_out, new_pincode = scrape_category_page(
                driver, pincode, current_browser_pincode
            )
            current_browser_pincode = new_pincode
            
            # Change Detection Logic
            has_change = False
            
            # Check In Stock
            for title, url in current_in_stock:
                key = (url, pincode)
                if product_status_seen.get(key) != "stock":
                    has_change = True
                    product_status_seen[key] = "stock"
            
            # Check Sold Out
            for title, url in current_sold_out:
                key = (url, pincode)
                if product_status_seen.get(key) != "sold":
                    product_status_seen[key] = "sold"

            # Alert
            if has_change:
                app_logger.info(f"Alerting {pincode}...")
                chat_ids = pincode_to_chat_ids.get(pincode, [])
                for chat_id in chat_ids:
                    send_consolidated_alert(chat_id, pincode, current_in_stock, current_sold_out)
            else:
                app_logger.info(f"No changes for {pincode}.")
            
            await asyncio.sleep(random.uniform(2, 5))
                
    finally:
        if driver:
            driver.quit()


async def check_subscriptions_expiry() -> None:
    expired_count = expire_subscriptions()
    if expired_count > 0:
        user_activity_logger.info(f"{expired_count} subscriptions expired.")


async def scheduler() -> None:
    await check_subscriptions_expiry()
    next_expiry_check = time.time() + Config.EXPIRY_CHECK_INTERVAL_SECONDS
    
    while True:
        await run_scraper_cycle()
        
        if time.time() > next_expiry_check:
            await check_subscriptions_expiry()
            next_expiry_check = time.time() + Config.EXPIRY_CHECK_INTERVAL_SECONDS
        
        app_logger.info(f"Waiting {Config.CHECK_INTERVAL_SECONDS}s...")
        await asyncio.sleep(Config.CHECK_INTERVAL_SECONDS)