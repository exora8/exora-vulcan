import requests
import pandas as pd
import time
import json
import os
import logging
from datetime import datetime

# --- ANSI COLOR CODES ---
class AnsiColors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    ORANGE = '\033[93m' # Istilah teknisnya Yellow, tapi visualnya oranye
    RESET = '\033[0m'   # Reset warna ke default

# --- KONFIGURASI LOGGING ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("trading_log.txt", mode='a'),
                              logging.StreamHandler()])

SETTINGS_FILE = "settings.json"

# --- FUNGSI PENGATURAN --- (Sama seperti sebelumnya)
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                logging.error("Error membaca settings.json. Menggunakan default.")
    return {
        "api_key": "YOUR_API_KEY_HERE",
        "symbol": "BTC",
        "currency": "USD",
        "exchange": "CCCAGG",
        "refresh_interval_seconds": 15,
        "data_limit": 250,
        "left_strength": 50,
        "right_strength": 150,
        "profit_target_percent_activation": 5.0,
        "trailing_stop_gap_percent": 5.0,
        "emergency_sl_percent": 10.0,
        "enable_secure_fib": True,
        "secure_fib_check_price": "Close"
    }

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=4)
    logging.info("Pengaturan disimpan ke settings.json")

def settings_menu(current_settings):
    print("\n--- Menu Pengaturan ---")
    new_settings = current_settings.copy()
    try:
        new_settings["api_key"] = input(f"API Key CryptoCompare [{current_settings.get('api_key','')}]: ") or current_settings.get('api_key','')
        new_settings["symbol"] = (input(f"Simbol Crypto Dasar (misal BTC) [{current_settings.get('symbol','BTC')}]: ") or current_settings.get('symbol','BTC')).upper()
        new_settings["currency"] = (input(f"Simbol Mata Uang Quote (misal USDT, USD) [{current_settings.get('currency','USD')}]: ") or current_settings.get('currency','USD')).upper()
        new_settings["exchange"] = (input(f"Exchange (misal Binance, Coinbase, atau CCCAGG untuk agregat) [{current_settings.get('exchange','CCCAGG')}]: ") or current_settings.get('exchange','CCCAGG'))
        new_settings["refresh_interval_seconds"] = int(input(f"Interval Refresh (detik) [{current_settings.get('refresh_interval_seconds',15)}]: ") or current_settings.get('refresh_interval_seconds',15))
        new_settings["data_limit"] = int(input(f"Limit Data Candle (untuk analisis awal) [{current_settings.get('data_limit',250)}]: ") or current_settings.get('data_limit',250))
        print("\n-- Parameter Pivot --")
        new_settings["left_strength"] = int(input(f"Left Strength (Bars Kiri) [{current_settings.get('left_strength',50)}]: ") or current_settings.get('left_strength',50))
        new_settings["right_strength"] = int(input(f"Right Strength (Bars Kanan - Konfirmasi) [{current_settings.get('right_strength',150)}]: ") or current_settings.get('right_strength',150))
        print("\n-- Parameter Trading --")
        new_settings["profit_target_percent_activation"] = float(input(f"Profit % untuk Aktivasi Trailing TP [{current_settings.get('profit_target_percent_activation',5.0)}]: ") or current_settings.get('profit_target_percent_activation',5.0))
        new_settings["trailing_stop_gap_percent"] = float(input(f"Gap Trailing TP % dari High [{current_settings.get('trailing_stop_gap_percent',5.0)}]: ") or current_settings.get('trailing_stop_gap_percent',5.0))
        new_settings["emergency_sl_percent"] = float(input(f"Emergency SL % dari Entry [{current_settings.get('emergency_sl_percent',10.0)}]: ") or current_settings.get('emergency_sl_percent',10.0))
        print("\n-- Fitur Secure FIB --")
        enable_sf_input = input(f"Aktifkan Secure FIB? (true/false) [{current_settings.get('enable_secure_fib',True)}]: ").lower()
        new_settings["enable_secure_fib"] = True if enable_sf_input == 'true' else (False if enable_sf_input == 'false' else current_settings.get('enable_secure_fib',True))
        secure_fib_price_input = (input(f"Harga Candle untuk Cek Secure FIB (Close/High) [{current_settings.get('secure_fib_check_price','Close')}]: ") or current_settings.get('secure_fib_check_price','Close')).capitalize()
        if secure_fib_price_input in ["Close", "High"]:
            new_settings["secure_fib_check_price"] = secure_fib_price_input
        else:
            print("Pilihan harga Secure FIB tidak valid. Menggunakan nilai sebelumnya.")
            new_settings["secure_fib_check_price"] = current_settings.get('secure_fib_check_price','Close')
        save_settings(new_settings)
        return new_settings
    except ValueError:
        print("Input tidak valid. Pengaturan tidak diubah.")
        return current_settings

# --- FUNGSI PENGAMBILAN DATA --- (Sama seperti sebelumnya)
def fetch_candles(symbol, currency, limit, exchange_name, api_key):
    url = f"https://min-api.cryptocompare.com/data/v2/histohour"
    params = {"fsym": symbol, "tsym": currency, "limit": limit -1, "api_key": api_key}
    if exchange_name and exchange_name.upper() != "CCCAGG":
        params["e"] = exchange_name
    try:
        response = requests.get(url, params=params)
        response.raise_for_status() 
        data = response.json()
        if data.get('Response') == 'Error':
            logging.error(f"API Error dari CryptoCompare: {data.get('Message', 'Pesan error tidak diketahui')}")
            logging.error(f"Parameter API: fsym={symbol}, tsym={currency}, exchange={exchange_name or 'CCCAGG (default)'}, limit={limit-1}")
            return pd.DataFrame()
        if 'Data' not in data or 'Data' not in data['Data']:
            logging.error(f"Format data dari API tidak sesuai harapan. Respons: {data}")
            return pd.DataFrame()
        df = pd.DataFrame(data['Data']['Data'])
        if df.empty:
            logging.info("Tidak ada data candle yang diterima dari API (DataFrame kosong).")
            return pd.DataFrame()
        df['timestamp'] = pd.to_datetime(df['time'], unit='s')
        df = df.set_index('timestamp')
        df = df[['open', 'high', 'low', 'close', 'volumefrom']] 
        df.rename(columns={'volumefrom': 'volume'}, inplace=True)
        return df
    except requests.exceptions.RequestException as e:
        logging.error(f"Kesalahan koneksi saat mengambil data: {e}")
        return pd.DataFrame()
    except KeyError as e:
        logging.error(f"Format data dari API tidak sesuai harapan (KeyError): {e}. Respons: {response.text if 'response' in locals() else 'N/A'}")
        return pd.DataFrame()
    except Exception as e:
        logging.error(f"Error tidak diketahui saat mengambil data: {e}")
        return pd.DataFrame()

# --- LOGIKA STRATEGI ---
strategy_state = {
    "last_signal_type": 0, "final_pivot_high_price_confirmed": None, "final_pivot_low_price_confirmed": None,
    "high_price_for_fib": None, "high_bar_index_for_fib": None, "active_fib_level": None,
    "active_fib_line_start_index": None, "entry_price_custom": None, "highest_price_for_trailing": None,
    "trailing_tp_active_custom": False, "current_trailing_stop_level": None,
    "emergency_sl_level_custom": None, "position_size": 0,
}

def find_pivots(series_list, left_strength, right_strength, is_high=True): # Menerima list
    pivots = [None] * len(series_list)
    if len(series_list) < left_strength + right_strength + 1:
        return pivots
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
        if is_pivot:
            pivots[i] = series_list[i] 
    return pivots

def run_strategy_logic(df, settings):
    global strategy_state 
    strategy_state["final_pivot_high_price_confirmed"] = None
    strategy_state["final_pivot_low_price_confirmed"] = None
    left_strength = settings['left_strength']
    right_strength = settings['right_strength']
    required_cols = ['high', 'low', 'open', 'close']
    if df.empty or not all(col in df.columns for col in required_cols):
        logging.warning("DataFrame kosong atau kekurangan kolom untuk run_strategy_logic.")
        return

    # Gunakan .tolist() untuk konversi ke list sebelum dikirim ke find_pivots
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
        logging.info(f"PIVOT HIGH Terkonfirmasi: {strategy_state['final_pivot_high_price_confirmed']:.5f} pada (event time {df.index[idx_pivot_event_high]})")
        
    if raw_pivot_low_price_at_event is not None and strategy_state["last_signal_type"] != -1:
        strategy_state["final_pivot_low_price_confirmed"] = raw_pivot_low_price_at_event
        strategy_state["last_signal_type"] = -1
        logging.info(f"PIVOT LOW Terkonfirmasi: {strategy_state['final_pivot_low_price_confirmed']:.5f} pada (event time {df.index[idx_pivot_event_low]})")

    current_candle = df.iloc[current_bar_index_in_df]

    if strategy_state["final_pivot_high_price_confirmed"] is not None:
        strategy_state["high_price_for_fib"] = strategy_state["final_pivot_high_price_confirmed"]
        strategy_state["high_bar_index_for_fib"] = idx_pivot_event_high
        if strategy_state["active_fib_level"] is not None:
            logging.debug("Menghapus FIB line visual lama karena HIGH baru.")
            strategy_state["active_fib_level"] = None
            strategy_state["active_fib_line_start_index"] = None

    if strategy_state["final_pivot_low_price_confirmed"] is not None:
        if strategy_state["high_price_for_fib"] is not None and strategy_state["high_bar_index_for_fib"] is not None:
            current_low_price = strategy_state["final_pivot_low_price_confirmed"]
            current_low_bar_index = idx_pivot_event_low
            if current_low_bar_index > strategy_state["high_bar_index_for_fib"]:
                calculated_fib_level = (strategy_state["high_price_for_fib"] + current_low_price) / 2.0
                is_fib_late = False
                if settings["enable_secure_fib"]:
                    price_to_check_str = settings["secure_fib_check_price"].lower()
                    price_val_current_candle = current_candle[price_to_check_str]
                    if price_val_current_candle > calculated_fib_level:
                        is_fib_late = True
                
                if is_fib_late:
                    logging.info(f"{AnsiColors.ORANGE}FIB Terlambat ({calculated_fib_level:.5f}) diabaikan. Harga cek ({settings['secure_fib_check_price']}: {price_val_current_candle:.5f}) sudah melewati.{AnsiColors.RESET}")
                    strategy_state["active_fib_level"] = None
                    strategy_state["active_fib_line_start_index"] = None
                else:
                    logging.info(f"FIB 0.5 Aktif: {calculated_fib_level:.5f} (dari High {strategy_state['high_price_for_fib']:.5f} di {df.index[strategy_state['high_bar_index_for_fib']]} & Low {current_low_price:.5f} di {df.index[current_low_bar_index]})")
                    strategy_state["active_fib_level"] = calculated_fib_level
                    strategy_state["active_fib_line_start_index"] = current_low_bar_index
                strategy_state["high_price_for_fib"] = None
                strategy_state["high_bar_index_for_fib"] = None

    if strategy_state["active_fib_level"] is not None and strategy_state["active_fib_line_start_index"] is not None:
        is_bullish_candle = current_candle['close'] > current_candle['open']
        is_closed_above_fib = current_candle['close'] > strategy_state["active_fib_level"]
        if is_bullish_candle and is_closed_above_fib:
            if strategy_state["position_size"] == 0: 
                strategy_state["position_size"] = 1 
                strategy_state["entry_price_custom"] = current_candle['close'] 
                strategy_state["highest_price_for_trailing"] = strategy_state["entry_price_custom"]
                strategy_state["trailing_tp_active_custom"] = False
                strategy_state["current_trailing_stop_level"] = None
                strategy_state["emergency_sl_level_custom"] = strategy_state["entry_price_custom"] * (1 - settings["emergency_sl_percent"] / 100.0)
                
                logging.info(f"{AnsiColors.GREEN}BUY ENTRY @ {strategy_state['entry_price_custom']:.5f} (FIB {strategy_state['active_fib_level']:.5f} terlewati){AnsiColors.RESET}")
                logging.info(f"   Emergency SL: {strategy_state['emergency_sl_level_custom']:.5f}") # Tidak diwarnai agar fokus pada BUY
            
            logging.debug(f"Garis FIB {strategy_state['active_fib_level']:.5f} dipotong karena harga close di atasnya.")
            strategy_state["active_fib_level"] = None 
            strategy_state["active_fib_line_start_index"] = None

    if strategy_state["position_size"] > 0: 
        strategy_state["highest_price_for_trailing"] = max(strategy_state.get("highest_price_for_trailing", current_candle['high']) , current_candle['high'])
        if not strategy_state["trailing_tp_active_custom"] and strategy_state["entry_price_custom"] is not None:
            profit_percent = ((strategy_state["highest_price_for_trailing"] - strategy_state["entry_price_custom"]) / strategy_state["entry_price_custom"]) * 100.0
            if profit_percent >= settings["profit_target_percent_activation"]:
                strategy_state["trailing_tp_active_custom"] = True
                logging.info(f"{AnsiColors.BLUE}Trailing TP Aktif. Profit: {profit_percent:.2f}%, High: {strategy_state['highest_price_for_trailing']:.5f}{AnsiColors.RESET}") # TP related info in blue

        if strategy_state["trailing_tp_active_custom"] and strategy_state["highest_price_for_trailing"] is not None:
            potential_new_stop_price = strategy_state["highest_price_for_trailing"] * (1 - (settings["trailing_stop_gap_percent"] / 100.0))
            if strategy_state["current_trailing_stop_level"] is None or potential_new_stop_price > strategy_state["current_trailing_stop_level"]:
                strategy_state["current_trailing_stop_level"] = potential_new_stop_price
                logging.debug(f"Trailing Stop Level diupdate ke: {strategy_state['current_trailing_stop_level']:.5f}")
        
        final_stop_for_exit = strategy_state["emergency_sl_level_custom"]
        exit_comment = "Emergency SL"
        if strategy_state["trailing_tp_active_custom"] and strategy_state["current_trailing_stop_level"] is not None:
            if final_stop_for_exit is None or strategy_state["current_trailing_stop_level"] > final_stop_for_exit : # Handle final_stop_for_exit being None
                final_stop_for_exit = strategy_state["current_trailing_stop_level"]
                exit_comment = "Trailing Stop"
        
        if final_stop_for_exit is not None and current_candle['low'] <= final_stop_for_exit:
            exit_price = min(current_candle['open'], final_stop_for_exit) 
            pnl = 0.0
            if strategy_state["entry_price_custom"] is not None and strategy_state["entry_price_custom"] != 0:
                 pnl = (exit_price - strategy_state["entry_price_custom"]) / strategy_state["entry_price_custom"] * 100.0
            
            exit_color = AnsiColors.RED # Default untuk SL
            if pnl > 0 and exit_comment == "Trailing Stop": # Jika Trailing Stop menghasilkan profit, bisa dianggap TP
                exit_color = AnsiColors.BLUE 
            
            logging.info(f"{exit_color}EXIT ORDER @ {exit_price:.5f} oleh {exit_comment}. PnL: {pnl:.2f}%{AnsiColors.RESET}")
            
            strategy_state["position_size"] = 0; strategy_state["entry_price_custom"] = None
            strategy_state["highest_price_for_trailing"] = None; strategy_state["trailing_tp_active_custom"] = False
            strategy_state["current_trailing_stop_level"] = None; strategy_state["emergency_sl_level_custom"] = None
    
    if strategy_state["position_size"] > 0:
        plot_stop_level = strategy_state.get("emergency_sl_level_custom")
        if strategy_state.get("trailing_tp_active_custom") and strategy_state.get("current_trailing_stop_level") is not None:
            # Pastikan kedua level ada sebelum membandingkan
            emergency_sl = strategy_state.get("emergency_sl_level_custom")
            current_trailing_sl = strategy_state.get("current_trailing_stop_level")
            if emergency_sl is not None and current_trailing_sl is not None and current_trailing_sl > emergency_sl:
                plot_stop_level = current_trailing_sl
            elif current_trailing_sl is not None and emergency_sl is None: # Jika emergency SL tidak ada (seharusnya tidak terjadi jika posisi aktif)
                 plot_stop_level = current_trailing_sl


        # --- PERBAIKAN ERROR DI SINI ---
        entry_price_display = strategy_state.get('entry_price_custom', 0)
        sl_display_str = f'{plot_stop_level:.5f}' if plot_stop_level is not None else 'N/A'
        logging.debug(f"Posisi Aktif. Entry: {entry_price_display:.5f}, Current SL: {sl_display_str}")

# --- FUNGSI UTAMA TRADING LOOP --- (Sama seperti sebelumnya, dengan penyesuaian `get` untuk settings)
def start_trading(settings):
    display_pair = f"{settings.get('symbol','N/A')}-{settings.get('currency','N/A')}"
    display_exchange = settings.get('exchange','N/A')
    logging.info(f"Memulai trading untuk {display_pair} di {display_exchange} dengan interval {settings.get('refresh_interval_seconds',0)} detik.")
    logging.info(f"Parameter: LeftStr={settings.get('left_strength',0)}, RightStr={settings.get('right_strength',0)}, "
                 f"ProfitTrailActiv={settings.get('profit_target_percent_activation',0.0)}%, TrailGap={settings.get('trailing_stop_gap_percent',0.0)}%, EmergSL={settings.get('emergency_sl_percent',0.0)}%")
    logging.info(f"SecureFIB: {settings.get('enable_secure_fib',False)}, SecureFIBCheck: {settings.get('secure_fib_check_price','N/A')}")

    if settings.get('api_key',"") == "YOUR_API_KEY_HERE" or not settings.get('api_key',""):
        logging.error("API Key belum diatur. Silakan atur melalui menu Settings.")
        return

    global strategy_state
    strategy_state = { # Reset state
        "last_signal_type": 0, "final_pivot_high_price_confirmed": None, "final_pivot_low_price_confirmed": None,
        "high_price_for_fib": None, "high_bar_index_for_fib": None, "active_fib_level": None,
        "active_fib_line_start_index": None, "entry_price_custom": None, "highest_price_for_trailing": None,
        "trailing_tp_active_custom": False, "current_trailing_stop_level": None,
        "emergency_sl_level_custom": None, "position_size": 0,
    }
    
    initial_fetch_limit = max(settings.get('data_limit',250), settings.get('left_strength',50) + settings.get('right_strength',150) + 50) 
    initial_fetch_limit = min(initial_fetch_limit, 1999) 

    all_data_df = fetch_candles(settings.get('symbol'), settings.get('currency'), initial_fetch_limit, settings.get('exchange'), settings.get('api_key'))

    if all_data_df.empty:
        logging.error("Tidak ada data awal yang bisa diambil. Periksa Simbol, Mata Uang, Exchange, dan API Key. Menghentikan trading.")
        return

    logging.info(f"Memproses {max(0, len(all_data_df) - 1)} candle historis awal untuk inisialisasi state...")
    start_warmup_processing_idx = settings.get('left_strength',50) + settings.get('right_strength',150)
    for i in range(start_warmup_processing_idx, len(all_data_df) -1): 
        historical_slice = all_data_df.iloc[:i+1]
        if len(historical_slice) < start_warmup_processing_idx +1 : 
            continue
        run_strategy_logic(historical_slice, settings)
        if strategy_state["position_size"] > 0: # Reset posisi jika terpicu saat pemanasan
            strategy_state["position_size"] = 0 
            strategy_state["entry_price_custom"] = None # Reset juga detail trading lainnya
            strategy_state["emergency_sl_level_custom"] = None
            # ... (bisa ditambahkan reset variabel state trading lainnya)
    logging.info("Inisialisasi state selesai.")

    try:
        while True:
            new_data_df = fetch_candles(settings.get('symbol'), settings.get('currency'), initial_fetch_limit, settings.get('exchange'), settings.get('api_key'))
            if new_data_df.empty:
                logging.warning("Gagal mengambil data baru atau tidak ada data baru. Mencoba lagi nanti.")
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
                    logging.warning(f"Index lama {last_known_index_val} tidak ditemukan setelah concat. Memproses beberapa bar terakhir.")
                    start_processing_idx_loc = max(0, len(all_data_df) - 5) 
            else:
                 start_processing_idx_loc = max(0, len(all_data_df) - settings.get('data_limit', 250))
                 start_processing_idx_loc = max(start_processing_idx_loc, settings.get('left_strength',50) + settings.get('right_strength',150))

            if start_processing_idx_loc >= len(all_data_df):
                current_time_display = all_data_df.index[-1].strftime('%Y-%m-%d %H:%M:%S') if not all_data_df.empty else "N/A"
                logging.info(f"Tidak ada candle baru untuk diproses sejak {current_time_display}. Menunggu...")
            else:
                logging.info(f"Memproses candle dari {all_data_df.index[start_processing_idx_loc].strftime('%Y-%m-%d %H:%M:%S')} hingga {all_data_df.index[-1].strftime('%Y-%m-%d %H:%M:%S')}")
                for i in range(start_processing_idx_loc, len(all_data_df)):
                    current_processing_slice = all_data_df.iloc[:i+1] 
                    if len(current_processing_slice) < settings.get('left_strength',50) + settings.get('right_strength',150) + 1:
                        continue 
                    logging.info(f"--- Menganalisa candle: {current_processing_slice.index[-1].strftime('%Y-%m-%d %H:%M:%S')} (Close: {current_processing_slice.iloc[-1]['close']:.5f}) ---")
                    run_strategy_logic(current_processing_slice, settings)
            
            max_hist_len = initial_fetch_limit * 2
            if len(all_data_df) > max_hist_len:
                all_data_df = all_data_df.iloc[-max_hist_len:]
            time.sleep(settings.get('refresh_interval_seconds',15))
    except KeyboardInterrupt:
        logging.info("Proses trading dihentikan oleh pengguna.")
    except Exception as e:
        logging.exception(f"Error tak terduga di loop trading utama: {e}")

# --- MENU UTAMA --- (Sama seperti sebelumnya)
def main_menu():
    settings = load_settings()
    while True:
        display_pair = f"{settings.get('symbol','N/A')}-{settings.get('currency','N/A')}"
        display_exchange = settings.get('exchange','N/A')
        print("\n========= Crypto Strategy Runner =========")
        print(f"Pair: {display_pair} | Exchange: {display_exchange} | Interval: {settings.get('refresh_interval_seconds',0)}s")
        print("--------------------------------------")
        print("1. Mulai Analisa Realtime")
        print("2. Pengaturan")
        print("3. Keluar")
        choice = input("Pilihan Anda: ")
        if choice == '1':
            start_trading(settings)
        elif choice == '2':
            settings = settings_menu(settings)
        elif choice == '3':
            logging.info("Aplikasi ditutup.")
            break
        else:
            print("Pilihan tidak valid.")

if __name__ == "__main__":
    main_menu()
