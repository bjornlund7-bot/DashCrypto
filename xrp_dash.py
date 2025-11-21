# =========================================================================
# === KRITISK FÖRSTA BLOCK: Nödvändiga Importer och Globala variabler ===
# === FIXAT: Uppdaterade för att använda modern Dash v2+ syntax (dcc, html) ===
# =========================================================================
import copy
from functools import lru_cache
from datetime import datetime, timedelta
import requests
import threading
import time
import collections
import itertools

# Bibliotek som behövs för logik och Dash-komponenter
import pandas as pd
from scipy.stats import linregress
import numpy as np
import dash
from dash.dependencies import Input, Output
# Rättat: Importerar dcc (dash_core_components) direkt från dash
from dash import dcc 
# Rättat: Importerar html (dash_html_components) direkt från dash
from dash import html 
import plotly.graph_objects as go


df_current_data = pd.DataFrame(columns=['col1', 'col2', 'col3']) # Ersätt med dina faktiska kolumner

# --- Globala inställningar och API-URL:er ---
EXCHANGE_RATE_URL = "https://api.exchangerate-api.com/v4/latest/EUR"
KRAKEN_TICKER_API_URL = "https://api.kraken.com/0/public/Ticker"
KRAKEN_OHLC_API_URL = "https://api.kraken.com/0/public/OHLC"

# Tidsinställningar
UPDATE_INTERVAL_SECONDS_DATA = 60 # Uppdateringsfrekvens för bakgrundstråden (60 sekunder)
UPDATE_INTERVAL_MS_WEB = 10000 # Uppdateringsfrekvens för webbplatsen (10 sekunder)
DASH_PORT = 8050
SUMMARY_SEND_TIMES = ["08:00", "12:00", "18:00", "22:00"] # Exempel

# Algoritm-inställningar
MAX_DASH_POINTS = 100 # Max antal punkter i historik (100 minuter)
SUMMARY_TREND_POINTS_30M = 30 # Används för 30m trend (Linjär regression)
SUMMARY_TREND_POINTS_360M = 360 # Max längd för deque/graf
REVERSION_THRESHOLD = 0.005 # 0.5% (Används i generate_mts_signal)
DIFF_THRESHOLD = 5 # Dummy-värde för notiser

# --- Valutor ---
CRYPTO_PAIRS = {
    'XRP': 'XXRPEUR', # Använd dina faktiska Kraken-tickrar här
    'BTC': 'XXBTZEUR',
    'ETH': 'XETHZEUR',
}
DEFAULT_PAIR_KEY = 'XRP'

# --- Trådhantering och Data Cacher ---
data_lock = threading.Lock()
global_kpi_cache = {}
# data_history maxlen är 360 minuter för att rymma 6 timmars data för grafer
data_history = collections.defaultdict(lambda: collections.deque(maxlen=SUMMARY_TREND_POINTS_360M))
current_signal_ratings = {}
SENT_NOTIFICATIONS = {}
SENT_DIFF_NOTIFICATIONS = {}
SENT_SPIKE_NOTIFICATIONS = {}
LAST_SUMMARY_SENT = datetime.min # För periodisk sammanfattning

# --- Dash app initialization ---
import dash # Säkerställ att dash är importerad om den inte fanns i blocket innan
app = dash.Dash(__name__)


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

    # Koden för initial datainsamling (före while True) behöver också felhantering
    initial_data_fetch = False
    with data_lock:
        if not global_kpi_cache:
            initial_data_fetch = True
            
    if initial_data_fetch:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Initial datainsamling påbörjad...")
        
        # --- LOOP FÖR INITIAL DATAINSAMLING ---
        for pair_key, pair_ticker in CRYPTO_PAIRS.items():
            
            # Steg 1: Försök Hämta Data
            print(f"🟢 Försöker hämta Ticker för {pair_key} ({pair_ticker})...") 
            
            ticker_data, error = get_crypto_data(pair_ticker)
            
            # Steg 2: Diagnostik och Felhantering (NY KOD FÖR BÄTTRE FELSÖKNING)
            if error:
                 # KRITISK LOGG: Logga felmeddelandet och hoppa över detta par
                 print(f"🔴 [FEL] Initial Ticker-hämtning för {pair_key}. FEL: {error}")
                 continue 
            elif not ticker_data:
                 # VARNING: Logga om data är tom trots att inget fel rapporterades
                 print(f"⚠️ [VARNING] Ticker-hämtning för {pair_key} returnerade ingen data och inget fel. Hoppar över.")
                 continue
            else:
                 # FRAMGÅNG: Logga priset för att bekräfta data
                 print(f"🟢 [OK] Ticker-hämtning för {pair_key} lyckades. Pris EUR: {ticker_data.get('price_eur', 'N/A')}")
                 
            # Steg 3: Initial Caching (Endast om data är OK)
            if ticker_data:
                with data_lock:
                    global_kpi_cache[pair_ticker] = {
                        **ticker_data,
                        'price_7d_eur': ticker_data['price_eur'],
                        'price_30d_eur': ticker_data['price_eur'],
                        'price_7d_sek': ticker_data['price_sek'],
                        'price_30d_sek': ticker_data['price_sek'],
                        'percent_change_100m': 0.0,
                        'percent_change_360m': 0.0,
                        'trend_30m_percent': 0.0,
                        'trend_30m_color': '#555555',
                        'time': datetime.now(),
                        'signal_rating': 0,
                        'signal_text': 'Väntar på historik',
                        'signal_color': '#555555',
                    }
                    data_history[pair_ticker].append({
                        'time': datetime.now(), 
                        'price_sek': ticker_data['price_sek'],
                        'price_eur': ticker_data['price_eur']
                    })
        
        # Logga när Initial cashing är helt klar
        print(f"🟢 [UPPSTART SLUTFÖRD] Initial cashing för alla par slutförd. Går till periodisk loop.")
        # --- SLUT PÅ INITIAL DATAINSAMLING ---


    while True:
        
        # Säkerställ att vi låser när vi skriver till delade globala variabler
        with data_lock:            
            # --- START PÅ LÅST BLOCK ---
            
            eur_sek_rate = get_eur_sek_rate()
            current_time = datetime.now()
            new_ratings = {}
            print(f"\n--- Datauppdatering startad: {current_time.strftime('%Y-%m-%d %H:%M:%S')} ---")

            local_interval_counter += 1
            is_ohlc_update_time = local_interval_counter % 60 == 0 # Varje hel timme

            # Första loop: Hämta Ticker-data, uppdatera historik, hämta OHLC
            for pair_key, pair_ticker in CRYPTO_PAIRS.items():
                
                # 1. Hämta Ticker-data
                ticker_data, error = get_crypto_data(pair_ticker)

                # --- Huvudloop: Ticker FELHANTERING ---
                if error:
                    print(f"🔴 [FEL Ticker] {pair_key}: {error}") 
                    continue # Hoppa till nästa par om fel uppstår
                
                cached_kpi = global_kpi_cache.get(pair_ticker, {})
                current_price_sek = ticker_data['price_sek']
                
                # 2. Uppdatera lokal historik (Deque)
                data_history[pair_ticker].append({
                    'time': current_time, 
                    'price_sek': ticker_data['price_sek'],
                    'price_eur': ticker_data['price_eur']
                })
                local_history_list = list(data_history[pair_ticker]) 

                # 3. Hämta/Uppdatera OHLC-data (Endast vid uppdatering)
                price_7d_eur, price_7d_sek = cached_kpi.get('price_7d_eur'), cached_kpi.get('price_7d_sek')
                price_30d_eur, price_30d_sek = cached_kpi.get('price_30d_eur'), cached_kpi.get('price_30d_sek')
                
                if is_ohlc_update_time:
                    p7e, p7s, error_7d = get_ohlc_price(pair_ticker, 7, eur_sek_rate)
                    if not error_7d:
                        price_7d_eur, price_7d_sek = p7e, p7s
                    else:
                        print(f"🔴 [FEL OHLC 7d] {pair_key}: {error_7d}")
                    
                    p30e, p30s, error_30d = get_ohlc_price(pair_ticker, 30, eur_sek_rate)
                    if not error_30d:
                        price_30d_eur, price_30d_sek = p30e, p30s
                    else:
                        print(f"🔴 [FEL OHLC 30d] {pair_key}: {error_30d}")


                # 4. Beräkna trend-KPI:er
                trend_30m_percent, trend_30m_text, trend_30m_color = calculate_30min_trend(pair_ticker, local_history_list)
                percent_change_100m = calculate_100min_change(local_history_list)
                percent_change_360m = calculate_360min_change(local_history_list)

                # 5. Skapa KPI-objekt för MTS-signal
                mts_kpi_data = {
                    'price_sek': current_price_sek,
                    'high_24h_sek': ticker_data['high_24h_sek'],
                    'low_24h_sek': ticker_data['low_24h_sek'],
                    'price_7d_sek': price_7d_sek,
                    'price_30d_sek': price_30d_sek,
                    'percent_change_100m': percent_change_100m,
                    'percent_change_360m': percent_change_360m,
                }
                
                # 6. Beräkna MTS-signal
                signal_text, total_rating, signal_color, percent_7d, percent_30d = generate_mts_signal(mts_kpi_data, local_history_list)
                
                # 7. Uppdatera global KPI cache
                global_kpi_cache[pair_ticker] = {
                    **ticker_data,
                    'price_7d_eur': price_7d_eur,
                    'price_30d_eur': price_30d_eur,
                    'price_7d_sek': price_7d_sek,
                    'price_30d_sek': price_30d_sek,
                    'percent_change_100m': percent_change_100m,
                    'percent_change_360m': percent_change_360m,
                    'trend_30m_percent': trend_30m_percent,
                    'trend_30m_text': trend_30m_text,
                    'trend_30m_color': trend_30m_color,
                    'percent_7d': percent_7d,
                    'percent_30d': percent_30d,
                    'time': current_time,
                    'signal_rating': total_rating,
                    'signal_text': signal_text,
                    'signal_color': signal_color,
                }
                new_ratings[pair_ticker] = total_rating

                # 8. Notis-logik (Här skulle notis-logiken placeras)
                # ... (notify_spike, notify_diff, etc.) ...

            # 9. Uppdatera signalratings för att matas in i Dash-callbacks
            current_signal_ratings = new_ratings

            # 10. Periodisk Sammanfattning
            # ... (logik för notify_periodic_summary) ...

            # 11. Excel-loggning var 5:e minut
            # ... (log_data_to_excel) ...


            # Loggar framgång för den fullständiga loopen
            print(f"🟢 [OK] Datauppdatering slutförd för alla par. {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"--- Datauppdatering klar: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")

            # --- SLUT PÅ LÅST BLOCK ---
            
        # Nödvändig paus för att undvika CPU-överbelastning och kontrollera uppdateringsfrekvensen
        time.sleep(UPDATE_INTERVAL_SECONDS_DATA)



# =========================================================================
# === NYTT BLOCK: Säkerhets- och Prestandaförbättringar (Fixar headers) ===
# =========================================================================

# 1. Sätter default maxålder för statiska filer (t.ex. 1 vecka)
# Fixar "A 'cache-control' header is missing or empty."
app.server.send_file_max_age_default = 60 * 60 * 24 * 7 # En vecka i sekunder

# 2. Lägger till säkerhetsrubriker till alla svar
# Fixar "Response should include 'x-content-type-options' header."
@app.server.after_request
def add_security_headers(response):
    # Förhindrar MIME-sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    
    # Sätter Content-Type charset till UTF-8 explicit om det saknas (Fixar charset-varningen)
    if 'content-type' in response.headers and 'charset' not in response.headers['content-type'].lower():
        response.headers['Content-Type'] += '; charset=utf-8'
        
    return response

# =========================================================================

# --- Hjälpfunktioner för formatering ---
def format_price_eur(price):
    if price is None: return "N/A"
    return f"€{price:,.8f}".rstrip('0').rstrip('.')

def format_price_sek(price):
    if price is None: return "N/A"
    # Mer aggressiv formatering för SEK (mindre decimaler)
    return f"{price:,.2f} kr"

def format_percent(percent):
    if percent is None: return "N/A"
    if percent >= 0: return f"+{percent:,.2f}%"
    return f"{percent:,.2f}%"

# --- Dummy-funktioner för notiser/loggning (antas finnas) ---
def notify_single(message): print(f"🔔 [NOTIS]: {message}")
def notify_spike(message): print(f"🚨 [SPETSVARNING]: {message}")
def notify_diff(message): print(f"⚠️ [DIFF VARNING]: {message}")
def notify_periodic_summary(message): print(f"📋 [SAMMANFATTNING]: {message}")
def log_data_to_excel(): pass # Dummy-funktion

# =========================================================================
# === START PÅ DIN URSPRUNGLIGA DEL 2 ===
# =========================================================================
@lru_cache(maxsize=1)
def get_eur_sek_rate():
    """Hämtar aktuell EUR/SEK växelkurs. Använder 11.50 SEK som fallback."""
    
    # 1. Hämta URL inuti try-blocket för att fånga NameError (om URL inte är definierad)
    try:
        # Kontrollera att variabeln är definierad
        url = EXCHANGE_RATE_URL 
        
        # Logga för felsökning
        print(f"DEBUG: Försöker hämta EUR/SEK från: {url}") 
        
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if 'rates' in data and 'SEK' in data['rates']:
            print("DEBUG: EUR/SEK lyckades.")
            return data['rates']['SEK']
        
        print("DEBUG: Kunde inte parsa EUR/SEK-data. Använder standardvärde.")
        return 11.50
        
    except NameError as name_e:
        # Fånga om EXCHANGE_RATE_URL inte är definierad globalt
        print(f"🔴 [KRITISKT FEL] Variabeln EXCHANGE_RATE_URL är odefinierad. {name_e}")
        return 11.50
    except requests.exceptions.RequestException as req_e:
        print(f"🔴 [FEL] Nätverksfel vid EUR/SEK hämtning. Använder standardvärde. {req_e}")
        return 11.50
    except Exception as e:
        print(f"🔴 [FEL] Oväntat fel vid EUR/SEK hämtning. Använder standardvärde. {e}")
        return 11.50
### ÄNDRING: Returnera BÅDE EUR och SEK pris ###
def get_ohlc_price(pair_ticker, since_days_ago, eur_sek_rate):

    # --- NYTT: Headers för att lura Kraken att vi är en webbläsare ---
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    # ----------------------------------------------------------------

    # Beräkna 'since' timestamp (i sekunder)
    # 86400 sekunder per dygn
    since_timestamp = time.time() - (since_days_ago * 86400) 
    
    payload = {
        'pair': pair_ticker,
        'interval': 60, # 60 minuter = 1 timme
        'since': int(since_timestamp)
    }
    
    print(f"DEBUG: Försöker hämta OHLC-data för {pair_ticker} sedan {since_days_ago} dagar.")

    try:
        # Gör API-anropet till Kraken med headers
        response = requests.get(KRAKEN_OHLC_API_URL, params=payload, headers=headers, timeout=10)
        response.raise_for_status() # Kasta undantag för 4xx/5xx fel
        
        data = response.json()
        
        # Kontrollera om Kraken returnerade ett fel
        if data.get('error'):
            kraken_error = data['error']
            # Ofta: EQuery:Unknown asset pair - om XXRPEUR är fel
            print(f"🔴 [FEL FRÅN KRAKEN] Kunde inte hämta OHLC för {pair_ticker}. Fel: {kraken_error}")
            return (None, None) # Returnera None för båda datastrukturerna

        # Hämta data-arrayen (key är 'XXRPEUR' eller vad pair_ticker är)
        data_key = list(data['result'].keys())[0]
        ohlc_data = data['result'][data_key]
        
        # Kolumnindex: [0=time, 1=open, 2=high, 3=low, 4=close, 5=vwap, 6=volume, 7=count]
        
        # Konvertera till DataFrame (EUR-data)
        df_eur = pd.DataFrame(ohlc_data, columns=[
            'time', 'open', 'high', 'low', 'close', 'vwap', 'volume', 'count'
        ])
        
        # Konvertera strängkolumner till numeriska, ignorera tidsstämpel (kolumn 0)
        numeric_cols = ['open', 'high', 'low', 'close', 'vwap', 'volume']
        for col in numeric_cols:
             df_eur[col] = pd.to_numeric(df_eur[col], errors='coerce')

        # Konvertera tid (timestamp) till datetime-objekt
        df_eur['time'] = pd.to_datetime(df_eur['time'], unit='s')
        
        # --- NYTT: Skapa SEK DataFrame ---
        df_sek = df_eur.copy()
        for col in ['open', 'high', 'low', 'close', 'vwap']:
            df_sek[col] = df_eur[col] * eur_sek_rate
        
        print(f"🟢 DEBUG: OHLC-data för {pair_ticker} hämtad och konverterad. Rader: {len(df_eur)}")
        
        # Returnera BÅDE EUR och SEK dataframes
        return (df_eur, df_sek)

    except requests.exceptions.Timeout:
        print(f"🔴 [FEL] Timeout (10s) vid hämtning av Kraken OHLC för {pair_ticker}.")
        return (None, None)
    except requests.exceptions.RequestException as req_e:
        print(f"🔴 [FEL] Nätverksfel vid Kraken OHLC för {pair_ticker}. {req_e}")
        return (None, None) 
    except Exception as e:
        print(f"🔴 [KRITISKT FEL] Oväntat fel vid bearbetning av OHLC-data för {pair_ticker}. {e}")
        return (None, None)
    # ----------------------------------------------------------------

    """Hämtar historiskt slutpris (stängningspris) från Kraken OHLC API."""
    
    # OBS: Använder since_days_ago för att beräkna target_timestamp.
    # Vi hämtar lite extra data (typ 10 dagar innan) för att säkerställa att vi fångar det exakta stängningspriset.
    since_time = datetime.now() - timedelta(days=since_days_ago)
    since_unix = int((since_time - timedelta(days=10)).timestamp())
    params = {'pair': pair_ticker, 'interval': 1440, 'since': since_unix}

    try:
        # KORRIGERING 1: Lägg till headers=headers i anropet
        response = requests.get(KRAKEN_OHLC_API_URL, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('error') and data['error']:
            # KORRIGERING 2: Logga fel vid API-svar
            print(f"🔴 [FEL] OHLC API-fel för {pair_ticker}: {data['error']}")
            return None, None, f"OHLC Fel: {data['error']}."

        kraken_pair_key = list(data['result'].keys())[0]
        ohlc_data = data['result'][kraken_pair_key]

        target_timestamp = since_time.timestamp()
        best_match_price_eur = None

        # Sök bakåt för det senaste stängningspriset FÖRE target_timestamp
        for entry in reversed(ohlc_data):
            timestamp = entry[0]
            if timestamp < target_timestamp:
                best_match_price_eur = float(entry[4]) # index 4 är stängningspris
                break

        if best_match_price_eur is not None:
            # Returnera (price_eur, price_sek, error)
            return best_match_price_eur, (best_match_price_eur * eur_sek_rate), None

        return None, None, f"Ingen tillförlitlig OHLC-data hittades."

    except Exception as e:
        # KORRIGERING 3: Logga nätverksfel vid exception
        print(f"🔴 [FEL] Fel vid hämtning av OHLC-data för {pair_ticker}: {e}")
        return None, None, f"Fel vid hämtning av OHLC-data: {e}"
### SLUT PÅ ÄNDRING ###


### ÄNDRING: Omdöpt och modifierad för att returnera EUR, SEK och valutaneutral 24h% ###

def get_crypto_data(pair_ticker):
    """Hämtar Aktuellt pris (EUR & SEK) och 24h KPI:er. Inkluderar robust felhantering."""
    
    # 1. Valutakurs
    # Antar att denna funktion (get_eur_sek_rate) är definierad någon annanstans
    eur_sek_rate = get_eur_sek_rate() 
    
    # 2. Headers för API-anrop
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    API_URL = f"https://api.kraken.com/0/public/Ticker?pair={pair_ticker}"
    
    # --- KRITISK TRY/EXCEPT FÖR ATT FÅNGA NÄTVERK- OCH PARSNINGSFEL ---
    try:
        # 3. Gör API-anropet med en timeout
        response = requests.get(API_URL, headers=headers, timeout=10)
        
        # Kastar ett undantag för 4xx/5xx fel
        response.raise_for_status()
        
        data = response.json()
        
        # Kontrollera om Kraken returnerade ett fel
        if data.get('error'):
            kraken_error = ", ".join(data['error'])
            return None, f"Kraken API-fel: {kraken_error}"

        # 4. Parsning (ANPASSAS AV DIG)
        result_key = list(data['result'].keys())[0]
        ticker = data['result'][result_key]
        
        # --- Din parsningslogik bör se ut ungefär så här ---
        current_price_eur = float(ticker['c'][0])
        percent_change_24h = float(ticker['p'][1]) # Antag att det här är 24h change
        high_24h_eur = float(ticker['h'][1])
        low_24h_eur = float(ticker['l'][1])

        # 5. Konvertera till SEK och skapa returobjekt
        ticker_data = {
            'price_eur': current_price_eur,
            'price_sek': current_price_eur * eur_sek_rate,
            'percent_change_24h': percent_change_24h,
            'high_24h_eur': high_24h_eur,
            'low_24h_eur': low_24h_eur,
            'high_24h_sek': high_24h_eur * eur_sek_rate,
            'low_24h_sek': low_24h_eur * eur_sek_rate,
            # Lägg till andra KPI:er du använder
        }
        
        return ticker_data, None # Ingen fel
        
    except requests.exceptions.RequestException as req_err:
        # Fångar nätverksfel (timeout, DNS-fel, anslutningsfel)
        return None, f"Nätverksfel vid API-anrop: {req_err}"
    except Exception as e:
        # Fångar alla andra fel (JSONDecodeError, KeyError vid parsing)
        return None, f"Allmänt fel i get_crypto_data: {type(e).__name__}: {e}"
    # Initialisera variabler för att undvika UnboundLocalError om 'try' misslyckas
    latest_price_eur, high_24h_eur, low_24h_eur, open_24h_eur = 0.0, 0.0, 0.0, 0.0
    percent_change_24h = 0.0
    price_sek, high_sek, low_sek, open_sek = 0.0, 0.0, 0.0, 0.0
    
    try:
        params = {'pair': pair_ticker}
        
        # VIKTIGT: Lägg till headers=headers här
        response = requests.get(KRAKEN_TICKER_API_URL, params=params, headers=headers, timeout=10)
        
        # --- NY KRITISK LOGGNING FÖR ATT FÅNGA STATUSKODEN INNAN DEN ORSAKAR ETT EXCEPTION ---
        if response.status_code != 200:
            print(f"🔴 [STATUSFEL] Kraken Ticker returnerade status: {response.status_code} för {pair_ticker}. Full respons: {response.text[:200]}") # <-- ÄNDRING/NY RAD
            
        response.raise_for_status() # Detta kastar HTTPError om status inte är 200
        data = response.json()

        if data.get('error') and data['error']: 
            return None, f"Ticker Fel: {data['error']} för {pair_ticker}"

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
        
        else: 
            return None, f"Fick ett tomt Ticker-resultat."

    except Exception as e: 
        # Här fångas HTTPError (om statuskoden inte var 200) eller andra fel
        return None, f"Fel vid hämtning av Ticker-data: {e}"

    # Dessa rader körs endast om 'try' lyckades, eller om 'try' avslutades med 'return None, error'
    
    # Procentuell skillnad hög och låg på 24h
    formel2 = ((high_24h_eur - low_24h_eur) / latest_price_eur) * 100 if latest_price_eur != 0 else 0

    if formel2 is not None:
        formel = f"{formel2:.2f}%"
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
        'percent_change_24h': percent_change_24h,
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
    slope, intercept, r_value, p_value, std_err = linregress(x_time_numeric, y_price)

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
    # Observera: kpi_data måste anpassas för att matcha de nya SEK-nycklarna från background_data_collector
    price_sek = kpi_data['price_sek']
    high_24h = kpi_data['high_24h_sek']
    low_24h = kpi_data['low_24h_sek']

    price_7d_ago = kpi_data.get('price_7d_sek')
    price_30d_ago = kpi_data.get('price_30d_sek')
    
    percent_change_100m = kpi_data.get('percent_change_100m', 0.0)
    percent_change_360m = kpi_data.get('percent_change_360m', 0.0)


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
    # percent_change_100m och 360m hämtas nu från kpi_data (som sätts i collectorn)

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
# === START PÅ DIN URSPRUNGLIGA DEL 3 ===
# =========================================================================

# Funktionen för att skapa instrumentpanelens layout
def create_dashboard_layout():
    # --- WEBBFÄRGER/TEMA DEFINITION ---
    DARK_BACKGROUND = '#2d3748' # Mörk bakgrund
    LIGHT_TEXT = '#edf2f7'       # Ljus text
    CARD_BACKGROUND_CONTRAST = '#4a5568' # Bakgrund för enskilda kort/element (inte översikt)
    BORDER_COLOR = '#666'        # Ljusare grå kant

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




# Följande funktion MÅSTE definieras globalt eftersom den används i callbacken
def calculate_sma(df, window, price_key):
    """Beräknar Simple Moving Average (SMA)."""
    # Se till att denna funktion finns i din fullständiga kodfil.
    # Jag inkluderar en placeholder här om den saknas.
    return df[price_key].rolling(window=window, min_periods=1).mean()


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


### ÄNDRING: Lyssnar nu på valutaväljaren + DEEPCOPY-KORRIGERING ###
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
        # **KORRIGERING: Använd deepcopy för att undvika data race-villkor med nested objects**
        local_kpi_cache = copy.deepcopy(global_kpi_cache)

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
        diff_24h_eur = kpi.get('formel') # Denna nyckel verkar vara oanvänd/felaktig i koden

        
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


### ÄNDRING: Lyssnar nu på valutaväljaren + DEEPCOPY-KORRIGERING ###
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
        # **KORRIGERING: Använd deepcopy**
        local_kpi_cache = copy.deepcopy(global_kpi_cache)
        
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

### ÄNDRING: Lyssnar nu på valutaväljaren + DEEPCOPY-KORRIGERING ###
@app.callback(
    Output('live-graph', 'figure'),
    [Input('hidden-data-refresh', 'children'),
     Input('crypto-pair-dropdown', 'value'),
     Input('currency-selector', 'value')] # Ny Input
)
def update_graph(hidden_refresh, selected_ticker, selected_currency):
    
    # Läs globala variabler under lås
    with data_lock:
        # **KORRIGERING: Använd deepcopy på history**
        history = copy.deepcopy(data_history.get(selected_ticker, collections.deque()))
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
        # calculate_sma MÅSTE vara definierad globalt
        df[f'SMA_{window}'] = calculate_sma(df, window, price_key) 
    
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
    # --- SLUT PÅ 24h Hög/Låg ---

    # Beräkna aktuell signalfärg (används för att markera aktuell punkt)
    signal_color = kpi.get('signal_color', '#999999')
    current_price = df[price_key].iloc[-1]
    current_time = df['time'].iloc[-1]
    
    # Lägg till en markör för den sista punkten
    fig.add_trace(go.Scatter(
        x=[current_time], 
        y=[current_price], 
        mode='markers', 
        name='Nuvarande Pris',
        marker=dict(size=10, color=signal_color, line=dict(width=2, color='white')),
        hoverinfo='name+y'
    ))

    fig.update_layout(
        title=f"{pair_key} Prisutveckling ({unit} - Senaste {len(df)} minuter)",
        xaxis_title="Tidpunkt",
        yaxis_title=f"Pris ({unit})",
        xaxis=dict(
            rangeselector=dict(
                buttons=list([
                    dict(count=60, label="1h", step="minute", stepmode="backward"),
                    dict(count=360, label="6h", step="minute", stepmode="backward"),
                    dict(step="all")
                ])
            ),
            rangeslider=dict(visible=False),
            type="date"
        ),
        template="plotly_dark", 
        hovermode="x unified",
        margin=dict(l=40, r=40, t=60, b=20),
        shapes=shapes, # Lägg till Hög/Låg linjerna
        annotations=annotations # Lägg till Hög/Låg etiketterna
    )

    # Förbättrad Y-axel formatering baserat på prisstorlek
    if current_price < 0.1:
        tickformat = '.8f'
    elif current_price < 10:
        tickformat = '.4f'
    elif current_price < 1000:
        tickformat = '.2f'
    else:
        tickformat = '.0f'

    fig.update_yaxes(tickformat=tickformat)

    return fig
### SLUT PÅ ÄNDRING ###

# =========================================================================
# === NY FUNKTION: Bakgrundsinsamlare med Kritisk Felhantering ===
# =========================================================================
import traceback


# =========================================================================
# === HUVUDFUNKTION OCH START AV APPLIKATIONEN ===
# =========================================================================

# 1. Sätt Layouten OMEDELBART
app.layout = create_dashboard_layout()

# 2. Starta Bakgrundstråden OMEDELBART
already_running = any(t.name == "BackgroundCollector" for t in threading.enumerate())
if not already_running:
    # Använd den nya funktionen med felhantering
    data_thread = threading.Thread(target=background_data_collector, name="BackgroundCollector", daemon=True) 
    data_thread.start()
    print(">>> Bakgrundstråd startad <<<")

# 3. Definiera Servern
server = app.server

# 4. Detta block körs BARA om du testar filen lokalt på din dator
if __name__ == '__main__':
    # ... [din existerande __main__ logik] ...
    print("---------------------------------------------------------")
    print(f">>> Startar Dash lokalt (port {DASH_PORT})... <<<")
    print("---------------------------------------------------------")
    app.run_server(debug=False, port=DASH_PORT, host='0.0.0.0')