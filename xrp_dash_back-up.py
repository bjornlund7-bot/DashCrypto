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
import threading # NY IMPORT

# --- Konstanter ---
KRAKEN_TICKER_API_URL = "https://api.kraken.com/0/public/Ticker"
KRAKEN_OHLC_API_URL = "https://api.kraken.com/0/public/OHLC"
EXCHANGE_RATE_URL = "https://api.exchangerate-api.com/v4/latest/EUR"

# Lista över tillgängliga kryptopar och deras Kraken-tickers (baserade i EUR)
CRYPTO_PAIRS = {
    'XRP/SEK (Ripple)': 'XRPEUR',
    'BTC/SEK (Bitcoin)': 'BTCEUR',
    'ETH/SEK (Ethereum)': 'ETHEUR',
    'SOL/SEK (Solana)': 'SOLEUR',
    'GRASS/SEK (Grass)': 'GRASSEUR',
    'ADA/SEK (Cardano)': 'ADAEUR',
    'DOT/SEK (Polkadot)': 'DOTEUR',
}
DEFAULT_PAIR_KEY = 'XRP/SEK (Ripple)'

# Filnamn för permanent datalagring (XLSX)
EXCEL_FILE_PATH = 'crypto_data_log.xlsx'

# Inställningar för Dash
UPDATE_INTERVAL_MS = 60000        # 60 sekunder
MAX_DASH_POINTS = 100             # 100 minuter historik (för Dash grafen)
SUMMARY_TREND_POINTS = 30         # 30 minuter för sammanfattningstrenden

# --- GLOBAL LAGER ---
data_history = {pair: collections.deque(maxlen=MAX_DASH_POINTS) for pair in CRYPTO_PAIRS.values()}
global_kpi_cache = {}
SENT_NOTIFICATIONS = {pair: 0 for pair in CRYPTO_PAIRS.values()} # För att undvika Köp/Sälj spam
SENT_DIFF_NOTIFICATIONS = {} 
current_signal_ratings = {} 
SENT_24H_SPIKE_NOTIFICATIONS = {pair: False for pair in CRYPTO_PAIRS.values()}
# Bakgrundsräknare för Excel-loggning/OHLC
background_interval_counter = 0 

# --- KONFIGURATION FÖR TELEGRAM (UPPDATERA DESSA!) ---
TELEGRAM_BOT_TOKEN = '8266312220:AAEpAFiIsf9UjaoKUOR8TCroLJIyIAR5jM4' 
TELEGRAM_CHAT_ID = '8342999996'    
DIFF_THRESHOLD = 6 # Signalvärdesdifferens 
SPIKE_24H_THRESHOLD = 25.0 # Procentuell uppgång över 24h för säljnotis


# --- Formateringsfunktioner ---
def format_sek(value):
    """Formaterar ett tal till 2 decimaler med tusenavgränsare (mellanslag) i SEK-stil."""
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")

def format_percent(value):
    """Formaterar en procentuell förändring med tecken och 2 decimaler."""
    return f"{value:+.2f} %"

# --- TELEGRAM NOTIS FUNKTIONER (OÄNDRAD) ---

def send_telegram_message(message_text):
    """Generisk funktion för att skicka meddelanden via Telegram API."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # Validera konstanter
    if TELEGRAM_BOT_TOKEN == 'DIN_TELEGRAM_BOT_TOKEN' or TELEGRAM_CHAT_ID == 'DITT_TELEGRAM_CHAT_ID':
         print(f"[{datetime.now().strftime('%H:%M:%S')}] FEL: Telegramkonstanter är inte inställda. Hoppar över notis.")
         return False

    try:
        response = requests.post(url, data={
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message_text,
            'parse_mode': 'Markdown' # Använd Markdown för fetstil/struktur
        }, timeout=5)
        response.raise_for_status() # Kasta fel vid dåligt svar (t.ex. 404)
        return True
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] FEL vid skickande av Telegramnotis: {e}")
        return False


def notify_diff(crypto1, rating1, crypto2, rating2, difference):
    """Skickar notis vid stor signalbetygsskillnad."""
    
    message = (
        f"🚨 *ALARM SIGNALDIFFERENS* 🚨\n\n"
        f"Skillnad i signalbetyg har uppnått tröskeln (Diff: `{difference}` >= `{DIFF_THRESHOLD}`).\n\n"
        f"Krypto 1: *{crypto1}* (Betyg: `{rating1}`)\n"
        f"Krypto 2: *{crypto2}* (Betyg: `{rating2}`)\n\n"
        f"Tid: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    return send_telegram_message(message)


def notify_single(signal_text, pair_key, current_price):
    """Skickar notis vid stark Köp/Sälj-signal."""

    message = (
        f"🔔 *STARK SIGNAL* 🔔\n\n"
        f"Kryptovaluta: *{pair_key}*\n"
        f"Signal: *{signal_text}*\n"
        f"Pris: `{format_sek(current_price)} SEK`\n"
        f"Tid: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    return send_telegram_message(message)

def notify_24h_spike(pair_key, percent_change, current_price):
    """Skickar notis vid kraftig 24h uppgång."""

    message = (
        f"🛑 *KRITISK SÄLJVARNING (24H SPÄRR)* 🛑\n\n"
        f"Kryptovaluta: *{pair_key}*\n"
        f"Uppgång: *{format_percent(percent_change)}* på 24 timmar!\n"
        f"Pris: `{format_sek(current_price)} SEK`\n\n"
        f"OBS: Detta indikerar en snabb och stor prisrörelse. Överväg vinsthemtagning.\n"
        f"Tid: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    return send_telegram_message(message)


def send_test_notification():
    """Skickar en testnotis via Telegram."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Försöker skicka TEST-TELEGRAM...")
    
    message = (
        f"✅ *TESTMEDDELANDE* ✅\n\n"
        f"Detta är ett automatiskt testmeddelande från din Kryptospårare.\n"
        f"Telegram-notiser fungerar korrekt.\n\n"
        f"Tid: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    success = send_telegram_message(message)
    if success:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] TEST TELEGRAM SKICKAT. Kontrollera din chatt.")
    else:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] TEST TELEGRAM MISSLYCKADES. Kontrollera Bot Token och Chat ID.")
    return success

# --- ÖVRIGA FUNKTIONER (OÄNDRADE) ---
def load_historical_data():
    """Laddar historik från Excel-filen för alla kända par vid start."""
    global data_history

    for pair_ticker in CRYPTO_PAIRS.values():
        if pair_ticker not in data_history:
            data_history[pair_ticker] = collections.deque(maxlen=MAX_DASH_POINTS)

        if not data_history[pair_ticker]:
             data_history[pair_ticker].append({'time': datetime.now() - timedelta(minutes=MAX_DASH_POINTS), 'price_sek': 0.0})

    if os.path.exists(EXCEL_FILE_PATH):
        try:
            xlsx = pd.ExcelFile(EXCEL_FILE_PATH)
            for pair_key, pair_ticker in CRYPTO_PAIRS.items():
                sheet_name = pair_key.split('/')[0].strip()
                if sheet_name in xlsx.sheet_names:
                    pair_df = pd.read_excel(xlsx, sheet_name=sheet_name)
                    if not pair_df.empty and 'time' in pair_df.columns:
                        pair_df['time'] = pd.to_datetime(pair_df['time'])
                        pair_df = pair_df[pair_df['price_sek'] > 0.0].sort_values(by='time').tail(MAX_DASH_POINTS)
                        data_history[pair_ticker].clear()
                        for index, row in pair_df.iterrows():
                            data_history[pair_ticker].append({'time': row['time'], 'price_sek': row['price_sek']})
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Varning: Kunde inte läsa historik från Excel: {e}")

def log_data_to_excel():
    """Skriver all aktuell historisk data till Excel-filen."""
    try:
        with pd.ExcelWriter(EXCEL_FILE_PATH, engine='openpyxl') as writer:
            for pair_key, pair_ticker in CRYPTO_PAIRS.items():
                current_df = pd.DataFrame(list(data_history[pair_ticker]))
                current_df = current_df[current_df['price_sek'] > 0.0]
                if len(current_df) < 1: continue
                sheet_name = pair_key.split('/')[0].strip()
                current_df['time'] = current_df['time'].dt.strftime('%Y-%m-%d %H:%M:%S')
                current_df['price_sek'] = current_df['price_sek'].round(4)
                current_df.to_excel(writer, sheet_name=sheet_name, index=False)
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
            return None, f"OHLC Fel: {data['error']}"

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
            return best_match_price_eur * eur_sek_rate, None

        return None, f"Ingen tillförlitlig OHLC-data hittades."

    except Exception as e:
        return None, f"Fel vid hämtning av OHLC-data: {e}"


def get_crypto_sek_data(pair_ticker):
    """Hämtar Aktuellt pris och 24h KPI:er."""
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

            latest_price_eur = float(result['c'][0])
            open_24h_eur = float(result['o'])

            price_sek = latest_price_eur * eur_sek_rate
            high_sek = float(result['h'][1]) * eur_sek_rate
            low_sek = float(result['l'][1]) * eur_sek_rate
            open_sek = open_24h_eur * eur_sek_rate

            percent_change_24h = ((price_sek - open_sek) / open_sek) * 100 if open_sek != 0 else 0

        else: return None, f"Fick ett tomt Ticker-resultat."

    except Exception as e: return None, f"Fel vid hämtning av Ticker-data: {e}"

    return {
        'price': price_sek,
        'high_24h': high_sek,
        'low_24h': low_sek,
        'percent_change_24h': percent_change_24h,
    }, None

def calculate_30min_trend(pair_ticker):
    """Beräknar den procentuella trenden över de senaste 30 lagrade datapunkterna."""
    history = data_history.get(pair_ticker)
    filtered_history = [p for p in history if p['price_sek'] > 0.0]

    if not filtered_history or len(filtered_history) < SUMMARY_TREND_POINTS:
        return 0.0, "Väntar på data", "gray"

    df = pd.DataFrame(filtered_history[-SUMMARY_TREND_POINTS:])

    x_time_numeric = np.array([t.timestamp() for t in df['time']])
    y_price = df['price_sek']

    slope, intercept, r_value, p_value, std_err = linregress(x_time_numeric, y_price)

    start_price_trend = slope * x_time_numeric.min() + intercept
    end_price_trend = slope * x_time_numeric.max() + intercept

    if start_price_trend == 0.0 or start_price_trend is None: return 0.0, "Ingen historik", "gray"

    percent_change = ((end_price_trend - start_price_trend) / start_price_trend) * 100

    if percent_change > 0.0: return percent_change, f"Stigande ({SUMMARY_TREND_POINTS} min)", "lightgreen"
    elif percent_change < 0.0: return percent_change, f"Fallande ({SUMMARY_TREND_POINTS} min)", "red"
    else: return 0.0, f"Stabil ({SUMMARY_TREND_POINTS} min)", "lightgray"


def generate_buy_sell_signal(trend_percent_30m, percent_24h, percent_7d):
    """
    Genererar en Köp/Sälj-signal med 11 nivåer och betyg i texten.
    Returnerar: (signal_text, signal_rating, color)
    """
    
    long_term_positive = percent_7d > 0.0
    medium_term_positive = percent_24h > 0.0
    
    T_WEAK = 0.05
    T_LIGHT_BUY = 0.5
    T_BUY = 1.0
    T_STRONG_BUY = 1.5
    T_VERY_STRONG_BUY = 2.0
    
    T_LIGHT_SELL = -0.5
    T_SELL = -1.0
    T_STRONG_SELL = -1.5
    T_VERY_STRONG_SELL = -2.0

    # --- KÖPSIGNALER (+1 till +5) ---
    if trend_percent_30m >= T_VERY_STRONG_BUY:
        rating = 5
        if long_term_positive and medium_term_positive:
            return f"MYCKET STARK KÖP (+{rating})", rating, '#006400'
        else:
            rating = 4
            return f"STARK KÖP (+{rating})", rating, '#3CB371' 

    if trend_percent_30m >= T_STRONG_BUY:
        rating = 4
        if long_term_positive or medium_term_positive:
            return f"STARK KÖP (+{rating})", rating, '#3CB371' 
        else:
            rating = 3
            return f"KÖP (+{rating})", rating, '#66CDAA'

    if trend_percent_30m >= T_BUY:
        rating = 3
        return f"KÖP (+{rating})", rating, '#66CDAA'

    if trend_percent_30m >= T_LIGHT_BUY:
        rating = 2
        return f"KÖP (Svag) (+{rating})", rating, '#7FFFD4'

    if trend_percent_30m > T_WEAK:
        rating = 1
        return f"KÖP (Lätt) (+{rating})", rating, '#98FB98'


    # --- SÄLJSIGNALER (-1 till -5) ---
    if trend_percent_30m <= T_VERY_STRONG_SELL:
        rating = -5
        if not long_term_positive and not medium_term_positive:
            return f"MYCKET STARK SÄLJ ({rating})", rating, '#8B0000'
        else:
            rating = -4
            return f"STARK SÄLJ ({rating})", rating, '#FF6347'

    if trend_percent_30m <= T_STRONG_SELL:
        rating = -4
        if not long_term_positive or not medium_term_positive:
            return f"STARK SÄLJ ({rating})", rating, '#FF6347' 
        else:
            rating = -3
            return f"SÄLJ ({rating})", rating, '#FA8072'

    if trend_percent_30m <= T_SELL:
        rating = -3
        return f"SÄLJ ({rating})", rating, '#FA8072'

    if trend_percent_30m <= T_LIGHT_SELL:
        rating = -2
        return f"SÄLJ (Svag) ({rating})", rating, '#FFA07A'

    if trend_percent_30m < -T_WEAK:
        rating = -1
        return f"SÄLJ (Lätt) ({rating})", rating, '#F08080'

    # --- NEUTRAL (0) ---
    else:
        rating = 0
        return "NEUTRAL (0)", rating, '#BBBBBB'


def check_signal_arbitrage(ratings):
    """
    Jämför signalbetyg för alla kryptopar.
    Skickar TELEGRAM-notis om differensen når DIFF_THRESHOLD (5/6).
    """
    global SENT_DIFF_NOTIFICATIONS
    
    crypto_keys = list(CRYPTO_PAIRS.keys())
    
    for key1, key2 in itertools.combinations(crypto_keys, 2):
        
        ticker1 = CRYPTO_PAIRS[key1]
        ticker2 = CRYPTO_PAIRS[key2]
        
        rating1 = ratings.get(ticker1, 0)
        rating2 = ratings.get(ticker2, 0)
        
        if rating1 is None or rating2 is None:
            continue
            
        difference = abs(rating1 - rating2)
        
        sorted_tickers = sorted([ticker1, ticker2])
        pair_key_tracker = f"{sorted_tickers[0]} __{sorted_tickers[1]}"
        
        
        if difference >= DIFF_THRESHOLD:
            last_notified_diff = SENT_DIFF_NOTIFICATIONS.get(pair_key_tracker, 0)

            # Skicka notis om gapet är nytt ELLER större än det senast skickade
            if difference > last_notified_diff:
                
                success = notify_diff(key1, rating1, key2, rating2, difference)
                
                if success:
                    SENT_DIFF_NOTIFICATIONS[pair_key_tracker] = difference
                    
        else:
            # Återställ notisstatus om gapet faller under tröskeln
            if pair_key_tracker in SENT_DIFF_NOTIFICATIONS:
                 SENT_DIFF_NOTIFICATIONS[pair_key_tracker] = 0

# --- NY KÄRNFUNKTION FÖR DATAHÄMTNING ---

def process_data_and_log(n):
    """
    Kärnlogiken för datahämtning, historikuppdatering, och KPI-caching.
    Denna funktion anropas nu av bakgrundstråden.
    """
    global global_kpi_cache
    
    eur_sek_rate = get_eur_sek_rate()
    new_kpi_cache = {}
    current_time = datetime.now()
    
    log_to_excel = True # ÄNDRING: Logga varje gång (varje minut) för att persistent spara de 100 senaste punkterna.
    fetch_ohlc = n % 5 == 0
    
    print(f"[{current_time.strftime('%H:%M:%S')}] Bakgrundsjobb: Startar datahämtning. Excel-logg: ALLTID (för persistent 100-punkts historik).")

    for pair_key, pair_ticker in CRYPTO_PAIRS.items():

        price_data, error = get_crypto_sek_data(pair_ticker)

        if error or price_data is None:
            if data_history.get(pair_ticker) and data_history[pair_ticker]:
                latest_point = data_history[pair_ticker][-1]
                price_sek = latest_point['price_sek']

                data_history[pair_ticker].append({'time': current_time, 'price_sek': price_sek})

                kpi_fallback = global_kpi_cache.get(pair_ticker,
                                                     {'price': price_sek, 'high_24h': price_sek, 'low_24h': price_sek,
                                                      'percent_change_24h': 0.0, 'price_7d': price_sek, 'price_30d': price_sek})
                new_kpi_cache[pair_ticker] = kpi_fallback

            print(f"[{current_time.strftime('%H:%M:%S')}] FEL: Kunde inte hämta Ticker data för {pair_ticker}. Fortsätter med gammalt data.")
            continue


        prev_7d = global_kpi_cache.get(pair_ticker, {}).get('price_7d', price_data['price'])
        prev_30d = global_kpi_cache.get(pair_ticker, {}).get('price_30d', price_data['price'])

        price_7d_ago, price_30d_ago = prev_7d, prev_30d

        if fetch_ohlc:
              p_7d, error_7d = get_ohlc_price(pair_ticker, 7, eur_sek_rate)
              p_30d, error_30d = get_ohlc_price(pair_ticker, 30, eur_sek_rate)

              if p_7d is not None: price_7d_ago = p_7d
              if p_30d is not None: price_30d_ago = p_30d


        price_sek = price_data['price']
        data_history[pair_ticker].append({'time': current_time, 'price_sek': price_sek})


        new_kpi_cache[pair_ticker] = {
            'price': price_sek,
            'high_24h': price_data['high_24h'],
            'low_24h': price_data['low_24h'],
            'percent_change_24h': price_data['percent_change_24h'],
            'price_7d': price_7d_ago,
            'price_30d': price_30d_ago,
        }

    global_kpi_cache = new_kpi_cache

    if log_to_excel:
        log_data_to_excel()
        print(f"[{current_time.strftime('%H:%M:%S')}] Excel-logg slutförd.")
    
    return True # Indikerar att jobbet är klart

# --- HJÄLPFUNKTION: Kompakt kort för sammanfattningen (OÄNDRAD) ---
def create_summary_card(key_name, price_sek, high_sek, low_sek, percent_change_24h, trend_percent, trend_color, signal_text, signal_color):
    """Skapar ett litet, kompakt kort för den globala sammanfattningsrutan."""
    crypto_symbol = key_name.split('/')[0].strip()

    if percent_change_24h >= 0:
        color_24h = '#3CB371'
        arrow_24h = '▲'
    else:
        color_24h = '#FF6347'
        arrow_24h = '▼'

    formatted_price = format_sek(price_sek)
    formatted_high = format_sek(high_sek)
    formatted_low = format_sek(low_sek)
    formatted_24h_percent = format_percent(percent_change_24h)

    trend_display = f"{format_percent(trend_percent)}"
    if trend_percent > 0:
        arrow_30m = '▲'
        color_30m_text = 'lightgreen'
    elif trend_percent < 0:
        arrow_30m = '▼'
        color_30m_text = 'red'
    else:
        arrow_30m = '—'
        color_30m_text = 'lightgray'


    return html.Div(
        style={
            'backgroundColor': '#1E1E1E',
            'padding': '10px',
            'borderRadius': '8px',
            'width': '12%',
            'boxShadow': '0 2px 4px rgba(0, 0, 0, 0.5)',
            'margin': '5px',
            'borderLeft': f'4px solid {signal_color}'
        },
        children=[
            html.H4(crypto_symbol, style={'margin': '0 0 5px 0', 'color': '#00BFFF', 'fontSize': '16px'}),
            html.P(f"{formatted_price} SEK", style={'margin': '0 0 5px 0', 'fontWeight': 'bold', 'color': '#FFFFFF', 'fontSize': '18px'}),

            html.Div(
                style={'fontSize': '10px', 'color': color_24h, 'fontWeight': 'bold', 'marginBottom': '5px'},
                children=[
                    html.Span(f"{arrow_24h} 24h Utv: {formatted_24h_percent}"),
                ]
            ),

            html.Div(
                style={'fontSize': '10px', 'color': '#BBBBBB', 'marginBottom': '5px'},
                children=[
                    html.Span(f"H: {formatted_high}", style={'color': '#3CB371', 'marginRight': '10px'}),
                    html.Span(f"L: {formatted_low}", style={'color': '#FF6347'}),
                ]
            ),
            
            html.P(signal_text,
                   style={'margin': '5px 0 0 0', 'fontSize': '12px', 'fontWeight': 'bold', 'color': signal_color}),

            html.P(f"Trend ({SUMMARY_TREND_POINTS} min): {arrow_30m} {trend_display}",
                   style={'margin': '0', 'fontSize': '10px', 'fontWeight': 'bold', 'color': color_30m_text, 'marginTop': '2px'}),
        ]
    )


# --- Dash Applikation och Callbacks ---

def create_kpi_card(title, value, unit, is_percent=False):
    """Skapar en stiliserad KPI-kortkomponent för detaljvyn."""
    if is_percent:
        color = '#3CB371' if value >= 0 else '#FF6347'
        arrow = '▲' if value >= 0 else '▼'
        display_value = f"{arrow} {value:+.2f}{unit}"
        value_style = {'fontSize': '24px', 'fontWeight': 'bold', 'color': color, 'margin': '5px 0'}
    else:
        display_value = f"{format_sek(value)} {unit}"
        value_style = {'fontSize': '24px', 'fontWeight': 'bold', 'color': '#FFFFFF', 'margin': '5px 0'}

    return html.Div(
        style={
            'backgroundColor': '#1E1E1E',
            'padding': '15px',
            'borderRadius': '8px',
            'textAlign': 'center',
            'width': '20%',
            'boxShadow': '0 4px 8px rgba(0, 0, 0, 0.2)'
        },
        children=[
            html.P(title, style={'fontSize': '14px', 'color': '#BBBBBB', 'margin': '0 0 5px 0'}),
            html.P(display_value, style=value_style)
        ]
    )

app = Dash(__name__)

app.layout = html.Div(
    style={'backgroundColor': '#111111', 'color': '#FFFFFF', 'padding': '20px', 'fontFamily': 'Arial, sans-serif'},
    children=[
        html.H1(children='Kryptovaluta Realtidsspårare i SEK',
                style={'textAlign': 'center', 'color': '#00BFFF', 'marginBottom': '30px'}),

        html.H2(f"Global Överblick (Köp/Sälj-signal & 24h Utv.)",
                style={'textAlign': 'center', 'color': '#BBBBBB', 'marginTop': '20px'}),
        html.Div(id='global-summary-display', style={
            'display': 'flex',
            'justifyContent': 'center',
            'flexWrap': 'wrap',
            'marginBottom': '40px',
            'padding': '10px',
            'backgroundColor': '#1C1C1C',
            'borderRadius': '12px',
        }),

        html.H2("Detaljerad Spårning",
                style={'textAlign': 'center', 'color': '#00BFFF', 'marginBottom': '15px'}),

        dcc.Dropdown(
            id='crypto-selector',
            options=[{'label': key, 'value': key} for key in CRYPTO_PAIRS.keys()],
            value=DEFAULT_PAIR_KEY,
            clearable=False,
            style={
                'backgroundColor': '#FFFFFF',
                'color': '#000000',
                'width': '50%',
                'margin': '0px auto 20px auto',
                'padding': '5px',
                'border': 'none'
            },
            optionHeight=35,
        ),

        html.Div(id='current-price-display', style={'textAlign': 'center', 'fontSize': '40px', 'marginBottom': '10px', 'fontWeight': 'bold', 'color': '#FFFFFF'}),

        html.Div(id='kpi-display', style={
            'display': 'flex',
            'justifyContent': 'space-around',
            'marginBottom': '30px',
            'padding': '10px',
        }),

        dcc.Graph(id='live-update-graph', config={'displayModeBar': False}),

        dcc.Interval(
            id='interval-component',
            interval=UPDATE_INTERVAL_MS,
            n_intervals=0
        )
    ]
)

# CALLBACK: Funktion som körs varje gång dcc.Interval tickar. 
# DENNA FUNGERAR NU BARA SOM EN TRIGGER FÖR DASH! Den tunga logiken körs i bakgrunden.
@app.callback(
    Output('interval-component', 'interval'),
    [Input('interval-component', 'n_intervals')]
)
def data_fetch_trigger(n):
    """Dash-callback för att hålla timern aktiv och trigga andra callbacks."""
    # Den tunga logiken (fetch_and_log) körs i bakgrundstråden. 
    # Vi returnerar bara intervallet (UPDATE_INTERVAL_MS)
    return UPDATE_INTERVAL_MS


# --- GLOBAL SUMMARY CALLBACK (med All Notislogik) ---
@app.callback(
    Output('global-summary-display', 'children'),
    [Input('interval-component', 'n_intervals')] # Triggas av dcc.Interval för uppdatering
)
def update_global_summary(n_intervals):
    """
    Skapar alla kompakta summary-kort, hanterar enskilda Köp/Sälj-notiser,
    hanterar 24h-uppgångsnotiser OCH anropar funktionen för signal-differensnotiser.
    
    Denna callback använder den data som BAKGRUNDSTRÅDEN har sparat i global_kpi_cache och data_history.
    """
    global SENT_NOTIFICATIONS
    global current_signal_ratings 
    global SENT_24H_SPIKE_NOTIFICATIONS
    
    summary_cards = []
    NOTIFICATION_THRESHOLD = 5
    
    ratings_to_check = {}

    for pair_key, pair_ticker in CRYPTO_PAIRS.items():

        kpi_data = global_kpi_cache.get(pair_ticker)
        trend_percent, trend_text, trend_color = calculate_30min_trend(pair_ticker)
        
        # Säkerställer att vi har ett pris även om kpi_data är None (fallback till senaste historik)
        price_sek = data_history.get(pair_ticker, [{'price_sek': 0.0}])[-1]['price_sek']

        percent_24h = 0.0
        percent_7d = 0.0
        signal_rating = 0

        if kpi_data and kpi_data['price'] != 0.0:
            
            percent_24h = kpi_data.get('percent_change_24h', 0.0)

            if kpi_data.get('price_7d', 0.0) != 0.0:
                price_7d_ago = kpi_data['price_7d']
                percent_7d = ((kpi_data['price'] - price_7d_ago) / price_7d_ago) * 100
            
            signal_text, signal_rating, signal_color = generate_buy_sell_signal(trend_percent, percent_24h, percent_7d)

            
            # --- Enskild Köp/Sälj Notislogik ---
            current_notification_level = SENT_NOTIFICATIONS.get(pair_ticker, 0)
            
            if abs(signal_rating) >= NOTIFICATION_THRESHOLD and signal_rating != current_notification_level:
                success = notify_single(signal_text, pair_key, kpi_data['price']) 
                if success:
                    SENT_NOTIFICATIONS[pair_ticker] = signal_rating
                
            elif abs(signal_rating) < NOTIFICATION_THRESHOLD and current_notification_level != 0:
                SENT_NOTIFICATIONS[pair_ticker] = 0
            # --- Enskild Köp/Sälj Notislogik Slut ---

            # --- 24h SPIKE NOTISLOGIK ---
            if percent_24h >= SPIKE_24H_THRESHOLD and not SENT_24H_SPIKE_NOTIFICATIONS.get(pair_ticker, False):
                success = notify_24h_spike(pair_key, percent_24h, kpi_data['price'])
                if success:
                    SENT_24H_SPIKE_NOTIFICATIONS[pair_ticker] = True
            elif percent_24h < SPIKE_24H_THRESHOLD and SENT_24H_SPIKE_NOTIFICATIONS.get(pair_ticker, False):
                # Återställ flaggan om priset faller under tröskeln
                SENT_24H_SPIKE_NOTIFICATIONS[pair_ticker] = False
            # --- 24h SPIKE NOTISLOGIK SLUT ---
            
        else:
            signal_text, signal_rating, signal_color = "Väntar på data", 0, "gray"

        # SPARA SIGNALBETYGET för DIFF-jämförelse
        ratings_to_check[pair_ticker] = signal_rating


        # Skapa Summary Card
        if kpi_data is None or kpi_data['price'] == 0.0:
            high_sek = low_sek = price_sek 
            summary_cards.append(create_summary_card(
                pair_key, price_sek, high_sek, low_sek, percent_24h, trend_percent, trend_color, signal_text, signal_color
            ))
            continue
            
        summary_cards.append(
            create_summary_card(
                key_name=pair_key,
                price_sek=kpi_data['price'],
                high_sek=kpi_data['high_24h'],
                low_sek=kpi_data['low_24h'],
                percent_change_24h=kpi_data['percent_change_24h'],
                trend_percent=trend_percent,
                trend_color=trend_color,
                signal_text=signal_text,
                signal_color=signal_color 
            )
        )

    # --- KÖR DIFF-ANALYSEN HÄR EFTER ATT ALLA BETYG ÄR KLARA ---
    current_signal_ratings = ratings_to_check
    check_signal_arbitrage(current_signal_ratings)

    return summary_cards


# CALLBACK: Detaljvy för valt krypto (OÄNDRAD)
@app.callback(
    [Output('live-update-graph', 'figure'),
     Output('current-price-display', 'children'),
     Output('kpi-display', 'children')],
    [Input('interval-component', 'n_intervals'),
     Input('crypto-selector', 'value')],
    [State('crypto-selector', 'value')]
)
def update_graph_live(n_intervals, selected_pair_key, current_pair_key):

    pair_ticker = CRYPTO_PAIRS.get(current_pair_key)
    current_history = data_history.get(pair_ticker, collections.deque(maxlen=MAX_DASH_POINTS))

    filtered_history = [p for p in current_history if p['price_sek'] > 0.0]

    if not filtered_history or len(filtered_history) <= 1:
          return (
              go.Figure(layout=go.Layout(plot_bgcolor='#111111', paper_bgcolor='#111111')),
              f"Väntar på tillräckligt med data för {current_pair_key}...",
              html.Div("Grafdata ej tillgänglig ännu. Väntar på första loggade punkterna.", style={'color': '#888888', 'textAlign': 'center'})
             )

    kpi_data = global_kpi_cache.get(pair_ticker)

    price_sek = filtered_history[-1]['price_sek']

    if kpi_data is None:
        high_sek, low_sek, percent_24h = price_sek, price_sek, 0.0
        price_7d_ago, price_30d_ago = price_sek, price_sek
    else:
        high_sek = kpi_data['high_24h']
        low_sek = kpi_data['low_24h']
        percent_24h = kpi_data['percent_change_24h']
        price_7d_ago = kpi_data['price_7d']
        price_30d_ago = kpi_data['price_30d']


    percent_7d = 0.0
    if price_7d_ago is not None and price_7d_ago != 0:
        percent_7d = ((price_sek - price_7d_ago) / price_7d_ago) * 100

    percent_30d = 0.0
    if price_30d_ago is not None and price_30d_ago != 0:
        percent_30d = ((price_sek - price_30d_ago) / price_30d_ago) * 100

    # --- 2. Skapa DataFrame och Figur (Graf) ---
    df = pd.DataFrame(filtered_history)

    trend_trace = None
    if len(df) >= 2:
        x_time_numeric = np.array([t.timestamp() for t in df['time']])
        y_price = df['price_sek']

        slope, intercept, r_value, p_value, std_err = linregress(x_time_numeric, y_price)
        trend_line = slope * x_time_numeric + intercept

        start_price_trend = slope * x_time_numeric.min() + intercept
        end_price_trend = slope * x_time_numeric.max() + intercept

        if start_price_trend != 0:
            trend_percent_change = ((end_price_trend - start_price_trend) / start_price_trend) * 100
        else:
            trend_percent_change = 0.0

        if slope >= 0:
            trend_color = '#3CB371'
            trend_name = f'POSITIV TREND ({format_percent(trend_percent_change)} / {MAX_DASH_POINTS} min)'
        else:
            trend_color = '#FF6347'
            trend_name = f'NEGATIV TREND ({format_percent(trend_percent_change)} / {MAX_DASH_POINTS} min)'

        trend_trace = go.Scatter(
            x=df['time'], y=trend_line, mode='lines', name=trend_name, line=dict(color=trend_color, dash='dash', width=4), hoverinfo='name'
        )


    data_traces = [
        go.Scatter(x=df['time'], y=df['price_sek'], mode='lines+markers', name=f'Aktuellt Pris ({current_pair_key})', line=dict(color='#00BFFF', width=2), marker=dict(size=8)),
        go.Scatter(x=df['time'], y=[high_sek] * len(df), mode='lines', name='24h Högsta', line=dict(color='#3CB371', dash='dot', width=1.5), hoverinfo='name+y'),
        go.Scatter(x=df['time'], y=[low_sek] * len(df), mode='lines', name='24h Lägsta', line=dict(color='#FF6347', dash='dot', width=1.5), hoverinfo='name+y')
    ]

    if trend_trace:
        data_traces.append(trend_trace)

    fig = go.Figure(
        data=data_traces,
        layout=go.Layout(
            xaxis_title="Tid", yaxis_title="Pris i SEK", title=f"{current_pair_key} Prisutveckling de senaste {MAX_DASH_POINTS} minuterna",
            plot_bgcolor='#111111', paper_bgcolor='#111111', font=dict(color='#FFFFFF', size=14),
            legend=dict(x=0, y=1.0, orientation='h'),
            yaxis=dict(tickformat=',.2f', separatethousands=True),
            margin=dict(l=40, r=40, t=40, b=40)
        )
    )

    # 3. KPI LOGIK: Skapa de visuella KPI-korten
    kpi_cards = [
        create_kpi_card(
            title='Aktuellt Pris',
            value=price_sek,
            unit='SEK'
        ),
        create_kpi_card(
            title='24h Utveckling',
            value=percent_24h,
            unit='%',
            is_percent=True
        ),
        create_kpi_card(
            title='24h Högsta',
            value=high_sek,
            unit='SEK'
        ),
        create_kpi_card(
            title='24h Lägsta',
            value=low_sek,
            unit='SEK'
        ),
        create_kpi_card(
            title='7d Utveckling',
            value=percent_7d,
            unit='%',
            is_percent=True
        ),
        create_kpi_card(
            title='30d Utveckling',
            value=percent_30d,
            unit='%',
            is_percent=True
        )
    ]
    
    # 4. Uppdatera det aktuella priset OCH VYN
    display_text = f"Aktuell kurs ({current_pair_key}): {format_sek(price_sek)} SEK"
    
    return fig, display_text, html.Div(kpi_cards, style={'display': 'flex', 'justifyContent': 'space-around', 'width': '95%', 'margin': '0 auto'})

# --- NY FUNKTION FÖR BAKGRUNDSTRÅDEN ---

def run_background_data_fetch():
    """
    Hanterar den kontinuerliga datainsamlingsloopen.
    Denna funktion körs i en separat tråd och är oberoende av webbläsarens anslutning.
    """
    global background_interval_counter
    
    # Kör en första hämtning direkt för att fylla cachen innan Dash startar
    process_data_and_log(background_interval_counter)
    background_interval_counter += 1
    
    while True:
        try:
            # Vänta 60 sekunder
            time.sleep(UPDATE_INTERVAL_MS / 1000) 
            
            # Kör databearbetningen
            process_data_and_log(background_interval_counter)
            
            # Räknaren för 5-minuters intervall uppdateras
            background_interval_counter += 1
            if background_interval_counter >= 5:
                background_interval_counter = 0

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] KRITISKT FEL i bakgrundstråd: {e}")
            time.sleep(10) # Vänta 10 sekunder och försök igen vid fel


# Starta servern
if __name__ == '__main__':
    load_historical_data()

    print(f"Kryptovaluta Realtidsspårare startar...")
    print(f"Notiser skickas via Telegram.")
    print(f"Telegram Bot Token: {TELEGRAM_BOT_TOKEN}")
    print(f"Telegram Chat ID: {TELEGRAM_CHAT_ID}")
    print(f"Differens tröskel (Signaler): {DIFF_THRESHOLD}")
    print(f"24h Uppgångs tröskel (Säljnotis): {SPIKE_24H_THRESHOLD}%")
    
    # KÖR TESTSKICKNING AV TELEGRAM HÄR
    print("\n--- KÖR TESTSKICKNING ---")
    send_test_notification()
    print("-------------------------\n")
    
    # STARTAR NU DATAHÄMTNINGEN I EN SEPARAT TRÅD
    print(f"[{datetime.now().strftime('%H:%M:%S')}] STARTAR BAKGRUNDSJOBB...")
    data_thread = threading.Thread(target=run_background_data_fetch, daemon=True)
    data_thread.start()
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Bakgrundstråd startad. Startar Dash server på http://0.0.0.0:8050")
    print(f"Vänta 1-2 minuter på första datainsamlingen för alla par...")

    # KORRIGERAT: Ändrad till debug=False för maximal stabilitet och databehållning
    # Host='0.0.0.0' tillåter anslutning från andra enheter i nätverket.
    app.run(debug=False, host='0.0.0.0', port=8050)
