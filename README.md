# Automated Trading Bot

A Python-based automated trading bot that implements a momentum strategy using Rate of Change (ROC) indicator. The bot runs 24/7, executes trades through Alpaca API, and sends real-time notifications via Pushbullet.

## Features

- Momentum-based trading strategy using Rate of Change (ROC)
- Real-time market data fetching via Alpaca API
- Automated trade execution
- Pushbullet notifications for trade alerts and system status
- Hourly strategy execution using scheduler
- Comprehensive logging system

## Setup

1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill in your credentials:
   - Alpaca API credentials (get from https://app.alpaca.markets/)
   - Twilio credentials for WhatsApp notifications (get from https://www.twilio.com/)

4. Configure your trading parameters in the `.env` file:
   - TRADING_SYMBOL: The stock symbol to trade
   - Other parameters as needed

## Running the Bot

```bash
python trading_bot.py
```

## Deployment on Oracle Cloud VM

1. Create an Oracle Cloud Free Tier account
2. Launch an Always Free VM instance
3. Install Python and required dependencies
4. Set up a cron job to ensure the bot runs continuously:
   ```bash
   crontab -e
   @reboot cd /path/to/trading-bot && python trading_bot.py
   ```

## Monitoring

- Check trading_bot.log for detailed activity logs
- Monitor WhatsApp notifications for real-time alerts
- Review Alpaca dashboard for trade history

## Risk Warning

This is a sample trading bot for educational purposes. Always test thoroughly with paper trading before using real money. Past performance does not guarantee future results.
