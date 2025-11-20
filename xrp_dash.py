import os
import re
import threading
import time
from datetime import datetime, timedelta
import collections
import itertools
from functools import lru_cache

# För datahantering och SMA
import numpy as np
import pandas as pd
from scipy.stats import linregress
import requests

# Dash imports (Behålls trots att app-layouten saknas)
# from dash import Dash # Se nedan

# =========================================================================
# === KONSTANTER OCH IMPORTER (PLATSHÅLLARE) ===
# Vänligen ersätt dessa med dina faktiska värden och biblioteksanrop
# =========================================================================

# --- Externa Konstanter (Ersätt med dina riktiga värden) ---
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"
EXCEL_FILE_PATH = 'krypto_logg.xlsx'

# API:er (EUR-baserade)
KRAKEN_TICKER_API_URL = "https://api.kraken.com/0/public/Ticker"
KRAKEN_OHLC_API_URL = "https://api.kraken.com/0/public/OHLC"
EXCHANGE_RATE_URL = "https://api.exchangerate.host/latest?base=EUR&symbols=SEK" # Exempel

# Kryptopar (Ticker är Kraksens ticker, t.ex. XXBTZEUR)
CRYPTO_PAIRS = {
    'Bitcoin / EUR': 'XXBTZEUR',
    'Ethereum / EUR': 'XETHZEUR',
    'Cardano / EUR': 'ADAZEUR',
    # Lägg till fler par här
}

# SMA-fönster (i minuter)
SMA_WINDOWS = [5, 20, 50]

# Tidsramar i minuter (Antal datapunkter per minut)
SUMMARY_TREND_POINTS_30M = 30 # För 30m trend/kort trigger
MAX_DASH_POINTS = 100 # För 100m trend/SMA
SUMMARY_TREND_POINTS_360M = 360 # För 360m trend/periodisk sammanfattning

# För att koden ska fungera i Canvas-miljön måste du lägga till Dash-import och initiering
try:
    from dash import Dash
    app = Dash(__name__)
except ImportError:
    # Simulerad Dash-miljö om den inte är tillgänglig
    class Dash:
        def __init__(self, name): pass
    app = Dash(__name__)

# =========================================================================
# === START PÅ DEN INSÄNDA KODEN (MED KOMPLETTERINGAR) ===
# =========================================================================

# --- Strategikonstanter ---
DIFF_THRESHOLD = 21 # Signalvärdesdifferens
REVERSION_THRESHOLD = 0.02 # 2% (0.02)

# NYA SPIKE TRÖSKLAR (GÄLLER NU 30m, 100m, 360m OCH 24h)
SPIKE_THRESHOLDS = {
    '+100%': 100.0,
    '+75%': 75.0,
    '+50%': 50.0,
    '+25%': 25.0,
    '+10%': 10.0,
    '-10%': -10.0,
    '-25%': -25.0,
    '-50%': -50.0,
}
# Sortera trösklar: högst till lägst värde
SORTED_SPIKE_THRESHOLDS = sorted(SPIKE_THRESHOLDS.items(), key=lambda item: item[1], reverse=True)
TIMEFRAMES_FOR_SPIKES = ['30m', '100m', '360m', '24h']


# --- GLOBAL LAGER ---
data_lock = threading.Lock()
data_history = {pair: collections.deque(maxlen=max(SMA_WINDOWS)) for pair in CRYPTO_PAIRS.values()}
global_kpi_cache = {}
SENT_NOTIFICATIONS = {pair: 0 for pair in CRYPTO_PAIRS.values()}
SENT_DIFF_NOTIFICATIONS = {}
current_signal_ratings = {}

# NY STRUKTUR FÖR SPIKE-NOTISER (Per Tidsram, Per Par, Per Tröskel)
SENT_SPIKE_NOTIFICATIONS = {
    tf: {
        pair: {label: False for label in SPIKE_THRESHOLDS.keys()}
        for pair in CRYPTO_PAIRS.values()
    }
    for tf in TIMEFRAMES_FOR_SPIKES
}

# För periodisk sammanfattning
SUMMARY_SEND_TIMES = [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]
LAST_SUMMARY_SENT = {hour: None for hour in SUMMARY_SEND_TIMES}


def format_price_sek(value):
    """Formaterar ett tal till 4 decimaler med tusenavgränsare (mellanslag) i SEK-stil."""
    if not isinstance(value, (int, float)) or np.isnan(value) or value is None:
        return "N/A"
    # Format i SEK: mellanslag som tusenavgränsare, komma som decimalavgränsare
    return f"{value:,.4f}".replace(",", "X").replace(".", ",").replace("X", " ")

def format_price_eur(value):
    """Formaterar ett tal till 4 decimaler med tusenavgränsare (mellanslag) i EUR-stil (som ofta använder punkt)."""
    if not isinstance(value, (int, float)) or np.isnan(value) or value is None:
        return "N/A"
    # Format i EUR: mellanslag som tusenavgränsare, punkt som decimalavgränsare
    return f"{value:,.4f}".replace(",", " ")

def format_percent(value):
    """Formaterar en procentuell förändring med tecken och 2 decimaler."""
    if value is None:
        return "N/A %"
    if not isinstance(value, (int, float)) or np.isnan(value):
        return "N/A %"
    return f"{value:+.2f} %"

# --- TELEGRAM NOTIS FUNKTIONER ---

def send_telegram_message(message_text):
    """Generisk funktion för att skicka meddelanden via Telegram API."""
    base_url = "https://api.telegram.org/bot{token}/sendMessage"
    url = base_url.format(token=TELEGRAM_BOT_TOKEN)

    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message_text,
        'parse_mode': 'Markdown'
    }

    try:
        response = requests.post(url, data=payload, timeout=5)
        response.raise_for_status()
        time.sleep(1.0)
        return True
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] FEL vid skickande av Telegramnotis: {e}")
        return False


def notify_periodic_summary():
    """Skickar en periodisk sammanfattning av de senaste 360m (6h) trenderna."""
    global global_kpi_cache
    
    with data_lock:
        local_kpi_cache = global_kpi_cache.copy()
        
    if not local_kpi_cache:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Sammanfattning misslyckades: KPI-cache är tom.")
        return False
        
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Skickar Periodisk Sammanfattning (360m trend)...")

    summary_data = []
    
    for pair_key, pair_ticker in CRYPTO_PAIRS.items():
        kpi = local_kpi_cache.get(pair_ticker, {})
        
        change_360m = kpi.get('percent_change_360m')
        signal_rating = kpi.get('signal_rating')
        change_24h = kpi.get('percent_change_24h')
        aktuellt_varde_eur = kpi.get('price_eur')

        display_name = pair_key.split('/')[0].strip()
        display_name = re.sub(r'\s*\((.*?)\)', '', display_name).strip()


        if change_360m is not None and signal_rating is not None and change_24h is not None and aktuellt_varde_eur is not None:
            summary_data.append({
                'crypto': display_name,
                'change_360m': change_360m,
                'rating': signal_rating,
                'change_24h': change_24h,
                'aktuellt_varde': format_price_eur(aktuellt_varde_eur),
            })

    if not summary_data:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Sammanfattning misslyckades: Ingen meningsfull 360m data hittades.")
        return False

    # 3. Sortera data (Högst procentuell förändring överst)
    sorted_summary = sorted(summary_data, key=lambda x: x['change_360m'], reverse=True)
    
    # 4. Bygg meddelandet
    header = (
        f"⏳ *PERIODISK SAMMANFATTNING (360 MIN TREND)* ⏳\n\n"
        f"Översikt över 6-timmars och 24-timmars rörelse samt MTS-signalbetyg.\n"
        f"Tid: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"| Krypto | 360m % | 24h % | Betyg | Kurs (EUR) |\n"
        f"|---|---|---|---|---|\n"
    )
    
    table_rows = []
    for item in sorted_summary:
        # Formatera kolumner
        crypto_col = f"`{item['crypto']}`"
        change_360m_col = f"`{format_percent(item['change_360m'])}`"
        change_24h_col = f"`{format_percent(item['change_24h'])}`"
        rating_col = f"`{item['rating']:+}`"
        aktuellt_varde_col = f"`{item['aktuellt_varde']}`"

        
        table_rows.append(f"| {crypto_col} | {change_360m_col} | {change_24h_col} | {rating_col} | {aktuellt_varde_col} |")
        
    message = header + "\n".join(table_rows)

    # 5. Skicka meddelandet
    return send_telegram_message(message)


def notify_diff(crypto1, rating1, crypto2, rating2, difference):
    """Skickar notis vid stor signalbetygsskillnad."""
    message = (
        f"🚨 *ALARM SIGNALDIFFERENS ({DIFF_THRESHOLD}-steg)* 🚨\n\n"
        f"Skillnad i signalbetyg har uppnått tröskeln (Diff: `{difference}` >= `{DIFF_THRESHOLD}`).\n\n"
        f"Krypto 1: *{crypto1}* (Betyg: `{rating1:+}`)\n"
        f"Krypto 2: *{crypto2}* (Betyg: `{rating2:+}`)\n\n"
        f"Tid: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    return send_telegram_message(message)


def notify_single(signal_text, pair_key, current_price_eur, signal_rating):
    """Skickar notis vid stark Köp/Sälj-signal. Använder ALLTID EUR."""
    price_formatted = format_price_eur(current_price_eur)

    message = (
        f"🔔 *MTS HANDELSTRIGGER (Betyg {signal_rating:+})* 🔔\n\n"
        f"Kryptovaluta: *{pair_key}*\n"
        f"Signal: *{signal_text}*\n"
        f"Pris: `{price_formatted} EUR`\n"
        f"Tid: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    return send_telegram_message(message)

def notify_spike(timeframe_label, pair_key, percent_change, current_price_eur, threshold_label):
    """(GENERALISERAD) Skickar notis vid kraftig uppgång/nedgång på en specifik tidsram. Använder ALLTID EUR."""
    
    price_formatted = format_price_eur(current_price_eur)

    direction = "UPPGÅNG" if percent_change >= 0 else "NEDGÅNG"
    emoji = "🚀" if percent_change >= 0 else "📉"
    
    message = (
        f"{emoji} *{timeframe_label.upper()} PRISVARNING ({threshold_label} {direction})* {emoji}\n\n"
        f"Kryptovaluta: *{pair_key}*\n"
        f"Förändring: *{format_percent(percent_change)}* på {timeframe_label}.\n"
        f"Tröskel: *{threshold_label}* passerad.\n"
        f"Pris: `{price_formatted} EUR`\n"
        f"Tid: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    return send_telegram_message(message)


def send_test_notification():
    """Skickar en testnotis via Telegram."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Försöker skicka TEST-TELEGRAM...")

    message = (
        f"✅ *OMSTART* ✅\n\n"
        f"Detta är ett automatiskt testmeddelande från din Kryptospårare.\n"
        f"Telegram-notiser fungerar korrekt (om du ser detta i din chatt).\n\n"
        f"Tid: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    success = send_telegram_message(message)
    if success:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] TEST TELEGRAM SKICKAT. Kontrollera din chatt.")
    else:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] TEST TELEGRAM MISSLYCKADES. Kontrollera dina Telegram-konstanter och/eller felloggen ovan.")
    return success

# --- ÖVRIGA FUNKTIONER (Datahantering och KPI:er) ---

def sanitize_sheet_name(pair_key):
    """Rensar kryptonamnet för att användas som arkivnamn i Excel."""
    name = pair_key.split('/')[0].strip()
    name = re.sub(r'\s*\((.*?)\)', '', name).strip()
    name = re.sub(r'[^\w\s-]', '', name)
    name = name.replace(' ', '_')
    return name[:31]

def load_historical_data():
    """Laddar historik från Excel-filen för alla kända par vid start."""
    global data_history

    max_len = max(SMA_WINDOWS)

    for pair_ticker in CRYPTO_PAIRS.values():
        if pair_ticker not in data_history:
            data_history[pair_ticker] = collections.deque(maxlen=max_len)
        else:
             data_history[pair_ticker] = collections.deque(data_history[pair_ticker], maxlen=max_len)

        if not data_history[pair_ticker]:
            # Lägg till en startpunkt med pris 0 för att undvika tomma lister vid första körningen
            data_history[pair_ticker].append({'time': datetime.now() - timedelta(minutes=max_len), 'price_sek': 0.0, 'price_eur': 0.0})

    if os.path.exists(EXCEL_FILE_PATH):
        try:
            xlsx = pd.ExcelFile(EXCEL_FILE_PATH)
            for pair_key, pair_ticker in CRYPTO_PAIRS.items():
                sheet_name = sanitize_sheet_name(pair_key)
                if sheet_name in xlsx.sheet_names:
                    pair_df = pd.read_excel(xlsx, sheet_name=sheet_name)
                    
                    if not pair_df.empty and 'time' in pair_df.columns:
                        pair_df['time'] = pd.to_datetime(pair_df['time'])
                        
                        # Fallback för gamla loggfiler som bara har price_sek
                        if 'price_eur' not in pair_df.columns:
                            pair_df['price_eur'] = 0.0
                        
                        pair_df = pair_df[pair_df['price_sek'] > 0.0].sort_values(by='time').tail(max_len)
                        
                        with data_lock:
                            data_history[pair_ticker].clear()
                            for index, row in pair_df.iterrows():
                                data_history[pair_ticker].append({
                                    'time': row['time'], 
                                    'price_sek': row['price_sek'],
                                    'price_eur': row.get('price_eur', 0.0)
                                })
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Varning: Kunde inte läsa historik från Excel: {e}") 

def log_data_to_excel(data_to_log):
    """Skriver all aktuell historisk data till Excel-filen. Anropas inuti data_lock."""
    
    try:
        with pd.ExcelWriter(EXCEL_FILE_PATH, engine='openpyxl') as writer:
            for pair_key, pair_ticker in CRYPTO_PAIRS.items():
                current_df = pd.DataFrame(data_to_log.get(pair_ticker, []))
                
                current_df = current_df[current_df['price_sek'] > 0.0]
                if len(current_df) < 1: continue
                
                sheet_name = sanitize_sheet_name(pair_key)  
                current_df['time'] = current_df['time'].dt.strftime('%Y-%m-%d %H:%M:%S')
                current_df['price_sek'] = current_df['price_sek'].round(8)
                current_df['price_eur'] = current_df['price_eur'].round(8)
                
                # Säkerställ kolumnordning
                current_df = current_df[['time', 'price_sek', 'price_eur']]
                
                current_df.to_excel(writer, sheet_name=sheet_name, index=False)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Data loggad till Excel.")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] FEL vid skrivning till Excel: {e}")

@lru_cache(maxsize=1)
def get_eur_sek_rate():
    """Hämtar aktuell EUR/SEK växelkurs. Använder 11.50 SEK som fallback."""
    try:
        response = requests.get(EXCHANGE_RATE_URL, timeout=5)
        response.raise_for_status()
        data = response.json()
        if 'rates' in data and 'SEK' in data['rates']:
            return data['rates']['SEK']
        return 11.50
    except requests.exceptions.RequestException:
        return 11.50
    except Exception:
        return 11.50

def get_ohlc_price(pair_ticker, since_days_ago, eur_sek_rate):
    """Hämtar historiskt slutpris (stängningspris) från Kraken OHLC API."""
    since_time = datetime.now() - timedelta(days=since_days_ago)
    since_unix = int((since_time - timedelta(days=10)).timestamp())
    params = {'pair': pair_ticker, 'interval': 1440, 'since': since_unix}

    try:
        response = requests.get(KRAKEN_OHLC_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('error') and data['error']:
            return None, None, f"OHLC Fel: {data['error']}."

        kraken_pair_key = list(data['result'].keys())[0]
        ohlc_data = data['result'][kraken_pair_key]

        target_timestamp = since_time.timestamp()
        best_match_price_eur = None

        for entry in reversed(ohlc_data):
            timestamp = entry[0]
            if timestamp < target_timestamp:
                best_match_price_eur = float(entry[4])
                break

        if best_match_price_eur is not None:
            # Returnera (price_eur, price_sek, error)
            return best_match_price_eur, (best_match_price_eur * eur_sek_rate), None

        return None, None, f"Ingen tillförlitlig OHLC-data hittades."

    except Exception as e:
        return None, None, f"Fel vid hämtning av OHLC-data: {e}"


def get_crypto_data(pair_ticker):
    """Hämtar Aktuellt pris (EUR & SEK) och 24h KPI:er."""
    eur_sek_rate = get_eur_sek_rate()
    try:
        params = {'pair': pair_ticker}
        response = requests.get(KRAKEN_TICKER_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('error') and data['error']: return None, f"Ticker Fel: {data['error']} för {pair_ticker}"

        if data.get('result'):
            kraken_pair_key = list(data['result'].keys())[0]
            result = data['result'][kraken_pair_key]

            # Basvärden i EUR
            latest_price_eur = float(result['c'][0])
            open_24h_eur = float(result['o'])
            high_24h_eur = float(result['h'][1])
            low_24h_eur = float(result['l'][1])

            # SEK-konverteringar
            price_sek = latest_price_eur * eur_sek_rate
            high_sek = high_24h_eur * eur_sek_rate
            low_sek = low_24h_eur * eur_sek_rate
            open_sek = open_24h_eur * eur_sek_rate

            # 24h % (valutaneutral, baserad på EUR)
            percent_change_24h = ((latest_price_eur - open_24h_eur) / open_24h_eur) * 100 if open_24h_eur != 0 else 0

        else: return None, f"Fick ett tomt Ticker-resultat."

    except Exception as e: return None, f"Fel vid hämtning av Ticker-data: {e}"

    # Procentuell skillnad hög och låg på 24h
    formel2 = ((high_24h_eur - low_24h_eur) / latest_price_eur) * 100

    if formel2 is not None:
        formel = f"{formel2:.2f}""%"
    else:
        formel = "N/A"

    return {
        'price_eur': latest_price_eur,
        'high_24h_eur': high_24h_eur,
        'low_24h_eur': low_24h_eur,
        'open_24h_eur': open_24h_eur,
        'price_sek': price_sek,
        'high_24h_sek': high_sek,
        'low_24h_sek': low_sek,
        'open_24h_sek': open_sek,
        'percent_change_24h': percent_change_24h, # Denna är valutaneutral
        'formel': formel,
    }, None

def calculate_30min_trend(pair_ticker, history_data):
    """Beräknar den procentuella trenden över de senaste 30 lagrade datapunkterna (linjär regression)."""

    filtered_history = [p for p in history_data if p['price_sek'] > 0.0]

    if not filtered_history or len(filtered_history) < SUMMARY_TREND_POINTS_30M:
        return 0.0, "Väntar på data", "gray"

    df = pd.DataFrame(filtered_history[-SUMMARY_TREND_POINTS_30M:])

    x_time_numeric = np.array([t.timestamp() for t in df['time']])
    y_price = df['price_sek']

    # Linjär regression
    slope, intercept, _, _, _ = linregress(x_time_numeric, y_price)

    start_price_trend = slope * x_time_numeric.min() + intercept
    end_price_trend = slope * x_time_numeric.max() + intercept

    if start_price_trend == 0.0 or start_price_trend is None: return 0.0, "Ingen historik", "gray"

    percent_change = ((end_price_trend - start_price_trend) / start_price_trend) * 100

    if percent_change > 0.0: return percent_change, f"Stigande ({SUMMARY_TREND_POINTS_30M} min)", "#006400" # Mörkgrön
    elif percent_change < 0.0: return percent_change, f"Fallande ({SUMMARY_TREND_POINTS_30M} min)", "#8B0000" # Mörkröd
    else: return 0.0, f"Stabil ({SUMMARY_TREND_POINTS_30M} min)", "#555555" # Grå
    
def calculate_trend_change(history_data, num_points):
    """Beräknar den totala procentuella förändringen över de senaste 'num_points' minuter (Från startpunkt till slutpunkt)."""

    filtered_history = [p for p in history_data if p['price_sek'] > 0.0]

    if len(filtered_history) < 2:
        return 0.0 # Inte tillräckligt med data

    if len(filtered_history) < num_points:
        start_index = 0
    else:
        start_index = len(filtered_history) - num_points
    
    start_price = filtered_history[start_index]['price_sek']
    current_price = filtered_history[-1]['price_sek']
    
    if start_price == 0:
        return 0.0

    percent_change = ((current_price - start_price) / start_price) * 100
    return percent_change

# Funktion för 100m (Total förändring)
def calculate_100min_change(history_data):
    return calculate_trend_change(history_data, MAX_DASH_POINTS)

# Funktion för 360m trend (Total förändring)
def calculate_360min_change(history_data):
    return calculate_trend_change(history_data, SUMMARY_TREND_POINTS_360M)


def calculate_long_term_rating(percent_7d, percent_30d):
    """
    Beräknar Långsiktigt Betyg baserat på 7d och 30d utfall (Max +/- 4 poäng).
    """

    percent_7d = percent_7d if percent_7d is not None else 0.0
    percent_30d = percent_30d if percent_30d is not None else 0.0

    is_bullish_filter = (percent_7d >= 0.0 and percent_30d >= 0.0)
    is_bearish_filter = (percent_7d <= 0.0 and percent_30d <= 0.0)

    if not is_bullish_filter and not is_bearish_filter:
        return 0, "NEUTRAL (Blandad)", '#B8860B' # Guld

    # Skalningsfaktor: 4 poäng / 10% = 0.4 poäng per 1%
    rating = np.clip(percent_7d * 0.4, -4, 4)
    rating = round(rating)

    if is_bullish_filter and rating >= 1:
        return rating, "BULLISH (KÖP)", '#3CB371' # Medium havgrön
    elif is_bearish_filter and rating <= -1:
        return rating, "BEARISH (SÄLJ)", '#FF6347' # Tomatröd
    else:
        return rating, "WEAK FILTER (Avvakta)", '#555555' # Grå


# --- MTS HANDELSALGORITM FUNKTION (UPPDATERAD) ---
def generate_mts_signal(kpi_data, history_data):
    """
    Implementerar Multi-Timeframe Algoritmen (MTS) för 10-steg.
    Total Rating = Long-Term Rating (Max +/-4) + Short-Term Rating (Max +/-6).
    """

    filtered_history = [p for p in history_data if p['price_sek'] > 0.0]

    if len(filtered_history) < SUMMARY_TREND_POINTS_30M: 
        return "Väntar på 30m data", 0, '#555555', 0.0, 0.0

    # Huvud-KPI:er (i SEK)
    price_sek = kpi_data['price']
    high_24h = kpi_data['high_24h']
    low_24h = kpi_data['low_24h']

    price_7d_ago = kpi_data['price_7d']
    price_30d_ago = kpi_data['price_30d']

    # KORRIGERING: Hantera potentialen för att OHLC-data saknas/är noll
    if price_7d_ago is None or price_30d_ago is None or (price_7d_ago is not None and price_7d_ago <= 0) or (price_30d_ago is not None and price_30d_ago <= 0):
        price_7d_ago_calc = price_sek
        price_30d_ago_calc = price_sek
    else:
        price_7d_ago_calc = price_7d_ago
        price_30d_ago_calc = price_30d_ago

    percent_7d = ((price_sek - price_7d_ago_calc) / price_7d_ago_calc) * 100 if price_7d_ago_calc != 0 else 0
    percent_30d = ((price_sek - price_30d_ago_calc) / price_30d_ago_calc) * 100 if price_30d_ago_calc != 0 else 0

    # --- STEG 1: LÅNGSIKTIGT BETYG (Max +/- 4) ---
    long_term_rating, filter_status, filter_color = calculate_long_term_rating(percent_7d, percent_30d)

    if abs(long_term_rating) < 1:
        return filter_status, long_term_rating, filter_color, percent_7d, percent_30d

    # --- STEG 2 & 3: KORTSIKTIGT BETYG (Max +/- 6, fördelat 3+3) ---

    df_360m = pd.DataFrame(filtered_history[-SUMMARY_TREND_POINTS_360M:])
    prices_30m = df_360m['price_sek'].tail(SUMMARY_TREND_POINTS_30M)

    short_term_rating = 0
    signal_text = filter_status
    signal_color = filter_color

    is_bullish = long_term_rating >= 1
    is_bearish = long_term_rating <= -1


    # --- STEG 2: Medellångt Momentum (Max +/- 3 poäng) (UPPDATERAD) ---
    percent_change_100m = kpi_data['percent_change_100m']
    percent_change_360m = kpi_data['percent_change_360m']

    # 24h Kvartilanalys
    range_24h = high_24h - low_24h
    q3_boundary = low_24h + (0.75 * range_24h) if range_24h > 0 else high_24h
    q1_boundary = low_24h + (0.25 * range_24h) if range_24h > 0 else low_24h

    # Kriterier för STARK momentum (Kräver nu bekräftelse från 360m)
    strong_buy_trend = (percent_change_100m >= 0.5) and (percent_change_360m >= 1.0) # > 0.5% på 100m OCH > 1.0% på 360m
    strong_sell_trend = (percent_change_100m <= -0.5) and (percent_change_360m <= -1.0) # < -0.5% på 100m OCH < -1.0% på 360m
    
    is_strong_buy_momentum = is_bullish and strong_buy_trend and (price_sek > q3_boundary)
    is_strong_sell_momentum = is_bearish and strong_sell_trend and (price_sek < q1_boundary)

    if is_strong_buy_momentum:
        short_term_rating += 3
        signal_text = "Momentum: STARK KÖP (100m/360m bekräftat)"
        signal_color = '#00CED1' # Mörk turkos
    elif is_strong_sell_momentum:
        short_term_rating -= 3
        signal_text = "Momentum: STARK SÄLJ (100m/360m bekräftat)"
        signal_color = '#DC143C' # Röd
    else:
        # Svagare momentum: BARA 100m-trenden
        trend_100m_up_weak = (percent_change_100m >= 0.1)
        trend_100m_down_weak = (percent_change_100m <= -0.1)

        if is_bullish and trend_100m_up_weak:
             short_term_rating += 1 
             signal_text = "Momentum: Positiv (Väntar på styrka)"
             signal_color = '#9ACD32' # Gul-grön
        elif is_bearish and trend_100m_down_weak:
             short_term_rating -= 1 
             signal_text = "Momentum: Negativ (Väntar på svaghet)"
             signal_color = '#FFA07A' # Ljust Orange


    # --- STEG 3: KORTSIKTIG TRIGGER (Max +/- 3 poäng) (OFÖRÄNDRAD) ---

    high_30m = prices_30m.max() if not prices_30m.empty else price_sek
    low_30m = prices_30m.min() if not prices_30m.empty else price_sek

    reversion_buy_price = low_30m * (1 + REVERSION_THRESHOLD)
    reversion_sell_price = high_30m * (1 - REVERSION_THRESHOLD)

    is_near_30m_low = (price_sek <= high_30m) and (price_sek >= low_30m) and (price_sek <= reversion_buy_price)
    is_near_30m_high = (price_sek >= low_30m) and (price_sek <= high_30m) and (price_sek >= reversion_sell_price)

    if not df_360m.empty:
        sma_100m = df_360m['price_sek'].tail(MAX_DASH_POINTS).mean()
        previous_price = df_360m['price_sek'].iloc[-2] if len(df_360m) >= 2 else price_sek
    else:
        sma_100m = price_sek
        previous_price = price_sek

    momentum_shift_up = (previous_price < sma_100m) and (price_sek >= sma_100m)
    momentum_shift_down = (previous_price > sma_100m) and (price_sek <= sma_100m)


    # --- SLUTLIG TRADEMARK TRIGER (Trigger poäng: +3 eller -3) ---
    if is_bullish and (is_near_30m_low or momentum_shift_up):
        short_term_rating += 3
        signal_text = "KÖP-TRIGGER (Pulllback/Vändning)"
        signal_color = '#00BFFF' # Djupt himmelsblå

    elif is_bearish and (is_near_30m_high or momentum_shift_down):
        short_term_rating -= 3
        signal_text = "SÄLJ-TRIGGER (Uppsving/Vändning)"
        signal_color = '#FF4500' # Orange-röd

    short_term_rating = np.clip(short_term_rating, -6, 6)

    # --- TOTAL BETYG (Max +/- 10) ---
    total_rating = long_term_rating + short_term_rating

    if total_rating >= 8:
        signal_text = "ULTIMAT KÖP-SIGNAL"
        signal_color = '#00FA9A' # Vårmörkgrön
    elif total_rating <= -8:
        signal_text = "ULTIMAT SÄLJ-SIGNAL"
        signal_color = '#B22222' # Tegelröd
    elif total_rating >= 5:
        signal_text = "STARK KÖP-SIGNAL"
    elif total_rating <= -5:
        signal_text = "STARK SÄLJ-SIGNAL"
    elif abs(total_rating) < 1:
        signal_text = "TOTAL NEUTRALITET"
        signal_color = '#444444' # Mörkgrå

    return signal_text, total_rating, signal_color, percent_7d, percent_30d


def calculate_sma(df, window, price_key='price_sek'):
    """Beräknar Simple Moving Average (SMA) för en given Pandas DataFrame."""
    return df[price_key].rolling(window=min(window, len(df))).mean()

# =========================================================================
# === NY FUNKTION: DEDIKERAD BAKGRUNDSLOGIK (LÅS-FIX APPLICERAD)
# =========================================================================

def background_data_collector():
    """
    DEDIKERAD TRÅD. Hämtar, bearbetar, lagrar och loggar data i en loop.
    All skrivning till globala cacher sker inuti 'with data_lock:'.
    """
    global global_kpi_cache, SENT_NOTIFICATIONS, SENT_DIFF_NOTIFICATIONS, SENT_SPIKE_NOTIFICATIONS, current_signal_ratings, LAST_SUMMARY_SENT
    
    local_interval_counter = 0

    print("---------------------------------------------------------")
    print(">>> Startar 24/7 data-loggning i bakgrundstråd (var 60s) <<<")
    print("---------------------------------------------------------")

    initial_data_fetch = False
    with data_lock:
        if not global_kpi_cache:
            initial_data_fetch = True
            
    if initial_data_fetch:
        print(f"[{datetime.now().strftime('%H:%M:%M')}] Initial datainsamling påbörjad...")
        for pair_key, pair_ticker in CRYPTO_PAIRS.items():
            ticker_data, error = get_crypto_data(pair_ticker)
            if ticker_data:
                with data_lock:
                    global_kpi_cache[pair_ticker] = {
                        **ticker_data,
                        # Sätt initiala 7d/30d-priser för båda valutorna
                        'price_7d_eur': ticker_data['price_eur'],
                        'price_30d_eur': ticker_data['price_eur'],
                        'price_7d_sek': ticker_data['price_sek'],
                        'price_30d_sek': ticker_data['price_sek'],
                        'percent_change_100m': 0.0,
                        'percent_change_360m': 0.0,
                        'time': datetime.now(),
                        'signal_rating': 0,
                        'signal_text': 'Väntar på historik',
                        'signal_color': '#555555',
                    }
                    # Lägg till en första datapunkt för båda valutorna
                    data_history[pair_ticker].append({
                        'time': datetime.now(), 
                        'price_sek': ticker_data['price_sek'],
                        'price_eur': ticker_data['price_eur']
                    })


    while True:
        
        # Säkerställ att vi låser när vi skriver till delade globala variabler
        with data_lock:
            
            # --- START PÅ LÅST BLOCK ---
            
            eur_sek_rate = get_eur_sek_rate()
            current_time = datetime.now()
            new_ratings = {}
            print(f"\n--- Datauppdatering startad: {current_time.strftime('%Y-%m-%d %H:%M:%S')} ---")

            # Temporär cache för OHLC-data som kan ta tid att hämta
            ohlc_cache = {}
            # Använd en smartare kontroll: kör OHLC-hämtningen var 60:e datapunkt.
            is_ohlc_update_time = local_interval_counter % 60 == 0

            # Första loop: Hämta Ticker-data, uppdatera historik, hämta OHLC
            for pair_key, pair_ticker in CRYPTO_PAIRS.items():
                
                # 1. Hämta Ticker-data
                ticker_data, error = get_crypto_data(pair_ticker)

                if error:
                    print(f"[{pair_key}] FEL vid Ticker-data: {error}")
                    continue

                current_price_sek = ticker_data['price_sek']
                
                # 2. Uppdatera lokal historik (Deque)
                data_history[pair_ticker].append({
                    'time': current_time, 
                    'price_sek': ticker_data['price_sek'],
                    'price_eur': ticker_data['price_eur']
                })
                local_history_list = list(data_history[pair_ticker]) # Uppdaterad lista för beräkningar nedan

                # 3. Hämta/Använd OHLC-data
                price_7d_eur, price_7d_sek = None, None
                price_30d_eur, price_30d_sek = None, None
                
                cached_kpi = global_kpi_cache.get(pair_ticker, {})
                
                if is_ohlc_update_time:
                    # KORRIGERING AV AVBRUTEN KOD: Komplett anrop till get_ohlc_price
                    price_7d_eur, price_7d_sek, error_7d = get_ohlc_price(pair_ticker, 7, eur_sek_rate)
                    if error_7d:
                        print(f"[{pair_key}] Varning vid 7d OHLC: {error_7d}")
                        
                    price_30d_eur, price_30d_sek, error_30d = get_ohlc_price(pair_ticker, 30, eur_sek_rate)
                    if error_30d:
                        print(f"[{pair_key}] Varning vid 30d OHLC: {error_30d}")

                # Använd cache-värden om OHLC inte uppdaterades eller misslyckades
                price_7d_eur = price_7d_eur if price_7d_eur is not None else cached_kpi.get('price_7d_eur', ticker_data['price_eur'])
                price_30d_eur = price_30d_eur if price_30d_eur is not None else cached_kpi.get('price_30d_eur', ticker_data['price_eur'])
                price_7d_sek = price_7d_sek if price_7d_sek is not None else cached_kpi.get('price_7d_sek', ticker_data['price_sek'])
                price_30d_sek = price_30d_sek if price_30d_sek is not None else cached_kpi.get('price_30d_sek', ticker_data['price_sek'])


                # 4. Beräkna kortsiktiga KPI:er
                df_history = pd.DataFrame(local_history_list)
                
                # Beräkna SMA för SEK (huvudvalutan för logik)
                sma_values_sek = {
                    window: calculate_sma(df_history, window, 'price_sek').iloc[-1]
                    for window in SMA_WINDOWS
                }

                # Beräkna Trendförändringar (baserat på SEK historik)
                percent_change_100m = calculate_trend_change(local_history_list, MAX_DASH_POINTS)
                percent_change_360m = calculate_trend_change(local_history_list, SUMMARY_TREND_POINTS_360M)
                percent_change_30m = calculate_trend_change(local_history_list, SUMMARY_TREND_POINTS_30M)

                # 5. Förbered KPI input för MTS & Generera Signal
                mts_kpi_input = {
                    # Använd SEK för all logik
                    'price': ticker_data['price_sek'],
                    'high_24h': ticker_data['high_24h_sek'],
                    'low_24h': ticker_data['low_24h_sek'],
                    'price_7d': price_7d_sek,
                    'price_30d': price_30d_sek,
                    'percent_change_100m': percent_change_100m,
                    'percent_change_360m': percent_change_360m,
                }
                
                signal_text, total_rating, signal_color, percent_7d, percent_30d = generate_mts_signal(
                    mts_kpi_input, local_history_list
                )
                new_ratings[pair_key] = total_rating # Lagra för Diff Notis-check

                # 6. Uppdatera global KPI cache
                global_kpi_cache[pair_ticker] = {
                    **ticker_data, # Innehåller price_eur, price_sek, percent_change_24h etc.
                    'time': current_time,
                    'price_7d_eur': price_7d_eur,
                    'price_30d_eur': price_30d_eur,
                    'price_7d_sek': price_7d_sek,
                    'price_30d_sek': price_30d_sek,
                    'percent_change_100m': percent_change_100m,
                    'percent_change_360m': percent_change_360m,
                    'percent_change_30m': percent_change_30m,
                    'percent_change_7d': percent_7d,
                    'percent_change_30d': percent_30d,
                    'signal_rating': total_rating,
                    'signal_text': signal_text,
                    'signal_color': signal_color,
                    **{f'sma_{w}_sek': sma_values_sek[w] for w in SMA_WINDOWS},
                    # Lägg till SMA för EUR (För Dashboard-visning)
                    **{f'sma_{w}_eur': calculate_sma(df_history, w, 'price_eur').iloc[-1] for w in SMA_WINDOWS},
                }
                
                print(f"[{pair_key}] Pris SEK: {format_price_sek(current_price_sek)}, Betyg: {total_rating:+}")


                # 7. Notiskontroller (MTS och SPIKE)

                # MTS SINGLE NOTIFICATION CHECK
                if abs(total_rating) >= 8 and SENT_NOTIFICATIONS.get(pair_ticker) != total_rating:
                    trigger_text = "ULTIMAT KÖP" if total_rating >= 8 else "ULTIMAT SÄLJ"
                    if notify_single(trigger_text, pair_key, ticker_data['price_eur'], total_rating):
                        SENT_NOTIFICATIONS[pair_ticker] = total_rating
                elif abs(total_rating) < 5 and SENT_NOTIFICATIONS.get(pair_ticker) != 0:
                    SENT_NOTIFICATIONS[pair_ticker] = 0

                # SPIKE NOTIFICATION CHECK
                spike_changes = {
                    '30m': percent_change_30m,
                    '100m': percent_change_100m,
                    '360m': percent_change_360m,
                    '24h': ticker_data['percent_change_24h'], # Valutaneutral %
                }

                for tf_label in TIMEFRAMES_FOR_SPIKES:
                    change = spike_changes.get(tf_label, 0.0)
                    
                    # Gå igenom trösklarna från högst till lägst
                    for threshold_label, threshold_value in SORTED_SPIKE_THRESHOLDS:
                        already_sent = SENT_SPIKE_NOTIFICATIONS[tf_label][pair_ticker][threshold_label]
                        
                        # Kontrollera om tröskeln har passerats
                        threshold_passed = (change >= threshold_value and threshold_value > 0) or \
                                           (change <= threshold_value and threshold_value < 0)

                        if threshold_passed and not already_sent:
                            # Skicka notis och flagga som skickad
                            print(f"[{pair_key}] SPIKE ALERT: {threshold_label} på {tf_label} ({change:+.2f}%)")
                            if notify_spike(tf_label, pair_key, change, ticker_data['price_eur'], threshold_label):
                                SENT_SPIKE_NOTIFICATIONS[tf_label][pair_ticker][threshold_label] = True
                                # Bryt efter att ha skickat den högsta tröskeln för att undvika dubbelnotis
                                break 
                        
                        # Återställningslogik: Återställ flaggan om priset backar till 25% av tröskelvärdet
                        reset_needed = False
                        if already_sent:
                            # För positiva trösklar: Återställ om förändringen faller under 25% av tröskeln
                            if threshold_value > 0 and change < (threshold_value * 0.25):
                                reset_needed = True
                            # För negativa trösklar: Återställ om förändringen stiger över 25% av tröskeln (närmare noll)
                            elif threshold_value < 0 and change > (threshold_value * 0.25):
                                reset_needed = True

                        if reset_needed:
                            SENT_SPIKE_NOTIFICATIONS[tf_label][pair_ticker][threshold_label] = False
                            print(f"[{pair_key}] SPIKE RESET: {threshold_label} på {tf_label} återställd ({change:+.2f}%)")


            # --- STEG 8: Signalbetygsskillnadsnotis ---
            if len(new_ratings) >= 2:
                for (pair1_key, rating1), (pair2_key, rating2) in itertools.combinations(new_ratings.items(), 2):
                    difference = abs(rating1 - rating2)
                    key = tuple(sorted((pair1_key, pair2_key))) # Unik nyckel för paret

                    # Trigger check
                    if difference >= DIFF_THRESHOLD and SENT_DIFF_NOTIFICATIONS.get(key) != True:
                        if notify_diff(pair1_key, rating1, pair2_key, rating2, difference):
                            SENT_DIFF_NOTIFICATIONS[key] = True
                    
                    # Återställ check: Om skillnaden är under 1/3 av tröskeln
                    elif difference < (DIFF_THRESHOLD / 3) and SENT_DIFF_NOTIFICATIONS.get(key) == True:
                        SENT_DIFF_NOTIFICATIONS[key] = False

            # --- STEG 9: Periodisk Sammanfattningsnotis ---
            current_hour = current_time.hour
            if current_hour in SUMMARY_SEND_TIMES:
                last_sent = LAST_SUMMARY_SENT.get(current_hour)
                # Skicka om det är dags och det har gått minst en timme sedan senaste skickade (eller om det aldrig har skickats)
                if last_sent is None or (current_time - last_sent).total_seconds() >= 3600:
                    if notify_periodic_summary():
                        LAST_SUMMARY_SENT[current_hour] = current_time

            # --- STEG 10: Logga till Excel och avsluta låst block ---
            if local_interval_counter % 30 == 0: # Logga var 30:e minut (30 * 60s)
                log_data_to_excel(data_history)
                
            local_interval_counter += 1
            # --- SLUT PÅ LÅST BLOCK ---
        
        # 11. Sova (utanför låset)
        time.sleep(60) # Vänta 60 sekunder
        

# =========================================================================
# === START AV APPLIKATION (Exempel) ===
# För att starta bakgrundstråden behöver du köra den här delen
# =========================================================================

# if __name__ == '__main__':
#     # 1. Ladda historik från Excel
#     load_historical_data()
# 
#     # 2. Skicka testnotis (valfritt)
#     # send_test_notification()
# 
#     # 3. Starta bakgrundstråden
#     collector_thread = threading.Thread(target=background_data_collector, daemon=True)
#     collector_thread.start()
# 
#     # 4. Starta Dash-appen
#     # app.run_server(debug=False, use_reloader=False)