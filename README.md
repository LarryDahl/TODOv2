# Dotolista - Telegram Todo Bot v2

To-Do v.2 - Todo-list updated to this millenium

## Features

- Logs tasks into SQLite database
- Shows list of unfinished tasks
- Allows deleting or editing
- Project support with ordered steps
- Priority system with time-based boosts
- AI-analysis coming soonish

## Setup

1. Install dependencies:
   ```bash
   pip install -r app/requirements.txt
   ```

2. Create `.env` file with:
   ```
   BOT_TOKEN=your_telegram_bot_token
   DB_PATH=data/todo.db  # Optional, defaults to data/todo.db
   ```

3. Run the bot:
   ```bash
   python -m app.main
   ```

## Important: Single Instance Only

**⚠️ CRITICAL: Only run ONE instance of this bot at a time!**

Running multiple instances will cause `TelegramConflictError: terminated by other getUpdates request`.

### Why this happens:
- Telegram Bot API only allows one active `getUpdates` connection per bot token
- If you run the bot twice (e.g., in two terminals), both try to poll for updates
- Telegram rejects the second connection, causing the error

### How to check:
```bash
# Check if bot is already running
ps aux | grep "python.*app.main"
# or on Windows:
tasklist | findstr python
```

### If you see the error:
1. **Stop all running instances** of the bot
2. **Wait a few seconds** for Telegram to release the connection
3. **Start only ONE instance** again

### Development tips:
- Use `Ctrl+C` to stop the bot cleanly
- Check for background processes before starting
- If using a process manager (systemd, supervisor), ensure only one instance is configured
- **Never run both polling and webhook** at the same time (this bot uses polling only)

## Logging

The bot logs startup information including:
- Process ID (PID) - helps identify which instance is running
- Startup/shutdown events
- Error messages with full tracebacks

Look for log messages like:
```
Bot starting - PID: 12345
Starting polling - PID: 12345
Bot is ready to receive updates
```

## Database

- Default location: `data/todo.db`
- SQLite database (no separate server needed)
- Automatically creates tables on first run
- Migrations run automatically when schema changes
