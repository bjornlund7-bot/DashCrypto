import requests
import time
from datetime import datetime, timedelta
import pandas as pd
from dash import Dash, dcc, html, Input, Output, State
import plotly.graph_objects as go
import collections
from scipy.stats import linregress
import numpy as np
import os
import openpyxl
from functools import lru_cache
import itertools
import threading
from dash import exceptions
import re
import sys
import requests
import json
import logging
from redis import from_url, exceptions
import logging
import gunicorn

# --- Konstanter ---
KRAKEN_TICKER_API_URL = "https://api.kraken.com/0/public/Ticker"
KRAKEN_OHLC_API_URL = "https://api.kraken.com/0/public/OHLC"
EXCHANGE_RATE_URL = "https://api.exchangerate-api.com/v4/latest/EUR"

### ÄNDRING: Uppdaterade etiketter till EUR som standard ###
# Lista över tillgängliga kryptopar och deras Kraken-tickers (baserade i EUR)
CRYPTO_PAIRS = {
    'XRP (Ripple)': 'XRPEUR',
    'BTC (Bitcoin)': 'BTCEUR',
    'ETH (Ethereum)': 'ETHEUR',
    'SOL (Solana)': 'SOLEUR',
    'GRASS (Grass)': 'GRASSEUR',
    'ADA (Cardano)': 'ADAEUR',
    'DOT (Polkadot)': 'DOTEUR',
    'DOGE (Dogecoin)': 'DOGEEUR',
    'PUMP (PUMP)': 'PUMPEUR',
    'Cookie DAO': 'COOKIEEUR',
    'Moonwalk (MF)': 'MFEUR', 
    'YALA': 'YALAEUR', 
    'WIF (dogwifhat)': 'WIFEUR',
    'YFI (Yearn Finance)': 'YFIEUR',
    'BNB (BNB Chain)': 'BNBEUR',
    'TRX (Tron)': 'TRXEUR',
    'PEPE (Pepe)': 'PEPEEUR',
    'LTC (Litecoin)': 'LTCEUR',
    'TRUMP (Official Trump)': 'TRUMPEUR',
    'XTZ (Tezos)': 'XTZEUR',
    'DASH (Dash)': 'DASHEUR',
    'ZRO (LayerZero)': 'ZROEUR',
    'WOO (Woo Network)': 'WOOEUR',
    'GALA (Gala Games)': 'GALAEUR',
    'SUI (SUI)': 'SUIEUR',
    'BCH (Bitcoin Cash)': 'BCHEUR',
    'ATOM (Cosmos)': 'ATOMEUR',
    'AVAX (Avalanche)': 'AVAXEUR',
    'ICP (Internet Computer Protocol)': 'ICPEUR',
    'ZEC (Zcash)': 'ZECEUR',
    '0G (ZeroGravity)': '0G/EUR', 
    'XDC (XDC Network)': 'XDCEUR',
    'UNI (Uniswap)': 'UNIEUR',
    'IP (Story)': 'IPEUR',
    'INJ (Injective)': 'INJEUR',
    'AR (Arweave)': 'AREUR',
    'EGLD (MultiversX)': 'EGLDEUR',
    'LPT (LivePeer)': 'LPTEUR',
    'KSM (Kusama)': 'KSMEUR',
    'EUL (Euler)': 'EULEUR',
    'GMX (GMX)': 'GMXEUR',
    'AUCTION (Bounce)': 'AUCTIONEUR',
    'MOVR (Moonriver)': 'MOVREUR',
    'SSV (SSV Network)': 'SSVEUR',
    'MLN (Enzyme Finance)': 'MLNEUR',
    'ALCX (Alchemix)': 'ALCXEUR',
    'AERO (Aerodrome Finance)': 'AEROEUR',
    'MYX (MYX Finance)': 'MYXEUR',
    'GNO (Gnosis)': 'GNOEUR',
}
DEFAULT_PAIR_KEY = 'XRP (Ripple)'
### SLUT PÅ ÄNDRING ###

# Filnamn för permanent datalagring (XLSX)
EXCEL_FILE_PATH = os.environ.get("EXCEL_FILE_PATH", "crypto_data_log.xlsx")

# Inställningar för Dash
UPDATE_INTERVAL_MS_WEB = 5000 # Snabbare intervall för ENBART webbuppdateringen (t.ex. 5 sek)
UPDATE_INTERVAL_SECONDS_DATA = 60 # 60 sekunder - DATA HÄMTAS ENDAST I BAKGRUNDSTRÅDEN
MAX_DASH_POINTS = 1440         # 24 h historik
SUMMARY_TREND_POINTS_30M = 30    # 30 minuter
SUMMARY_TREND_POINTS_360M = 360  # 360 minuter (6 timmar)

# SMA-fönster för grafen
SMA_WINDOWS = [SUMMARY_TREND_POINTS_30M, MAX_DASH_POINTS, SUMMARY_TREND_POINTS_360M]

# =========================================================================
# === KONFIGURATION FÖR TELEGRAM (Hämta tokens och chat-ID från Renders miljövariabler) ===

# Byt ut 'DIN_TOKEN_VARIABEL' och 'DITT_CHAT_ID_VARIABEL' mot de exakta namnen
# du har angett i Renders inställningar (t.ex. TELEGRAM_TOKEN och TELEGRAM_CHATID)

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# =========================================================================


# --- Redis Konfiguration Hoppas detta ska hjälpa---
REDIS_URL = os.environ.get('REDIS_URL')

if REDIS_URL:
    try:
        r = from_url(REDIS_URL)
        r.ping()
        logger.debug("✅ Ansluten till Redis!")
    except exceptions.ConnectionError as e:
        logger.error(f"❌ Kunde inte ansluta till Redis: {e}")
        r = None
else:
    logger.warning("REDIS_URL hittades inte. Appen kommer inte att cache:a data.")
    r = None

# Fallback/Standarddata (Endast för att undvika fel om API-anrop misslyckas)
DEFAULT_DATA = {
    'XRP/EUR': 0.50, 'XRP/SEK': 5.50,
    'timestamp': time.time(),
    'EUR_SEK_RATE': 11.0 # Standardväxelkurs
}




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


# -------------------------------------------------------------
app = Dash(__name__)

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


### ÄNDRING: Omdöpt format_sek till format_price_sek och lagt till format_price_eur ###
def format_price_sek(value):
    """Formaterar ett tal till 4 decimaler med tusenavgränsare (mellanslag) i SEK-stil."""
    if not isinstance(value, (int, float)) or np.isnan(value) or value is None:
        return "N/A"
    return f"{value:,.4f}".replace(",", " ").replace(".", ",")

def format_price_eur(value):
    """Formaterar ett tal till 4 decimaler med tusenavgränsare (mellanslag) i EUR-stil."""
    if not isinstance(value, (int, float)) or np.isnan(value) or value is None:
        return "N/A"
    # Använder standard . för decimaler för EUR
    return f"{value:,.4f}".replace(",", " ")

def format_percent(value):
    """Formaterar en procentuell förändring med tecken och 2 decimaler."""
    if value is None:
        return "N/A %"
    if not isinstance(value, (int, float)) or np.isnan(value):
        return "N/A %"
    return f"{value:+.2f} %"
### SLUT PÅ ÄNDRING ###

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
    
    # 1. Hämta en säker kopia av datan
    with data_lock:
        local_kpi_cache = global_kpi_cache.copy()
        
    if not local_kpi_cache:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Sammanfattning misslyckades: KPI-cache är tom.")
        return False
        
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Skickar Periodisk Sammanfattning (360m trend)...")

    # 2. Förbered data för sortering och formatering
    summary_data = []
    
    # OBS: Vi använder CRYPTO_PAIRS.items() för att få det visningsvänliga namnet
    for pair_key, pair_ticker in CRYPTO_PAIRS.items():
        kpi = local_kpi_cache.get(pair_ticker, {})
        
        # Måste ha alla fält
        change_360m = kpi.get('percent_change_360m')
        signal_rating = kpi.get('signal_rating')
        change_24h = kpi.get('percent_change_24h') # HÄMTA NYTT FÄLT: 24h förändring
        aktuellt_varde = kpi.get('current_price_eur') # HÄMTA NYTT FÄLT: Aktuellt varde

        # Välj ett enklare namn för tabellen
        display_name = pair_key.split('/')[0].strip()
        display_name = re.sub(r'\s*\((.*?)\)', '', display_name).strip()


        if change_360m is not None and signal_rating is not None and change_24h is not None:
            summary_data.append({
                'crypto': display_name,
                'change_360m': change_360m,
                'rating': signal_rating,
                'change_24h': change_24h, # Lägg till 24h
                'aktuellt_varde': aktuellt_varde, # 2025-11-18
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
        f"| Krypto | 360m % | 24h % | Betyg | Kurs |\n" # NYA KOLUMNER
        f"|---|---|---|---|---|\n"
    )
    
    table_rows = []
    for item in sorted_summary:
        # Formatera kolumner
        crypto_col = f"`{item['crypto']}`"
        change_360m_col = f"`{format_percent(item['change_360m'])}`"
        change_24h_col = f"`{format_percent(item['change_24h'])}`" # Formatera 24h
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

    price_formatted = f"{current_price_eur:,.4f}".replace(",", "X").replace(".", ",").replace("X", ".")

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
    
    price_formatted = f"{current_price_eur:,.4f}".replace(",", "X").replace(".", ",").replace("X", ".")

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
            ### ÄNDRING: Lägg till båda valutorna i starthistorik ###
            data_history[pair_ticker].append({'time': datetime.now() - timedelta(minutes=max_len), 'price_sek': 0.0, 'price_eur': 0.0})

    if os.path.exists(EXCEL_FILE_PATH):
        try:
            xlsx = pd.ExcelFile(EXCEL_FILE_PATH)
            for pair_key, pair_ticker in CRYPTO_PAIRS.items():
                sheet_name = sanitize_sheet_name(pair_key)
                if sheet_name in xlsx.sheet_names:
                    pair_df = pd.read_excel(xlsx, sheet_name=sheet_name)
                    
                    ### ÄNDRING: Ladda historik för båda valutorna om de finns, annars fallback ###
                    if not pair_df.empty and 'time' in pair_df.columns:
                        pair_df['time'] = pd.to_datetime(pair_df['time'])
                        
                        # Fallback för gamla loggfiler som bara har price_sek
                        if 'price_eur' not in pair_df.columns:
                            pair_df['price_eur'] = 0.0 # Kan inte back-populata, sätter till 0
                        
                        pair_df = pair_df[pair_df['price_sek'] > 0.0].sort_values(by='time').tail(max_len)
                        
                        with data_lock:
                            data_history[pair_ticker].clear()
                            for index, row in pair_df.iterrows():
                                data_history[pair_ticker].append({
                                    'time': row['time'], 
                                    'price_sek': row['price_sek'],
                                    'price_eur': row.get('price_eur', 0.0) # Använd .get() för säkerhets skull
                                })
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Varning: Kunde inte läsa historik från Excel: {e}") 

def log_data_to_excel(data_to_log):
    """Skriver all aktuell historisk data till Excel-filen. Anropas inuti data_lock."""
    
    try:
        with pd.ExcelWriter(EXCEL_FILE_PATH, engine='openpyxl') as writer:
            for pair_key, pair_ticker in CRYPTO_PAIRS.items():
                current_df = pd.DataFrame(data_to_log.get(pair_ticker, []))
                
                ### ÄNDRING: Logga båda valutorna ###
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
### SLUT PÅ ÄNDRING ###

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

### ÄNDRING: Returnera BÅDE EUR och SEK pris ###
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
### SLUT PÅ ÄNDRING ###


### ÄNDRING: Omdöpt och modifierad för att returnera EUR, SEK och valutaneutral 24h% ###
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
        # OBS: Indentering och rätt variabel (formel2) och format (:.2f)
        formel = f"{formel2:.2f}""%"
    else: # OBS: Kolon (:) krävs här
        # OBS: Indentering
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
### SLUT PÅ ÄNDRING ###

def calculate_30min_trend(pair_ticker, history_data):
    """Beräknar den procentuella trenden över de senaste 30 lagrade datapunkterna (linjär regression)."""

    ### ÄNDRING: Använd 'price_sek' för all bakgrundslogik (behåller notiser intakta) ###
    filtered_history = [p for p in history_data if p['price_sek'] > 0.0]

    if not filtered_history or len(filtered_history) < SUMMARY_TREND_POINTS_30M:
        return 0.0, "Väntar på data", "gray"

    df = pd.DataFrame(filtered_history[-SUMMARY_TREND_POINTS_30M:])

    x_time_numeric = np.array([t.timestamp() for t in df['time']])
    y_price = df['price_sek'] # Behåll logik på SEK

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

    ### ÄNDRING: Använd 'price_sek' för all bakgrundslogik ###
    filtered_history = [p for p in history_data if p['price_sek'] > 0.0]

    if len(filtered_history) < 2:
        return 0.0 # Inte tillräckligt med data

    if len(filtered_history) < num_points:
        start_index = 0
    else:
        start_index = len(filtered_history) - num_points
    
    start_price = filtered_history[start_index]['price_sek'] # Behåll logik på SEK
    current_price = filtered_history[-1]['price_sek'] # Behåll logik på SEK
    
    if start_price == 0:
        return 0.0

    percent_change = ((current_price - start_price) / start_price) * 100
    return percent_change
### SLUT PÅ ÄNDRING ###

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
        return rating, "WEAK FILTER (Avvakta)", '#55555K' # Grå


# --- MTS HANDELSALGORITM FUNKTION (UPPDATERAD) ---
def generate_mts_signal(kpi_data, history_data):
    """
    Implementerar Multi-Timeframe Algoritmen (MTS) för 10-steg.
    Total Rating = Long-Term Rating (Max +/-4) + Short-Term Rating (Max +/-6).
    """

    ### ÄNDRING: Använd 'price_sek' för all bakgrundslogik ###
    filtered_history = [p for p in history_data if p['price_sek'] > 0.0]

    if len(filtered_history) < SUMMARY_TREND_POINTS_30M: 
        return "Väntar på 30m data", 0, '#555555', 0.0, 0.0

    # Huvud-KPI:er (Dessa är 'price_sek', 'high_24h_sek' etc. som matas in från background_collector)
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
    ### SLUT PÅ ÄNDRING ###

    # --- STEG 1: LÅNGSIKTIGT BETYG (Max +/- 4) ---
    long_term_rating, filter_status, filter_color = calculate_long_term_rating(percent_7d, percent_30d)

    if abs(long_term_rating) < 1:
        return filter_status, long_term_rating, filter_color, percent_7d, percent_30d

    # --- STEG 2 & 3: KORTSIKTIGT BETYG (Max +/- 6, fördelat 3+3) ---

    df_360m = pd.DataFrame(filtered_history[-SUMMARY_TREND_POINTS_360M:])
    prices_30m = df_360m['price_sek'].tail(SUMMARY_TREND_POINTS_30M) # Behåll logik på SEK

    short_term_rating = 0
    signal_text = filter_status
    signal_color = filter_color

    is_bullish = long_term_rating >= 1
    is_bearish = long_term_rating <= -1


    # --- STEG 2: Medellångt Momentum (Max +/- 3 poäng) (UPPDATERAD) ---
    percent_change_100m = kpi_data['percent_change_100m']
    percent_change_360m = kpi_data['percent_change_360m'] # NY KPI

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
        sma_100m = df_360m['price_sek'].tail(MAX_DASH_POINTS).mean() # Behåll logik på SEK
        previous_price = df_360m['price_sek'].iloc[-2] if len(df_360m) >= 2 else price_sek # Behåll logik på SEK
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


### ÄNDRING: Accepterar 'price_key' för att välja 'price_sek' eller 'price_eur' ###
def calculate_sma(df, window, price_key='price_sek'):
    """Beräknar Simple Moving Average (SMA) för en given Pandas DataFrame."""
    # Använd den specificerade pris-kolumnen
    return df[price_key].rolling(window=min(window, len(df))).mean()
### SLUT PÅ ÄNDRING ###

# =========================================================================
# === NY FUNKTION: DEDIKERAD BAKGRUNDSLOGIK (LÅS-FIX APPLICERAD)
# =========================================================================

def background_data_collector():
    """
    DEDIKERAD TRÅD. Hämtar, bearbetar, lagrar och loggar data i en loop.
    All skrivning till globala cacher sker inuti 'with data_lock:'.
    """
    global global_kpi_cache, SENT_NOTIFICATIONS, SENT_DIFF_NOTIFICATIONS, SENT_SPIKE_NOTIFICATIONS, current_signal_ratings, LAST_SUMMARY_SENT
    
    # Lokal räknare för OHLC/Excel-loggning
    local_interval_counter = 0

    print("---------------------------------------------------------")
    print(">>> Startar 24/7 data-loggning i bakgrundstråd (var 60s) <<<")
    print("---------------------------------------------------------")

    # Initial datainsamling vid start om cachen är tom
    initial_data_fetch = False
    with data_lock:
        if not global_kpi_cache:
            initial_data_fetch = True
            
    if initial_data_fetch:
        print(f"[{datetime.now().strftime('%H:%M:%M')}] Initial datainsamling påbörjad...")
        for pair_key, pair_ticker in CRYPTO_PAIRS.items():
            ### ÄNDRING: Hämta båda valutorna ###
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
            ### SLUT PÅ ÄNDRING ###


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
                
                ### ÄNDRING: Hämta data för båda valutorna ###
                # 1. Hämta Ticker-data
                ticker_data, error = get_crypto_data(pair_ticker)

                if error:
                    print(f"[{pair_key}] FEL vid Ticker-data: {error}")
                    continue

                current_price_sek = ticker_data['price_sek'] # För notiser
                
                # 2. Uppdatera lokal historik (Deque)
                data_history[pair_ticker].append({
                    'time': current_time, 
                    'price_sek': ticker_data['price_sek'],
                    'price_eur': ticker_data['price_eur']
                })
                local_history_list = list(data_history[pair_ticker]) # Uppdaterad lista för beräkningar nedan

                # 3. Hämta OHLC-data (Endast vid uppdatering)
                price_7d_eur, price_7d_sek = None, None
                price_30d_eur, price_30d_sek = None, None
                
                cached_kpi = global_kpi_cache.get(pair_ticker, {})
                
                if is_ohlc_update_time:
                    price_7d_eur, price_7d_sek, error_7d = get_ohlc_price(pair_ticker, 7, eur_sek_rate)
                    if error_7d:
                         print(f"[{pair_key}] Varning vid 7d OHLC: {error_7d}")
                    
                    price_30d_eur, price_30d_sek, error_30d = get_ohlc_price(pair_ticker, 30, eur_sek_rate)
                    if error_30d:
                         print(f"[{pair_key}] Varning vid 30d OHLC: {error_30d}")
                
                # 4. Uppdatera KPI-cache (använd gamla värden om nya OHLC saknas)
                price_7d_ago_eur = price_7d_eur if price_7d_eur is not None else cached_kpi.get('price_7d_eur')
                price_7d_ago_sek = price_7d_sek if price_7d_sek is not None else cached_kpi.get('price_7d_sek')
                price_30d_ago_eur = price_30d_eur if price_30d_eur is not None else cached_kpi.get('price_30d_eur')
                price_30d_ago_sek = price_30d_sek if price_30d_sek is not None else cached_kpi.get('price_30d_sek')
                
                # SÄKERSTÄLL att det finns ett startvärde (för att undvika None i MTS)
                if price_7d_ago_sek is None: price_7d_ago_sek = current_price_sek
                if price_30d_ago_sek is None: price_30d_ago_sek = current_price_sek
                # (Vi behöver inte göra detta för EUR, då MTS-logiken körs på SEK)

                ### SLUT PÅ ÄNDRING ###

                # 5. Beräkna kortsiktiga trender och MTS-signal (BASERAT PÅ SEK)
                trend_30m_percent, trend_30m_text, trend_30m_color = calculate_30min_trend(pair_ticker, local_history_list)
                percent_change_100m = calculate_100min_change(local_history_list)
                percent_change_360m = calculate_360min_change(local_history_list)
                
                # Komplett KPI-paket för MTS-algoritmen (SEK-BASERAD)
                full_kpi_data_for_mts = {
                    'price': ticker_data['price_sek'],
                    'high_24h': ticker_data['high_24h_sek'],
                    'low_24h': ticker_data['low_24h_sek'],
                    'price_7d': price_7d_ago_sek,
                    'price_30d': price_30d_ago_sek,
                    'percent_change_100m': percent_change_100m,
                    'percent_change_360m': percent_change_360m,
                }
                
                signal_text, signal_rating, signal_color, percent_7d, percent_30d = generate_mts_signal(full_kpi_data_for_mts, local_history_list)
                
                current_price_eur = ticker_data.get('price_eur', 0.0) # Använd .get()

                new_ratings[pair_ticker] = signal_rating
                
                # 6. Uppdatera Global KPI Cache (Lagra ALL data, EUR, SEK, och logik)
                global_kpi_cache[pair_ticker] = {
                    **ticker_data, # Innehåller alla price_eur, price_sek, high_24h_eur, etc.
                    'price_7d_eur': price_7d_ago_eur,
                    'price_7d_sek': price_7d_ago_sek,
                    'price_30d_eur': price_30d_ago_eur,
                    'price_30d_sek': price_30d_ago_sek,
                    'time': current_time,
                    'trend_30m_percent': trend_30m_percent, 
                    'trend_30m_text': trend_30m_text,
                    'trend_30m_color': trend_30m_color,
                    'percent_change_100m': percent_change_100m, # Från SEK-logik
                    'percent_change_360m': percent_change_360m, # Från SEK-logik
                    'signal_text': signal_text,
                    'signal_rating': signal_rating,
                    'signal_color': signal_color,
                    'percent_7d': percent_7d, # Från SEK-logik
                    'percent_30d': percent_30d, # Från SEK-logik
                }

                # 7. Kontrollera och skicka TELEGRAM notiser (MTS) - Använder EUR
                if abs(signal_rating) >= 5: # Stark köp/sälj
                    last_notified_rating = SENT_NOTIFICATIONS.get(pair_ticker, 0)
                    
                    if (signal_rating * last_notified_rating <= 0) or (abs(signal_rating) > abs(last_notified_rating)):
                        threading.Thread(target=notify_single, args=(signal_text, pair_key, current_price_eur, signal_rating)).start()
                        SENT_NOTIFICATIONS[pair_ticker] = signal_rating
                
                
                # 8. KONTROLLERA OCH SKICKA ALLA SPIKE-NOTISER (30m, 100m, 360m, 24h)
                
                # Hämta alla relevanta procentförändringar från den nyligen uppdaterade cachen
                kpi = global_kpi_cache[pair_ticker]
                percent_changes = {
                    '30m': kpi.get('trend_30m_percent'),
                    '100m': kpi.get('percent_change_100m'),
                    '360m': kpi.get('percent_change_360m'),
                    '24h': kpi.get('percent_change_24h'), # Denna är valutaneutral
                }

                for tf_label, percent_val in percent_changes.items():
                    
                    if percent_val is None: # Hoppa över om data saknas (t.ex. 30m vid start)
                        continue

                    for label, threshold in SORTED_SPIKE_THRESHOLDS:
                        is_positive_spike = threshold > 0 and percent_val >= threshold
                        is_negative_spike = threshold < 0 and percent_val <= threshold
                        
                        if is_positive_spike or is_negative_spike:
                            # Använd den nya globala state-variabeln
                            if not SENT_SPIKE_NOTIFICATIONS[tf_label][pair_ticker][label]:
                                threading.Thread(target=notify_spike, args=(
                                    tf_label, 
                                    pair_key, 
                                    percent_val, # Skicka rätt procentvärde
                                    current_price_eur, # Använd EUR för notis 
                                    label
                                )).start()
                                SENT_SPIKE_NOTIFICATIONS[tf_label][pair_ticker][label] = True
                                break # Skicka bara den starkaste notisen FÖR DENNA TIDSRAM
                        else:
                            # Återställ flaggan om priset faller under tröskeln
                            if SENT_SPIKE_NOTIFICATIONS[tf_label][pair_ticker][label]:
                                SENT_SPIKE_NOTIFICATIONS[tf_label][pair_ticker][label] = False
                                
                # 9. Återställ notifikationer om signalen är neutral
                if abs(signal_rating) < 1:
                     SENT_NOTIFICATIONS[pair_ticker] = 0

            # 10. Kontrollera Arbitrage-signal
            crypto_keys = list(CRYPTO_PAIRS.keys())
            for key1, key2 in itertools.combinations(crypto_keys, 2):

                ticker1 = CRYPTO_PAIRS[key1]
                ticker2 = CRYPTO_PAIRS[key2]

                rating1 = new_ratings.get(ticker1, 0)
                rating2 = new_ratings.get(ticker2, 0)

                if rating1 is None or rating2 is None:
                    continue

                difference = abs(rating1 - rating2)

                sorted_tickers = sorted([ticker1, ticker2])
                pair_key_tracker = f"{sorted_tickers[0]} __{sorted_tickers[1]}"

                if difference >= DIFF_THRESHOLD: 
                    last_notified_diff = SENT_DIFF_NOTIFICATIONS.get(pair_key_tracker, 0)

                    if difference > last_notified_diff:

                        threading.Thread(target=notify_diff, args=(key1, rating1, key2, rating2, difference)).start()

                        SENT_DIFF_NOTIFICATIONS[pair_key_tracker] = difference

                else:
                    if pair_key_tracker in SENT_DIFF_NOTIFICATIONS:
                        SENT_DIFF_NOTIFICATIONS[pair_key_tracker] = 0
                        
            # 11. Excel-loggning var 5:e minut
            local_interval_counter += 1
            if local_interval_counter % 5 == 0:
                # Skickar kopian av historiken till log_data_to_excel
                log_data_to_excel({ticker: list(history) for ticker, history in data_history.items()})
            
            # 12. Periodisk Sammanfattningskontroll
            now_hour = current_time.hour
            now_minute = current_time.minute
            
            # Skickas endast om timmen är i SUMMARY_SEND_TIMES och minuten är nära 00
            if now_hour in SUMMARY_SEND_TIMES and now_minute < 2:
                last_sent = LAST_SUMMARY_SENT.get(now_hour)
                # Skicka endast om den inte har skickats idag (eller om det är första gången)
                if last_sent is None or last_sent.date() < current_time.date():
                    # Måste skickas utanför data_lock
                    threading.Thread(target=notify_periodic_summary).start() 
                    LAST_SUMMARY_SENT[now_hour] = current_time
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Sammanfattningsnotis skickad för kl {now_hour}:00.")
            
            current_signal_ratings = new_ratings
            
            print(f"--- Datauppdatering klar: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")

            # --- SLUT PÅ LÅST BLOCK ---
        
        # SERVER-STYRD VÄNTETID (Helt oberoende av webbläsaren)
        time.sleep(UPDATE_INTERVAL_SECONDS_DATA) # Väntar 60 sekunder
        
# =========================================================================
# === DASH KOMPONENTER OCH LAYOUT ===
# =========================================================================

# Funktionen för att skapa instrumentpanelens layout
def create_dashboard_layout():
    # --- WEBBFÄRGER/TEMA DEFINITION ---
    DARK_BACKGROUND = '#2d3748' # Mörk bakgrund
    LIGHT_TEXT = '#edf2f7'      # Ljus text
    CARD_BACKGROUND_CONTRAST = '#4a5568' # Bakgrund för enskilda kort/element (inte översikt)
    BORDER_COLOR = '#666'         # Ljusare grå kant

    GLOBAL_STYLE = {
        'max-width': '2400px', 
        'margin': '0 auto', 
        'font-family': 'Arial, sans-serif',
        'background-color': DARK_BACKGROUND,
        'color': LIGHT_TEXT,
        'padding': '20px'
    }

    HEADER_STYLE = {'text-align': 'center', 'color': LIGHT_TEXT, 'margin-bottom': '20px'}

    return html.Div([
        # Titel och uppdateringsintervall
        html.H1("📈 Real-Time Multi-Timeframe Krypto-Övervakning (MTS)", style=HEADER_STYLE),
        
        # Intervallet används BARA för att UPPDATERA WEBBPLATSEN.
        dcc.Interval(
            id='web-update-interval', 
            interval=UPDATE_INTERVAL_MS_WEB, 
            n_intervals=0
        ),
        
        # Dold div för att trigga callbacks
        html.Div(id='background-status', style={'display': 'none'}),

        html.Div(id='current-time', style={'text-align': 'right', 'margin-right': '20px', 'font-size': '14px', 'color': '#aaa'}),

        html.Hr(style={'border-color': BORDER_COLOR}),

        # --- FLYTTAD: Huvudgrafen först efter globala element ---
        # Val av Kryptopar och KPI:er för diagrammet
        html.Div([
            html.Div([
                html.Label("Välj Kryptovaluta för diagrammet:", style={'font-weight': 'bold', 'margin-right': '10px', 'color': LIGHT_TEXT}),
                dcc.Dropdown(
                    id='crypto-pair-dropdown',
                    options=[{'label': k, 'value': v} for k, v in CRYPTO_PAIRS.items()],
                    value=CRYPTO_PAIRS[DEFAULT_PAIR_KEY],
                    style={'width': '300px', 'color': '#333'} 
                )
            ], style={'display': 'flex', 'align-items': 'center', 'margin-bottom': '20px'}),

            ### ÄNDRING: Lagt till valutaväljare ###
            html.Div([
                html.Label("Välj Valuta:", style={'font-weight': 'bold', 'margin-right': '10px', 'color': LIGHT_TEXT}),
                dcc.RadioItems(
                    id='currency-selector',
                    options=[
                        {'label': 'EUR (€)', 'value': 'EUR'},
                        {'label': 'SEK (kr)', 'value': 'SEK'},
                    ],
                    value='EUR', # Standardvaluta EUR
                    labelStyle={'display': 'inline-block', 'margin-right': '15px'},
                    style={'color': LIGHT_TEXT}
                )
            ], style={'display': 'flex', 'align-items': 'center', 'margin-bottom': '20px'}),
            ### SLUT PÅ ÄNDRING ###
            
            # Nuvarande KPI:er för valt par (visas under dropdown)
            html.Div(id='selected-pair-kpis', style={'margin-top': '10px', 'font-size': '16px', 'padding': '10px', 'border': f'1px dashed {BORDER_COLOR}', 'background-color': CARD_BACKGROUND_CONTRAST, 'border-radius': '5px'}),

        ], style={'margin': '20px', 'padding': '10px'}),
        
        dcc.Graph(id='live-graph', config={'displayModeBar': False}),
        
        html.Hr(style={'border-color': BORDER_COLOR}),

        # Översiktstabell (Nu under diagrammet)
        html.H2("📊 Översikt och Signalbetyg (Max +/-10)", style={'margin-left': '20px', 'margin-top': '20px', 'color': LIGHT_TEXT}),
        html.Div(id='summary-table-container', style={'margin': '20px', 'padding': '10px', 'background-color': '#000000', 'border': f'1px solid {BORDER_COLOR}', 'border-radius': '5px'}),
        
        # Dold div, används för att trigga data-beroende callbacks
        html.Div(id='hidden-data-refresh', style={'display': 'none'})

    ], style=GLOBAL_STYLE) 

# --- DASH CALLBACKS (Interaktion och Uppdatering) ---

# Callback för att uppdatera klockslag och simulera en data-refresh för webben
@app.callback(
    [Output('current-time', 'children'),
     Output('hidden-data-refresh', 'children')],
    Input('web-update-interval', 'n_intervals')
)
def update_web_only(n):
    """
    Uppdaterar klockan och triggar de övriga callbacksen.
    """
    current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return current_time_str, f"Webbdata redo för uppdatering {n} gånger."


### ÄNDRING: Lyssnar nu på valutaväljaren ###
@app.callback(
    Output('summary-table-container', 'children'),
    [Input('hidden-data-refresh', 'children'),
     Input('currency-selector', 'value')]
)
def update_summary_table(hidden_refresh, selected_currency):
    
    # --- TEMAVARIABLER DEFINIERAS LOKALT ---
    LIGHT_TEXT = '#edf2f7'         
    CARD_ROW_BACKGROUND = '#000000' 
    # ----------------------------------------
    
    # Läs globala variabler under lås
    with data_lock:
        local_kpi_cache = global_kpi_cache.copy()

    # SÄKERHETSKONTROLL
    if not local_kpi_cache or not local_kpi_cache.get(CRYPTO_PAIRS[DEFAULT_PAIR_KEY], {}).get('price_eur'): # Kontrollera EUR
        return html.Div("Väntar på första datahämtningen...", style={'color': '#777'})

    # --- Ställ in nycklar och formatering baserat på vald valuta ---
    if selected_currency == 'EUR':
        price_key = 'price_eur'
        unit = "EUR"
        format_func = format_price_eur
    else:
        price_key = 'price_sek'
        unit = "SEK"
        format_func = format_price_sek
    # ---

    # Återanvänd Dark Theme färger
    DARK_HEADER_BG = '#333'
    TABLE_STYLE = {'width': '100%', 'border-collapse': 'collapse', 'color': LIGHT_TEXT, 'border': '1px solid #666'}
    CELL_STYLE = {'padding': '8px', 'border': '1px solid #444', 'text-align': 'right'}
    LEFT_CELL_STYLE = {'padding': '8px', 'border': '1px solid #444', 'text-align': 'left'}
    HEADER_CELL_STYLE = {'background-color': DARK_HEADER_BG, 'color': LIGHT_TEXT, 'font-weight': 'bold', 'padding': '10px'}

    
    # NY SORTERING - Numeriskt fallande (Högst signalbetyg överst)
    def get_rating_for_sort(pair_ticker):
        # Sortera efter det faktiska signalbetyget (rating) numeriskt
        return local_kpi_cache.get(pair_ticker, {}).get('signal_rating') or 0
        
    sorted_pairs = sorted(
        CRYPTO_PAIRS.items(),
        key=lambda item: get_rating_for_sort(item[1]),
        reverse=True # Högst betyg (+10) först
    )
    
    # Justering av kolumnbredder (Krypto till 150px)
    table_header = [
        html.Thead(html.Tr([
            html.Th("Krypto", style={**LEFT_CELL_STYLE, **HEADER_CELL_STYLE, 'width': '150px'}), 
            html.Th(f"Pris ({unit})", style={**CELL_STYLE, **HEADER_CELL_STYLE, 'width': '100px'}), # Dynamisk enhet
            html.Th("30m %", style={**CELL_STYLE, **HEADER_CELL_STYLE, 'width': '80px'}),
            html.Th("100m %", style={**CELL_STYLE, **HEADER_CELL_STYLE, 'width': '80px'}),
            html.Th("360m %", style={**CELL_STYLE, **HEADER_CELL_STYLE, 'width': '80px'}),
            html.Th("24h %", style={**CELL_STYLE, **HEADER_CELL_STYLE, 'width': '80px'}), 
            html.Th("7d %", style={**CELL_STYLE, **HEADER_CELL_STYLE, 'width': '80px'}),
            html.Th("30d %", style={**CELL_STYLE, **HEADER_CELL_STYLE, 'width': '80px'}),
            html.Th("SIGNALBETYG", style={**CELL_STYLE, **HEADER_CELL_STYLE, 'width': '100px', 'text-align': 'center'}), 
            html.Th("MTS-Signal", style={**LEFT_CELL_STYLE, **HEADER_CELL_STYLE, 'width': '160px'}), 
            html.Th("30m Trend", style={**LEFT_CELL_STYLE, **HEADER_CELL_STYLE, 'width': '40px'}), 
        ]))
    ]
    
    table_rows = []
    
    for pair_key, pair_ticker in sorted_pairs:
        kpi = local_kpi_cache.get(pair_ticker, {})

        
        # --- ANVÄND .get() MED FALLBACK FÖR ALLA NYCKLAR ---

        price_val = kpi.get(price_key) # Dynamiskt pris
        percent_24h = kpi.get('percent_change_24h') # Valutaneutral
        percent_7d = kpi.get('percent_7d') # Från SEK-logik
        percent_30d = kpi.get('percent_30d') # Från SEK-logik
        percent_100m = kpi.get('percent_change_100m') # Från SEK-logik
        percent_360m = kpi.get('percent_change_360m') # Från SEK-logik
        diff_24h_eur = kpi.get('formel')

        
        # Hämta 30m procent och trend (Linjär Regression)
        percent_30m_linreg = kpi.get('trend_30m_percent')
        trend_30m_color = kpi.get('trend_30m_color', '#555555')
        
        # SÄKERSTÄLL ATT SIGNAL_RATING ALDRIG ÄR NONE
        signal_rating = kpi.get('signal_rating')
        signal_rating_display = f"{signal_rating:+}" if signal_rating is not None else 'N/A'
        
        signal_text = kpi.get('signal_text', "Väntar på data")
        signal_color = kpi.get('signal_color', '#444444')

        # Cell-formatering för Signalbetyg
        rating_style = {
            **CELL_STYLE,
            'text-align': 'center',
            'font-weight': 'bold',
            'background-color': signal_color,
            'color': LIGHT_TEXT 
        }
        
        # Cell-formatering för 30m Trend (Endast Färg)
        trend_30m_style = {
            **CELL_STYLE,
            'background-color': trend_30m_color,
            'color': trend_30m_color, # Textfärgen matchar bakgrunden (döljer texten)
            'width': '40px'
        }
        
        # Sätt färg på % kolumner
        def get_percent_style(percent_val):
            style = CELL_STYLE.copy()
            if percent_val is None: return style
            if percent_val > 0.5: style['color'] = '#00FA9A' # Stark Grön
            elif percent_val > 0: style['color'] = '#3CB371' # Grön
            elif percent_val < -0.5: style['color'] = '#B22222' # Stark Röd
            elif percent_val < 0: style['color'] = '#FF6347' # Röd
            return style

        row_cells = [
            html.Td(pair_key, style={**LEFT_CELL_STYLE, 'font-weight': 'bold'}),
            html.Td(format_func(price_val), style={**CELL_STYLE, 'color': LIGHT_TEXT}), # Dynamisk formatering
            html.Td(format_percent(percent_30m_linreg), style=get_percent_style(percent_30m_linreg)), 
            html.Td(format_percent(percent_100m), style=get_percent_style(percent_100m)),
            html.Td(format_percent(percent_360m), style=get_percent_style(percent_360m)),
            html.Td(format_percent(percent_24h), style=get_percent_style(percent_24h)), 
            html.Td(format_percent(percent_7d), style=get_percent_style(percent_7d)),
            html.Td(format_percent(percent_30d), style=get_percent_style(percent_30d)),
            html.Td(signal_rating_display, style=rating_style), 
            html.Td(signal_text, style={**LEFT_CELL_STYLE, 'color': LIGHT_TEXT}), 
            html.Td(
                diff_24h_eur,
                style={
                     **trend_30m_style,
                     'color': 'black'
                }
            ), # VISAR ENDAST FÄRG
        ]
        
        table_rows.append(html.Tr(row_cells, style={'background-color': CARD_ROW_BACKGROUND}))

    table_body = [html.Tbody(table_rows)]

    return html.Table(table_header + table_body, style=TABLE_STYLE)
### SLUT PÅ ÄNDRING ###


### ÄNDRING: Lyssnar nu på valutaväljaren ###
@app.callback(
    Output('selected-pair-kpis', 'children'),
    [Input('hidden-data-refresh', 'children'),
     Input('crypto-pair-dropdown', 'value'),
     Input('currency-selector', 'value')] # Ny Input
)
def update_selected_pair_kpis(hidden_refresh, selected_ticker, selected_currency):
    
    LIGHT_TEXT = '#edf2f7'
    
    # Läs globala variabler under lås
    with data_lock:
        local_kpi_cache = global_kpi_cache.copy()
        
    # SÄKERHETSKONTROLL
    if not local_kpi_cache or selected_ticker not in local_kpi_cache or not local_kpi_cache[selected_ticker].get('price_eur'):
        return html.Div("Väntar på data för det valda paret...", style={'color': '#aaa'})
         
    kpi = local_kpi_cache[selected_ticker]

    # --- Ställ in nycklar och formatering baserat på vald valuta ---
    if selected_currency == 'EUR':
        price_key = 'price_eur'
        high_key = 'high_24h_eur'
        low_key = 'low_24h_eur'
        unit = "€"
        format_func = format_price_eur
    else:
        price_key = 'price_sek'
        high_key = 'high_24h_sek'
        low_key = 'low_24h_sek'
        unit = "SEK"
        format_func = format_price_sek
    # ---
    
    current_price = kpi.get(price_key)
    high_24h = kpi.get(high_key)
    low_24h = kpi.get(low_key)
    percent_24h = kpi.get('percent_change_24h') # Valutaneutral
    percent_7d = kpi.get('percent_7d') # Från SEK-logik
    percent_30d = kpi.get('percent_30d') # Från SEK-logik
    
    def color_text_by_percent(value):
        color = LIGHT_TEXT
        if value is not None:
            if value > 0.5: color = '#00FA9A'
            elif value > 0: color = '#3CB371'
            elif value < -0.5: color = '#B22222'
            elif value < 0: color = '#FF6347'
        return color

    data_list = [
        html.P([html.Strong("Aktuellt Pris: ", style={'color': '#ADD8E6'}), f"{format_func(current_price)} {unit}"], style={'color': LIGHT_TEXT}),
        html.P([html.Strong("24h Förändring: ", style={'color': '#ADD8E6'}), html.Span(format_percent(percent_24h), style={'color': color_text_by_percent(percent_24h)})]),
        html.P([html.Strong(f"24h Hög/Låg: ", style={'color': '#ADD8E6'}), f"{format_func(high_24h)} {unit} / {format_func(low_24h)} {unit}"], style={'color': LIGHT_TEXT}),
        html.P([html.Strong("7d Förändring: ", style={'color': '#ADD8E6'}), html.Span(format_percent(percent_7d), style={'color': color_text_by_percent(percent_7d)})]),
        html.P([html.Strong("30d Förändring: ", style={'color': '#ADD8E6'}), html.Span(format_percent(percent_30d), style={'color': color_text_by_percent(percent_30d)})]),
    ]
    
    return html.Div(data_list)
### SLUT PÅ ÄNDRING ###

### ÄNDRING: Lyssnar nu på valutaväljaren ###
@app.callback(
    Output('live-graph', 'figure'),
    [Input('hidden-data-refresh', 'children'),
     Input('crypto-pair-dropdown', 'value'),
     Input('currency-selector', 'value')] # Ny Input
)
def update_graph(hidden_refresh, selected_ticker, selected_currency):
    
    # Läs globala variabler under lås
    with data_lock:
        history = data_history.get(selected_ticker, collections.deque())
        kpi = global_kpi_cache.get(selected_ticker, {}) # Hämta KPI
    
    # Använd lokal kopia av historik för att skapa DataFrame utanför låset
    local_history = list(history)
    
    # SÄKERHETSKONTROLL 1: Kontrollera om historiken är för kort eller om KPI saknas
    if not local_history or len(local_history) < 2 or not kpi or not kpi.get('price_eur'):
        return go.Figure(layout=go.Layout(
            title="Väntar på pris- och KPI-data...",
            xaxis={'visible': False},
            yaxis={'visible': False},
            template="plotly_dark"
        ))
    
    # --- Ställ in nycklar och formatering baserat på vald valuta ---
    if selected_currency == 'EUR':
        price_key = 'price_eur'
        high_key = 'high_24h_eur'
        low_key = 'low_24h_eur'
        unit = "EUR"
    else:
        price_key = 'price_sek'
        high_key = 'high_24h_sek'
        low_key = 'low_24h_sek'
        unit = "SEK"
    # ---

    # --- Hämta 24h Hög/Låg från KPI-cachen ---
    high_24h = kpi.get(high_key)
    low_24h = kpi.get(low_key)
    
    # Använd endast de senaste 360 punkterna (maxlängd) för grafritning
    df = pd.DataFrame(local_history) # Använd hela historiken (max 360 punkter)
    df = df[df[price_key] > 0.0] # Filtrera baserat på vald valuta
    
    # SÄKERHETSKONTROLL 2: Om alla priser var 0 i början
    if df.empty:
        return go.Figure(layout=go.Layout(
            title="Väntar på första meningsfulla prisdatan...",
            xaxis={'visible': False},
            yaxis={'visible': False},
            template="plotly_dark"
        ))

    # BERÄKNA FLERA SMA:er
    sma_data = {
        30: {'name': '30m SMA', 'color': '#FFD700'},  # Guld
        100: {'name': '100m SMA', 'color': '#008000'}, # Grön
        360: {'name': '360m SMA', 'color': '#B22222'}, # Eldtegel
    }
    
    for window, details in sma_data.items():
        df[f'SMA_{window}'] = calculate_sma(df, window, price_key) # Använd rätt price_key
    
    pair_key = next((key for key, value in CRYPTO_PAIRS.items() if value == selected_ticker), selected_ticker)
    
    fig = go.Figure()
    
    # Prislinje
    fig.add_trace(go.Scatter(
        x=df['time'], 
        y=df[price_key], # Dynamiskt pris
        mode='lines', 
        name=f'{pair_key} Pris',
        line=dict(color='#00BFFF', width=2) # Djupt himmelsblå
    ))
    
    # Lägg till alla SMA:er i grafen
    for window, details in sma_data.items():
        fig.add_trace(go.Scatter(
            x=df['time'], 
            y=df[f'SMA_{window}'], 
            mode='lines', 
            name=details['name'],
            line=dict(color=details['color'], width=2, dash='dot')
        ))

    # --- Lägg till horisontella linjer för 24h Hög/Låg ---
    shapes = []
    annotations = []

    if high_24h is not None and high_24h > 0:
        shapes.append(
            dict(
                type="line",
                xref="paper", yref="y",
                x0=0, y0=high_24h, x1=1, y1=high_24h,
                line=dict(color="#00FA9A", width=1, dash="dash") # NY FÄRG: GRÖN (Högst)
            )
        )
        annotations.append(
            dict(
                xref="paper", yref="y", x=1.0, y=high_24h, 
                text="24h Högst", showarrow=False, 
                xanchor='left', yanchor='middle', 
                font=dict(color="#00FA9A", size=10) # NY FÄRG
            )
        )
        
    if low_24h is not None and low_24h > 0:
        shapes.append(
            dict(
                type="line",
                xref="paper", yref="y",
                x0=0, y0=low_24h, x1=1, y1=low_24h,
                line=dict(color="#B22222", width=1, dash="dash") # NY FÄRG: RÖD (Lägst)
            )
        )
        annotations.append(
            dict(
                xref="paper", yref="y", x=1.0, y=low_24h, 
                text="24h Lägst", showarrow=False, 
                xanchor='left', yanchor='middle', 
                font=dict(color="#B22222", size=10) # NY FÄRG
            )
        )
    # --- SLUT Lägg till horisontella linjer ---

    fig.update_layout(
        title=f'Prisutveckling för {pair_key} (Senaste {len(df)} min)',
        xaxis_title='Tid',
        yaxis_title=f'Pris ({unit})', # Dynamisk Y-axel
        hovermode="x unified",
        template="plotly_dark", # Använd det mörka Plotly-temat
        margin=dict(l=40, r=40, t=40, b=20),
        shapes=shapes,
        annotations=annotations,
        # Lägg till en layout justering för att säkerställa att legend visas bra
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )

    return fig
### SLUT PÅ ÄNDRING ###

# Lägg till denna rad för att exponera server-instansen för Gunicorn/Render
server = app.server 
# VIKTIGT: Sätt layouten globalt så att den finns när Gunicorn startar servern.
app.layout = create_dashboard_layout()


# --- INITIALISERING OCH KÖRNING ---
if __name__ == '__main__':

    # Använd Renders PORT-miljövariabel, annars 8050 lokalt
    port = int(os.environ.get('PORT', 8050)) 
    app.run_server(debug=True, port=port)
    
    # 1. Ladda historik från Excel (körs en gång vid start)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Laddar historisk data från Excel...")
    load_historical_data()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Historisk data laddad/verifierad.")
    
    # 2. Skicka en testnotis via Telegram (körs en gång vid start)
    send_test_notification()
    
    # 3. Sätt layout (DENNA ÄR BORTTAGEN)
    
    # 4. STARTA DEN DEDIKERADE BAKGRUNDSTRÅDEN
    collector_thread = threading.Thread(target=background_data_collector)
    collector_thread.daemon = True 
    collector_thread.start()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Bakgrundstråd startad.")

    # 5. Kör applikationen
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Startar Dash-servern på http://0.0.0.0:8050/ (host='0.0.0.0').")
    
    app.run(debug=False, host='0.0.0.0', port=8050)