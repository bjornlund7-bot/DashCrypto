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
DEFAULT_COIN_SYMBOL = DEFAULT_PAIR_KEY.split(' ')[0] 

COINS_LABELS = list(CRYPTO_PAIRS.keys())
COINS_SYMBOLS = [label.split(' ')[0] for label in COINS_LABELS]
SYMBOL_TO_LABEL = {label.split(' ')[0]: label for label in COINS_LABELS}
CURRENCIES = ['EUR', 'SEK']
UPDATE_INTERVAL_SECONDS_DATA = 120 
OHLC_CACHE_INTERVAL_MIN = 5 

# Tidsintervall för schemalagd sammanställning (i 24-timmarsformat)
SUMMARY_SCHEDULE_HOURS = [6, 9, 12, 15, 18, 21] 
REDIS_SUMMARY_KEY = 'summary_last_sent_time' # Nyckel för att spärra schemat

# ... (TIME_WINDOWS, TREND_WINDOWS, ALERTS KONSTANTER oförändrade)

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
TREND_WINDOWS = {
    '1h': {'blocks': 12, 'color': '#ff7f0e', 'name': 'Trend (1h)'}, 
    '3h': {'blocks': 36, 'color': '#2ca02c', 'name': 'Trend (3h)'}, 
    '6h': {'blocks': 72, 'color': '#d62728', 'name': 'Trend (6h)'}, 
    '12h': {'blocks': 144, 'color': '#9467bd', 'name': 'Trend (12h)'}, 
}
ALERT_THRESHOLDS_UP = sorted([10, 20, 30, 40, 50, 75, 100], reverse=True)
ALERT_THRESHOLDS_DOWN = sorted([-10, -20, -25, -30, -50, -75]) 
ALERT_PERIODS = ['30m', '1h', '3h', '6h', '12h', '24h']
ALERT_DEBOUNCE_SECONDS = 4 * 3600 # 4 timmar

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
    """Formaterar priset med rätt decimaler för Dashboard."""
    if p is None: return "N/A"
    price_format = f"{p:,.4f}" if p < 10 else f"{p:,.2f}"
    return price_format.replace(",", "TEMP").replace(".", ",").replace("TEMP", " ")

def format_price_telegram(p):
    """Formaterar priset för Telegram (få decimaler, inga tusentalsavgränsare för små valutor)."""
    if p is None: return "N/A"
    # Använd 4 decimaler för små priser (under 10), annars 2, utan tusentalsavgränsare.
    if p < 10:
        return f"{p:.4f}".replace(".", ",")
    else:
        # behåll tusentalsavgränsare för stora tal som BTC
        return f"{p:,.2f}".replace(",", "TEMP").replace(".", ",").replace("TEMP", " ")

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

def format_change_telegram(c):
    """Formaterar procentuell förändring för Telegram-text."""
    if c is None: return " N/A "
    
    sign = "+" if c >= 0 else ""
    # Använd fast bredd och begränsa till 4 tecken + symbol/tecken + 2 decimaler
    # Exempel: '+12.34%' eller '-0.56%'
    return f"{sign}{c:.2f}%".rjust(6)

def format_summary_for_telegram(data, eur_to_sek, timezone_offset_hours):
    """
    Formaterar den sorterade listan av kryptovalutor till ett läsbart Telegram-meddelande.
    """
    
    # 1. Förbered och sortera data (samma logik som i update_all_live_data)
    summary_data = []
    for label in COINS_LABELS:
        coin_symbol_loop = label.split(' ')[0]
        price_eur = data.get(f'{coin_symbol_loop}/EUR')
        percent_data_loop = data.get('ALL_PERCENT_CHANGE', {}).get(coin_symbol_loop, {})
        sort_key_30m = percent_data_loop.get('30m') if percent_data_loop.get('30m') is not None else -float('inf')
        sort_key_1h = percent_data_loop.get('1h') if percent_data_loop.get('1h') is not None else -float('inf')
        sort_key_6h = percent_data_loop.get('6h') if percent_data_loop.get('6h') is not None else -float('inf')

        summary_data.append({
            'symbol': coin_symbol_loop,
            'price_eur': price_eur,
            'percent_data': percent_data_loop,
            'sort_30m': sort_key_30m,
            'sort_1h': sort_key_1h,
            'sort_6h': sort_key_6h
        })

    # Sortera efter 30m, 1h, 6h förändring (högst först)
    summary_data.sort(key=lambda x: (x['sort_30m'], x['sort_1h'], x['sort_6h']), reverse=True)
    
    # 2. Skapa meddelandehuvud
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc + timedelta(hours=timezone_offset_hours)
    
    header = (
        f"🌟 **MARKNADSSAMMANFATTNING** 🌟\n"
        f"Tid: *{now_local.strftime('%Y-%m-%d %H:%M:%S')} CET/CEST*\n\n"
    )
    
    # 3. Skapa tabell med monospace-font (```) för justering
    # Vi använder f-strängar och rjust() för att simulera en fast bredd i Telegram.
    
    # Rubriker: Symbol | Pris(EUR) | 30m | 1h | 6h
    table_header = (
        "```"
        "VALUTA | PRIS EUR | 30M |  1H  |  6H \n"
        "-------------------------------------\n"
    )
    
    table_rows = []
    for item in summary_data:
        symbol = item['symbol'].ljust(6)
        
        # Formatera priset
        price_str = format_price_telegram(item['price_eur'])
        price_display = price_str.rjust(8) # Justera priset (t.ex. 0,5544)

        change_30m = format_change_telegram(item['percent_data'].get('30m'))
        change_1h = format_change_telegram(item['percent_data'].get('1h'))
        change_6h = format_change_telegram(item['percent_data'].get('6h'))
        
        row = f"{symbol} | {price_display} | {change_30m} |{change_1h} |{change_6h}"
        table_rows.append(row)

    table_body = "\n".join(table_rows)
    table_footer = "```"
    
    return header + table_header + table_body + table_footer


# --- Bakgrundsjobb ---

# NY FUNKTION: background_summary_sender
def background_summary_sender(redis_instance):
    """Schemalägger sändning av marknadssammanfattningen till Telegram."""
    
    # Antag att systemet kör i CET/CEST (+1 eller +2 timmar från UTC)
    # Vi använder en timmes offset just nu, men detta kan variera baserat på sommar/vintertid.
    # För att vara säker används en 1 timmes cykel för att kontrollera.
    
    while True:
        try:
            now_utc = datetime.now(timezone.utc)
            # För Dashboards: Lägg till 1 timme för att få CET/CEST.
            # OBS: Detta fungerar inte perfekt över sommar/vintertid men är en bra start.
            timezone_offset_hours = 1 if now_utc.month in range(3, 10) else 1 # Vi använder 1 för att matcha CET/CEST med ett antagande.
            now_local = now_utc + timedelta(hours=timezone_offset_hours)
            
            current_hour = now_local.hour
            current_minute = now_local.minute
            
            # Kontrollera om det är dags att skicka (på hel timme)
            if current_hour in SUMMARY_SCHEDULE_HOURS and current_minute == 0:
                # Använd Redis för att spärra sändningen i 65 minuter för att undvika dubbla meddelanden
                # ifall systemet kraschar och startar om snabbt under samma minut.
                
                # Nyckel: YYYYMMDD_HH
                debounce_key = f"{REDIS_SUMMARY_KEY}:{now_local.strftime('%Y%m%d_%H')}"
                
                if redis_instance and redis_instance.set(debounce_key, 1, ex=3600*1, nx=True): # Spärra i 1 timme
                    logger.info(f"Dags att skicka schemalagd sammanfattning för {current_hour}:00.")
                    
                    data = get_data_from_redis()
                    if data:
                        eur_to_sek = data.get('EUR_SEK_RATE', 11.0)
                        
                        # Formatera meddelandet
                        telegram_message = format_summary_for_telegram(data, eur_to_sek, timezone_offset_hours)
                        
                        # Skicka meddelandet
                        if send_telegram_message(telegram_message):
                            logger.info(f"✅ Schemalagd sammanfattning skickad till Telegram kl. {current_hour}:00.")
                        else:
                            logger.error("❌ Misslyckades skicka schemalagd sammanfattning till Telegram.")
                    else:
                        logger.warning("Kunde inte hämta data från Redis för schemalagd sammanfattning.")

            # Vänta 60 sekunder
            time.sleep(60)

        except Exception as e:
            logger.error(f"❌ Fel i schemaläggningstråd: {e}")
            time.sleep(60)


# MODIFIERAD FUNKTION: background_data_fetch (ingen funktionsändring, bara namnet på variabeln i alert)
def background_data_fetch(redis_instance):
    """Hämtar Ticker och OHLC data, beräknar förändringar och cachar till Redis. KÖR ÄVEN ALERTER."""
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
            all_24h_range_ohlc = {} 
            alert_data_for_sending = {} 
            
            # 1. Hämta data och beräkna %-förändring OCH 24h Hög/Låg för ALLA VALUTOR
            for label, ticker in CRYPTO_PAIRS.items():
                coin_symbol = label.split(' ')[0]
                current_price_eur = new_data.get(f'{coin_symbol}/EUR')
                
                if current_price_eur is None:
                    continue
                    
                periods_ago_24h = 86400 
                ohlc_5min_data = fetch_ohlc_data_from_kraken(ticker, OHLC_CACHE_INTERVAL_MIN, periods_ago_24h) 
                
                if ohlc_5min_data:
                    prices_eur = [item['price'] for item in ohlc_5min_data]
                    if prices_eur:
                        max_ohlc = max(prices_eur) 
                        min_ohlc = min(prices_eur)
                        all_24h_range_ohlc[coin_symbol] = {'high_eur': max_ohlc, 'low_eur': min_ohlc}
                    
                    if coin_symbol == DEFAULT_COIN_SYMBOL:
                         ohlc_cache_key = f'OHLC_CACHED_{OHLC_CACHE_INTERVAL_MIN}MIN_{ticker}'
                         redis_instance.set(ohlc_cache_key, json.dumps(ohlc_5min_data), ex=7200) 
                         
                    short_term_periods = {k: v for k, v in TIME_WINDOWS.items() if v['interval'] == OHLC_CACHE_INTERVAL_MIN}
                    percent_changes = calculate_percentage_changes(ohlc_5min_data, current_price_eur, short_term_periods)
                else:
                    short_term_periods = {k: v for k, v in TIME_WINDOWS.items() if v['interval'] == OHLC_CACHE_INTERVAL_MIN}
                    percent_changes = {k: None for k in short_term_periods.keys()}

                periods_ago_30d = 2592000 
                ohlc_1day_data = fetch_ohlc_data_from_kraken(ticker, 1440, periods_ago_30d) 
                long_term_periods = {k: v for k, v in TIME_WINDOWS.items() if v['interval'] == 1440}
                long_term_changes = calculate_percentage_changes(ohlc_1day_data, current_price_eur, long_term_periods)
                
                percent_changes.update(long_term_changes) 
                all_percent_changes[coin_symbol] = percent_changes
                
                alert_data_for_sending[coin_symbol] = {
                    'changes': percent_changes,
                    'price_eur': current_price_eur 
                }
                
                time.sleep(0.1) 
            
            # --- Steg 2: KÖR ALERT KONTROLL ---
            if redis_instance:
                check_and_send_alerts(alert_data_for_sending, redis_instance)
            
            # --- Steg 3: SPARA TILL REDIS ---
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
            
def check_and_send_alerts(alert_data, r_instance):
    """(Funktionens logik oförändrad från föregående steg, tar bort Trigger och lägger till pris)"""
    if not r_instance:
        return

    for coin_symbol, data in alert_data.items():
        changes = data['changes']
        current_price_eur = data['price_eur']
        coin_label = SYMBOL_TO_LABEL.get(coin_symbol, coin_symbol)
        
        if current_price_eur is None:
            continue
            
        formatted_price = format_price_telegram(current_price_eur)
        
        for period in ALERT_PERIODS:
            change_percent = changes.get(period)
            
            if change_percent is None:
                continue
            
            # --- UPPGÅNGAR ---
            if change_percent > 0:
                highest_threshold_met = None
                for threshold in ALERT_THRESHOLDS_UP:
                    if change_percent >= threshold:
                        highest_threshold_met = threshold
                        break 
                
                if highest_threshold_met is not None:
                    key = f"alert:{coin_symbol}:{period}:+{highest_threshold_met}"
                    
                    if r_instance.set(key, 1, ex=ALERT_DEBOUNCE_SECONDS, nx=True):
                        message = (
                            f"🔥 **HÖGSTA PRISUPPGÅNG ALERT** 🔥\n"
                            f"Valuta: *{coin_label} ({coin_symbol})*\n"
                            f"Aktuellt Pris: *{formatted_price} EUR*\n"
                            f"Rörelse: *+{change_percent:.2f}%* under {period}"
                        )
                        send_telegram_message(message)
                        logger.info(f"Telegram Alert skickad: {coin_symbol} HÖGST +{highest_threshold_met}% på {period}")
                        
            # --- NEDGÅNGAR ---
            elif change_percent < 0:
                lowest_threshold_met = None
                for threshold in ALERT_THRESHOLDS_DOWN:
                    if change_percent <= threshold: 
                        lowest_threshold_met = threshold
                        break 
                
                if lowest_threshold_met is not None:
                    key = f"alert:{coin_symbol}:{period}:{lowest_threshold_met}"
                    
                    if r_instance.set(key, 1, ex=ALERT_DEBOUNCE_SECONDS, nx=True):
                        message = (
                            f"🔻 **LÄGSTA PRISNEDGÅNG ALERT** 🔻\n"
                            f"Valuta: *{coin_label} ({coin_symbol})*\n"
                            f"Aktuellt Pris: *{formatted_price} EUR*\n"
                            f"Rörelse: *{change_percent:.2f}%* under {period}"
                        )
                        send_telegram_message(message)
                        logger.info(f"Telegram Alert skickad: {coin_symbol} LÄGST {lowest_threshold_met}% på {period}")

if r:
    # 1. Tråd för live data och alerts
    worker_thread = threading.Thread(target=background_data_fetch, args=(r,), daemon=True)
    worker_thread.start()
    logger.debug(">>> Bakgrundstråd (Live Data/Alerts) startad!")
    
    # 2. Tråd för schemalagda sammanfattningar
    summary_thread = threading.Thread(target=background_summary_sender, args=(r,), daemon=True)
    summary_thread.start()
    logger.debug(">>> Bakgrundstråd (Schemalagd Sammanfattning) startad!")


# --- Dash App Initiering och Layout (oförändrad) ---

app = dash.Dash(__name__, external_stylesheets=['[https://codepen.io/chriddyp/cnWqWbL.css](https://codepen.io/chriddyp/cnWqWbL.css)'])
server = app.server 

def create_selected_coin_box(label, symbol, price, currency, eur_rate, high_eur, low_eur, percent_data): # (oförändrad)
    # ... (Dashboard HTML-generering)
    price_text = f"{format_price_display(price)} {currency}"
    coin_emoji = CRYPTO_EMOJIS.get(symbol, '')
    
    change_24h = percent_data.get('24h')
    price_color = '#28a745' if change_24h is not None and change_24h > 0 else '#dc3545' if change_24h is not None and change_24h < 0 else '#495057'
    
    high_display = high_eur * eur_rate if currency == 'SEK' and high_eur is not None else high_eur
    low_display = low_eur * eur_rate if currency == 'SEK' and low_eur is not None else low_eur

    periods_col1 = ['30m', '1h', '3h'] 
    periods_col2 = ['6h', '24h', '7d', '30d'] 

    def create_change_display(period):
        return html.Div(
            style={'display': 'flex', 'justifyContent': 'space-between', 'margin': '3px 0', 'padding': '0 5px', 'fontSize': '0.9em'},
            children=[
                html.Span(f"{period}:", style={'color': '#6c757d', 'fontWeight': 'normal'}),
                format_change(percent_data.get(period))
            ]
        )
    
    col1 = html.Div(
        style={'flex': '1 1 30%', 'minWidth': '220px', 'paddingRight': '15px', 'borderRight': '1px solid #dee2e6'},
        children=[
            html.H2(
                html.Span([html.Span(f"{coin_emoji} ", style={'marginRight': '5px'}), f"{label} ({symbol})"]), 
                style={'fontSize': '1.5em', 'color': '#0056b3', 'marginBottom': '5px', 'textAlign': 'center'}
            ),
            html.Div(style={'textAlign': 'center', 'marginTop': '10px'}, children=[
                html.P("Nuvarande Pris", style={'margin': '0', 'color': '#6c757d', 'fontWeight': 'bold', 'fontSize': '0.9em'}),
                html.P(price_text, id='current-price-display', style={'fontSize': '2.5em', 'fontWeight': '800', 'color': price_color, 'margin': '0'})
            ]),
        ]
    )

    col2 = html.Div(
        style={'flex': '1 1 20%', 'minWidth': '150px', 'padding': '0 15px', 'borderRight': '1px solid #dee2e6'},
        children=[
            html.P("24h Intervall (OHLC)", style={'margin': '0 0 10px 0', 'color': '#495057', 'fontWeight': 'bold', 'textAlign': 'center', 'fontSize': '0.9em'}),
            html.Div(style={'padding': '5px 0', 'fontSize': '0.9em'}, children=[
                html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center', 'marginBottom': '5px'}, children=[
                    html.Span("Hög:", style={'fontWeight': 'bold', 'color': 'green'}),
                    html.Span(f"{format_price_display(high_display)} {currency}", style={'color': 'green', 'fontWeight': '600'})
                ]),
                html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center'}, children=[
                    html.Span("Låg:", style={'fontWeight': 'bold', 'color': 'red'}),
                    html.Span(f"{format_price_display(low_display)} {currency}", style={'color': 'red', 'fontWeight': '600'})
                ]),
            ])
        ]
    )

    col3 = html.Div(
        style={'flex': '1 1 45%', 'minWidth': '250px', 'paddingLeft': '15px'},
        children=[
            html.P("Prisrörelser (%)", style={'margin': '0 0 10px 0', 'color': '#495057', 'fontWeight': 'bold', 'textAlign': 'center', 'fontSize': '0.9em'}),
            html.Div(
                style={'display': 'flex', 'justifyContent': 'space-around', 'gap': '10px'},
                children=[
                    html.Div(
                        style={'flex': '1 1 45%', 'minWidth': '100px'},
                        children=[create_change_display(p) for p in periods_col1]
                    ),
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

def create_summary_row(coin_symbol, label, current_price, percent_data, currency, is_selected, eur_to_sek): # (oförändrad)
    # ... (Dashboard HTML-generering)
    coin_emoji = CRYPTO_EMOJIS.get(coin_symbol, '')
    
    row_bg_color = '#f0f8ff' if is_selected else 'white'
    price_display = current_price * eur_to_sek if currency == 'SEK' and current_price is not None else current_price
    
    col_style = {'flex': '1 1 10%', 'textAlign': 'right', 'whiteSpace': 'nowrap', 'padding': '0 5px', 'fontSize': '0.8em'}

    row_columns = [
        html.Div(
            style={'flex': '0 0 160px', 'textAlign': 'left', 'fontWeight': 'bold', 'color': '#0056b3', 'paddingLeft': '5px', 'whiteSpace': 'nowrap'},
            children=[html.Span(f"{coin_emoji} {coin_symbol}")]
        ),
        html.Div(
            f"{format_price_display(price_display)}",
            style={'flex': '0 0 100px', 'textAlign': 'right', 'fontWeight': 'bold', 'paddingRight': '5px'}
        ),
        html.Div(format_change(percent_data.get('30m')), style=col_style),
        html.Div(format_change(percent_data.get('1h')), style=col_style),
        html.Div(format_change(percent_data.get('3h')), style=col_style),
        html.Div(format_change(percent_data.get('6h')), style=col_style),
        html.Div(format_change(percent_data.get('7d')), style=col_style),
        html.Div(format_change(percent_data.get('30d')), style=col_style),
    ]

    return html.Div(
        id={'type': 'summary-card', 'index': coin_symbol},
        n_clicks=0,
        style={
            'display': 'flex',
            'justifyContent': 'space-between',
            'alignItems': 'center',
            'padding': '7px 0',
            'borderBottom': '1px solid #eee',
            'cursor': 'pointer',
            'backgroundColor': row_bg_color,
            'transition': 'background-color 0.2s ease',
            'boxShadow': '0 1px 2px rgba(0,0,0,0.05)' if is_selected else 'none'
        },
        children=row_columns
    )


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
                    html.Label("Välj fiatvaluta:", style={'marginBottom': '5px', 'fontWeight': 'bold', 'color': '#495057', 'display': 'block'}),
                    dcc.Dropdown(id='currency-dropdown', options=[{'label': f'{c} ({c})', 'value': c} for c in CURRENCIES], value='EUR', clearable=False),
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
                     options=[{'label': config['name'].split(' ')[1].replace('(', '').replace(')', ''), 'value': key} for key, config in TREND_WINDOWS.items()],
                     value=list(TREND_WINDOWS.keys()), # Använd alla som default
                     inline=True,
                     style={'display': 'inline-block'}
                 ),
            ]),
            dcc.Loading(id="loading-1", type="circle", children=[dcc.Graph(id='live-update-graph', config={'displayModeBar': False})]),
        ]),
        
        html.Div(id='crypto-summary-container', style={'marginTop': '30px', 'paddingTop': '20px', 'borderTop': '1px solid #dee2e6', 'marginBottom': '30px'}, children=[
             html.H3('📊 Sammanfattning: Prisrörelser', style={'fontSize': '1.3em', 'color': '#0056b3', 'marginBottom': '10px'}),
             dcc.Loading(id="loading-2", type="dot", children=[html.Div(id='crypto-summary')])
        ]),
        
        html.Div(style={'marginTop': '40px', 'padding': '20px', 'border': '1px solid #17a2b8', 'borderRadius': '6px', 'backgroundColor': '#e8f7fa'}, children=[
            html.H3('🔔 Automatisk Telegram Alert-status (Aktiv)', style={'fontSize': '1.3em', 'color': '#17a2b8', 'marginBottom': '10px'}),
            html.P('Aviseringar skickas automatiskt när det högsta/lägsta tröskelvärdet uppnås under 30m, 1h, 3h, 6h, 12h eller 24h:', style={'margin': '0 0 10px 0'}),
            html.Div(style={'display': 'flex', 'gap': '30px'}, children=[
                html.Div([
                    html.P('**Uppgångar (Högsta skickas):**', style={'fontWeight': 'bold', 'color': '#28a745', 'margin': '0'}),
                    html.Ul([html.Li(f'+{t}%') for t in ALERT_THRESHOLDS_UP[::-1]], style={'marginTop': '5px', 'paddingLeft': '20px'})
                ]),
                html.Div([
                    html.P('**Nedgångar (Lägsta skickas):**', style={'fontWeight': 'bold', 'color': '#dc3545', 'margin': '0'}),
                    html.Ul([html.Li(f'{t}%') for t in ALERT_THRESHOLDS_DOWN], style={'marginTop': '5px', 'paddingLeft': '20px'})
                ])
            ]),
            html.P(f"Obs! Samma alert skickas max en gång per {ALERT_DEBOUNCE_SECONDS / 3600:.0f} timmar.", style={'fontSize': '0.9em', 'color': '#6c757d', 'marginTop': '10px'}),
            html.P(f"**Schemalagda sammanställningar skickas kl: {', '.join([f'{h:02d}:00' for h in SUMMARY_SCHEDULE_HOURS])} (CET/CEST)**", style={'fontSize': '0.9em', 'color': '#17a2b8', 'marginTop': '10px', 'fontWeight': 'bold'}),
        ]),
    ]),
    dcc.Interval(id='interval-component', interval=UPDATE_INTERVAL_SECONDS_DATA*1000, n_intervals=0)
])

# ... (Callbacks update_all_live_data, update_trendline_visibility, update_dropdown_on_card_click oförändrade)

if __name__ == '__main__':
    app.run_server(debug=True)