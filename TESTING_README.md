# Amul Product Alert Bot - Testing Guide

Complete end-to-end testing guide for the Amul Product Alert Bot.

---

## Table of Contents

1. [Prerequisites & Setup](#prerequisites--setup)
2. [Environment Configuration](#environment-configuration)
3. [Database Setup](#database-setup)
4. [Running the Bot](#running-the-bot)
5. [Testing User Commands](#testing-user-commands)
6. [Testing Admin Commands](#testing-admin-commands)
7. [Testing Background Tasks](#testing-background-tasks)
8. [Testing Scraper](#testing-scraper)
9. [Testing Database Operations](#testing-database-operations)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites & Setup

### Required Installations

```bash
# Python 3.8+
python --version

# PostgreSQL database
# - Windows: Download from https://www.postgresql.org/download/windows/
# - macOS: brew install postgresql
# - Linux: sudo apt-get install postgresql

# ChromeDriver for Selenium
# Download from: https://chromedriver.chromium.org/
# Match your Chrome version
```

### Install Python Dependencies

```bash
cd "path/to/amul product alert"
pip install -r requirements.txt
```

**Dependencies should include:**
- python-telegram-bot >= 20.0
- psycopg2-binary >= 2.9
- selenium >= 4.15
- python-dotenv
- APScheduler

---

## Environment Configuration

### Create `.env` File

Create a `.env` file in the project root:

```env
# Telegram Bot
BOT_TOKEN=your_telegram_bot_token_here
LOG_GROUP_ID=-1001234567890

# Database (PostgreSQL)
DATABASE_URL=postgresql://postgres:password@localhost:5432/amul_db
DB_HOST=localhost
DB_PORT=5432
DB_NAME=amul_db
DB_USER=postgres
DB_PASSWORD=your_password

# Admin
ADMIN_IDS=123456789,987654321

# Scraper
CHROMEDRIVER_PATH=/path/to/chromedriver
AMUL_PRODUCT_URL=https://www.amul.com/products

# Feature Flags (optional)
ENABLE_AUTO_APPROVE=false
AUTO_APPROVE_TRIAL_DAYS=7
SCRAPER_INTERVAL_MINUTES=5
LOG_LEVEL=INFO
```

### Get Telegram Bot Token

1. Open Telegram app
2. Search for **@BotFather**
3. Send `/newbot`
4. Follow instructions to create bot
5. Copy the token and add to `.env`

### Get Your Chat ID (For Testing)

1. Send any message to your bot
2. Run this in Python terminal:
```python
from telegram import Bot
token = "YOUR_BOT_TOKEN"
bot = Bot(token=token)
updates = bot.get_updates()
for update in updates:
    print(f"Chat ID: {update.message.chat_id}")
```

---

## Database Setup

### Start PostgreSQL

**Windows:**
```bash
# If installed as service, it auto-starts
# Or start manually from pgAdmin
```

**macOS/Linux:**
```bash
psql -U postgres
```

### Create Database

```sql
-- Connect to PostgreSQL
psql -U postgres

-- Create database
CREATE DATABASE amul_db;

-- Connect to new database
\c amul_db

-- Verify connection
\dt  -- should show no tables yet (they'll be created by bot)
```

### Initialize Database Tables

The bot will create tables automatically on first run, OR you can run:

```bash
cd "path/to/amul product alert"
python -c "from database import init_db; init_db()"
```

**Check if tables were created:**

```sql
psql -U postgres -d amul_db

-- List all tables
\dt

-- Expected tables:
-- - users
-- - subscriptions
-- - user_preferences
-- - alert_settings
-- - pending_alerts
-- - admin_settings
-- - product_status_cache
```

---

## Running the Bot

### Start the Bot

```bash
cd "path/to/amul product alert"
python main.py
```

**Expected Output:**
```
INFO:root:Bot started successfully
INFO:root:Polling for updates...
INFO:root:Scraper cycle started
```

### Keep Bot Running

For local testing, keep the terminal open. For production:

```bash
# Using nohup (Linux/macOS)
nohup python main.py > bot.log 2>&1 &

# Using Screen (Linux/macOS)
screen -S amul_bot
python main.py
# Press Ctrl+A then D to detach

# Using pm2 (Node-based, but works with Python)
pm2 start main.py --name "amul_bot"
```

---

## Testing User Commands

Open Telegram, find your bot, and test these commands:

### 1. `/start` - Welcome & Registration

**Test:**
```
Send: /start
Expected: Welcome message with options button
Check DB: SELECT * FROM users WHERE user_id = YOUR_ID
Expected: User should be registered
```

**Response should include:**
- Welcome message
- /add for pincode
- /help for commands

### 2. `/add` - Set Pincode

**Test:**
```
Send: /add
Response: "Please enter your pincode"

Send: 411001
Expected: "Pincode added successfully!"
Check DB: SELECT pincode FROM users WHERE user_id = YOUR_ID
Expected: pincode = 411001
```

### 3. `/subscription` - Show Subscription Status

**Test:**
```
Send: /subscription
Expected: Subscription status (paid/free/trial/expired)
Shows: Start date, expiry date, days remaining
```

### 4. `/preferences` - Select Products

**Test:**
```
Send: /preferences
Expected: Inline buttons with products
- Amul Milk
- Amul Butter
- Amul Chocolate
- etc.

Click on product
Expected: ✅ added to preferences
Check DB: SELECT * FROM user_preferences WHERE user_id = YOUR_ID
```

### 5. `/alertsettings` - Configure Frequency

**Test:**
```
Send: /alertsettings
Expected: Inline buttons with options:
- Instant (as soon as stock available)
- Hourly digest (bundled hourly)
- Daily digest (bundled daily)

Click option
Expected: Settings saved
Check DB: SELECT alert_frequency FROM alert_settings WHERE user_id = YOUR_ID
```

### 6. `/quiethours` - Set Quiet Hours

**Test:**
```
Send: /quiethours
Response: "Enter start hour (0-23)"

Send: 22
Response: "Enter end hour (0-23)"

Send: 8
Expected: "Quiet hours set: 22:00 - 08:00"
Check DB: SELECT quiet_hours_start, quiet_hours_end FROM alert_settings
Expected: start=22, end=8
```

### 7. `/pause` - Pause Alerts

**Test:**
```
Send: /pause
Response: "How many days to pause? (1-30)"

Send: 7
Expected: "Alerts paused for 7 days"
Check DB: SELECT is_paused, pause_until FROM subscriptions WHERE user_id = YOUR_ID
Expected: is_paused=true, pause_until = current_date + 7 days
```

### 8. `/resume` - Resume Alerts

**Test:**
```
Send: /resume
Expected: "Alerts resumed!"
Check DB: SELECT is_paused FROM subscriptions WHERE user_id = YOUR_ID
Expected: is_paused=false
```

### 9. `/rules` - Service Rules

**Test:**
```
Send: /rules
Expected: Bot rules and terms of service displayed
```

### 10. `/help` - Commands Help

**Test:**
```
Send: /help
Expected: List of all available commands with descriptions
```

### 11. `/dm` - Message Admin

**Test:**
```
Send: /dm
Response: "Please enter your message"

Send: "Test message to admin"
Expected: Message sent, admin receives it in log group
Check LOG_GROUP_ID: Message should appear
```

### 12. `/proof` - Payment Proof Instructions

**Test:**
```
Send: /proof
Expected: Instructions for submitting payment proof
```

### 13. Photo Handler - Submit Payment Proof

**Test:**
```
Send: Photo of payment
Expected: "Proof received, admin will review"
Check DB: SELECT * FROM pending_approvals
Expected: Photo metadata stored
```

---

## Testing Admin Commands

Use ADMIN_ID from `.env` to test these:

### 1. `/autoapprove` - Toggle Free Trial

**Test (as Admin):**
```
Send: /autoapprove
Expected: Inline buttons:
- ON (enable free trial)
- OFF (disable free trial)

Click: ON
Expected: "Auto-approve enabled for 7 days"
Check DB: SELECT * FROM admin_settings
Expected: auto_approve=true, trial_days=7
```

### 2. `/settings` - Bot Settings

**Test:**
```
Send: /settings
Expected: Current settings displayed:
- Auto-approve: ON/OFF
- Trial days: X
- Scraper interval: X minutes
- Maintenance mode: ON/OFF
```

### 3. `/stats` - User Statistics

**Test:**
```
Send: /stats
Expected: Statistics like:
- Total users: X
- Active subscriptions: X
- Paused users: X
- Free trial users: X
- Blocked users: X
```

### 4. `/approve` - Approve Subscription

**Test:**
```
Send: /approve
Response: "Enter user ID"

Send: 123456789
Expected: "User approved! Subscription activated"
Check DB: SELECT is_approved FROM subscriptions WHERE user_id = 123456789
Expected: is_approved=true
```

### 5. `/extend` - Extend Subscription

**Test:**
```
Send: /extend
Response: "Enter user ID"
Send: 123456789

Response: "Enter days to extend"
Send: 30

Expected: "Subscription extended by 30 days"
Check DB: SELECT expiry_date FROM subscriptions WHERE user_id = 123456789
Expected: expiry_date moved forward by 30 days
```

### 6. `/block` - Block User

**Test:**
```
Send: /block
Response: "Enter user ID"

Send: 123456789
Expected: "User blocked!"
Check DB: SELECT is_blocked FROM users WHERE user_id = 123456789
Expected: is_blocked=true
```

### 7. `/unblock` - Unblock User

**Test:**
```
Send: /unblock
Response: "Enter user ID"

Send: 123456789
Expected: "User unblocked!"
Check DB: SELECT is_blocked FROM users WHERE user_id = 123456789
Expected: is_blocked=false
```

### 8. `/broadcast` - Message All Users

**Test:**
```
Send: /broadcast
Response: "Enter message to broadcast"

Send: "Maintenance window at 2 AM"
Expected: "Broadcasting to X users..."
All users should receive: "Maintenance window at 2 AM"
Check LOG_GROUP_ID: Broadcast logged
```

### 9. `/reply` - Reply to User

**Test:**
```
Send: /reply
Response: "Enter user ID"

Send: 123456789

Response: "Enter reply message"
Send: "Your payment has been approved"

Expected: User 123456789 receives the message
```

### 10. `/adminhelp` - Admin Help

**Test:**
```
Send: /adminhelp
Expected: List of admin commands with descriptions
```

---

## Testing Background Tasks

### 1. Scraper Cycle (Every 5 minutes)

**Test:**
```
1. Check console logs for "Scraper cycle started"
2. Verify Selenium opens Chrome browser
3. Check website for product availability
4. Verify pending_alerts table is updated
5. Wait for alerts to be sent to users

Expected:
- INFO:root:Scraper cycle started
- INFO:root:Checking product: Amul Milk
- INFO:root:Product available at pincode: 411001
- INFO:root:Alerts sent: 5 users
```

**Logs Location:**
```
# If you configured logging, check:
tail -f amul_bot.log

# Or in Python:
import logging
logging.basicConfig(level=logging.INFO)
```

### 2. Hourly Digests (Every 60 minutes)

**Test:**
```
1. Set alert frequency to "Hourly" for a user
2. Generate some pending alerts
3. Wait for hourly digest to run

Expected:
- INFO:root:Sending hourly digests...
- User receives bundled alerts in one message
- pending_alerts table cleared for that user
```

### 3. Daily Digests (At 08:00 AM)

**Test:**
```
1. Set alert frequency to "Daily" for a user
2. Generate some pending alerts
3. Wait until 08:00 AM (or manually trigger)

Expected:
- INFO:root:Sending daily digests...
- User receives all alerts in one message at 08:00
- pending_alerts table cleared
```

### 4. Auto-Resume Paused Users (Every 24 hours)

**Test:**
```
1. Pause user alerts for 1 day
2. Wait 24 hours (or check if pause_until < now())
3. Bot should automatically resume

Check DB:
SELECT is_paused FROM subscriptions WHERE user_id = YOUR_ID
Expected: is_paused = false
User should receive: "Your alerts have been resumed!"
```

---

## Testing Scraper

### Direct Scraper Test

```python
# In Python terminal
from scraper import check_product_availability

# Test single product
result = check_product_availability("Amul Milk", "411001")
print(result)

# Expected output:
# {
#     'product': 'Milk',
#     'available': True,
#     'pincode': '411001',
#     'timestamp': '2026-01-31 14:30:00'
# }
```

### Selenium Check

```python
from selenium import webdriver
from selenium.webdriver.common.by import By

driver = webdriver.Chrome('/path/to/chromedriver')
driver.get('https://www.amul.com/products')

# Check if page loads
title = driver.title
print(f"Page title: {title}")

# Find product elements
products = driver.find_elements(By.CLASS_NAME, "product-item")
print(f"Found {len(products)} products")

driver.quit()
```

### Test with Real Products

```python
from scraper import scrape_amul_products

products = scrape_amul_products()
for product in products:
    print(f"- {product['name']}: Available at {product['pincodes']}")

# Should output something like:
# - Milk: Available at [411001, 411002, 411003]
# - Butter: Available at [411001, 411004]
# - Chocolate: Available at [411002]
```

---

## Testing Database Operations

### Connection Test

```python
import psycopg2
from config import DATABASE_URL

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# Test query
cur.execute("SELECT version()")
print(cur.fetchone())

cur.close()
conn.close()
```

### Table Creation Test

```python
from database import init_db

# Initialize all tables
init_db()

# Check tables
import psycopg2
from config import DATABASE_URL

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public'
""")

tables = cur.fetchall()
for table in tables:
    print(f"✓ {table[0]}")

cur.close()
conn.close()

# Expected tables:
# ✓ users
# ✓ subscriptions
# ✓ user_preferences
# ✓ alert_settings
# ✓ pending_alerts
# ✓ admin_settings
# ✓ product_status_cache
```

### User Registration Test

```python
from database import create_user

# Create test user
user_id = 123456789
username = "testuser"
first_name = "Test"

success = create_user(user_id, username, first_name)
print(f"User created: {success}")

# Verify in DB
from database import get_user
user = get_user(user_id)
print(user)
```

### Subscription Test

```python
from database import create_subscription, get_subscription

# Create subscription
user_id = 123456789
success = create_subscription(user_id, subscription_type="trial")
print(f"Subscription created: {success}")

# Get subscription
subscription = get_subscription(user_id)
print(subscription)
```

### Preferences Test

```python
from database import add_user_preference, get_user_preferences

# Add preference
user_id = 123456789
preference = "Amul Milk"
success = add_user_preference(user_id, preference)
print(f"Preference added: {success}")

# Get preferences
prefs = get_user_preferences(user_id)
print(f"User preferences: {prefs}")
```

### Alerts Test

```python
from database import add_pending_alert, get_pending_alerts

# Add alert
user_id = 123456789
product = "Amul Milk"
pincode = "411001"
success = add_pending_alert(user_id, product, pincode)
print(f"Alert added: {success}")

# Get alerts
alerts = get_pending_alerts(user_id)
print(f"Pending alerts: {alerts}")
```

---

## Testing Workflow - Complete End-to-End

### Day 1: Setup & Configuration
- [ ] Install Python dependencies
- [ ] Set up PostgreSQL database
- [ ] Create `.env` file
- [ ] Verify chromedriver is working
- [ ] Start bot and check logs

### Day 2: Basic User Flow
- [ ] Register new user (`/start`)
- [ ] Add pincode (`/add`)
- [ ] Select products (`/preferences`)
- [ ] Configure alert settings (`/alertsettings`)
- [ ] Set quiet hours (`/quiethours`)
- [ ] Check subscription status (`/subscription`)

### Day 3: Alert Testing
- [ ] Manually trigger scraper
- [ ] Verify alerts sent to users
- [ ] Test instant alerts
- [ ] Test hourly digest
- [ ] Wait for daily digest at 08:00 AM

### Day 4: Pause/Resume
- [ ] Pause alerts (`/pause`)
- [ ] Verify paused in DB
- [ ] Resume alerts (`/resume`)
- [ ] Wait 24 hours to test auto-resume

### Day 5: Admin Features
- [ ] Test `/stats` command
- [ ] Test `/broadcast` to all users
- [ ] Test `/block` and `/unblock` user
- [ ] Test `/approve` and `/extend` subscription
- [ ] Enable/disable auto-approve

### Day 6: Error Handling
- [ ] Send invalid pincode
- [ ] Send invalid product
- [ ] Test network interruption
- [ ] Test database connection loss
- [ ] Test bot restart recovery

### Day 7: Performance
- [ ] Test with 10+ concurrent users
- [ ] Verify response time < 100ms
- [ ] Check memory usage
- [ ] Check database query performance
- [ ] Review logs for errors

---

## Troubleshooting

### Bot Won't Start

```
Error: "No module named 'telegram'"
Solution: pip install python-telegram-bot

Error: "ModuleNotFoundError: No module named 'config'"
Solution: Make sure you're in the correct directory:
cd "path/to/amul product alert"

Error: "Bot token is invalid"
Solution: Check BOT_TOKEN in .env file
```

### Database Connection Failed

```
Error: "psycopg2.OperationalError: could not connect to server"
Solution:
1. Check PostgreSQL is running
2. Verify DATABASE_URL in .env
3. Check username/password
4. Verify database exists: psql -l

# Test connection:
python -c "import psycopg2; psycopg2.connect('postgresql://user:pass@localhost/amul_db')"
```

### Scraper Not Working

```
Error: "WebDriver error"
Solution:
1. Download correct chromedriver version
2. Match your Chrome version: chrome://version
3. Set correct path in CHROMEDRIVER_PATH

Error: "Element not found"
Solution:
1. Website HTML may have changed
2. Update selectors in scraper.py
3. Manually check: https://www.amul.com/products
```

### Alerts Not Sending

```
Troubleshoot:
1. Check pending_alerts table is populated
2. Verify user has preferences selected
3. Check quiet hours aren't blocking alert
4. Verify user subscription is active
5. Check bot has message permissions

# Debug:
SELECT * FROM pending_alerts;
SELECT * FROM subscriptions WHERE user_id = YOUR_ID;
SELECT * FROM alert_settings WHERE user_id = YOUR_ID;
```

### Background Tasks Not Running

```
Check logs for:
- "Scraper cycle started"
- "Sending hourly digests"
- "Checking expired pauses"

If not running:
1. Verify bot is still running
2. Check for exceptions in logs
3. Verify APScheduler is installed
4. Check timezone settings
```

---

## Test Checklist

- [ ] Bot starts without errors
- [ ] User can register with `/start`
- [ ] User can set pincode with `/add`
- [ ] User can select products with `/preferences`
- [ ] User can configure alerts with `/alertsettings`
- [ ] User can set quiet hours with `/quiethours`
- [ ] User can pause/resume with `/pause` and `/resume`
- [ ] Admin can approve users with `/approve`
- [ ] Admin can broadcast with `/broadcast`
- [ ] Admin can block/unblock users
- [ ] Scraper runs every 5 minutes
- [ ] Hourly digest sent at correct time
- [ ] Daily digest sent at 08:00 AM
- [ ] Auto-resume works after pause expires
- [ ] Database operations complete successfully
- [ ] Error handling works correctly
- [ ] Response time < 100ms
- [ ] No memory leaks after 24 hours

---

## Support

If tests fail, check:
1. Console logs for error messages
2. Database logs: `tail -f /var/log/postgresql/postgresql.log`
3. Bot logs (if configured)
4. Telegram updates: `https://api.telegram.org/bot<TOKEN>/getUpdates`

Good luck testing! 🚀
