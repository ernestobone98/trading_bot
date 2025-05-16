# Automated Long-Term Trading Bot

A Python-based automated trading bot that implements a long-term strategy using 50-day and 200-day Simple Moving Averages (SMA) crossover, with MACD confirmation. The bot supports multiple trading symbols, runs 24/7 (checking hourly based on daily data), executes trades through the Alpaca API, and sends real-time notifications via Pushbullet.

## Features

- Long-term trading strategy:
    - 50-day & 200-day Simple Moving Average (SMA) crossover (Golden Cross/Death Cross)
    - Moving Average Convergence Divergence (MACD) for signal confirmation
- Supports multiple trading symbols simultaneously.
- Real-time market data fetching (daily timeframe) via Alpaca API.
- Automated trade execution.
- Pushbullet notifications for trade alerts and system status.
- Hourly strategy execution using `schedule` (evaluates daily data each hour).
- Comprehensive logging system.
- Key dependency: `pandas-ta` for technical indicator calculation.

## Setup

1.  **Clone this repository:**
    ```bash
    git clone <your-repository-url>
    cd trading-bot
    ```
2.  **Create a Python virtual environment (recommended):**
    ```bash
    python -m venv env
    source env/bin/activate  # On Windows: env\Scripts\activate
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Configure Environment Variables:**
    Copy `.env.example` (if you have one) to `.env` or create a new `.env` file and add your credentials:
    ```
    ALPACA_API_KEY="YOUR_ALPACA_API_KEY"
    ALPACA_SECRET_KEY="YOUR_ALPACA_SECRET_KEY"
    ALPACA_BASE_URL="https://paper-api.alpaca.markets" # For paper trading, or https://api.alpaca.markets for live
    
    PUSHBULLET_API_KEY="YOUR_PUSHBULLET_API_KEY" 
    
    # Comma-separated list of symbols to trade
    TRADING_SYMBOLS="SPY,QQQ,AAPL" 
    ```
    - Get Alpaca API credentials from [https://app.alpaca.markets/](https://app.alpaca.markets/).
    - Get Pushbullet API key from [https://www.pushbullet.com/#settings/account](https://www.pushbullet.com/#settings/account).

## Running the Bot

```bash
python trading_bot.py
```
The bot will run the strategy once on startup and then every hour.

## Deployment on a Server (e.g., Oracle Cloud VM)

1.  Create a server instance (e.g., Oracle Cloud Free Tier, AWS EC2, DigitalOcean Droplet).
2.  Ensure Python, pip, and git are installed.
3.  Clone the repository and set up the virtual environment and dependencies as described in the "Setup" section.
4.  Create the `.env` file with your production credentials on the server.
5.  To run the bot continuously and ensure it restarts on reboot, you can use a process manager like `systemd` (recommended for robustness) or a simpler `cron` job.

    **Example using `cron` (simpler, less robust):**
    ```bash
    crontab -e
    ```
    Add the following line (adjust paths as necessary):
    ```
    @reboot /path/to/your/trading-bot/env/bin/python /path/to/your/trading-bot/trading_bot.py >> /path/to/your/trading-bot/cron.log 2>&1
    ```
    Ensure your script is executable or called with the python interpreter from your virtual environment.

    **For `systemd` (more complex, more robust):**
    You would create a service file in `/etc/systemd/system/tradingbot.service`. This provides better process management, logging, and auto-restarts. (Detailed `systemd` setup is beyond this README's scope but is a common practice for production Python applications).

## Monitoring

- Check `trading_bot.log` for detailed activity logs.
- Monitor Pushbullet notifications for real-time alerts.
- Review your Alpaca dashboard for trade history and positions.

## Risk Warning

This trading bot is provided for educational and illustrative purposes only. Trading financial markets involves substantial risk of loss and is not suitable for all investors. Always test thoroughly with paper trading before risking real money. Past performance is not indicative of future results. The developers and contributors of this bot are not liable for any financial losses incurred. Use at your own risk.
