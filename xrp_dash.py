import dash
from dash import dcc, html, ctx, ALL
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
from datetime import datetime, timezone, timedelta

# --- Konstanter, Logging och API Konfiguration ---

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

# [KONSTANTER]
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
    'MYX (MYX Finance)': 'MYX/EUR', 'GNO (Gnosis)': 'GNO/EUR', 'KOBAN (Lucky Kat)': 'KOBAN/EUR', 'XNAP (SNAPX)': 'XNAP/EUR',
    'LINK (Chainlink)': 'LINK/EUR', 'XLM (Lumen)': 'XLM/EUR', 'HBAR (Hedera)': 'HBAR/EUR', 'TON (Toncoin)': 'TON/EUR',
    'AAVE (Aave)': 'AAVE/EUR', 'ONDO (Ondo)': 'ONDO/EUR', 'QNT (Quant)': 'QNT/EUR', 'RENDER (Render)': 'RENDER/EUR',
    'BRICK (Bricks)': 'BRICK/EUR',
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
DEFAULT_COIN_SYMBOL = DEFAULT_PAIR_KEY.split(' ')[0]

COINS_LABELS = list(CRYPTO_PAIRS.keys())
COINS_SYMBOLS = [label.split(' ')[0] for label in COINS_LABELS]

BASE_CURRENCIES = ['EUR', 'SEK'] + [s for s in COINS_SYMBOLS]
SYMBOL_TO_LABEL = {label.split(' ')[0]: label for label in COINS_LABELS}

UPDATE_INTERVAL_SECONDS_DATA = 120
SUMMARY_SCHEDULE_HOURS = [7, 9, 12, 15, 18, 21]
REDIS_SUMMARY_KEY = 'summary_last_sent_time'

# Tidsfönster för beräkning av %-förändring
TIME_WINDOWS = {
    '30m': {'blocks': 6, 'interval': 5},
    '1h': {'blocks': 12, 'interval': 5},
    '3h': {'blocks': 36, 'interval': 5},
    '6h': {'blocks': 72, 'interval': 5},
    '12h': {'blocks': 144, 'interval': 5},
    '18h': {'blocks': 216, 'interval': 5},
    '24h': {'blocks': 288, 'interval': 5},
    '7d': {'blocks': 7, 'interval': 1440},
    '30d': {'blocks': 30, 'interval': 1440},
    '6m': {'blocks': 180, 'interval': 1440},
    '1y': {'blocks': 365, 'interval': 1440},
}

# Trendlinjer (visas endast i 24h-vyn då de är baserade på 5min data)
TREND_WINDOWS = {
    '1h':  {'blocks': 12,  'color': '#ff7f0e', 'name': 'Trend (1h)',  'weight': 5, 'source': '5min', 'show_line': True},
    '3h':  {'blocks': 36,  'color': '#2ca02c', 'name': 'Trend (3h)',  'weight': 4, 'source': '5min', 'show_line': True},
    '6h':  {'blocks': 72,  'color': '#d62728', 'name': 'Trend (6h)',  'weight': 3, 'source': '5min', 'show_line': True},
    '12h': {'blocks': 144, 'color': '#9467bd', 'name': 'Trend (12h)', 'weight': 3, 'source': '5min', 'show_line': True},
    '18h': {'blocks': 216, 'color': '#8c564b', 'name': 'Trend (18h)', 'weight': 2, 'source': '5min', 'show_line': True},
    '7d':  {'blocks': 7,   'color': '#e377c2', 'name': 'Trend (7d)',  'weight': 1, 'source': '1day', 'show_line': False},
    '30d': {'blocks': 30,  'color': '#7f7f7f', 'name': 'Trend (30d)', 'weight': 0.4, 'source': '1day', 'show_line': False},
    '6m': {'blocks': 180, 'color': '#17becf', 'name': 'Trend (6m)', 'weight': 0.2, 'source': '1day', 'show_line': False},
    '1y': {'blocks': 365, 'color': '#bcbd22', 'name': 'Trend (1år)', 'weight': 0.1, 'source': '1day', 'show_line': False},
}

ALERT_THRESHOLDS_UP = sorted([10, 20, 30, 40, 50, 75, 100], reverse=True)
ALERT_THRESHOLDS_DOWN = sorted([-10, -20, -25, -30, -50, -75])
ALERT_PERIODS = ['30m', '1h', '3h', '6h', '12h', '24h']
ALERT_DEBOUNCE_SECONDS = 2 * 3600 

TRADE_VALUE_ALERTS = sorted([50, 75, 100, 150], reverse=True)
TRADE_VALUE_DEBOUNCE_SECONDS = 2 * 3600 

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
    'timestamp': time.time(),
    'EUR_SEK_RATE': 11.0,
    'ALL_PERCENT_CHANGE': {},
    'ALL_24H_RANGE_OHLC': {},
}

# --- Hjälpfunktioner ---

def format_price_display(p):
    if p is None: return "N/A"
    price_format = f"{p:,.8f}" if p < 0.1 else (f"{p:,.4f}" if p < 10 else f"{p:,.2f}")
    return price_format.replace(",", "TEMP").replace(".", ",").replace("TEMP", " ")

def format_price_telegram(p):
    if p is None: return "N/A"
    if p < 10:
        return f"{p:.4f}".replace(".", ",")
    else:
        return f"{p:,.2f}".replace(",", "TEMP").replace(".", ",").replace("TEMP", " ")

def get_data_from_redis():
    if r:
        try:
            cached_data = r.get('crypto_data')
            if cached_data:
                return json.loads(cached_data)
        except exceptions.ConnectionError as e:
            logger.error(f"Redis-anslutningsfel: {e}")
    return None

def format_change_telegram(c):
    if c is None: return " N/A "
    sign = "+" if c >= 0 else ""
    return f"{sign}{c:.2f}%".rjust(6)

def format_trade_value_telegram(v):
    if v is None: return " N/A "
    sign = "+" if v >= 0 else ""
    return f"{sign}{int(round(v))}".rjust(4)

def calculate_trade_value(short_term_data, current_price_eur, long_term_data=None):
    if not short_term_data or current_price_eur is None:
        return None, {}

    V = current_price_eur
    trade_value = 0.0
    individual_trends = {}
    
    for key, config in TREND_WINDOWS.items():
        blocks = config['blocks']
        weight = config['weight']
        source = config.get('source', '5min')
        
        historical_data = None
        if source == '5min':
            historical_data = short_term_data
        elif source == '1day':
            historical_data = long_term_data
            
        if not historical_data:
            individual_trends[key] = None
            continue
        
        data_segment = historical_data[-blocks:] 
        if len(data_segment) < blocks:
            individual_trends[key] = None
            continue 

        x_values = np.arange(blocks) 
        y_values = np.array([item['price'] for item in data_segment])
        
        slope, intercept, _, _, _ = linregress(x_values, y_values)
        Tx = slope * (blocks - 1) + intercept 
        
        if V is not None and V != 0:
            Hx = (((Tx - V) / V) * 100) * weight
            trade_value += Hx
            individual_trends[key] = {'val': Hx, 'price': Tx} 
        else:
            individual_trends[key] = None

    return trade_value, individual_trends

def fetch_exchange_rate():
    try:
        response = requests.get(EXCHANGE_RATE_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data['rates'].get('SEK', 11.0)
    except requests.exceptions.RequestException as e:
        logger.error(f"Error exchange rate: {e}. Using 11.0.")
        return 11.0

def fetch_crypto_data():
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
        current_data = {'timestamp': t, 'EUR_SEK_RATE': sek_rate, 'ALL_PERCENT_CHANGE': {}, 'ALL_24H_RANGE_OHLC': {}}
        
        for label, ticker in CRYPTO_PAIRS.items():
            coin_symbol = label.split(' ')[0]
            coin_info = result_key.get(ticker)
            if coin_info is None: continue
            try:
                price_eur = float(coin_info['c'][0])
                price_yesterday_eur = float(coin_info['o']) 
                diff_24h_eur = price_eur - price_yesterday_eur
                current_data[f'{coin_symbol}/EUR'] = price_eur
                current_data[f'{coin_symbol}/DIFF_24H_EUR'] = diff_24h_eur
            except Exception as e:
                logger.warning(f"Failed ticker parse for {ticker}: {e}")
            
        return current_data
    except Exception as e:
        logger.error(f"Error fetching ticker: {e}")
        return DEFAULT_DATA 

def fetch_ohlc_data_from_kraken(kraken_ticker, interval, periods_ago_seconds):
    time_ago = int(time.time()) - periods_ago_seconds 
    params = { 'pair': kraken_ticker, 'interval': interval, 'since': time_ago }
    try:
        response = requests.get(KRAKEN_OHLC_API_URL, params=params, timeout=15)
        response.raise_for_status()
        ohlc_data = response.json()
        if ohlc_data.get('error'): return []
        result_key = next(iter(ohlc_data['result'])) 
        data_list = ohlc_data['result'][result_key]
        return [{'time': int(row[0]), 'price': float(row[4])} for row in data_list]
    except Exception as e:
        logger.error(f"Error fetching OHLC: {e}")
        return []

def calculate_percentage_changes(ohlc_data, current_price, periods):
    changes = {}
    if not ohlc_data or current_price is None:
        return {key: None for key in periods}
    for period, config in periods.items():
        blocks = config['blocks']
        if len(ohlc_data) >= blocks:
            ref_price = ohlc_data[-blocks]['price']
            if ref_price > 0:
                changes[period] = ((current_price - ref_price) / ref_price) * 100
            else: changes[period] = None 
        else: changes[period] = None
    return changes

def calculate_trendline(historical_data, blocks):
    if len(historical_data) < blocks:
        return None, None, None
    data_segment = historical_data[-blocks:]
    x_values = np.arange(blocks) 
    y_values = np.array([item['price'] for item in data_segment])
    slope, intercept, _, _, _ = linregress(x_values, y_values)
    start_index_global = len(historical_data) - blocks 
    return slope, intercept, start_index_global

def format_change(c):
    if c is None: return html.Span("N/A", style={'color': '#6c757d'})
    color = '#28a745' if c > 0 else '#dc3545' 
    symbol = '▲' if c > 0 else '▼'
    return html.Span(f"{symbol} {abs(c):.2f}%", style={'color': color, 'fontWeight': 'bold', 'fontSize': '0.85em'})

def format_trade_value_display(v):
    if v is None: return html.Span("N/A", style={'color': '#6c757d'})
    val = int(round(v))
    color = '#006400' if val > 0 else '#8B0000' 
    symbol = '▲' if val > 0 else '▼'
    return html.Span(f"{symbol} {abs(val)}", style={'color': color, 'fontWeight': 'bold', 'fontSize': '0.85em'})

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}, timeout=10)
        return True
    except Exception: return False

def check_and_send_alerts(alert_data, r_instance):
    if not r_instance: return
    for coin_symbol, data in alert_data.items():
        changes = data['changes']
        price = data['price_eur']
        if price is None: continue
        for period in ALERT_PERIODS:
            c = changes.get(period)
            if c is None: continue
            if c > 0:
                threshold = next((t for t in ALERT_THRESHOLDS_UP if c >= t), None)
                if threshold and r_instance.set(f"alert:{coin_symbol}:+{period}:{threshold}", 1, ex=ALERT_DEBOUNCE_SECONDS, nx=True):
                    send_telegram_message(f"🚀 **HÖG PRISUPPGÅNG**\n*{SYMBOL_TO_LABEL.get(coin_symbol)}*\nPris: *{format_price_telegram(price)} EUR*\n+{c:.2f}% ({period})")
            elif c < 0:
                threshold = next((t for t in ALERT_THRESHOLDS_DOWN if c <= t), None)
                if threshold and r_instance.set(f"alert:{coin_symbol}:{period}:{threshold}", 1, ex=ALERT_DEBOUNCE_SECONDS, nx=True):
                    send_telegram_message(f"🔻 **HÖG PRISNEDGÅNG**\n*{SYMBOL_TO_LABEL.get(coin_symbol)}*\nPris: *{format_price_telegram(price)} EUR*\n{c:.2f}% ({period})")

def background_data_fetch(redis_instance):
    while True:
        try:
            new_data = fetch_crypto_data()
            all_percent_changes = {}
            all_24h_range_ohlc = {} 
            alert_data_all = {}
            
            for label, ticker in CRYPTO_PAIRS.items():
                coin_symbol = label.split(' ')[0]
                price = new_data.get(f'{coin_symbol}/EUR')
                if price is None: continue
                
                # Hämta 24h (5min) OCH 7 dagar (15min)
                ohlc_5m = fetch_ohlc_data_from_kraken(ticker, 5, 86400)
                ohlc_15m = fetch_ohlc_data_from_kraken(ticker, 15, 604800)
                ohlc_1d = fetch_ohlc_data_from_kraken(ticker, 1440, 365 * 86400)

                if ohlc_5m:
                    redis_instance.set(f'OHLC_CACHED_5MIN_{ticker}', json.dumps(ohlc_5m), ex=7200)
                    prices = [item['price'] for item in ohlc_5m]
                    all_24h_range_ohlc[coin_symbol] = {'high_eur': max(prices), 'low_eur': min(prices)}
                
                if ohlc_15m:
                    redis_instance.set(f'OHLC_CACHED_15MIN_{ticker}', json.dumps(ohlc_15m), ex=7200)

                if ohlc_1d:
                    redis_instance.set(f'OHLC_1DAY_{ticker}', json.dumps(ohlc_1d), ex=86400)

                # Beräkna procentuella förändringar
                p_short = calculate_percentage_changes(ohlc_5m, price, {k:v for k,v in TIME_WINDOWS.items() if v['interval']==5})
                p_long = calculate_percentage_changes(ohlc_1d, price, {k:v for k,v in TIME_WINDOWS.items() if v['interval']==1440})
                p_short.update(p_long)
                all_percent_changes[coin_symbol] = p_short
                alert_data_all[coin_symbol] = {'changes': p_short, 'price_eur': price}
                
                time.sleep(0.1) 

            check_and_send_alerts(alert_data_all, redis_instance)
            new_data['ALL_PERCENT_CHANGE'] = all_percent_changes
            new_data['ALL_24H_RANGE_OHLC'] = all_24h_range_ohlc
            redis_instance.set('crypto_data', json.dumps(new_data), ex=300)
            
            time.sleep(UPDATE_INTERVAL_SECONDS_DATA)
        except Exception as e:
            logger.error(f"Bakgrundsfel: {e}")
            time.sleep(60)

if r:
    threading.Thread(target=background_data_fetch, args=(r,), daemon=True).start()

# --- Dash App ---

app = dash.Dash(__name__)
server = app.server

def create_summary_row(symbol, label, price, percent_data, trade_value, currency, is_selected):
    row_style = {'display': 'flex', 'alignItems': 'center', 'padding': '5px 0', 'borderBottom': '1px solid #eee', 'fontSize': '0.85em', 'cursor': 'pointer', 'backgroundColor': '#e6f7ff' if is_selected else '#fff'}
    
    price_str = format_price_display(price)
    change_24h = percent_data.get('24h')
    change_color = '#28a745' if change_24h and change_24h > 0 else '#dc3545' if change_24h and change_24h < 0 else '#495057'

    return html.Div(id={'type': 'summary-card', 'index': symbol}, style=row_style, children=[
        html.Div(f"{CRYPTO_EMOJIS.get(symbol, '')} {label}", style={'flex': '0 0 160px', 'paddingLeft': '5px', 'fontWeight': 'bold'}),
        html.Div([html.Span(price_str), html.Span(f" ({change_24h:.2f}%)" if change_24h else "", style={'color': change_color, 'fontSize': '0.9em'})], style={'flex': '0 0 140px', 'textAlign': 'right', 'fontWeight': 'bold'}),
        html.Div(format_change(percent_data.get('1h')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('3h')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('24h')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('7d')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_trade_value_display(trade_value), style={'flex': '0 0 80px', 'textAlign': 'right', 'fontWeight': 'bold', 'paddingRight': '5px'}),
    ])

def create_selected_coin_box(label, symbol, price, currency, base_price_eur, high_eur, low_eur, percent_data, trade_value, individual_trends, diff_24h_eur):
    coin_emoji = CRYPTO_EMOJIS.get(symbol, '')
    price_color = '#28a745' if percent_data.get('24h', 0) > 0 else '#dc3545'
    
    mult = base_price_eur if currency == 'SEK' else (1/base_price_eur if currency in COINS_SYMBOLS else 1)
    high_display = high_eur * mult if high_eur else None
    low_display = low_eur * mult if low_eur else None

    return html.Div(style={'border': '2px solid #0056b3', 'borderRadius': '10px', 'padding': '15px', 'backgroundColor': '#f8f9fa', 'display': 'flex', 'justifyContent': 'space-around', 'flexWrap': 'wrap'}, children=[
        html.Div(style={'textAlign': 'center'}, children=[
            html.H2(f"{coin_emoji} {label} ({symbol})"),
            html.P(f"{format_price_display(price)} {currency}", style={'fontSize': '2.5em', 'fontWeight': '800', 'color': price_color, 'margin': '0'}),
            html.P(f"Handelsvärde: {trade_value:,.2f}" if trade_value else "", style={'fontSize': '1.5em', 'fontWeight': 'bold', 'color': '#0056b3'})
        ]),
        html.Div(children=[
            html.P(f"Hög 24h: {format_price_display(high_display)}", style={'color': 'green'}),
            html.P(f"Låg 24h: {format_price_display(low_display)}", style={'color': 'red'}),
            html.P([html.Span("1h: "), format_change(percent_data.get('1h'))]),
            html.P([html.Span("24h: "), format_change(percent_data.get('24h'))]),
            html.P([html.Span("7d: "), format_change(percent_data.get('7d'))]),
        ])
    ])

app.layout = html.Div(style={'backgroundColor': '#f8f9fa', 'padding': '20px'}, children=[
    html.H1('📈 DJ-Investment Dashboard', style={'textAlign': 'center', 'color': '#0056b3'}),
    
    html.Div(style={'display': 'flex', 'gap': '20px', 'flexWrap': 'wrap'}, children=[
        html.Div(style={'flex': '0 0 250px'}, children=[
            html.Label("Välj valuta:"),
            dcc.Dropdown(id='coin-dropdown', options=[{'label': k, 'value': k.split(' ')[0]} for k in COINS_LABELS], value=DEFAULT_COIN_SYMBOL),
            html.Label("Basvaluta:"),
            dcc.Dropdown(id='currency-dropdown', options=[{'label': c, 'value': c} for c in BASE_CURRENCIES], value='EUR'),
            # Tillägg: Väljare för 24h eller 7d
            html.Label("Tidsfönster i graf:"),
            dcc.RadioItems(id='timespan-selector', options=[{'label': ' 24h (5m)', 'value': '24h'}, {'label': ' 7d (15m)', 'value': '7d'}], value='24h'),
        ]),
        html.Div(style={'flex': '1'}, children=[
            html.Div(id='current-price-summary-box-container'),
            dcc.Graph(id='live-update-graph'),
        ])
    ]),
    
    html.Div(id='crypto-summary', style={'marginTop': '20px'}),
    
    dcc.Store(id='table-sort-store', data={'key': 'sort_tv', 'asc': False}),
    dcc.Interval(id='interval-component', interval=UPDATE_INTERVAL_SECONDS_DATA*1000)
])

@app.callback(
    Output('table-sort-store', 'data'),
    Input({'type': 'sort-header', 'index': ALL}, 'n_clicks'),
    State('table-sort-store', 'data'),
    prevent_initial_call=True
)
def update_sort(n, current):
    if not ctx.triggered_id: return current
    key = ctx.triggered_id['index']
    return {'key': key, 'asc': not current['asc'] if key == current['key'] else False}

@app.callback(
    [Output('current-price-summary-box-container', 'children'), 
     Output('crypto-summary', 'children'),
     Output('live-update-graph', 'figure')],
    [Input('interval-component', 'n_intervals'), 
     Input('coin-dropdown', 'value'), 
     Input('currency-dropdown', 'value'),
     Input('table-sort-store', 'data'),
     Input('timespan-selector', 'value')] # Inkludera timespan-selector i input
)
def update_ui(n, coin_symbol, currency, sort, timespan):
    data = get_data_from_redis()
    if not data: return html.Div("Laddar..."), html.Div("Laddar..."), go.Figure()

    eur_to_sek = data.get('EUR_SEK_RATE', 11.0)
    base_price_eur = eur_to_sek if currency == 'SEK' else (data.get(f'{currency}/EUR', 1.0) if currency in COINS_SYMBOLS else 1.0)
    
    # Förbered sammanfattning
    summary_list = []
    for label in COINS_LABELS:
        s = label.split(' ')[0]
        ticker = CRYPTO_PAIRS[label]
        pe = data.get(f'{s}/EUR')
        pd = data.get('ALL_PERCENT_CHANGE', {}).get(s, {})
        
        # Beräkna Handelsvärde
        h5 = json.loads(r.get(f'OHLC_CACHED_5MIN_{ticker}') or '[]') if r else []
        h1 = json.loads(r.get(f'OHLC_1DAY_{ticker}') or '[]') if r else []
        tv, trends = calculate_trade_value(h5, pe, h1)
        
        pb = pe * base_price_eur if currency == 'SEK' else (pe / base_price_eur if pe and base_price_eur else pe)
        
        summary_list.append({
            'symbol': s, 'label': label, 'price': pb, 'percent': pd, 'trade_value': tv,
            'sort_tv': tv if tv else -999, 'sort_price': pb if pb else -999
        })

    summary_list.sort(key=lambda x: x.get(sort['key'], 0), reverse=not sort['asc'])
    
    # Skapa rader
    header = html.Div(style={'display': 'flex', 'fontWeight': 'bold', 'backgroundColor': '#eee', 'padding': '5px'}, children=[
        html.Div("Valuta", style={'flex': '0 0 160px'}),
        html.Div("Pris", style={'flex': '0 0 140px', 'textAlign': 'right'}),
        html.Div("1h", style={'flex': '1', 'textAlign': 'right'}),
        html.Div("3h", style={'flex': '1', 'textAlign': 'right'}),
        html.Div("24h", style={'flex': '1', 'textAlign': 'right'}),
        html.Div("7d", style={'flex': '1', 'textAlign': 'right'}),
        html.Div("H.V.", id={'type': 'sort-header', 'index': 'sort_tv'}, style={'flex': '0 0 80px', 'textAlign': 'right', 'cursor': 'pointer'})
    ])
    
    rows = [create_summary_row(i['symbol'], i['label'], i['price'], i['percent'], i['trade_value'], currency, i['symbol']==coin_symbol) for i in summary_list]
    
    # Skapa Graf
    ticker = CRYPTO_PAIRS[SYMBOL_TO_LABEL[coin_symbol]]
    # Välj rätt data baserat på växlaren
    interval_val = 5 if timespan == '24h' else 15 # Logik för att välja 5 eller 15 min
    ohlc_raw = r.get(f'OHLC_CACHED_{interval_val}MIN_{ticker}') if r else None
    hist_data = json.loads(ohlc_raw) if ohlc_raw else []
    
    fig = go.Figure()
    if hist_data:
        x = [time.strftime('%m-%d %H:%M', time.gmtime(i['time']+3600)) for i in hist_data]
        y_eur = [i['price'] for i in hist_data]
        
        mult = base_price_eur if currency == 'SEK' else (1/base_price_eur if currency in COINS_SYMBOLS else 1)
        y = [p * mult for p in y_eur]
        
        fig.add_trace(go.Scatter(x=x, y=y, name="Pris", line=dict(color='#0056b3')))
        
        # Rita ut trendlinjer om 24h är valt
        if timespan == '24h':
            for k, conf in TREND_WINDOWS.items():
                if conf.get('show_line') and conf.get('source') == '5min':
                    slope, intercept, start = calculate_trendline(hist_data, conf['blocks'])
                    if slope:
                        ty = (slope * np.arange(conf['blocks']) + intercept) * mult
                        fig.add_trace(go.Scatter(x=x[start:], y=ty, name=conf['name'], line=dict(dash='dash', width=1)))

    fig.update_layout(title=f"{coin_symbol} - {timespan}", template="plotly_white", height=400)

    selected_info = next(i for i in summary_list if i['symbol'] == coin_symbol)
    range_data = data.get('ALL_24H_RANGE_OHLC', {}).get(coin_symbol, {})
    
    box = create_selected_coin_box(selected_info['label'], coin_symbol, selected_info['price'], currency, base_price_eur, range_data.get('high_eur'), range_data.get('low_eur'), selected_info['percent'], selected_info['trade_value'], {}, 0)

    return box, html.Div([header] + rows), fig

@app.callback(
    Output('coin-dropdown', 'value'),
    Input({'type': 'summary-card', 'index': ALL}, 'n_clicks'),
    prevent_initial_call=True
)
def click_coin(n):
    if not any(n) or not ctx.triggered_id: return dash.no_update
    return ctx.triggered_id['index']

if __name__ == '__main__':
    app.run_server(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 8050)))