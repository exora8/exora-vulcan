import requests
import pandas as pd
import time
import json
import os
import logging
from datetime import datetime
import smtplib # Untuk email
from email.mime.text import MIMEText # Untuk email
import sys # Untuk cek platform (beep)

# --- ANSI COLOR CODES ---
class AnsiColors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    ORANGE = '\033[93m' # Warning / Late FIB
    RED = '\033[91m'    # Error / SL
    ENDC = '\033[0m'    # Reset
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    CYAN = '\033[96m'

# --- KONFIGURASI LOGGING ---
# Kita akan handle warna langsung di print/logging calls untuk konsol
# File log tidak akan punya kode ANSI
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_formatter = logging.Formatter(f'%(asctime)s - {AnsiColors.BOLD}%(levelname)s{AnsiColors.ENDC} - %(message)s') # Pesan akan diwarnai manual

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Handler untuk file
fh = logging.FileHandler("trading_log.txt", mode='a')
fh.setFormatter(file_formatter)
logger.addHandler(fh)

# Handler untuk konsol
ch = logging.StreamHandler()
ch.setFormatter(console_formatter) # Pesan akan diwarnai manual saat logging.info dipanggil
logger.addHandler(ch)


SETTINGS_FILE = "settings.json"
CRYPTOCOMPARE_MAX_LIMIT = 1999

# --- FUNGSI BEEP ---
def play_notification_sound():
    try:
        if sys.platform == "win32":
            import winsound
            winsound.Beep(1000, 500) # Frekuensi 1000 Hz, Durasi 500 ms
        else: # Linux, macOS
            print('\a', end='', flush=True) # Karakter BEL
            time.sleep(0.2) # Beri sedikit jeda agar terdengar
            print('\a', end='', flush=True)
    except Exception as e:
        logging.warning(f"Tidak bisa memainkan suara notifikasi: {e}")

# --- FUNGSI EMAIL ---
def send_email_notification(subject, body_text, settings):
    if not settings.get("enable_email_notifications", False):
        return

    sender_email = settings.get("email_sender_address")
    sender_password = settings.get("email_sender_app_password") # Gunakan App Password!
    receiver_email = settings.get("email_receiver_address")

    if not all([sender_email, sender_password, receiver_email]):
        logging.warning("Konfigurasi email tidak lengkap. Notifikasi email dilewati.")
        return

    msg = MIMEText(body_text)
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = receiver_email

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp_server: # Port SSL untuk Gmail
            smtp_server.login(sender_email, sender_password)
            smtp_server.sendmail(sender_email, receiver_email, msg.as_string())
        logging.info(f"{AnsiColors.CYAN}Notifikasi email berhasil dikirim ke {receiver_email}{AnsiColors.ENDC}")
    except Exception as e:
        logging.error(f"{AnsiColors.RED}Gagal mengirim email notifikasi: {e}{AnsiColors.ENDC}")


# --- FUNGSI PENGATURAN ---
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                logging.error("Error membaca settings.json. Menggunakan default.")
    return {
        "api_key": "YOUR_API_KEY_HERE", "symbol": "BTC", "currency": "USD", "exchange": "CCCAGG",
        "timeframe": "hour", "refresh_interval_seconds": 60,
        "left_strength": 50, "right_strength": 150,
        "profit_target_percent_activation": 5.0, "trailing_stop_gap_percent": 5.0,
        "emergency_sl_percent": 10.0, "enable_secure_fib": True, "secure_fib_check_price": "Close",
        "enable_email_notifications": False, # Email nonaktif by default
        "email_sender_address": "pengirim@gmail.com",
        "email_sender_app_password": "xxxx xxxx xxxx xxxx", # HARUS APP PASSWORD
        "email_receiver_address": "penerima@example.com"
    }

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=4)
    logging.info(f"{AnsiColors.CYAN}Pengaturan disimpan ke settings.json{AnsiColors.ENDC}")

def settings_menu(current_settings):
    print(f"\n{AnsiColors.HEADER}--- Menu Pengaturan ---{AnsiColors.ENDC}")
    new_settings = current_settings.copy()
    try:
        # ... (input API Key, Symbol, Currency, Exchange, Timeframe, Refresh Interval sama) ...
        new_settings["api_key"] = input(f"API Key CryptoCompare [{current_settings.get('api_key','')}]: ") or current_settings.get('api_key','')
        new_settings["symbol"] = (input(f"Simbol Crypto Dasar (misal BTC) [{current_settings.get('symbol','BTC')}]: ") or current_settings.get('symbol','BTC')).upper()
        new_settings["currency"] = (input(f"Simbol Mata Uang Quote (misal USDT, USD) [{current_settings.get('currency','USD')}]: ") or current_settings.get('currency','USD')).upper()
        new_settings["exchange"] = (input(f"Exchange (misal Binance, Coinbase, atau CCCAGG untuk agregat) [{current_settings.get('exchange','CCCAGG')}]: ") or current_settings.get('exchange','CCCAGG'))
        tf_input = (input(f"Timeframe (minute/hour/day) [{current_settings.get('timeframe','hour')}]: ") or current_settings.get('timeframe','hour')).lower()
        if tf_input in ['minute', 'hour', 'day']: new_settings["timeframe"] = tf_input
        else: print("Timeframe tidak valid."); new_settings["timeframe"] = current_settings.get('timeframe','hour')
        new_settings["refresh_interval_seconds"] = int(input(f"Interval Refresh (detik) [{current_settings.get('refresh_interval_seconds',60)}]: ") or current_settings.get('refresh_interval_seconds',60))

        print(f"\n{AnsiColors.HEADER}-- Parameter Pivot --{AnsiColors.ENDC}")
        new_settings["left_strength"] = int(input(f"Left Strength [{current_settings.get('left_strength',50)}]: ") or current_settings.get('left_strength',50))
        new_settings["right_strength"] = int(input(f"Right Strength [{current_settings.get('right_strength',150)}]: ") or current_settings.get('right_strength',150))

        print(f"\n{AnsiColors.HEADER}-- Parameter Trading --{AnsiColors.ENDC}")
        new_settings["profit_target_percent_activation"] = float(input(f"Profit % Aktivasi Trailing TP [{current_settings.get('profit_target_percent_activation',5.0)}]: ") or current_settings.get('profit_target_percent_activation',5.0))
        new_settings["trailing_stop_gap_percent"] = float(input(f"Gap Trailing TP % [{current_settings.get('trailing_stop_gap_percent',5.0)}]: ") or current_settings.get('trailing_stop_gap_percent',5.0))
        new_settings["emergency_sl_percent"] = float(input(f"Emergency SL % [{current_settings.get('emergency_sl_percent',10.0)}]: ") or current_settings.get('emergency_sl_percent',10.0))
        
        print(f"\n{AnsiColors.HEADER}-- Fitur Secure FIB --{AnsiColors.ENDC}")
        enable_sf_input = input(f"Aktifkan Secure FIB? (true/false) [{current_settings.get('enable_secure_fib',True)}]: ").lower()
        new_settings["enable_secure_fib"] = True if enable_sf_input == 'true' else (False if enable_sf_input == 'false' else current_settings.get('enable_secure_fib',True))
        secure_fib_price_input = (input(f"Harga Cek Secure FIB (Close/High) [{current_settings.get('secure_fib_check_price','Close')}]: ") or current_settings.get('secure_fib_check_price','Close')).capitalize()
        if secure_fib_price_input in ["Close", "High"]: new_settings["secure_fib_check_price"] = secure_fib_price_input
        else: print("Pilihan harga Secure FIB tidak valid."); new_settings["secure_fib_check_price"] = current_settings.get('secure_fib_check_price','Close')

        print(f"\n{AnsiColors.HEADER}-- Notifikasi Email (Gmail) --{AnsiColors.ENDC}")
        email_enable_input = input(f"Aktifkan Notifikasi Email? (true/false) [{current_settings.get('enable_email_notifications',False)}]: ").lower()
        new_settings["enable_email_notifications"] = True if email_enable_input == 'true' else (False if email_enable_input == 'false' else current_settings.get('enable_email_notifications',False))
        new_settings["email_sender_address"] = input(f"Email Pengirim (Gmail) [{current_settings.get('email_sender_address','')}]: ") or current_settings.get('email_sender_address','')
        new_settings["email_sender_app_password"] = input(f"App Password Email Pengirim [{current_settings.get('email_sender_app_password','')}]: ") or current_settings.get('email_sender_app_password','')
        new_settings["email_receiver_address"] = input(f"Email Penerima [{current_settings.get('email_receiver_address','')}]: ") or current_settings.get('email_receiver_address','')
        
        save_settings(new_settings)
        return new_settings
    except ValueError:
        print(f"{AnsiColors.RED}Input tidak valid. Pengaturan tidak diubah.{AnsiColors.ENDC}")
        return current_settings

# --- FUNGSI PENGAMBILAN DATA --- (fetch_candles sama seperti versi sebelumnya)
def fetch_candles(symbol, currency, limit, exchange_name, api_key, timeframe="hour"):
    if timeframe == "minute": api_endpoint = "histominute"
    elif timeframe == "day": api_endpoint = "histoday"
    else: api_endpoint = "histohour"
    url = f"https://min-api.cryptocompare.com/data/v2/{api_endpoint}"
    params = {"fsym": symbol, "tsym": currency, "limit": limit, "api_key": api_key}
    if exchange_name and exchange_name.upper() != "CCCAGG": params["e"] = exchange_name
    try:
        logging.debug(f"Fetching data from: {url} with params: {params}")
        response = requests.get(url, params=params)
        response.raise_for_status() 
        data = response.json()
        if data.get('Response') == 'Error':
            logging.error(f"{AnsiColors.RED}API Error CryptoCompare: {data.get('Message', 'N/A')}{AnsiColors.ENDC} (Params: fsym={symbol}, tsym={currency}, exch={exchange_name or 'CCCAGG'}, lim={limit}, tf={timeframe})")
            return pd.DataFrame()
        if 'Data' not in data or 'Data' not in data['Data']:
            logging.error(f"{AnsiColors.RED}Format data API tidak sesuai.{AnsiColors.ENDC} Respons: {data}")
            return pd.DataFrame()
        df = pd.DataFrame(data['Data']['Data'])
        if df.empty: logging.info("Tidak ada data candle dari API."); return pd.DataFrame()
        df['timestamp'] = pd.to_datetime(df['time'], unit='s')
        df = df.set_index('timestamp')
        expected_cols = ['open', 'high', 'low', 'close', 'volumefrom']
        for col in expected_cols:
            if col not in df.columns:
                logging.warning(f"Kolom '{col}' tidak ditemukan! Mengisi dengan NA."); df[col] = pd.NA
        df = df[expected_cols]; df.rename(columns={'volumefrom': 'volume'}, inplace=True)
        return df
    except requests.exceptions.RequestException as e: logging.error(f"{AnsiColors.RED}Kesalahan koneksi: {e}{AnsiColors.ENDC}"); return pd.DataFrame()
    except Exception as e: logging.error(f"{AnsiColors.RED}Error fetch_candles: {e}{AnsiColors.ENDC}"); return pd.DataFrame()


# --- LOGIKA STRATEGI --- (strategy_state dan find_pivots sama)
strategy_state = {
    "last_signal_type": 0, "final_pivot_high_price_confirmed": None, "final_pivot_low_price_confirmed": None,
    "high_price_for_fib": None, "high_bar_index_for_fib": None, "active_fib_level": None,
    "active_fib_line_start_index": None, "entry_price_custom": None, "highest_price_for_trailing": None,
    "trailing_tp_active_custom": False, "current_trailing_stop_level": None,
    "emergency_sl_level_custom": None, "position_size": 0,
}
def find_pivots(series_list, left_strength, right_strength, is_high=True):
    pivots = [None] * len(series_list)
    if len(series_list) < left_strength + right_strength + 1: return pivots
    for i in range(left_strength, len(series_list) - right_strength):
        is_pivot = True
        for j in range(1, left_strength + 1):
            if is_high:
                if series_list[i] <= series_list[i-j]: is_pivot = False; break
            else:
                if series_list[i] >= series_list[i-j]: is_pivot = False; break
        if not is_pivot: continue
        for j in range(1, right_strength + 1):
            if is_high:
                if series_list[i] < series_list[i+j]: is_pivot = False; break 
            else:
                if series_list[i] > series_list[i+j]: is_pivot = False; break 
        if is_pivot: pivots[i] = series_list[i] 
    return pivots

def run_strategy_logic(df, settings):
    global strategy_state 
    # ... (reset state & setup awal sama) ...
    strategy_state["final_pivot_high_price_confirmed"] = None
    strategy_state["final_pivot_low_price_confirmed"] = None
    left_strength = settings['left_strength']
    right_strength = settings['right_strength']
    required_cols = ['high', 'low', 'open', 'close']
    if df.empty or not all(col in df.columns for col in required_cols):
        logging.warning(f"{AnsiColors.ORANGE}DataFrame kosong/kurang kolom di run_strategy_logic.{AnsiColors.ENDC}")
        return

    raw_pivot_highs = find_pivots(df['high'].tolist(), left_strength, right_strength, is_high=True)
    raw_pivot_lows  = find_pivots(df['low'].tolist(),  left_strength, right_strength, is_high=False)
    current_bar_index_in_df = len(df) - 1 
    if current_bar_index_in_df < 0 : return

    idx_pivot_event_high = current_bar_index_in_df - right_strength
    raw_pivot_high_price_at_event = None
    if idx_pivot_event_high >= 0 and idx_pivot_event_high < len(raw_pivot_highs):
        raw_pivot_high_price_at_event = raw_pivot_highs[idx_pivot_event_high]

    idx_pivot_event_low = current_bar_index_in_df - right_strength
    raw_pivot_low_price_at_event = None
    if idx_pivot_event_low >= 0 and idx_pivot_event_low < len(raw_pivot_lows):
        raw_pivot_low_price_at_event = raw_pivot_lows[idx_pivot_event_low]

    if raw_pivot_high_price_at_event is not None and strategy_state["last_signal_type"] != 1:
        strategy_state["final_pivot_high_price_confirmed"] = raw_pivot_high_price_at_event
        strategy_state["last_signal_type"] = 1
        logging.info(f"{AnsiColors.CYAN}PIVOT HIGH: {strategy_state['final_pivot_high_price_confirmed']:.5f} @ {df.index[idx_pivot_event_high].strftime('%Y-%m-%d %H:%M')}{AnsiColors.ENDC}")
        
    if raw_pivot_low_price_at_event is not None and strategy_state["last_signal_type"] != -1:
        strategy_state["final_pivot_low_price_confirmed"] = raw_pivot_low_price_at_event
        strategy_state["last_signal_type"] = -1
        logging.info(f"{AnsiColors.CYAN}PIVOT LOW:  {strategy_state['final_pivot_low_price_confirmed']:.5f} @ {df.index[idx_pivot_event_low].strftime('%Y-%m-%d %H:%M')}{AnsiColors.ENDC}")

    current_candle = df.iloc[current_bar_index_in_df]
    # ... (Logika FIB, SecureFIB, sama, hanya tambahkan warna dan notifikasi) ...
    if strategy_state["final_pivot_high_price_confirmed"] is not None: # High baru
        strategy_state["high_price_for_fib"] = strategy_state["final_pivot_high_price_confirmed"]
        strategy_state["high_bar_index_for_fib"] = idx_pivot_event_high
        if strategy_state["active_fib_level"] is not None:
            logging.debug("Resetting active FIB due to new High.")
            strategy_state["active_fib_level"] = None; strategy_state["active_fib_line_start_index"] = None

    if strategy_state["final_pivot_low_price_confirmed"] is not None: # Low baru
        if strategy_state["high_price_for_fib"] is not None and strategy_state["high_bar_index_for_fib"] is not None:
            current_low_price = strategy_state["final_pivot_low_price_confirmed"]
            current_low_bar_index = idx_pivot_event_low
            if current_low_bar_index > strategy_state["high_bar_index_for_fib"]:
                calculated_fib_level = (strategy_state["high_price_for_fib"] + current_low_price) / 2.0
                is_fib_late = False
                if settings["enable_secure_fib"]:
                    price_to_check_str = settings["secure_fib_check_price"].lower()
                    if price_to_check_str not in current_candle: price_to_check_str = 'close' 
                    price_val_current_candle = current_candle[price_to_check_str]
                    if price_val_current_candle > calculated_fib_level: is_fib_late = True
                
                if is_fib_late:
                    logging.info(f"{AnsiColors.ORANGE}FIB Terlambat ({calculated_fib_level:.5f}), Harga Cek ({settings['secure_fib_check_price']}: {price_val_current_candle:.5f}) > FIB.{AnsiColors.ENDC}")
                    strategy_state["active_fib_level"] = None; strategy_state["active_fib_line_start_index"] = None
                else:
                    logging.info(f"{AnsiColors.CYAN}FIB 0.5 Aktif: {calculated_fib_level:.5f}{AnsiColors.ENDC} (H: {strategy_state['high_price_for_fib']:.2f}, L: {current_low_price:.2f})")
                    strategy_state["active_fib_level"] = calculated_fib_level
                    strategy_state["active_fib_line_start_index"] = current_low_bar_index
                strategy_state["high_price_for_fib"] = None; strategy_state["high_bar_index_for_fib"] = None

    if strategy_state["active_fib_level"] is not None and strategy_state["active_fib_line_start_index"] is not None: # Cek Entry
        is_bullish_candle = current_candle['close'] > current_candle['open']
        is_closed_above_fib = current_candle['close'] > strategy_state["active_fib_level"]
        if is_bullish_candle and is_closed_above_fib:
            if strategy_state["position_size"] == 0: 
                strategy_state["position_size"] = 1 # Atau qty lain
                entry_px = current_candle['close']
                strategy_state["entry_price_custom"] = entry_px
                strategy_state["highest_price_for_trailing"] = entry_px
                strategy_state["trailing_tp_active_custom"] = False
                strategy_state["current_trailing_stop_level"] = None
                emerg_sl = entry_px * (1 - settings["emergency_sl_percent"] / 100.0)
                strategy_state["emergency_sl_level_custom"] = emerg_sl
                
                log_msg = f"BUY ENTRY @ {entry_px:.5f} (FIB {strategy_state['active_fib_level']:.5f} dilewati). Emerg SL: {emerg_sl:.5f}"
                logging.info(f"{AnsiColors.GREEN}{AnsiColors.BOLD}{log_msg}{AnsiColors.ENDC}")
                play_notification_sound()
                email_subject = f"BUY Signal: {settings['symbol']}-{settings['currency']}"
                email_body = f"New BUY signal triggered for {settings['symbol']}-{settings['currency']} on {settings['exchange']}.\n\n" \
                             f"Entry Price: {entry_px:.5f}\n" \
                             f"FIB Level: {strategy_state['active_fib_level']:.5f}\n" \
                             f"Emergency SL: {emerg_sl:.5f}\n" \
                             f"Timestamp: {current_candle.name.strftime('%Y-%m-%d %H:%M:%S')}"
                send_email_notification(email_subject, email_body, settings)
            
            strategy_state["active_fib_level"] = None; strategy_state["active_fib_line_start_index"] = None

    if strategy_state["position_size"] > 0: # Manajemen Posisi
        strategy_state["highest_price_for_trailing"] = max(strategy_state.get("highest_price_for_trailing", current_candle['high']) , current_candle['high'])
        if not strategy_state["trailing_tp_active_custom"] and strategy_state["entry_price_custom"] is not None:
            profit_percent = ((strategy_state["highest_price_for_trailing"] - strategy_state["entry_price_custom"]) / strategy_state["entry_price_custom"]) * 100.0 if strategy_state["entry_price_custom"] != 0 else 0
            if profit_percent >= settings["profit_target_percent_activation"]:
                strategy_state["trailing_tp_active_custom"] = True
                logging.info(f"{AnsiColors.BLUE}Trailing TP Aktif. Profit: {profit_percent:.2f}%, High: {strategy_state['highest_price_for_trailing']:.5f}{AnsiColors.ENDC}")

        if strategy_state["trailing_tp_active_custom"] and strategy_state["highest_price_for_trailing"] is not None:
            potential_new_stop_price = strategy_state["highest_price_for_trailing"] * (1 - (settings["trailing_stop_gap_percent"] / 100.0))
            if strategy_state["current_trailing_stop_level"] is None or potential_new_stop_price > strategy_state["current_trailing_stop_level"]:
                strategy_state["current_trailing_stop_level"] = potential_new_stop_price
                logging.debug(f"Trailing SL update: {strategy_state['current_trailing_stop_level']:.5f}")
        
        final_stop_for_exit = strategy_state["emergency_sl_level_custom"]
        exit_comment = "Emergency SL"
        exit_color = AnsiColors.RED # Warna default untuk SL
        if strategy_state["trailing_tp_active_custom"] and strategy_state["current_trailing_stop_level"] is not None:
            if final_stop_for_exit is None or strategy_state["current_trailing_stop_level"] > final_stop_for_exit :
                final_stop_for_exit = strategy_state["current_trailing_stop_level"]
                exit_comment = "Trailing Stop"
                # Jika trailing stop, bisa jadi TP, jadi warna biru
                exit_color = AnsiColors.BLUE 
        
        if final_stop_for_exit is not None and current_candle['low'] <= final_stop_for_exit:
            exit_price = min(current_candle['open'], final_stop_for_exit) 
            pnl = 0.0
            if strategy_state["entry_price_custom"] is not None and strategy_state["entry_price_custom"] != 0:
                 pnl = (exit_price - strategy_state["entry_price_custom"]) / strategy_state["entry_price_custom"] * 100.0
            
            # Jika pnl negatif meski dari Trailing Stop, kembalikan ke merah
            if exit_comment == "Trailing Stop" and pnl < 0:
                exit_color = AnsiColors.RED

            log_msg = f"EXIT ORDER @ {exit_price:.5f} by {exit_comment}. PnL: {pnl:.2f}%"
            logging.info(f"{exit_color}{AnsiColors.BOLD}{log_msg}{AnsiColors.ENDC}")
            play_notification_sound()
            email_subject = f"Trade Closed: {settings['symbol']}-{settings['currency']} ({exit_comment})"
            email_body = f"Trade closed for {settings['symbol']}-{settings['currency']} on {settings['exchange']}.\n\n" \
                         f"Exit Price: {exit_price:.5f}\n" \
                         f"Reason: {exit_comment}\n" \
                         f"Entry Price: {strategy_state.get('entry_price_custom', 0):.5f}\n" \
                         f"PnL: {pnl:.2f}%\n" \
                         f"Timestamp: {current_candle.name.strftime('%Y-%m-%d %H:%M:%S')}"
            send_email_notification(email_subject, email_body, settings)

            # Reset state trading
            strategy_state["position_size"] = 0; strategy_state["entry_price_custom"] = None
            strategy_state["highest_price_for_trailing"] = None; strategy_state["trailing_tp_active_custom"] = False
            strategy_state["current_trailing_stop_level"] = None; strategy_state["emergency_sl_level_custom"] = None
    
    if strategy_state["position_size"] > 0:
        # ... (log debug Posisi Aktif sama) ...
        plot_stop_level = strategy_state.get("emergency_sl_level_custom")
        if strategy_state.get("trailing_tp_active_custom") and strategy_state.get("current_trailing_stop_level") is not None:
            emergency_sl = strategy_state.get("emergency_sl_level_custom")
            current_trailing_sl = strategy_state.get("current_trailing_stop_level")
            if emergency_sl is not None and current_trailing_sl is not None and current_trailing_sl > emergency_sl: plot_stop_level = current_trailing_sl
            elif current_trailing_sl is not None and emergency_sl is None: plot_stop_level = current_trailing_sl
        entry_price_display = strategy_state.get('entry_price_custom', 0)
        sl_display_str = f'{plot_stop_level:.5f}' if plot_stop_level is not None else 'N/A'
        logging.debug(f"Posisi Aktif. Entry: {entry_price_display:.5f}, Current SL: {sl_display_str}")


# --- FUNGSI UTAMA TRADING LOOP ---
def start_trading(settings):
    # ... (setup awal dan log info sama) ...
    display_pair = f"{settings.get('symbol','N/A')}-{settings.get('currency','N/A')}"
    display_exchange = settings.get('exchange','N/A')
    display_timeframe = settings.get('timeframe','N/A')
    refresh_interval = settings.get('refresh_interval_seconds',0)
    
    logging.info(f"{AnsiColors.HEADER}================ STRATEGY START ================{AnsiColors.ENDC}")
    logging.info(f"Pair: {AnsiColors.BOLD}{display_pair}{AnsiColors.ENDC} | Exchange: {AnsiColors.BOLD}{display_exchange}{AnsiColors.ENDC} | TF: {AnsiColors.BOLD}{display_timeframe}{AnsiColors.ENDC} | Refresh: {AnsiColors.BOLD}{refresh_interval}s{AnsiColors.ENDC}")
    logging.info(f"Params: LeftStr={settings.get('left_strength',0)}, RightStr={settings.get('right_strength',0)}, TrailActiv={settings.get('profit_target_percent_activation',0.0)}%, TrailGap={settings.get('trailing_stop_gap_percent',0.0)}%, EmergSL={settings.get('emergency_sl_percent',0.0)}%")
    logging.info(f"SecureFIB: {settings.get('enable_secure_fib',False)}, CheckPrice: {settings.get('secure_fib_check_price','N/A')}")
    if settings.get('enable_email_notifications'):
        logging.info(f"Email Notif: {AnsiColors.GREEN}Aktif{AnsiColors.ENDC} (Ke: {settings.get('email_receiver_address')})")
    else:
        logging.info(f"Email Notif: {AnsiColors.ORANGE}Nonaktif{AnsiColors.ENDC}")
    logging.info(f"{AnsiColors.HEADER}==============================================={AnsiColors.ENDC}")


    if settings.get('api_key',"") == "YOUR_API_KEY_HERE" or not settings.get('api_key',""):
        logging.error(f"{AnsiColors.RED}API Key belum diatur! Atur via menu Settings.{AnsiColors.ENDC}")
        return

    global strategy_state # Reset state
    strategy_state = {
        "last_signal_type": 0, "final_pivot_high_price_confirmed": None, "final_pivot_low_price_confirmed": None,
        "high_price_for_fib": None, "high_bar_index_for_fib": None, "active_fib_level": None,
        "active_fib_line_start_index": None, "entry_price_custom": None, "highest_price_for_trailing": None,
        "trailing_tp_active_custom": False, "current_trailing_stop_level": None,
        "emergency_sl_level_custom": None, "position_size": 0,
    }
    
    fetch_limit_for_api = CRYPTOCOMPARE_MAX_LIMIT
    all_data_df = fetch_candles(settings.get('symbol'), settings.get('currency'), fetch_limit_for_api, 
                                settings.get('exchange'), settings.get('api_key'), settings.get('timeframe'))

    if all_data_df.empty:
        logging.error(f"{AnsiColors.RED}Tidak ada data awal. Periksa setting & koneksi. Menghentikan.{AnsiColors.ENDC}")
        return

    logging.info(f"Memproses {max(0, len(all_data_df) - 1)} candle historis awal untuk inisialisasi state...")
    start_warmup_processing_idx = settings.get('left_strength',50) + settings.get('right_strength',150)
    for i in range(start_warmup_processing_idx, len(all_data_df) -1): 
        historical_slice = all_data_df.iloc[:i+1]
        if len(historical_slice) < start_warmup_processing_idx +1 : continue
        run_strategy_logic(historical_slice, settings)
        if strategy_state["position_size"] > 0: # Reset jika ada trade saat pemanasan
            strategy_state["position_size"] = 0; strategy_state["entry_price_custom"] = None 
            strategy_state["emergency_sl_level_custom"] = None
    logging.info(f"{AnsiColors.CYAN}Inisialisasi state selesai.{AnsiColors.ENDC}")
    logging.info(f"{AnsiColors.HEADER}---------- MULAI LIVE ANALYSIS ----------{AnsiColors.ENDC}")

    try:
        while True:
            current_loop_time = datetime.now()
            logging.info(f"\n{AnsiColors.BOLD}--- Analisa Candle Baru ({current_loop_time.strftime('%Y-%m-%d %H:%M:%S')}) ---{AnsiColors.ENDC}")
            new_data_df = fetch_candles(settings.get('symbol'), settings.get('currency'), fetch_limit_for_api, 
                                        settings.get('exchange'), settings.get('api_key'), settings.get('timeframe'))
            if new_data_df.empty:
                logging.warning(f"{AnsiColors.ORANGE}Gagal/tidak ada data baru. Mencoba lagi...{AnsiColors.ENDC}")
                time.sleep(settings.get('refresh_interval_seconds',15))
                continue
            
            last_known_index_val = all_data_df.index[-1] if not all_data_df.empty else None
            combined_df = pd.concat([all_data_df, new_data_df])
            combined_df = combined_df[~combined_df.index.duplicated(keep='last')]
            combined_df.sort_index(inplace=True)
            all_data_df = combined_df
            
            start_processing_idx_loc = 0
            if last_known_index_val:
                try:
                    idx_loc = all_data_df.index.get_loc(last_known_index_val)
                    start_processing_idx_loc = idx_loc + 1
                except KeyError: 
                    logging.warning(f"{AnsiColors.ORANGE}Index lama {last_known_index_val} tidak ditemukan. Proses beberapa bar terakhir.{AnsiColors.ENDC}")
                    start_processing_idx_loc = max(0, len(all_data_df) - 5) 
            else:
                 start_processing_idx_loc = max(0, len(all_data_df) - int(fetch_limit_for_api/2) )
                 start_processing_idx_loc = max(start_processing_idx_loc, settings.get('left_strength',50) + settings.get('right_strength',150))

            if start_processing_idx_loc >= len(all_data_df):
                ts_display = all_data_df.index[-1].strftime('%H:%M:%S') if not all_data_df.empty else "N/A"
                logging.info(f"Tidak ada candle baru sejak {ts_display}. Menunggu {settings.get('refresh_interval_seconds',15)} detik...")
            else:
                num_new_candles = len(all_data_df) - start_processing_idx_loc
                logging.info(f"Memproses {AnsiColors.BOLD}{num_new_candles}{AnsiColors.ENDC} candle baru (dari {all_data_df.index[start_processing_idx_loc].strftime('%H:%M')} hingga {all_data_df.index[-1].strftime('%H:%M')}).")
                for i in range(start_processing_idx_loc, len(all_data_df)):
                    current_processing_slice = all_data_df.iloc[:i+1] 
                    if len(current_processing_slice) < settings.get('left_strength',50) + settings.get('right_strength',150) + 1: continue 
                    # log analisa candle individu bisa di-debug jika terlalu verbose
                    # logging.debug(f"Menganalisa candle: {current_processing_slice.index[-1].strftime('%H:%M')} (Close: {current_processing_slice.iloc[-1]['close']:.5f})")
                    run_strategy_logic(current_processing_slice, settings)
            
            logging.info(f"{AnsiColors.BOLD}--- Selesai Loop Analisa. Menunggu {settings.get('refresh_interval_seconds',15)} detik ---{AnsiColors.ENDC}")
            time.sleep(settings.get('refresh_interval_seconds',15))
    except KeyboardInterrupt:
        logging.info(f"\n{AnsiColors.ORANGE}Proses trading dihentikan oleh pengguna.{AnsiColors.ENDC}")
    except Exception as e:
        logging.exception(f"{AnsiColors.RED}Error tak terduga di loop trading utama: {e}{AnsiColors.ENDC}")
    finally:
        logging.info(f"{AnsiColors.HEADER}================ STRATEGY STOP ================{AnsiColors.ENDC}")


# --- MENU UTAMA ---
def main_menu():
    settings = load_settings()
    while True:
        # ... (tampilan menu utama sama) ...
        display_pair = f"{settings.get('symbol','N/A')}-{settings.get('currency','N/A')}"
        display_exchange = settings.get('exchange','N/A')
        display_timeframe = settings.get('timeframe','N/A')
        refresh_interval = settings.get('refresh_interval_seconds',0)
        print(f"\n{AnsiColors.HEADER}========= Crypto Strategy Runner ========={AnsiColors.ENDC}")
        print(f"Pair: {AnsiColors.BOLD}{display_pair}{AnsiColors.ENDC} | Exch: {AnsiColors.BOLD}{display_exchange}{AnsiColors.ENDC} | TF: {AnsiColors.BOLD}{display_timeframe}{AnsiColors.ENDC} | Int: {AnsiColors.BOLD}{refresh_interval}s{AnsiColors.ENDC}")
        print("--------------------------------------")
        print(f"1. {AnsiColors.GREEN}Mulai Analisa Realtime{AnsiColors.ENDC}")
        print(f"2. {AnsiColors.ORANGE}Pengaturan{AnsiColors.ENDC}")
        print(f"3. {AnsiColors.RED}Keluar{AnsiColors.ENDC}")
        choice = input("Pilihan Anda: ")

        if choice == '1':
            start_trading(settings)
        elif choice == '2':
            settings = settings_menu(settings)
        elif choice == '3':
            logging.info("Aplikasi ditutup.")
            break
        else:
            print(f"{AnsiColors.RED}Pilihan tidak valid.{AnsiColors.ENDC}")

if __name__ == "__main__":
    main_menu()
