import dash
from dash import dcc, html, dash_table, ctx, ALL
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

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

# [KONSTANTER]
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
KRAKEN_TICKER_API_URL = "https://api.kraken.com/0/public/Ticker"
KRAKEN_OHLC_API_URL = "https://api.kraken.com/0/public/OHLC"
EXCHANGE_RATE_URL = "https://api.exchangerate-api.com/v4/latest/EUR"

# URL för logotyper
LOGO_BASE_URL = "https://assets.coincap.io/assets/icons/"

# Färgteman
THEMES = {
    'light': {
        'bg': '#f8f9fa',
        'container_bg': 'white',
        'text': '#495057',
        'text_header': '#0056b3',
        'border': '#dee2e6',
        'graph_template': 'plotly_white',
        'table_header': '#f0f0f0',
        'table_cell': 'white',
        'dropdown_bg': 'white',
        'dropdown_text': '#333'
    },
    'dark': {
        'bg': '#121212',
        'container_bg': '#1e1e1e',
        'text': '#e0e0e0',
        'text_header': '#90caf9',
        'border': '#333333',
        'graph_template': 'plotly_dark',
        'table_header': '#2c2c2c',
        'table_cell': '#1e1e1e',
        'dropdown_bg': '#2c2c2c',
        'dropdown_text': '#e0e0e0'
    }
}

LOGO_OVERRIDES = {
    'GRASS': 'https://cryptologos.cc/logos/grass-grass-logo.png',
    'WIF': 'https://s2.coinmarketcap.com/static/img/coins/64x64/28752.png',
    'PEPE': 'https://assets.coincap.io/assets/icons/pepe@2x.png',
    'PUMP': 'https://s2.coinmarketcap.com/static/img/coins/64x64/29272.png',
    'TRUMP': 'https://s2.coinmarketcap.com/static/img/coins/64x64/31535.png',
    'DOGE': 'https://assets.coincap.io/assets/icons/doge@2x.png',
    'SOL': 'https://assets.coincap.io/assets/icons/sol@2x.png',
    'XRP': 'https://assets.coincap.io/assets/icons/xrp@2x.png',
    'BTC': 'https://assets.coincap.io/assets/icons/btc@2x.png',
    'ETH': 'https://assets.coincap.io/assets/icons/eth@2x.png',
}

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
    'MYX (MYX Finance)': 'MYX/EUR', 'GNO (Gnosis)': 'GNO/EUR', 'KOBAN (Lucky Kat)': 'KOBAN/EUR',
    'LINK (Chainlink)': 'LINK/EUR', 'XLM (Lumen)': 'XLM/EUR', 'HBAR (Hedera)': 'HBAR/EUR', 'TON (Toncoin)': 'TON/EUR',
    'AAVE (Aave)': 'AAVE/EUR', 'ONDO (Ondo)': 'ONDO/EUR', 'QNT (Quant)': 'QNT/EUR', 'RENDER (Render)': 'RENDER/EUR',
    'ALMANAK (Almanak)': 'ALMANAK/EUR', 'NOBODY (Nobody Sausage)': 'NOBODY/EUR',
}

DEFAULT_PAIR_KEY = 'XRP (Ripple)'
DEFAULT_COIN_SYMBOL = DEFAULT_PAIR_KEY.split(' ')[0]

COINS_LABELS = list(CRYPTO_PAIRS.keys())
COINS_SYMBOLS = [label.split(' ')[0] for label in COINS_LABELS]

BASE_CURRENCIES = ['EUR', 'SEK', 'USD'] + [s for s in COINS_SYMBOLS]
SYMBOL_TO_LABEL = {label.split(' ')[0]: label for label in COINS_LABELS}

# --- UPPDATERINGSINTERVALL ---
UPDATE_INTERVAL_FAST = 10   
UPDATE_INTERVAL_SLOW = 120  
OHLC_FETCH_INTERVAL_SECONDS = 120
OHLC_CACHE_INTERVAL_MIN = 5

SUMMARY_SCHEDULE_HOURS = [7, 9, 12, 15, 18, 21]
REDIS_SUMMARY_KEY = 'summary_last_sent_time'

TIME_WINDOWS = {
    '30m': {'blocks': 6, 'interval': OHLC_CACHE_INTERVAL_MIN},
    '1h': {'blocks': 12, 'interval': OHLC_CACHE_INTERVAL_MIN},
    '3h': {'blocks': 36, 'interval': OHLC_CACHE_INTERVAL_MIN},
    '6h': {'blocks': 72, 'interval': OHLC_CACHE_INTERVAL_MIN},
    '12h': {'blocks': 144, 'interval': OHLC_CACHE_INTERVAL_MIN},
    '18h': {'blocks': 216, 'interval': OHLC_CACHE_INTERVAL_MIN},
    '24h': {'blocks': 288, 'interval': OHLC_CACHE_INTERVAL_MIN},
    '7d': {'blocks': 7, 'interval': 1440},
    '30d': {'blocks': 30, 'interval': 1440},
    '6m': {'blocks': 180, 'interval': 1440},
    '1y': {'blocks': 365, 'interval': 1440},
}

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
    'EXCHANGE_RATES': {'SEK': 11.0, 'USD': 1.05}, 
    'ALL_24H_RANGE_OHLC': {'XRP': {'high_eur': 0.52, 'low_eur': 0.48}},
    'ALL_OHLC_CACHED': {},
    'ALL_PERCENT_CHANGE': {},
}

# --- Hjälpfunktioner ---

def get_logo_url(symbol):
    """Genererar URL för officiell logotyp med fallback."""
    s_upper = symbol.upper()
    if s_upper in LOGO_OVERRIDES:
        return LOGO_OVERRIDES[s_upper]
    return f"{LOGO_BASE_URL}{symbol.lower()}@2x.png"

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
            logger.error(f"Redis-anslutningsfel i callback: {e}")
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

    return trade_value if trade_value is not None else None, individual_trends

def format_summary_for_telegram(data, eur_to_sek, timezone_offset_hours):
    summary_data = []
    ohlc_interval = OHLC_CACHE_INTERVAL_MIN

    for label in COINS_LABELS:
        coin_symbol_loop = label.split(' ')[0]
        ticker = CRYPTO_PAIRS[label]
        price_eur = data.get(f'{coin_symbol_loop}/EUR')
        percent_data_loop = data.get('ALL_PERCENT_CHANGE', {}).get(coin_symbol_loop, {})
        
        ohlc_cache_key = f'OHLC_CACHED_{ohlc_interval}MIN_{ticker}'
        hist_data_5min_json = r.get(ohlc_cache_key) if r else None
        hist_data_5min = json.loads(hist_data_5min_json) if hist_data_5min_json else []

        ohlc_1day_key = f'OHLC_1DAY_{ticker}'
        hist_data_1day_json = r.get(ohlc_1day_key) if r else None
        hist_data_1day = json.loads(hist_data_1day_json) if hist_data_1day_json else []
        
        trade_value_int = None
        if hist_data_5min and price_eur is not None:
            h_5min = hist_data_5min.copy()
            h_5min.append({'time': data.get('timestamp', time.time()), 'price': price_eur})
            h_1day = hist_data_1day.copy()
            h_1day.append({'time': data.get('timestamp', time.time()), 'price': price_eur})
            
            trade_value, _ = calculate_trade_value(h_5min, price_eur, h_1day)
            if trade_value is not None:
                trade_value_int = int(round(trade_value))

        sort_key_3h = percent_data_loop.get('3h') if percent_data_loop.get('3h') is not None else -float('inf')
        sort_key_24h = percent_data_loop.get('24h') if percent_data_loop.get('24h') is not None else -float('inf')
        sort_trade_value = trade_value_int if trade_value_int is not None else -float('inf')

        summary_data.append({
            'symbol': coin_symbol_loop,
            'price_eur': price_eur,
            'percent_data': percent_data_loop,
            'trade_value_int': trade_value_int, 
            'sort_trade_value': sort_trade_value, 
            'sort_3h': sort_key_3h,
            'sort_24h': sort_key_24h
        })

    summary_data.sort(key=lambda x: (x['sort_24h'], x['sort_3h'], x['sort_trade_value']), reverse=True)
    
    now_utc = datetime.now(timezone.utc)
    offset = 1 
    if now_utc.month in range(4, 10): 
        offset = 2 
    elif now_utc.month == 3 and now_utc.day > 24 and now_utc.weekday() == 6:
        offset = 2
    elif now_utc.month == 10 and now_utc.day > 24 and now_utc.weekday() == 6:
        offset = 1 
    
    now_local = now_utc + timedelta(hours=offset)
    
    header = (
        f"🌟 **MARKNADSSAMMANFATTNING** 🌟\n"
        f"Tid: *{now_local.strftime('%Y-%m-%d %H:%M:%S')} CET/CEST*\n\n"
        f"Sorterad efter 24h, 3h sedan Handelsvärde."
    )
    
    table_header = (
        "```"
        "KRYPTO | PRIS EUR |  3H   |  24H  | H.V.\n"
        "-----------------------------------------\n"
    )
    
    table_rows = []
    for item in summary_data:
        symbol = item['symbol'].ljust(6)
        
        price_str = format_price_telegram(item['price_eur'])
        price_display = price_str.rjust(8) 

        change_3h = format_change_telegram(item['percent_data'].get('3h'))
        change_24h = format_change_telegram(item['percent_data'].get('24h'))
        
        trade_value_str = format_trade_value_telegram(item['trade_value_int']) 
        
        row = f"{symbol} | {price_display} |{change_3h} |{change_24h} |{trade_value_str}"
        table_rows.append(row)

    table_body = "\n".join(table_rows)
    table_footer = "```"
    return header + table_header + table_body + table_footer

def fetch_exchange_rate():
    try:
        response = requests.get(EXCHANGE_RATE_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        return {
            'SEK': data['rates'].get('SEK', 11.0),
            'USD': data['rates'].get('USD', 1.05)
        }
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching exchange rate: {e}. Using fallback.")
        return {'SEK': 11.0, 'USD': 1.05}

def fetch_crypto_data():
    try:
        t = time.time()
        rates = fetch_exchange_rate()
        kraken_tickers = ','.join(CRYPTO_PAIRS.values())
        response = requests.get(KRAKEN_TICKER_API_URL, params={'pair': kraken_tickers}, timeout=15)
        response.raise_for_status()
        kraken_data = response.json()

        if kraken_data.get('error'):
            logger.error(f"Kraken API error: {kraken_data['error']}")
            return DEFAULT_DATA

        result_key = kraken_data.get('result', {})
        current_data = {
            'timestamp': t, 
            'EXCHANGE_RATES': rates,
            'ALL_PERCENT_CHANGE': {}, 
            'ALL_OHLC_CACHED': {}, 
            'ALL_24H_RANGE_OHLC': {}
        }
        
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
                
            except (ValueError, IndexError, TypeError) as e:
                logger.warning(f"Failed to parse Ticker data for {ticker}: {e}")
            
        return current_data if len(current_data) > 4 else DEFAULT_DATA
    except Exception as e:
        logger.error(f"❌ Error fetching/processing ticker data: {e}")
        return DEFAULT_DATA 

# --- Del 2 Start ---

def fetch_ohlc_data_from_kraken(kraken_ticker, interval, periods_ago_seconds):
    time_ago = int(time.time()) - periods_ago_seconds 
    params = { 'pair': kraken_ticker, 'interval': interval, 'since': time_ago }
    try:
        response = requests.get(KRAKEN_OHLC_API_URL, params=params, timeout=15)
        response.raise_for_status()
        ohlc_data = response.json()
        if ohlc_data.get('error'):
            return []
        result_key = next(iter(ohlc_data['result'])) 
        data_list = ohlc_data['result'][result_key]
        
        # Spara Open, High, Low, Close för Candlesticks
        return [{
            'time': int(row[0]),
            'price': float(row[4]), # Fortfarande 'price' (Close) för bakåtkompatibilitet
            'open': float(row[1]),
            'high': float(row[2]),
            'low': float(row[3]),
            'close': float(row[4])
        } for row in data_list]
    except Exception as e:
        logger.error(f"Error fetching OHLC data for {kraken_ticker}: {e}")
        return []

def calculate_percentage_changes(ohlc_data, current_price, periods):
    changes = {}
    if not ohlc_data or current_price is None or current_price == 0:
        return {key: None for key in periods}

    for period, config in periods.items():
        if period not in TIME_WINDOWS: continue
        blocks = config['blocks']
        if len(ohlc_data) >= blocks:
            reference_price = ohlc_data[-blocks]['price']
            if reference_price > 0:
                changes[period] = ((current_price - reference_price) / reference_price) * 100
            else:
                changes[period] = None 
        else:
            changes[period] = None
    return changes

def calculate_trendline(historical_data, blocks):
    if len(historical_data) < blocks:
        return None, None, None
    data_segment = historical_data[-blocks:]
    x_values = np.arange(blocks) 
    y_values = np.array([item['price'] for item in data_segment])
    slope, intercept, r_value, p_value, std_err = linregress(x_values, y_values)
    start_index_global = len(historical_data) - blocks 
    return slope, intercept, start_index_global

def format_change(c):
    if c is None: return html.Span("N/A", style={'color': '#6c757d'})
    if abs(c) < 0.01: return html.Span("0.00%", style={'color': '#6c757d', 'fontWeight': 'bold'})
    color = '#28a745' if c > 0 else '#dc3545' 
    symbol = '▲' if c > 0 else '▼'
    return html.Span(f"{symbol} {abs(c):.2f}%", style={'color': color, 'fontWeight': 'bold', 'fontSize': '0.85em'})

def format_trade_value_display(v):
    if v is None: return html.Span("N/A", style={'color': '#6c757d'})
    val = int(round(v))
    if val == 0: return html.Span("0", style={'color': '#6c757d', 'fontWeight': 'bold'})
    color = '#006400' if val > 0 else '#8B0000' 
    symbol = '▲' if val > 0 else '▼'
    return html.Span(f"{symbol} {abs(val)}", style={'color': color, 'fontWeight': 'bold', 'fontSize': '0.85em'})

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}, timeout=10)
        return True
    except Exception as e:
        logger.error(f"Kunde inte skicka Telegram-meddelande: {e}")
        return False

def check_and_send_trade_value_alerts(alert_data, r_instance):
    if not r_instance: return
    for coin_symbol, data in alert_data.items():
        trade_value = data.get('trade_value')
        current_price_eur = data.get('price_eur')
        if trade_value is None or current_price_eur is None: continue
        
        if trade_value > 0:
            highest_threshold_met = None
            for threshold in TRADE_VALUE_ALERTS:
                if trade_value >= threshold:
                    highest_threshold_met = threshold
                    break
            
            if highest_threshold_met is not None:
                key = f"tv_alert:{coin_symbol}:+{highest_threshold_met}"
                if r_instance.set(key, 1, ex=TRADE_VALUE_DEBOUNCE_SECONDS, nx=True):
                    coin_label = SYMBOL_TO_LABEL.get(coin_symbol, coin_symbol)
                    msg = (f"🔥 **HÖGT HANDELSVÄRDE** 🔥\n"
                           f"Valuta: *{coin_label} ({coin_symbol})*\n"
                           f"Aktuellt Pris: *{format_price_telegram(current_price_eur)} EUR*\n"
                           f"Handelsvärde ($H.V.$): **+{trade_value}** (Tröskel: +{highest_threshold_met})")
                    send_telegram_message(msg)
                    logger.info(f"Telegram TV Alert skickad: {coin_symbol} HÖGT +{highest_threshold_met}")

def check_and_send_alerts(alert_data, r_instance):
    if not r_instance: return
    for coin_symbol, data in alert_data.items():
        changes = data['changes']
        current_price_eur = data['price_eur']
        if current_price_eur is None: continue
        
        for period in ALERT_PERIODS:
            change_percent = changes.get(period)
            if change_percent is None: continue
            
            coin_label = SYMBOL_TO_LABEL.get(coin_symbol, coin_symbol)
            formatted_price = format_price_telegram(current_price_eur)
            
            if change_percent > 0:
                threshold = next((t for t in ALERT_THRESHOLDS_UP if change_percent >= t), None)
                if threshold is not None:
                    key = f"alert:{coin_symbol}:+{period}:{threshold}"
                    if r_instance.set(key, 1, ex=ALERT_DEBOUNCE_SECONDS, nx=True):
                        msg = (f"🚀 **HÖG PRISUPPGÅNG** 🚀\nValuta: *{coin_label}*\nPris: *{formatted_price} EUR*\nRörelse: *+{change_percent:.2f}%* ({period})")
                        send_telegram_message(msg)
                        logger.info(f"Telegram Alert: {coin_symbol} +{threshold}% ({period})")
            elif change_percent < 0:
                threshold = next((t for t in ALERT_THRESHOLDS_DOWN if change_percent <= t), None)
                if threshold is not None:
                    key = f"alert:{coin_symbol}:{period}:{threshold}"
                    if r_instance.set(key, 1, ex=ALERT_DEBOUNCE_SECONDS, nx=True):
                        msg = (f"🔻 **HÖG PRISNEDGÅNG** 🔻\nValuta: *{coin_label}*\nPris: *{formatted_price} EUR*\nRörelse: *{change_percent:.2f}%* ({period})")
                        send_telegram_message(msg)
                        logger.info(f"Telegram Alert: {coin_symbol} {threshold}% ({period})")


# ==========================================
# NYA FUNKTIONER FÖR KÖP/SÄLJ-SIGNALER (RSI 80/20)
# ==========================================
def calculate_rsi(ohlc_data, periods=14):
    """Räknar ut Relative Strength Index (RSI) med ren Python-matematik"""
    if not ohlc_data or len(ohlc_data) < periods + 1:
        return None

    # Hämta stängningspriserna
    prices = [float(item['close']) for item in ohlc_data]
    
    gains = []
    losses = []
    
    # Räkna ut prisförändringar
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
            
    # Vi fokuserar bara på de senaste perioderna (vanligtvis 14)
    gains = gains[-periods:]
    losses = losses[-periods:]
    
    avg_gain = sum(gains) / periods
    avg_loss = sum(losses) / periods
    
    if avg_loss == 0:
        return 100.0 # Priset har bara gått upp, RSI slår i taket
        
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return round(rsi, 2)

def check_rsi_alerts(coin_symbol, current_price_eur, ohlc_data, r_instance):
    """Kollar om valutan är överköpt (>80) eller översåld (<20)"""
    rsi_value = calculate_rsi(ohlc_data, periods=14)
    if rsi_value is None:
        return

    state_key = f"rsi_state:{coin_symbol}"
    previous_state = r_instance.get(state_key) if r_instance else None
    if previous_state:
        previous_state = previous_state.decode('utf-8')
    
    # Bestäm nuvarande tillstånd baserat på dina 80/20-gränser
    current_state = "neutral"
    if rsi_value >= 80:
        current_state = "overbought"
    elif rsi_value <= 20:
        current_state = "oversold"
        
    # Larma BARA om vi går från neutral/motsatt in i en NY extrem-zon
    if previous_state != current_state:
        coin_label = SYMBOL_TO_LABEL.get(coin_symbol, coin_symbol)
        
        if current_state == "oversold":
            msg = f"🟢 **KÖPSIGNAL (RSI)** 🟢\nValuta: *{coin_label}*\nPris: *{format_price_telegram(current_price_eur)} EUR*\nStatus: *Översåld (RSI: {rsi_value})* - Priset har fallit kraftigt och en vändning uppåt är möjlig."
            send_telegram_message(msg)
            logger.info(f"RSI Alert skickad: {coin_symbol} KÖP (RSI {rsi_value})")
            
        elif current_state == "overbought":
            msg = f"🔴 **SÄLJSIGNAL (RSI)** 🔴\nValuta: *{coin_label}*\nPris: *{format_price_telegram(current_price_eur)} EUR*\nStatus: *Överköpt (RSI: {rsi_value})* - Priset har rusat kraftigt och en rekyl nedåt är möjlig."
            send_telegram_message(msg)
            logger.info(f"RSI Alert skickad: {coin_symbol} SÄLJ (RSI {rsi_value})")
    
    # Spara tillståndet så vi inte larmar igen förrän trenden ändras
    if r_instance:
        r_instance.set(state_key, current_state)
# ==========================================




# --- Bakgrundstrådar ---

def background_data_fetch(redis_instance):
    last_ohlc_fetch_time = 0
    last_long_term_fetch = 0 
    
    while True:
        cycle_start_time = time.time()
        try:
            # 1. Hämta Priser (Tickers) - Varje cykel (10 sekunder)
            new_data = fetch_crypto_data()
            if not new_data or new_data == DEFAULT_DATA:
                time.sleep(UPDATE_INTERVAL_FAST)
                continue
            
            should_update_ohlc = (time.time() - last_ohlc_fetch_time) > OHLC_FETCH_INTERVAL_SECONDS
            fetch_extra_intervals = (time.time() - last_long_term_fetch) > 900 
            
            if should_update_ohlc:
                last_ohlc_fetch_time = time.time()
                logger.debug("⏳ Hämtar tung OHLC historik...")
            
            if fetch_extra_intervals:
                last_long_term_fetch = time.time()
                logger.debug("⏳ Hämtar 1v och 1mån data...")

            all_percent_changes = {}
            all_24h_range_ohlc = {} 
            alert_data_for_sending = {} 
            trade_value_alert_data = {} 

            for label, ticker in CRYPTO_PAIRS.items():
                coin_symbol = label.split(' ')[0]
                current_price_eur = new_data.get(f'{coin_symbol}/EUR')
                if current_price_eur is None: continue
                
                ohlc_5min_data = []
                ohlc_1day_data = []
                
                if should_update_ohlc:
                    periods_ago_24h = 86400 
                    ohlc_5min_data = fetch_ohlc_data_from_kraken(ticker, OHLC_CACHE_INTERVAL_MIN, periods_ago_24h) 
                    if ohlc_5min_data:
                         redis_instance.set(f'OHLC_CACHED_{OHLC_CACHE_INTERVAL_MIN}MIN_{ticker}', json.dumps(ohlc_5min_data), ex=7200)


# Aktivera vår RSI Köp/Sälj-algoritm live
                         check_rsi_alerts(coin_symbol, current_price_eur, ohlc_5min_data, redis_instance)


def background_summary_sender(redis_instance):
    while True:
        try:
            now_utc = datetime.now(timezone.utc)
            timezone_offset_hours = 1 
            if now_utc.month in range(4, 10): 
                timezone_offset_hours = 2 
            elif now_utc.month == 3 and now_utc.day > 24 and now_utc.weekday() == 6:
                timezone_offset_hours = 2
            elif now_utc.month == 10 and now_utc.day > 24 and now_utc.weekday() == 6: 
                timezone_offset_hours = 1 
            
            now_local = now_utc + timedelta(hours=timezone_offset_hours)
            
            if now_local.hour in SUMMARY_SCHEDULE_HOURS and now_local.minute == 0:
                debounce_key = f"{REDIS_SUMMARY_KEY}:{now_local.strftime('%Y%m%d_%H')}"
                if redis_instance and redis_instance.set(debounce_key, 1, ex=3600*1, nx=True): 
                    data = get_data_from_redis()
                    if data:
                        rates = data.get('EXCHANGE_RATES', {})
                        eur_to_sek = rates.get('SEK', 11.0)
                        msg = format_summary_for_telegram(data, eur_to_sek, timezone_offset_hours)
                        if send_telegram_message(msg): logger.info("✅ Sammanfattning skickad.")
            time.sleep(60)
        except Exception as e:
            logger.error(f"❌ Fel i schema-tråd: {e}")
            time.sleep(60)

if r:
    threading.Thread(target=background_data_fetch, args=(r,), daemon=True).start()
    threading.Thread(target=background_summary_sender, args=(r,), daemon=True).start()

# --- Helpers för Layout ---

def create_selected_coin_box(label, symbol, price, currency, base_price_eur, high_eur, low_eur, percent_data, trade_value=None, individual_trends=None, diff_24h_eur=None, theme='light'): 
    if individual_trends is None: individual_trends = {}
    colors = THEMES[theme]
        
    price_text = f"{format_price_display(price)} {currency}"
    # Logo istället för emoji (utan onError för att undvika Render-krasch)
    logo_img = html.Img(src=get_logo_url(symbol), style={'width': '35px', 'height': '35px', 'marginRight': '10px', 'verticalAlign': 'middle'})
    
    change_24h = percent_data.get('24h') 
    price_color = '#28a745' if change_24h and change_24h > 0 else '#dc3545' if change_24h and change_24h < 0 else colors['text']
    trade_value_color = '#006400' if trade_value and trade_value > 0 else '#8B0000' if trade_value and trade_value < 0 else colors['text']
    # Anpassa mörkgrön/mörkröd för dark mode om nödvändigt, annars fungerar standardfärgerna hyfsat
    if theme == 'dark':
        if trade_value and trade_value > 0: trade_value_color = '#4caf50'
        if trade_value and trade_value < 0: trade_value_color = '#ef5350'

    multiplier = 1
    high_display, low_display = None, None
    if high_eur is not None and low_eur is not None and base_price_eur:
        if currency == 'SEK' or currency == 'USD':
            multiplier = base_price_eur 
        elif currency == 'EUR':
            multiplier = 1
        elif base_price_eur and currency in COINS_SYMBOLS:
            multiplier = 1 / base_price_eur
        else:
            multiplier = 1 
            
        high_display = high_eur * multiplier
        low_display = low_eur * multiplier

    def create_change_row(period, value):
        display_name = {'7d': '7dgr', '30d': '30dgr', '6m': '6mån', '1y': '1år', '30m': '30min'}.get(period, period)
        return html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'margin': '3px 0', 'padding': '0 5px', 'fontSize': '0.9em'},
                        children=[html.Span(f"{display_name.capitalize()}:", style={'color': colors['text'], 'opacity': '0.7', 'flex': '0 0 50px'}), html.Div(value, style={'flex': '1', 'textAlign': 'right'})])
        
    short_term_keys = [k for k, v in TREND_WINDOWS.items() if v.get('source') == '5min']
    long_term_keys = [k for k, v in TREND_WINDOWS.items() if v.get('source') == '1day']

    diff_24h_base = None
    if diff_24h_eur is not None:
        if currency == 'SEK' or currency == 'USD':
            diff_24h_base = diff_24h_eur * (base_price_eur if base_price_eur else 1.0)
        elif currency == 'EUR':
            diff_24h_base = diff_24h_eur
        elif currency in COINS_SYMBOLS and base_price_eur:
            diff_24h_base = diff_24h_eur / base_price_eur 

    main_price_section = html.Div(style={'flex': '1 1 300px', 'minWidth': '300px', 'paddingRight': '15px'}, children=[
        html.H2([logo_img, html.Span(f"{label} ({symbol})")], style={'fontSize': '1.5em', 'color': colors['text_header'], 'marginBottom': '5px', 'textAlign': 'center', 'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center'}),
        
        html.Div(style={'textAlign': 'center', 'marginTop': '10px'}, children=[
            html.P("Nuvarande Pris", style={'margin': '0', 'color': colors['text'], 'opacity': '0.7', 'fontWeight': 'bold', 'fontSize': '0.9em'}),
            html.P(price_text, id='current-price-display', style={'fontSize': '2.5em', 'fontWeight': '800', 'color': price_color, 'margin': '0'}),
        ]),
        
        html.Div(style={'textAlign': 'center', 'fontSize': '0.9em', 'fontWeight': '600', 'color': price_color, 'margin': '0'}, children=[
            html.Span(f"({'+' if diff_24h_base >= 0 else ''}{diff_24h_base:,.4f} {currency}, ", style={'marginRight': '0px'}),
            format_change(change_24h), 
            html.Span(")")
        ] if diff_24h_base is not None else html.P("24h Diff: N/A", style={'fontSize': '0.8em', 'color': colors['text']})),

        html.Div(style={'textAlign': 'center', 'marginTop': '15px', 'padding': '5px 0', 'borderTop': f'1px solid {colors["border"]}'}, children=[
            html.P("Handelsvärde (Viktad Trendindikator)", style={'margin': '0', 'color': colors['text'], 'opacity': '0.7', 'fontWeight': 'bold', 'fontSize': '0.8em'}),
            html.P(f"{trade_value:,.2f}" if trade_value is not None else "N/A", style={'fontSize': '1.8em', 'fontWeight': '800', 'color': trade_value_color, 'margin': '0'})
        ])
    ])

    changes_section = html.Div(style={'flex': '1 1 250px', 'minWidth': '250px', 'padding': '0 15px', 'borderLeft': f'1px solid {colors["border"]}'}, children=[
        html.P("Prisrörelser (%) & 24h Intervall", style={'margin': '0 0 10px 0', 'color': colors['text'], 'fontWeight': 'bold', 'textAlign': 'center', 'fontSize': '0.9em'}),
        
        html.Div(style={'padding': '5px 0 10px 0', 'borderBottom': f'1px solid {colors["border"]}', 'fontSize': '0.9em'}, children=[
            html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'marginBottom': '5px'}, children=[
                html.Span("Hög 24h:", style={'fontWeight': 'bold', 'color': '#4caf50' if theme=='dark' else 'green'}), 
                html.Span(f"{format_price_display(high_display)} {currency}" if high_display is not None else "N/A", style={'color': '#4caf50' if theme=='dark' else 'green', 'fontWeight': '600'})
            ]),
            html.Div(style={'display': 'flex', 'justifyContent': 'space-between'}, children=[
                html.Span("Låg 24h:", style={'fontWeight': 'bold', 'color': '#ef5350' if theme=='dark' else 'red'}), 
                html.Span(f"{format_price_display(low_display)} {currency}" if low_display is not None else "N/A", style={'color': '#ef5350' if theme=='dark' else 'red', 'fontWeight': '600'})
            ]),
        ]),
        
        html.Div(style={'paddingTop': '10px', 'display': 'grid', 'gridTemplateColumns': '1fr 1fr', 'gap': '5px 10px'}, children=[
            create_change_row('30m', format_change(percent_data.get('30m'))),
            create_change_row('18h', format_change(percent_data.get('18h'))),
            create_change_row('1h', format_change(percent_data.get('1h'))),
            create_change_row('7d', format_change(percent_data.get('7d'))), 
            create_change_row('3h', format_change(percent_data.get('3h'))),
            create_change_row('30d', format_change(percent_data.get('30d'))),
            create_change_row('6h', format_change(percent_data.get('6h'))),
            create_change_row('6m', format_change(percent_data.get('6m'))),
            create_change_row('12h', format_change(percent_data.get('12h'))),
            create_change_row('1y', format_change(percent_data.get('1y'))),

        ])
    ])

    def render_trend_row(key):
        data_obj = individual_trends.get(key)
        val = None
        trend_price = None
        
        if isinstance(data_obj, dict):
            val = data_obj.get('val')
            raw_price = data_obj.get('price')
            if raw_price is not None:
                trend_price = raw_price * multiplier
        elif isinstance(data_obj, (int, float)):
            val = data_obj

        val_str = f"{val:,.2f}" if val is not None else "N/A"
        price_str = f" ({format_price_display(trend_price)})" if trend_price is not None else ""
        
        color = colors['text']
        if val is not None:
            if val > 0: color = '#4caf50' if theme=='dark' else '#006400'
            elif val < 0: color = '#ef5350' if theme=='dark' else '#8B0000'

        return html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'marginBottom': '3px'}, children=[
            html.Span(f"{TREND_WINDOWS[key]['name'].split(' ')[1]}:", style={'color': colors['text'], 'opacity': '0.7', 'fontWeight': 'bold'}), 
            html.Span(f"{val_str}{price_str}", style={'color': color, 'fontWeight': '600'})
        ])

    trend_section = html.Div(style={'flex': '1 1 200px', 'minWidth': '200px', 'paddingLeft': '15px', 'borderLeft': f'1px solid {colors["border"]}'}, children=[
        html.P("Trendvärden (Hₓ) - Riktning/Vikt", style={'margin': '0 0 10px 0', 'color': colors['text'], 'fontWeight': 'bold', 'textAlign': 'center', 'fontSize': '0.9em'}),
        
        html.P("Kort Sikt (5m data)", style={'margin': '0 0 5px 0', 'color': colors['text'], 'opacity': '0.7', 'fontSize': '0.8em', 'fontWeight': 'bold'}),
        html.Div([
            render_trend_row(key) for key in short_term_keys if key in individual_trends 
        ]),
        
        html.P("Lång Sikt (1d data)", style={'margin': '10px 0 5px 0', 'color': colors['text'], 'opacity': '0.7', 'fontSize': '0.8em', 'fontWeight': 'bold', 'borderTop': f'1px dotted {colors["border"]}', 'paddingTop': '5px'}),
        html.Div([
            render_trend_row(key) for key in long_term_keys if key in individual_trends 
        ]),
    ])

    return html.Div(id='current-price-box', style={'border': f'2px solid {colors["text_header"]}', 'borderRadius': '10px', 'padding': '15px', 'marginBottom': '20px', 'backgroundColor': colors['container_bg']}, children=[
            html.Div(style={'display': 'flex', 'justifyContent': 'space-around', 'alignItems': 'flex-start', 'flexWrap': 'wrap', 'gap': '10px'}, children=[
                main_price_section, 
                changes_section, 
                trend_section
            ])
        ])


# --- Dash App ---

app = dash.Dash(__name__, external_stylesheets=['https://codepen.io/chriddyp/cnWqWbL.css'])
server = app.server 

# Kolumndefinitioner för DataTable
TABLE_COLUMNS = [
    {"name": "Valuta", "id": "label", "presentation": "markdown"}, # Logo + Namn
    {"name": "Pris (24h%)", "id": "price", "type": "text"}, 
    {"name": "30m", "id": "30m", "type": "numeric", "format": {"specifier": "+.2f"}},
    {"name": "1h", "id": "1h", "type": "numeric", "format": {"specifier": "+.2f"}},
    {"name": "3h", "id": "3h", "type": "numeric", "format": {"specifier": "+.2f"}},
    {"name": "6h", "id": "6h", "type": "numeric", "format": {"specifier": "+.2f"}},
    {"name": "12h", "id": "12h", "type": "numeric", "format": {"specifier": "+.2f"}},
    {"name": "24h", "id": "24h", "type": "numeric", "format": {"specifier": "+.2f"}},
    {"name": "7d", "id": "7d", "type": "numeric", "format": {"specifier": "+.2f"}},
    {"name": "30d", "id": "30d", "type": "numeric", "format": {"specifier": "+.2f"}},
    {"name": "H.V.", "id": "trade_value", "type": "numeric", "format": {"specifier": "+d"}},
]

app.layout = html.Div(id='main-layout', style={'minHeight': '100vh', 'padding': '40px 10px', 'fontFamily': 'Roboto, Arial, sans-serif'}, children=[
    html.Div(id='content-container', style={'maxWidth': '1400px', 'margin': '40px auto', 'padding': '30px', 'borderRadius': '12px', 'boxShadow': '0 4px 12px rgba(0,0,0,0.1)', 'border': '1px solid #dee2e6'}, children=[
        html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center', 'marginBottom': '30px'}, children=[
            html.H1('📈 DJ-Investment Dashboard (Kraken Live)', style={'textAlign': 'center', 'color': '#0056b3', 'margin': '0', 'flex': '1'}),
            html.Div([
                dcc.Checklist(
                    id='theme-switch',
                    options=[{'label': ' Dark Mode', 'value': 'dark'}],
                    value=[],
                    inline=True,
                    inputStyle={"margin-right": "5px"}
                )
            ], style={'marginLeft': '20px'})
        ]),
        
        html.Div(style={'display': 'flex', 'gap': '20px', 'marginBottom': '20px', 'flexWrap': 'wrap'}, children=[
            html.Div(style={'flex': '0 0 200px', 'minWidth': '200px'}, children=[
                html.H3('⚙️ Kontroller', id='controls-header', style={'fontSize': '1.3em', 'marginBottom': '15px'}),
                html.Div(style={'marginBottom': '20px'}, children=[
                    html.Label("Välj kryptovaluta:", style={'marginBottom': '5px', 'fontWeight': 'bold', 'display': 'block'}),
                    dcc.Dropdown(id='coin-dropdown', options=[{'label': label, 'value': label.split(' ')[0]} for label in COINS_LABELS], value=DEFAULT_COIN_SYMBOL, clearable=False),
                ]),
                html.Div(children=[
                    html.Label("Välj basvaluta/krypto:", style={'marginBottom': '5px', 'fontWeight': 'bold', 'display': 'block'}),
                    dcc.Dropdown(id='currency-dropdown', options=[{'label': f'{c} ({c})', 'value': c} for c in BASE_CURRENCIES], value='EUR', clearable=False),
                ]),
            ]),
            html.Div(style={'flex': '1 1 600px', 'minWidth': '600px'}, children=[
                html.Div(id='current-price-summary-box-container'),
                html.Div(id='last-updated', style={'textAlign': 'center', 'fontSize': '0.9em', 'marginBottom': '0px'}),
            ]),
            dcc.Store(id='chart-data-store'), 
            dcc.Store(id='current-currency-store'),
            dcc.Store(id='initial-coin-symbol-store', data=DEFAULT_COIN_SYMBOL),
        ]),
        
        html.Div(style={'paddingTop': '20px', 'borderTop': '1px solid #dee2e6', 'marginBottom': '30px'}, children=[
            html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center', 'marginBottom': '10px'}, children=[
                html.Div(style={'display': 'flex', 'alignItems': 'center'}, children=[
                     html.Label("Visa Trendlinjer:", style={'fontWeight': 'bold', 'marginRight': '15px', 'fontSize': '0.9em'}),
                     dcc.Checklist(
                         id='trendline-checkboxes',
                         options=[{'label': config['name'].split(' ')[1].replace('(', '').replace(')', ''), 'value': key} for key, config in TREND_WINDOWS.items() if config.get('show_line')],
                         value=[k for k, v in TREND_WINDOWS.items() if v.get('show_line')], 
                         inline=True,
                         style={'display': 'inline-block'}
                     ),
                ]),
                html.Div(style={'display': 'flex', 'alignItems': 'center'}, children=[
                     html.Label("Candle (Live):", style={'fontWeight': 'bold', 'marginRight': '5px', 'fontSize': '0.9em'}),
                     dcc.Dropdown(
                        id='live-candle-interval',
                        options=[
                            {'label': '15 min', 'value': 15},
                            {'label': '30 min', 'value': 30},
                            {'label': '1 timme', 'value': 60}
                        ],
                        value=15,
                        clearable=False,
                        style={'width': '100px', 'marginRight': '20px'}
                     ),
                     html.Label("Graf Tidsintervall:", style={'fontWeight': 'bold', 'marginRight': '10px', 'fontSize': '0.9em'}),
                     dcc.RadioItems(
                        id='graph-timeframe',
                        options=[
                            {'label': ' 4 Timmar (Live)', 'value': '4h_live'},
                            {'label': ' 1 Dag (5m)', 'value': '1d'},
                            {'label': ' 1 Vecka (15m)', 'value': '1w'},
                            {'label': ' 1 Månad (60m)', 'value': '1m'}
                        ],
                        value='1d',
                        inline=True,
                        labelStyle={'marginRight': '15px', 'cursor': 'pointer'}
                     )
                ])
            ]),
            dcc.Loading(id="loading-1", type="circle", children=[dcc.Graph(id='live-update-graph', config={'displayModeBar': False})]),
        ]),
        
        html.Div(id='crypto-summary-container', style={'marginTop': '30px', 'paddingTop': '20px', 'borderTop': '1px solid #dee2e6', 'marginBottom': '30px'}, children=[
             html.H3('📊 Sammanfattning: Handelsvärde & Prisrörelser', id='summary-header', style={'fontSize': '1.3em', 'marginBottom': '10px'}),
             dcc.Loading(id="loading-2", type="dot", children=[
                 dash_table.DataTable(
                     id='crypto-table',
                     columns=TABLE_COLUMNS,
                     data=[], # Fylls av callback
                     sort_action="native",
                     sort_mode="single",
                     sort_by=[{'column_id': '24h', 'direction': 'desc'}], # STANDARDSORTERING PÅ 24h
                     style_table={'overflowX': 'auto'},
                     style_cell={
                         'textAlign': 'right',
                         'padding': '10px',
                         'fontFamily': 'Roboto, Arial, sans-serif',
                         'fontSize': '0.9em'
                     },
                     style_header={
                         'fontWeight': 'bold',
                         'borderBottom': '2px solid #0056b3'
                     },
                     style_cell_conditional=[
                         {'if': {'column_id': 'label'}, 'textAlign': 'left'},
                         {'if': {'column_id': 'price'}, 'fontWeight': 'bold'}
                     ],
                     style_data_conditional=[
                         # Färga procent-kolumner (Grön om > 0, Röd om < 0)
                         {
                             'if': {'filter_query': f'{{{col}}} > 0', 'column_id': col},
                             'color': '#28a745', 'fontWeight': 'bold'
                         } for col in ['30m', '1h', '3h', '6h', '12h', '24h', '7d', '30d', 'trade_value']
                     ] + [
                         {
                             'if': {'filter_query': f'{{{col}}} < 0', 'column_id': col},
                             'color': '#dc3545', 'fontWeight': 'bold'
                         } for col in ['30m', '1h', '3h', '6h', '12h', '24h', '7d', '30d', 'trade_value']
                     ] + [
                         # Färga PRIS baserat på 24h utveckling (Kräver att vi har 24h data i raden)
                         {
                             'if': {'filter_query': '{24h} > 0', 'column_id': 'price'},
                             'color': '#28a745'
                         },
                         {
                             'if': {'filter_query': '{24h} < 0', 'column_id': 'price'},
                             'color': '#dc3545'
                         }
                     ],
                     markdown_options={'html': True} # Tillåt bilder i markdown
                 )
             ])
        ]),
        
        html.Div(style={'marginTop': '40px', 'padding': '20px', 'border': '1px solid #17a2b8', 'borderRadius': '6px', 'backgroundColor': '#e8f7fa'}, children=[
            html.H3('🔔 Automatisk Telegram Alert-status (Aktiv)', style={'fontSize': '1.3em', 'color': '#17a2b8', 'marginBottom': '10px'}),
            html.P('Aviseringar skickas automatiskt när det högsta/lägsta tröskelvärdet uppnås för Prisrörelser eller *positivt* Handelsvärde:', style={'margin': '0 0 10px 0', 'color': '#000'}), # Textfärg tvingad till svart här
            html.Div(style={'display': 'flex', 'gap': '50px', 'flexWrap': 'wrap', 'color': '#000'}, children=[ # Textfärg tvingad till svart här
                html.Div([
                    html.P('**Prisrörelser (%):**', style={'fontWeight': 'bold', 'color': '#28a745', 'margin': '0 0 5px 0'}),
                    html.Ul([html.Li(f'+{t}%' if t > 0 else f'{t}%') for t in ALERT_THRESHOLDS_UP[::-1] + ALERT_THRESHOLDS_DOWN], style={'marginTop': '5px', 'paddingLeft': '20px', 'fontSize': '0.9em'})
                ]),
                html.Div([
                    html.P('**Handelsvärde (H.V.) (Endast Positiv):**', style={'fontWeight': 'bold', 'color': '#006400', 'margin': '0 0 5px 0'}),
                    html.Ul([html.Li(f'+{t}') for t in TRADE_VALUE_ALERTS], style={'marginTop': '5px', 'paddingLeft': '20px', 'fontSize': '0.9em'}) 
                ]),
            ]),
            html.P(f"Obs! Samma alert skickas max en gång per {ALERT_DEBOUNCE_SECONDS / 3600:.0f} timme (Pris och H.V. har separata spärrar).", style={'fontSize': '0.9em', 'color': '#6c757d', 'marginTop': '10px'}),
            html.P(f"**Schemalagda sammanställningar skickas kl: {', '.join([f'{h:02d}:00' for h in SUMMARY_SCHEDULE_HOURS])} (CET/CEST)**", style={'fontSize': '0.9em', 'color': '#17a2b8', 'marginTop': '10px', 'fontWeight': 'bold'}),
        ]),
    ]),
    dcc.Interval(id='interval-fast', interval=UPDATE_INTERVAL_FAST*1000, n_intervals=0),
    dcc.Interval(id='interval-slow', interval=UPDATE_INTERVAL_SLOW*1000, n_intervals=0)
])

# --- Callbacks ---

# CALLBACK: Uppdatera huvudstil för Dark/Light Mode
@app.callback(
    [Output('main-layout', 'style'),
     Output('content-container', 'style'),
     Output('controls-header', 'style'),
     Output('summary-header', 'style'),
     Output('last-updated', 'style')],
    [Input('theme-switch', 'value')]
)
def update_main_style(theme_value):
    theme = 'dark' if theme_value else 'light'
    colors = THEMES[theme]
    
    main_style = {'backgroundColor': colors['bg'], 'minHeight': '100vh', 'padding': '40px 10px', 'fontFamily': 'Roboto, Arial, sans-serif', 'color': colors['text']}
    content_style = {'maxWidth': '1400px', 'margin': '40px auto', 'padding': '30px', 'borderRadius': '12px', 'boxShadow': '0 4px 12px rgba(0,0,0,0.1)', 'border': f'1px solid {colors["border"]}', 'backgroundColor': colors['container_bg']}
    header_style = {'fontSize': '1.3em', 'marginBottom': '15px', 'color': colors['text']}
    last_updated_style = {'textAlign': 'center', 'fontSize': '0.9em', 'marginBottom': '0px', 'color': colors['text']}
    
    return main_style, content_style, header_style, header_style, last_updated_style

# CALLBACK: Styr hastigheten på graf-uppdateringen
@app.callback(
    Output('interval-fast', 'interval'),
    Input('graph-timeframe', 'value')
)
def update_interval_speed(timeframe):
    if timeframe == '4h_live':
        return 10 * 1000 # 10 sekunder
    else:
        return 120 * 1000 # 2 minuter

# CALLBACK 1: GRAF och TOP-BOX (Drivs av interval-fast)
@app.callback(
    Output('current-price-summary-box-container', 'children'), 
    Output('last-updated', 'children'),
    Output('chart-data-store', 'data'), 
    Output('current-currency-store', 'data'), 
    [Input('interval-fast', 'n_intervals'), 
     Input('coin-dropdown', 'value'), 
     Input('currency-dropdown', 'value'),
     Input('graph-timeframe', 'value'),
     Input('live-candle-interval', 'value'),
     Input('theme-switch', 'value')] 
)
def update_fast_components(n, coin_symbol, currency, timeframe, candle_interval, theme_value):
    data = get_data_from_redis()
    theme = 'dark' if theme_value else 'light'
    if data is None or 'EXCHANGE_RATES' not in data:
        loading_box = create_selected_coin_box("Laddar...", "", 0.0, currency, 11.0, None, None, {}, None, {}, None, theme=theme)
        return loading_box, "Väntar...", None, currency

    rates = data.get('EXCHANGE_RATES', {})
    eur_to_sek = rates.get('SEK', 11.0)
    eur_to_usd = rates.get('USD', 1.05)
    
    coin_label = SYMBOL_TO_LABEL.get(coin_symbol, coin_symbol)
    timestamp = data.get('timestamp')
    local_timestamp = timestamp + 3600 
    updated_text = f"Senast uppdaterad: {time.strftime('%H:%M:%S', time.gmtime(local_timestamp))} Lokal tid (CET/CEST)"
    current_price_eur = data.get(f'{coin_symbol}/EUR')
    diff_24h_eur = data.get(f'{coin_symbol}/DIFF_24H_EUR') 
    base_price_eur = 1.0 

    if currency == 'SEK':
        base_price_eur = eur_to_sek 
        current_price_base = current_price_eur * eur_to_sek if current_price_eur is not None else None
    elif currency == 'USD':
        base_price_eur = eur_to_usd
        current_price_base = current_price_eur * eur_to_usd if current_price_eur is not None else None
    elif currency == 'EUR':
        current_price_base = current_price_eur
    elif currency in COINS_SYMBOLS:
        base_price_eur = data.get(f'{currency}/EUR') 
        current_price_base = (current_price_eur / base_price_eur) if current_price_eur and base_price_eur else None
    else:
        current_price_base = current_price_eur

    selected_ticker = CRYPTO_PAIRS.get(coin_label, f'{coin_symbol}/EUR')
    
    graph_hist_data = []
    
    if timeframe == '4h_live':
        if candle_interval == 15:
            raw_json = r.get(f'OHLC_LIVE_VIEW_{selected_ticker}') if r else None
            if raw_json:
                graph_hist_data = json.loads(raw_json)
            else:
                 graph_hist_data = fetch_ohlc_data_from_kraken(selected_ticker, 15, 3600 * 12)
        else:
             graph_hist_data = fetch_ohlc_data_from_kraken(selected_ticker, candle_interval, 3600 * 12)

    elif timeframe == '1w':
        raw_json = r.get(f'OHLC_1WEEK_{selected_ticker}') if r else None
        graph_hist_data = json.loads(raw_json) if raw_json else []
    elif timeframe == '1m':
        raw_json = r.get(f'OHLC_1MONTH_{selected_ticker}') if r else None
        graph_hist_data = json.loads(raw_json) if raw_json else []
    else:
        ohlc_interval = OHLC_CACHE_INTERVAL_MIN 
        raw_json = r.get(f'OHLC_CACHED_{ohlc_interval}MIN_{selected_ticker}') if r else None
        graph_hist_data = json.loads(raw_json) if raw_json else []

    hist_data_5min = json.loads(r.get(f'OHLC_CACHED_{OHLC_CACHE_INTERVAL_MIN}MIN_{selected_ticker}') or '[]') if r else []
    hist_data_1day = json.loads(r.get(f'OHLC_1DAY_{selected_ticker}') or '[]') if r else []
    
    trade_value, individual_trends, chart_data_store = None, {}, None
    
    if hist_data_5min and current_price_eur is not None:
        hist_5min_curr = hist_data_5min + [{'time': timestamp, 'price': current_price_eur}]
        hist_1day_curr = hist_data_1day + [{'time': timestamp, 'price': current_price_eur}]
        trade_value, individual_trends = calculate_trade_value(hist_5min_curr, current_price_eur, hist_1day_curr)

    if graph_hist_data and current_price_eur is not None and timeframe == '4h_live':
        last_entry = graph_hist_data[-1]
        last_time = last_entry['time']
        interval_seconds = candle_interval * 60
        current_time = int(time.time())
        current_graph_data = graph_hist_data.copy()
        
        if current_time < (last_time + interval_seconds):
            current_graph_data[-1]['close'] = current_price_eur
            current_graph_data[-1]['high'] = max(last_entry.get('high', -999), current_price_eur)
            current_graph_data[-1]['low'] = min(last_entry.get('low', 9999999), current_price_eur)
        else:
            next_block_time = last_time + interval_seconds
            current_graph_data.append({
                'time': next_block_time,
                'open': current_price_eur,
                'close': current_price_eur,
                'high': current_price_eur,
                'low': current_price_eur
            })

        prices_eur_graph = [item['price'] if 'price' in item else item['close'] for item in current_graph_data]
        
        chart_data_store = {
            'historical_data': current_graph_data, 
            'current_price_eur': current_price_eur, 
            'max_ohlc_eur': max(prices_eur_graph) if prices_eur_graph else None, 
            'min_ohlc_eur': min(prices_eur_graph) if prices_eur_graph else None, 
            'eur_to_sek': eur_to_sek, 
            'base_price_eur': base_price_eur, 
            'coin_symbol': coin_symbol, 
            'trade_value': trade_value,
            'individual_trends': individual_trends,
            'timeframe': timeframe,
            'candle_interval': candle_interval
        }
    elif graph_hist_data:
        chart_data_store = {
            'historical_data': graph_hist_data,
            'current_price_eur': current_price_eur,
            'base_price_eur': base_price_eur,
            'timeframe': timeframe,
            'coin_symbol': coin_symbol,
            'candle_interval': None
        }

    percent_data = data.get('ALL_PERCENT_CHANGE', {}).get(coin_symbol, {})
    range_data = data.get('ALL_24H_RANGE_OHLC', {}).get(coin_symbol, {})
    
    summary_box = create_selected_coin_box(coin_label, coin_symbol, current_price_base or 0.0, currency, base_price_eur, range_data.get('high_eur'), range_data.get('low_eur'), percent_data, trade_value, individual_trends, diff_24h_eur, theme=theme)
    
    return summary_box, updated_text, chart_data_store, currency


# CALLBACK 2: TABELLEN (Drivs av interval-slow, 2 minuter)
@app.callback(
    [Output('crypto-table', 'data'),
     Output('crypto-table', 'style_header'),
     Output('crypto-table', 'style_cell')],
    [Input('interval-slow', 'n_intervals'),
     Input('currency-dropdown', 'value'),
     Input('theme-switch', 'value')]
)
def update_table_slow(n, currency, theme_value):
    theme = 'dark' if theme_value else 'light'
    colors = THEMES[theme]
    
    data = get_data_from_redis()
    if data is None or 'EXCHANGE_RATES' not in data:
        return [], {}, {}

    rates = data.get('EXCHANGE_RATES', {})
    eur_to_sek = rates.get('SEK', 11.0)
    eur_to_usd = rates.get('USD', 1.05)
    
    base_price_eur = 1.0 
    if currency == 'SEK': base_price_eur = eur_to_sek 
    elif currency == 'USD': base_price_eur = eur_to_usd
    elif currency in COINS_SYMBOLS: base_price_eur = data.get(f'{currency}/EUR') 

    table_data = []
    for label in COINS_LABELS:
        sl = label.split(' ')[0]
        tl = CRYPTO_PAIRS[label]
        pe = data.get(f'{sl}/EUR')
        pd = data.get('ALL_PERCENT_CHANGE', {}).get(sl, {})
        h5 = json.loads(r.get(f'OHLC_CACHED_{OHLC_CACHE_INTERVAL_MIN}MIN_{tl}') or '[]') if r else []
        h1 = json.loads(r.get(f'OHLC_1DAY_{tl}') or '[]') if r else []
        
        tv_int = None
        if h5 and pe:
            tv_val, _ = calculate_trade_value(h5 + [{'time': data.get('timestamp'), 'price': pe}], pe, h1 + [{'time': data.get('timestamp'), 'price': pe}])
            if tv_val is not None: tv_int = int(round(tv_val))
        
        pb = pe
        if currency == 'SEK': pb = pe * eur_to_sek if pe else None
        elif currency == 'USD': pb = pe * eur_to_usd if pe else None
        elif currency != 'EUR' and base_price_eur: pb = pe / base_price_eur if pe else None

        logo_url = get_logo_url(sl)
        label_html = f"<img src='{logo_url}' style='height: 24px; width: 24px; vertical-align: middle; margin-right: 8px;' /> **{label}**"
        
        # Formatera priset med 24h% inom parentes
        price_formatted = f"{format_price_display(pb)} {currency}" if pb is not None else "N/A"
        change_24h_val = pd.get('24h')
        if change_24h_val is not None:
            sign = "+" if change_24h_val >= 0 else ""
            price_formatted += f" ({sign}{change_24h_val:.2f}%)"

        row = {
            'label': label_html,
            'symbol': sl, 
            'price': price_formatted,
            '30m': pd.get('30m'),
            '1h': pd.get('1h'),
            '3h': pd.get('3h'),
            '6h': pd.get('6h'),
            '12h': pd.get('12h'),
            '24h': pd.get('24h'),
            '7d': pd.get('7d'),
            '30d': pd.get('30d'),
            'trade_value': tv_int
        }
        table_data.append(row)

    style_header = {
        'backgroundColor': colors['table_header'],
        'color': colors['text'],
        'fontWeight': 'bold',
        'borderBottom': f'2px solid {colors["text_header"]}'
    }
    
    style_cell = {
        'backgroundColor': colors['table_cell'],
        'color': colors['text'],
        'textAlign': 'right',
        'padding': '10px',
        'fontFamily': 'Roboto, Arial, sans-serif',
        'fontSize': '0.9em',
        'border': f'1px solid {colors["border"]}'
    }

    return table_data, style_header, style_cell

@app.callback(
    Output('live-update-graph', 'figure'),
    [Input('chart-data-store', 'data'), Input('current-currency-store', 'data'), Input('trendline-checkboxes', 'value'), Input('theme-switch', 'value')],
    [State('coin-dropdown', 'value')]
)
def update_trendline_visibility(chart_data_store, currency, selected_trends, theme_value, coin_symbol):
    if chart_data_store is None: return go.Figure()
    
    theme = 'dark' if theme_value else 'light'
    colors = THEMES[theme]
    
    hist_data = chart_data_store['historical_data']
    base_price_eur = chart_data_store['base_price_eur'] 
    coin_label = SYMBOL_TO_LABEL.get(coin_symbol, coin_symbol)
    timeframe = chart_data_store.get('timeframe', '1d')
    candle_interval = chart_data_store.get('candle_interval')
    
    figure = go.Figure()
    
    prices_eur = [item.get('close', item.get('price')) for item in hist_data]
    opens_eur = [item.get('open', item.get('price')) for item in hist_data]
    highs_eur = [item.get('high', item.get('price')) for item in hist_data]
    lows_eur = [item.get('low', item.get('price')) for item in hist_data]
    
    def convert_currency(val_list):
        if currency == 'SEK' or currency == 'USD': return [p * base_price_eur for p in val_list]
        elif currency == 'EUR': return val_list
        elif base_price_eur: return [p / base_price_eur for p in val_list]
        else: return val_list

    prices = convert_currency(prices_eur)
    opens = convert_currency(opens_eur)
    highs = convert_currency(highs_eur)
    lows = convert_currency(lows_eur)
    
    current_price_converted = prices[-1] if prices else 0

    if timeframe == '4h_live':
        times = [time.strftime('%H:%M', time.gmtime(item['time'] + 3600)) for item in hist_data]
        interval_label = f"{candle_interval}m"
        
        figure.add_trace(go.Candlestick(
            x=times, open=opens, high=highs, low=lows, close=prices,
            name=f'Kurs ({interval_label})',
            increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
        ))
        
        if times:
            figure.add_trace(go.Scatter(
                x=[times[-1]], y=[current_price_converted],
                mode='markers',
                name='Live Pris',
                marker=dict(color='#2196f3', size=10, symbol='circle', line=dict(color='white', width=2))
            ))

        figure.add_hline(y=current_price_converted, line_dash="dot", line_color="#2196f3", opacity=0.5, annotation_text=f" Live: {format_price_display(current_price_converted)}", annotation_position="right")
        
        slope, intercept, start_idx = calculate_trendline(hist_data, len(hist_data))
        if slope is not None:
             trend_y_eur = slope * np.arange(len(hist_data)) + intercept
             trend_y = convert_currency(trend_y_eur)
             figure.add_trace(go.Scatter(x=times, y=trend_y, mode='lines', name='Trend (4h)', line=dict(color='#ff9800', width=2, dash='dot')))



        figure.update_layout(xaxis_rangeslider_visible=False) 

    else:
        times = [time.strftime('%Y-%m-%d %H:%M', time.gmtime(item['time'] + 3600)) for item in hist_data]
        figure.add_trace(go.Scatter(x=times, y=prices, mode='lines', name=f'Kurs', line=dict(color=colors['text_header'], width=2)))

    time_label = "1 Dag (5m)"
    if timeframe == '4h_live': time_label = f"4 Timmar ({candle_interval}m Live)"
    elif timeframe == '1w': time_label = "1 Vecka (15m)"
    elif timeframe == '1m': time_label = "1 Månad (60m)"

    if timeframe in ['1d', '4h_live']:
        high_val, low_val = max(highs) if highs else None, min(lows) if lows else None
        if high_val and high_val != current_price_converted: 
            figure.add_hline(y=high_val, line_dash="dash", line_color="#4caf50", annotation_text="Hög", opacity=0.3)
        if low_val and low_val != current_price_converted: 
            figure.add_hline(y=low_val, line_dash="dash", line_color="#ef5350", annotation_text="Låg", annotation_position="bottom left", opacity=0.3)

    if timeframe in ['1d', '1w', '1m'] and times and prices:
        figure.add_trace(go.Scatter(
            x=[times[-1]], y=[prices[-1]],
            mode='markers',
            name='Nuvarande',
            marker=dict(color='#2196f3', size=8)
        ))

    if timeframe == '1d':
        for key in selected_trends:
            config = TREND_WINDOWS.get(key)
            if not config or not config.get('show_line', False) or config.get('source') != '5min': continue
            
            if len(hist_data) >= config['blocks']:
                slope, intercept, start_idx = calculate_trendline(hist_data, config['blocks'])
                trend_y_eur = slope * np.arange(config['blocks']) + intercept
                trend_y = convert_currency(trend_y_eur)
                figure.add_trace(go.Scatter(x=times[start_idx:], y=trend_y, mode='lines', name=config['name'], line=dict(color=config['color'], width=2, dash='dash')))
    
    elif timeframe in ['1w', '1m']:
         slope, intercept, start_idx = calculate_trendline(hist_data, len(hist_data))
         if slope is not None:
             trend_y_eur = slope * np.arange(len(hist_data)) + intercept
             trend_y = convert_currency(trend_y_eur)
             figure.add_trace(go.Scatter(x=times, y=trend_y, mode='lines', name=f'Trend ({timeframe})', line=dict(color='#ff9800', width=2, dash='dot')))

    figure.update_layout(
        title=f"Prisutveckling: {coin_label} ({time_label})", 
        template=colors['graph_template'], 
        height=500, 
        hovermode="x unified",
        margin=dict(r=50),
        paper_bgcolor=colors['container_bg'],
        plot_bgcolor=colors['container_bg'],
        font={'color': colors['text']}
    )
    return figure

# Uppdaterad Callback för att välja valuta via tabell-klick
@app.callback(
    Output('coin-dropdown', 'value', allow_duplicate=True),
    [Input('crypto-table', 'active_cell')],
    [State('crypto-table', 'derived_virtual_data')],
    prevent_initial_call=True
)
def update_dropdown_selection_sorted(active_cell, virtual_data):
    if active_cell and virtual_data:
        row_index = active_cell['row']
        if row_index < len(virtual_data):
            selected_row = virtual_data[row_index]
            return selected_row['symbol']
    return dash.no_update

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8050))
    app.run_server(debug=False, host='0.0.0.0', port=port)