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

# Konfigurera logging
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
    'BRICK (Bricks)': 'BRICK/EUR', 'ALMANAK (Almanak)': 'ALMANAK/EUR',
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

BASE_CURRENCIES = ['EUR', 'SEK', 'USD'] + [s for s in COINS_SYMBOLS]
SYMBOL_TO_LABEL = {label.split(' ')[0]: label for label in COINS_LABELS}

UPDATE_INTERVAL_SECONDS_DATA = 120
OHLC_CACHE_INTERVAL_MIN = 5

# Tidsintervall för schemalagd sammanställning (i 24-timmarsformat)
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

# Konfiguration för Trendlinjer och H.V. beräkning
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
ALERT_DEBOUNCE_SECONDS = 2 * 3600 # 2 timmar

TRADE_VALUE_ALERTS = sorted([50, 75, 100, 150], reverse=True)
TRADE_VALUE_DEBOUNCE_SECONDS = 2 * 3600 # 1 timme

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
    'EXCHANGE_RATES': {'SEK': 11.0, 'USD': 1.05}, 
    'ALL_24H_RANGE_OHLC': {'XRP': {'high_eur': 0.52, 'low_eur': 0.48}},
    'ALL_OHLC_CACHED': {},
    'ALL_PERCENT_CHANGE': {},
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
        return [{'time': int(row[0]), 'price': float(row[4])} for row in data_list]
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

def format_price_color_summary(price_in_base, change_24h):
    if price_in_base is None: return html.Div("N/A", style={'color': '#6c757d'})
    price_str = format_price_display(price_in_base)
    color = '#495057'
    if change_24h is not None:
        if change_24h >= 0.01: color = '#28a745'
        elif change_24h <= -0.01: color = '#dc3545'
    return html.Div(price_str, style={'flex': '0 0 100px', 'textAlign': 'right', 'fontWeight': 'bold', 'paddingRight': '5px', 'color': color})

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

# --- Bakgrundstrådar ---

def background_data_fetch(redis_instance):
    UPDATE_CYCLE_SECONDS = UPDATE_INTERVAL_SECONDS_DATA
    last_long_term_fetch = 0 
    
    while True:
        cycle_start_time = time.time()
        try:
            new_data = fetch_crypto_data()
            if not new_data or new_data == DEFAULT_DATA:
                time.sleep(UPDATE_CYCLE_SECONDS)
                continue
                
            all_percent_changes = {}
            all_24h_range_ohlc = {} 
            alert_data_for_sending = {} 
            trade_value_alert_data = {} 
            
            fetch_extra_intervals = (time.time() - last_long_term_fetch) > 900 
            if fetch_extra_intervals:
                last_long_term_fetch = time.time()
                logger.debug("⏳ Hämtar 1v och 1mån data från Kraken...")

            for label, ticker in CRYPTO_PAIRS.items():
                coin_symbol = label.split(' ')[0]
                current_price_eur = new_data.get(f'{coin_symbol}/EUR')
                if current_price_eur is None: continue
                        
                # 1. Standard 5-min data (för 24h graf och kortsiktiga beräkningar)
                periods_ago_24h = 86400 
                ohlc_5min_data = fetch_ohlc_data_from_kraken(ticker, OHLC_CACHE_INTERVAL_MIN, periods_ago_24h) 
                if ohlc_5min_data:
                     redis_instance.set(f'OHLC_CACHED_{OHLC_CACHE_INTERVAL_MIN}MIN_{ticker}', json.dumps(ohlc_5min_data), ex=7200)

                # 2. 1-dag data (för 1 år trend)
                periods_ago_1y = 365 * 86400 * 1.1 
                ohlc_1day_data = fetch_ohlc_data_from_kraken(ticker, 1440, periods_ago_1y) 
                if ohlc_1day_data:
                     redis_instance.set(f'OHLC_1DAY_{ticker}', json.dumps(ohlc_1day_data), ex=86400)

                # 3. NYTT: 1-minut data (för 30min grafen - Snabba uppdateringar)
                # Vi hämtar senaste 60 minuter för att vara säkra på att fylla grafen
                ohlc_1min_data = fetch_ohlc_data_from_kraken(ticker, 1, 3600)
                if ohlc_1min_data:
                    redis_instance.set(f'OHLC_CACHED_1MIN_{ticker}', json.dumps(ohlc_1min_data), ex=300)

                # 4. EXTRA: 1-Vecka och 1-Månad (Var 15e min)
                if fetch_extra_intervals:
                    ohlc_1week_data = fetch_ohlc_data_from_kraken(ticker, 15, 7 * 86400)
                    if ohlc_1week_data:
                        redis_instance.set(f'OHLC_1WEEK_{ticker}', json.dumps(ohlc_1week_data), ex=3600)
                    
                    ohlc_1month_data = fetch_ohlc_data_from_kraken(ticker, 60, 30 * 86400)
                    if ohlc_1month_data:
                        redis_instance.set(f'OHLC_1MONTH_{ticker}', json.dumps(ohlc_1month_data), ex=7200)

                trade_value_int = None
                if ohlc_5min_data and ohlc_1day_data:
                    hist_5min_current = ohlc_5min_data.copy()
                    hist_5min_current.append({'time': new_data.get('timestamp'), 'price': current_price_eur})
                    hist_1day_current = ohlc_1day_data.copy()
                    hist_1day_current.append({'time': new_data.get('timestamp'), 'price': current_price_eur})
                    
                    trade_value, _ = calculate_trade_value(hist_5min_current, current_price_eur, hist_1day_current)
                    if trade_value is not None:
                        trade_value_int = int(round(trade_value))
                
                if ohlc_5min_data:
                    prices_eur = [item['price'] for item in ohlc_5min_data]
                    if prices_eur:
                        all_24h_range_ohlc[coin_symbol] = {'high_eur': max(prices_eur), 'low_eur': min(prices_eur)}
                    short_term_periods = {k: v for k, v in TIME_WINDOWS.items() if v['interval'] == OHLC_CACHE_INTERVAL_MIN}
                    percent_changes = calculate_percentage_changes(ohlc_5min_data, current_price_eur, short_term_periods)
                else:
                    percent_changes = {}

                long_term_periods = {k: v for k, v in TIME_WINDOWS.items() if v['interval'] == 1440}
                long_term_changes = calculate_percentage_changes(ohlc_1day_data, current_price_eur, long_term_periods)
                
                percent_changes.update(long_term_changes) 
                all_percent_changes[coin_symbol] = percent_changes
                alert_data_for_sending[coin_symbol] = {'changes': percent_changes, 'price_eur': current_price_eur}
                trade_value_alert_data[coin_symbol] = {'trade_value': trade_value_int, 'price_eur': current_price_eur}
                time.sleep(0.1) 
            
            if redis_instance:
                check_and_send_alerts(alert_data_for_sending, redis_instance)
                check_and_send_trade_value_alerts(trade_value_alert_data, redis_instance) 
                new_data['ALL_PERCENT_CHANGE'] = all_percent_changes
                new_data['ALL_24H_RANGE_OHLC'] = all_24h_range_ohlc 
                redis_instance.set('crypto_data', json.dumps(new_data), ex=UPDATE_CYCLE_SECONDS + 60)
                logger.debug("✅ Hela 'crypto_data' sparad.")
            
            time.sleep(max(0, UPDATE_CYCLE_SECONDS - (time.time() - cycle_start_time)))
        except Exception as e:
            logger.error(f"❌ Fel i bakgrundstråd: {e}")
            time.sleep(60)

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
                        if send_telegram_message(msg):
                            logger.info("✅ Sammanfattning skickad.")
                time.sleep(60)
        except Exception as e:
            logger.error(f"❌ Fel i schema-tråd: {e}")
            time.sleep(60)

if r:
    threading.Thread(target=background_data_fetch, args=(r,), daemon=True).start()
    threading.Thread(target=background_summary_sender, args=(r,), daemon=True).start()

# --- Dash App ---

app = dash.Dash(__name__, external_stylesheets=['https://codepen.io/chriddyp/cnWqWbL.css'])
server = app.server

def create_summary_row(symbol, label, price, percent_data, trade_value, currency, is_selected, eur_to_sek):
    row_style = {
        'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center',
        'padding': '5px 0', 'borderBottom': '1px solid #eee', 'fontSize': '0.85em', 'cursor': 'pointer',
        'backgroundColor': '#fff'
    }
    if is_selected:
        row_style['backgroundColor'] = '#e6f7ff'
        row_style['border'] = '1px solid #0056b3'

    change_24h = percent_data.get('24h')
    price_str = format_price_display(price)
    change_str = ""
    change_color = '#495057'

    if change_24h is not None:
        if change_24h >= 0.01:
            change_color = '#28a745'
            change_str = f" (+{change_24h:.2f}%)"
        elif change_24h <= -0.01:
            change_color = '#dc3545'
            change_str = f" ({change_24h:.2f}%)"
        else:
            change_str = f" ({change_24h:.2f}%)"

    price_div = html.Div([
        html.Span(price_str, style={'color': '#495057'}),
        html.Span(change_str, style={'color': change_color, 'fontSize': '0.9em', 'fontWeight': 'normal'})
    ], style={'flex': '0 0 140px', 'textAlign': 'right', 'fontWeight': 'bold', 'paddingRight': '5px'})

    cols = [
        html.Div(html.Span(f"{CRYPTO_EMOJIS.get(symbol, '')} {label}", style={'fontWeight': 'bold', 'color': '#0056b3' if is_selected else '#495057'}), style={'flex': '0 0 160px', 'paddingLeft': '5px'}),
        price_div,
        html.Div(format_change(percent_data.get('30m')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('1h')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('3h')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('6h')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('12h')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('24h')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('7d')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('30d')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_trade_value_display(trade_value), style={'flex': '0 0 80px', 'textAlign': 'right', 'fontWeight': 'bold', 'paddingRight': '5px'}),
    ]
    return html.Div(cols, id={'type': 'summary-card', 'index': symbol}, style=row_style)

def create_selected_coin_box(label, symbol, price, currency, base_price_eur, high_eur, low_eur, percent_data, trade_value=None, individual_trends=None, diff_24h_eur=None):
    if individual_trends is None: individual_trends = {}
    price_text = f"{format_price_display(price)} {currency}"
    coin_emoji = CRYPTO_EMOJIS.get(symbol, '')
    
    change_24h = percent_data.get('24h')
    price_color = '#28a745' if change_24h and change_24h > 0 else '#dc3545' if change_24h and change_24h < 0 else '#495057'
    trade_value_color = '#006400' if trade_value and trade_value > 0 else '#8B0000' if trade_value and trade_value < 0 else '#495057'
    
    multiplier = 1
    high_display, low_display = None, None
    if high_eur is not None and low_eur is not None and base_price_eur:
        if currency == 'SEK' or currency == 'USD': multiplier = base_price_eur
        elif currency == 'EUR': multiplier = 1
        elif base_price_eur and currency in COINS_SYMBOLS: multiplier = 1 / base_price_eur
        else: multiplier = 1
        high_display = high_eur * multiplier
        low_display = low_eur * multiplier

    def create_change_row(period, value):
        display_name = {'7d': '7dgr', '30d': '30dgr', '6m': '6mån', '1y': '1år', '30m': '30min'}.get(period, period)
        return html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'margin': '3px 0', 'padding': '0 5px', 'fontSize': '0.9em'}, children=[
            html.Span(f"{display_name.capitalize()}:", style={'color': '#6c757d', 'flex': '0 0 50px'}),
            html.Div(value, style={'flex': '1', 'textAlign': 'right'})
        ])

    short_term_keys = [k for k, v in TREND_WINDOWS.items() if v.get('source') == '5min']
    long_term_keys = [k for k, v in TREND_WINDOWS.items() if v.get('source') == '1day']
    
    diff_24h_base = None
    if diff_24h_eur is not None:
        if currency == 'SEK' or currency == 'USD':
            diff_24h_base = diff_24h_eur * base_price_eur
        elif currency == 'EUR':
            diff_24h_base = diff_24h_eur
        elif base_price_eur and currency in COINS_SYMBOLS:
            diff_24h_base = diff_24h_eur / base_price_eur

    diff_color = '#28a745' if diff_24h_base and diff_24h_base > 0 else '#dc3545' if diff_24h_base and diff_24h_base < 0 else '#495057'
    diff_sign = "+" if diff_24h_base and diff_24h_base > 0 else ""
    diff_text = f"{diff_sign}{format_price_display(diff_24h_base)}" if diff_24h_base is not None else "N/A"

    return html.Div(style={'padding': '15px', 'backgroundColor': '#f8f9fa', 'border': '1px solid #dee2e6', 'borderRadius': '4px', 'marginBottom': '20px'}, children=[
        html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'flex-start', 'marginBottom': '10px'}, children=[
            html.Div([
                html.H3(f"{coin_emoji} {label}", style={'margin': '0', 'color': '#0056b3', 'fontSize': '1.4em'}),
                html.Div(f"Aktuellt pris ({currency})", style={'fontSize': '0.8em', 'color': '#6c757d', 'marginTop': '4px'})
            ]),
            html.Div(style={'textAlign': 'right'}, children=[
                html.Div(price_text, style={'fontSize': '1.6em', 'fontWeight': 'bold', 'color': price_color}),
                html.Div(f"24h: {diff_text}", style={'fontSize': '0.9em', 'color': diff_color, 'fontWeight': 'bold'})
            ])
        ]),
        html.Div(style={'display': 'grid', 'gridTemplateColumns': 'repeat(auto-fit, minmax(140px, 1fr))', 'gap': '10px'}, children=[
            html.Div([
                html.Div("H.V. (Totalt)", style={'fontSize': '0.75em', 'color': '#6c757d', 'marginBottom': '2px'}),
                html.Div(format_trade_value_display(trade_value), style={'fontSize': '1.3em', 'fontWeight': 'bold'})
            ], style={'padding': '8px', 'backgroundColor': '#fff', 'borderRadius': '4px', 'border': '1px solid #eee'}),
            html.Div([
                html.Div("Dagens Högsta", style={'fontSize': '0.75em', 'color': '#6c757d', 'marginBottom': '2px'}),
                html.Div(format_price_display(high_display), style={'fontSize': '1.1em', 'fontWeight': 'bold', 'color': '#28a745'})
            ], style={'padding': '8px', 'backgroundColor': '#fff', 'borderRadius': '4px', 'border': '1px solid #eee'}),
            html.Div([
                html.Div("Dagens Lägsta", style={'fontSize': '0.75em', 'color': '#6c757d', 'marginBottom': '2px'}),
                html.Div(format_price_display(low_display), style={'fontSize': '1.1em', 'fontWeight': 'bold', 'color': '#dc3545'})
            ], style={'padding': '8px', 'backgroundColor': '#fff', 'borderRadius': '4px', 'border': '1px solid #eee'}),
        ]),
        html.Hr(style={'margin': '15px 0', 'opacity': '0.3'}),
        html.Div(style={'display': 'flex', 'gap': '20px', 'flexWrap': 'wrap'}, children=[
            html.Div(style={'flex': '1', 'minWidth': '150px'}, children=[
                html.Div("Kortsiktiga trender (H.V.)", style={'fontSize': '0.8em', 'fontWeight': 'bold', 'color': '#495057', 'marginBottom': '5px'}),
                html.Div([create_change_row(k, format_trade_value_display(individual_trends.get(k, {}).get('val') if individual_trends.get(k) else None)) for k in short_term_keys])
            ]),
            html.Div(style={'flex': '1', 'minWidth': '150px'}, children=[
                html.Div("Långsiktiga trender (H.V.)", style={'fontSize': '0.8em', 'fontWeight': 'bold', 'color': '#495057', 'marginBottom': '5px'}),
                html.Div([create_change_row(k, format_trade_value_display(individual_trends.get(k, {}).get('val') if individual_trends.get(k) else None)) for k in long_term_keys])
            ]),
            html.Div(style={'flex': '1', 'minWidth': '150px'}, children=[
                html.Div("Prisförändring (%)", style={'fontSize': '0.8em', 'fontWeight': 'bold', 'color': '#495057', 'marginBottom': '5px'}),
                html.Div([create_change_row(k, format_change(percent_data.get(k))) for k in ['30m', '1h', '3h', '6h', '12h', '24h']])
            ]),
            html.Div(style={'flex': '1', 'minWidth': '150px'}, children=[
                html.Div("Historik (%)", style={'fontSize': '0.8em', 'fontWeight': 'bold', 'color': '#495057', 'marginBottom': '5px'}),
                html.Div([create_change_row(k, format_change(percent_data.get(k))) for k in ['7d', '30d', '6m', '1y']])
            ]),
        ])
    ])

app.layout = html.Div(style={'fontFamily': '"Segoe UI", Roboto, Helvetica, Arial, sans-serif', 'backgroundColor': '#f0f2f5', 'padding': '20px'}, children=[
    html.Div(style={'maxWidth': '1400px', 'margin': '0 auto'}, children=[
        html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center', 'marginBottom': '20px', 'backgroundColor': '#fff', 'padding': '15px 25px', 'borderRadius': '8px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.05)'}, children=[
            html.H1("Live Crypto Dashboard", style={'margin': '0', 'color': '#0056b3', 'fontSize': '1.8em', 'fontWeight': 'bold'}),
            html.Div(style={'display': 'flex', 'gap': '15px', 'alignItems': 'center'}, children=[
                html.Div([
                    html.Label("Välj Valuta:", style={'fontSize': '0.8em', 'color': '#6c757d', 'marginBottom': '3px', 'display': 'block'}),
                    dcc.Dropdown(id='coin-dropdown', options=[{'label': k, 'value': k.split(' ')[0]} for k in COINS_LABELS], value=DEFAULT_COIN_SYMBOL, style={'width': '200px'})
                ]),
                html.Div([
                    html.Label("Visa i:", style={'fontSize': '0.8em', 'color': '#6c757d', 'marginBottom': '3px', 'display': 'block'}),
                    dcc.Dropdown(id='currency-dropdown', options=[{'label': c, 'value': c} for c in BASE_CURRENCIES], value='EUR', style={'width': '100px'})
                ]),
                html.Button("Uppdatera Nu", id='manual-refresh-btn', className='button-primary', style={'marginTop': '18px'})
            ])
        ]),
        
        dcc.Interval(id='interval-component', interval=UPDATE_INTERVAL_SECONDS_DATA * 1000, n_intervals=0),
        dcc.Store(id='initial-coin-symbol-store', data=DEFAULT_COIN_SYMBOL),
        dcc.Store(id='chart-data-store'),
        
        html.Div(id='selected-coin-info-container'),
        
        html.Div(style={'backgroundColor': '#fff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.05)', 'marginBottom': '20px'}, children=[
            html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center', 'marginBottom': '15px'}, children=[
                html.H4("Prisutveckling & Analys", style={'margin': '0', 'color': '#495057'}),
                dcc.RadioItems(
                    id='graph-timeframe',
                    options=[
                        {'label': ' Live (30m)', 'value': '1h_live'},
                        {'label': ' 1 Dag', 'value': '1d'},
                        {'label': ' 1 Vecka', 'value': '1w'},
                        {'label': ' 1 Månad', 'value': '1m'},
                    ],
                    value='1h_live',
                    labelStyle={'display': 'inline-block', 'marginRight': '15px', 'fontSize': '0.9em', 'color': '#495057'}
                )
            ]),
            dcc.Graph(id='live-update-graph', config={'displayModeBar': False})
        ]),
        
        html.Div(style={'backgroundColor': '#fff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.05)'}, children=[
            html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center', 'marginBottom': '15px', 'paddingBottom': '10px', 'borderBottom': '2px solid #f0f2f5'}, children=[
                html.H4("Marknadsöversikt", style={'margin': '0', 'color': '#495057'}),
                html.Span(id='last-updated-text', style={'fontSize': '0.8em', 'color': '#999'})
            ]),
            html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'padding': '10px 0', 'borderBottom': '1px solid #dee2e6', 'fontWeight': 'bold', 'fontSize': '0.75em', 'color': '#6c757d', 'textTransform': 'uppercase', 'letterSpacing': '0.5px'}, children=[
                html.Div("Krypto", style={'flex': '0 0 160px', 'paddingLeft': '5px'}),
                html.Div("Pris & 24h", style={'flex': '0 0 140px', 'textAlign': 'right', 'paddingRight': '5px'}),
                html.Div("30m", style={'flex': '1', 'textAlign': 'right'}),
                html.Div("1h", style={'flex': '1', 'textAlign': 'right'}),
                html.Div("3h", style={'flex': '1', 'textAlign': 'right'}),
                html.Div("6h", style={'flex': '1', 'textAlign': 'right'}),
                html.Div("12h", style={'flex': '1', 'textAlign': 'right'}),
                html.Div("24h", style={'flex': '1', 'textAlign': 'right'}),
                html.Div("7d", style={'flex': '1', 'textAlign': 'right'}),
                html.Div("30d", style={'flex': '1', 'textAlign': 'right'}),
                html.Div("H.V.", style={'flex': '0 0 80px', 'textAlign': 'right', 'paddingRight': '5px'}),
            ]),
            html.Div(id='summary-table-container')
        ])
    ])
])

# --- Callbacks ---

@app.callback(
    [Output('summary-table-container', 'children'),
     Output('last-updated-text', 'children'),
     Output('selected-coin-info-container', 'children'),
     Output('chart-data-store', 'data')],
    [Input('interval-component', 'n_intervals'),
     Input('manual-refresh-btn', 'n_clicks'),
     Input('coin-dropdown', 'value')],
    [State('currency-dropdown', 'value')]
)
def update_dashboard_data(n_int, n_clicks, selected_coin_symbol, currency):
    data = get_data_from_redis()
    if not data: return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    
    eur_to_sek = data.get('EXCHANGE_RATES', {}).get('SEK', 11.0)
    eur_to_usd = data.get('EXCHANGE_RATES', {}).get('USD', 1.05)
    
    base_rate = 1.0
    if currency == 'SEK': base_rate = eur_to_sek
    elif currency == 'USD': base_rate = eur_to_usd
    
    summary_rows = []
    selected_coin_box = dash.no_update
    chart_data_store = {}

    for label in COINS_LABELS:
        coin_symbol = label.split(' ')[0]
        price_eur = data.get(f'{coin_symbol}/EUR')
        diff_24h_eur = data.get(f'{coin_symbol}/DIFF_24H_EUR')
        percent_data = data.get('ALL_PERCENT_CHANGE', {}).get(coin_symbol, {})
        range_data = data.get('ALL_24H_RANGE_OHLC', {}).get(coin_symbol, {})
        
        hist_data_5min = []
        hist_data_1day = []
        if r:
            ticker = CRYPTO_PAIRS[label]
            h_json = r.get(f'OHLC_CACHED_{OHLC_CACHE_INTERVAL_MIN}MIN_{ticker}')
            if h_json: hist_data_5min = json.loads(h_json)
            h_day_json = r.get(f'OHLC_1DAY_{ticker}')
            if h_day_json: hist_data_1day = json.loads(h_day_json)

        trade_value = None
        ind_trends = {}
        if hist_data_5min and price_eur is not None:
            h_5min_current = hist_data_5min.copy()
            h_5min_current.append({'time': data.get('timestamp'), 'price': price_eur})
            h_1day_current = hist_data_1day.copy() if hist_data_1day else []
            h_1day_current.append({'time': data.get('timestamp'), 'price': price_eur})
            trade_value, ind_trends = calculate_trade_value(h_5min_current, price_eur, h_1day_current)

        is_selected = (coin_symbol == selected_coin_symbol)
        
        price_in_base = price_eur
        if price_eur is not None:
            if currency == 'SEK' or currency == 'USD': price_in_base = price_eur * base_rate
            elif currency == 'EUR': price_in_base = price_eur
            elif currency in data.get('EXCHANGE_RATES', {}): price_in_base = price_eur * data['EXCHANGE_RATES'][currency]
            elif f'{currency}/EUR' in data: price_in_base = price_eur / data[f'{currency}/EUR']
            else: price_in_base = price_eur

        summary_rows.append(create_summary_row(coin_symbol, label, price_in_base, percent_data, trade_value, currency, is_selected, eur_to_sek))
        
        if is_selected:
            base_coin_price_eur = data.get(f'{currency}/EUR') if currency in COINS_SYMBOLS else 1.0
            selected_coin_box = create_selected_coin_box(label, coin_symbol, price_in_base, currency, base_rate, range_data.get('high_eur'), range_data.get('low_eur'), percent_data, trade_value, ind_trends, diff_24h_eur)
            chart_data_store = {'hist': hist_data_5min, 'price': price_eur, 'base': base_rate, 'coin_label': label}

    last_updated = f"Senast uppdaterad: {time.strftime('%H:%M:%S', time.localtime(data.get('timestamp', time.time())))}"
    return summary_rows, last_updated, selected_coin_box, chart_data_store

@app.callback(
    Output('live-update-graph', 'figure'),
    [Input('chart-data-store', 'data')],
    [State('currency-dropdown', 'value'),
     State('graph-timeframe', 'value'),
     State('coin-dropdown', 'value')]
)
def update_graph(chart_data, currency, timeframe, coin_symbol):
    if not chart_data: return go.Figure()
    
    current_price = chart_data.get('price')
    base_rate = chart_data.get('base', 1.0)
    coin_label = chart_data.get('coin_label')
    ticker = CRYPTO_PAIRS.get(coin_label)
    
    hist_data = []
    time_label = "30m"
    
    if timeframe == '1h_live':
        h_json = r.get(f'OHLC_CACHED_1MIN_{ticker}')
        if h_json: hist_data = json.loads(h_json)
        time_label = "30 min (Live)"
    elif timeframe == '1d':
        h_json = r.get(f'OHLC_CACHED_{OHLC_CACHE_INTERVAL_MIN}MIN_{ticker}')
        if h_json: hist_data = json.loads(h_json)
        time_label = "24 Timmar"
    elif timeframe == '1w':
        h_json = r.get(f'OHLC_1WEEK_{ticker}')
        if h_json: hist_data = json.loads(h_json)
        time_label = "1 Vecka"
    elif timeframe == '1m':
        h_json = r.get(f'OHLC_1MONTH_{ticker}')
        if h_json: hist_data = json.loads(h_json)
        time_label = "1 Månad"

    if not hist_data: return go.Figure()

    times = [datetime.fromtimestamp(item['time']).strftime('%H:%M' if timeframe in ['1h_live', '1d'] else '%d/%m %H:%M') for item in hist_data]
    
    # Valutakonvertering
    if currency == 'SEK' or currency == 'USD':
        prices = [item['price'] * base_rate for item in hist_data]
        current_p_display = current_price * base_rate if current_price else None
    elif currency == 'EUR':
        prices = [item['price'] for item in hist_data]
        current_p_display = current_price
    else:
        # Om currency är en annan kryptovaluta
        data = get_data_from_redis()
        base_price_eur = data.get(f'{currency}/EUR') if data else None
        if base_price_eur:
            prices = [item['price'] / base_price_eur for item in hist_data]
            current_p_display = current_price / base_price_eur if current_price else None
        else:
            prices = [item['price'] for item in hist_data]
            current_p_display = current_price

    figure = go.Figure()
    
    # Huvudlinje
    figure.add_trace(go.Scatter(x=times, y=prices, mode='lines', line=dict(color='#0056b3', width=2), name='Pris'))
    
    # --- NY LOGIK FÖR PUNKTER OCH VEKE ---
    if timeframe == '1h_live':
        # 1. Neongrön punkt (Storlek 12)
        figure.add_trace(go.Scatter(
            x=[times[-1]], y=[current_p_display],
            mode='markers',
            marker=dict(color='#39FF14', size=12, line=dict(width=1, color='black')),
            name='Live'
        ))
        
        # 2. Veke bakom punkten (visar minutens rörelse)
        # Vi ritar en liten vertikal linje som sträcker sig +/- 0.05% från nuvarande pris
        figure.add_shape(
            type="line", x0=times[-1], y0=current_p_display * 0.9995, 
            x1=times[-1], y1=current_p_display * 1.0005,
            line=dict(color="#39FF14", width=3)
        )
    else:
        # 3. Blå punkter (Dubbelt så stora = Storlek 6)
        figure.add_trace(go.Scatter(
            x=[times[-1]], y=[current_p_display],
            mode='markers',
            marker=dict(color='blue', size=6),
            name='Nu'
        ))

    # Trendlinjer (endast på relevanta tidsfönster)
    if timeframe == '1d':
        slope, intercept, start_idx = calculate_trendline(hist_data, len(hist_data))
        if slope is not None:
            x_range = np.arange(len(hist_data))
            trend_y_eur = slope * x_range + intercept
            
            # Konvertera trendlinjen till rätt valuta
            if currency == 'SEK' or currency == 'USD': trend_y = trend_y_eur * base_rate
            elif currency == 'EUR': trend_y = trend_y_eur
            else:
                data = get_data_from_redis()
                base_p = data.get(f'{currency}/EUR') if data else None
                trend_y = trend_y_eur / base_p if base_p else trend_y_eur
                
            figure.add_trace(go.Scatter(x=times, y=trend_y, mode='lines', name='Trend (Period)', line=dict(color='#FFD700', width=3, dash='dot')))

    figure.update_layout(title=f"Prisutveckling: {coin_label} ({time_label})", template="plotly_white", height=500, hovermode="x unified")
    return figure

@app.callback(
    Output('coin-dropdown', 'value'),
    [Input({'type': 'summary-card', 'index': ALL}, 'n_clicks'),
     Input('initial-coin-symbol-store', 'data')],
    [State({'type': 'summary-card', 'index': ALL}, 'id')]
)
def update_dropdown_selection(n_clicks, initial_coin, ids):
    trigger = ctx.triggered_id
    if not trigger or trigger == 'initial-coin-symbol-store':
        return initial_coin if initial_coin else dash.no_update
    
    if isinstance(trigger, dict) and trigger.get('type') == 'summary-card':
        idx = ctx.triggered_id['index']
        return idx
    return dash.no_update

if __name__ == '__main__':
    app.run_server(debug=True)