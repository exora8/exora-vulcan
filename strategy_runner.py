import requests
import pandas as pd
import time
import json
import os
import logging
from datetime import datetime

# --- KONFIGURASI LOGGING ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("trading_log.txt"),
                              logging.StreamHandler()])

SETTINGS_FILE = "settings.json"

# --- FUNGSI PENGATURAN ---
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r') as f:
            try:
                loaded_settings = json.load(f)
                # Pastikan keys esensial ada, jika tidak, tambahkan dari default
                defaults = get_default_settings()
                for key, value in defaults.items():
                    if key not in loaded_settings:
                        loaded_settings[key] = value
                # Pastikan crypto_pair konsisten jika symbol/currency ada
                if 'symbol' in loaded_settings and 'currency' in loaded_settings:
                     loaded_settings['crypto_pair'] = f"{loaded_settings['symbol']}-{loaded_settings['currency']}"
                return loaded_settings
            except json.JSONDecodeError:
                logging.error("Error membaca settings.json. Menggunakan default.")
    return get_default_settings()

def get_default_settings():
    # Default settings jika file tidak ada atau error
    return {
        "api_key": "YOUR_API_KEY_HERE",
        "symbol": "BTC",          # Untuk API CryptoCompare fsym
        "currency": "USDT",       # Untuk API CryptoCompare tsym (USDT lebih umum di Binance drpd USD)
        "crypto_pair": "BTC-USDT",# Untuk tampilan, akan di-derive
        "exchange": "Binance",    # Exchange di CryptoCompare, atau CCCAGG untuk agregat
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
    # Pastikan crypto_pair konsisten sebelum menyimpan
    if 'symbol' in settings and 'currency' in settings:
        settings['crypto_pair'] = f"{settings['symbol']}-{settings['currency']}"
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=4)
    logging.info("Pengaturan disimpan ke settings.json")

def settings_menu(current_settings):
    print("\n--- Menu Pengaturan ---")
    new_settings = current_settings.copy()
    try:
        new_settings["api_key"] = input(f"API Key CryptoCompare [{current_settings.get('api_key', '')}]: ") or current_settings.get('api_key', '')
        
        default_symbol = current_settings.get('symbol', 'BTC')
        symbol_input_raw = input(f"Simbol Crypto Dasar (misal BTC, ETH) [{default_symbol}]: ")
        new_settings["symbol"] = symbol_input_raw.upper() if symbol_input_raw else default_symbol
        
        default_currency = current_settings.get('currency', 'USDT')
        currency_input_raw = input(f"Simbol Mata Uang Kutipan (misal USD, USDT, BUSD) [{default_currency}]: ")
        new_settings["currency"] = currency_input_raw.upper() if currency_input_raw else default_currency

        # Update crypto_pair untuk konsistensi internal dan tampilan
        new_settings["crypto_pair"] = f"{new_settings['symbol']}-{new_settings['currency']}"
        logging.info(f"Pasangan dikonfigurasi menjadi: {new_settings['crypto_pair']}")

        default_exchange = current_settings.get('exchange', 'Binance')
        exchange_input_raw = input(f"Exchange (misal Binance, Coinbase, atau kosongkan untuk harga agregat) [{default_exchange}]: ")
        new_settings["exchange"] = exchange_input_raw if exchange_input_raw else default_exchange
        if not new_settings["exchange"].strip(): # Jika pengguna memasukkan spasi atau string kosong
             new_settings["exchange"] = "CCCAGG" # Gunakan CCCAGG sebagai default jika input kosong
        
        new_settings["refresh_interval_seconds"] = int(input(f"Interval Refresh (detik) [{current_settings.get('refresh_interval_seconds', 15)}]: ") or current_settings.get('refresh_interval_seconds', 15))
        new_settings["data_limit"] = int(input(f"Limit Data Candle (untuk analisis awal) [{current_settings.get('data_limit', 250)}]: ") or current_settings.get('data_limit', 250))
        
        print("\n-- Parameter Pivot --")
        new_settings["left_strength"] = int(input(f"Left Strength (Bars Kiri) [{current_settings.get('left_strength',50)}]: ") or current_settings.get('left_strength',50))
        new_settings["right_strength"] = int(input(f"Right Strength (Bars Kanan - Konfirmasi) [{current_settings.get('right_strength',150)}]: ") or current_settings.get('right_strength',150))

        print("\n-- Parameter Trading --")
        new_settings["profit_target_percent_activation"] = float(input(f"Profit % untuk Aktivasi Trailing TP [{current_settings.get('profit_target_percent_activation',5.0)}]: ") or current_settings.get('profit_target_percent_activation',5.0))
        new_settings["trailing_stop_gap_percent"] = float(input(f"Gap Trailing TP % dari High [{current_settings.get('trailing_stop_gap_percent',5.0)}]: ") or current_settings.get('trailing_stop_gap_percent',5.0))
        new_settings["emergency_sl_percent"] = float(input(f"Emergency SL % dari Entry [{current_settings.get('emergency_sl_percent',10.0)}]: ") or current_settings.get('emergency_sl_percent',10.0))
        
        print("\n-- Fitur Secure FIB --")
        default_enable_sf = current_settings.get('enable_secure_fib', True)
        enable_sf_input = input(f"Aktifkan Secure FIB? (true/false) [{str(default_enable_sf).lower()}]: ").lower()
        if enable_sf_input == 'true': new_settings["enable_secure_fib"] = True
        elif enable_sf_input == 'false': new_settings["enable_secure_fib"] = False
        else: new_settings["enable_secure_fib"] = default_enable_sf
        
        default_secure_fib_price = current_settings.get('secure_fib_check_price', "Close")
        secure_fib_price_input_raw = input(f"Harga Candle untuk Cek Secure FIB (Close/High) [{default_secure_fib_price}]: ")
        secure_fib_price_input = secure_fib_price_input_raw.capitalize() if secure_fib_price_input_raw else default_secure_fib_price
        if secure_fib_price_input in ["Close", "High"]:
            new_settings["secure_fib_check_price"] = secure_fib_price_input
        else:
            print("Pilihan harga Secure FIB tidak valid. Menggunakan nilai sebelumnya.")
            new_settings["secure_fib_check_price"] = default_secure_fib_price

        save_settings(new_settings)
        return new_settings
    except ValueError:
        print("Input tidak valid. Pengaturan tidak diubah.")
        return current_settings
    except Exception as e:
        logging.error(f"Error di menu pengaturan: {e}")
        return current_settings

# --- FUNGSI PENGAMBILAN DATA ---
def fetch_candles(symbol, currency, limit, exchange_name, api_key):
    url = f"https://min-api.cryptocompare.com/data/v2/histohour"
    
    params = {
        "fsym": symbol,
        "tsym": currency,
        "limit": limit -1, 
        "api_key": api_key
    }
    # Hanya tambahkan parameter 'e' jika exchange_name bukan CCCAGG dan tidak kosong
    if exchange_name and exchange_name.upper() != "CCCAGG":
        params["e"] = exchange_name

    try:
        logging.debug(f"Fetching candles with params: {params}")
        response = requests.get(url, params=params)
        response.raise_for_status() 
        data = response.json()
        if data['Response'] == 'Error':
            # Pesan error dari CryptoCompare kadang menyertakan 'BTC-USD' sebagai contoh pair yg di-attempt.
            # Ini bisa jadi hasil dari bagaimana mereka memproses fsym dan tsym.
            logging.error(f"API Error dari CryptoCompare: {data['Message']} (untuk fsym={symbol}, tsym={currency}, exchange={exchange_name})")
            return pd.DataFrame()

        df = pd.DataFrame(data['Data']['Data'])
        if df.empty:
            logging.warning(f"Tidak ada data yang dikembalikan dari API untuk {symbol}-{currency} di {exchange_name}.")
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
        logging.error(f"Format data dari API tidak sesuai harapan. Missing key: {e}. Data: {data}")
        return pd.DataFrame()
    except Exception as e:
        logging.error(f"Error tidak diketahui saat mengambil data: {e}")
        return pd.DataFrame()

# ... (Sisa kode `strategy_state`, `find_pivots`, `run_strategy_logic` tetap sama) ...
# Fungsi `find_pivots` dan `run_strategy_logic` TIDAK PERLU diubah karena sudah menggunakan
# `df['high']`, `df['low']`, `df['close']` yang didapat dari `fetch_candles`.
# `strategy_state` juga tidak perlu diubah.

# --- FUNGSI UTAMA TRADING LOOP ---
def start_trading(settings):
    # Pastikan 'symbol' dan 'currency' ada di settings
    current_symbol = settings.get('symbol')
    current_currency = settings.get('currency')
    current_exchange = settings.get('exchange', 'CCCAGG') # Default ke CCCAGG jika tidak ada

    if not current_symbol or not current_currency:
        logging.error("Simbol crypto atau mata uang kutipan belum diatur dengan benar. Silakan cek Pengaturan.")
        return

    logging.info(f"Memulai trading untuk {current_symbol}-{current_currency} di {current_exchange} dengan interval {settings['refresh_interval_seconds']} detik.")
    logging.info(f"Parameter: LeftStr={settings['left_strength']}, RightStr={settings['right_strength']}, "
                 f"ProfitTrailActiv={settings['profit_target_percent_activation']}%, TrailGap={settings['trailing_stop_gap_percent']}%, EmergSL={settings['emergency_sl_percent']}%")
    logging.info(f"SecureFIB: {settings['enable_secure_fib']}, SecureFIBCheck: {settings['secure_fib_check_price']}")

    if settings.get('api_key') == "YOUR_API_KEY_HERE" or not settings.get('api_key'):
        logging.error("API Key belum diatur. Silakan atur melalui menu Settings.")
        return
    
    global strategy_state # Reset state setiap kali start_trading dipanggil
    strategy_state = {
        "last_signal_type": 0, "final_pivot_high_price_confirmed": None, "final_pivot_low_price_confirmed": None,
        "high_price_for_fib": None, "high_bar_index_for_fib": None, "active_fib_level": None,
        "active_fib_line_start_index": None, "entry_price_custom": None, "highest_price_for_trailing": None,
        "trailing_tp_active_custom": False, "current_trailing_stop_level": None,
        "emergency_sl_level_custom": None, "position_size": 0,
    }
    
    initial_fetch_limit = max(settings['data_limit'], settings['left_strength'] + settings['right_strength'] + 50) 
    initial_fetch_limit = min(initial_fetch_limit, 1999)

    all_data_df = fetch_candles(current_symbol, current_currency, initial_fetch_limit, current_exchange, settings['api_key'])

    if all_data_df.empty:
        logging.error(f"Tidak ada data awal yang bisa diambil untuk {current_symbol}-{current_currency} di {current_exchange}. Menghentikan trading.")
        return

    logging.info(f"Memproses {len(all_data_df) - 1} candle historis awal untuk inisialisasi state...")
    for i in range(settings['left_strength'] + settings['right_strength'], len(all_data_df) -1): 
        historical_slice = all_data_df.iloc[:i+1]
        run_strategy_logic(historical_slice, settings) # `settings` dilewatkan karena run_strategy_logic membutuhkannya
        if strategy_state["position_size"] > 0:
            strategy_state["position_size"] = 0 
    logging.info("Inisialisasi state selesai.")

    try:
        while True:
            new_data_df = fetch_candles(current_symbol, current_currency, initial_fetch_limit, current_exchange, settings['api_key'])

            if new_data_df.empty:
                logging.warning(f"Gagal mengambil data baru untuk {current_symbol}-{current_currency}. Mencoba lagi nanti.")
                time.sleep(settings['refresh_interval_seconds'])
                continue
            
            # ... (sisa logika penggabungan dan pemrosesan data di loop while true tetap sama) ...
            # Bagian ini:
            combined_df = pd.concat([all_data_df, new_data_df])
            combined_df = combined_df[~combined_df.index.duplicated(keep='last')]
            combined_df.sort_index(inplace=True)
            
            last_known_index = all_data_df.index[-1] if not all_data_df.empty else None
            all_data_df = combined_df

            if last_known_index:
                try:
                    start_processing_idx_loc = all_data_df.index.get_loc(last_known_index) + 1
                except KeyError: 
                    start_processing_idx_loc = max(0, len(all_data_df) - 5) 
            else: 
                start_processing_idx_loc = settings['left_strength'] + settings['right_strength']


            if start_processing_idx_loc >= len(all_data_df):
                logging.info(f"Tidak ada candle baru untuk diproses ({current_symbol}-{current_currency}) sejak {last_known_index}. Menunggu...")
            else:
                logging.info(f"Memproses candle ({current_symbol}-{current_currency}) dari {all_data_df.index[start_processing_idx_loc]} hingga {all_data_df.index[-1]}")
                for i in range(start_processing_idx_loc, len(all_data_df)):
                    current_processing_slice = all_data_df.iloc[:i+1] 
                    if len(current_processing_slice) < settings['left_strength'] + settings['right_strength'] + 1:
                        continue
                    logging.info(f"--- Menganalisa candle: {current_processing_slice.index[-1]} (Close: {current_processing_slice.iloc[-1]['close']}) ---")
                    run_strategy_logic(current_processing_slice, settings) # settings dilewatkan
            
            max_hist_len = initial_fetch_limit * 2
            if len(all_data_df) > max_hist_len:
                all_data_df = all_data_df.iloc[-max_hist_len:]

            time.sleep(settings['refresh_interval_seconds'])

    except KeyboardInterrupt:
        logging.info("Proses trading dihentikan oleh pengguna.")
    except Exception as e:
        logging.exception(f"Error tak terduga di loop trading utama: {e}")


# --- MENU UTAMA ---
def main_menu():
    settings = load_settings()
    while True:
        # Pastikan symbol dan currency ada untuk tampilan, gunakan default jika tidak ada
        display_symbol = settings.get('symbol', 'N/A')
        display_currency = settings.get('currency', 'N/A')
        display_exchange = settings.get('exchange', 'CCCAGG')
        refresh_interval = settings.get('refresh_interval_seconds', 15)

        print("\n========= Crypto Strategy Runner =========")
        print(f"Pair: {display_symbol}-{display_currency} | Exchange: {display_exchange} | Interval: {refresh_interval}s")
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
    # Sisa dari kode Anda seperti `strategy_state`, `find_pivots`, `run_strategy_logic`
    # diletakkan di sini atau diimpor jika berada di file terpisah.
    # Untuk contoh ini, kita asumsikan semua ada dalam satu file.
    
    # --- LOGIKA STRATEGI (Dipotong untuk keringkasan, kode ini sama seperti sebelumnya) ---
    strategy_state = {
        "last_signal_type": 0, "final_pivot_high_price_confirmed": None, "final_pivot_low_price_confirmed": None,
        "high_price_for_fib": None, "high_bar_index_for_fib": None, "active_fib_level": None,
        "active_fib_line_start_index": None, "entry_price_custom": None, "highest_price_for_trailing": None,
        "trailing_tp_active_custom": False, "current_trailing_stop_level": None,
        "emergency_sl_level_custom": None, "position_size": 0,
    }

    def find_pivots(series, left_strength, right_strength, is_high=True):
        pivots = [None] * len(series)
        for i in range(left_strength, len(series) - right_strength):
            is_pivot = True
            for j in range(1, left_strength + 1):
                if is_high:
                    if series[i] <= series[i-j]: is_pivot = False; break
                else: 
                    if series[i] >= series[i-j]: is_pivot = False; break
            if not is_pivot: continue
            for j in range(1, right_strength + 1):
                if is_high:
                    if series[i] < series[i+j]: is_pivot = False; break 
                else: 
                    if series[i] > series[i+j]: is_pivot = False; break 
            if is_pivot:
                pivots[i] = series[i] 
        return pivots

    def run_strategy_logic(df, settings_param): # Ganti nama parameter agar tidak bentrok dengan modul `settings`
        global strategy_state 
        strategy_state["final_pivot_high_price_confirmed"] = None
        strategy_state["final_pivot_low_price_confirmed"] = None
        left_strength = settings_param['left_strength']
        right_strength = settings_param['right_strength']
        raw_pivot_highs = find_pivots(df['high'], left_strength, right_strength, is_high=True)
        raw_pivot_lows  = find_pivots(df['low'],  left_strength, right_strength, is_high=False)
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
            logging.info(f"PIVOT HIGH Terkonfirmasi: {strategy_state['final_pivot_high_price_confirmed']} pada (event time {df.index[idx_pivot_event_high]})")
        if raw_pivot_low_price_at_event is not None and strategy_state["last_signal_type"] != -1:
            strategy_state["final_pivot_low_price_confirmed"] = raw_pivot_low_price_at_event
            strategy_state["last_signal_type"] = -1
            logging.info(f"PIVOT LOW Terkonfirmasi: {strategy_state['final_pivot_low_price_confirmed']} pada (event time {df.index[idx_pivot_event_low]})")
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
                    if settings_param["enable_secure_fib"]:
                        price_to_check_str = settings_param["secure_fib_check_price"].lower()
                        price_val_current_candle = current_candle[price_to_check_str]
                        if price_val_current_candle > calculated_fib_level:
                            is_fib_late = True
                    if is_fib_late:
                        logging.info(f"FIB Terlambat ({calculated_fib_level:.5f}) diabaikan. Harga cek ({settings_param['secure_fib_check_price']}: {price_val_current_candle:.5f}) sudah melewati.")
                        strategy_state["active_fib_level"] = None
                        strategy_state["active_fib_line_start_index"] = None
                    else:
                        logging.info(f"FIB 0.5 Aktif: {calculated_fib_level:.5f} (dari High {strategy_state['high_price_for_fib']:.5f} & Low {current_low_price:.5f})")
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
                    strategy_state["emergency_sl_level_custom"] = strategy_state["entry_price_custom"] * (1 - settings_param["emergency_sl_percent"] / 100.0)
                    logging.info(f"BUY ENTRY @ {strategy_state['entry_price_custom']:.5f} (FIB {strategy_state['active_fib_level']:.5f} terlewati)")
                    logging.info(f"   Emergency SL: {strategy_state['emergency_sl_level_custom']:.5f}")
                logging.debug(f"Garis FIB {strategy_state['active_fib_level']:.5f} dipotong.")
                strategy_state["active_fib_level"] = None 
                strategy_state["active_fib_line_start_index"] = None
        if strategy_state["position_size"] > 0:
            strategy_state["highest_price_for_trailing"] = max(strategy_state["highest_price_for_trailing"] or current_candle['high'], current_candle['high'])
            if not strategy_state["trailing_tp_active_custom"] and strategy_state["entry_price_custom"] is not None:
                profit_percent = ((strategy_state["highest_price_for_trailing"] - strategy_state["entry_price_custom"]) / strategy_state["entry_price_custom"]) * 100.0
                if profit_percent >= settings_param["profit_target_percent_activation"]:
                    strategy_state["trailing_tp_active_custom"] = True
                    logging.info(f"Trailing TP Aktif. Profit: {profit_percent:.2f}%, High: {strategy_state['highest_price_for_trailing']:.5f}")
            if strategy_state["trailing_tp_active_custom"] and strategy_state["highest_price_for_trailing"] is not None:
                potential_new_stop_price = strategy_state["highest_price_for_trailing"] * (1 - (settings_param["trailing_stop_gap_percent"] / 100.0))
                if strategy_state["current_trailing_stop_level"] is None or potential_new_stop_price > strategy_state["current_trailing_stop_level"]:
                    strategy_state["current_trailing_stop_level"] = potential_new_stop_price
                    logging.debug(f"Trailing Stop Level diupdate ke: {strategy_state['current_trailing_stop_level']:.5f}")
            final_stop_for_exit = strategy_state["emergency_sl_level_custom"]
            exit_comment = "Emergency SL"
            if strategy_state["trailing_tp_active_custom"] and strategy_state["current_trailing_stop_level"] is not None:
                if strategy_state["current_trailing_stop_level"] > strategy_state["emergency_sl_level_custom"]:
                    final_stop_for_exit = strategy_state["current_trailing_stop_level"]
                    exit_comment = "Trailing Stop"
            if final_stop_for_exit is not None and current_candle['low'] <= final_stop_for_exit:
                exit_price = min(current_candle['open'], final_stop_for_exit) 
                pnl = (exit_price - strategy_state["entry_price_custom"]) / strategy_state["entry_price_custom"] * 100.0 if strategy_state["entry_price_custom"] else 0
                logging.info(f"EXIT ORDER @ {exit_price:.5f} oleh {exit_comment}. PnL: {pnl:.2f}%")
                strategy_state["position_size"] = 0; strategy_state["entry_price_custom"] = None; strategy_state["highest_price_for_trailing"] = None
                strategy_state["trailing_tp_active_custom"] = False; strategy_state["current_trailing_stop_level"] = None; strategy_state["emergency_sl_level_custom"] = None
        if strategy_state["position_size"] > 0:
            plot_stop_level = strategy_state["emergency_sl_level_custom"]
            if strategy_state["trailing_tp_active_custom"] and strategy_state["current_trailing_stop_level"] and strategy_state["current_trailing_stop_level"] > strategy_state["emergency_sl_level_custom"]:
                plot_stop_level = strategy_state["current_trailing_stop_level"]
            logging.debug(f"Posisi Aktif. Entry: {strategy_state.get('entry_price_custom', 0):.5f}, Current SL: {plot_stop_level:.5f if plot_stop_level else 'N/A'}")

    main_menu()
