import redis
import requests
import json
import time
import os
import threading
from datetime import datetime, timezone, timedelta
import logging
import numpy as np
import dash
from dash import dcc, html, Input, Output, State, ALL, ctx
import plotly.graph_objects as go

# --- 1. KONFIGURATION OCH KONSTANTER (Från Del 1) ---

# Logger setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Miljövariabler
KRAKEN_API_URL = "https://api.kraken.com/0/public/Ticker"
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Kraken Pairs & Dash Config
COINS_LABELS = [
    "XBT Bitcoin", "ETH Ethereum", "ADA Cardano", "SOL Solana", "DOT Polkadot",
    "MATIC Polygon", "DOGE Dogecoin", "LTC Litecoin", "LINK Chainlink", "UNI Uniswap",
    "BCH Bitcoin Cash", "XLM Stellar", "ALGO Algorand"
]
COINS_SYMBOLS = [label.split(' ')[0] for label in COINS_LABELS] # XBT, ETH, ADA, etc.

# Mappar Coin Label till Kraken Ticker
CRYPTO_PAIRS = {
    "XBT Bitcoin": "XXBTZUSD", "ETH Ethereum": "XETHZUSD", "ADA Cardano": "ADAUSD",
    "SOL Solana": "SOLUSD", "DOT Polkadot": "DOTUSD", "MATIC Polygon": "MATICUSD",
    "DOGE Dogecoin": "DOGEUSD", "LTC Litecoin": "XLTCZUSD", "LINK Chainlink": "LINKUSD",
    "UNI Uniswap": "UNIUSD", "BCH Bitcoin Cash": "BCHUSD", "XLM Stellar": "XXLMZUSD",
    "ALGO Algorand": "ALGOUSD"
}
# Omvänd mappning för enkelhet
SYMBOL_TO_LABEL = {v.split(' ')[0]: k for k, v in CRYPTO_PAIRS.items()} 

CRYPTO_EMOJIS = {
    "XBT": "₿", "ETH": "Ξ", "ADA": "₳", "SOL": "◎", "DOT": "Ⓟ",
    "MATIC": "🔺", "DOGE": "Ɖ", "LTC": "Ł", "LINK": "🔗", "UNI": "🦄",
    "BCH": "Ƀ", "XLM": "⭐", "ALGO": "🅰️"
}

BASE_CURRENCIES = ['EUR', 'SEK', 'XBT', 'ETH'] 
DEFAULT_COIN_SYMBOL = 'XBT'

# Redis Nycklar
REDIS_DATA_KEY = 'KRAKEN_DASH_DATA'
REDIS_SUMMARY_KEY = 'SUMMARY_SENT_DEBOUNCE'
REDIS_ALERT_KEY = 'PRICE_ALERT_DEBOUNCE'
REDIS_TRADE_ALERT_KEY = 'TRADE_ALERT_DEBOUNCE'

# Schemaläggning och intervaller
UPDATE_INTERVAL_SECONDS_DATA = 5 * 60 # 5 minuters intervall för datahämtning
OHLC_CACHE_INTERVAL_MIN = 5 
SUMMARY_SCHEDULE_HOURS = [9, 14, 20] # CET/CEST
ALERT_DEBOUNCE_SECONDS = 6 * 3600 # 6 timmars spärr för alerts

# Trösklar för Alerts och Handelsvärde
ALERT_THRESHOLDS_UP = [0.5, 1.0, 2.0, 3.0] # Positiva procentuella förändringar (30m/1h)
ALERT_THRESHOLDS_DOWN = [-0.5, -1.0, -2.0, -3.0] # Negativa procentuella förändringar (30m/1h)
TRADE_VALUE_ALERTS = [50, 70, 90] # Positiva handelsvärden

# Trendlinjekonfiguration
TREND_WINDOWS = {
    'H12': {'name': 'Trend (12 timmar)', 'blocks': 144, 'weight': 1.0, 'color': '#ff7f0e', 'source': '5min', 'show_line': True},
    'H24': {'name': 'Trend (24 timmar)', 'blocks': 288, 'weight': 2.0, 'color': '#2ca02c', 'source': '5min', 'show_line': True},
    'D03': {'name': 'Trend (3 dagar)', 'blocks': 864, 'weight': 5.0, 'color': '#d62728', 'source': '5min', 'show_line': False},
    
    'D07_1d': {'name': 'Trend (7 dagar)', 'blocks': 7, 'weight': 10.0, 'color': '#9467bd', 'source': '1day', 'show_line': False},
    'D30_1d': {'name': 'Trend (30 dagar)', 'blocks': 30, 'weight': 20.0, 'color': '#1f77b4', 'source': '1day', 'show_line': False},
}


# --- 2. VERKTYGSFUNKTIONER (Från Del 1) ---

def connect_redis():
    try:
        r = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True)
        r.ping()
        logger.info("✅ Ansluten till Redis framgångsrikt.")
        return r
    except Exception as e:
        logger.error(f"❌ Kunde inte ansluta till Redis: {e}")
        return None

r = connect_redis()

def get_data_from_redis():
    if r:
        data = r.get(REDIS_DATA_KEY)
        if data:
            return json.loads(data)
    return None

def fetch_ohlc_data(pair, interval=OHLC_CACHE_INTERVAL_MIN, since=None):
    # Enkel wrapper för Kraken OHLC
    try:
        url = f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval={interval}"
        if since: url += f"&since={since}"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data['error']:
            logger.error(f"Kraken OHLC fel för {pair}: {data['error']}")
            return []

        # Formatera data: [['time', 'open', 'high', 'low', 'close', ...], ...]
        ohlc_list = data['result'][list(data['result'].keys())[0]]
        
        formatted_data = []
        for item in ohlc_list:
            formatted_data.append({
                'time': int(item[0]),
                'price': float(item[4]) # Stängningspris
            })
        return formatted_data
    except Exception as e:
        logger.error(f"Fel vid hämtning av OHLC för {pair}: {e}")
        return []

def calculate_trade_value(hist_5min, current_price_eur, hist_1day):
    # Beräkna individuella trendvärden och ett sammanvägt "handelsvärde"
    individual_trends = {}
    trade_value = 0.0

    # 1. Kort sikt (5min-data)
    for key, config in TREND_WINDOWS.items():
        if config['source'] == '5min':
            data = hist_5min
            blocks = config['blocks']
            
            if len(data) >= blocks:
                # Linjär regression: y = slope * x + intercept
                slope, _, _ = calculate_trendline(data, blocks)
                
                # Trendvärde (directionality): trend_value = slope * 1000
                trend_val = slope * 1000 * 60 * 5 # Normaliserar med 5min intervall
                
                individual_trends[key] = trend_val
                
                # Viktad summa: trade_value += trend_val * weight
                trade_value += trend_val * config['weight']

    # 2. Lång sikt (1day-data)
    for key, config in TREND_WINDOWS.items():
        if config['source'] == '1day':
            data = hist_1day
            blocks = config['blocks']
            
            if len(data) >= blocks:
                # Linjär regression: y = slope * x + intercept
                slope, _, _ = calculate_trendline(data, blocks)
                
                # Trendvärde (directionality): trend_value = slope * 1000
                trend_val = slope * 1000 * 60 * 60 * 24 # Normaliserar med 1day intervall
                
                individual_trends[key] = trend_val
                
                # Viktad summa: trade_value += trend_val * weight
                trade_value += trend_val * config['weight']

    return trade_value, individual_trends

def calculate_trendline(data, blocks):
    if len(data) < blocks:
        return 0.0, 0.0, 0
    
    # Använd bara de senaste 'blocks' datapunkterna
    trend_data = data[-blocks:]
    
    # Tiden normaliseras till index [0, 1, 2, ...]
    x = np.arange(blocks) 
    y = np.array([item['price'] for item in trend_data])
    
    # Utför linjär regression
    slope, intercept = np.polyfit(x, y, 1)
    
    return slope, intercept, len(data) - blocks

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram-konfiguration saknas. Hoppar över meddelande.")
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return True
        else:
            logger.error(f"❌ Telegram-fel: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Kunde inte skicka Telegram-meddelande: {e}")
        return False

def format_price_display(p):
    if p is None: return "N/A"
    price_format = f"{p:,.8f}" if p < 0.1 else (f"{p:,.4f}" if p < 10 else f"{p:,.2f}")
    # Använder svenska/europeiska formatet: komma som decimal, mellanslag som tusentalsavgränsare
    return price_format.replace(",", "TEMP").replace(".", ",").replace("TEMP", " ")

def format_change(percent):
    if percent is None: return html.Span("N/A", style={'color': '#6c757d'})
    
    color = '#495057'
    symbol = ''
    
    if percent > 0.01:
        color = '#28a745'
        symbol = '+'
    elif percent < -0.01:
        color = '#dc3545'
        symbol = '' # Minus är implicit
        
    return html.Span(f"{symbol}{percent:.2f}%", style={'color': color, 'fontWeight': 'bold'})

def format_trade_value_display(value):
    if value is None: return html.Span("N/A", style={'color': '#6c757d'})
    
    color = '#495057'
    symbol = ''
    
    if value > 0:
        color = '#006400'
        symbol = '+'
    elif value < 0:
        color = '#8B0000'
        symbol = ''
        
    return html.Span(f"{symbol}{value:,.2f}", style={'color': color, 'fontWeight': '900'})

def format_summary_for_telegram(data, eur_to_sek, timezone_offset_hours):
    timestamp = data.get('timestamp')
    local_timestamp = timestamp + 3600 * timezone_offset_hours
    updated_time = time.strftime('%H:%M:%S', time.gmtime(local_timestamp))
    
    message = f"**🗓️ Daglig Sammanfattning - {updated_time} Lokal Tid**\n"
    message += f"Valutakurs: 1 EUR = {eur_to_sek:.2f} SEK\n"
    message += "---"
    
    # Hämta och sortera data baserat på det högsta Handelsvärdet (trade_value)
    summary_list = []
    
    for symbol in COINS_SYMBOLS:
        peur = data.get(f'{symbol}/EUR')
        pd = data.get('ALL_PERCENT_CHANGE', {}).get(symbol, {})
        tv = data.get('TRADE_VALUE', {}).get(symbol)
        
        if peur is not None:
            price_sek = peur * eur_to_sek
            
            # Formatering av procentuell förändring
            def format_p(p):
                if p is None: return "N/A"
                sign = '+' if p >= 0 else ''
                return f"{sign}{p:.2f}%"

            summary_list.append({
                'symbol': symbol,
                'label': SYMBOL_TO_LABEL.get(symbol, symbol),
                'price_sek': price_sek,
                'tv': tv,
                'change_24h': pd.get('24h'),
                'change_30m': pd.get('30m')
            })

    # Sortering: Högst Handelsvärde (TV) först, sedan 24h%
    summary_list.sort(key=lambda x: (x['tv'] if x['tv'] is not None else -float('inf'), x['change_24h'] if x['change_24h'] is not None else -float('inf')), reverse=True)
    
    for item in summary_list:
        tv_str = f"({item['tv']:.0f})" if item['tv'] is not None else "(N/A)"
        
        # Färgkodning av rubriken baserat på TV (Handelsvärde)
        if item['tv'] is not None and item['tv'] > 50:
             title_prefix = "🔥"
        elif item['tv'] is not None and item['tv'] > 0:
             title_prefix = "🟢"
        else:
             title_prefix = "⚫"

        message += f"\n{title_prefix} **{item['symbol']} {tv_str}**\n"
        message += f"  Pris: {format_price_display(item['price_sek'])} SEK\n"
        
        # Visar 24h och 30m förändring
        ch_24h = item['change_24h']
        ch_30m = item['change_30m']
        
        def format_p_tg(p):
            if p is None: return "N/A"
            sign = '+' if p >= 0 else ''
            return f"{sign}{p:.2f}%"

        message += f"  24h: {format_p_tg(ch_24h)} | 30m: {format_p_tg(ch_30m)}\n"
        
    return message


# --- 3. BAKGRUNDSTRÅDAR OCH HÄMTNINGSLOGIK (Från Del 1) ---

def background_data_fetch(redis_instance):
    logger.info("Startar bakgrundstråd för datahämtning...")
    
    last_ohlc_timestamp_5min = 0
    last_ohlc_timestamp_1day = 0
    
    while True:
        try:
            # --- Steg 1: Hämta aktuell valutakurs (EUR/SEK) ---
            sek_rate = 11.0 # Fallbackvärde
            try:
                # Använder en enkel gratis API för valuta
                response = requests.get('https://api.exchangerate.host/latest?base=EUR&symbols=SEK', timeout=5)
                if response.status_code == 200:
                    sek_rate = response.json().get('rates', {}).get('SEK', sek_rate)
            except Exception as e:
                logger.warning(f"Kunde inte hämta EUR/SEK-kurs: {e}")

            # --- Steg 2: Hämta aktuell krypto-tickerdata ---
            tickers_to_fetch = ','.join(CRYPTO_PAIRS.values())
            url = f"{KRAKEN_API_URL}?pair={tickers_to_fetch}"
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            kraken_data = response.json()
            
            current_timestamp = int(time.time())
            
            # Huvuddatabehållare
            current_data = {
                'timestamp': current_timestamp,
                'EUR_SEK_RATE': sek_rate,
                'ALL_PERCENT_CHANGE': {},
                'ALL_24H_RANGE_OHLC': {},
                'TRADE_VALUE': {}
            }
            
            # Konvertera Kraken-data och förbered OHLC-uppdatering
            for label, ticker in CRYPTO_PAIRS.items():
                symbol = label.split(' ')[0]
                ticker_data = kraken_data['result'].get(ticker)
                
                if not ticker_data: continue

                # Ticker data: [0]=ask, [1]=bid, [2]=last, [3]=volume, [4]=vwap, [5]=count, [6]=low/high (24h), [7]=open (24h)
                last_price_eur = float(ticker_data['c'][0])
                percent_24h = float(ticker_data['p'][1]) * 100
                open_24h = float(ticker_data['o'][1])
                diff_24h_eur = last_price_eur - open_24h

                current_data[f'{symbol}/EUR'] = last_price_eur
                current_data[f'{symbol}/DIFF_24H_EUR'] = diff_24h_eur
                
                # Lägg till procentuella förändringar (Antar att 30m, 1h, etc. beräknas baserat på OHLC)
                # För tillfället lagrar vi bara 24h
                current_data['ALL_PERCENT_CHANGE'][symbol] = {'24h': percent_24h}
                current_data['ALL_24H_RANGE_OHLC'][symbol] = {
                    'low_eur': float(ticker_data['l'][1]), 
                    'high_eur': float(ticker_data['h'][1])
                }
            
            # --- Steg 3: Hämta och cache:a OHLC-data (5 minuters intervall) ---
            # Hämta bara data sedan senaste lyckade hämtningen
            if current_timestamp > last_ohlc_timestamp_5min + (OHLC_CACHE_INTERVAL_MIN * 60):
                ohlc_successful = True
                new_last_timestamp_5min = current_timestamp
                
                for label, ticker in CRYPTO_PAIRS.items():
                    symbol = label.split(' ')[0]
                    
                    # Hämta 5min data (och 12h/24h/3d trend)
                    # Vi hämtar all historik som OHLC (5 minuter)
                    if last_ohlc_timestamp_5min == 0:
                        # Första körningen: hämta 3 dagar (för 3d-trenden)
                        ohlc_data = fetch_ohlc_data(ticker, interval=OHLC_CACHE_INTERVAL_MIN, since=current_timestamp - (3 * 24 * 3600))
                    else:
                        # Nästa körningar: hämta bara de nya blocken
                        ohlc_data = fetch_ohlc_data(ticker, interval=OHLC_CACHE_INTERVAL_MIN, since=last_ohlc_timestamp_5min)
                    
                    if ohlc_data:
                        existing_data_json = redis_instance.get(f'OHLC_CACHED_{OHLC_CACHE_INTERVAL_MIN}MIN_{ticker}')
                        if existing_data_json:
                            existing_data = json.loads(existing_data_json)
                            # Lägg till nya datapunkter och ta bort gamla (för att hålla storleken under kontroll, t.ex. 3 dagar)
                            existing_data.extend([d for d in ohlc_data if d['time'] > existing_data[-1]['time']])
                            
                            # Trimma till 3 dagar + lite marginal (3d = 864 punkter)
                            max_points = 1000 
                            if len(existing_data) > max_points:
                                existing_data = existing_data[-max_points:]
                                
                            redis_instance.set(f'OHLC_CACHED_{OHLC_CACHE_INTERVAL_MIN}MIN_{ticker}', json.dumps(existing_data))
                        else:
                             redis_instance.set(f'OHLC_CACHED_{OHLC_CACHE_INTERVAL_MIN}MIN_{ticker}', json.dumps(ohlc_data))

                        # Beräkna korttids procentuella förändringar (30m, 1h, 3h, 6h, 12h)
                        for period, minutes in {'30m': 30, '1h': 60, '3h': 180, '6h': 360, '12h': 720}.items():
                            blocks = int(minutes / OHLC_CACHE_INTERVAL_MIN)
                            if len(existing_data) >= blocks:
                                start_price = existing_data[-blocks]['price']
                                current_price = current_data.get(f'{symbol}/EUR')
                                if current_price and start_price:
                                    change = ((current_price - start_price) / start_price) * 100
                                    current_data['ALL_PERCENT_CHANGE'][symbol][period] = change
                            else:
                                current_data['ALL_PERCENT_CHANGE'][symbol][period] = None # Eller en liten siffra

                    else:
                        ohlc_successful = False
                        logger.warning(f"Kunde inte hämta 5min OHLC för {ticker}.")

                if ohlc_successful:
                    last_ohlc_timestamp_5min = new_last_timestamp_5min
                    
            # --- Steg 4: Hämta och cache:a OHLC-data (1 dags intervall för långa trender) ---
            if current_timestamp > last_ohlc_timestamp_1day + (24 * 3600): # En gång per dag
                 ohlc_successful_1d = True
                 new_last_timestamp_1day = current_timestamp

                 for label, ticker in CRYPTO_PAIRS.items():
                    # Hämta 1d data (för 7d/30d trend)
                    # Hämta 35 dagar för att stödja 30-dagars trenden
                    ohlc_data_1d = fetch_ohlc_data(ticker, interval=240, since=current_timestamp - (35 * 24 * 3600)) 
                    
                    if ohlc_data_1d:
                        # Behåll bara de senaste 35 dagarna
                        if len(ohlc_data_1d) > 35:
                            ohlc_data_1d = ohlc_data_1d[-35:]
                            
                        redis_instance.set(f'OHLC_1DAY_{ticker}', json.dumps(ohlc_data_1d))
                        
                        # Beräkna 7d och 30d procentuella förändringar
                        current_price = current_data.get(f'{symbol}/EUR')
                        
                        # 7d
                        if len(ohlc_data_1d) >= 7:
                            start_price = ohlc_data_1d[-7]['price']
                            if current_price and start_price:
                                change = ((current_price - start_price) / start_price) * 100
                                current_data['ALL_PERCENT_CHANGE'][symbol]['7d'] = change
                        
                        # 30d
                        if len(ohlc_data_1d) >= 30:
                            start_price = ohlc_data_1d[-30]['price']
                            if current_price and start_price:
                                change = ((current_price - start_price) / start_price) * 100
                                current_data['ALL_PERCENT_CHANGE'][symbol]['30d'] = change
                                
                    else:
                        ohlc_successful_1d = False
                        logger.warning(f"Kunde inte hämta 1day OHLC för {ticker}.")
                 
                 if ohlc_successful_1d:
                    last_ohlc_timestamp_1day = new_last_timestamp_1day

            # --- Steg 5: Beräkna Handelsvärde och Alerts ---
            for label, ticker in CRYPTO_PAIRS.items():
                symbol = label.split(' ')[0]
                peur = current_data.get(f'{symbol}/EUR')
                pd = current_data['ALL_PERCENT_CHANGE'].get(symbol, {})
                
                # Hämta cache-data för trendberäkning
                hist_5min = json.loads(redis_instance.get(f'OHLC_CACHED_{OHLC_CACHE_INTERVAL_MIN}MIN_{ticker}') or '[]')
                hist_1day = json.loads(redis_instance.get(f'OHLC_1DAY_{ticker}') or '[]')

                if hist_5min and peur:
                    # Lägg till aktuell prispunkt för korrekt beräkning
                    hist_5min_curr = hist_5min + [{'time': current_timestamp, 'price': peur}]
                    hist_1day_curr = hist_1day + [{'time': current_timestamp, 'price': peur}]
                    
                    trade_value, individual_trends = calculate_trade_value(hist_5min_curr, peur, hist_1day_curr)
                    current_data['TRADE_VALUE'][symbol] = trade_value
                    
                    # 5a. Alert för Handelsvärde (Endast Positiv)
                    if trade_value is not None and trade_value > 0:
                        max_alert_value = max([t for t in TRADE_VALUE_ALERTS if t <= trade_value] or [0])
                        if max_alert_value > 0:
                            alert_key = f"{REDIS_TRADE_ALERT_KEY}:{symbol}:{max_alert_value}"
                            if redis_instance.set(alert_key, 1, ex=ALERT_DEBOUNCE_SECONDS, nx=True):
                                msg = f"🔔 **Handelsvärde ALERT** (Positiv)\n\n"
                                msg += f"**{CRYPTO_EMOJIS.get(symbol, '')} {label}** har nått Handelsvärde: **+{trade_value:,.0f}**.\n"
                                msg += f"Pris: {format_price_display(peur * sek_rate)} SEK\n"
                                msg += f"24h %: {format_change(pd.get('24h', 0.0)).children}"
                                send_telegram_message(msg)
                                logger.info(f"✅ Handelsvärde ALERT skickad för {symbol} (+{trade_value:,.0f}).")
                                
                    # 5b. Alert för Prisrörelse (30m och 1h)
                    for period in ['30m', '1h']:
                        change = pd.get(period)
                        if change is not None:
                            # Positiva trösklar
                            max_up_alert = max([t for t in ALERT_THRESHOLDS_UP if t <= change] or [0])
                            if max_up_alert > 0:
                                alert_key = f"{REDIS_ALERT_KEY}:{symbol}:{period}:{max_up_alert}_up"
                                if redis_instance.set(alert_key, 1, ex=ALERT_DEBOUNCE_SECONDS, nx=True):
                                    msg = f"🔔 **Prisrörelse ALERT** ({period} UP)\n\n"
                                    msg += f"**{CRYPTO_EMOJIS.get(symbol, '')} {label}** har ökat med **+{change:.2f}%** på {period}.\n"
                                    msg += f"Pris: {format_price_display(peur * sek_rate)} SEK\n"
                                    msg += f"Handelsvärde: {format_trade_value_display(trade_value or 0.0).children}"
                                    send_telegram_message(msg)
                                    logger.info(f"✅ Pris ALERT skickad för {symbol} ({period} +{change:.2f}%).")
                                    
                            # Negativa trösklar
                            min_down_alert = min([t for t in ALERT_THRESHOLDS_DOWN if t >= change] or [0])
                            if min_down_alert < 0:
                                alert_key = f"{REDIS_ALERT_KEY}:{symbol}:{period}:{min_down_alert}_down"
                                if redis_instance.set(alert_key, 1, ex=ALERT_DEBOUNCE_SECONDS, nx=True):
                                    msg = f"🔔 **Prisrörelse ALERT** ({period} DOWN)\n\n"
                                    msg += f"**{CRYPTO_EMOJIS.get(symbol, '')} {label}** har minskat med **{change:.2f}%** på {period}.\n"
                                    msg += f"Pris: {format_price_display(peur * sek_rate)} SEK\n"
                                    msg += f"Handelsvärde: {format_trade_value_display(trade_value or 0.0).children}"
                                    send_telegram_message(msg)
                                    logger.info(f"✅ Pris ALERT skickad för {symbol} ({period} {change:.2f}%).")

            # --- Steg 6: Lagra all uppdaterad data i Redis ---
            redis_instance.set(REDIS_DATA_KEY, json.dumps(current_data))
            logger.info(f"✅ Data uppdaterad och sparad i Redis: {len(current_data)-5} kryptos. Nästa hämtning om {UPDATE_INTERVAL_SECONDS_DATA}s.")
            
            time.sleep(UPDATE_INTERVAL_SECONDS_DATA)

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Nätverksfel vid datahämtning: {e}. Försöker igen om 60s.")
            time.sleep(60)
        except Exception as e:
            logger.error(f"❌ Oväntat fel i bakgrundstråd: {e}. Försöker igen om 60s.")
            time.sleep(60)


def background_summary_sender(redis_instance):
    logger.info("Startar bakgrundstråd för sammanfattning...")
    
    # Huvudfunktionen är oförändrad, den anropar format_summary_for_telegram (som uppdaterats i steg 2)
    while True:
        try:
            now_utc = datetime.now(timezone.utc)
            timezone_offset_hours = 1 # Grund offset för CET
            
            # Förenklad DST-kontroll (mars till oktober)
            if now_utc.month in range(4, 10): 
                timezone_offset_hours = 2 # CEST
            elif now_utc.month == 3 and now_utc.day > 24 and now_utc.weekday() == 6: # Sista söndagen i mars
                timezone_offset_hours = 2
            elif now_utc.month == 10 and now_utc.day > 24 and now_utc.weekday() == 6: # Sista söndagen i oktober
                timezone_offset_hours = 1 
             
            now_local = now_utc + timedelta(hours=timezone_offset_hours)
            
            # Skicka sammanfattning vid schemalagd tid
            if now_local.hour in SUMMARY_SCHEDULE_HOURS and now_local.minute == 0:
                # Debounce-nyckel för att säkerställa att meddelandet skickas max 1 gång per timme
                debounce_key = f"{REDIS_SUMMARY_KEY}:{now_local.strftime('%Y%m%d_%H')}"
                
                # nx=True säkerställer att nyckeln bara sätts om den INTE redan finns
                if redis_instance and redis_instance.set(debounce_key, 1, ex=3600*1, nx=True): 
                    data = get_data_from_redis()
                    if data:
                        # timezone_offset_hours skickas med för att korrigera tidszonen i meddelandetexten
                        msg = format_summary_for_telegram(data, data.get('EUR_SEK_RATE', 11.0), timezone_offset_hours)
                        if send_telegram_message(msg): logger.info("✅ Sammanfattning skickad.")
                    else:
                        logger.warning("Kunde inte hämta data från Redis för sammanfattning.")

            time.sleep(60) # Vänta 60 sekunder

        except Exception as e:
            logger.error(f"❌ Fel i schema-tråd: {e}")
            time.sleep(60)

# Starta bakgrundstrådar om Redis-anslutning lyckades
if r:
    threading.Thread(target=background_data_fetch, args=(r,), daemon=True).start()
    threading.Thread(target=background_summary_sender, args=(r,), daemon=True).start()

# --- 4. DASH WEB-GRÄNSSNITT (Från Del 2) ---

# --- Funktioner för Dash-komponenter (med ändringar 2, 3 och 4) ---

def format_summary_price_with_change(price_in_base, change_24h):
    # Ändring 4: Visar pris + 24h % i parentes
    if price_in_base is None: return html.Div("N/A", style={'color': '#6c757d', 'flex': '0 0 120px', 'textAlign': 'right', 'paddingRight': '5px'})
    
    price_str = format_price_display(price_in_base)
    
    change_str = ""
    color = '#495057'
    if change_24h is not None:
        if change_24h >= 0.01:
            color = '#28a745'
            change_str = f" (+{change_24h:.2f}%)"
        elif change_24h <= -0.01:
            color = '#dc3545'
            change_str = f" ({change_24h:.2f}%)"
        else:
            color = '#6c757d'
            change_str = f" (0.00%)"

    return html.Div([
        html.Span(price_str, style={'color': '#495057'}), 
        html.Span(change_str, style={'color': color, 'fontSize': '0.9em', 'fontWeight': 'normal'})
    ], style={'flex': '0 0 120px', 'textAlign': 'right', 'fontWeight': 'bold', 'paddingRight': '5px'})


def create_summary_row(symbol, label, price, percent_data, trade_value, currency, is_selected, eur_to_sek):
    row_style = {'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center', 'padding': '5px 0', 'borderBottom': '1px solid #eee', 'fontSize': '0.85em', 'cursor': 'pointer', 'backgroundColor': '#fff'}
    if is_selected:
        row_style['backgroundColor'] = '#e6f7ff'
        row_style['border'] = '1px solid #0056b3'
    
    # Ändring 4: Använder det nya prisformatet
    price_div = format_summary_price_with_change(price, percent_data.get('24h')) 
    
    # Skapa DIV:ar för varje kolumn (Ändring 2: Lagt till 12h)
    cols = [
        html.Div(html.Span(f"{CRYPTO_EMOJIS.get(symbol, '')} {label}", style={'fontWeight': 'bold', 'color': '#0056b3' if is_selected else '#495057'}), style={'flex': '0 0 160px', 'paddingLeft': '5px'}),
        price_div, 
        html.Div(format_change(percent_data.get('30m')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('1h')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('3h')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('6h')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('12h')), style={'flex': '1', 'textAlign': 'right'}), # <-- NY 12H KOLUMN
        html.Div(format_change(percent_data.get('24h')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('7d')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('30d')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_trade_value_display(trade_value), style={'flex': '0 0 80px', 'textAlign': 'right', 'fontWeight': 'bold', 'paddingRight': '5px'}),
    ]

    return html.Div(cols, id={'type': 'summary-card', 'index': symbol}, style=row_style)


def create_selected_coin_box(label, symbol, price, currency, base_price_eur, high_eur, low_eur, percent_data, trade_value=None, individual_trends=None, diff_24h_eur=None): 
    if individual_trends is None: individual_trends = {}
    
    # ... (Resten av funktionen är oförändrad)
    price_text = f"{format_price_display(price)} {currency}"
    coin_emoji = CRYPTO_EMOJIS.get(symbol, '')
    change_24h = percent_data.get('24h') 
    price_color = '#28a745' if change_24h and change_24h > 0 else '#dc3545' if change_24h and change_24h < 0 else '#495057'
    trade_value_color = '#006400' if trade_value and trade_value > 0 else '#8B0000' if trade_value and trade_value < 0 else '#495057'
    
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

    periods_col1, periods_col2 = ['30m', '1h', '3h'], ['6h', '12h', '18h'] 

    def create_change_row(period, value):
        return html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'margin': '3px 0', 'padding': '0 5px', 'fontSize': '0.9em'},
                         children=[html.Span(f"{period}:", style={'color': '#6c757d', 'flex': '0 0 40px'}), html.Div(value, style={'flex': '1', 'textAlign': 'right'})])
    
    def create_trend_display_list(trend_keys):
        return [
            html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'marginBottom': '3px'}, children=[
                html.Span(f"{TREND_WINDOWS[key]['name'].split(' ')[1]}:", style={'color': '#6c757d', 'fontWeight': 'bold'}), 
                html.Span(f"{individual_trends[key]:,.2f}" if individual_trends[key] is not None else "N/A", style={'color': '#006400' if (individual_trends[key] or 0) > 0 else '#8B0000' if (individual_trends[key] or 0) < 0 else '#6c757d', 'fontWeight': '600'})
            ])
            for key in trend_keys if key in individual_trends 
        ]
        
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

    # --- LAYOUT KVARSTÅR ---
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
        
        html.Div(style={'padding': '5px 0 10px 0', 'borderBottom': '1px dotted #dee2e6', 'fontSize': '0.9em'}, children=[
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
            create_change_row(p, format_change(percent_data.get(p))) for p in periods_col1 + periods_col2
        ])
    ])

    trend_section = html.Div(style={'flex': '1 1 200px', 'minWidth': '200px', 'paddingLeft': '15px', 'borderLeft': '1px solid #dee2e6'}, children=[
        html.P("Trendvärden (Hₓ) - Riktning/Vikt", style={'margin': '0 0 10px 0', 'color': '#495057', 'fontWeight': 'bold', 'textAlign': 'center', 'fontSize': '0.9em'}),
        
        html.P("Kort Sikt (5m data)", style={'margin': '0 0 5px 0', 'color': '#6c757d', 'fontSize': '0.8em', 'fontWeight': 'bold'}),
        html.Div(create_trend_display_list(short_term_keys)),
        
        html.P("Lång Sikt (1d data)", style={'margin': '10px 0 5px 0', 'color': '#6c757d', 'fontSize': '0.8em', 'fontWeight': 'bold', 'borderTop': '1px dotted #dee2e6', 'paddingTop': '5px'}),
        html.Div(create_trend_display_list(long_term_keys)),
    ])

    return html.Div(id='current-price-box', style={'border': '2px solid #0056b3', 'borderRadius': '10px', 'padding': '15px', 'marginBottom': '20px', 'backgroundColor': '#f8f9fa'}, children=[
            html.Div(style={'display': 'flex', 'justifyContent': 'space-around', 'alignItems': 'flex-start', 'flexWrap': 'wrap', 'gap': '10px'}, children=[
                main_price_section, 
                changes_section, 
                trend_section
            ])
            ])


app = dash.Dash(__name__, external_stylesheets=['https://codepen.io/chriddyp/cnWqWbL.css'])
server = app.server 

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
    
    # Skicka med de individuella trendvärdena och 24h diff till boxen
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

        # Lagra sorteringsnycklar för Ändring 3
        summary_data.append({'symbol': sl, 'label': label, 'price': pb, 'percent': pd, 'trade_value': tv_int, 
            's24h': pd.get('24h', -float('inf')), 's7d': pd.get('7d', -float('inf')), 's30d': pd.get('30d', -float('inf'))})

    # Ändring 3: Sortering: 24h, 7dgr, 30dgr (reverse=True)
    summary_data.sort(key=lambda x: (x['s24h'], x['s7d'], x['s30d']), reverse=True)
    
    # --- UPPDATERAT TABELLHUVUD (Ändring 2: 12h) ---
    header_style = {'display': 'flex', 'justifyContent': 'space-between', 'fontWeight': 'bold', 'padding': '7px 0', 'borderBottom': '2px solid #0056b3', 'backgroundColor': '#f0f0f0', 'marginBottom': '5px', 'color': '#495057', 'fontSize': '0.85em'}
    header_cols = [
        html.Div("Valuta", style={'flex': '0 0 160px', 'paddingLeft': '5px'}), 
        html.Div(f"Pris ({currency})", style={'flex': '0 0 120px', 'textAlign': 'right'}), # Bredare för att rymma %
        html.Div("30m", style={'flex': '1', 'textAlign': 'right'}), 
        html.Div("1h", style={'flex': '1', 'textAlign': 'right'}), 
        html.Div("3h", style={'flex': '1', 'textAlign': 'right'}), 
        html.Div("6h", style={'flex': '1', 'textAlign': 'right'}),
        html.Div("12h", style={'flex': '1', 'textAlign': 'right'}), # <-- NY 12H KOLUMN
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