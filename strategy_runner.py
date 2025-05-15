# ... (bagian atas skrip tetap sama) ...

# --- FUNGSI PENGATURAN ---
def load_settings():
    default_settings = {
        "api_key": "YOUR_API_KEY_HERE",
        "symbol": "BTC",
        "currency": "USD",
        "crypto_pair": "BTC-USD", # Untuk display, akan diupdate
        "exchange": "Coinbase",
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
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r') as f:
            try:
                loaded_settings = json.load(f)
                # Migrasi dari format lama jika 'symbol' atau 'currency' tidak ada
                if "symbol" not in loaded_settings or "currency" not in loaded_settings:
                    if "crypto_pair" in loaded_settings and '-' in loaded_settings["crypto_pair"]:
                        parts = loaded_settings["crypto_pair"].split('-', 1)
                        loaded_settings["symbol"] = parts[0].upper()
                        loaded_settings["currency"] = parts[1].upper()
                    else: # Fallback jika crypto_pair juga tidak ada atau formatnya aneh
                        loaded_settings["symbol"] = default_settings["symbol"]
                        loaded_settings["currency"] = default_settings["currency"]
                
                # Pastikan semua keys dari default ada
                settings = default_settings.copy()
                settings.update(loaded_settings)
                # Update crypto_pair untuk display konsisten dengan symbol dan currency
                settings["crypto_pair"] = f"{settings['symbol']}-{settings['currency']}"
                return settings
            except json.JSONDecodeError:
                logging.error("Error membaca settings.json. Menggunakan default.")
    # Jika file tidak ada atau error, buat crypto_pair dari default symbol/currency
    default_settings["crypto_pair"] = f"{default_settings['symbol']}-{default_settings['currency']}"
    return default_settings

def save_settings(settings):
    # Pastikan crypto_pair konsisten sebelum menyimpan
    settings["crypto_pair"] = f"{settings['symbol']}-{settings['currency']}"
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=4)
    logging.info("Pengaturan disimpan ke settings.json")

def settings_menu(current_settings):
    print("\n--- Menu Pengaturan ---")
    new_settings = current_settings.copy() # Salin untuk dimodifikasi
    try:
        new_settings["api_key"] = input(f"API Key CryptoCompare [{current_settings['api_key']}]: ") or current_settings['api_key']
        
        # Meminta Symbol dan Currency secara terpisah
        new_settings["symbol"] = (input(f"Simbol Crypto Dasar (misal BTC) [{current_settings['symbol']}]: ") or current_settings['symbol']).upper()
        new_settings["currency"] = (input(f"Simbol Crypto Quote/Mata Uang (misal USD, USDT) [{current_settings['currency']}]: ") or current_settings['currency']).upper()
        
        # crypto_pair akan diupdate otomatis di save_settings atau saat load berikutnya
        # Untuk tampilan di menu utama, kita bisa update di sini juga
        # new_settings["crypto_pair"] = f"{new_settings['symbol']}-{new_settings['currency']}" # Dihandle di save_settings

        current_exchange_display = current_settings['exchange']
        if current_exchange_display == "CCCAGG":
            current_exchange_display = "AGREGAT (CCCAGG)"
        
        exchange_input = input(f"Exchange (misal Coinbase, Binance. KOSONGKAN untuk AGREGAT) [{current_exchange_display}]: ")
        if not exchange_input.strip() and current_settings['exchange'] == "CCCAGG": # User mengosongkan, dan sebelumnya sudah CCCAGG
             new_settings['exchange'] = "CCCAGG"
        elif not exchange_input.strip(): # User mengosongkan, sebelumnya BUKAN CCCAGG (atau baru)
            new_settings['exchange'] = "CCCAGG"
            logging.info("Exchange diatur ke AGREGAT (CCCAGG) karena input kosong.")
        else:
            new_settings['exchange'] = exchange_input # Ambil input user jika tidak kosong

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
        enable_sf_input = input(f"Aktifkan Secure FIB? (true/false) [{current_settings['enable_secure_fib']}]: ").strip().lower()
        if enable_sf_input == 'true':
            new_settings['enable_secure_fib'] = True
        elif enable_sf_input == 'false':
            new_settings['enable_secure_fib'] = False
        # Jika input lain, biarkan nilai lama (sudah di-copy dari current_settings)

        secure_fib_price_input = (input(f"Harga Candle untuk Cek Secure FIB (Close/High) [{current_settings['secure_fib_check_price']}]: ") or current_settings['secure_fib_check_price']).capitalize()
        if secure_fib_price_input in ["Close", "High"]:
            new_settings["secure_fib_check_price"] = secure_fib_price_input
        else:
            print("Pilihan harga Secure FIB tidak valid. Menggunakan nilai sebelumnya.")

        save_settings(new_settings)
        return new_settings # Kembalikan settings yang sudah diperbarui
    except ValueError:
        print("Input tidak valid. Pengaturan tidak diubah.")
        return current_settings # Kembalikan settings lama jika ada error
    except Exception as e:
        logging.error(f"Terjadi error di menu pengaturan: {e}")
        return current_settings

# ... (sisa skrip, termasuk fetch_candles, run_strategy_logic, start_trading, main_menu, tetap sama) ...

# Perlu juga update di main_menu untuk menampilkan crypto_pair yang sudah terformat dengan benar
def main_menu():
    settings = load_settings() # load_settings sekarang memastikan crypto_pair konsisten
    while True:
        # Pastikan crypto_pair selalu terupdate dari symbol dan currency saat ini
        current_display_pair = f"{settings['symbol']}-{settings['currency']}"
        current_display_exchange = settings['exchange']
        if current_display_exchange == "CCCAGG":
            current_display_exchange = "AGREGAT"

        print("\n========= Crypto Strategy Runner =========")
        print(f"Pair: {current_display_pair} | Exchange: {current_display_exchange} | Interval: {settings['refresh_interval_seconds']}s")
        print("--------------------------------------")
        print("1. Mulai Analisa Realtime")
        print("2. Pengaturan")
        print("3. Keluar")
        choice = input("Pilihan Anda: ")

        if choice == '1':
            start_trading(settings)
        elif choice == '2':
            settings = settings_menu(settings) # settings akan diupdate di sini
        elif choice == '3':
            logging.info("Aplikasi ditutup.")
            break
        else:
            print("Pilihan tidak valid.")

if __name__ == "__main__":
    main_menu()
