import requests
import json
import time
import datetime
import math

# --- Konfigurasi Awal & Variabel Global ---
CONFIG = {
    "api_key": "",
    "crypto_pair": "BTC/USD",  # Contoh: BTC/USD, ETH/USDT
    "interval": "histohour", # 'histominute', 'histohour', 'histoday'
    "data_limit": 500, # Jumlah candle untuk di-fetch (pertimbangkan leftStrength + rightStrength)

    # Parameter Pivot (dari Pine Script)
    "leftStrength": 50,
    "rightStrength": 150,

    # Parameter Trading (dari Pine Script)
    "profitTargetPercentForActivation": 5.0,
    "trailingStopGapPercent": 5.0,
    "emergencySlPercent": 10.0,

    # Fitur Secure FIB (dari Pine Script)
    "enableSecureFib": True,
    "secureFibCheckPrice": "Close", # "Close" atau "High"

    # Parameter Strategi (dari Pine Script)
    "initial_capital": 47.0,
    "commission_percent": 0.44
}

# Variabel State (mirip 'var' di Pine Script)
# Akan direset di dalam fungsi utama untuk setiap run
current_equity = CONFIG["initial_capital"]
position_active = False
entry_price_custom = float('nan')
asset_qty = 0.0 # Jumlah crypto yang dipegang

# State untuk Logika Pine Script
lastSignalType = 0 # 0 = netral, 1 = high terakhir, -1 = low terakhir
finalPivotHighPrice = float('nan')
finalPivotLowPrice = float('nan')

highPriceForFib = float('nan')
highBarIndexForFib = float('nan')
activeFibLevel = float('nan')
# activeFibLineStartX tidak relevan untuk CLI, tapi logikanya dipertahankan melalui activeFibLevel

highest_price_for_trailing = float('nan')
trailing_tp_active_custom = False
current_trailing_stop_level = float('nan')
emergency_sl_level_custom = float('nan')

# --- Fungsi Logging ---
def log_event(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

# --- Fungsi API CryptoCompare ---
def get_crypto_data(api_key, fsym, tsym, interval, limit, aggregate=1):
    BASE_URL = "https://min-api.cryptocompare.com/data/v2/"
    endpoint = f"{interval}"
    
    params = {
        "fsym": fsym,
        "tsym": tsym,
        "limit": limit,
        "aggregate": aggregate,
        "api_key": api_key
    }
    try:
        response = requests.get(BASE_URL + endpoint, params=params)
        response.raise_for_status()  # Raises an exception for bad status codes
        data = response.json()
        if data.get("Response") == "Error":
            log_event(f"CryptoCompare API Error: {data.get('Message')}")
            return None
        # Data dari CryptoCompare adalah newest first, kita butuh oldest first
        # Juga, timestamp adalah UNIX
        candles = []
        for item in data.get("Data", {}).get("Data", []):
            candles.append({
                "time": item["time"],
                "open": item["open"],
                "high": item["high"],
                "low": item["low"],
                "close": item["close"],
                "volumefrom": item["volumefrom"] # Atau 'volumeto' tergantung kebutuhan
            })
        return candles # Sudah oldest first karena API mengembalikan data dari dulu ke sekarang jika limit dipakai
    except requests.exceptions.RequestException as e:
        log_event(f"Network error fetching data: {e}")
        return None
    except json.JSONDecodeError:
        log_event("Error decoding JSON response from CryptoCompare.")
        return None

# --- Fungsi Menu Pengaturan ---
def display_settings_menu():
    global CONFIG
    log_event("--- Pengaturan Strategi ---")
    
    temp_api_key = input(f"Masukkan API Key CryptoCompare (saat ini: {'*' * len(CONFIG['api_key']) if CONFIG['api_key'] else 'Kosong'}): ")
    if temp_api_key: CONFIG["api_key"] = temp_api_key

    temp_pair = input(f"Masukkan Pasangan Crypto (misal BTC/USD, saat ini: {CONFIG['crypto_pair']}): ")
    if temp_pair: CONFIG["crypto_pair"] = temp_pair.upper()
    
    temp_interval = input(f"Masukkan Interval (histominute, histohour, histoday, saat ini: {CONFIG['interval']}): ")
    if temp_interval in ["histominute", "histohour", "histoday"]: CONFIG["interval"] = temp_interval
    else: log_event("Interval tidak valid, menggunakan default.")

    while True:
        try:
            temp_limit = input(f"Jumlah candle untuk dianalisis (saat ini: {CONFIG['data_limit']}): ")
            if temp_limit: CONFIG["data_limit"] = int(temp_limit)
            if CONFIG["data_limit"] < CONFIG["leftStrength"] + CONFIG["rightStrength"] + 50: # buffer tambahan
                log_event(f"Data limit harus cukup besar, minimal {CONFIG['leftStrength'] + CONFIG['rightStrength'] + 50}")
                CONFIG["data_limit"] = CONFIG["leftStrength"] + CONFIG['rightStrength'] + 50
            break
        except ValueError:
            log_event("Masukkan angka yang valid untuk jumlah candle.")

    # ... tambahkan input untuk parameter lain jika diinginkan ...
    # Misalnya:
    # try:
    #     ls = input(f"Left Strength (saat ini: {CONFIG['leftStrength']}): ")
    #     if ls: CONFIG['leftStrength'] = int(ls)
    #     rs = input(f"Right Strength (saat ini: {CONFIG['rightStrength']}): ")
    #     if rs: CONFIG['rightStrength'] = int(rs)
    #     # ... dan seterusnya untuk parameter lain
    # except ValueError:
    #     log_event("Input parameter tidak valid, menggunakan default.")

    log_event("Pengaturan disimpan.")
    log_event(f"Crypto: {CONFIG['crypto_pair']}, Interval: {CONFIG['interval']}, Data Limit: {CONFIG['data_limit']}")
    log_event(f"Initial Capital: {CONFIG['initial_capital']}, Commission: {CONFIG['commission_percent']}%")


# --- Fungsi Pine Script TA (Pivot) ---
# Pine Script's pivothigh/low are confirmed `rightStrength` bars AFTER the actual pivot.
# This means when we are at `bar_index`, we look at `bar_index - rightStrength` for the pivot.
def calculate_pivot(data, bar_idx, length_left, length_right, is_high=True):
    if bar_idx < length_left + length_right: # Tidak cukup data untuk konfirmasi pivot yang terjadi length_right bar yang lalu
        return float('nan')

    pivot_candidate_idx = bar_idx - length_right
    
    if pivot_candidate_idx < length_left: # Tidak cukup data di kiri untuk pivot_candidate_idx
        return float('nan')

    price_series = 'high' if is_high else 'low'
    pivot_val = data[pivot_candidate_idx][price_series]

    # Cek kiri
    for i in range(1, length_left + 1):
        if is_high:
            if data[pivot_candidate_idx - i][price_series] > pivot_val:
                return float('nan')
        else: # is_low
            if data[pivot_candidate_idx - i][price_series] < pivot_val:
                return float('nan')
    
    # Cek kanan (relatif terhadap pivot_candidate_idx, hingga bar_idx yang merupakan bar konfirmasi)
    for i in range(1, length_right + 1):
        if is_high:
            # Dalam Pine, pivot high harus STRICTLY greater than highs di kanan dalam window `rightStrength`
            # Namun, implementasi umum adalah >= atau >. Mari kita coba > dulu.
            if data[pivot_candidate_idx + i][price_series] >= pivot_val: 
                return float('nan')
        else: # is_low
            if data[pivot_candidate_idx + i][price_series] <= pivot_val:
                return float('nan')
                
    return pivot_val


# --- Fungsi Utama Strategi ---
def run_strategy():
    global CONFIG, current_equity, position_active, entry_price_custom, asset_qty
    global lastSignalType, finalPivotHighPrice, finalPivotLowPrice
    global highPriceForFib, highBarIndexForFib, activeFibLevel
    global highest_price_for_trailing, trailing_tp_active_custom 
    global current_trailing_stop_level, emergency_sl_level_custom

    # Reset state untuk setiap run
    current_equity = CONFIG["initial_capital"]
    position_active = False
    entry_price_custom = float('nan')
    asset_qty = 0.0
    lastSignalType = 0
    finalPivotHighPrice = float('nan')
    finalPivotLowPrice = float('nan')
    highPriceForFib = float('nan')
    highBarIndexForFib = float('nan')
    activeFibLevel = float('nan')
    highest_price_for_trailing = float('nan')
    trailing_tp_active_custom = False
    current_trailing_stop_level = float('nan')
    emergency_sl_level_custom = float('nan')

    fsym, tsym = CONFIG["crypto_pair"].split('/')
    log_event(f"Fetching {CONFIG['data_limit']} candles for {CONFIG['crypto_pair']} ({CONFIG['interval']})...")
    
    historical_data = get_crypto_data(
        CONFIG["api_key"], 
        fsym, 
        tsym, 
        CONFIG["interval"], 
        CONFIG["data_limit"]
    )

    if not historical_data or len(historical_data) < CONFIG["leftStrength"] + CONFIG["rightStrength"] + 1:
        log_event("Tidak cukup data untuk menjalankan strategi.")
        return

    log_event(f"Data diterima. Memulai simulasi strategi ({len(historical_data)} candles)...")
    
    # Loop utama melalui setiap candle (bar)
    for bar_index in range(len(historical_data)):
        current_bar = historical_data[bar_index]
        close_price = current_bar["close"]
        high_price = current_bar["high"]
        low_price = current_bar["low"]
        open_price = current_bar["open"]
        bar_time = datetime.datetime.fromtimestamp(current_bar["time"]).strftime('%Y-%m-%d %H:%M:%S')

        log_event(f"--- Bar #{bar_index} ({bar_time}) O:{open_price} H:{high_price} L:{low_price} C:{close_price} ---")

        # Simpan close sebelumnya untuk perbandingan position_size
        prev_position_active = position_active 

        # --- Logika Deteksi Pivot ---
        # Pivot dikonfirmasi di bar_index, tapi terjadinya di bar_index - rightStrength
        # Reset final pivots untuk bar ini, akan diisi jika ada yang baru
        temp_finalPivotHighPrice_this_bar = float('nan')
        temp_finalPivotLowPrice_this_bar = float('nan')

        rawPivotHigh = calculate_pivot(historical_data, bar_index, CONFIG["leftStrength"], CONFIG["rightStrength"], is_high=True)
        rawPivotLow = calculate_pivot(historical_data, bar_index, CONFIG["leftStrength"], CONFIG["rightStrength"], is_high=False)

        if not math.isnan(rawPivotHigh):
            pivot_occurrence_idx = bar_index - CONFIG["rightStrength"]
            pivot_occurrence_time = datetime.datetime.fromtimestamp(historical_data[pivot_occurrence_idx]["time"]).strftime('%Y-%m-%d %H:%M:%S')
            log_event(f"Raw Pivot High @ {rawPivotHigh:.5f} (terjadi di bar {pivot_occurrence_idx} - {pivot_occurrence_time}, konfirmasi di bar {bar_index})")
            if lastSignalType != 1:
                finalPivotHighPrice = rawPivotHigh # Ini adalah harga pivot yang terjadi di bar_index - rightStrength
                temp_finalPivotHighPrice_this_bar = finalPivotHighPrice
                lastSignalType = 1
                log_event(f"FINAL Pivot High Terdeteksi: {finalPivotHighPrice:.5f} (konfirmasi). Alert: Pivot High pada {CONFIG['crypto_pair']}")
        
        if not math.isnan(rawPivotLow):
            pivot_occurrence_idx = bar_index - CONFIG["rightStrength"]
            pivot_occurrence_time = datetime.datetime.fromtimestamp(historical_data[pivot_occurrence_idx]["time"]).strftime('%Y-%m-%d %H:%M:%S')
            log_event(f"Raw Pivot Low @ {rawPivotLow:.5f} (terjadi di bar {pivot_occurrence_idx} - {pivot_occurrence_time}, konfirmasi di bar {bar_index})")
            if lastSignalType != -1:
                # Pine: "if na(finalPivotHighPrice)" -> ini berarti jika belum ada High yg valid menunggu, atau high sebelumnya sdh diproses
                # Dalam implementasi ini, highPriceForFib yang belum di-consume menandakan ada high yang menunggu.
                if math.isnan(highPriceForFib): # atau if math.isnan(finalPivotHighPrice) SEBELUM diset di atas jika ada rawPivotHigh
                    finalPivotLowPrice = rawPivotLow # Ini adalah harga pivot yang terjadi di bar_index - rightStrength
                    temp_finalPivotLowPrice_this_bar = finalPivotLowPrice
                    lastSignalType = -1
                    log_event(f"FINAL Pivot Low Terdeteksi: {finalPivotLowPrice:.5f} (konfirmasi). Alert: Pivot Low pada {CONFIG['crypto_pair']}")
                else:
                     log_event(f"Raw Pivot Low {rawPivotLow:.5f} terdeteksi tapi ada High ({highPriceForFib}) menunggu untuk FIB. Low ini mungkin akan diproses untuk FIB.")


        # --- Logika Konfirmasi FIB 0.5 Dinamis ---
        # Kondisi 1: HIGH baru terkonfirmasi (finalPivotHighPrice baru saja di-set di atas)
        if not math.isnan(temp_finalPivotHighPrice_this_bar): # Menggunakan temp_finalPivotHighPrice_this_bar
            highPriceForFib = temp_finalPivotHighPrice_this_bar
            highBarIndexForFib = bar_index - CONFIG["rightStrength"] # Index aktual dari bar pivot High
            activeFibLevel = float('nan') # Reset FIB aktif karena High baru
            log_event(f"Pivot High {highPriceForFib:.5f} (di bar {highBarIndexForFib}) disimpan untuk kalkulasi FIB.")

        # Kondisi 2: LOW baru terkonfirmasi (finalPivotLowPrice baru saja di-set di atas)
        # Atau rawPivotLow terdeteksi saat highPriceForFib ada
        # Kita proses jika ada rawPivotLow (bukan hanya finalPivotLowPrice) karena Pine script memprosesnya dalam blok "if not na(rawPivotLowPrice)"
        # Dan kemudian "if not na(finalPivotLowPrice)"
        
        # Kita gunakan rawPivotLow untuk konsistensi dengan Pine Script yang memprosesnya pada bar konfirmasi low
        current_low_for_fib_check = float('nan')
        if not math.isnan(rawPivotLow): # Pivot low yang dikonfirmasi di bar ini
            current_low_for_fib_check = rawPivotLow 
        
        if not math.isnan(current_low_for_fib_check):
            if not math.isnan(highPriceForFib) and not math.isnan(highBarIndexForFib):
                currentLowPriceForFib = current_low_for_fib_check
                currentLowBarIndex = bar_index - CONFIG["rightStrength"] # Index aktual dari bar pivot Low

                if currentLowBarIndex > highBarIndexForFib: # Pastikan LOW setelah HIGH
                    calculatedFibLevel = (highPriceForFib + currentLowPriceForFib) / 2.0
                    isFibLate = False

                    if CONFIG["enableSecureFib"]:
                        priceToCheckAgainstFib = current_bar[CONFIG["secureFibCheckPrice"].lower()] # Gunakan harga close/high dari BAR SAAT INI (bar_index)
                        if priceToCheckAgainstFib > calculatedFibLevel:
                            isFibLate = True
                    
                    if isFibLate:
                        log_event(f"FIB Terlambat ({calculatedFibLevel:.5f}) karena harga cek ({CONFIG['secureFibCheckPrice']}: {priceToCheckAgainstFib:.5f}) sudah melewatinya. FIB diabaikan.")
                        activeFibLevel = float('nan') 
                    else:
                        activeFibLevel = calculatedFibLevel
                        log_event(f"FIB 0.5 Level Aktif: {activeFibLevel:.5f} (dari High {highPriceForFib:.5f} di bar {highBarIndexForFib} & Low {currentLowPriceForFib:.5f} di bar {currentLowBarIndex})")
                    
                    # HIGH ini sudah diproses (baik FIB-nya valid atau terlambat), reset untuk menunggu HIGH baru.
                    highPriceForFib = float('nan')
                    highBarIndexForFib = float('nan')
                # else:
                    # log_event(f"Low ({currentLowPriceForFib}) terdeteksi sebelum High ({highPriceForFib}) atau pada bar yang sama. Tidak valid untuk pair FIB ini.")


        # Kondisi 3: Cek setiap bar apakah garis FIB visual aktif perlu dipotong ATAU memicu entry
        if not math.isnan(activeFibLevel): # Hanya proses jika activeFibLevel VALID
            isBullishCandle = close_price > open_price
            isClosedAboveFib = close_price > activeFibLevel

            if isBullishCandle and isClosedAboveFib:
                if not position_active: # strategy.position_size == 0
                    # --- ENTRY LOGIC ---
                    position_active = True
                    entry_price_custom = close_price # Entri pada close_price
                    
                    # Hitung berapa banyak aset yang bisa dibeli
                    equity_to_use = current_equity * (CONFIG["default_qty_value"]/100.0 if "default_qty_value" in CONFIG else 1.0) # default_qty_value = 100
                    cost_before_commission = equity_to_use
                    commission_amount = cost_before_commission * (CONFIG["commission_percent"] / 100.0)
                    total_cost = cost_before_commission + commission_amount
                    
                    if current_equity >= total_cost:
                        asset_qty = cost_before_commission / entry_price_custom
                        current_equity -= total_cost # Kurangi modal dengan total biaya
                        log_event(f"EQUITY: Sisa modal setelah beli: {current_equity:.2f} {tsym}")
                    else: # Tidak cukup modal setelah komisi, mungkin hanya bisa beli sebagian atau tidak sama sekali
                        # Untuk simplicity, asumsikan initial capital cukup. Dalam sistem riil, ini perlu penanganan.
                        # Atau, hitung mundur: asset_qty = current_equity / (entry_price_custom * (1 + CONFIG["commission_percent"]/100))
                        asset_qty = (current_equity / (1 + CONFIG["commission_percent"]/100.0)) / entry_price_custom
                        cost_after_commission = asset_qty * entry_price_custom * (1 + CONFIG["commission_percent"]/100.0)
                        current_equity -= cost_after_commission # Seharusnya jadi mendekati 0 atau sisa kecil
                        log_event(f"EQUITY: Modal hampir habis setelah beli: {current_equity:.2f} {tsym}")

                    highest_price_for_trailing = entry_price_custom # atau high_price jika entri terjadi
                    trailing_tp_active_custom = False
                    current_trailing_stop_level = float('nan')
                    emergency_sl_level_custom = entry_price_custom * (1 - CONFIG["emergencySlPercent"] / 100.0)

                    log_event(f"STRATEGY BUY: {asset_qty:.8f} {fsym} @ {entry_price_custom:.5f} {tsym}. Entry FIB Cross.")
                    log_event(f"   Emergency SL: {emergency_sl_level_custom:.5f}. Current Equity: {current_equity:.2f} {tsym}")
                    log_event(f"   Alert: PRDA Buy Entry - BUY {asset_qty:.8f} @ {entry_price_custom:.5f} on {CONFIG['crypto_pair']}")
                
                # Reset info FIB karena sudah digunakan/terpotong
                log_event(f"FIB Level {activeFibLevel:.5f} terpicu/terpotong oleh candle bullish close di atasnya.")
                activeFibLevel = float('nan')


        # --- Logika Manajemen Posisi Strategi ---
        if position_active:
            # Cek jika baru masuk posisi di bar ini (dibandingkan dengan state sebelum proses bar ini)
            # Ini sudah ditangani di blok entry di atas.
            # Bagian ini untuk update per bar JIKA sudah dalam posisi

            highest_price_for_trailing = max(highest_price_for_trailing if not math.isnan(highest_price_for_trailing) else high_price, high_price)

            if not trailing_tp_active_custom and not math.isnan(entry_price_custom):
                profitPercent = ((highest_price_for_trailing - entry_price_custom) / entry_price_custom) * 100.0
                if profitPercent >= CONFIG["profitTargetPercentForActivation"]:
                    trailing_tp_active_custom = True
                    log_event(f"Trailing TP Aktif. Profit mencapai {profitPercent:.2f}% (Target: {CONFIG['profitTargetPercentForActivation']}%). Highest price: {highest_price_for_trailing:.5f}")
            
            if trailing_tp_active_custom and not math.isnan(highest_price_for_trailing):
                potentialNewStopPrice = highest_price_for_trailing * (1 - (CONFIG["trailingStopGapPercent"] / 100.0))
                if math.isnan(current_trailing_stop_level) or potentialNewStopPrice > current_trailing_stop_level:
                    current_trailing_stop_level = potentialNewStopPrice
                    log_event(f"Trailing Stop Level diperbarui ke: {current_trailing_stop_level:.5f}")
            
            final_stop_for_exit = emergency_sl_level_custom
            exit_comment = "Emergency SL"
            if trailing_tp_active_custom and not math.isnan(current_trailing_stop_level):
                if current_trailing_stop_level > emergency_sl_level_custom: # Pastikan trailing stop lebih tinggi dari emergency
                    final_stop_for_exit = current_trailing_stop_level
                    exit_comment = "Trailing Stop"
            
            # Cek kondisi exit
            if not math.isnan(final_stop_for_exit) and low_price <= final_stop_for_exit:
                exit_price = final_stop_for_exit # Asumsi order stop terpenuhi di level stop
                
                proceeds_before_commission = asset_qty * exit_price
                commission_on_exit = proceeds_before_commission * (CONFIG["commission_percent"] / 100.0)
                net_proceeds = proceeds_before_commission - commission_on_exit
                
                initial_investment_for_this_trade = asset_qty * entry_price_custom # Perlu dikalkulasi ulang atau disimpan
                                                                               # karena entry_price_custom adalah harga per unit
                                                                               # dan asset_qty sudah memperhitungkan komisi beli.
                                                                               # Lebih baik hitung PnL dari perubahan equity.
                
                old_equity_before_this_trade = current_equity + (asset_qty * entry_price_custom * (1 + CONFIG["commission_percent"]/100.0)) # Perkiraan kasar
                                                                                                                                       # Lebih akurat: simpan equity sebelum entry
                
                pnl_amount = net_proceeds - (asset_qty * entry_price_custom) # PnL kotor sebelum komisi jual, tapi asset_qty sudah nett dari komisi beli
                                                                             # Simplifikasi: PnL = (exit_price * asset_qty) * (1 - comm_sell) - (entry_price_custom * asset_qty) * (1 + comm_buy)
                                                                             # Atau, lebih mudah, PnL dari perubahan total equity jika initial_capital hanya untuk trade ini
                
                current_equity += net_proceeds
                
                pnl_percent = ((exit_price - entry_price_custom) / entry_price_custom) * 100 if entry_price_custom > 0 else 0
                # PnL yang lebih akurat memperhitungkan komisi:
                # (exit_price * (1-comm/100) - entry_price * (1+comm/100)) / (entry_price * (1+comm/100)) * 100
                effective_entry_price = entry_price_custom * (1 + CONFIG["commission_percent"]/100.0)
                effective_exit_price = exit_price * (1 - CONFIG["commission_percent"]/100.0)
                pnl_percent_net = ((effective_exit_price - effective_entry_price) / effective_entry_price) * 100 if effective_entry_price > 0 else 0


                log_event(f"STRATEGY EXIT: {exit_comment} Hit @ {exit_price:.5f}. Selling {asset_qty:.8f} {fsym}")
                log_event(f"   Entry: {entry_price_custom:.5f}, Exit: {exit_price:.5f}. PnL ~ {pnl_percent_net:.2f}% (Net Komisi)")
                log_event(f"   Current Equity: {current_equity:.2f} {tsym}")
                log_event(f"   Alert: PRDA Trade Closed on {CONFIG['crypto_pair']}. PnL: {pnl_percent_net:.2f}%. Exit by: {exit_comment}")

                # Reset status posisi
                position_active = False
                entry_price_custom = float('nan') 
                asset_qty = 0.0
                highest_price_for_trailing = float('nan')
                trailing_tp_active_custom = False
                current_trailing_stop_level = float('nan')
                emergency_sl_level_custom = float('nan')
        
        # Saat posisi baru saja ditutup (cek perubahan state position_active)
        if not position_active and prev_position_active: # Jika sebelumnya aktif, sekarang tidak
             log_event(f"Posisi Ditutup di bar #{bar_index}.")
             # Variabel sudah direset di blok exit di atas
        
        # Plot Level Stop Loss (Visual) - di CLI jadi log saja
        if position_active:
            plot_stop_level_val = emergency_sl_level_custom
            if trailing_tp_active_custom and not math.isnan(current_trailing_stop_level) and current_trailing_stop_level > emergency_sl_level_custom:
                plot_stop_level_val = current_trailing_stop_level
            if not math.isnan(plot_stop_level_val):
                 log_event(f"   INFO: Aktif Stop Level (Visual): {plot_stop_level_val:.5f}")
        
        # Sedikit delay untuk membaca log per bar jika diinginkan
        # time.sleep(0.1) 

    log_event("--- Simulasi Selesai ---")
    log_event(f"Modal Awal: {CONFIG['initial_capital']:.2f} {tsym}")
    log_event(f"Modal Akhir: {current_equity:.2f} {tsym}")
    profit_total = current_equity - CONFIG['initial_capital']
    profit_percent_total = (profit_total / CONFIG['initial_capital']) * 100 if CONFIG['initial_capital'] > 0 else 0
    log_event(f"Total PnL: {profit_total:.2f} {tsym} ({profit_percent_total:.2f}%)")


# --- Main Execution ---
if __name__ == "__main__":
    display_settings_menu()
    
    if not CONFIG["api_key"]:
        log_event("API Key CryptoCompare diperlukan. Silakan masukkan melalui menu pengaturan.")
    else:
        run_strategy()
