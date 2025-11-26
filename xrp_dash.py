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
    'LINK (Chainlink)': 'LINK/EUR', 'XLM (Lumen)': 'XLM/EUR', 'HBAR (Hedera)': 'HBAR/EUR', 'TON (Toncoin)': 'XRP/EUR',
    'AAVE (Aave)': 'AAVE/EUR', 'ONDO (Ondo)': 'ONDO/EUR', 'QNT (Quant)': 'QNT/EUR', 'RENDER (Render)': 'RENDER/EUR',
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
}

# Konfiguration för Trendlinjer och H.V. beräkning
TREND_WINDOWS = {
    '1h':  {'blocks': 12,  'color': '#ff7f0e', 'name': 'Trend (1h)',  'weight': 3, 'source': '5min', 'show_line': True},
    '3h':  {'blocks': 36,  'color': '#2ca02c', 'name': 'Trend (3h)',  'weight': 3, 'source': '5min', 'show_line': True},
    '6h':  {'blocks': 72,  'color': '#d62728', 'name': 'Trend (6h)',  'weight': 5, 'source': '5min', 'show_line': True},
    '12h': {'blocks': 144, 'color': '#9467bd', 'name': 'Trend (12h)', 'weight': 5, 'source': '5min', 'show_line': True},
    '18h': {'blocks': 216, 'color': '#8c564b', 'name': 'Trend (18h)', 'weight': 3, 'source': '5min', 'show_line': True},
    '7d':  {'blocks': 7,   'color': '#e377c2', 'name': 'Trend (7d)',  'weight': 0.75, 'source': '1day', 'show_line': False},
    '30d': {'blocks': 30,  'color': '#7f7f7f', 'name': 'Trend (30d)', 'weight': 0.5, 'source': '1day', 'show_line': False},
}

ALERT_THRESHOLDS_UP = sorted([10, 20, 30, 40, 50, 75, 100], reverse=True)
ALERT_THRESHOLDS_DOWN = sorted([-10, -20, -25, -30, -50, -75])
ALERT_PERIODS = ['30m', '1h', '3h', '6h', '12h', '24h']
ALERT_DEBOUNCE_SECONDS = 2 * 3600 # 2 timmar

TRADE_VALUE_ALERTS = sorted([25, 50, 75, 100], reverse=True)
TRADE_VALUE_DEBOUNCE_SECONDS = 1 * 3600 # 1 timme

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
            # HÄR ÄR ÄNDRINGEN: Sparar en dict med både värde och pris
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
        return data['rates'].get('SEK', 11.0)
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching exchange rate: {e}. Using fallback 11.0.")
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
        current_data = {'timestamp': t, 'EUR_SEK_RATE': sek_rate, 'ALL_PERCENT_CHANGE': {}, 'ALL_OHLC_CACHED': {}, 'ALL_24H_RANGE_OHLC': {}}
        
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
                    key = f"alert:{coin_symbol}:{period}:+{threshold}"
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

            for label, ticker in CRYPTO_PAIRS.items():
                coin_symbol = label.split(' ')[0]
                current_price_eur = new_data.get(f'{coin_symbol}/EUR')
                if current_price_eur is None: continue
                    
                periods_ago_24h = 86400 
                ohlc_5min_data = fetch_ohlc_data_from_kraken(ticker, OHLC_CACHE_INTERVAL_MIN, periods_ago_24h) 
                if ohlc_5min_data:
                     redis_instance.set(f'OHLC_CACHED_{OHLC_CACHE_INTERVAL_MIN}MIN_{ticker}', json.dumps(ohlc_5min_data), ex=7200)

                periods_ago_30d = 2592000 
                ohlc_1day_data = fetch_ohlc_data_from_kraken(ticker, 1440, periods_ago_30d) 
                if ohlc_1day_data:
                    redis_instance.set(f'OHLC_1DAY_{ticker}', json.dumps(ohlc_1day_data), ex=86400)

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
                        msg = format_summary_for_telegram(data, data.get('EUR_SEK_RATE', 11.0), timezone_offset_hours)
                        if send_telegram_message(msg): logger.info("✅ Sammanfattning skickad.")
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
        if currency == 'SEK':
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
        display_name = {'7d': '7dgr', '30d': '30dgr', '30m': '30min'}.get(period, period)
        return html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'margin': '3px 0', 'padding': '0 5px', 'fontSize': '0.9em'},
                        children=[html.Span(f"{display_name.capitalize()}:", style={'color': '#6c757d', 'flex': '0 0 50px'}), html.Div(value, style={'flex': '1', 'textAlign': 'right'})])
        
    short_term_keys = [k for k, v in TREND_WINDOWS.items() if v.get('source') == '5min']
    long_term_keys = [k for k, v in TREND_WINDOWS.items() if v.get('source') == '1day']

    diff_24h_base = None
    if diff_24h_eur is not None:
        if currency == 'SEK':
            diff_24h_base = diff_24h_eur * (base_price_eur if base_price_eur else 1.0)
        elif currency == 'EUR':
            diff_24h_base = diff_24h_eur
        elif currency in COINS_SYMBOLS and base_price_eur:
            diff_24h_base = diff_24h_eur / base_price_eur 

    main_price_section = html.Div(style={'flex': '1 1 300px', 'minWidth': '300px', 'paddingRight': '15px'}, children=[
        html.H2(html.Span([html.Span(f"{coin_emoji} ", style={'marginRight': '5px'}), f"{label} ({symbol})"]), style={'fontSize': '1.5em', 'color': '#0056b3', 'marginBottom': '5px', 'textAlign': 'center'}),
        
        html.Div(style={'textAlign': 'center', 'marginTop': '10px'}, children=[
            html.P("Nuvarande Pris", style={'margin': '0', 'color': '#6c757d', 'fontWeight': 'bold', 'fontSize': '0.9em'}),
            html.P(price_text, id='current-price-display', style={'fontSize': '2.5em', 'fontWeight': '800', 'color': price_color, 'margin': '0'}),
        ]),
        
        html.Div(style={'textAlign': 'center', 'fontSize': '0.9em', 'fontWeight': '600', 'color': price_color, 'margin': '0'}, children=[
            html.Span(f"({'+' if diff_24h_base >= 0 else ''}{diff_24h_base:,.4f} {currency}, ", style={'marginRight': '0px'}),
            format_change(change_24h), 
            html.Span(")")
        ] if diff_24h_base is not None else html.P("24h Diff: N/A", style={'fontSize': '0.8em', 'color': '#6c757d'})),

        html.Div(style={'textAlign': 'center', 'marginTop': '15px', 'padding': '5px 0', 'borderTop': '1px solid #dee2e6'}, children=[
            html.P("Handelsvärde (Viktad Trendindikator)", style={'margin': '0', 'color': '#6c757d', 'fontWeight': 'bold', 'fontSize': '0.8em'}),
            html.P(f"{trade_value:,.2f}" if trade_value is not None else "N/A", style={'fontSize': '1.8em', 'fontWeight': '800', 'color': trade_value_color, 'margin': '0'})
        ])
    ])

    changes_section = html.Div(style={'flex': '1 1 250px', 'minWidth': '250px', 'padding': '0 15px', 'borderLeft': '1px solid #dee2e6'}, children=[
        html.P("Prisrörelser (%) & 24h Intervall", style={'margin': '0 0 10px 0', 'color': '#495057', 'fontWeight': 'bold', 'textAlign': 'center', 'fontSize': '0.9em'}),
        
        html.Div(style={'padding': '5px 0 10px 0', 'borderBottom': '1px solid #dee2e6', 'fontSize': '0.9em'}, children=[
            html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'marginBottom': '5px'}, children=[
                html.Span("Hög 24h:", style={'fontWeight': 'bold', 'color': 'green'}), 
                html.Span(f"{format_price_display(high_display)} {currency}" if high_display is not None else "N/A", style={'color': 'green', 'fontWeight': '600'})
            ]),
            html.Div(style={'display': 'flex', 'justifyContent': 'space-between'}, children=[
                html.Span("Låg 24h:", style={'fontWeight': 'bold', 'color': 'red'}), 
                html.Span(f"{format_price_display(low_display)} {currency}" if low_display is not None else "N/A", style={'color': 'red', 'fontWeight': '600'})
            ]),
        ]),
        
        html.Div(style={'paddingTop': '10px', 'display': 'grid', 'gridTemplateColumns': '1fr 1fr', 'gap': '5px 10px'}, children=[
            create_change_row('30m', format_change(percent_data.get('30m'))),
            create_change_row('12h', format_change(percent_data.get('12h'))),
            create_change_row('1h', format_change(percent_data.get('1h'))),
            create_change_row('18h', format_change(percent_data.get('18h'))),
            create_change_row('3h', format_change(percent_data.get('3h'))),
            create_change_row('7d', format_change(percent_data.get('7d'))), 
            create_change_row('6h', format_change(percent_data.get('6h'))),
            create_change_row('30d', format_change(percent_data.get('30d'))), 
        ])
    ])

    # --- LOKAL FUNKTION FÖR ATT RENDERA TRENDRADEN ---
    def render_trend_row(key):
        data_obj = individual_trends.get(key)
        # Hantera både gammalt format (float) och nytt format (dict) för säkerhets skull
        val = None
        trend_price = None
        
        if isinstance(data_obj, dict):
            val = data_obj.get('val')
            raw_price = data_obj.get('price')
            if raw_price is not None:
                # Omvandla trendpriset till vald valuta (SEK etc) med multiplier
                trend_price = raw_price * multiplier
        elif isinstance(data_obj, (int, float)):
            val = data_obj

        val_str = f"{val:,.2f}" if val is not None else "N/A"
        price_str = f" ({format_price_display(trend_price)})" if trend_price is not None else ""
        
        color = '#6c757d'
        if val is not None:
            if val > 0: color = '#006400'
            elif val < 0: color = '#8B0000'

        return html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'marginBottom': '3px'}, children=[
            html.Span(f"{TREND_WINDOWS[key]['name'].split(' ')[1]}:", style={'color': '#6c757d', 'fontWeight': 'bold'}), 
            html.Span(f"{val_str}{price_str}", style={'color': color, 'fontWeight': '600'})
        ])
    # -------------------------------------------------

    trend_section = html.Div(style={'flex': '1 1 200px', 'minWidth': '200px', 'paddingLeft': '15px', 'borderLeft': '1px solid #dee2e6'}, children=[
        html.P("Trendvärden (Hₓ) - Riktning/Vikt", style={'margin': '0 0 10px 0', 'color': '#495057', 'fontWeight': 'bold', 'textAlign': 'center', 'fontSize': '0.9em'}),
        
        html.P("Kort Sikt (5m data)", style={'margin': '0 0 5px 0', 'color': '#6c757d', 'fontSize': '0.8em', 'fontWeight': 'bold'}),
        html.Div([
            render_trend_row(key) for key in short_term_keys if key in individual_trends 
        ]),
        
        html.P("Lång Sikt (1d data)", style={'margin': '10px 0 5px 0', 'color': '#6c757d', 'fontSize': '0.8em', 'fontWeight': 'bold', 'borderTop': '1px dotted #dee2e6', 'paddingTop': '5px'}),
        html.Div([
            render_trend_row(key) for key in long_term_keys if key in individual_trends 
        ]),
    ])

    return html.Div(id='current-price-box', style={'border': '2px solid #0056b3', 'borderRadius': '10px', 'padding': '15px', 'marginBottom': '20px', 'backgroundColor': '#f8f9fa'}, children=[
            html.Div(style={'display': 'flex', 'justifyContent': 'space-around', 'alignItems': 'flex-start', 'flexWrap': 'wrap', 'gap': '10px'}, children=[
                main_price_section, 
                changes_section, 
                trend_section
            ])
        ])


app.layout = html.Div(style={'backgroundColor': '#f8f9fa', 'minHeight': '100vh', 'padding': '40px 10px', 'fontFamily': 'Roboto, Arial, sans-serif'}, children=[
    html.Div(style={'maxWidth': '1400px', 'margin': '40px auto', 'padding': '30px', 'borderRadius': '12px', 'boxShadow': '0 4px 12px rgba(0,0,0,0.1)', 'backgroundColor': 'white', 'border': '1px solid #dee2e6'}, children=[
        html.H1('📈 DJ-Investment Dashboard (Kraken Live)', style={'textAlign': 'center', 'color': '#0056b3', 'marginBottom': '30px', 'fontSize': '1.8em'}),
        html.Div(style={'display': 'flex', 'gap': '20px', 'marginBottom': '20px', 'flexWrap': 'wrap'}, children=[
            html.Div(style={'flex': '0 0 200px', 'minWidth': '200px'}, children=[
                html.H3('⚙️ Kontroller', style={'fontSize': '1.3em', 'color': '#495057', 'marginBottom': '15px'}),
                html.Div(style={'marginBottom': '20px'}, children=[
                    html.Label("Välj kryptovaluta:", style={'marginBottom': '5px', 'fontWeight': 'bold', 'color': '#495057', 'display': 'block'}),
                    dcc.Dropdown(id='coin-dropdown', options=[{'label': label, 'value': label.split(' ')[0]} for label in COINS_LABELS], value=DEFAULT_COIN_SYMBOL, clearable=False),
                ]),
                html.Div(children=[
                    html.Label("Välj basvaluta/krypto:", style={'marginBottom': '5px', 'fontWeight': 'bold', 'color': '#495057', 'display': 'block'}),
                    dcc.Dropdown(id='currency-dropdown', options=[{'label': f'{c} ({c})', 'value': c} for c in BASE_CURRENCIES], value='EUR', clearable=False),
                ]),
            ]),
            html.Div(style={'flex': '1 1 600px', 'minWidth': '600px'}, children=[
                html.Div(id='current-price-summary-box-container'),
                html.Div(id='last-updated', style={'textAlign': 'center', 'fontSize': '0.9em', 'color': '#6c757d', 'marginBottom': '0px'}),
            ]),
            dcc.Store(id='chart-data-store'), 
            dcc.Store(id='current-currency-store'),
            dcc.Store(id='initial-coin-symbol-store', data=DEFAULT_COIN_SYMBOL),
        ]),
        
        html.Div(style={'paddingTop': '20px', 'borderTop': '1px solid #dee2e6', 'marginBottom': '30px'}, children=[
            html.Div(style={'textAlign': 'center', 'marginBottom': '10px'}, children=[
                 html.Label("Visa Trendlinjer:", style={'fontWeight': 'bold', 'color': '#495057', 'marginRight': '15px', 'fontSize': '0.9em'}),
                 dcc.Checklist(
                     id='trendline-checkboxes',
                     options=[{'label': config['name'].split(' ')[1].replace('(', '').replace(')', ''), 'value': key} for key, config in TREND_WINDOWS.items() if config.get('show_line')],
                     value=[k for k, v in TREND_WINDOWS.items() if v.get('show_line')], 
                     inline=True,
                     style={'display': 'inline-block'}
                 ),
            ]),
            dcc.Loading(id="loading-1", type="circle", children=[dcc.Graph(id='live-update-graph', config={'displayModeBar': False})]),
        ]),
        
        html.Div(id='crypto-summary-container', style={'marginTop': '30px', 'paddingTop': '20px', 'borderTop': '1px solid #dee2e6', 'marginBottom': '30px'}, children=[
             html.H3('📊 Sammanfattning: Handelsvärde & Prisrörelser', style={'fontSize': '1.3em', 'color': '#0056b3', 'marginBottom': '10px'}),
             dcc.Loading(id="loading-2", type="dot", children=[html.Div(id='crypto-summary')])
        ]),
        
        html.Div(style={'marginTop': '40px', 'padding': '20px', 'border': '1px solid #17a2b8', 'borderRadius': '6px', 'backgroundColor': '#e8f7fa'}, children=[
            html.H3('🔔 Automatisk Telegram Alert-status (Aktiv)', style={'fontSize': '1.3em', 'color': '#17a2b8', 'marginBottom': '10px'}),
            html.P('Aviseringar skickas automatiskt när det högsta/lägsta tröskelvärdet uppnås för Prisrörelser eller *positivt* Handelsvärde:', style={'margin': '0 0 10px 0'}),
            html.Div(style={'display': 'flex', 'gap': '50px', 'flexWrap': 'wrap'}, children=[
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
    dcc.Interval(id='interval-component', interval=UPDATE_INTERVAL_SECONDS_DATA*1000, n_intervals=0)
])

@app.callback(
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
        loading_box = create_selected_coin_box("Laddar...", "", 0.0, currency, 11.0, None, None, {}, None, {}, None)
        return loading_box, "Väntar...", None, currency, html.Div("Laddar...")

    eur_to_sek = data.get('EUR_SEK_RATE', 11.0)
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
    elif currency == 'EUR':
        current_price_base = current_price_eur
    elif currency in COINS_SYMBOLS:
        base_price_eur = data.get(f'{currency}/EUR') 
        current_price_base = (current_price_eur / base_price_eur) if current_price_eur and base_price_eur else None
    else:
        current_price_base = current_price_eur

    selected_ticker = CRYPTO_PAIRS.get(coin_label, f'{coin_symbol}/EUR')
    ohlc_interval = OHLC_CACHE_INTERVAL_MIN 
    hist_data_5min = json.loads(r.get(f'OHLC_CACHED_{ohlc_interval}MIN_{selected_ticker}') or '[]') if r else []
    hist_data_1day = json.loads(r.get(f'OHLC_1DAY_{selected_ticker}') or '[]') if r else []
    
    trade_value, individual_trends, chart_data_store = None, {}, None
    if hist_data_5min and current_price_eur is not None:
        hist_5min_curr = hist_data_5min + [{'time': timestamp, 'price': current_price_eur}]
        hist_1day_curr = hist_data_1day + [{'time': timestamp, 'price': current_price_eur}]
        
        trade_value, individual_trends = calculate_trade_value(hist_5min_curr, current_price_eur, hist_1day_curr)
        
        prices_eur = [item['price'] for item in hist_5min_curr]
        chart_data_store = {
            'historical_data': hist_5min_curr, 
            'current_price_eur': current_price_eur, 
            'max_ohlc_eur': max(prices_eur) if prices_eur else None, 
            'min_ohlc_eur': min(prices_eur) if prices_eur else None, 
            'eur_to_sek': eur_to_sek, 
            'base_price_eur': base_price_eur, 
            'coin_symbol': coin_symbol, 
            'trade_value': trade_value,
            'individual_trends': individual_trends 
        }

    percent_data = data.get('ALL_PERCENT_CHANGE', {}).get(coin_symbol, {})
    range_data = data.get('ALL_24H_RANGE_OHLC', {}).get(coin_symbol, {})
    
    summary_box = create_selected_coin_box(coin_label, coin_symbol, current_price_base or 0.0, currency, base_price_eur, range_data.get('high_eur'), range_data.get('low_eur'), percent_data, trade_value, individual_trends, diff_24h_eur)
        
    summary_data = []
    for label in COINS_LABELS:
        sl = label.split(' ')[0]
        tl = CRYPTO_PAIRS[label]
        pe = data.get(f'{sl}/EUR')
        pd = data.get('ALL_PERCENT_CHANGE', {}).get(sl, {})
        h5 = json.loads(r.get(f'OHLC_CACHED_{ohlc_interval}MIN_{tl}') or '[]') if r else []
        h1 = json.loads(r.get(f'OHLC_1DAY_{tl}') or '[]') if r else []
        
        tv_int = None
        if h5 and pe:
            tv_val, _ = calculate_trade_value(h5 + [{'time': timestamp, 'price': pe}], pe, h1 + [{'time': timestamp, 'price': pe}])
            if tv_val is not None: tv_int = int(round(tv_val))
        
        pb = pe
        if currency == 'SEK': pb = pe * eur_to_sek if pe else None
        elif currency != 'EUR' and base_price_eur: pb = pe / base_price_eur if pe else None

        summary_data.append({
            'symbol': sl, 
            'label': label, 
            'price': pb, 
            'percent': pd, 
            'trade_value': tv_int, 
            'sort_tv': tv_int if tv_int else -float('inf'), 
            's30': pd.get('30m', -float('inf')), 
            's1h': pd.get('1h', -float('inf')), 
            's6h': pd.get('6h', -float('inf')),
            'sort_24h': pd.get('24h', -float('inf')),
            'sort_7d': pd.get('7d', -float('inf')),
            'sort_30d': pd.get('30d', -float('inf'))
        })

    summary_data.sort(
        key=lambda x: (
            x['sort_24h'] if x['sort_24h'] is not None else -float('inf'),
            x['sort_7d'] if x['sort_7d'] is not None else -float('inf'),
            x['sort_30d'] if x['sort_30d'] is not None else -float('inf')
        ), 
        reverse=True
    )

    
    header_style = {'display': 'flex', 'justifyContent': 'space-between', 'fontWeight': 'bold', 'padding': '7px 0', 'borderBottom': '2px solid #0056b3', 'backgroundColor': '#f0f0f0', 'marginBottom': '5px', 'color': '#495057', 'fontSize': '0.85em'}
    header_cols = [
        html.Div("Valuta", style={'flex': '0 0 160px', 'paddingLeft': '5px'}), 
        html.Div(f"Pris ({currency})", style={'flex': '0 0 140px', 'textAlign': 'right'}),
        html.Div("30m", style={'flex': '1', 'textAlign': 'right'}), 
        html.Div("1h", style={'flex': '1', 'textAlign': 'right'}), 
        html.Div("3h", style={'flex': '1', 'textAlign': 'right'}), 
        html.Div("6h", style={'flex': '1', 'textAlign': 'right'}),
        html.Div("12h", style={'flex': '1', 'textAlign': 'right'}), 
        html.Div("24h", style={'flex': '1', 'textAlign': 'right'}), 
        html.Div("7d", style={'flex': '1', 'textAlign': 'right'}), 
        html.Div("30d", style={'flex': '1', 'textAlign': 'right'}), 
        html.Div("H.V.", style={'flex': '0 0 80px', 'textAlign': 'right', 'paddingRight': '5px'})
    ]
    
    rows = [create_summary_row(item['symbol'], item['label'], item['price'], item['percent'], item['trade_value'], currency, item['symbol'] == coin_symbol, eur_to_sek) for item in summary_data]
    return summary_box, updated_text, chart_data_store, currency, html.Div([html.Div(header_cols, style=header_style)] + rows)

@app.callback(
    Output('live-update-graph', 'figure'),
    [Input('chart-data-store', 'data'), Input('current-currency-store', 'data'), Input('trendline-checkboxes', 'value')],
    [State('coin-dropdown', 'value')]
)
def update_trendline_visibility(chart_data_store, currency, selected_trends, coin_symbol):
    if chart_data_store is None: return go.Figure()
    hist_data = chart_data_store['historical_data']
    eur_to_sek = chart_data_store['eur_to_sek']
    base_price_eur = chart_data_store['base_price_eur'] 
    coin_label = SYMBOL_TO_LABEL.get(coin_symbol, coin_symbol)
    
    figure = go.Figure()
    prices_eur = [item['price'] for item in hist_data]
    
    if currency == 'SEK': prices = [p * eur_to_sek for p in prices_eur]
    elif currency == 'EUR': prices = prices_eur
    elif base_price_eur: prices = [p / base_price_eur for p in prices_eur]
    else: prices = prices_eur

    times = [time.strftime('%H:%M', time.gmtime(item['time'] + 3600)) for item in hist_data]
    figure.add_trace(go.Scatter(x=times, y=prices, mode='lines+markers', name=f'Kurs (5 min)', line=dict(color='#0056b3', width=3)))

    high_val, low_val = max(prices) if prices else None, min(prices) if prices else None
    if high_val: figure.add_hline(y=high_val, line_dash="dash", line_color="green", annotation_text="24h Hög")
    if low_val: figure.add_hline(y=low_val, line_dash="dash", line_color="red", annotation_text="24h Låg", annotation_position="bottom left")

    for key in selected_trends:
        config = TREND_WINDOWS.get(key)
        if not config or not config.get('show_line', False) or config.get('source') != '5min': continue
        if len(hist_data) >= config['blocks']:
            slope, intercept, start_idx = calculate_trendline(hist_data, config['blocks'])
            trend_y_eur = slope * np.arange(config['blocks']) + intercept
            
            if currency == 'SEK': trend_y = trend_y_eur * eur_to_sek
            elif currency == 'EUR': trend_y = trend_y_eur
            elif base_price_eur: trend_y = trend_y_eur / base_price_eur
            else: trend_y = trend_y_eur
            
            figure.add_trace(go.Scatter(x=times[start_idx:], y=trend_y, mode='lines', name=config['name'], line=dict(color=config['color'], width=2, dash='dash')))

    figure.update_layout(title=f"Prisutveckling: {coin_label}", template="plotly_white", height=500, hovermode="x unified")
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
         if not any(n_clicks): return dash.no_update
         return trigger['index']
         
    return dash.no_update

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8050))
    app.run_server(debug=False, host='0.0.0.0', port=port)