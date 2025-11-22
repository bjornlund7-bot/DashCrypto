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

# NOTERA: Följande miljövariabler MÅSTE vara satta för fullständig funktionalitet
# - TELEGRAM_BOT_TOKEN
# - TELEGRAM_CHAT_ID
# - REDIS_URL

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
DEFAULT_PAIR_KEY = 'XRP (Ripple)' 
STANDARD_TICKER = CRYPTO_PAIRS[DEFAULT_PAIR_KEY] 
COINS_LABELS = list(CRYPTO_PAIRS.keys())
COINS_SYMBOLS = [label.split(' ')[0] for label in COINS_LABELS]
SYMBOL_TO_LABEL = {label.split(' ')[0]: label for label in COINS_LABELS}
CURRENCIES = ['EUR', 'SEK']
UPDATE_INTERVAL_SECONDS_DATA = 60 
OHLC_CACHE_INTERVAL_MIN = 5 

TIME_WINDOWS = {
    '30m': {'blocks': 6, 'interval': OHLC_CACHE_INTERVAL_MIN},  
    '1h': {'blocks': 12, 'interval': OHLC_CACHE_INTERVAL_MIN},  
    '3h': {'blocks': 36, 'interval': OHLC_CACHE_INTERVAL_MIN},  
    '6h': {'blocks': 72, 'interval': OHLC_CACHE_INTERVAL_MIN},  
    '24h': {'blocks': 288, 'interval': OHLC_CACHE_INTERVAL_MIN},
    '7d': {'blocks': 7, 'interval': 1440},  
    '30d': {'blocks': 30, 'interval': 1440}, 
}

TREND_WINDOWS = {
    '1h': {'blocks': 12, 'color': '#ff7f0e', 'name': 'Trend (1h)'}, 
    '3h': {'blocks': 36, 'color': '#2ca02c', 'name': 'Trend (3h)'}, 
    '6h': {'blocks': 72, 'color': '#d62728', 'name': 'Trend (6h)'}, 
}

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
    'ALL_24H_RANGE': {'XRP': {'high_eur': 0.52, 'low_eur': 0.48}},
    'ALL_PERCENT_CHANGE': {}
}

# --- Hjälpfunktioner ---

def get_data_from_redis():
    """Hämtar data från Redis cache."""
    if r:
        try:
            cached_data = r.get('crypto_data')
            if cached_data:
                return json.loads(cached_data)
            else:
                return None
        except exceptions.ConnectionError as e:
            logger.error(f"Redis-anslutningsfel i callback: {e}")
            return None
    return None

def send_telegram_alert(coin_label, price, currency, threshold):
    """Skickar ett meddelande via Telegram-bot."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("Kan inte skicka Telegram-meddelande: Bot Token eller Chat ID saknas.")
        return False
        
    message = (
        f"🚨 Krypto Alert: Prisgräns nådd! 🚨\n\n"
        f"Valuta: {coin_label}\n"
        f"Gränsvärde: {threshold:,.4f} {currency}\n"
        f"Nuvarande pris: {price:,.4f} {currency}\n"
        f"Tid: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} Lokal Tid"
    )

    telegram_api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    try:
        response = requests.post(telegram_api_url, data={
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'Markdown'
        }, timeout=10)
        
        response.raise_for_status() 
        logger.info(f"✅ Telegram-meddelande skickat: {coin_label}")
        return True
        
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Fel vid utskick till Telegram: {e}")
        return False

def fetch_exchange_rate():
    """Hämtar EUR till SEK växelkurs."""
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
    """Hämtar realtids Ticker och 24h data från Kraken."""
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
        current_data = {'timestamp': t, 'EUR_SEK_RATE': sek_rate, 'ALL_24H_RANGE': {}, 'ALL_PERCENT_CHANGE': {}}
        
        for label, ticker in CRYPTO_PAIRS.items():
            coin_symbol = label.split(' ')[0]
            coin_info = result_key.get(ticker)
            
            # Fallback check for alternate name if direct match fails
            if coin_info is None:
                for key, info in result_key.items():
                     # Kraken returns altname, but sometimes the key itself is the altname, 
                     # but we rely on the input pair mapping
                     if key == ticker:
                         coin_info = info
                         break

            if coin_info:
                try:
                    price_eur = float(coin_info['c'][0])
                    high_24h_eur = float(coin_info['h'][0]) 
                    low_24h_eur = float(coin_info['l'][0])  
                    
                    current_data[f'{coin_symbol}/EUR'] = price_eur
                    current_data[f'{coin_symbol}/SEK'] = price_eur * sek_rate
                    
                    current_data['ALL_24H_RANGE'][coin_symbol] = {
                        'high_eur': high_24h_eur,
                        'low_eur': low_24h_eur
                    }
                except (ValueError, IndexError, TypeError) as e:
                    logger.warning(f"Failed to parse Ticker data (price/range) for {ticker}: {e}")
            
        if len(current_data) > 3: 
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
    """Hämtar OHLC-data (Close Price) från Kraken."""
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
        return [{'time': int(row[0]), 'price': float(row[4])} for row in data_list]
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching OHLC data (Interval {interval}) for {kraken_ticker}: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error processing OHLC data: {e}")
        return []

def calculate_percentage_changes(ohlc_data, current_price, periods):
    """
    Beräknar procentuell förändring baserat på historisk OHLC-data.
    Returnerar None om data saknas, 0.0 för 0% förändring.
    """
    changes = {}
    if not ohlc_data or current_price is None or current_price == 0:
        # Return None if data is missing/invalid to display 'N/A'
        return {key: None for key in periods}

    for period, config in periods.items():
        blocks = config['blocks']
        if len(ohlc_data) >= blocks:
            # -blocks refers to the item 'blocks' periods ago.
            reference_price = ohlc_data[-blocks]['price']
            if reference_price and reference_price > 0:
                change = ((current_price - reference_price) / reference_price) * 100
                changes[period] = change
            else:
                # Historical price is zero or missing, cannot calculate
                changes[period] = None 
        else:
            # Not enough historical data points
            changes[period] = None 
    return changes

def calculate_trendline(historical_data, blocks):
    """Beräknar en linjär trendlinje (Least Squares) för de senaste 'blocks' datan."""
    if len(historical_data) < blocks:
        return None, None, None
    data_segment = historical_data[-blocks:]
    x_values = np.arange(blocks) # Använd index 0 till blocks-1 för linregress
    y_values = np.array([item['price'] for item in data_segment])
    
    # Utför linjär regression
    slope, intercept, r_value, p_value, std_err = linregress(x_values, y_values)
    
    # Startindexet i den totala historiska datan
    start_index_global = len(historical_data) - blocks 
    
    return slope, intercept, start_index_global

def format_change(c):
    """Global format funktion. Visar N/A för None, 0.00% för 0.0."""
    if c is None: 
        return html.Span("N/A", style={'color': '#6c757d'})
    
    # Explicitly check for 0.0 to differentiate from missing data
    if c == 0.0:
        return html.Span("0.00%", style={'color': '#6c757d', 'fontWeight': 'bold'})
        
    color = '#10b981' if c > 0 else '#ef4444'
    symbol = '▲' if c > 0 else '▼'
    return html.Span(f"{symbol} {abs(c):.2f}%", style={'color': color, 'fontWeight': 'bold'})

# --- Bakgrundstrådens Logik ---
def update_redis_cache(redis_instance):
    """Uppdaterar all krypto- och OHLC-data i Redis var 120:e sekund."""
    UPDATE_CYCLE_SECONDS = 120 
    
    while True:
        cycle_start_time = time.time()
        
        try:
            logger.debug("--- Bakgrundstråd: Startar uppdateringscykel ---")
            
            new_data = fetch_crypto_data()
            if redis_instance:
                # Cache Ticker data quickly
                redis_instance.set('crypto_data', json.dumps(new_data), ex=UPDATE_CYCLE_SECONDS + 60)
                logger.debug("✅ Prisdata (Ticker) sparad snabbt.")

            all_percent_changes = {} 
            
            # Fetch OHLC data for each pair sequentially (or in batches)
            for label, ticker in CRYPTO_PAIRS.items():
                coin_symbol = label.split(' ')[0]
                current_price_eur = new_data.get(f'{coin_symbol}/EUR')
                
                if current_price_eur is None:
                    time.sleep(1) 
                    continue
                
                # 1. Fetch 5-min OHLC for short-term changes/graphing (24h worth)
                periods_ago_24h = 86400 
                ohlc_5min_data = fetch_ohlc_data_from_kraken(ticker, OHLC_CACHE_INTERVAL_MIN, periods_ago_24h) 
                
                short_term_periods = {k: v for k, v in TIME_WINDOWS.items() if v['interval'] == OHLC_CACHE_INTERVAL_MIN}
                percent_changes = calculate_percentage_changes(ohlc_5min_data, current_price_eur, short_term_periods)
                
                if ohlc_5min_data and redis_instance:
                    ohlc_cache_key = f'OHLC_CACHED_{OHLC_CACHE_INTERVAL_MIN}MIN_{ticker}' 
                    redis_instance.set(ohlc_cache_key, json.dumps(ohlc_5min_data), ex=7200) 
                    logger.debug(f"    >>> OHLC 5-min sparad för {ticker}")
                    
                # 2. Fetch 1-day OHLC for long-term changes (30d worth)
                periods_ago_30d = 2592000 
                ohlc_1day_data = fetch_ohlc_data_from_kraken(ticker, 1440, periods_ago_30d) 
                long_term_periods = {k: v for k, v in TIME_WINDOWS.items() if v['interval'] == 1440}
                long_term_changes = calculate_percentage_changes(ohlc_1day_data, current_price_eur, long_term_periods)
                
                percent_changes.update(long_term_changes)
                all_percent_changes[coin_symbol] = percent_changes
                
                time.sleep(0.2) 
            
            new_data['ALL_PERCENT_CHANGE'] = all_percent_changes
            
            if redis_instance:
                # Save data again, now including the calculated percentage changes
                redis_instance.set('crypto_data', json.dumps(new_data), ex=UPDATE_CYCLE_SECONDS + 60)
                logger.debug("✅ Hela 'crypto_data' inkl procentrörelser sparad.")
            
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
    worker_thread = threading.Thread(target=update_redis_cache, args=(r,), daemon=True)
    worker_thread.start()
    logger.debug(">>> Bakgrundstråd startad!")

# --- DASH ---
app = dash.Dash(__name__, external_stylesheets=['https://codepen.io/chriddyp/pen/bWLwgP.css'])
server = app.server 

app.layout = html.Div(style={'backgroundColor': '#f8f9fa', 'minHeight': '100vh', 'padding': '40px 10px', 'fontFamily': 'Roboto, Arial, sans-serif'}, children=[
    html.Div(style={'maxWidth': '1400px', 'margin': '40px auto', 'padding': '30px', 'borderRadius': '12px', 'boxShadow': '0 4px 12px rgba(0,0,0,0.1)', 'backgroundColor': 'white', 'border': '1px solid #dee2e6'}, children=[
        html.H1('📈 MTS Krypto Dashboard (Kraken Live)', style={'textAlign': 'center', 'color': '#0056b3', 'marginBottom': '30px', 'fontSize': '1.8em'}),
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
        html.Div(id='current-price', style={'textAlign': 'center', 'fontSize': '3em', 'fontWeight': '800', 'color': '#0056b3', 'marginBottom': '5px'}),
        html.Div(id='last-updated', style={'textAlign': 'center', 'fontSize': '0.9em', 'color': '#6c757d', 'marginBottom': '40px'}),
        dcc.Loading(id="loading-1", type="circle", children=[dcc.Graph(id='live-update-graph', config={'displayModeBar': False})]),
        html.Div(style={'marginTop': '40px', 'paddingTop': '20px', 'borderTop': '1px solid #dee2e6'}, children=[
            html.H3('🔔 Telegram Alert-inställningar', style={'fontSize': '1.3em', 'color': '#0056b3', 'marginBottom': '15px'}),
            html.P("Skickar notis när priset når eller överstiger ditt angivna gränsvärde."),
            html.Div(style={'display': 'flex', 'gap': '10px', 'alignItems': 'center', 'flexWrap': 'wrap'}, children=[
                dcc.Input(id='alert-threshold', type='number', placeholder='Ange gränsvärde', style={'flexGrow': 1, 'padding': '10px', 'borderRadius': '6px', 'border': '1px solid #ccc', 'minWidth': '150px'}),
                html.Button('Aktivera Alert', id='alert-button', n_clicks=0, style={'backgroundColor': '#17a2b8', 'color': 'white', 'padding': '10px 15px', 'borderRadius': '6px', 'border': 'none', 'cursor': 'pointer', 'fontWeight': 'bold', 'transition': 'background-color 0.3s ease', 'flexShrink': 0})
            ]),
            html.Div(id='alert-output', style={'marginTop': '10px', 'fontSize': '0.9em', 'minHeight': '20px'})
        ]),
        html.Div(style={'marginTop': '50px', 'paddingTop': '20px', 'borderTop': '1px solid #dee2e6'}, children=[
            html.H3('📊 Sammanfattning av alla valutor', style={'fontSize': '1.3em', 'color': '#0056b3', 'marginBottom': '20px'}),
            dcc.Loading(id="loading-2", type="dot", children=[html.Div(id='crypto-summary', style={'display': 'flex', 'flexWrap': 'wrap', 'gap': '15px', 'justifyContent': 'flex-start'})])
        ]),
    ]),
    dcc.Interval(id='interval-component', interval=120*1000, n_intervals=0)
])

@app.callback(
    Output('current-price', 'children'),
    Output('last-updated', 'children'),
    Output('live-update-graph', 'figure'),
    Output('crypto-summary', 'children'),
    [Input('interval-component', 'n_intervals'), Input('coin-dropdown', 'value'), Input('currency-dropdown', 'value')]
)
def update_all_live_data(n, coin_symbol, currency):
    data = get_data_from_redis()
    
    if data is None or 'EUR_SEK_RATE' not in data:
        loading_text = html.Span("Laddar data...", style={'color': '#6c757d'})
        loading_time = "Väntar på data från Kraken/Redis..."
        figure = go.Figure(go.Scatter(x=[0], y=[0], mode='text', text=['Laddar...'], textfont=dict(size=20, color="#0056b3")))
        figure.update_layout(title="Hämtar data...", template="plotly_white", height=400)
        loading_summary = html.Div("Laddar kryptoöversikt...", style={'textAlign': 'center', 'width': '100%', 'color': '#6c757d', 'padding': '20px'})
        return loading_text, loading_time, figure, loading_summary

    eur_to_sek = data.get('EUR_SEK_RATE', 11.0)
    coin_label = SYMBOL_TO_LABEL.get(coin_symbol, coin_symbol)
    price_key = f'{coin_symbol}/{currency}'
    current_price_display_currency = data.get(price_key)
    timestamp = data.get('timestamp')
    current_price_eur = data.get(f'{coin_symbol}/EUR') 
    
    # --- PRIS OCH UPPDATERINGSTEXT ---
    if current_price_display_currency is None:
        price_text = html.Span(f"❌ Pris för {coin_symbol}/{currency} saknas.", style={'color': '#dc3545', 'fontSize': '1.2em'})
        updated_text = "Data saknas."
    else:
        # Format the price with SEK/EUR separators (using space for thousands and comma for decimal)
        price_format = f"{current_price_display_currency:,.4f}" if current_price_display_currency < 10 else f"{current_price_display_currency:,.2f}"
        price_format = price_format.replace(",", "TEMP").replace(".", ",").replace("TEMP", " ") 
        
        # Determine color based on overall availability/validity
        color = '#28a745' if current_price_eur else '#dc3545'
        price_text = html.Span(f"{coin_label}: {price_format} {currency}", style={'color': color})
        updated_text = f"Senast uppdaterad: {time.strftime('%H:%M:%S', time.localtime(timestamp))} Lokal tid (CET/CEST)"
    
    # --- GRAF RITNING ---
    ohlc_interval = OHLC_CACHE_INTERVAL_MIN 
    kraken_ticker = CRYPTO_PAIRS.get(coin_label, f'{coin_symbol}/EUR')
    ohlc_cache_key = f'OHLC_CACHED_{ohlc_interval}MIN_{kraken_ticker}'
    
    historical_data_json = r.get(ohlc_cache_key) if r else None
    historical_data = json.loads(historical_data_json) if historical_data_json else []
        
    range_data_raw = data.get('ALL_24H_RANGE', {}).get(coin_symbol, {})
    high_24h_eur = range_data_raw.get('high_eur')
    low_24h_eur = range_data_raw.get('low_eur')
    
    figure = go.Figure()
    
    if historical_data and current_price_eur is not None:
        prices_eur = [item['price'] for item in historical_data]
        if currency == 'SEK':
            prices_display = [p * eur_to_sek for p in prices_eur]
            high_24h_display = high_24h_eur * eur_to_sek if high_24h_eur is not None else None
            low_24h_display = low_24h_eur * eur_to_sek if low_24h_eur is not None else None
        else: 
            prices_display = prices_eur
            high_24h_display = high_24h_eur
            low_24h_display = low_24h_eur
        
        # Inkludera den senaste prisuppdateringen i slutet av grafen
        prices_display.append(current_price_display_currency)
        
        # Lägg till nuvarande tidpunkt till tidsaxeln (behövs för att matcha sista priset)
        times = [time.strftime('%H:%M', time.localtime(item['time'])) for item in historical_data]
        times.append(time.strftime('%H:%M', time.localtime(timestamp)))
        
        figure.add_trace(go.Scatter(x=times, y=prices_display, mode='lines+markers', name=f'Kurs ({ohlc_interval} min)', line=dict(color='#0056b3', width=3), marker=dict(size=4), hoverinfo='x+y'))
        
        # Trendlinjer (baseras på historisk OHLC-data, exkluderar den senaste ticker-uppdateringen)
        # OBS: trendlinjerna beräknas på OHLC (EUR) och konverteras sedan till display-valuta
        for trend_key, config in TREND_WINDOWS.items():
            blocks = config['blocks']
            slope, intercept, start_index = calculate_trendline(historical_data, blocks)
            if slope is not None and start_index is not None:
                # trend_x_indices är index i den segmenterade data-listan (0 till blocks-1)
                trend_x_indices = np.arange(blocks)
                # Trendlinjens Y-värden i EUR
                trend_y_eur = slope * trend_x_indices + intercept
                # Konvertera till display-valuta
                trend_y_display = trend_y_eur * eur_to_sek if currency == 'SEK' else trend_y_eur
                # Motsvarande tider (OHLC-tider)
                trend_times = times[start_index:start_index + blocks]
                
                figure.add_trace(go.Scatter(x=trend_times, y=trend_y_display, mode='lines', name=config['name'], line=dict(color=config['color'], width=2, dash='dash'), hoverinfo='x+y'))

        def format_24h_label(p):
            if p is None: return "N/A"
            price_format_24h = f"{p:,.4f}" if p < 10 else f"{p:,.2f}"
            return price_format_24h.replace(",", "TEMP").replace(".", ",").replace("TEMP", " ")

        if high_24h_display: figure.add_hline(y=high_24h_display, line_dash="dot", line_color="green", annotation_text=f"24h Högsta: {format_24h_label(high_24h_display)} {currency}", annotation_position="top right")
        if low_24h_display: figure.add_hline(y=low_24h_display, line_dash="dot", line_color="red", annotation_text=f"24h Lägsta: {format_24h_label(low_24h_display)} {currency}", annotation_position="bottom right")

    else:
        # Fallback för grafen om historik saknas
        msg = f"Laddar historik ({ohlc_interval}-min) för {coin_label}..."
        current_time_str = time.strftime('%H:%M:%S', time.localtime())
        price_display = current_price_display_currency if current_price_display_currency else 0
        figure.add_trace(go.Scatter(x=[current_time_str], y=[price_display], mode='markers+text', marker=dict(size=10, color='#28a745'), text=[f"Pris: {price_display:,.2f} {currency}"], textposition="top center"))
        figure.add_trace(go.Scatter(x=[0], y=[0], mode='text', text=[msg], showlegend=False))
    
    figure.update_layout(title=f'{coin_label} Prisutveckling ({currency})', xaxis_title=f"Tid ({ohlc_interval} min)", yaxis_title=f"Pris ({currency})", template="plotly_white", margin=dict(l=40, r=40, t=40, b=40), height=400, hovermode="x unified", plot_bgcolor='white', paper_bgcolor='white', xaxis=dict(showgrid=False), yaxis=dict(gridcolor='#f0f0f0'))
    
    # --- SAMMANFATTNINGSKORT ---
    all_percent_changes = data.get('ALL_PERCENT_CHANGE', {}) 
    all_24h_range = data.get('ALL_24H_RANGE', {})
    summary_cards = []
    card_style = {'flex': '0 1 calc(25% - 15px)', 'minWidth': '200px', 'padding': '15px', 'border': '1px solid #e0e0e0', 'borderRadius': '8px', 'backgroundColor': '#ffffff', 'boxShadow': '0 2px 4px rgba(0,0,0,0.05)', 'transition': 'transform 0.2s ease', 'cursor': 'pointer'}
    periods_to_show = ['30m', '1h', '3h', '6h', '24h', '7d', '30d']
    
    for label in COINS_LABELS:
        coin_symbol_loop = label.split(' ')[0]
        price_eur = data.get(f'{coin_symbol_loop}/EUR')
        range_data = all_24h_range.get(coin_symbol_loop, {})
        percent_data = all_percent_changes.get(coin_symbol_loop, {})
        high_24h_eur = range_data.get('high_eur')
        low_224h_eur = range_data.get('low_eur')
        
        current_price_loop = None
        high_24h = None
        low_24h = None

        if price_eur is not None:
            if currency == 'SEK':
                current_price_loop = price_eur * eur_to_sek
                high_24h = high_24h_eur * eur_to_sek if high_24h_eur is not None else None
                low_24h = low_224h_eur * eur_to_sek if low_224h_eur is not None else None
            else:
                current_price_loop = price_eur
                high_24h = high_24h_eur
                low_24h = low_224h_eur
            
            def format_price(p):
                if p is None: return "N/A"
                price_format = f"{p:,.4f}" if p < 10 else f"{p:,.2f}"
                return price_format.replace(",", "TEMP").replace(".", ",").replace("TEMP", " ")
            
            formatted_price = format_price(current_price_loop)
            formatted_high = format_price(high_24h)
            formatted_low = format_price(low_24h)
            price_text_loop = f"{formatted_price} {currency}"
            
        else:
            price_text_loop = "N/A"
            formatted_high = "N/A"
            formatted_low = "N/A"
            
        # Välj färg för kortet baserat på 24h förändring (om tillgänglig)
        change_24h = percent_data.get('24h')
        card_class = ''
        if change_24h is not None:
            if change_24h > 0.5:
                card_class = 'border-l-4 border-green-500' # Lätt tillägg för att indikera positiv rörelse
            elif change_24h < -0.5:
                card_class = 'border-l-4 border-red-500' # Lätt tillägg för att indikera negativ rörelse
        
        card_content = [
            html.P(label, style={'margin': '0 0 5px 0', 'fontSize': '1.1em', 'fontWeight': '500', 'color': '#0056b3'}),
            html.P(price_text_loop, style={'margin': '0 0 10px 0', 'fontSize': '1.4em', 'fontWeight': 'bold', 'color': '#28a745' if price_eur else '#dc3545'}),
            html.Div(style={'borderTop': '1px solid #f0f0f0', 'paddingTop': '10px', 'marginBottom': '10px'}, children=[
                html.Small("Prisrörelse:", style={'color': '#6c757d', 'fontWeight': 'bold', 'display': 'block', 'marginBottom': '5px'}),
                html.Table(style={'width': '100%', 'fontSize': '0.9em', 'borderCollapse': 'collapse'}, children=[
                    html.Tbody([
                        html.Tr(children=[
                            html.Td(f"{period}:", style={'padding': '3px 5px', 'borderBottom': '1px dotted #e0e0e0', 'width': '50%'}),
                            html.Td(format_change(percent_data.get(period)), style={'padding': '3px 5px', 'borderBottom': '1px dotted #e0e0e0', 'textAlign': 'right'})
                        ]) for period in periods_to_show
                    ])
                ])
            ]),
            html.Small("24h Högsta:", style={'color': '#6c757d', 'display': 'block', 'marginTop': '5px'}),
            html.Small(f"{formatted_high} {currency}", style={'color': 'green', 'fontWeight': 'bold', 'display': 'block'}),
            html.Small("24h Lägsta:", style={'color': '#6c757d', 'marginTop': '5px', 'display': 'block'}),
            html.Small(f"{formatted_low} {currency}", style={'color': 'red', 'fontWeight': 'bold', 'display': 'block'}),
        ]
        
        # Wrap card in Div with an implicit click handler to update the main graph
        card = html.Div(
            id={'type': 'summary-card', 'index': coin_symbol_loop},
            className=card_class,
            style=card_style, 
            children=card_content,
            n_clicks=0, # Lägg till n_clicks för att kunna trigga en callback
            title=f"Klicka för att se {label} i diagrammet."
        )
        summary_cards.append(card)

    return price_text, updated_text, figure, summary_cards

# Callback för att uppdatera Dropdown när man klickar på ett summary-kort
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

    # Hitta vilket kort som klickades
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # Hantera potentialen att det triggas av något annat än n_clicks
    if '"type":"summary-card"' not in triggered_id:
        raise dash.exceptions.PreventUpdate
        
    # Parsar ID:t för att få symbolen
    try:
        triggered_id_dict = json.loads(triggered_id)
        coin_symbol = triggered_id_dict['index']
        return coin_symbol
    except (json.JSONDecodeError, KeyError):
        raise dash.exceptions.PreventUpdate

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
        if success: return html.Span(f"🔔 ALERT SKICKAD: {coin_label} priset {current_price:,.4f} {currency} uppnådde gränsen {threshold_val:,.4f}.", style={'color': '#28a745', 'fontWeight': 'bold'})
        else: return html.Span("❌ ALERT: Kunde inte skicka Telegram-meddelande.", style={'color': '#dc3545', 'fontWeight': 'bold'})
    else: 
        return html.Span(f"✅ Alert satt för {coin_label}. Trigger vid {threshold_val:,.4f} {currency}. Nuvarande pris: {current_price:,.4f}.", style={'color': '#495057'})

if __name__ == '__main__':
    # Observera: Körning lokalt kräver att Redis-servern är igång och tillgänglig
    # samt att miljövariablerna (REDIS_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID) är satta i terminalen.
    app.run_server(debug=True) 
if __name__ != '__main__':
    pass