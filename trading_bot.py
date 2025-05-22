import os
import time
import logging
import schedule
import pandas as pd
import pandas_ta as ta # For technical indicators
import numpy as np
from datetime import datetime, timedelta, date as GDate
import pytz
from dotenv import load_dotenv
from alpaca_trade_api.rest import REST, TimeFrame
from notifications import send_pushbullet_alert
from prometheus_client import start_http_server, Gauge, Counter, Info

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    filename='trading_bot.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- Prometheus Metrics Definition ---
bot_info = Info('trading_bot', 'Information about the trading bot')
bot_active = Gauge('trading_bot_active', 'Is the trading bot currently running (1 for active, 0 for inactive)')
last_run_timestamp_seconds = Gauge('trading_bot_last_run_timestamp_seconds', 'Timestamp of the last strategy execution run')

trades_total = Counter('trading_bot_trades_total', 'Total number of trades executed', ['symbol', 'side'])
errors_total = Counter('trading_bot_errors_total', 'Total number of errors encountered', ['type'])

current_position_qty_metric = Gauge('trading_bot_current_position_qty', 'Current quantity held for a symbol', ['symbol'])
asset_latest_close_price_metric = Gauge('trading_bot_asset_latest_close_price', 'Latest closing price for an asset', ['symbol'])
asset_sma_short_metric = Gauge('trading_bot_asset_sma_short', 'Short-term SMA for an asset', ['symbol'])
asset_sma_long_metric = Gauge('trading_bot_asset_sma_long', 'Long-term SMA for an asset', ['symbol'])
asset_macd_line_metric = Gauge('trading_bot_asset_macd_line', 'MACD line for an asset', ['symbol'])
asset_macd_signal_line_metric = Gauge('trading_bot_asset_macd_signal_line', 'MACD signal line for an asset', ['symbol'])
# ---

class LongTermTradingBot: # Renamed class for clarity
    def __init__(self):
        # Initialize Alpaca API client
        self.api = REST(
            key_id=os.getenv('ALPACA_API_KEY'),
            secret_key=os.getenv('ALPACA_SECRET_KEY'),
            base_url=os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
        )
        symbols_str = os.getenv('TRADING_SYMBOLS', 'SPY') # Expecting comma-separated string
        self.symbols = [symbol.strip().upper() for symbol in symbols_str.split(',')]
        self.timeframe = TimeFrame.Day # Changed to Day for long-term
        self.positions = {symbol: 0.0 for symbol in self.symbols} # To store current quantity for each symbol

        # Indicator parameters
        self.sma_short_window = 50
        self.sma_long_window = 200
        self.macd_fast_period = 12
        self.macd_slow_period = 26
        self.macd_signal_period = 9
        
        self.initial_data_fetch_limit = self.sma_long_window + 100 # Fetch enough data for longest SMA

        self.todays_executed_trades = []  # For daily summary
        self.last_summary_sent_date = None # Track when last summary was sent

        bot_info.info({'version': '1.0.0', 'strategy': 'LongTermSMAMACD'})

    def is_market_open(self):
        """Check if the stock market is currently open."""
        try:
            clock = self.api.get_clock()
            logging.info(f"Market status: is_open={clock.is_open}, next_open='{clock.next_open}', next_close='{clock.next_close}'")
            return clock.is_open
        except Exception as e:
            logging.error(f"Error checking market status: {e}")
            send_pushbullet_alert(f"Bot Error: Could not check market status: {e}")
            errors_total.labels(type='get_clock').inc()
            return False # Assume closed if status check fails

    def get_historical_data(self, symbol):
        """Fetch historical data for analysis for a specific symbol"""
        try:
            # Define an explicit end date to be yesterday in New York time.
            # This ensures we're asking for 'limit' bars ending on a completed trading day.
            yesterday_ny = pd.Timestamp.now(tz='America/New_York').normalize() - pd.Timedelta(days=1)
            end_dt_for_api = yesterday_ny.to_pydatetime().strftime('%Y-%m-%d') # Convert to standard Python datetime yyyy-mm-dd
            start_dt_for_api = (yesterday_ny - pd.Timedelta(days=self.initial_data_fetch_limit)).to_pydatetime().strftime('%Y-%m-%d')

            logging.info(f"Fetching {self.initial_data_fetch_limit} bars for {symbol} ending on {end_dt_for_api}")

            bars = self.api.get_bars(
                symbol,
                self.timeframe,
                limit=self.initial_data_fetch_limit,
                start=start_dt_for_api,
                end=end_dt_for_api  # Explicitly set end date
            ).df
            # Ensure datetime index is timezone-aware (Alpaca usually provides this)
            if bars.index.tz is None:
                bars.index = bars.index.tz_localize('UTC')
            else:
                bars.index = bars.index.tz_convert('UTC')
            return bars
        except Exception as e:
            logging.error(f"Error fetching historical data for {symbol}: {e}")
            send_pushbullet_alert(f"Error fetching data for {symbol}: {e}")
            errors_total.labels(type='fetch_data').inc()
            return pd.DataFrame() # Return empty DataFrame on error

    def calculate_indicators(self, data, symbol): # Added symbol for metrics
        """Calculate SMA and MACD indicators"""
        if data.empty or len(data) < self.sma_long_window:
            logging.warning(f"Not enough data to calculate indicators. Data length: {len(data)}, required: {self.sma_long_window}")
            return data # Return original data if not enough for calculation

        try:
            data[f'SMA{self.sma_short_window}'] = ta.sma(data['close'], length=self.sma_short_window)
            data[f'SMA{self.sma_long_window}'] = ta.sma(data['close'], length=self.sma_long_window)
            
            # Calculate MACD using pandas_ta
            macd_df = ta.macd(data['close'], fast=self.macd_fast_period, slow=self.macd_slow_period, signal=self.macd_signal_period)
            if macd_df is not None and not macd_df.empty:
                data[f'MACD_{self.macd_fast_period}_{self.macd_slow_period}_{self.macd_signal_period}'] = macd_df[f'MACD_{self.macd_fast_period}_{self.macd_slow_period}_{self.macd_signal_period}']
                data[f'MACDs_{self.macd_fast_period}_{self.macd_slow_period}_{self.macd_signal_period}'] = macd_df[f'MACDs_{self.macd_fast_period}_{self.macd_slow_period}_{self.macd_signal_period}']
                # data[f'MACDh_{self.macd_fast_period}_{self.macd_slow_period}_{self.macd_signal_period}'] = macd_df[f'MACDh_{self.macd_fast_period}_{self.macd_slow_period}_{self.macd_signal_period}'] # Histogram, if needed
            else:
                logging.warning("MACD calculation returned None or empty DataFrame.")
                # Add NaN columns if MACD calculation fails to prevent KeyErrors later
                data[f'MACD_{self.macd_fast_period}_{self.macd_slow_period}_{self.macd_signal_period}'] = float('nan')
                data[f'MACDs_{self.macd_fast_period}_{self.macd_slow_period}_{self.macd_signal_period}'] = float('nan')

        except Exception as e:
            logging.error(f"Error calculating indicators: {e}")
            errors_total.labels(type='calculate_indicators').inc()
            # Ensure columns exist even if calculation fails
            if f'SMA{self.sma_short_window}' not in data.columns: data[f'SMA{self.sma_short_window}'] = float('nan')
            if f'SMA{self.sma_long_window}' not in data.columns: data[f'SMA{self.sma_long_window}'] = float('nan')
            if f'MACD_{self.macd_fast_period}_{self.macd_slow_period}_{self.macd_signal_period}' not in data.columns: data[f'MACD_{self.macd_fast_period}_{self.macd_slow_period}_{self.macd_signal_period}'] = float('nan')
            if f'MACDs_{self.macd_fast_period}_{self.macd_slow_period}_{self.macd_signal_period}' not in data.columns: data[f'MACDs_{self.macd_fast_period}_{self.macd_slow_period}_{self.macd_signal_period}'] = float('nan')
            
        # Update metrics after calculation, before dropna to get latest available values
        if not data.empty:
            latest_data_for_metrics = data.iloc[-1]
            asset_sma_short_metric.labels(symbol=symbol).set(latest_data_for_metrics.get(f'SMA{self.sma_short_window}', float('nan')))
            asset_sma_long_metric.labels(symbol=symbol).set(latest_data_for_metrics.get(f'SMA{self.sma_long_window}', float('nan')))
            asset_macd_line_metric.labels(symbol=symbol).set(latest_data_for_metrics.get(f'MACD_{self.macd_fast_period}_{self.macd_slow_period}_{self.macd_signal_period}', float('nan')))
            asset_macd_signal_line_metric.labels(symbol=symbol).set(latest_data_for_metrics.get(f'MACDs_{self.macd_fast_period}_{self.macd_slow_period}_{self.macd_signal_period}', float('nan')))

        return data.dropna() # Drop rows with NaN values after indicator calculation

    def generate_signals(self, data, current_position_qty, symbol): # Added symbol for potential future metrics
        """Generate trading signals based on SMA crossover and MACD confirmation"""
        if data.empty or len(data) < 2: # Need at least 2 data points for comparison
            logging.info("Not enough data points to generate signals after indicator calculation.")
            return None

        latest = data.iloc[-1]
        # previous = data.iloc[-2] # For detecting crossover event, if needed explicitly

        sma_short = latest[f'SMA{self.sma_short_window}']
        sma_long = latest[f'SMA{self.sma_long_window}']
        macd_line = latest[f'MACD_{self.macd_fast_period}_{self.macd_slow_period}_{self.macd_signal_period}']
        macd_signal_line = latest[f'MACDs_{self.macd_fast_period}_{self.macd_slow_period}_{self.macd_signal_period}']

        # Buy Signal: Golden Cross (SMA short > SMA long) & MACD confirmation (MACD line > Signal line)
        # And not already in a long position
        if sma_short > sma_long and macd_line > macd_signal_line and float(current_position_qty) <= 0:
            # Optional: Check for actual crossover if using 'previous' data
            # prev_sma_short = previous[f'SMA{self.sma_short_window}']
            # prev_sma_long = previous[f'SMA{self.sma_long_window}']
            # if prev_sma_short <= prev_sma_long: # Confirms crossover just happened
            return 'buy'

        # Sell Signal: Death Cross (SMA short < SMA long) & MACD confirmation (MACD line < Signal line)
        # And currently in a long position
        elif sma_short < sma_long and macd_line < macd_signal_line and float(current_position_qty) > 0:
            # Optional: Check for actual crossover
            # prev_sma_short = previous[f'SMA{self.sma_short_window}']
            # prev_sma_long = previous[f'SMA{self.sma_long_window}']
            # if prev_sma_short >= prev_sma_long: # Confirms crossover just happened
            return 'sell'
            
        return None

    def execute_trade(self, signal, symbol, current_position_qty):
        """Execute trades based on signals for a specific symbol"""
        qty_to_trade = 1 # Define your position sizing logic here
        trade_executed_flag = False
        trade_description = ""

        try:
            if signal == 'buy' and float(current_position_qty) <= 0:
                self.api.submit_order(
                    symbol=symbol,
                    qty=qty_to_trade,
                    side='buy',
                    type='market',
                    time_in_force='gtc'
                )
                message = f"BUY order placed for {qty_to_trade} of {symbol}"
                logging.info(message)
                # send_pushbullet_alert(message) # Removed for daily summary
                trade_description = f"BOUGHT {qty_to_trade} {symbol}"
                self.positions[symbol] += qty_to_trade
                trades_total.labels(symbol=symbol, side='buy').inc()
                trade_executed_flag = True
                
            elif signal == 'sell' and float(current_position_qty) > 0:
                sell_qty = min(qty_to_trade, abs(float(current_position_qty)))
                if sell_qty > 0:
                    self.api.submit_order(
                        symbol=symbol,
                        qty=sell_qty,
                        side='sell',
                        type='market',
                        time_in_force='gtc'
                    )
                    message = f"SELL order placed for {sell_qty} of {symbol}"
                    logging.info(message)
                    # send_pushbullet_alert(message) # Removed for daily summary
                    trade_description = f"SOLD {sell_qty} {symbol}"
                    self.positions[symbol] -= sell_qty
                    trades_total.labels(symbol=symbol, side='sell').inc()
                    trade_executed_flag = True
                else:
                    logging.info(f"Sell signal for {symbol}, but position qty is {current_position_qty}. No trade placed.")

            if trade_executed_flag:
                current_position_qty_metric.labels(symbol=symbol).set(self.positions[symbol])
                if trade_description: # Add to daily summary list
                    self.todays_executed_trades.append(trade_description)

        except Exception as e:
            error_message = f"Error executing trade for {symbol}: {e}"
            logging.error(error_message)
            send_pushbullet_alert(error_message) # Keep for errors
            errors_total.labels(type='execute_trade').inc()

    def send_daily_summary(self):
        """Sends a daily summary of trades via Pushbullet."""
        try:
            ny_timezone = pytz.timezone('America/New_York')
            current_ny_date = datetime.now(ny_timezone).date()

            if self.last_summary_sent_date == current_ny_date:
                logging.info(f"Daily summary for {current_ny_date} already sent. Skipping.")
                return

            if not self.todays_executed_trades:
                summary_message = f"Trading Bot Summary ({current_ny_date.strftime('%Y-%m-%d')}): No trades were executed today."
                logging.info("No trades to summarize today.")
            else:
                trades_list_str = "\n".join([f"- {trade}" for trade in self.todays_executed_trades])
                summary_message = f"Trading Bot Summary ({current_ny_date.strftime('%Y-%m-%d')}): {trades_list_str}"
            
            send_pushbullet_alert(summary_message)
            logging.info(f"Sent daily summary: {summary_message}")
            self.todays_executed_trades.clear()
            self.last_summary_sent_date = current_ny_date
        except Exception as e:
            error_message = f"Error sending daily trade summary: {e}"
            logging.error(error_message)
            send_pushbullet_alert(error_message) # Alert if summary sending fails
            errors_total.labels(type='send_summary').inc()

    def run_strategy(self):
        """Main strategy execution loop for all symbols"""
        logging.info(f"Running trading strategy for symbols: {', '.join(self.symbols)}..." )
        bot_active.set(1)
        last_run_timestamp_seconds.set(time.time())
        
        for symbol in self.symbols:
            logging.info(f"Processing symbol: {symbol}")
            current_qty = 0.0 # Initialize current_qty
            try:
                # Get current position from Alpaca for the symbol
                try:
                    position = self.api.get_position(symbol)
                    current_qty = float(position.qty)
                    self.positions[symbol] = current_qty # Update local cache
                    current_position_qty_metric.labels(symbol=symbol).set(current_qty)
                except Exception as e: # Handles 'position does not exist'
                    logging.info(f"No existing position for {symbol} or error fetching: {e}")
                    current_qty = 0.0
                    self.positions[symbol] = 0.0
                    current_position_qty_metric.labels(symbol=symbol).set(0.0) # Ensure metric is set
                    if "position does not exist" not in str(e).lower(): # Don't count 'no position' as an error
                        errors_total.labels(type='get_position').inc()


                # Get historical data
                data = self.get_historical_data(symbol)
                if data.empty:
                    logging.warning(f"No data fetched for {symbol}, skipping.")
                    asset_latest_close_price_metric.labels(symbol=symbol).set(float('nan')) # No data, set to NaN
                    continue
                
                asset_latest_close_price_metric.labels(symbol=symbol).set(data.iloc[-1]['close'])

                # Calculate indicators
                data_with_indicators = self.calculate_indicators(data.copy(), symbol) # Pass symbol
                if data_with_indicators.empty or len(data_with_indicators) < 2: # Changed to 2 for generate_signals
                     logging.warning(f"Not enough data after indicator calculation for {symbol} to generate signals. Required 2, got {len(data_with_indicators)}")
                     continue
 
                # Generate signals
                signal = self.generate_signals(data_with_indicators, current_qty, symbol) # Pass symbol
 
                # Execute trades
                if signal:
                    self.execute_trade(signal, symbol, current_qty)
                else:
                    logging.info(f"No signal generated for {symbol}.")

            except Exception as e:
                logging.error(f"Major error in run_strategy for {symbol}: {e}")
                send_pushbullet_alert(f"Bot Error for {symbol}: {e}")
                errors_total.labels(type='run_strategy_main').inc()
                continue # Move to next symbol

def run_bot_job(bot_instance):
    logging.info("Scheduled job triggered.")
    if bot_instance.is_market_open():
        logging.info("Market is open. Running strategy.")
        bot_instance.run_strategy()
    else:
        logging.info("Market is closed. Skipping strategy run.")

def main():
    bot = LongTermTradingBot()

    # Start Prometheus HTTP server
    try:
        start_http_server(8000)
        logging.info("Prometheus metrics server started on port 8000.")
    except Exception as e:
        logging.error(f"Could not start Prometheus metrics server: {e}")

    # --- Scheduling --- 
    # Run trading strategy once daily at 16:30 New York time
    schedule.every().day.at("16:30", "America/New_York").do(run_bot_job, bot_instance=bot) 
    logging.info("Scheduled daily job to run at 16:30 New York time.")

    # Send daily summary (e.g., after market close NY time)
    # Ensure pytz is installed for timezone-aware scheduling
    try:
        schedule.every().day.at("16:30", "America/New_York").do(bot.send_daily_summary)
        logging.info("Scheduled daily summary to be sent at 16:30 New York time.")
    except Exception as e: # schedule library might raise error if timezone string is bad with some versions
        logging.error(f"Failed to schedule daily summary with timezone: {e}. Scheduling without timezone as fallback.")
        schedule.every().day.at("21:30").do(bot.send_daily_summary) # Fallback to UTC or server time
        logging.info("Fallback: Scheduled daily summary to be sent at 21:30 server time.")

    # Run once immediately at startup (checking market hours)
    logging.info("Running initial job execution (checking market hours)...")
    run_bot_job(bot_instance=bot)

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Bot stopped by user (KeyboardInterrupt).")
        bot_active.set(0)
    except Exception as e:
        logging.critical(f"Critical error in main: {e}")
        bot_active.set(0)
        errors_total.labels(type='main_critical').inc()
