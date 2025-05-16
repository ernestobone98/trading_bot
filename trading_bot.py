import os
import time
import logging
import schedule
import pandas as pd
import pandas_ta as ta # For technical indicators
import numpy as np
from datetime import datetime
from dotenv import load_dotenv
from alpaca_trade_api.rest import REST, TimeFrame
from notifications import send_pushbullet_alert

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    filename='trading_bot.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

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
        
        self.initial_data_fetch_limit = self.sma_long_window + 50 # Fetch enough data for longest SMA

    def get_historical_data(self, symbol):
        """Fetch historical data for analysis for a specific symbol"""
        try:
            bars = self.api.get_bars(
                symbol,
                self.timeframe,
                limit=self.initial_data_fetch_limit 
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
            return pd.DataFrame() # Return empty DataFrame on error

    def calculate_indicators(self, data):
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
            # Ensure columns exist even if calculation fails
            if f'SMA{self.sma_short_window}' not in data.columns: data[f'SMA{self.sma_short_window}'] = float('nan')
            if f'SMA{self.sma_long_window}' not in data.columns: data[f'SMA{self.sma_long_window}'] = float('nan')
            if f'MACD_{self.macd_fast_period}_{self.macd_slow_period}_{self.macd_signal_period}' not in data.columns: data[f'MACD_{self.macd_fast_period}_{self.macd_slow_period}_{self.macd_signal_period}'] = float('nan')
            if f'MACDs_{self.macd_fast_period}_{self.macd_slow_period}_{self.macd_signal_period}' not in data.columns: data[f'MACDs_{self.macd_fast_period}_{self.macd_slow_period}_{self.macd_signal_period}'] = float('nan')
            
        return data.dropna() # Drop rows with NaN values after indicator calculation

    def generate_signals(self, data, current_position_qty):
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
        # current_position_qty is already passed, so direct check is fine
        qty_to_trade = 1 # Define your position sizing logic here

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
                send_pushbullet_alert(message)
                self.positions[symbol] += qty_to_trade # Update local position tracking
                
            elif signal == 'sell' and float(current_position_qty) > 0:
                # Ensure we sell only what we have if qty_to_trade is dynamic
                # For fixed qty=1, this is fine if self.positions[symbol] reflects actual holding
                sell_qty = min(qty_to_trade, abs(float(current_position_qty)))
                if sell_qty > 0:
                    self.api.submit_order(
                        symbol=symbol,
                        qty=sell_qty, # Sell the quantity held or intended, whichever is smaller
                        side='sell',
                        type='market',
                        time_in_force='gtc'
                    )
                    message = f"SELL order placed for {sell_qty} of {symbol}"
                    logging.info(message)
                    send_pushbullet_alert(message)
                    self.positions[symbol] -= sell_qty # Update local position tracking
                else:
                    logging.info(f"Sell signal for {symbol}, but position qty is {current_position_qty}. No trade placed.")


        except Exception as e:
            error_message = f"Error executing trade for {symbol}: {e}"
            logging.error(error_message)
            send_pushbullet_alert(error_message)

    def run_strategy(self):
        """Main strategy execution loop for all symbols"""
        logging.info(f"Running trading strategy for symbols: {', '.join(self.symbols)}...")
        
        for symbol in self.symbols:
            logging.info(f"Processing symbol: {symbol}")
            try:
                # Get current position from Alpaca for the symbol
                try:
                    position = self.api.get_position(symbol)
                    current_qty = float(position.qty)
                    self.positions[symbol] = current_qty # Update local cache
                except Exception as e: # Handles 'position does not exist'
                    logging.info(f"No existing position for {symbol} or error fetching: {e}")
                    current_qty = 0.0
                    self.positions[symbol] = 0.0


                # Get historical data
                data = self.get_historical_data(symbol)
                if data.empty:
                    logging.warning(f"No data fetched for {symbol}, skipping.")
                    continue
                
                # Calculate indicators
                data_with_indicators = self.calculate_indicators(data.copy()) # Use .copy() to avoid SettingWithCopyWarning
                if data_with_indicators.empty or len(data_with_indicators) < self.sma_long_window:
                     logging.warning(f"Not enough data after indicator calculation for {symbol} to generate signals. Required {self.sma_long_window}, got {len(data_with_indicators)}")
                     continue
                
                # Generate trading signals
                signal = self.generate_signals(data_with_indicators, current_qty)
                
                # Execute trades based on signals
                if signal:
                    logging.info(f"Signal '{signal}' generated for {symbol}.")
                    self.execute_trade(signal, symbol, current_qty)
                else:
                    logging.info(f"No signal generated for {symbol}.")
                    
            except Exception as e:
                error_message = f"Strategy execution error for symbol {symbol}: {e}"
                logging.error(error_message)
                send_pushbullet_alert(error_message)
            
            time.sleep(1) # Small delay to avoid hitting API rate limits if many symbols

def main():
    bot = LongTermTradingBot() # Use the new class name
    
    # Run once at startup
    bot.run_strategy() 

    # Schedule the strategy to run daily (or adjust as needed for a "long-term" strategy)
    # For testing, hourly might be fine, but for daily data, daily checks are more appropriate.
    # schedule.every().day.at("08:00").do(bot.run_strategy) # Example: Run daily at 8 AM market time (adjust timezone)
    schedule.every().hour.do(bot.run_strategy) # Keeping hourly for now as per original
    
    logging.info(f"Trading bot started for symbols: {', '.join(bot.symbols)}...")
    send_pushbullet_alert(f"Trading bot started successfully for symbols: {', '.join(bot.symbols)}!")

    # Keep the script running
    while True:
        schedule.run_pending()
        time.sleep(60) # Check schedule every minute

if __name__ == "__main__":
    main()
