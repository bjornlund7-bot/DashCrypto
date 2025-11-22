import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import time
import threading
import os
import requests
import json
import logging
from redis import from_url, exceptions
from scipy.stats import linregress 
import numpy as np 

# --- Konstanter, Logging och API Konfiguration ---

# Konfigurera logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

# [KONSTANTER]
# OBS: Dessa måste sättas som miljövariabler i din Render/deployment-miljö
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
KRAKEN_TICKER_API_URL = "https://api.kraken.com/0/public/Ticker"
KRAKEN_OHLC_API_URL = "https://api.kraken.com/0/public/OHLC"
EXCHANGE_RATE_URL = "https://api.exchangerate-api.com/v4/latest/EUR"

CRYPTO_PAIRS = {
    'XRP (Ripple)': 'XRP/EUR', 'BTC (Bitcoin)': 'BTC/EUR', 'ETH (Ethereum)': 'ETH/EUR', 
    'SOL (Solana)': 'SOL/EUR', 'GRASS (Grass)': 'GRASS/EUR', 'ADA (Cardano)': 'ADA/EUR', 
    'DOT (Polkadot)': 'DOT/EUR', 'DOGE (Dogecoin)': 'DOGE/EUR', 'PUMP (PUMP)': 'PUMP/EUR', 
    'Cookie DAO': 'COOKIE/EUR', 'Moonwalk (MF)': 'MF/EUR', 'YALA': 'YALA/EUR', 
    'WIF (dogwifhat)': 'WIF/EUR', 'YFI (Yearn Finance)': 'YFI/EUR', 'BNB (BNB Chain)': 'BNB/EUR', 
    'TRX (Tron)': 'TRX/EUR', 'PEPE (Pepe)': 'PEPE/EUR', 'LTC (Litecoin)': 'LTC/EUR', 
    'TRUMP (Official Trump)': 'TRUMP/EUR', 'XTZ (Tezos)': 'XTZ/EUR', 'DASH (Dash)': 'DASH/EUR', 
    'ZRO (LayerZero)': 'ZRO/EUR', 'WOO (Woo Network)': 'WOO/EUR', 'GALA (Gala Games)': 'GALA/EUR', 
    'SUI (SUI)': 'SUI/EUR', 'BCH (Bitcoin Cash)': 'BCH/EUR', 'ATOM (Cosmos)': 'ATOM/EUR', 
    'AVAX (Avalanche)': 'AVAX/EUR', 'ICP (Internet Computer Protocol)': 'ICP/EUR', 
    'ZEC (Zcash)': 'ZEC/EUR', '0G (ZeroGravity)': '0G/EUR', 'XDC (XDC Network)': 'XDC/EUR', 
    'UNI (Uniswap)': 'UNI/EUR', 'IP (Story)': 'IP/EUR', 'INJ (Injective)': 'INJ/EUR', 
    'AR (Arweave)': 'AR/EUR', 'EGLD (MultiversX)': 'EGLD/EUR', 'LPT (LivePeer)': 'LPT/EUR', 
    'KSM (Kusama)': 'KSM/EUR', 'EUL (Euler)': 'EUL/EUR', 'GMX (GMX)': 'GMX/EUR', 
    'AUCTION (Bounce)': 'AUCTION/EUR', 'MOVR (Moonriver)': 'MOVR/EUR', 'SSV (SSV Network)': 'SSV/EUR', 
    'MLN (Enzyme Finance)': 'MLN/EUR', 'ALCX (Alchemix)': 'ALCX/EUR', 'AERO (Aerodrome Finance)': 'AERO/EUR', 
    'MYX (MYX Finance)': 'MYX/EUR', 'GNO (Gnosis)': 'GNO/EUR',
}

CRYPTO_EMOJIS = {
    'XRP': '🌊', 'BTC': '💰', 'ETH': '💎', 'SOL': '☀️', 'GRASS': '🌱', 'ADA': '₳', 
    'DOT': '🟣', 'DOGE': '🐕', 'PUMP': '🚀', 'COOKIE': '🍪', 'MF': '🚶', 'YALA': '🦁', 
    'WIF': '🐶', 'YFI': '🚜', 'BNB': '🟡', 'TRX': '🌐', 'PEPE': '🐸', 'LTC': '🥈', 
    'TRUMP': '🦅', 'XTZ': '⚙️', 'DASH': '🪙', 'ZRO': '🔗', 'WOO': '🐻', 'GALA': '🎮', 
    'SUI': '💧', 'BCH': '🌱', 'ATOM': '⚛️', 'AVAX': '🔺', 'ICP': '💻', 'ZEC': '🦓', 
    '0G': '🌌', 'XDC': '🤝', 'UNI': '🦄', 'IP': '📖', 'INJ': '💉', 'AR': '📦', 
    'EGLD': '⚡', 'LPT': '🎥', 'KSM': '🐥', 'EUL': '🏛️', 'GMX': '🐻', 'AUCTION': '🔨', 
    'MOVR': '🌕', 'SSV': '🔐', 'MLN': '🧪', 'ALCX': '⚗️', 'AERO': '✈️', 'MYX': '🔄', 
    'GNO': '🦉',
}

DEFAULT_PAIR_KEY = 'XRP (Ripple)' 
COINS_LABELS = list(CRYPTO_PAIRS.keys())
COINS_SYMBOLS = [label.split(' ')[0] for label in COINS_LABELS]
SYMBOL_TO_LABEL = {label.split(' ')[0]: label for label in COINS_LABELS}
CURRENCIES = ['EUR', 'SEK']
UPDATE_INTERVAL_SECONDS_DATA = 120 
OHLC_CACHE_INTERVAL_MIN = 5 

TIME_WINDOWS = {
    '30m': {'blocks': 6, 'interval': OHLC_CACHE_INTERVAL_MIN},  
    '1h': {'blocks': 12, 'interval': OHLC_CACHE_INTERVAL_MIN},  
    '3h': {'blocks': 36, 'interval': OHLC_CACHE_INTERVAL_MIN},  
    '6h': {'blocks': 72, 'interval': OHLC_CACHE_INTERVAL_MIN}, 
    '12h': {'blocks': 144, 'interval': OHLC_CACHE_INTERVAL_MIN}, 
    '24h': {'blocks': 288, 'interval': OHLC_CACHE_INTERVAL_MIN},
    '7d': {'blocks': 7, 'interval': 1440},  
    '30d': {'blocks': 30, 'interval': 1440}, 
}
PRICE_CHANGE_PERIODS = [p for p in TIME_WINDOWS.keys() if p != '12h']

TREND_WINDOWS = {
    '1h': {'blocks': 12, 'color': '#ff7f0e', 'name': 'Trend (1h)'}, 
    '3h': {'blocks': 36, 'color': '#2ca02c', 'name': 'Trend (3h)'}, 
    '6h': {'blocks': 72, 'color': '#d62728', 'name': 'Trend (6h)'}, 
    '12h': {'blocks': 144, 'color': '#9467bd', 'name': 'Trend (12h)'}, 
}
DEFAULT_TRENDS = list(TREND_WINDOWS.keys()) 

# [REDIS KONFIGURATION]
REDIS_URL = os.environ.get('REDIS_URL')
r = None
if REDIS_URL:
    try:
        r = from_url(REDIS_URL)
        r.ping()
        logger.debug("✅ Ansluten till Redis!")
    except exceptions.ConnectionError as e:
        logger.error(f"❌ Kunde inte ansluta till Redis: {e}")
        r = None
        
DEFAULT_DATA = {
    'XRP/EUR': 0.50, 'XRP/SEK': 5.50,
    'timestamp': time.time(),
    'EUR_SEK_RATE': 11.0, 
    'ALL_24H_RANGE_OHLC': {'XRP': {'high_eur': 0.52, 'low_eur': 0.48}}, 
    'ALL_OHLC_CACHED': {}, 
    'ALL_PERCENT_CHANGE': {},
}

# --- Hjälpfunktioner ---

def format_price_display(p):
    """
    Formaterar priset med rätt decimaler.
    """
    if p is None: return "N/A"
    price_format = f"{p:,.4f}" if p < 10 else f"{p:,.2f}"
    return price_format.replace(",", "TEMP").replace(".", ",").replace("TEMP", " ")

def get_data_from_redis():
    """Hämtar data från Redis cache."""
    if r:
        try:
            cached_data = r.get('crypto_data')
            if cached_data:
                return json.loads(cached_data)
        except exceptions.ConnectionError as e:
            logger.error(f"Redis-anslutningsfel i callback: {e}")
    return None

def fetch_exchange_rate():
    """Hämtar EUR/SEK växelkurs."""
    try:
        response = requests.get(EXCHANGE_RATE_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        sek_rate = data['rates'].get('SEK')
        return sek_rate if sek_rate else 11.0
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching exchange rate: {e}. Using fallback 11.0.")
        return 11.0

def fetch_crypto_data():
    """Hämtar realtids Ticker data från Kraken."""
    try:
        t = time.time()
        sek_rate = fetch_exchange_rate()
        kraken_tickers = ','.join(CRYPTO_PAIRS.values())
        response = requests.get(KRAKEN_TICKER_API_URL, params={'pair': kraken_tickers}, timeout=15)
        response.raise_for_status()
        kraken_data = response.json()

        if kraken_data.get('error'):
            logger.error(f"Kraken API error: {kraken_data['error']}")
            return DEFAULT_DATA

        result_key = kraken_data.get('result', {})
        current_data = {'timestamp': t, 'EUR_SEK_RATE': sek_rate, 'ALL_PERCENT_CHANGE': {}, 'ALL_OHLC_CACHED': {}, 'ALL_24H_RANGE_OHLC': {}}
        
        for label, ticker in CRYPTO_PAIRS.items():
            coin_symbol = label.split(' ')[0]
            coin_info = result_key.get(ticker)
            
            if coin_info is None: continue

            try:
                price_eur = float(coin_info['c'][0])
                current_data[f'{coin_symbol}/EUR'] = price_eur
                current_data[f'{coin_symbol}/SEK'] = price_eur * sek_rate
            except (ValueError, IndexError, TypeError) as e:
                logger.warning(f"Failed to parse Ticker data (price) for {ticker}: {e}")
            
        if len(current_data) > 4: 
            return current_data
        else:
            return DEFAULT_DATA

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ API-fel vid hämtning av Ticker: {e}. Använder standardvärden.")
        return DEFAULT_DATA
    except Exception as e:
        logger.error(f"❌ Oväntat fel i Ticker-hantering: {e}")
        return DEFAULT_DATA 

def fetch_ohlc_data_from_kraken(kraken_ticker, interval, periods_ago_seconds):
    """Hämtar historisk OHLC (Open, High, Low, Close) data från Kraken."""
    time_ago = int(time.time()) - periods_ago_seconds 
    params = { 'pair': kraken_ticker, 'interval': interval, 'since': time_ago }
    try:
        response = requests.get(KRAKEN_OHLC_API_URL, params=params, timeout=15)
        response.raise_for_status()
        ohlc_data = response.json()
        if ohlc_data.get('error'):
            logger.error(f"Kraken OHLC API error for {kraken_ticker}, interval {interval}: {ohlc_data['error']}")
            return []
        
        result_key = next(iter(ohlc_data['result'])) 
        data_list = ohlc_data['result'][result_key]
        
        # Kolumnindex: 0=time, 4=close
        return [{'time': int(row[0]), 'price': float(row[4])} for row in data_list]
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching OHLC data (Interval {interval}) for {kraken_ticker}: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error processing OHLC data: {e}")
        return []

def calculate_percentage_changes(ohlc_data, current_price, periods):
    """Beräknar procentuell förändring baserat på OHLC data."""
    changes = {}
    if not ohlc_data or current_price is None or current_price == 0:
        return {key: None for key in periods}

    for period, config in periods.items():
        if period == '12h': continue
        
        blocks = config['blocks']
        interval = config['interval']
        
        # Kontrollerar om vi har tillräckligt med data för perioden
        if (interval == OHLC_CACHE_INTERVAL_MIN and period in ['30m', '1h', '3h', '6h', '24h']) or \
           (interval == 1440 and period in ['7d', '30d']):
            
            blocks_needed = blocks
            
            if len(ohlc_data) >= blocks_needed:
                reference_price = ohlc_data[-blocks_needed]['price']
                
                if reference_price is not None and reference_price > 0:
                    change = ((current_price - reference_price) / reference_price) * 100
                    changes[period] = change
                else:
                    changes[period] = None 
            else:
                changes[period] = None 
        else:
            changes[period] = None
            
    return changes


def calculate_trendline(historical_data, blocks):
    """Beräknar linjär trendlinje för en given datasegment."""
    if len(historical_data) < blocks:
        return None, None, None
    data_segment = historical_data[-blocks:]
    x_values = np.arange(blocks) 
    y_values = np.array([item['price'] for item in data_segment])
    
    slope, intercept, r_value, p_value, std_err = linregress(x_values, y_values)
    
    start_index_global = len(historical_data) - blocks 
    
    return slope, intercept, start_index_global

def format_change(c):
    """Formaterar procentuell förändring med färg och symbol."""
    if c is None: 
        return html.Span("N/A", style={'color': '#6c757d', 'fontWeight': 'normal'})
    
    if c == 0.0:
        return html.Span("0.00%", style={'color': '#6c757d', 'fontWeight': 'bold'})
        
    color = '#28a745' if c > 0 else '#dc3545' 
    symbol = '▲' if c > 0 else '▼'
    return html.Span(f"{symbol} {abs(c):.2f}%", style={'color': color, 'fontWeight': 'bold'})

# Hjälpfunktion för Telegram Alert
def send_telegram_alert(coin_label, price, currency, threshold):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram-tokens är inte konfigurerade. Alert skickas ej.")
        return False
        
    message = (
        f"🚨 KRYPTO ALERT 🚨\n"
        f"Valuta: {coin_label}\n"
        f"Pris: {format_price_display(price)} {currency}\n"
        f"Gränsvärde uppnått: {format_price_display(threshold)} {currency}"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message
    }
    
    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        return response.json().get('ok', False)
    except requests.exceptions.RequestException as e:
        logger.error(f"Kunde inte skicka Telegram-meddelande: {e}")
        return False


# --- Bakgrundsjobb ---

def background_data_fetch(redis_instance):
    """Hämtar Ticker och OHLC data och cachar till Redis."""
    UPDATE_CYCLE_SECONDS = UPDATE_INTERVAL_SECONDS_DATA
    
    while True:
        cycle_start_time = time.time()
        
        try:
            logger.debug("--- Bakgrundstråd: Startar uppdateringscykel ---")
            
            new_data = fetch_crypto_data()
            if not new_data or new_data == DEFAULT_DATA:
                logger.warning("Misslyckades med att hämta aktuell tickerdata. Försöker igen senare.")
                time.sleep(UPDATE_CYCLE_SECONDS)
                continue
                
            all_percent_changes = {}
            all_ohlc_cached = {}
            all_24h_range_ohlc = {} 
            
            # 2. Hämta OHLC-data, beräkna %-förändring OCH 24h Hög/Låg för ALLA VALUTOR
            for label, ticker in CRYPTO_PAIRS.items():
                coin_symbol = label.split(' ')[0]
                current_price_eur = new_data.get(f'{coin_symbol}/EUR')
                
                if current_price_eur is None:
                    continue
                    
                # a. Hämta 5-min OHLC (24h historik)
                periods_ago_24h = 86400 
                ohlc_5min_data = fetch_ohlc_data_from_kraken(ticker, OHLC_CACHE_INTERVAL_MIN, periods_ago_24h) 
                
                if ohlc_5min_data:
                    
                    prices_eur = [item['price'] for item in ohlc_5min_data]
                    if prices_eur:
                        max_ohlc = max(prices_eur) 
                        min_ohlc = min(prices_eur)
                        all_24h_range_ohlc[coin_symbol] = {'high_eur': max_ohlc, 'low_eur': min_ohlc}
                    
                    if coin_symbol == DEFAULT_PAIR_KEY.split(' ')[0]:
                         ohlc_cache_key = f'OHLC_CACHED_{OHLC_CACHE_INTERVAL_MIN}MIN_{ticker}'
                         redis_instance.set(ohlc_cache_key, json.dumps(ohlc_5min_data), ex=7200) 
                         
                    short_term_periods = {k: v for k, v in TIME_WINDOWS.items() if v['interval'] == OHLC_CACHE_INTERVAL_MIN}
                    percent_changes = calculate_percentage_changes(ohlc_5min_data, current_price_eur, short_term_periods)
                else:
                    percent_changes = {k: None for k in PRICE_CHANGE_PERIODS if k in short_term_periods}

                # b. Hämta 1-dag OHLC (för längre tidsramar 7d, 30d)
                periods_ago_30d = 2592000 
                ohlc_1day_data = fetch_ohlc_data_from_kraken(ticker, 1440, periods_ago_30d) 
                long_term_periods = {k: v for k, v in TIME_WINDOWS.items() if v['interval'] == 1440}
                long_term_changes = calculate_percentage_changes(ohlc_1day_data, current_price_eur, long_term_periods)
                
                percent_changes.update(long_term_changes) 
                all_percent_changes[coin_symbol] = percent_changes
                
                time.sleep(0.1) 
            
            new_data['ALL_PERCENT_CHANGE'] = all_percent_changes
            new_data['ALL_24H_RANGE_OHLC'] = all_24h_range_ohlc 
            
            if redis_instance:
                redis_instance.set('crypto_data', json.dumps(new_data), ex=UPDATE_CYCLE_SECONDS + 60)
                logger.debug("✅ Hela 'crypto_data' inkl procentrörelser och 24h OHLC-intervall sparad.")
            
            cycle_duration = time.time() - cycle_start_time
            time_to_sleep = UPDATE_CYCLE_SECONDS - cycle_duration
            if time_to_sleep > 0:
                time.sleep(time_to_sleep)
            else:
                logger.warning(f"Cykeln tog lång tid: {cycle_duration:.2f}s")
                
        except Exception as e:
            logger.error(f"❌ Fel i bakgrundstråd: {e}")
            time.sleep(60)

if r:
    worker_thread = threading.Thread(target=background_data_fetch, args=(r,), daemon=True)
    worker_thread.start()
    logger.debug(">>> Bakgrundstråd startad!")

# --- Dash App Initiering och Layout ---

app = dash.Dash(__name__, external_stylesheets=['https://codepen.io/chriddyp/cnWqWbL.css'])
server = app.server 

def create_selected_coin_box(label, symbol, price, currency, eur_rate, high_eur, low_eur, percent_data):
    """
    Genererar den större sammanställningsboxen för den valda valutan, 
    strukturerad i tre kompakta kolumner.
    """
    
    price_text = f"{format_price_display(price)} {currency}"
    coin_emoji = CRYPTO_EMOJIS.get(symbol, '')
    
    change_24h = percent_data.get('24h')
    price_color = '#28a745' if change_24h is not None and change_24h > 0 else '#dc3545' if change_24h is not None and change_24h < 0 else '#495057'
    
    high_display = high_eur * eur_rate if currency == 'SEK' and high_eur is not None else high_eur
    low_display = low_eur * eur_rate if currency == 'SEK' and low_eur is not None else low_eur

    periods_col1 = PRICE_CHANGE_PERIODS[0:4] # 30m, 1h, 3h, 6h
    periods_col2 = PRICE_CHANGE_PERIODS[4:]  # 24h, 7d, 30d

    def create_change_display(period):
        return html.Div(
            style={'display': 'flex', 'justifyContent': 'space-between', 'margin': '3px 0', 'padding': '0 5px'},
            children=[
                html.Span(f"{period}:", style={'color': '#6c757d', 'fontWeight': 'normal', 'fontSize': '0.9em'}),
                format_change(percent_data.get(period))
            ]
        )
    
    # --- KOLUMN 1: Namn & Pris ---
    col1 = html.Div(
        style={'flex': '1 1 30%', 'minWidth': '220px', 'paddingRight': '15px', 'borderRight': '1px solid #dee2e6'},
        children=[
            # Valutanamn
            html.H2(
                html.Span([html.Span(f"{coin_emoji} ", style={'marginRight': '5px'}), f"{label} ({symbol})"]), 
                style={'fontSize': '1.5em', 'color': '#0056b3', 'marginBottom': '5px', 'textAlign': 'center'}
            ),
            # Pris
            html.Div(style={'textAlign': 'center', 'marginTop': '10px'}, children=[
                html.P("Nuvarande Pris", style={'margin': '0', 'color': '#6c757d', 'fontWeight': 'bold', 'fontSize': '0.9em'}),
                html.P(price_text, id='current-price-display', style={'fontSize': '2.5em', 'fontWeight': '800', 'color': price_color, 'margin': '0'})
            ]),
        ]
    )

    # --- KOLUMN 2: 24h Intervall ---
    col2 = html.Div(
        style={'flex': '1 1 20%', 'minWidth': '150px', 'padding': '0 15px', 'borderRight': '1px solid #dee2e6'},
        children=[
            html.P("24h Intervall (OHLC)", style={'margin': '0 0 10px 0', 'color': '#495057', 'fontWeight': 'bold', 'textAlign': 'center', 'fontSize': '0.9em'}),
            html.Div(style={'padding': '5px 0'}, children=[
                html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center', 'marginBottom': '5px'}, children=[
                    html.Span("Hög:", style={'fontWeight': 'bold', 'color': 'green', 'fontSize': '0.9em'}),
                    html.Span(f"{format_price_display(high_display)} {currency}", style={'color': 'green', 'fontWeight': '600'})
                ]),
                html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center'}, children=[
                    html.Span("Låg:", style={'fontWeight': 'bold', 'color': 'red', 'fontSize': '0.9em'}),
                    html.Span(f"{format_price_display(low_display)} {currency}", style={'color': 'red', 'fontWeight': '600'})
                ]),
            ])
        ]
    )

    # --- KOLUMN 3: Prisrörelser (%) ---
    col3 = html.Div(
        style={'flex': '1 1 45%', 'minWidth': '250px', 'paddingLeft': '15px'},
        children=[
            html.P("Prisrörelser (%)", style={'margin': '0 0 10px 0', 'color': '#495057', 'fontWeight': 'bold', 'textAlign': 'center', 'fontSize': '0.9em'}),
            html.Div(
                style={'display': 'flex', 'justifyContent': 'space-around', 'gap': '10px'},
                children=[
                    # Sub-Kolumn 1 (Korta perioder)
                    html.Div(
                        style={'flex': '1 1 45%', 'minWidth': '100px'},
                        children=[create_change_display(p) for p in periods_col1]
                    ),
                    # Sub-Kolumn 2 (Långa perioder)
                    html.Div(
                        style={'flex': '1 1 45%', 'minWidth': '100px'},
                        children=[create_change_display(p) for p in periods_col2]
                    ),
                ]
            )
        ]
    )

    return html.Div(
        id='current-price-box',
        style={'border': '2px solid #0056b3', 'borderRadius': '10px', 'padding': '15px', 'marginBottom': '20px', 'backgroundColor': '#f8f9fa'},
        children=[
            html.Div(
                style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'flex-start', 'flexWrap': 'wrap', 'gap': '10px'},
                children=[col1, col2, col3]
            )
        ]
    )

# --- NY FUNKTION FÖR RAD-RENDERARE ---

def create_summary_row(coin_symbol, label, current_price, high_24h, low_24h, percent_data, currency, is_selected, eur_to_sek):
    """Skapar en enskild rad för list/tabellvyn."""
    
    coin_emoji = CRYPTO_EMOJIS.get(coin_symbol, '')
    
    # Prisförändring 24h
    change_24h = percent_data.get('24h')
    change_24h_display = format_change(change_24h)
    
    # Färgkodning baserad på val
    row_bg_color = '#f0f8ff' if is_selected else 'white'
    
    # Konvertera priser till displayvaluta
    price_display = current_price * eur_to_sek if currency == 'SEK' and current_price is not None else current_price
    high_display = high_24h * eur_to_sek if currency == 'SEK' and high_24h is not None else high_24h
    low_display = low_24h * eur_to_sek if currency == 'SEK' and low_24h is not None else low_24h
    
    # Rad layout (simulerar en tabellrad med Divs)
    row_columns = [
        # Valuta (Klickbar)
        html.Div(
            style={'flex': '0 0 160px', 'textAlign': 'left', 'fontWeight': 'bold', 'color': '#0056b3'},
            children=[html.Span(f"{coin_emoji} {label}", style={'whiteSpace': 'nowrap'})]
        ),
        # Pris
        html.Div(
            f"{format_price_display(price_display)} {currency}",
            style={'flex': '0 0 120px', 'textAlign': 'right', 'fontWeight': 'bold'}
        ),
        # 24h % Förändring
        html.Div(
            change_24h_display,
            style={'flex': '0 0 100px', 'textAlign': 'right'}
        ),
        # 24h Hög (OHLC)
        html.Div(
            f"{format_price_display(high_display)}",
            style={'flex': '0 0 120px', 'textAlign': 'right', 'color': 'green'}
        ),
        # 24h Låg (OHLC)
        html.Div(
            f"{format_price_display(low_display)}",
            style={'flex': '0 0 120px', 'textAlign': 'right', 'color': 'red'}
        ),
        # KORTA PERIODER (%)
        html.Div(format_change(percent_data.get('30m')), style={'flex': '0 0 80px', 'textAlign': 'right', 'whiteSpace': 'nowrap'}),
        html.Div(format_change(percent_data.get('1h')), style={'flex': '0 0 80px', 'textAlign': 'right', 'whiteSpace': 'nowrap'}),
        html.Div(format_change(percent_data.get('3h')), style={'flex': '0 0 80px', 'textAlign': 'right', 'whiteSpace': 'nowrap'}),
        # LÅNGA PERIODER (%)
        html.Div(format_change(percent_data.get('7d')), style={'flex': '0 0 80px', 'textAlign': 'right', 'whiteSpace': 'nowrap'}),
        html.Div(format_change(percent_data.get('30d')), style={'flex': '0 0 80px', 'textAlign': 'right', 'whiteSpace': 'nowrap'}),
    ]

    return html.Div(
        id={'type': 'summary-card', 'index': coin_symbol},
        n_clicks=0,
        style={
            'display': 'flex',
            'justifyContent': 'space-between',
            'alignItems': 'center',
            'padding': '10px 15px',
            'borderBottom': '1px solid #eee',
            'cursor': 'pointer',
            'backgroundColor': row_bg_color,
            'transition': 'background-color 0.2s ease, box-shadow 0.2s ease',
            'flexWrap': 'wrap',
            'boxShadow': '0 1px 2px rgba(0,0,0,0.05)' if is_selected else 'none'
        },
        children=row_columns
    )


app.layout = html.Div(style={'backgroundColor': '#f8f9fa', 'minHeight': '100vh', 'padding': '40px 10px', 'fontFamily': 'Roboto, Arial, sans-serif'}, children=[
    html.Div(style={'maxWidth': '1400px', 'margin': '40px auto', 'padding': '30px', 'borderRadius': '12px', 'boxShadow': '0 4px 12px rgba(0,0,0,0.1)', 'backgroundColor': 'white', 'border': '1px solid #dee2e6'}, children=[
        
        # 1. Namnbyte implementerat
        html.H1('📈 DJ-Investment Dashboard (Kraken Live)', style={'textAlign': 'center', 'color': '#0056b3', 'marginBottom': '30px', 'fontSize': '1.8em'}),
        
        # Kontroller
        html.Div(style={'display': 'flex', 'justifyContent': 'center', 'gap': '20px', 'alignItems': 'center', 'marginBottom': '30px', 'flexWrap': 'wrap'}, children=[
            html.Div(style={'flexGrow': 1, 'maxWidth': '300px'}, children=[
                html.Label("Välj kryptovaluta:", style={'marginBottom': '5px', 'fontWeight': 'bold', 'color': '#495057', 'display': 'block'}),
                dcc.Dropdown(id='coin-dropdown', options=[{'label': label, 'value': label.split(' ')[0]} for label in COINS_LABELS], value=DEFAULT_PAIR_KEY.split(' ')[0], clearable=False),
            ]),
            html.Div(style={'flexGrow': 1, 'maxWidth': '180px'}, children=[
                html.Label("Välj fiatvaluta:", style={'marginBottom': '5px', 'fontWeight': 'bold', 'color': '#495057', 'display': 'block'}),
                dcc.Dropdown(id='currency-dropdown', options=[{'label': f'{c} ({c})', 'value': c} for c in CURRENCIES], value='EUR', clearable=False),
            ]),
        ]),
        
        # SAMMANFATTNINGSBOXEN (Huvudboxen)
        html.Div(id='current-price-summary-box-container'),
        
        html.Div(id='last-updated', style={'textAlign': 'center', 'fontSize': '0.9em', 'color': '#6c757d', 'marginBottom': '20px'}),
        
        # Kontroller för trendlinjer
        html.Div(style={'textAlign': 'center', 'marginBottom': '10px', 'padding': '10px 0', 'borderBottom': '1px solid #eee'}, children=[
             html.Label("Visa Trendlinjer:", style={'fontWeight': 'bold', 'color': '#495057', 'marginRight': '15px'}),
             dcc.Checklist(
                 id='trendline-checkboxes',
                 options=[{'label': config['name'].split(' ')[1].replace('(', '').replace(')', ''), 'value': key} for key, config in TREND_WINDOWS.items()],
                 value=DEFAULT_TRENDS, 
                 inline=True,
                 style={'display': 'inline-block'}
             ),
             dcc.Store(id='chart-data-store'), 
             dcc.Store(id='current-currency-store'),
        ]),
        
        dcc.Loading(id="loading-1", type="circle", children=[dcc.Graph(id='live-update-graph', config={'displayModeBar': False})]),
        
        # Telegram Alerts
        html.Div(style={'marginTop': '40px', 'paddingTop': '20px', 'borderTop': '1px solid #dee2e6'}, children=[
            html.H3('🔔 Telegram Alert-inställningar', style={'fontSize': '1.3em', 'color': '#0056b3', 'marginBottom': '15px'}),
            html.P("Skickar notis när priset når eller överstiger ditt angivna gränsvärde."),
            html.Div(style={'display': 'flex', 'gap': '10px', 'alignItems': 'center', 'flexWrap': 'wrap'}, children=[
                dcc.Input(id='alert-threshold', type='number', placeholder='Ange gränsvärde', style={'flexGrow': 1, 'padding': '10px', 'borderRadius': '6px', 'border': '1px solid #ccc', 'minWidth': '150px'}),
                html.Button('Aktivera Alert', id='alert-button', n_clicks=0, style={'backgroundColor': '#17a2b8', 'color': 'white', 'padding': '10px 15px', 'borderRadius': '6px', 'border': 'none', 'cursor': 'pointer', 'fontWeight': 'bold', 'transition': 'background-color 0.3s ease', 'flexShrink': 0})
            ]),
            html.Div(id='alert-output', style={'marginTop': '10px', 'fontSize': '0.9em', 'minHeight': '20px'})
        ]),
        
        # Sammanfattning av alla valutor (Nu som lista/tabell)
        html.Div(style={'marginTop': '50px', 'paddingTop': '20px', 'borderTop': '1px solid #dee2e6'}, children=[
            html.H3('📊 Sammanfattning av alla valutor', style={'fontSize': '1.3em', 'color': '#0056b3', 'marginBottom': '10px'}),
            dcc.Loading(id="loading-2", type="dot", children=[html.Div(id='crypto-summary')])
        ]),
    ]),
    dcc.Interval(id='interval-component', interval=UPDATE_INTERVAL_SECONDS_DATA*1000, n_intervals=0)
])

# --- Callbacks ---

# Huvud-Callback: Uppdaterar all live data
@app.callback(
    # OUTPUTS MÅSTE VARA SEPARATA ARGUMENT FÖR ATT UNDVIKA KEYERROR
    Output('current-price-summary-box-container', 'children'), 
    Output('last-updated', 'children'),
    Output('chart-data-store', 'data'), 
    Output('current-currency-store', 'data'), 
    Output('crypto-summary', 'children'),
    
    [Input('interval-component', 'n_intervals'), 
     Input('coin-dropdown', 'value'), 
     Input('currency-dropdown', 'value')]
)
def update_all_live_data(n, coin_symbol, currency):
    data = get_data_from_redis()
    
    if data is None or 'EUR_SEK_RATE' not in data:
        loading_box = create_selected_coin_box("Laddar...", "", 0.0, currency, 11.0, None, None, {})
        loading_time = "Väntar på data från Kraken/Redis..."
        loading_summary = html.Div("Laddar kryptoöversikt...", style={'textAlign': 'center', 'width': '100%', 'color': '#6c757d', 'padding': '20px'})
        return loading_box, loading_time, None, currency, loading_summary

    eur_to_sek = data.get('EUR_SEK_RATE', 11.0)
    coin_label = SYMBOL_TO_LABEL.get(coin_symbol, coin_symbol)
    price_key = f'{coin_symbol}/{currency}'
    current_price_display_currency = data.get(price_key)
    timestamp = data.get('timestamp')
    current_price_eur = data.get(f'{coin_symbol}/EUR') 
    
    local_timestamp = timestamp + 3600 
    updated_text = f"Senast uppdaterad: {time.strftime('%H:%M:%S', time.gmtime(local_timestamp))} Lokal tid (CET/CEST)"
    
    percent_data = data.get('ALL_PERCENT_CHANGE', {}).get(coin_symbol, {})
    all_24h_range_ohlc = data.get('ALL_24H_RANGE_OHLC', {})
    selected_coin_24h_range = all_24h_range_ohlc.get(coin_symbol, {})
    
    # --- Förbered OHLC data för grafen och Store ---
    ohlc_interval = OHLC_CACHE_INTERVAL_MIN 
    kraken_ticker = CRYPTO_PAIRS.get(coin_label, f'{coin_symbol}/EUR')
    ohlc_cache_key = f'OHLC_CACHED_{ohlc_interval}MIN_{kraken_ticker}'
    
    historical_data_json = r.get(ohlc_cache_key) if r else None
    historical_data = json.loads(historical_data_json) if historical_data_json else []
    
    chart_data_store = None
    if historical_data and current_price_eur is not None:
        historical_data.append({'time': timestamp, 'price': current_price_eur})
        prices_eur = [item['price'] for item in historical_data]
        max_ohlc = max(prices_eur) if prices_eur else None
        min_ohlc = min(prices_eur) if prices_eur else None
        
        chart_data_store = {
            'historical_data': historical_data,
            'current_price_eur': current_price_eur,
            'max_ohlc_eur': max_ohlc,
            'min_ohlc_eur': min_ohlc,
            'eur_to_sek': eur_to_sek,
            'coin_symbol': coin_symbol
        }
    
    # 1. GENERERA SAMMANFATTNINGSBOXEN
    if current_price_display_currency is not None:
        summary_box = create_selected_coin_box(
            coin_label, coin_symbol, 
            current_price_display_currency, currency, 
            eur_to_sek, 
            selected_coin_24h_range.get('high_eur'), 
            selected_coin_24h_range.get('low_eur'), 
            percent_data
        )
    else:
        summary_box = create_selected_coin_box(coin_label, coin_symbol, 0.0, currency, eur_to_sek, None, None, percent_data)
        
    # 2. GENERERA SAMMANFATTNINGS-LISTA/TABELL
    
    # Skapa rubrikraden
    header_style = {
        'display': 'flex', 'justifyContent': 'space-between', 'fontWeight': 'bold', 
        'padding': '10px 15px', 'borderBottom': '2px solid #0056b3', 'backgroundColor': '#f0f0f0',
        'marginBottom': '5px', 'color': '#495057', 'flexWrap': 'wrap', 'fontSize': '0.9em'
    }
    
    header_columns = [
        html.Div("Valuta", style={'flex': '0 0 160px', 'textAlign': 'left'}),
        html.Div(f"Pris ({currency})", style={'flex': '0 0 120px', 'textAlign': 'right'}),
        html.Div("24h %", style={'flex': '0 0 100px', 'textAlign': 'right'}),
        html.Div("24h Hög", style={'flex': '0 0 120px', 'textAlign': 'right'}),
        html.Div("24h Låg", style={'flex': '0 0 120px', 'textAlign': 'right'}),
        html.Div("30m", style={'flex': '0 0 80px', 'textAlign': 'right', 'title': '30 minuters förändring'}),
        html.Div("1h", style={'flex': '0 0 80px', 'textAlign': 'right', 'title': '1 timmes förändring'}),
        html.Div("3h", style={'flex': '0 0 80px', 'textAlign': 'right', 'title': '3 timmars förändring'}),
        html.Div("7d", style={'flex': '0 0 80px', 'textAlign': 'right', 'title': '7 dagars förändring'}),
        html.Div("30d", style={'flex': '0 0 80px', 'textAlign': 'right', 'title': '30 dagars förändring'}),
    ]
    
    summary_header = html.Div(header_columns, style=header_style)
    
    # Skapa listan med rader
    summary_rows = []
    
    for label in COINS_LABELS:
        coin_symbol_loop = label.split(' ')[0]
        price_eur = data.get(f'{coin_symbol_loop}/EUR')
        range_data_ohlc = all_24h_range_ohlc.get(coin_symbol_loop, {})
        percent_data_loop = data.get('ALL_PERCENT_CHANGE', {}).get(coin_symbol_loop, {})
        
        is_selected = coin_symbol_loop == coin_symbol
        
        summary_row = create_summary_row(
            coin_symbol=coin_symbol_loop,
            label=label,
            current_price=price_eur,
            high_24h=range_data_ohlc.get('high_eur'),
            low_24h=range_data_ohlc.get('low_eur'),
            percent_data=percent_data_loop,
            currency=currency,
            is_selected=is_selected,
            eur_to_sek=eur_to_sek
        )
        summary_rows.append(summary_row)
        
    summary_list_view = html.Div([summary_header] + summary_rows, style={'border': '1px solid #ccc', 'borderRadius': '8px', 'overflow': 'hidden'})

    return summary_box, updated_text, chart_data_store, currency, summary_list_view


# Callback för grafen (oförändrad)
@app.callback(
    Output('live-update-graph', 'figure'),
    [Input('chart-data-store', 'data'), Input('current-currency-store', 'data'), Input('trendline-checkboxes', 'value')],
    [State('coin-dropdown', 'value')]
)
def update_trendline_visibility(chart_data_store, currency, selected_trends, coin_symbol):
    
    if chart_data_store is None:
        figure = go.Figure(go.Scatter(x=[0], y=[0], mode='text', text=['Laddar historik...'], textfont=dict(size=20, color="#0056b3")))
        figure.update_layout(title="Hämtar data...", template="plotly_white", height=400)
        return figure
        
    historical_data = chart_data_store['historical_data']
    eur_to_sek = chart_data_store['eur_to_sek']
    max_ohlc_eur = chart_data_store['max_ohlc_eur']
    min_ohlc_eur = chart_data_store['min_ohlc_eur']
    coin_label = SYMBOL_TO_LABEL.get(coin_symbol, coin_symbol)
    ohlc_interval = OHLC_CACHE_INTERVAL_MIN
    
    figure = go.Figure()

    if currency == 'SEK':
        prices_display = [item['price'] * eur_to_sek for item in historical_data]
        high_24h_display = max_ohlc_eur * eur_to_sek if max_ohlc_eur is not None else None
        low_24h_display = min_ohlc_eur * eur_to_sek if min_ohlc_eur is not None else None
    else: 
        prices_display = [item['price'] for item in historical_data]
        high_24h_display = max_ohlc_eur
        low_24h_display = min_ohlc_eur
    
    # Lägg till 1 timme för att konvertera UTC till CET/CEST
    times = [time.strftime('%H:%M', time.gmtime(item['time'] + 3600)) for item in historical_data]
    
    figure.add_trace(go.Scatter(x=times, y=prices_display, mode='lines+markers', name=f'Kurs ({ohlc_interval} min)', line=dict(color='#0056b3', width=3), marker=dict(size=4), hoverinfo='x+y'))
    
    if high_24h_display: figure.add_hline(y=high_24h_display, line_dash="dot", line_color="green", annotation_text=f"OHLC Högsta: {format_price_display(high_24h_display)} {currency}", annotation_position="top right")
    if low_24h_display: figure.add_hline(y=low_24h_display, line_dash="dot", line_color="red", annotation_text=f"OHLC Lägsta: {format_price_display(low_24h_display)} {currency}", annotation_position="bottom right")

    for trend_key, config in TREND_WINDOWS.items():
        if trend_key in selected_trends: 
            blocks = config['blocks']
            data_for_trend = historical_data[:-1] if len(historical_data) > 0 else [] 
            slope, intercept, start_index = calculate_trendline(data_for_trend, blocks)
            
            if slope is not None and start_index is not None:
                trend_x_indices = np.arange(blocks)
                trend_y_eur = slope * trend_x_indices + intercept
                trend_y_display = trend_y_eur * eur_to_sek if currency == 'SEK' else trend_y_eur
                trend_times = times[start_index:start_index + blocks]
                
                figure.add_trace(go.Scatter(x=trend_times, y=trend_y_display, mode='lines', name=config['name'], line=dict(color=config['color'], width=2, dash='dot'), hoverinfo='x+y'))

    figure.update_layout(title=f'{coin_label} Prisutveckling ({currency})', xaxis_title=f"Tid ({ohlc_interval} min)", yaxis_title=f"Pris ({currency})", template="plotly_white", margin=dict(l=40, r=40, t=40, b=40), height=400, hovermode="x unified", plot_bgcolor='white', paper_bgcolor='white', xaxis=dict(showgrid=False), yaxis=dict(gridcolor='#f0f0f0'))

    return figure

# Callback för att uppdatera Dropdown när man klickar på en rad
@app.callback(
    Output('coin-dropdown', 'value'),
    [Input({'type': 'summary-card', 'index': dash.dependencies.ALL}, 'n_clicks')],
    [State({'type': 'summary-card', 'index': dash.dependencies.ALL}, 'id')],
    prevent_initial_call=True
)
def update_dropdown_on_card_click(n_clicks, ids):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate

    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if '"type":"summary-card"' not in triggered_id:
        raise dash.exceptions.PreventUpdate
        
    try:
        triggered_id_dict = json.loads(triggered_id)
        coin_symbol = triggered_id_dict['index']
        return coin_symbol
    except (json.JSONDecodeError, KeyError):
        raise dash.exceptions.PreventUpdate

# Callback för Telegram Alert
@app.callback(
    Output('alert-output', 'children'), 
    [Input('alert-button', 'n_clicks')], 
    [State('alert-threshold', 'value'), State('coin-dropdown', 'value'), State('currency-dropdown', 'value')]
)
def handle_telegram_alert(n_clicks, threshold, coin_symbol, currency):
    if n_clicks is None or n_clicks == 0: return ""
    
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
        
    if threshold is None or threshold == '': return html.Span("❌ Ange ett giltigt gränsvärde.", style={'color': '#dc3545', 'fontWeight': 'bold'})
    
    data = get_data_from_redis()
    if data is None: return html.Span("❌ Kan inte kontrollera priset just nu. Försök igen om en stund.", style={'color': '#dc3545', 'fontWeight': 'bold'})
    
    price_key = f'{coin_symbol}/{currency}'
    current_price = data.get(price_key)
    
    if current_price is None: return html.Span(f"❌ Prisdata för {coin_symbol} saknas.", style={'color': '#dc3545', 'fontWeight': 'bold'})
    
    try: threshold_val = float(threshold)
    except ValueError: return html.Span("❌ Gränsvärdet måste vara ett nummer.", style={'color': '#dc3545', 'fontWeight': 'bold'})
    
    coin_label = SYMBOL_TO_LABEL.get(coin_symbol, coin_symbol)
    
    if current_price >= threshold_val:
        success = send_telegram_alert(coin_label, current_price, currency, threshold_val)
        if success: return html.Span(f"🔔 ALERT SKICKAD: {coin_label} priset {format_price_display(current_price)} {currency} uppnådde gränsen {format_price_display(threshold_val)}.", style={'color': '#28a745', 'fontWeight': 'bold'})
        else: return html.Span("❌ ALERT: Kunde inte skicka Telegram-meddelande.", style={'color': '#dc3545', 'fontWeight': 'bold'})
    else: 
        return html.Span(f"✅ Alert satt för {coin_label}. Trigger vid {format_price_display(threshold_val)} {currency}. Nuvarande pris: {format_price_display(current_price)}.", style={'color': '#495057'})

if __name__ == '__main__':
    # Observera: För körning lokalt måste REDIS_URL, TELEGRAM_BOT_TOKEN och TELEGRAM_CHAT_ID vara satta som miljövariabler.
    app.run_server(debug=True)