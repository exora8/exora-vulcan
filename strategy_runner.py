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
                return json.load(f)
            except json.JSONDecodeError:
                logging.error("Error membaca settings.json. Menggunakan default.")
    # Default settings jika file tidak ada atau error
    return {
        "api_key": "YOUR_API_KEY_HERE", # GANTI DENGAN API KEY ANDA
        "crypto_pair": "BTC-USD", # Untuk tampilan
        "symbol": "BTC",          # Untuk API CryptoCompare
        "currency": "USD",        # Untuk API CryptoCompare
        "exchange": "Coinbase",   # Exchange di CryptoCompare
        "refresh_interval_seconds": 15,
        "data_limit": 250, # Jumlah candle yang diambil lebih banyak untuk kalkulasi pivot
        "left_strength": 50,
        "right_strength": 150,
        "profit_target_percent_activation": 5.0,
        "trailing_stop_gap_percent": 5.0,
        "emergency_sl_percent": 10.0,
        "enable_secure_fib": True,
        "secure_fib_check_price": "Close" # "Close" atau "High"
    }

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=4)
    logging.info("Pengaturan disimpan ke settings.json")

def settings_menu(current_settings):
    print("\n--- Menu Pengaturan ---")
    new_settings = current_settings.copy()
    try:
        new_settings["api_key"] = input(f"API Key CryptoCompare [{current_settings['api_key']}]: ") or current_settings['api_key']
        
        pair_input = input(f"Pasangan Crypto (misal BTC-USD) [{current_settings['crypto_pair']}]: ") or current_settings['crypto_pair']
        if '-' in pair_input:
            new_settings["symbol"] = pair_input.split('-')[0].upper()
            new_settings["currency"] = pair_input.split('-')[1].upper()
            new_settings["crypto_pair"] = f"{new_settings['symbol']}-{new_settings['currency']}"
        else:
            print("Format pasangan crypto salah. Menggunakan nilai sebelumnya.")

        new_settings["exchange"] = input(f"Exchange (misal Coinbase, Kraken, Binance) [{current_settings['exchange']}]: ") or current_settings['exchange']
        new_settings["refresh_interval_seconds"] = int(input(f"Interval Refresh (detik) [{current_settings['refresh_interval_seconds']}]: ") or current_settings['refresh_interval_seconds'])
        new_settings["data_limit"] = int(input(f"Limit Data Candle (untuk analisis awal) [{current_settings['data_limit']}]: ") or current_settings['data_limit'])
        
        print("\n-- Parameter Pivot --")
        new_settings["left_strength"] = int(input(f"Left Strength (Bars Kiri) [{current_settings['left_strength']}]: ") or current_settings['left_strength'])
        new_settings["right_strength"] = int(input(f"Right Strength (Bars Kanan - Konfirmasi) [{current_settings['right_strength']}]: ") or current_settings['right_strength'])

        print("\n-- Parameter Trading --")
        new_settings["profit_target_percent_activation"] = float(input(f"Profit % untuk Aktivasi Trailing TP [{current_settings['profit_target_percent_activation']}]: ") or current_settings['profit_target_percent_activation'])
        new_settings["trailing_stop_gap_percent"] = float(input(f"Gap Trailing TP % dari High [{current_settings['trailing_stop_gap_percent']}]: ") or current_settings['trailing_stop_gap_percent'])
        new_settings["emergency_sl_percent"] = float(input(f"Emergency SL % dari Entry [{current_settings['emergency_sl_percent']}]: ") or current_settings['emergency_sl_percent'])
        
        print("\n-- Fitur Secure FIB --")
        enable_sf_input = input(f"Aktifkan Secure FIB? (true/false) [{current_settings['enable_secure_fib']}]: ").lower()
        new_settings["enable_secure_fib"] = True if enable_sf_input == 'true' else (False if enable_sf_input == 'false' else current_settings['enable_secure_fib'])
        
        secure_fib_price_input = input(f"Harga Candle untuk Cek Secure FIB (Close/High) [{current_settings['secure_fib_check_price']}]: ").capitalize()
        if secure_fib_price_input in ["Close", "High"]:
            new_settings["secure_fib_check_price"] = secure_fib_price_input
        else:
            print("Pilihan harga Secure FIB tidak valid. Menggunakan nilai sebelumnya.")

        save_settings(new_settings)
        return new_settings
    except ValueError:
        print("Input tidak valid. Pengaturan tidak diubah.")
        return current_settings

# --- FUNGSI PENGAMBILAN DATA ---
def fetch_candles(symbol, currency, limit, exchange_name, api_key):
    # Kita butuh data ekstra untuk kalkulasi pivot di awal
    # rightStrength adalah krusial karena pivot baru valid setelah N bar ke kanan
    # Jadi total limit = limit yg mau dianalisa + left_strength + right_strength
    # Namun, API mungkin punya batasannya sendiri, jadi kita ambil `limit` saja dan pastikan `limit` cukup besar.
    # CryptoCompare `limit` adalah jumlah data points *sebelum* `toTs` (jika ada). Jika tidak ada `toTs`, berarti `limit` data terbaru.
    # Untuk `histohour` atau `histominute`, limit maksimal biasanya 2000.
    
    url = f"https://min-api.cryptocompare.com/data/v2/histohour" # Bisa ganti ke histominute jika perlu
    # Untuk mendapatkan data terbaru, kita tidak set 'toTs'
    # Limit di CryptoCompare adalah jumlah data points, bukan index. 
    # Jadi jika kita mau `limit` data terbaru, kita set `limit` tersebut.
    # Pastikan `limit` cukup besar untuk `leftStrength` dan `rightStrength`.
    # Misal, jika rightStrength=150, kita butuh setidaknya 150 candle setelah potensi pivot.
    
    params = {
        "fsym": symbol,
        "tsym": currency,
        "limit": limit -1, # API mengembalikan limit+1 data points
        "e": exchange_name,
        "api_key": api_key
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status() # Raise HTTPError untuk bad responses (4XX atau 5XX)
        data = response.json()
        if data['Response'] == 'Error':
            logging.error(f"API Error: {data['Message']}")
            return pd.DataFrame()

        df = pd.DataFrame(data['Data']['Data'])
        df['timestamp'] = pd.to_datetime(df['time'], unit='s')
        df = df.set_index('timestamp')
        df = df[['open', 'high', 'low', 'close', 'volumefrom']] # volumefrom adalah volume base currency
        df.rename(columns={'volumefrom': 'volume'}, inplace=True)
        return df
    except requests.exceptions.RequestException as e:
        logging.error(f"Kesalahan koneksi saat mengambil data: {e}")
        return pd.DataFrame()
    except KeyError:
        logging.error("Format data dari API tidak sesuai harapan.")
        return pd.DataFrame()
    except Exception as e:
        logging.error(f"Error tidak diketahui saat mengambil data: {e}")
        return pd.DataFrame()

# --- LOGIKA STRATEGI ---
# Variabel state yang akan di-manage secara global dalam konteks 'start_trading'
strategy_state = {
    "last_signal_type": 0, # 0: none, 1: high, -1: low
    "final_pivot_high_price_confirmed": None, # Harga pivot high yang terkonfirmasi (terjadi di index - right_strength)
    "final_pivot_low_price_confirmed": None,  # Harga pivot low yang terkonfirmasi
    
    "high_price_for_fib": None,
    "high_bar_index_for_fib": None, # Index di DataFrame asli
    
    "active_fib_level": None,
    "active_fib_line_start_index": None, # Index di DataFrame asli

    # Status Trading
    "entry_price_custom": None,
    "highest_price_for_trailing": None,
    "trailing_tp_active_custom": False,
    "current_trailing_stop_level": None,
    "emergency_sl_level_custom": None,
    "position_size": 0, # 0 = no position, >0 = long position
}

def find_pivots(series, left_strength, right_strength, is_high=True):
    pivots = [None] * len(series)
    for i in range(left_strength, len(series) - right_strength):
        is_pivot = True
        # Cek Kiri
        for j in range(1, left_strength + 1):
            if is_high:
                if series[i] <= series[i-j]: is_pivot = False; break
            else: # is_low
                if series[i] >= series[i-j]: is_pivot = False; break
        if not is_pivot: continue

        # Cek Kanan
        for j in range(1, right_strength + 1):
            if is_high:
                if series[i] < series[i+j]: is_pivot = False; break # PineScript ta.pivothigh: high[rs] < ph
            else: # is_low
                if series[i] > series[i+j]: is_pivot = False; break # PineScript ta.pivotlow: low[rs] > pl
        if is_pivot:
            pivots[i] = series[i] # Pivot terdeteksi di index i, akan dikonfirmasi nanti
    return pivots


def run_strategy_logic(df, settings):
    global strategy_state # Menggunakan state global

    # Reset temporary confirmed pivots untuk iterasi ini
    strategy_state["final_pivot_high_price_confirmed"] = None
    strategy_state["final_pivot_low_price_confirmed"] = None
    
    # Ambil parameter dari settings untuk kemudahan
    left_strength = settings['left_strength']
    right_strength = settings['right_strength']

    # 1. Deteksi Pivot (RAW)
    # Pivot baru dikonfirmasi setelah `right_strength` bar. Jadi, raw pivot yang terdeteksi di index `k`
    # sebenarnya adalah pivot yang terjadi di `k`, dan sinyalnya baru muncul di `k + right_strength`.
    # Namun, fungsi `ta.pivothigh` di PineScript mengembalikan harga pivot pada bar dimana pivot itu terjadi,
    # tapi hanya setelah `right_strength` bar berlalu.
    # Kita akan menghitung pivot pada keseluruhan df, lalu memprosesnya.
    
    raw_pivot_highs = find_pivots(df['high'], left_strength, right_strength, is_high=True)
    raw_pivot_lows  = find_pivots(df['low'],  left_strength, right_strength, is_high=False)

    # Iterasi pada data yang cukup untuk konfirmasi (mulai dari `right_strength` dari akhir)
    # Ini simulasi, jadi kita proses bar terakhir dari data yang diterima.
    # Anggap `df` adalah data historis sampai bar *sebelum* bar saat ini (current_bar).
    # Kita akan memproses bar terakhir dari `df` sebagai "current_bar" yang baru close.
    
    current_bar_index_in_df = len(df) - 1 # Index dari bar terakhir dalam DataFrame
    if current_bar_index_in_df < 0 : return # Tidak ada data

    # Cek apakah ada pivot yang *terkonfirmasi* di bar saat ini
    # Pivot yang terjadi di `idx_pivot_event = current_bar_index_in_df - right_strength`
    # baru akan terkonfirmasi di `current_bar_index_in_df`.
    
    idx_pivot_event_high = current_bar_index_in_df - right_strength
    raw_pivot_high_price_at_event = None
    if idx_pivot_event_high >= 0 and idx_pivot_event_high < len(raw_pivot_highs):
        raw_pivot_high_price_at_event = raw_pivot_highs[idx_pivot_event_high]

    idx_pivot_event_low = current_bar_index_in_df - right_strength
    raw_pivot_low_price_at_event = None
    if idx_pivot_event_low >= 0 and idx_pivot_event_low < len(raw_pivot_lows):
        raw_pivot_low_price_at_event = raw_pivot_lows[idx_pivot_event_low]

    # Logika Alternating Pivot
    if raw_pivot_high_price_at_event is not None and strategy_state["last_signal_type"] != 1:
        strategy_state["final_pivot_high_price_confirmed"] = raw_pivot_high_price_at_event # Ini harga di idx_pivot_event_high
        strategy_state["last_signal_type"] = 1
        logging.info(f"PIVOT HIGH Terkonfirmasi: {strategy_state['final_pivot_high_price_confirmed']} pada (event time {df.index[idx_pivot_event_high]})")
        # plotshape(finalPivotHighPrice, offset=-rightStrength) -> ini artinya plot di idx_pivot_event_high

    if raw_pivot_low_price_at_event is not None and strategy_state["last_signal_type"] != -1:
        # PineScript: `if na(finalPivotHighPrice)` -> ini agak tricky, mungkin maksudnya jika tidak ada high baru di bar yang sama
        # Untuk Python, kita anggap jika high tidak terkonfirmasi di bar ini, dan low terkonfirmasi, maka proses low.
        # Atau, jika high sudah ada sebelumnya (dari bar lain).
        # Simplifikasi: Cukup alternating.
        strategy_state["final_pivot_low_price_confirmed"] = raw_pivot_low_price_at_event # Ini harga di idx_pivot_event_low
        strategy_state["last_signal_type"] = -1
        logging.info(f"PIVOT LOW Terkonfirmasi: {strategy_state['final_pivot_low_price_confirmed']} pada (event time {df.index[idx_pivot_event_low]})")


    # --- Logika Konfirmasi FIB 0.5 Dinamis ---
    current_candle = df.iloc[current_bar_index_in_df] # Candle saat ini (baru close)

    # Kondisi 1: HIGH baru terkonfirmasi (dari iterasi ini)
    if strategy_state["final_pivot_high_price_confirmed"] is not None:
        strategy_state["high_price_for_fib"] = strategy_state["final_pivot_high_price_confirmed"]
        strategy_state["high_bar_index_for_fib"] = idx_pivot_event_high # Index terjadinya pivot
        
        if strategy_state["active_fib_level"] is not None: # Ada FIB aktif dari pair sebelumnya
            logging.debug("Menghapus FIB line visual lama karena HIGH baru.")
            strategy_state["active_fib_level"] = None
            strategy_state["active_fib_line_start_index"] = None

    # Kondisi 2: LOW baru terkonfirmasi (dari iterasi ini)
    if strategy_state["final_pivot_low_price_confirmed"] is not None:
        if strategy_state["high_price_for_fib"] is not None and strategy_state["high_bar_index_for_fib"] is not None:
            current_low_price = strategy_state["final_pivot_low_price_confirmed"]
            current_low_bar_index = idx_pivot_event_low # Index terjadinya pivot low

            if current_low_bar_index > strategy_state["high_bar_index_for_fib"]: # Pastikan LOW setelah HIGH
                calculated_fib_level = (strategy_state["high_price_for_fib"] + current_low_price) / 2.0
                is_fib_late = False

                if settings["enable_secure_fib"]:
                    price_to_check_str = settings["secure_fib_check_price"].lower()
                    price_val_current_candle = current_candle[price_to_check_str] # Menggunakan candle saat ini (dimana low dikonfirmasi)
                    
                    if price_val_current_candle > calculated_fib_level:
                        is_fib_late = True
                
                if is_fib_late:
                    logging.info(f"FIB Terlambat ({calculated_fib_level:.5f}) diabaikan. Harga cek ({settings['secure_fib_check_price']}: {price_val_current_candle:.5f}) sudah melewati.")
                    strategy_state["active_fib_level"] = None
                    strategy_state["active_fib_line_start_index"] = None
                else:
                    logging.info(f"FIB 0.5 Aktif: {calculated_fib_level:.5f} (dari High {strategy_state['high_price_for_fib']:.5f} di {df.index[strategy_state['high_bar_index_for_fib']]} & Low {current_low_price:.5f} di {df.index[current_low_bar_index]})")
                    strategy_state["active_fib_level"] = calculated_fib_level
                    strategy_state["active_fib_line_start_index"] = current_low_bar_index # Garis dimulai dari konfirmasi low
                
                # HIGH ini sudah diproses
                strategy_state["high_price_for_fib"] = None
                strategy_state["high_bar_index_for_fib"] = None

    # Kondisi 3: Cek setiap bar (candle saat ini) apakah memicu entry atau memotong garis FIB
    if strategy_state["active_fib_level"] is not None and strategy_state["active_fib_line_start_index"] is not None:
        is_bullish_candle = current_candle['close'] > current_candle['open']
        is_closed_above_fib = current_candle['close'] > strategy_state["active_fib_level"]

        if is_bullish_candle and is_closed_above_fib:
            if strategy_state["position_size"] == 0: # Jika belum ada posisi
                # --- STRATEGY ENTRY ---
                strategy_state["position_size"] = 1 # Simulasikan ukuran posisi, bisa disesuaikan
                strategy_state["entry_price_custom"] = current_candle['close'] # Entry di close candle trigger
                strategy_state["highest_price_for_trailing"] = strategy_state["entry_price_custom"]
                strategy_state["trailing_tp_active_custom"] = False
                strategy_state["current_trailing_stop_level"] = None
                strategy_state["emergency_sl_level_custom"] = strategy_state["entry_price_custom"] * (1 - settings["emergency_sl_percent"] / 100.0)
                
                logging.info(f"BUY ENTRY @ {strategy_state['entry_price_custom']:.5f} (FIB {strategy_state['active_fib_level']:.5f} terlewati)")
                logging.info(f"   Emergency SL: {strategy_state['emergency_sl_level_custom']:.5f}")
            
            logging.debug(f"Garis FIB {strategy_state['active_fib_level']:.5f} dipotong karena harga close di atasnya.")
            # Reset info garis aktif karena sudah digunakan
            strategy_state["active_fib_level"] = None 
            strategy_state["active_fib_line_start_index"] = None


    # --- Logika Manajemen Posisi ---
    if strategy_state["position_size"] > 0: # Jika sedang dalam posisi
        # Update highest price for trailing
        strategy_state["highest_price_for_trailing"] = max(strategy_state["highest_price_for_trailing"] or current_candle['high'], current_candle['high'])

        # Aktivasi Trailing TP
        if not strategy_state["trailing_tp_active_custom"] and strategy_state["entry_price_custom"] is not None:
            profit_percent = ((strategy_state["highest_price_for_trailing"] - strategy_state["entry_price_custom"]) / strategy_state["entry_price_custom"]) * 100.0
            if profit_percent >= settings["profit_target_percent_activation"]:
                strategy_state["trailing_tp_active_custom"] = True
                logging.info(f"Trailing TP Aktif. Profit: {profit_percent:.2f}%, High: {strategy_state['highest_price_for_trailing']:.5f}")

        # Update Trailing Stop Level
        if strategy_state["trailing_tp_active_custom"] and strategy_state["highest_price_for_trailing"] is not None:
            potential_new_stop_price = strategy_state["highest_price_for_trailing"] * (1 - (settings["trailing_stop_gap_percent"] / 100.0))
            if strategy_state["current_trailing_stop_level"] is None or potential_new_stop_price > strategy_state["current_trailing_stop_level"]:
                strategy_state["current_trailing_stop_level"] = potential_new_stop_price
                logging.debug(f"Trailing Stop Level diupdate ke: {strategy_state['current_trailing_stop_level']:.5f}")
        
        # Cek Kondisi Exit
        final_stop_for_exit = strategy_state["emergency_sl_level_custom"]
        exit_comment = "Emergency SL"
        
        if strategy_state["trailing_tp_active_custom"] and strategy_state["current_trailing_stop_level"] is not None:
            if strategy_state["current_trailing_stop_level"] > strategy_state["emergency_sl_level_custom"]:
                final_stop_for_exit = strategy_state["current_trailing_stop_level"]
                exit_comment = "Trailing Stop"
        
        # Harga low candle saat ini menyentuh stop loss
        if final_stop_for_exit is not None and current_candle['low'] <= final_stop_for_exit:
            exit_price = min(current_candle['open'], final_stop_for_exit) # Asumsi exit terjadi di stop atau open jika gap down
            pnl = (exit_price - strategy_state["entry_price_custom"]) / strategy_state["entry_price_custom"] * 100.0
            logging.info(f"EXIT ORDER @ {exit_price:.5f} oleh {exit_comment}. PnL: {pnl:.2f}%")
            
            # Reset status trading
            strategy_state["position_size"] = 0
            strategy_state["entry_price_custom"] = None
            strategy_state["highest_price_for_trailing"] = None
            strategy_state["trailing_tp_active_custom"] = False
            strategy_state["current_trailing_stop_level"] = None
            strategy_state["emergency_sl_level_custom"] = None
    
    # Visualisasi (opsional, bisa di-extend untuk plot jika pakai matplotlib)
    if strategy_state["position_size"] > 0:
        plot_stop_level = strategy_state["emergency_sl_level_custom"]
        if strategy_state["trailing_tp_active_custom"] and strategy_state["current_trailing_stop_level"] is not None and \
           strategy_state["current_trailing_stop_level"] > strategy_state["emergency_sl_level_custom"]:
            plot_stop_level = strategy_state["current_trailing_stop_level"]
        logging.debug(f"Posisi Aktif. Entry: {strategy_state['entry_price_custom']:.5f}, Current SL: {plot_stop_level:.5f if plot_stop_level else 'N/A'}")


# --- FUNGSI UTAMA TRADING LOOP ---
def start_trading(settings):
    logging.info(f"Memulai trading untuk {settings['crypto_pair']} di {settings['exchange']} dengan interval {settings['refresh_interval_seconds']} detik.")
    logging.info(f"Parameter: LeftStr={settings['left_strength']}, RightStr={settings['right_strength']}, "
                 f"ProfitTrailActiv={settings['profit_target_percent_activation']}%, TrailGap={settings['trailing_stop_gap_percent']}%, EmergSL={settings['emergency_sl_percent']}%")
    logging.info(f"SecureFIB: {settings['enable_secure_fib']}, SecureFIBCheck: {settings['secure_fib_check_price']}")

    if settings['api_key'] == "YOUR_API_KEY_HERE" or not settings['api_key']:
        logging.error("API Key belum diatur. Silakan atur melalui menu Settings.")
        return

    # Mengelola state historis data agar bisa terus dianalisa dengan benar
    # Kita butuh data yang cukup panjang untuk lookback pivot.
    # Minimal (left_strength + right_strength + beberapa buffer).
    # data_limit dari settings adalah berapa banyak candle baru yang mau diambil per fetch.
    # Kita akan ambil data_limit + (left_strength + right_strength) untuk punya cukup histori
    # Tapi API CryptoCompare punya limit sendiri per request (misal 2000 untuk histohour).
    # Jadi, `fetch_limit` harus <= API limit.
    
    # Untuk `histohour`, limitnya 2000. Untuk `histominute`, juga 2000.
    # Kita ambil jumlah data yang cukup untuk kalkulasi awal
    # `settings['data_limit']` bisa kita anggap sebagai jumlah candle yang ingin kita proses dalam satu "batch" baru.
    # Tapi untuk kalkulasi pivot, kita butuh sejarah lebih panjang.
    
    # Untuk keperluan simulasi ini, kita akan fetch sejumlah `data_limit` candle terbaru
    # dan mengasumsikan `data_limit` cukup besar untuk `left+right strength`.
    # Idealnya, kita akan mengakumulasi data.
    
    # Reset state setiap kali start_trading dipanggil
    global strategy_state
    strategy_state = {
        "last_signal_type": 0, "final_pivot_high_price_confirmed": None, "final_pivot_low_price_confirmed": None,
        "high_price_for_fib": None, "high_bar_index_for_fib": None, "active_fib_level": None,
        "active_fib_line_start_index": None, "entry_price_custom": None, "highest_price_for_trailing": None,
        "trailing_tp_active_custom": False, "current_trailing_stop_level": None,
        "emergency_sl_level_custom": None, "position_size": 0,
    }
    
    # Ambil data awal yang cukup untuk kalkulasi pivot
    # Jumlah minimum candle = left_strength + right_strength + 1 (untuk candle saat ini)
    # Kita ambil lebih banyak, misal data_limit dari setting, yang harusnya > dari min_candles
    initial_fetch_limit = max(settings['data_limit'], settings['left_strength'] + settings['right_strength'] + 50) 
    # Pastikan tidak melebihi batas API (misal, 2000 untuk histohour)
    initial_fetch_limit = min(initial_fetch_limit, 1999) # CryptoCompare limit is N+1, so request N-1

    all_data_df = fetch_candles(settings['symbol'], settings['currency'], initial_fetch_limit, settings['exchange'], settings['api_key'])

    if all_data_df.empty:
        logging.error("Tidak ada data awal yang bisa diambil. Menghentikan trading.")
        return

    # Proses data historis awal untuk "memanaskan" state (misal last_signal_type, high_price_for_fib, dll.)
    # Kita tidak melakukan trade pada data historis ini, hanya update state.
    logging.info(f"Memproses {len(all_data_df) - 1} candle historis awal untuk inisialisasi state...")
    # Iterasi dari candle tertua ke yang lebih baru, tapi tidak sampai candle terakhir
    # Karena candle terakhir akan diproses sebagai "current candle" di loop utama.
    for i in range(settings['left_strength'] + settings['right_strength'], len(all_data_df) -1): # -1 agar candle terakhir tidak diproses disini
        # Ambil slice data sampai candle ke-i (inklusif)
        # Ini akan jadi 'df' yang masuk ke run_strategy_logic
        # run_strategy_logic akan memproses candle terakhir dari slice ini
        historical_slice = all_data_df.iloc[:i+1]
        run_strategy_logic(historical_slice, settings)
        # Karena ini pemanasan, kita tidak mau ada BUY/SELL, jadi reset posisi jika terpicu
        if strategy_state["position_size"] > 0:
            strategy_state["position_size"] = 0 
            # Bisa juga reset variabel trading lainnya jika tidak ingin ada sisa state trading dari pemanasan
    logging.info("Inisialisasi state selesai.")


    try:
        while True:
            # Di loop utama, kita hanya fetch 1 candle terbaru (atau beberapa jika ada delay)
            # Untuk CryptoCompare, cara termudah adalah fetch N candle terbaru, lalu bandingkan dengan yang lama.
            # Untuk simplifikasi, kita akan fetch `settings['data_limit']` lagi dan proses hanya yang baru.
            # Ini kurang efisien tapi lebih mudah diimplementasikan untuk contoh ini.
            
            # Fetch data terbaru
            new_data_df = fetch_candles(settings['symbol'], settings['currency'], initial_fetch_limit, settings['exchange'], settings['api_key'])

            if new_data_df.empty:
                logging.warning("Gagal mengambil data baru. Mencoba lagi nanti.")
                time.sleep(settings['refresh_interval_seconds'])
                continue

            # Gabungkan dengan data lama dan buang duplikat, jaga urutan
            # Ini penting jika kita mau menjaga state dengan benar antar fetch
            combined_df = pd.concat([all_data_df, new_data_df])
            combined_df = combined_df[~combined_df.index.duplicated(keep='last')]
            combined_df.sort_index(inplace=True)
            
            # Tentukan candles mana yang baru dan perlu diproses
            # Ambil index terakhir dari all_data_df SEBELUM di-update
            last_known_index = all_data_df.index[-1] if not all_data_df.empty else None
            
            all_data_df = combined_df # Update all_data_df dengan data terbaru

            # Slice data yang akan diproses (semua data setelah last_known_index)
            if last_known_index:
                # Ambil semua bar setelah last_known_index
                # Kita perlu memastikan ada cukup data sebelumnya untuk lookback pivot
                # Jadi, kita akan proses beberapa bar terakhir dari `all_data_df`
                # Atau, idealnya, kita proses per bar yang baru masuk.
                
                # Cari index dari last_known_index di all_data_df yang baru
                try:
                    start_processing_idx_loc = all_data_df.index.get_loc(last_known_index) + 1
                except KeyError: # Jika last_known_index tidak ada lagi (misal data lama sekali)
                    start_processing_idx_loc = max(0, len(all_data_df) - 5) # Proses 5 bar terakhir sebagai fallback
            else: # Data pertama kali
                start_processing_idx_loc = settings['left_strength'] + settings['right_strength'] # Mulai setelah cukup data untuk pivot


            if start_processing_idx_loc >= len(all_data_df):
                logging.info(f"Tidak ada candle baru untuk diproses sejak {last_known_index}. Menunggu...")
            else:
                logging.info(f"Memproses candle dari {all_data_df.index[start_processing_idx_loc]} hingga {all_data_df.index[-1]}")
                # Iterasi untuk setiap candle baru yang perlu diproses
                for i in range(start_processing_idx_loc, len(all_data_df)):
                    # Slice data sampai candle ke-i (inklusif) yang akan diproses
                    # run_strategy_logic akan memproses candle terakhir dari slice ini (yaitu df.iloc[i])
                    current_processing_slice = all_data_df.iloc[:i+1] 
                    
                    # Pastikan slice ini cukup panjang untuk left_strength
                    if len(current_processing_slice) < settings['left_strength'] + settings['right_strength'] + 1:
                        continue # Belum cukup data untuk memproses candle ini

                    logging.info(f"--- Menganalisa candle: {current_processing_slice.index[-1]} (Close: {current_processing_slice.iloc[-1]['close']}) ---")
                    run_strategy_logic(current_processing_slice, settings)
            
            # Jaga ukuran all_data_df agar tidak terlalu besar (misal, 2x initial_fetch_limit)
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
        print("\n========= Crypto Strategy Runner =========")
        print(f"Pair: {settings['crypto_pair']} | Interval: {settings['refresh_interval_seconds']}s")
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
