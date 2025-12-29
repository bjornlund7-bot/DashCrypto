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
    'AUCTION (Bounce)': 'AUCTION/槌', 'MOVR (Moonriver)': 'MOVR/EUR', 'SSV (SSV Network)': 'SSV/EUR',
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
        sort_key_24h = percent_data_loop.get('24h') if percent_data_loop.get('24h') is not None else -float('inf')
        summary_data.append({
            'symbol': coin_symbol_loop,
            'price_eur': price_eur,
            'percent_data': percent_data_loop,
            'trade_value_int': trade_value_int, 
            'sort_trade_value': trade_value_int if trade_value_int is not None else -float('inf'), 
            'sort_24h': sort_key_24h
        })
    summary_data.sort(key=lambda x: (x['sort_24h']), reverse=True)
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc + timedelta(hours=timezone_offset_hours)
    header = f"🌟 **MARKNADSSAMMANFATTNING** 🌟\nPriserna sorterade efter 24h rörelse.\n\n"
    table_header = "```\nKRYPTO | PRIS EUR |  3H   |  24H  | H.V.\n-----------------------------------------\n"
    table_rows = []
    for item in summary_data:
        symbol = item['symbol'].ljust(6)
        price_display = format_price_telegram(item['price_eur']).rjust(8) 
        change_3h = format_change_telegram(item['percent_data'].get('3h'))
        change_24h = format_change_telegram(item['percent_data'].get('24h'))
        trade_value_str = format_trade_value_telegram(item['trade_value_int']) 
        table_rows.append(f"{symbol} | {price_display} |{change_3h} |{change_24h} |{trade_value_str}")
    return header + table_header + "\n".join(table_rows) + "```"

def fetch_exchange_rate():
    try:
        response = requests.get(EXCHANGE_RATE_URL, timeout=10)
        data = response.json()
        return {'SEK': data['rates'].get('SEK', 11.0), 'USD': data['rates'].get('USD', 1.05)}
    except:
        return {'SEK': 11.0, 'USD': 1.05}

def fetch_crypto_data():
    try:
        t = time.time()
        rates = fetch_exchange_rate()
        kraken_tickers = ','.join(CRYPTO_PAIRS.values())
        response = requests.get(KRAKEN_TICKER_API_URL, params={'pair': kraken_tickers}, timeout=15)
        kraken_data = response.json()
        if kraken_data.get('error'): return DEFAULT_DATA
        result_key = kraken_data.get('result', {})
        current_data = {'timestamp': t, 'EXCHANGE_RATES': rates, 'ALL_PERCENT_CHANGE': {}, 'ALL_OHLC_CACHED': {}, 'ALL_24H_RANGE_OHLC': {}}
        for label, ticker in CRYPTO_PAIRS.items():
            coin_symbol = label.split(' ')[0]
            coin_info = result_key.get(ticker)
            if coin_info is None: continue
            price_eur = float(coin_info['c'][0])
            price_yesterday_eur = float(coin_info['o']) 
            current_data[f'{coin_symbol}/EUR'] = price_eur
            current_data[f'{coin_symbol}/DIFF_24H_EUR'] = price_eur - price_yesterday_eur
        return current_data
    except:
        return DEFAULT_DATA 

def fetch_ohlc_data_from_kraken(kraken_ticker, interval, periods_ago_seconds):
    time_ago = int(time.time()) - periods_ago_seconds 
    try:
        response = requests.get(KRAKEN_OHLC_API_URL, params={'pair': kraken_ticker, 'interval': interval, 'since': time_ago}, timeout=15)
        ohlc_data = response.json()
        result_key = next(iter(ohlc_data['result'])) 
        return [{'time': int(row[0]), 'price': float(row[4])} for row in ohlc_data['result'][result_key]]
    except:
        return []

def calculate_percentage_changes(ohlc_data, current_price, periods):
    changes = {}
    if not ohlc_data or current_price is None: return {k: None for k in periods}
    for period, config in periods.items():
        blocks = config['blocks']
        if len(ohlc_data) >= blocks:
            ref = ohlc_data[-blocks]['price']
            changes[period] = ((current_price - ref) / ref) * 100 if ref > 0 else None
        else:
            changes[period] = None
    return changes

def calculate_trendline(historical_data, blocks):
    if len(historical_data) < blocks: return None, None, None
    data_segment = historical_data[-blocks:]
    x_values = np.arange(blocks) 
    y_values = np.array([item['price'] for item in data_segment])
    slope, intercept, _, _, _ = linregress(x_values, y_values)
    return slope, intercept, len(historical_data) - blocks 

def format_change(c):
    if c is None: return html.Span("N/A", style={'color': '#6c757d'})
    color = '#28a745' if c > 0 else '#dc3545' 
    return html.Span(f"{'▲' if c > 0 else '▼'} {abs(c):.2f}%", style={'color': color, 'fontWeight': 'bold', 'fontSize': '0.85em'})

def format_trade_value_display(v):
    if v is None: return html.Span("N/A", style={'color': '#6c757d'})
    val = int(round(v))
    color = '#006400' if val > 0 else '#8B0000' if val < 0 else '#6c757d'
    return html.Span(f"{'▲' if val > 0 else '▼' if val < 0 else ''} {abs(val)}", style={'color': color, 'fontWeight': 'bold', 'fontSize': '0.85em'})

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}, timeout=10)
        return True
    except: return False

def check_and_send_trade_value_alerts(alert_data, r_instance):
    if not r_instance: return
    for coin_symbol, data in alert_data.items():
        tv = data.get('trade_value')
        if tv and tv > 0:
            threshold = next((t for t in TRADE_VALUE_ALERTS if tv >= t), None)
            if threshold:
                if r_instance.set(f"tv_alert:{coin_symbol}:+{threshold}", 1, ex=TRADE_VALUE_DEBOUNCE_SECONDS, nx=True):
                    send_telegram_message(f"🔥 **H.V. ALERT**\n{coin_symbol}: **+{tv}**")

def check_and_send_alerts(alert_data, r_instance):
    if not r_instance: return
    for coin_symbol, data in alert_data.items():
        changes = data['changes']
        for period in ALERT_PERIODS:
            c = changes.get(period)
            if c is None: continue
            if c > 0:
                t = next((thr for thr in ALERT_THRESHOLDS_UP if c >= thr), None)
                if t and r_instance.set(f"alert:{coin_symbol}:+{period}:{t}", 1, ex=ALERT_DEBOUNCE_SECONDS, nx=True):
                    send_telegram_message(f"🚀 **UPPGÅNG**\n{coin_symbol}: +{c:.2f}% ({period})")
            elif c < 0:
                t = next((thr for thr in ALERT_THRESHOLDS_DOWN if c <= thr), None)
                if t and r_instance.set(f"alert:{coin_symbol}:{period}:{t}", 1, ex=ALERT_DEBOUNCE_SECONDS, nx=True):
                    send_telegram_message(f"🔻 **NEDGÅNG**\n{coin_symbol}: {c:.2f}% ({period})")

def background_data_fetch(redis_instance):
    last_ohlc = 0
    while True:
        try:
            new_data = fetch_crypto_data()
            should_ohlc = (time.time() - last_ohlc) > OHLC_FETCH_INTERVAL_SECONDS
            if should_ohlc: last_ohlc = time.time()
            all_pct, all_range, alert_data, tv_alert_data = {}, {}, {}, {}
            for label, ticker in CRYPTO_PAIRS.items():
                coin = label.split(' ')[0]
                price = new_data.get(f'{coin}/EUR')
                if price is None: continue
                if should_ohlc:
                    o5 = fetch_ohlc_data_from_kraken(ticker, 5, 86400)
                    if o5: redis_instance.set(f'OHLC_CACHED_5MIN_{ticker}', json.dumps(o5), ex=7200)
                    o1y = fetch_ohlc_data_from_kraken(ticker, 1440, 31536000)
                    if o1y: redis_instance.set(f'OHLC_1DAY_{ticker}', json.dumps(o1y), ex=86400)
                    o1m = fetch_ohlc_data_from_kraken(ticker, 1, 3600)
                    if o1m: redis_instance.set(f'OHLC_CACHED_1MIN_{ticker}', json.dumps(o1m), ex=300)
                cached_5 = json.loads(redis_instance.get(f'OHLC_CACHED_5MIN_{ticker}') or '[]')
                cached_1d = json.loads(redis_instance.get(f'OHLC_1DAY_{ticker}') or '[]')
                tv_int = None
                if cached_5 and price:
                    tv, _ = calculate_trade_value(cached_5 + [{'time': time.time(), 'price': price}], price, cached_1d + [{'time': time.time(), 'price': price}])
                    tv_int = int(round(tv)) if tv else None
                if cached_5:
                    prices = [i['price'] for i in cached_5]
                    all_range[coin] = {'high_eur': max(max(prices), price), 'low_eur': min(min(prices), price)}
                pct = calculate_percentage_changes(cached_5, price, {k: v for k, v in TIME_WINDOWS.items() if v['interval'] == 5})
                pct.update(calculate_percentage_changes(cached_1d, price, {k: v for k, v in TIME_WINDOWS.items() if v['interval'] == 1440}))
                all_pct[coin] = pct
                alert_data[coin] = {'changes': pct, 'price_eur': price}
                tv_alert_data[coin] = {'trade_value': tv_int}
            check_and_send_alerts(alert_data, redis_instance)
            check_and_send_trade_value_alerts(tv_alert_data, redis_instance)
            new_data.update({'ALL_PERCENT_CHANGE': all_pct, 'ALL_24H_RANGE_OHLC': all_range})
            redis_instance.set('crypto_data', json.dumps(new_data), ex=60)
            time.sleep(UPDATE_INTERVAL_FAST)
        except: time.sleep(10)

def background_summary_sender(redis_instance):
    while True:
        try:
            now = datetime.now(timezone.utc)
            local_hour = (now + timedelta(hours=1)).hour
            if local_hour in SUMMARY_SCHEDULE_HOURS and now.minute == 0:
                if redis_instance.set(f"summary_sent:{now.strftime('%Y%H')}", 1, ex=3500, nx=True):
                    d = get_data_from_redis()
                    if d: send_telegram_message(format_summary_for_telegram(d, d['EXCHANGE_RATES']['SEK'], 1))
            time.sleep(60)
        except: time.sleep(60)

if r:
    threading.Thread(target=background_data_fetch, args=(r,), daemon=True).start()
    threading.Thread(target=background_summary_sender, args=(r,), daemon=True).start()

def create_summary_row(symbol, label, price, percent_data, trade_value, currency, is_selected, eur_to_sek):
    row_style = {'display': 'flex', 'alignItems': 'center', 'padding': '5px 0', 'borderBottom': '1px solid #eee', 'fontSize': '0.85em', 'cursor': 'pointer', 'backgroundColor': '#e6f7ff' if is_selected else '#fff'}
    return html.Div([
        html.Div(f"{CRYPTO_EMOJIS.get(symbol, '')} {label}", style={'flex': '0 0 160px', 'paddingLeft': '5px', 'fontWeight': 'bold'}),
        html.Div(f"{format_price_display(price)}", style={'flex': '0 0 140px', 'textAlign': 'right', 'fontWeight': 'bold'}),
        html.Div(format_change(percent_data.get('30m')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('1h')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('3h')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('24h')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('7d')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_trade_value_display(trade_value), style={'flex': '0 0 80px', 'textAlign': 'right', 'fontWeight': 'bold'})
    ], id={'type': 'summary-card', 'index': symbol}, style=row_style)

def create_selected_coin_box(label, symbol, price, currency, base_price_eur, high_eur, low_eur, percent_data, trade_value=None, individual_trends=None, diff_24h_eur=None): 
    return html.Div(style={'border': '2px solid #0056b3', 'borderRadius': '10px', 'padding': '15px', 'backgroundColor': '#f8f9fa'}, children=[
        html.H2(f"{CRYPTO_EMOJIS.get(symbol, '')} {label} ({symbol})", style={'textAlign': 'center', 'color': '#0056b3'}),
        html.Div(style={'textAlign': 'center'}, children=[
            html.P(f"{format_price_display(price)} {currency}", style={'fontSize': '2.5em', 'fontWeight': '800', 'margin': '0'}),
            html.P(f"H.V: {trade_value}" if trade_value else "")
        ])
    ])

app = dash.Dash(__name__)
server = app.server 
app.layout = html.Div([
    html.Div(style={'maxWidth': '1200px', 'margin': 'auto', 'padding': '20px'}, children=[
        dcc.Dropdown(id='coin-dropdown', options=[{'label': l, 'value': l.split(' ')[0]} for l in COINS_LABELS], value=DEFAULT_COIN_SYMBOL),
        dcc.Dropdown(id='currency-dropdown', options=[{'label': c, 'value': c} for c in BASE_CURRENCIES], value='EUR'),
        html.Div(id='current-price-summary-box-container'),
        dcc.RadioItems(id='graph-timeframe', options=[{'label': '1h Live', 'value': '1h_live'}, {'label': '1d', 'value': '1d'}, {'label': '1w', 'value': '1w'}], value='1d', inline=True),
        dcc.Graph(id='live-update-graph'),
        html.Div(id='crypto-summary'),
        dcc.Store(id='chart-data-store'),
        dcc.Interval(id='interval-fast', interval=10000)
    ])
])

@app.callback(
    [Output('current-price-summary-box-container', 'children'), Output('chart-data-store', 'data')],
    [Input('interval-fast', 'n_intervals'), Input('coin-dropdown', 'value'), Input('currency-dropdown', 'value'), Input('graph-timeframe', 'value')]
)
def update_fast(n, coin, curr, tf):
    data = get_data_from_redis()
    if not data: return html.Div("Laddar..."), None
    ticker = CRYPTO_PAIRS[SYMBOL_TO_LABEL[coin]]
    hist = []
    if tf == '1h_live': hist = json.loads(r.get(f'OHLC_CACHED_1MIN_{ticker}') or '[]')
    else: hist = json.loads(r.get(f'OHLC_CACHED_5MIN_{ticker}') or '[]')
    price = data.get(f'{coin}/EUR')
    base = data['EXCHANGE_RATES'].get(curr, 1.0) if curr in ['SEK', 'USD'] else (data.get(f'{curr}/EUR', 1.0) if curr in COINS_SYMBOLS else 1.0)
    box = create_selected_coin_box(coin, coin, price*base if curr in ['SEK','USD'] else price/base, curr, base, None, None, data['ALL_PERCENT_CHANGE'].get(coin, {}))
    chart = {'hist': hist, 'price': price, 'base': base, 'tf': tf, 'coin': coin}
    return box, chart

@app.callback(
    Output('live-update-graph', 'figure'),
    [Input('chart-data-store', 'data')],
    [State('currency-dropdown', 'value')]
)
def update_graph(chart, curr):
    if not chart: return go.Figure()
    fig = go.Figure()
    prices = [i['price'] for i in chart['hist']]
    if chart['price']: prices.append(chart['price'])
    
    # Valutaomvandling för grafen
    if curr == 'SEK' or curr == 'USD': display_prices = [p * chart['base'] for p in prices]
    elif curr == 'EUR': display_prices = prices
    else: display_prices = [p / chart['base'] for p in prices]
    
    times = [time.strftime('%H:%M', time.gmtime(i['time']+3600)) for i in chart['hist']]
    if len(times) < len(display_prices): times.append(time.strftime('%H:%M', time.gmtime(time.time()+3600)))
    
    fig.add_trace(go.Scatter(x=times, y=display_prices, mode='lines', line=dict(color='#0056b3')))

    # Candle-logik för 1h Live (visar rörelse under minuten på sista punkten)
    if chart['tf'] == '1h_live' and len(display_prices) > 0:
        # Hämta rådata för sista minuten för att se high/low inom den minuten
        last_min_price = display_prices[-1]
        # Vi simulerar candle-veken genom att använda 24h range som referens eller bara visa nuvarande punktens särdrag
        # Här lägger vi till en neongrön punkt storlek 12
        fig.add_trace(go.Scatter(
            x=[times[-1]], y=[last_min_price],
            mode='markers',
            marker=dict(color='#39FF14', size=12, line=dict(width=1, color='black')),
            name='Live'
        ))
        # Candle-veke (visar volatilitet sista minuten)
        fig.add_shape(type="line", x0=times[-1], y0=last_min_price*0.999, x1=times[-1], y1=last_min_price*1.001,
                      line=dict(color="#39FF14", width=3))
    else:
        # Blå punkt för 1d, 1w, 1m (Storlek 6 = dubbelt mot förra 3)
        fig.add_trace(go.Scatter(
            x=[times[-1]], y=[display_prices[-1]],
            mode='markers',
            marker=dict(color='blue', size=6),
            name='Pris'
        ))

    fig.update_layout(template="plotly_white", margin=dict(l=20, r=20, t=40, b=20))
    return fig

@app.callback(
    Output('crypto-summary', 'children'),
    [Input('interval-fast', 'n_intervals'), Input('coin-dropdown', 'value'), Input('currency-dropdown', 'value')]
)
def update_table(n, coin, curr):
    data = get_data_from_redis()
    if not data: return ""
    base = data['EXCHANGE_RATES'].get(curr, 1.0) if curr in ['SEK', 'USD'] else (data.get(f'{curr}/EUR', 1.0) if curr in COINS_SYMBOLS else 1.0)
    rows = []
    for label in COINS_LABELS:
        c = label.split(' ')[0]
        p = data.get(f'{c}/EUR', 0)
        rows.append(create_summary_row(c, label, p*base if curr in ['SEK','USD'] else p/base, data['ALL_PERCENT_CHANGE'].get(c, {}), None, curr, c==coin, 11))
    return rows

if __name__ == '__main__':
    app.run_server(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 8050)))