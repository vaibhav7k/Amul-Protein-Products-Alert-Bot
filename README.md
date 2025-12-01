# 🥛 Amul Product Alert Bot

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot%20API-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Database-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Selenium](https://img.shields.io/badge/Selenium-Web%20Scraping-43B02A?style=for-the-badge&logo=selenium&logoColor=white)](https://www.selenium.dev/)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
[![Maintenance](https://img.shields.io/badge/Maintained%3F-no-red.svg?style=for-the-badge)](https://github.com/vaibhav7k/Amul-Protein-Products-Alert-Bot/graphs/commit-activity)

A powerful Telegram bot that monitors Amul Shop product availability and sends real-time stock alerts to subscribers based on their pincode. Never miss your favorite Amul products again!

---

## 📸 Screenshots

<p align="center">
  <img src="assets/screenshot_start.PNG" alt="Start Menu" width="30%" />
  <img src="assets/screenshot_alert.PNG" alt="Stock Alert" width="30%" />
</p>

<p align="center">
  <em>Left: Welcome menu with options | Right: Stock alert notification</em>
</p>

---

## ✨ Features

* **🔄 Real-time Stock Monitoring** - Automatically checks Amul products every 30 seconds
* **📍 Pincode-based Alerts** - Users receive alerts only for their specific location
* **👥 Subscription Management** - Admin-controlled user subscriptions with expiry dates
* **🆓 Auto-approve Mode** - Optional free trial mode for new users
* **👑 Admin Dashboard** - Comprehensive admin commands for user management
* **🛡️ Rate Limiting** - Built-in spam protection for all commands
* **📦 Consolidated Alerts** - Groups multiple product updates into single messages
* **🗄️ Connection Pooling** - Efficient database operations with PostgreSQL
* **📝 Comprehensive Logging** - Built-in logging to Telegram groups for monitoring
* **🧵 Non-Blocking Architecture** - Async design keeps the bot responsive

## 🛠️ Prerequisites

Before you begin, ensure you have the following installed:

1. **Python 3.9+**: [Download Python](https://www.python.org/downloads/)
2. **PostgreSQL**: [Download PostgreSQL](https://www.postgresql.org/download/)
3. **Google Chrome**: Required for web scraping
4. **ChromeDriver**: Must match your Chrome version - [Download ChromeDriver](https://chromedriver.chromium.org/downloads)
5. **Telegram Bot Token**: Create a bot via [@BotFather](https://t.me/BotFather)

> **⚠️ Important:** Ensure ChromeDriver is added to your system's `PATH` environment variable or set the path in `.env`.

---

## 📁 Project Structure

```
amul_bot/
├── main.py              # Entry point - ties everything together
├── config.py            # Environment variables & constants
├── database.py          # PostgreSQL operations with connection pooling
├── scraper.py           # Selenium web scraping logic
├── utils.py             # Logging, decorators, helper functions
├── handlers/            # Telegram command handlers
│   ├── __init__.py      # Package exports
│   ├── user.py          # User-facing commands (/start, /add, etc.)
│   └── admin.py         # Admin-only commands (/stats, /broadcast, etc.)
├── requirements.txt     # Python dependencies with version pins
├── Procfile             # Heroku deployment configuration
├── .env.example         # Environment variable template
├── .gitignore           # Git ignore rules
├── LICENSE              # MIT License
└── README.md            # This file
```

---

## 🚀 Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/vaibhav7k/Amul-Protein-Products-Alert-Bot.git
   cd Amul-Protein-Products-Alert-Bot
   ```

2. **Create and activate a virtual environment**
   ```bash
   # Windows
   python -m venv venv
   .\venv\Scripts\activate

   # macOS/Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your actual values
   ```

5. **Run the bot**
   ```bash
   python main.py
   ```

---

## 💡 Usage

### For Users:
1. Start the bot with `/start`
2. Set your pincode using `/add <pincode>`
3. Submit payment proof (if required) or wait for auto-approval
4. Receive real-time stock alerts for your location!

### For Admins:
1. Add the bot to your admin group
2. Use `/adminhelp` to see all available commands
3. Approve users, broadcast messages, and manage subscriptions

---

## ⚙️ Configuration

Copy `.env.example` to `.env` and fill in your values:

| Variable | Description | Required |
|----------|-------------|----------|
| `BOT_TOKEN` | Telegram bot token from @BotFather | ✅ |
| `DATABASE_URL` | PostgreSQL connection URL | ✅ |
| `ADMIN_GROUP_ID` | Telegram group ID for admin actions | ✅ |
| `LOG_GROUP_ID` | Telegram group ID for logging | ❌ |
| `GOOGLE_CHROME_BIN` | Path to Chrome binary | ✅ |
| `CHROMEDRIVER_PATH` | Path to ChromeDriver | ✅ |
| `CHECK_INTERVAL_SECONDS` | Stock check frequency (default: 30) | ❌ |

> **💡 Tip:** To get a Telegram group ID, add [@userinfobot](https://t.me/userinfobot) to your group.

---

## 📱 Bot Commands

### User Commands
| Command | Description |
|---------|-------------|
| `/start` | Start the bot and see the main menu |
| `/add <pincode>` | Set or update your pincode |
| `/subscription` | Check your subscription status |
| `/proof` | Get payment instructions |
| `/rules` | View service rules |
| `/dm <message>` | Send a message to admin |
| `/help` | Show available commands |

### Admin Commands (Admin Group Only)
| Command | Description |
|---------|-------------|
| `/approve <chat_id> [days]` | Approve user subscription |
| `/extend <chat_id> <days>` | Extend subscription |
| `/block <chat_id>` | Block a user |
| `/unblock <chat_id>` | Unblock a user |
| `/reply <chat_id> <msg>` | Reply to a user |
| `/broadcast <message>` | Message all active users |
| `/stats` | View user statistics |
| `/autoapprove <on\|off>` | Toggle free trial mode |
| `/settings` | View current settings |
| `/adminhelp` | Show admin commands |

---

## 🌐 Deployment

### Heroku

1. **Create a new Heroku app**
   ```bash
   heroku create your-app-name
   ```

2. **Add PostgreSQL addon**
   ```bash
   heroku addons:create heroku-postgresql:mini
   ```

3. **Add Chrome buildpacks**
   ```bash
   heroku buildpacks:add heroku/python
   heroku buildpacks:add https://github.com/heroku/heroku-buildpack-google-chrome
   heroku buildpacks:add https://github.com/heroku/heroku-buildpack-chromedriver
   ```

4. **Set environment variables**
   ```bash
   heroku config:set BOT_TOKEN=your_token
   heroku config:set ADMIN_GROUP_ID=your_group_id
   ```

5. **Deploy**
   ```bash
   git push heroku main
   ```

6. **Scale the worker**
   ```bash
   heroku ps:scale worker=1
   ```

---

## 🔧 Troubleshooting

### ChromeDriver not found
- **Windows**: Download from [chromedriver.chromium.org](https://chromedriver.chromium.org/downloads) and add to `PATH`
- **macOS**: `brew install chromedriver`
- **Linux**: `sudo apt install chromium-chromedriver`

### Bot not responding
- Verify `BOT_TOKEN` is correct
- Check if the bot is running: `python main.py`
- Review logs for error messages

### Database connection failed
- Verify `DATABASE_URL` format: `postgres://user:pass@host:port/dbname`
- Ensure PostgreSQL is running
- Check network/firewall settings

### Scraper errors
- Ensure Chrome and ChromeDriver versions match
- Check if Amul website structure has changed
- Review Selenium logs for detailed errors

---

## 💻 Code Quality

This project maintains professional coding standards:

- ✅ **Type Hints** - All functions include proper type annotations
- ✅ **Docstrings** - Comprehensive documentation for all modules
- ✅ **Logging** - Proper logging throughout for debugging
- ✅ **Error Handling** - Specific exception handling with meaningful messages
- ✅ **PEP 8 Compliance** - Code follows Python style guidelines
- ✅ **Dependency Pinning** - All package versions are pinned for reproducibility
- ✅ **Modular Architecture** - Clean separation of concerns

---

## 🔒 Security Notes

- ⚠️ Never commit `.env` file to version control
- 🔑 Keep your `BOT_TOKEN` secret
- 🌍 Use environment variables for all sensitive data
- 👑 The admin group ID restricts admin commands to authorized users
- 🛡️ Rate limiting prevents spam and abuse

---

## 🤝 Contributing

Contributions are welcome! Here's how you can help:

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

### Ways to Contribute:
- 🐛 Report bugs by opening issues
- 💡 Suggest new features
- 📝 Improve documentation
- 🧪 Write tests

---

## 📋 Changelog

### Version 1.0.0 (Initial Release)
- ✨ Real-time stock monitoring with Selenium
- 📍 Pincode-based alert system
- 👥 User subscription management
- 👑 Comprehensive admin dashboard
- 🆓 Auto-approve mode for free trials
- 📦 Consolidated alert messages
- 🗄️ PostgreSQL with connection pooling
- 📝 Telegram logging integration
- 🛡️ Rate limiting for spam protection

---

## 🙋 FAQ

**Q: How often does the bot check for stock?**  
A: By default, every 30 seconds. This can be configured via `CHECK_INTERVAL_SECONDS`.

**Q: Can I monitor products for multiple pincodes?**  
A: Currently, each user can only set one pincode at a time.

**Q: What products are monitored?**  
A: The bot monitors Amul High Protein products including milk, lassi, buttermilk, paneer, and whey protein. See `config.py` to customize.

**Q: Is there an API available?**  
A: No, the bot scrapes the Amul website directly using Selenium.

**Q: Can I self-host this bot?**  
A: Yes! Follow the installation instructions above.

**Q: How do I add new products to monitor?**  
A: Edit the `URLS_TO_CHECK` list in `config.py`.

---

## ⚠️ Disclaimer

This software is intended for **personal use only**. It should be used responsibly and in accordance with Amul's terms of service.

The developers of this application assume no liability for any misuse or any issues arising from the use of this bot.

---

##  License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

---

## 📞 Support & Contact

- 🐛 Found a bug? Open an [issue](https://github.com/vaibhav7k/Amul-Protein-Products-Alert-Bot/issues)
- 💡 Have a suggestion? Start a [discussion](https://github.com/vaibhav7k/Amul-Protein-Products-Alert-Bot/discussions)
- ⭐ Like this project? Give it a star!

---

## 🙏 Acknowledgments

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - Telegram Bot API wrapper
- [Selenium](https://www.selenium.dev/) - Web automation framework
- [psycopg2](https://www.psycopg.org/) - PostgreSQL adapter for Python
- [Amul](https://amul.com/) - For their amazing products! 🥛

---

<p align="center">
  <strong>Made with ❤️ by <a href="https://github.com/vaibhav7k">Vaibhav</a></strong>
  <br>
  <sub>⭐ If you found this project helpful, please consider giving it a star!</sub>
</p>
