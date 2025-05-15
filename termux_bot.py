# Import libraries
import requests
import pandas as pd
import time
import datetime
import os
import math # For math.isnan, math.nan, math.max
import json # For saving/loading settings

# --- GLOBAL SETTINGS (Default values, can be changed via menu) ---
SETTINGS = {
    "symbol": "BTC",
    "currency": "USDT",
    "timeframe": "histohour", # CryptoCompare options: histominute, histohour, histoday
    "limit_data": 2000, # Number of candles to fetch for backtesting/initial run
    "poll_interval_seconds": 60, # How often to check for new candle in live mode

    "leftStrength": 50,
    "rightStrength": 150,
    "profitTargetPercentForActivation": 5.0,
    "trailingStopGapPercent": 5.0,
    "emergencySlPercent": 10.0,
    "enableSecureFib": True,
    "secureFibCheckPrice": "Close", # "Close" or "High"

    "initial_capital": 47.0,
    "default_qty_type": "percent_of_equity", # Not fully implemented, uses percent_of_equity
    "default_qty_value": 100.0, # e.g. 100% of equity
    "commission_percent": 0.44,

    "crypto_compare_api_key": "YOUR_CRYPTOCOMPARE_API_KEY" # !!! GANTI DENGAN API KEY ANDA !!!
}

CONFIG_FILE = "trade_bot_settings.json"

# --- Helper Functions ---
def send_termux_notification(title, content):
    """Sends a notification in Termux."""
    try:
        os.system(f'termux-notification -t "{title}" -c "{content}"')
        print(f"Notification: [{title}] {content}")
    except Exception as e:
        print(f"Error sending notification: {e}. (Is termux-api installed and allowed?)")

def fetch_cryptocompare_ohlcv(symbol, currency, timeframe, limit, api_key, toTs=None):
    """Fetches OHLCV data from CryptoCompare."""
    if not api_key or api_key == "YOUR_CRYPTOCOMPARE_API_KEY":
        print("ERROR: CryptoCompare API Key not set in SETTINGS.")
        return pd.DataFrame()

    url = f"https://min-api.cryptocompare.com/data/v2/{timeframe}"
    params = {
        "fsym": symbol,
        "tsym": currency,
        "limit": limit,
        "api_key": api_key
    }
    if toTs:
        params["toTs"] = toTs

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        if data["Response"] == "Error":
            print(f"CryptoCompare API Error: {data['Message']}")
            return pd.DataFrame()

        df = pd.DataFrame(data["Data"]["Data"])
        if df.empty:
            return pd.DataFrame()

        df['timestamp'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('timestamp', inplace=True)
        df.rename(columns={'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close', 'volumefrom': 'volume'}, inplace=True)
        return df[['open', 'high', 'low', 'close', 'volume']]
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from CryptoCompare: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"Error processing CryptoCompare data: {e}")
        return pd.DataFrame()

# --- Pine Script Logic Emulation ---
class PineStrategy:
    def __init__(self, settings):
        self.settings = settings
        self.df = pd.DataFrame()

        # Pine Script state variables
        self.lastSignalType = 0  # 0: none, 1: high, -1: low
        self.finalPivotHighPrice = float('nan')
        self.finalPivotLowPrice = float('nan')
        self.finalPivotHighBarIndex = float('nan') # Bar index where high occurred
        self.finalPivotLowBarIndex = float('nan') # Bar index where low occurred

        self.highPriceForFib = float('nan')
        self.highBarIndexForFib = float('nan') # Bar index of the high used for FIB

        self.activeFibLevel = float('nan')
        self.activeFibLineStartX = float('nan') # Bar index where the visual FIB line would start

        # Strategy state variables
        self.current_equity = self.settings["initial_capital"]
        self.position_size_asset = 0.0 # Quantity of asset held
        self.entry_price_custom = float('nan')
        self.highest_price_for_trailing = float('nan')
        self.trailing_tp_active_custom = False
        self.current_trailing_stop_level = float('nan')
        self.emergency_sl_level_custom = float('nan')

        self.trades = [] # To store details of simulated trades
        self.current_bar_index = -1

        # Store previous values for [1] access
        self.prev_position_size_asset = 0.0
        self.prev_opentrades_count = 0
        self.prev_closedtrades_count = 0


    def _reset_trade_state(self):
        self.entry_price_custom = float('nan')
        self.highest_price_for_trailing = float('nan')
        self.trailing_tp_active_custom = False
        self.current_trailing_stop_level = float('nan')
        self.emergency_sl_level_custom = float('nan')

    def _calculate_pivots_for_bar(self, bar_idx):
        """
        Calculates pivots based on Pine's logic.
        A pivot at index `p_idx` is confirmed `rightStrength` bars later, at `bar_idx = p_idx + rightStrength`.
        So, if we are at `bar_idx`, the potential pivot occurred at `p_idx = bar_idx - rightStrength`.
        """
        L = self.settings['leftStrength']
        R = self.settings['rightStrength']
        series_high = self.df['high']
        series_low = self.df['low']

        rawPivotHigh = float('nan')
        rawPivotLow = float('nan')
        pivot_occurred_at_idx = bar_idx - R

        if pivot_occurred_at_idx >= L: # Enough data to look left and for pivot itself
            # Check High Pivot
            is_high = True
            val_at_pivot = series_high.iloc[pivot_occurred_at_idx]
            # Look left (from pivot_occurred_at_idx - L to pivot_occurred_at_idx - 1)
            for k in range(pivot_occurred_at_idx - L, pivot_occurred_at_idx):
                if series_high.iloc[k] >= val_at_pivot: # Pine is strict with >= for left side
                    is_high = False
                    break
            if is_high:
                # Look right (from pivot_occurred_at_idx + 1 to bar_idx)
                for k in range(pivot_occurred_at_idx + 1, bar_idx + 1):
                    if series_high.iloc[k] > val_at_pivot: # Pine is > for right side
                        is_high = False
                        break
            if is_high:
                rawPivotHigh = val_at_pivot

            # Check Low Pivot
            is_low = True
            val_at_pivot = series_low.iloc[pivot_occurred_at_idx]
            # Look left
            for k in range(pivot_occurred_at_idx - L, pivot_occurred_at_idx):
                if series_low.iloc[k] <= val_at_pivot:
                    is_low = False
                    break
            if is_low:
                # Look right
                for k in range(pivot_occurred_at_idx + 1, bar_idx + 1):
                    if series_low.iloc[k] < val_at_pivot:
                        is_low = False
                        break
            if is_low:
                rawPivotLow = val_at_pivot
        
        return rawPivotHigh, rawPivotLow, pivot_occurred_at_idx


    def process_bar(self, current_bar_data, bar_idx):
        self.current_bar_index = bar_idx
        # Make current_bar_data accessible like series (e.g., current_bar_data['close'])
        # In Pine, 'high', 'low', 'close', 'open' refer to current bar.

        # --- Logika Deteksi Pivot ---
        # Note: Pine's ta.pivothigh returns the price of the pivot `rightStrength` bars *after* it's confirmed.
        # The actual pivot occurred `rightStrength` bars ago.
        rawPivotHighPrice, rawPivotLowPrice, pivot_occurred_at_idx = self._calculate_pivots_for_bar(bar_idx)

        current_finalPivotHighPrice = float('nan')
        current_finalPivotLowPrice = float('nan')

        if not math.isnan(rawPivotHighPrice) and self.lastSignalType != 1:
            self.finalPivotHighPrice = rawPivotHighPrice
            self.finalPivotHighBarIndex = pivot_occurred_at_idx # Store the actual bar index of the pivot
            self.lastSignalType = 1
            current_finalPivotHighPrice = self.finalPivotHighPrice # For alert this bar
            print(f"Bar {bar_idx} ({current_bar_data.name}): Pivot High detected at {self.finalPivotHighPrice} (occurred at bar {self.finalPivotHighBarIndex})")
            # Alert for Pivot High
            send_termux_notification("Pivot High Terdeteksi", f"PRDA StratV3: Pivot High {self.finalPivotHighPrice} pada {self.settings['symbol']}/{self.settings['currency']}")


        if not math.isnan(rawPivotLowPrice) and self.lastSignalType != -1:
            # Only register a low if a high wasn't just registered on the same raw pivot check cycle
            # or if there was no preceding high pivot at all (to start with a low)
            if math.isnan(self.finalPivotHighPrice) or self.lastSignalType == 1 : # Ensure we alternate or start with a low if no high
                self.finalPivotLowPrice = rawPivotLowPrice
                self.finalPivotLowBarIndex = pivot_occurred_at_idx # Store the actual bar index of the pivot
                self.lastSignalType = -1
                current_finalPivotLowPrice = self.finalPivotLowPrice # For alert this bar
                print(f"Bar {bar_idx} ({current_bar_data.name}): Pivot Low detected at {self.finalPivotLowPrice} (occurred at bar {self.finalPivotLowBarIndex})")
                # Alert for Pivot Low
                send_termux_notification("Pivot Low Terdeteksi", f"PRDA StratV3: Pivot Low {self.finalPivotLowPrice} pada {self.settings['symbol']}/{self.settings['currency']}")


        # --- Logika Konfirmasi FIB 0.5 Dinamis ---
        # Kondisi 1: HIGH baru terkonfirmasi (this means self.finalPivotHighPrice was just set)
        if not math.isnan(current_finalPivotHighPrice): # Use the value found on *this* bar's processing
            self.highPriceForFib = current_finalPivotHighPrice
            self.highBarIndexForFib = self.finalPivotHighBarIndex # Actual bar where the high occurred
            print(f"Bar {bar_idx}: High registered for FIB: {self.highPriceForFib} from bar {self.highBarIndexForFib}")
            # Reset active FIB if any, as new High is primary
            self.activeFibLevel = float('nan')
            self.activeFibLineStartX = float('nan')


        # Kondisi 2: LOW baru terkonfirmasi (this means self.finalPivotLowPrice was just set)
        if not math.isnan(current_finalPivotLowPrice): # Use the value found on *this* bar's processing
            if not math.isnan(self.highPriceForFib) and not math.isnan(self.highBarIndexForFib):
                currentLowPrice = current_finalPivotLowPrice
                currentLowBarIndex = self.finalPivotLowBarIndex # Actual bar where the low occurred

                if currentLowBarIndex > self.highBarIndexForFib: # Ensure LOW is after HIGH
                    calculatedFibLevel = (self.highPriceForFib + currentLowPrice) / 2.0
                    isFibLate = False

                    if self.settings['enableSecureFib']:
                        priceToCheckVal = current_bar_data[self.settings['secureFibCheckPrice'].lower()]
                        if priceToCheckVal > calculatedFibLevel:
                            isFibLate = True
                    
                    if isFibLate:
                        print(f"Bar {bar_idx}: Late FIB detected at {calculatedFibLevel}. Ignored.")
                        self.activeFibLevel = float('nan')
                        self.activeFibLineStartX = float('nan')
                    else:
                        self.activeFibLevel = calculatedFibLevel
                        self.activeFibLineStartX = currentLowBarIndex # Visual line starts from the low confirmation
                        print(f"Bar {bar_idx}: Active FIB level set: {self.activeFibLevel} (High: {self.highPriceForFib} @bar{self.highBarIndexForFib}, Low: {currentLowPrice} @bar{currentLowBarIndex})")
                    
                    # HIGH this has been processed (FIB valid or late), reset for new HIGH
                    self.highPriceForFib = float('nan')
                    self.highBarIndexForFib = float('nan')
            # else:
                # print(f"Bar {bar_idx}: Low confirmed, but no preceding High for FIB.")

        # Kondisi 3: Cek setiap bar apakah active FIB memicu entry
        if not math.isnan(self.activeFibLevel) and not math.isnan(self.activeFibLineStartX):
            isBullishCandle = current_bar_data['close'] > current_bar_data['open']
            isClosedAboveFib = current_bar_data['close'] > self.activeFibLevel

            if isBullishCandle and isClosedAboveFib:
                if self.position_size_asset == 0 : # strategy.position_size == 0
                    self._strategy_entry("Buy", current_bar_data['close'], current_bar_data.name) # .name is timestamp
                
                # FIB used for entry, reset it
                print(f"Bar {bar_idx}: FIB level {self.activeFibLevel} crossed. Resetting active FIB.")
                self.activeFibLevel = float('nan')
                self.activeFibLineStartX = float('nan')
        
        # --- Logika Manajemen Posisi Strategi ---
        # (Must run every bar if in position)

        # Saat posisi baru saja dimasuki (check based on prev_position_size)
        if self.position_size_asset > 0 and self.prev_position_size_asset == 0:
            # This block runs ONCE per new position, on the bar of entry.
            # self.entry_price_custom is set by _strategy_entry
            self.highest_price_for_trailing = self.entry_price_custom # Start with entry price
            self.trailing_tp_active_custom = False
            self.current_trailing_stop_level = float('nan')
            self.emergency_sl_level_custom = self.entry_price_custom * (1 - self.settings['emergencySlPercent'] / 100.0)
            
            print(f"Bar {bar_idx}: BUY ENTRY @ {self.entry_price_custom:.5f}. Emerg SL: {self.emergency_sl_level_custom:.5f}")
            # Alert is handled by _strategy_entry

        # Jika sedang dalam posisi (long)
        if self.position_size_asset > 0:
            self.highest_price_for_trailing = max(self.highest_price_for_trailing if not math.isnan(self.highest_price_for_trailing) else current_bar_data['high'], current_bar_data['high'])

            if not self.trailing_tp_active_custom and not math.isnan(self.entry_price_custom):
                profitPercent = ((self.highest_price_for_trailing - self.entry_price_custom) / self.entry_price_custom) * 100.0
                if profitPercent >= self.settings['profitTargetPercentForActivation']:
                    self.trailing_tp_active_custom = True
                    print(f"Bar {bar_idx}: Trailing TP Activated. High: {self.highest_price_for_trailing}")
            
            if self.trailing_tp_active_custom and not math.isnan(self.highest_price_for_trailing):
                potentialNewStopPrice = self.highest_price_for_trailing * (1 - (self.settings['trailingStopGapPercent'] / 100.0))
                if math.isnan(self.current_trailing_stop_level) or potentialNewStopPrice > self.current_trailing_stop_level:
                    self.current_trailing_stop_level = potentialNewStopPrice
                    # print(f"Bar {bar_idx}: Trailing TP updated to {self.current_trailing_stop_level}") # Can be noisy
            
            final_stop_for_exit = self.emergency_sl_level_custom
            exit_comment = "Emergency SL"
            if self.trailing_tp_active_custom and not math.isnan(self.current_trailing_stop_level):
                if self.current_trailing_stop_level > self.emergency_sl_level_custom: # Trailing stop is more favorable
                    final_stop_for_exit = self.current_trailing_stop_level
                    exit_comment = "Trailing Stop"
            
            # Check if stop loss is hit
            # Pine's strategy.exit(stop=...) triggers if low <= stop_level
            if not math.isnan(final_stop_for_exit) and current_bar_data['low'] <= final_stop_for_exit:
                # Exit price for stop is the stop_level itself
                self._strategy_exit("ExitOrder", final_stop_for_exit, exit_comment, current_bar_data.name)


        # Saat posisi baru saja ditutup
        if self.position_size_asset == 0 and self.prev_position_size_asset > 0:
            print(f"Bar {bar_idx}: Position Closed (Logic after exit call). Resetting trade state.")
            # Alert is handled by _strategy_exit
            self._reset_trade_state() # Reset all trade-specific states

        # Update previous state for next bar
        self.prev_position_size_asset = self.position_size_asset
        # opentrades and closedtrades count update is handled in _strategy_entry/_exit


    def _strategy_entry(self, id_str, price, timestamp):
        """ Simulates strategy.entry """
        if self.position_size_asset > 0: # Already in position
            print(f"Warning: Entry requested for {id_str} but already in position.")
            return

        qty_to_buy_asset = 0
        cost_of_trade = 0

        if self.settings['default_qty_type'] == "percent_of_equity":
            investment_amount = self.current_equity * (self.settings['default_qty_value'] / 100.0)
            if price > 0:
                qty_to_buy_asset = investment_amount / price
            else:
                print("Error: Entry price is zero, cannot calculate quantity.")
                return
        else: # Add other types like strategy.fixed if needed
            print(f"Unsupported default_qty_type: {self.settings['default_qty_type']}")
            return
        
        cost_of_trade = qty_to_buy_asset * price
        commission_cost = cost_of_trade * (self.settings['commission_percent'] / 100.0)

        # Update equity: Subtract commission. The asset value is now part of portfolio.
        self.current_equity -= commission_cost 
        
        self.position_size_asset = qty_to_buy_asset
        self.entry_price_custom = price # This is strategy.opentrades.entry_price(...)

        current_opentrades_count = sum(1 for t in self.trades if t.get('status') == 'OPEN') + 1

        trade_info = {
            "id": id_str,
            "type": "BUY",
            "entry_price": price,
            "qty": qty_to_buy_asset,
            "cost": cost_of_trade,
            "commission_entry": commission_cost,
            "timestamp_entry": timestamp,
            "status": "OPEN"
        }
        self.trades.append(trade_info)
        
        print(f"SIMULATE ENTRY: {id_str} - Qty: {qty_to_buy_asset:.8f} {self.settings['symbol']} @ {price:.5f}. Cost: {cost_of_trade:.2f} {self.settings['currency']}. Commission: {commission_cost:.3f}. Equity: {self.current_equity:.2f}")
        
        # Alert for PRDA Buy Entry
        # strategy.opentrades > strategy.opentrades[1]
        if current_opentrades_count > self.prev_opentrades_count:
             send_termux_notification("PRDA Buy Entry", f"PRDA StratV3: BUY {qty_to_buy_asset:.4f} @ {price:.5f} on {self.settings['symbol']}/{self.settings['currency']}")
        self.prev_opentrades_count = current_opentrades_count


    def _strategy_exit(self, id_str, price, comment, timestamp):
        """ Simulates strategy.exit """
        if self.position_size_asset == 0:
            print(f"Warning: Exit requested for {id_str} but not in position.")
            return

        qty_to_sell_asset = self.position_size_asset # Sell all
        proceeds_from_sale = qty_to_sell_asset * price
        commission_cost = proceeds_from_sale * (self.settings['commission_percent'] / 100.0)

        # Find the open trade to close it
        open_trade_index = -1
        for i, trade in reversed(list(enumerate(self.trades))):
            if trade.get('status') == 'OPEN' and trade.get('type') == 'BUY': # Assuming only BUY entries for now
                open_trade_index = i
                break
        
        if open_trade_index == -1:
            print("Error: Could not find open trade to close.")
            self._reset_trade_state() # Critical to reset state
            self.position_size_asset = 0
            return

        # Calculate PnL for this trade
        entry_cost_of_asset_sold = self.trades[open_trade_index]['cost']
        entry_commission_for_asset_sold = self.trades[open_trade_index]['commission_entry']

        # Gross PnL = (Sell Price - Buy Price) * Qty
        # Net PnL = Gross PnL - Entry Commission - Exit Commission
        pnl_trade = (price * qty_to_sell_asset) - (self.trades[open_trade_index]['entry_price'] * qty_to_sell_asset) \
                    - entry_commission_for_asset_sold - commission_cost

        # Update equity: Add proceeds, subtract commission.
        self.current_equity += (proceeds_from_sale - commission_cost - entry_cost_of_asset_sold)
        # Simplified: self.current_equity += pnl_trade

        self.trades[open_trade_index].update({
            "exit_price": price,
            "proceeds": proceeds_from_sale,
            "commission_exit": commission_cost,
            "timestamp_exit": timestamp,
            "status": "CLOSED",
            "pnl": pnl_trade,
            "comment": comment
        })

        print(f"SIMULATE EXIT: {id_str} ({comment}) - Qty: {qty_to_sell_asset:.8f} {self.settings['symbol']} @ {price:.5f}. Proceeds: {proceeds_from_sale:.2f} {self.settings['currency']}. Commission: {commission_cost:.3f}. PnL: {pnl_trade:.2f}. Equity: {self.current_equity:.2f}")
        
        self.position_size_asset = 0
        self._reset_trade_state() # Important to reset after exit

        current_closedtrades_count = sum(1 for t in self.trades if t.get('status') == 'CLOSED')
        # Alert for PRDA Trade Closed
        # strategy.closedtrades > strategy.closedtrades[1]
        if current_closedtrades_count > self.prev_closedtrades_count:
            send_termux_notification("PRDA Trade Closed", f"PRDA StratV3: Trade Closed on {self.settings['symbol']}/{self.settings['currency']}. PnL: {pnl_trade:.2f}. Exit by: {comment}")
        self.prev_closedtrades_count = current_closedtrades_count


    def run_backtest(self, historical_df):
        print("\n--- Starting Backtest ---")
        if historical_df.empty:
            print("No data to backtest.")
            return

        self.df = historical_df.copy()
        # Reset all states for a fresh backtest
        self.__init__(self.settings) # Re-initialize to reset states
        self.df = historical_df.copy() # Re-assign df after re-init

        # Ensure DataFrame index is DatetimeIndex and sorted
        if not isinstance(self.df.index, pd.DatetimeIndex):
            self.df.index = pd.to_datetime(self.df.index)
        self.df.sort_index(inplace=True)

        # Pine Script typically needs some bars to warm up indicators like pivots.
        # The pivot calculation itself handles the necessary lookback window.
        # R_strength = self.settings['rightStrength']
        # L_strength = self.settings['leftStrength']
        # warmup_period = R_strength + L_strength # Minimum bars for first pivot calculation
        warmup_period = self.settings['rightStrength'] # Pivot is confirmed R bars later
        
        if len(self.df) < warmup_period:
            print(f"Not enough data for backtest. Need at least {warmup_period} bars, have {len(self.df)}")
            return

        for i in range(len(self.df)):
            if i < warmup_period: # Skip bars needed for indicator warmup (pivot confirmation)
                # Still need to update prev_ values for the first real processing bar
                self.prev_position_size_asset = self.position_size_asset
                self.prev_opentrades_count = sum(1 for t in self.trades if t.get('status') == 'OPEN')
                self.prev_closedtrades_count = sum(1 for t in self.trades if t.get('status') == 'CLOSED')
                continue
            
            current_bar_series = self.df.iloc[i]
            self.process_bar(current_bar_series, i)
        
        self.print_backtest_summary()


    def print_backtest_summary(self):
        print("\n--- Backtest Summary ---")
        print(f"Initial Capital: {self.settings['initial_capital']:.2f} {self.settings['currency']}")
        print(f"Final Equity: {self.current_equity:.2f} {self.settings['currency']}")
        
        total_pnl = self.current_equity - self.settings['initial_capital']
        percent_return = (total_pnl / self.settings['initial_capital']) * 100 if self.settings['initial_capital'] > 0 else 0
        print(f"Total Net PnL: {total_pnl:.2f} {self.settings['currency']} ({percent_return:.2f}%)")

        closed_trades = [t for t in self.trades if t.get('status') == 'CLOSED']
        num_trades = len(closed_trades)
        print(f"Total Trades: {num_trades}")

        if num_trades > 0:
            winning_trades = sum(1 for t in closed_trades if t['pnl'] > 0)
            losing_trades = num_trades - winning_trades
            win_rate = (winning_trades / num_trades) * 100 if num_trades > 0 else 0
            print(f"Winning Trades: {winning_trades}")
            print(f"Losing Trades: {losing_trades}")
            print(f"Win Rate: {win_rate:.2f}%")

            total_gross_pnl = sum(t['pnl'] for t in closed_trades) # pnl already net of commissions for the trade
            avg_pnl_per_trade = total_gross_pnl / num_trades
            print(f"Average PnL per Trade: {avg_pnl_per_trade:.2f} {self.settings['currency']}")
            
            total_commissions = sum(t.get('commission_entry',0) + t.get('commission_exit',0) for t in closed_trades)
            print(f"Total Commissions Paid: {total_commissions:.3f} {self.settings['currency']}")
        
        if not closed_trades:
            print("No trades were executed during the backtest.")
        # else:
        #     print("\nTrade Log:")
        #     for i, trade in enumerate(closed_trades):
        #         print(f"  Trade {i+1}: Entry @ {trade['entry_price']:.5f} on {trade['timestamp_entry']}")
        #         print(f"             Exit @ {trade['exit_price']:.5f} on {trade['timestamp_exit']} ({trade['comment']})")
        #         print(f"             PnL: {trade['pnl']:.2f}, Qty: {trade['qty']:.4f}")
        print("--- End of Backtest Summary ---")

    def run_live_simulation(self):
        print("\n--- Starting Live Simulation (Ctrl+C to stop) ---")
        print(f"Monitoring {self.settings['symbol']}/{self.settings['currency']} on {self.settings['timeframe']}")
        
        # Initial data load (fetch more than needed for pivot calculations)
        required_bars_for_init = self.settings['leftStrength'] + self.settings['rightStrength'] + 50 # some buffer
        historical_df = fetch_cryptocompare_ohlcv(
            self.settings['symbol'], self.settings['currency'],
            self.settings['timeframe'], required_bars_for_init, self.settings['crypto_compare_api_key']
        )

        if historical_df.empty or len(historical_df) < self.settings['rightStrength']: # Need at least R bars for first pivot confirmation
            print("Not enough initial data to start live simulation. Exiting.")
            return

        self.df = historical_df.copy()
        self.__init__(self.settings) # Reset state
        self.df = historical_df.copy() # Assign df again

        # Process initial historical data to set up indicator states
        # Pine Script would effectively do this. We need enough history for pivots to form.
        print(f"Processing {len(self.df)} initial historical bars...")
        warmup_period = self.settings['rightStrength'] 
        for i in range(len(self.df)):
            if i < warmup_period: # Skip bars needed for indicator warmup (pivot confirmation)
                 # Still need to update prev_ values for the first real processing bar
                self.prev_position_size_asset = self.position_size_asset
                self.prev_opentrades_count = sum(1 for t in self.trades if t.get('status') == 'OPEN')
                self.prev_closedtrades_count = sum(1 for t in self.trades if t.get('status') == 'CLOSED')
                continue
            current_bar_series = self.df.iloc[i]
            self.process_bar(current_bar_series, i) # Process to build up state
        
        print("Initial data processed. Starting real-time candle fetching simulation.")

        last_fetched_timestamp = self.df.index[-1]

        try:
            while True:
                time.sleep(self.settings['poll_interval_seconds'])
                
                # Fetch the latest 2 candles to see if a new one has closed
                # Using toTs=last_fetched_timestamp.timestamp() might miss the current forming candle.
                # Fetching a small number like 5 candles and checking the last one is safer.
                latest_candles_df = fetch_cryptocompare_ohlcv(
                    self.settings['symbol'], self.settings['currency'],
                    self.settings['timeframe'], 5, self.settings['crypto_compare_api_key']
                )

                if not latest_candles_df.empty:
                    new_candle = latest_candles_df.iloc[-1] # Potentially the newest closed candle
                    new_candle_timestamp = latest_candles_df.index[-1]

                    # Check if it's actually a new, closed candle
                    if new_candle_timestamp > last_fetched_timestamp:
                        print(f"\nNew candle detected: {new_candle_timestamp}")
                        # Append to our main DataFrame and process
                        # Ensure no duplicate index by dropping if it exists then appending
                        if new_candle_timestamp in self.df.index:
                            self.df = self.df.drop(new_candle_timestamp)
                        
                        # Create a new DataFrame for the single new candle to ensure correct structure
                        new_row_df = pd.DataFrame([new_candle], index=[new_candle_timestamp])
                        self.df = pd.concat([self.df, new_row_df])
                        
                        last_fetched_timestamp = new_candle_timestamp
                        
                        # Process the new bar (it's now the last row of self.df)
                        current_bar_idx = len(self.df) - 1
                        self.process_bar(self.df.iloc[current_bar_idx], current_bar_idx)
                        
                        print(f"Processed bar {current_bar_idx} ({new_candle_timestamp}). Waiting for next candle...")
                        print(f"Current Equity: {self.current_equity:.2f}, Position Size: {self.position_size_asset:.4f} {self.settings['symbol']}")
                        if self.position_size_asset > 0:
                            print(f"  Entry: {self.entry_price_custom:.5f}, Emerg SL: {self.emergency_sl_level_custom:.5f}, Trail SL: {self.current_trailing_stop_level if not math.isnan(self.current_trailing_stop_level) else 'N/A'}")

                    else:
                        # print(f". {datetime.datetime.now()}", end='', flush=True) # heartbeat
                        pass
                else:
                    print("Failed to fetch latest candles.")

        except KeyboardInterrupt:
            print("\nLive simulation stopped by user.")
        finally:
            self.print_backtest_summary() # Show summary of live simulated trades

# --- Settings Management ---
def load_settings():
    global SETTINGS
    try:
        with open(CONFIG_FILE, 'r') as f:
            SETTINGS.update(json.load(f))
        print(f"Settings loaded from {CONFIG_FILE}")
    except FileNotFoundError:
        print(f"No settings file found at {CONFIG_FILE}. Using defaults.")
    except json.JSONDecodeError:
        print(f"Error decoding {CONFIG_FILE}. Using defaults.")

def save_settings():
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(SETTINGS, f, indent=4)
        print(f"Settings saved to {CONFIG_FILE}")
    except Exception as e:
        print(f"Error saving settings: {e}")

def display_settings():
    print("\n--- Current Settings ---")
    for key, value in SETTINGS.items():
        if key == "crypto_compare_api_key" and value and value != "YOUR_CRYPTOCOMPARE_API_KEY":
            print(f"{key}: {'*' * (len(value)-4) + value[-4:]}")
        else:
            print(f"{key}: {value}")
    print("---")

def change_settings():
    display_settings()
    while True:
        key_to_change = input("Enter setting key to change (or 'done' to finish): ").strip()
        if key_to_change.lower() == 'done':
            break
        if key_to_change not in SETTINGS:
            print("Invalid setting key.")
            continue

        current_value = SETTINGS[key_to_change]
        new_value_str = input(f"Enter new value for '{key_to_change}' (current: {current_value}): ").strip()
        
        try:
            # Try to convert to the type of the original setting
            original_type = type(current_value)
            if original_type == bool:
                if new_value_str.lower() in ['true', 't', 'yes', 'y', '1']:
                    new_value = True
                elif new_value_str.lower() in ['false', 'f', 'no', 'n', '0']:
                    new_value = False
                else:
                    raise ValueError("Invalid boolean value")
            else:
                new_value = original_type(new_value_str)
            
            SETTINGS[key_to_change] = new_value
            print(f"'{key_to_change}' updated to {new_value}")
        except ValueError:
            print(f"Invalid value type for '{key_to_change}'. Expected {original_type.__name__}.")
        except Exception as e:
            print(f"An error occurred: {e}")
    save_settings()


# --- Main Menu ---
def main_menu():
    load_settings()
    strategy_instance = PineStrategy(SETTINGS)

    while True:
        print("\n--- Termux Pine Strategy Bot ---")
        print("1. Start Live Simulation")
        print("2. Run Backtest")
        print("3. Settings")
        print("4. Exit")
        choice = input("Enter your choice: ").strip()

        if choice == '1':
            strategy_instance.settings = SETTINGS # Ensure strategy uses current settings
            strategy_instance.run_live_simulation()
        elif choice == '2':
            print("Fetching data for backtest...")
            historical_df = fetch_cryptocompare_ohlcv(
                SETTINGS['symbol'], SETTINGS['currency'],
                SETTINGS['timeframe'], SETTINGS['limit_data'], SETTINGS['crypto_compare_api_key']
            )
            if not historical_df.empty:
                strategy_instance.settings = SETTINGS # Ensure strategy uses current settings
                strategy_instance.run_backtest(historical_df)
            else:
                print("Could not fetch data for backtest.")
        elif choice == '3':
            change_settings()
        elif choice == '4':
            print("Exiting.")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main_menu()
