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

# URL för logotyper (Open Source Repository)
LOGO_BASE_URL = "https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/"

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
    """Genererar URL för officiell logotyp."""
    s = symbol.lower()
    return f"{LOGO_BASE_URL}{s}.png"

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

                    periods_ago_1y = 365 * 86400 * 1.1 
                    ohlc_1day_data = fetch_ohlc_data_from_kraken(ticker, 1440, periods_ago_1y) 
                    if ohlc_1day_data:
                         redis_instance.set(f'OHLC_1DAY_{ticker}', json.dumps(ohlc_1day_data), ex=86400)
                         
                    # Hämta 15min data som grund för Live-vyn 
                    # Vi hämtar 12 timmars historik nu
                    ohlc_live_view = fetch_ohlc_data_from_kraken(ticker, 15, 3600 * 12)
                    if ohlc_live_view:
                        redis_instance.set(f'OHLC_LIVE_VIEW_{ticker}', json.dumps(ohlc_live_view), ex=300)
                
                else:
                    cached_5min = redis_instance.get(f'OHLC_CACHED_{OHLC_CACHE_INTERVAL_MIN}MIN_{ticker}')
                    ohlc_5min_data = json.loads(cached_5min) if cached_5min else []
                    
                    cached_1day = redis_instance.get(f'OHLC_1DAY_{ticker}')
                    ohlc_1day_data = json.loads(cached_1day) if cached_1day else []

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
                        current_high = max(max(prices_eur), current_price_eur)
                        current_low = min(min(prices_eur), current_price_eur)
                        all_24h_range_ohlc[coin_symbol] = {'high_eur': current_high, 'low_eur': current_low}

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

            if redis_instance:
                check_and_send_alerts(alert_data_for_sending, redis_instance)
                check_and_send_trade_value_alerts(trade_value_alert_data, redis_instance)

            new_data['ALL_PERCENT_CHANGE'] = all_percent_changes
            new_data['ALL_24H_RANGE_OHLC'] = all_24h_range_ohlc
            redis_instance.set('crypto_data', json.dumps(new_data), ex=UPDATE_INTERVAL_FAST + 60)
            logger.debug("✅ Snabb uppdatering sparad (10s).")

            time.sleep(max(0, UPDATE_INTERVAL_FAST - (time.time() - cycle_start_time)))

        except Exception as e:
            logger.error(f"❌ Fel i bakgrundstråd: {e}")
            time.sleep(30)

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

# --- Helpers för Layout ---

def create_summary_row(symbol, label, price, percent_data, trade_value, currency, is_selected, eur_to_sek):
    row_style = {'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center', 'padding': '5px 0', 'borderBottom': '1px solid #eee', 'fontSize': '0.85em', 'cursor': 'pointer', 'backgroundColor': '#fff'}
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

    # Logo istället för emoji
    logo_img = html.Img(src=get_logo_url(symbol), style={'width': '20px', 'height': '20px', 'marginRight': '8px', 'verticalAlign': 'middle'})

    price_div = html.Div([
        html.Span(price_str, style={'color': '#495057'}),
        html.Span(change_str, style={'color': change_color, 'fontSize': '0.9em', 'fontWeight': 'normal'})
    ], style={'flex': '0 0 140px', 'textAlign': 'right', 'fontWeight': 'bold', 'paddingRight': '5px'})

    return html.Div([
        html.Div([logo_img, html.Span(symbol, style={'fontWeight': 'bold'})], style={'flex': '0 0 90px', 'display': 'flex', 'alignItems': 'center'}),
        price_div,
        html.Div(format_trade_value_display(trade_value), style={'flex': '0 0 50px', 'textAlign': 'right', 'paddingRight': '10px'})
    ], style=row_style, id={'type': 'summary-card', 'index': symbol})

# --- Dash App Setup ---
app = dash.Dash(__name__, meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1.0"}])
server = app.server

app.layout = html.Div([
    dcc.Interval(id='fast-update', interval=UPDATE_INTERVAL_FAST * 1000, n_intervals=0),
    dcc.Store(id='initial-coin-symbol-store', data=DEFAULT_COIN_SYMBOL),
    
    # Header
    html.Div([
        html.Div([
            html.Img(id='header-logo', src=get_logo_url(DEFAULT_COIN_SYMBOL), style={'width': '40px', 'height': '40px', 'marginRight': '15px'}),
            html.H2(id='header-title', children="Crypto Dashboard", style={'margin': '0', 'color': '#0056b3', 'fontSize': '1.5em'})
        ], style={'display': 'flex', 'alignItems': 'center'})
    ], style={'padding': '15px 20px', 'backgroundColor': '#fff', 'borderBottom': '2px solid #0056b3', 'marginBottom': '15px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),

    html.Div([
        # Vänster Kolumn: Marknadsöversikt
        html.Div([
            html.Div([
                html.H4("Marknadsöversikt", style={'margin': '0 0 15px 0', 'color': '#333', 'borderBottom': '1px solid #ddd', 'paddingBottom': '5px'}),
                html.Div([
                    html.Div("VALUTA", style={'flex': '0 0 90px', 'fontSize': '0.75em', 'color': '#666', 'fontWeight': 'bold'}),
                    html.Div("PRIS", style={'flex': '0 0 140px', 'fontSize': '0.75em', 'color': '#666', 'fontWeight': 'bold', 'textAlign': 'right', 'paddingRight': '5px'}),
                    html.Div("H.V.", style={'flex': '0 0 50px', 'fontSize': '0.75em', 'color': '#666', 'fontWeight': 'bold', 'textAlign': 'right', 'paddingRight': '10px'})
                ], style={'display': 'flex', 'justifyContent': 'space-between', 'padding': '0 0 5px 0', 'borderBottom': '1px solid #eee'}),
                html.Div(id='market-summary-list', style={'height': '700px', 'overflowY': 'auto'})
            ], style={'backgroundColor': '#fff', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.05)'})
        ], className='four columns', style={'width': '33%', 'marginRight': '1%'}),

        # Höger Kolumn: Grafer och Detaljer
        html.Div([
            # Rad 1: Kontroller
            html.Div([
                html.Div([
                    html.Label("Välj Valuta:", style={'fontWeight': 'bold', 'fontSize': '0.9em'}),
                    dcc.Dropdown(id='coin-dropdown', options=[{'label': k, 'value': k.split(' ')[0]} for k in COINS_LABELS], value=DEFAULT_COIN_SYMBOL, clearable=False)
                ], style={'width': '48%', 'display': 'inline-block', 'marginRight': '4%'}),
                html.Div([
                    html.Label("Basvaluta:", style={'fontWeight': 'bold', 'fontSize': '0.9em'}),
                    dcc.Dropdown(id='currency-dropdown', options=[{'label': c, 'value': c} for c in BASE_CURRENCIES], value='EUR', clearable=False)
                ], style={'width': '48%', 'display': 'inline-block'})
            ], style={'backgroundColor': '#fff', 'padding': '15px', 'borderRadius': '8px', 'marginBottom': '15px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.05)'}),

            # Rad 2: Pris & Statistik
            html.Div(id='price-stats-container', style={'marginBottom': '15px'}),

            # Rad 3: Huvudgraf
            html.Div([
                html.Div([
                    html.Div([
                        dcc.RadioItems(
                            id='timeframe-selector',
                            options=[
                                {'label': '12 Timmar (Live)', 'value': 'live'},
                                {'label': '1 Vecka', 'value': '1w'},
                                {'label': '1 Månad', 'value': '1m'}
                            ],
                            value='live',
                            inline=True,
                            labelStyle={'marginRight': '15px', 'fontSize': '0.9em', 'fontWeight': 'bold', 'color': '#555'}
                        )
                    ], style={'marginBottom': '10px', 'padding': '0 10px'}),
                    dcc.Graph(id='price-graph', config={'displayModeBar': False})
                ], style={'backgroundColor': '#fff', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.05)'})
            ], style={'marginBottom': '15px'}),
            
            # Rad 4: Handelsvärde (H.V.) Detaljer
            html.Div(id='trade-value-details-container')

        ], className='eight columns', style={'width': '65%'})
    ], style={'display': 'flex', 'padding': '0 20px'})
], style={'backgroundColor': '#f4f7f9', 'minHeight': '100vh', 'fontFamily': '"Segoe UI", Roboto, Helvetica, Arial, sans-serif'})

# --- Callbacks ---

@app.callback(
    [Output('market-summary-list', 'children'),
     Output('header-logo', 'src'),
     Output('header-title', 'children'),
     Output('price-stats-container', 'children'),
     Output('trade-value-details-container', 'children')],
    [Input('fast-update', 'n_intervals'),
     Input('coin-dropdown', 'value'),
     Input('currency-dropdown', 'value')]
)
def update_fast_elements(n, selected_coin, currency):
    data = get_data_from_redis()
    if not data: return dash.no_update
    
    rates = data.get('EXCHANGE_RATES', {})
    eur_to_sek = rates.get('SEK', 11.0)
    eur_to_usd = rates.get('USD', 1.05)

    # 1. Bygg marknadsöversikten
    summary_rows = []
    for label in COINS_LABELS:
        coin_symbol = label.split(' ')[0]
        ticker = CRYPTO_PAIRS[label]
        price_eur = data.get(f'{coin_symbol}/EUR')
        percent_data = data.get('ALL_PERCENT_CHANGE', {}).get(coin_symbol, {})
        
        # Beräkna Trade Value för raden
        ohlc_5min = json.loads(r.get(f'OHLC_CACHED_5MIN_{ticker}')) if r and r.get(f'OHLC_CACHED_5MIN_{ticker}') else []
        ohlc_1day = json.loads(r.get(f'OHLC_1DAY_{ticker}')) if r and r.get(f'OHLC_1DAY_{ticker}') else []
        
        row_trade_value = None
        if ohlc_5min and price_eur is not None:
             h_5min = ohlc_5min.copy()
             h_5min.append({'time': data.get('timestamp'), 'price': price_eur})
             h_1day = ohlc_1day.copy()
             h_1day.append({'time': data.get('timestamp'), 'price': price_eur})
             row_trade_value, _ = calculate_trade_value(h_5min, price_eur, h_1day)

        summary_rows.append(create_summary_row(coin_symbol, label, price_eur, percent_data, row_trade_value, 'EUR', coin_symbol == selected_coin, eur_to_sek))

    # 2. Uppdatera Header Info
    header_logo = get_logo_url(selected_coin)
    header_title = f"{SYMBOL_TO_LABEL.get(selected_coin, selected_coin)} Dashboard"

    # 3. Uppdatera Pris & Statistik (Topp-boxarna)
    price_eur = data.get(f'{selected_coin}/EUR')
    
    # Konvertera pris till vald basvaluta
    price_in_base = price_eur
    base_symbol = currency
    if currency == 'SEK': price_in_base = price_eur * eur_to_sek
    elif currency == 'USD': price_in_base = price_eur * eur_to_usd
    elif currency in COINS_SYMBOLS:
        other_coin_price_eur = data.get(f'{currency}/EUR')
        if other_coin_price_eur and other_coin_price_eur > 0:
            price_in_base = price_eur / other_coin_price_eur
    
    # 24h Range
    range_data = data.get('ALL_24H_RANGE_OHLC', {}).get(selected_coin, {})
    high_eur = range_data.get('high_eur', price_eur)
    low_eur = range_data.get('low_eur', price_eur)
    
    def conv_p(p_eur):
        if currency == 'SEK': return p_eur * eur_to_sek
        if currency == 'USD': return p_eur * eur_to_usd
        if currency in COINS_SYMBOLS:
            ref = data.get(f'{currency}/EUR')
            return p_eur / ref if ref else p_eur
        return p_eur

    percent_data = data.get('ALL_PERCENT_CHANGE', {}).get(selected_coin, {})
    
    # Beräkna Handelsvärde och trender för detaljboxen
    ticker_selected = CRYPTO_PAIRS[SYMBOL_TO_LABEL.get(selected_coin)]
    ohlc_5min_sel = json.loads(r.get(f'OHLC_CACHED_5MIN_{ticker_selected}')) if r and r.get(f'OHLC_CACHED_5MIN_{ticker_selected}') else []
    ohlc_1day_sel = json.loads(r.get(f'OHLC_1DAY_{ticker_selected}')) if r and r.get(f'OHLC_1DAY_{ticker_selected}') else []
    
    current_tv, individual_trends = None, {}
    if ohlc_5min_sel and price_eur is not None:
        h_5min_sel = ohlc_5min_sel.copy()
        h_5min_sel.append({'time': data.get('timestamp'), 'price': price_eur})
        h_1day_sel = ohlc_1day_sel.copy()
        h_1day_sel.append({'time': data.get('timestamp'), 'price': price_eur})
        current_tv, individual_trends = calculate_trade_value(h_5min_sel, price_eur, h_1day_sel)

    # UI för Pris-boxar
    stats_ui = html.Div([
        html.Div([
            html.Small(f"PRIS ({base_symbol})", style={'color': '#666', 'fontSize': '0.7em', 'fontWeight': 'bold'}),
            html.Div(format_price_display(price_in_base), style={'fontSize': '1.8em', 'fontWeight': 'bold', 'color': '#0056b3'})
        ], style={'flex': '1', 'backgroundColor': '#fff', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.05)', 'marginRight': '10px'}),
        
        html.Div([
            html.Small("24H HÖGST / LÄGST", style={'color': '#666', 'fontSize': '0.7em', 'fontWeight': 'bold'}),
            html.Div([
                html.Span(format_price_display(conv_p(high_eur)), style={'color': '#28a745', 'fontWeight': 'bold'}),
                html.Span(" / ", style={'color': '#ccc'}),
                html.Span(format_price_display(conv_p(low_eur)), style={'color': '#dc3545', 'fontWeight': 'bold'})
            ], style={'fontSize': '1.2em', 'marginTop': '5px'})
        ], style={'flex': '1', 'backgroundColor': '#fff', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.05)', 'marginRight': '10px'}),

        html.Div([
            html.Small("HANDELSVÄRDE (H.V.)", style={'color': '#666', 'fontSize': '0.7em', 'fontWeight': 'bold'}),
            html.Div(format_trade_value_display(current_tv), style={'fontSize': '1.8em', 'fontWeight': 'bold', 'marginTop': '5px'})
        ], style={'flex': '0 0 180px', 'backgroundColor': '#fff', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.05)'})
    ], style={'display': 'flex', 'justifyContent': 'space-between'})

    # UI för Handelsvärde Detaljer
    tv_details_rows = []
    if individual_trends:
        # Sortera TREND_WINDOWS i den ordning vi vill visa dem
        sorted_keys = ['1h', '3h', '6h', '12h', '18h', '7d', '30d', '6m', '1y']
        for key in sorted_keys:
            trend = individual_trends.get(key)
            if trend:
                val = trend['val']
                trend_price = trend['price']
                color = '#28a745' if val > 0 else '#dc3545'
                bg_color = '#eafaf1' if val > 0 else '#fdf2f2'
                
                tv_details_rows.append(html.Div([
                    html.Div(key.upper(), style={'fontWeight': 'bold', 'fontSize': '0.75em', 'color': '#666'}),
                    html.Div(f"{'+' if val > 0 else ''}{val:.1f}", style={'color': color, 'fontWeight': 'bold', 'fontSize': '1.1em'}),
                    html.Div(format_price_display(conv_p(trend_price)), style={'fontSize': '0.7em', 'color': '#888'})
                ], style={'flex': '1', 'textAlign': 'center', 'padding': '10px', 'backgroundColor': bg_color, 'margin': '0 5px', 'borderRadius': '6px'}))

    tv_ui = html.Div([
        html.H5("Analys: Trendpåverkan per tidsfönster", style={'margin': '0 0 10px 0', 'fontSize': '0.9em', 'color': '#333'}),
        html.Div(tv_details_rows, style={'display': 'flex', 'justifyContent': 'space-between'})
    ], style={'backgroundColor': '#fff', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.05)'})

    return summary_rows, header_logo, header_title, stats_ui, tv_ui

@app.callback(
    Output('price-graph', 'figure'),
    [Input('fast-update', 'n_intervals'),
     Input('coin-dropdown', 'value'),
     Input('currency-dropdown', 'value'),
     Input('timeframe-selector', 'value')]
)
def update_graph(n, selected_coin, currency, timeframe):
    data = get_data_from_redis()
    if not data: return go.Figure()

    coin_label = SYMBOL_TO_LABEL.get(selected_coin, selected_coin)
    ticker = CRYPTO_PAIRS[coin_label]
    
    # Hämta historisk data baserat på vald vy
    hist_data = []
    time_label = "12 Timmar"
    
    if timeframe == 'live':
        cached_live = r.get(f'OHLC_LIVE_VIEW_{ticker}') if r else None
        hist_data = json.loads(cached_live) if cached_live else []
        time_label = "12 Timmar (Live)"
    elif timeframe == '1w':
        cached_1w = r.get(f'OHLC_1WEEK_{ticker}') if r else None
        hist_data = json.loads(cached_1w) if cached_1w else []
        time_label = "1 Vecka"
    elif timeframe == '1m':
        cached_1m = r.get(f'OHLC_1MONTH_{ticker}') if r else None
        hist_data = json.loads(cached_1m) if cached_1m else []
        time_label = "1 Månad"

    if not hist_data:
        fig = go.Figure()
        fig.update_layout(title="Hämtar data...")
        return fig

    # Konverteringsfunktion för grafen
    rates = data.get('EXCHANGE_RATES', {})
    def convert_currency(price_eur_val):
        if currency == 'SEK': return price_eur_val * rates.get('SEK', 11.0)
        if currency == 'USD': return price_eur_val * rates.get('USD', 1.05)
        if currency in COINS_SYMBOLS:
            ref_price = data.get(f'{currency}/EUR')
            return price_eur_val / ref_price if ref_price else price_eur_val
        return price_eur_val

    times = [datetime.fromtimestamp(item['time']) for item in hist_data]
    prices = [convert_currency(item['price']) for item in hist_data]

    # Skapa grafen
    figure = go.Figure()
    
    # Candlestick eller Line? Vi kör Line för renhet men med snygg färg
    figure.add_trace(go.Scatter(
        x=times, y=prices,
        mode='lines',
        line=dict(color='#0056b3', width=2),
        fill='tozeroy',
        fillcolor='rgba(0, 86, 179, 0.05)',
        name='Pris'
    ))

    # Trendlinje om vi är i vecka/månad vy
    if timeframe in ['1w', '1m']:
         # Trendlinje för vecka/månad
         slope, intercept, start_idx = calculate_trendline(hist_data, len(hist_data))
         if slope is not None:
             trend_y_eur = slope * np.arange(len(hist_data)) + intercept
             trend_y = convert_currency(trend_y_eur)
             figure.add_trace(go.Scatter(x=times, y=trend_y, mode='lines', name=f'Trend ({timeframe})', line=dict(color='#FFD700', width=2, dash='dot')))

    figure.update_layout(
        title=f"Prisutveckling: {coin_label} ({time_label})", 
        template="plotly_white", 
        height=500, 
        hovermode="x unified",
        margin=dict(r=50) 
    )
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
        return trigger.get('index')
    
    return dash.no_update

if __name__ == '__main__':
    app.run_server(debug=True)