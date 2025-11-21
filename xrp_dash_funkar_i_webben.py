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

# --- Konfiguration och Initialisering ---

logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

# =========================================================================
# === TELEGRAM Konfiguration (Hämta från Render Miljövariabler) ===
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    logger.warning("❌ TELEGRAM-inställningar saknas. Alerts kommer inte att fungera.")
# =========================================================================

# --- API Konstanter ---
KRAKEN_TICKER_API_URL = "https://api.kraken.com/0/public/Ticker"
KRAKEN_OHLC_API_URL = "https://api.kraken.com/0/public/OHLC"
EXCHANGE_RATE_URL = "https://api.exchangerate-api.com/v4/latest/EUR"

# Lista över tillgängliga kryptopar och deras Kraken-tickers (baserade i EUR)
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

# Extrahera symboler och tickers
COINS_LABELS = list(CRYPTO_PAIRS.keys())
COINS_SYMBOLS = [label.split(' ')[0] for label in COINS_LABELS]
SYMBOL_TO_LABEL = {label.split(' ')[0]: label for label in COINS_LABELS}

CURRENCIES = ['EUR', 'SEK']

# Inställningar för Dash
UPDATE_INTERVAL_SECONDS_DATA = 60 
OHLC_CACHE_INTERVAL_MIN = 5 # 5 minuters intervall stöds av Kraken.

# Beräkningskonstanter för procentrörelse (i 5-minuters block)
TIME_WINDOWS = {
    '30m': 6,  # 30 minuter / 5 min/block = 6 block
    '1h': 12,   # 1 timme / 5 min/block = 12 block
    '3h': 36,   # 3 timmar / 5 min/block = 36 block
    '6h': 72,   # 6 timmar / 5 min/block = 72 block
    '24h': 288, # 24 timmar / 5 min/block = 288 block
}


# --- Redis Konfiguration ---
REDIS_URL = os.environ.get('REDIS_URL')

if REDIS_URL:
    try:
        r = from_url(REDIS_URL)
        r.ping()
        logger.debug("✅ Ansluten till Redis!")
    except exceptions.ConnectionError as e:
        logger.error(f"❌ Kunde inte ansluta till Redis: {e}")
        r = None
else:
    logger.warning("REDIS_URL hittades inte. Appen kommer inte att cache:a data.")
    r = None

# Fallback/Standarddata 
DEFAULT_DATA = {
    'XRP/EUR': 0.50, 'XRP/SEK': 5.50,
    'timestamp': time.time(),
    'EUR_SEK_RATE': 11.0, 
    'ALL_24H_RANGE': {'XRP': {'high_eur': 0.52, 'low_eur': 0.48}},
    'ALL_PERCENT_CHANGE': {} # Ny nyckel för procentrörelser
}

# --- Telegram Utskick Funktion (Oförändrad) ---

def send_telegram_alert(coin_label, price, currency, threshold):
    # [KOD FÖR TELEGRAM ALERT]
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("Kan inte skicka Telegram-meddelande: Bot Token eller Chat ID saknas.")
        return False
        
    message = (
        f"🚨 Krypto Alert: Prisgräns nådd! 🚨\n\n"
        f"Valuta: {coin_label}\n"
        f"Gränsvärde: {threshold:,.4f} {currency}\n"
        f"Nuvarande pris: {price:,.4f} {currency}\n"
        f"Tid: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} UTC"
    )

    telegram_api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    try:
        response = requests.post(telegram_api_url, data={
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'Markdown'
        }, timeout=10)
        
        response.raise_for_status() 
        
        logger.info(f"✅ Telegram-meddelande skickat: {coin_label} till {TELEGRAM_CHAT_ID}")
        return True
        
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Fel vid utskick till Telegram: {e}. Svar: {response.text if 'response' in locals() else 'Inget svar'}")
        return False

# --- API Data Hämtning Funktioner (Oförändrade) ---
def fetch_exchange_rate():
    # [KOD FÖR EXCHANGE RATE]
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
    # [KOD FÖR CRYPTO TICKER DATA]
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
            
            if coin_info is None:
                 for key, info in result_key.items():
                    if info.get('altname') == coin_symbol:
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

def fetch_ohlc_data_from_kraken(kraken_ticker, interval):
    # [KOD FÖR OHLC DATA MED SINCE=24H]
    time_24h_ago = int(time.time()) - 86400 
    
    params = {
        'pair': kraken_ticker, 
        'interval': interval,
        'since': time_24h_ago
    }
        
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

# --- NY FUNKTION: Beräkna Procentrörelse ---

def calculate_percentage_changes(ohlc_data, current_price):
    """Beräknar procentuell förändring baserat på historisk OHLC-data."""
    
    changes = {}
    
    # Historisk data måste vara sorterad i tid (ASC)
    if not ohlc_data:
        return {key: 0.0 for key in TIME_WINDOWS}

    # Den äldsta datan ligger i början av listan (index 0) om den kommer från Kraken med 'since'
    
    # Hämta referenspriser baserat på antalet 5-minuters block
    for period, blocks in TIME_WINDOWS.items():
        
        # Säkerställ att vi har tillräckligt med data för perioden + nuvarande pris
        if len(ohlc_data) >= blocks:
            # Hämta priset vid referenspunkten (t.ex. 6 block bakåt för 30m)
            reference_price = ohlc_data[-blocks]['price']
            
            if reference_price and reference_price > 0:
                change = ((current_price - reference_price) / reference_price) * 100
                changes[period] = change
            else:
                changes[period] = 0.0
        else:
            # Om datan är nyare än t.ex. 6h (72 block) kan vi inte beräkna 24h
            changes[period] = 0.0 
            
    return changes

# --- Bakgrundstrådens Logik (Fullständig Cache) ---

def update_redis_cache(redis_instance):
    """Loop som körs i bakgrunden för att uppdatera ALL data i Redis-cachen, 
       inklusive 5-min OHLC-historik och procentrörelser för ALLA mynt."""
    
    UPDATE_CYCLE_SECONDS = 120 
    
    while True:
        cycle_start_time = time.time()
        
        try:
            logger.debug("--- Bakgrundstråd: Startar fullständig uppdateringscykel ---")
            
            # 1. Hämta realtidsdata (Nuvarande Pris & 24H High/Low)
            new_data = fetch_crypto_data()
            
            # Initiera procent-dict för lagring
            all_percent_changes = {} 
            
            ohlc_interval = OHLC_CACHE_INTERVAL_MIN 
            
            for label, ticker in CRYPTO_PAIRS.items():
                coin_symbol = label.split(' ')[0]
                
                # Hämta aktuellt pris i EUR
                current_price_eur = new_data.get(f'{coin_symbol}/EUR')
                
                # 2. Hämta OHLC-data (5 minuter)
                ohlc_data = fetch_ohlc_data_from_kraken(ticker, interval=ohlc_interval) 
                
                if ohlc_data and current_price_eur:
                    
                    # Beräkna procentrörelser baserat på 5-minuters datan
                    percent_changes = calculate_percentage_changes(ohlc_data, current_price_eur)
                    all_percent_changes[coin_symbol] = percent_changes
                    
                    # Lagra OHLC i Redis
                    ohlc_cache_key = f'OHLC_CACHED_{ohlc_interval}MIN_{ticker}' 
                    redis_instance.set(ohlc_cache_key, json.dumps(ohlc_data), ex=7200) 
                    logger.debug(f"   >>> OHLC {ohlc_interval}-min sparad i cache för {ticker}")
                
                # Pausa 2 sekunder
                time.sleep(2) 
            
            # 3. Uppdatera Ticker-data med procentrörelser
            new_data['ALL_PERCENT_CHANGE'] = all_percent_changes
            
            if redis_instance:
                redis_instance.set('crypto_data', json.dumps(new_data), ex=UPDATE_CYCLE_SECONDS + 5)
            
            # --- Cykel avslutad ---
            
            cycle_duration = time.time() - cycle_start_time
            logger.debug(f"✅ Fullständig cache-cykel slutförd på {cycle_duration:.2f} sekunder.")
            
            time_to_sleep = UPDATE_CYCLE_SECONDS - cycle_duration
            if time_to_sleep > 0:
                 logger.debug(f"Väntar {time_to_sleep:.2f} sekunder till nästa cykel.")
                 time.sleep(time_to_sleep)
            else:
                 logger.warning(f"Cykeln tog för lång tid ({cycle_duration:.2f}s)! Överskrider uppdateringsintervallet.")


        except Exception as e:
            logger.error(f"❌ Kritisk fel i bakgrundstråd: {e}")
            time.sleep(60)
            
if r:
    worker_thread = threading.Thread(target=update_redis_cache, args=(r,), daemon=True)
    worker_thread.start()
    logger.debug(">>> Bakgrundstråd startad och snurrar!")

# --- Dash Applikation och Layout (oförändrad) ---
app = dash.Dash(__name__, external_stylesheets=[
    'https://codepen.io/chriddyp/pen/bWLwgP.css' 
])
server = app.server
# [LAYOUT KOD OFÖRÄNDRAD]

app.layout = html.Div(style={
    'backgroundColor': '#f8f9fa', 
    'minHeight': '100vh', 
    'padding': '40px 10px',
    'fontFamily': 'Roboto, Arial, sans-serif'
}, children=[
    
    html.Div(style={
        'maxWidth': '1400px',
        'margin': '40px auto',
        'padding': '30px',
        'borderRadius': '12px',
        'boxShadow': '0 4px 12px rgba(0, 0, 0, 0.1)',
        'backgroundColor': 'white',
        'border': '1px solid #dee2e6'
    }, children=[
        
        html.H1('📈 MTS Krypto Dashboard (Kraken Live)', style={'textAlign': 'center', 'color': '#0056b3', 'marginBottom': '30px', 'fontSize': '1.8em'}),

        html.Div(style={'display': 'flex', 'justifyContent': 'center', 'gap': '20px', 'alignItems': 'center', 'marginBottom': '30px'}, children=[
            
            html.Div(style={'flexGrow': 1, 'maxWidth': '300px'}, children=[
                html.Label("Välj kryptovaluta:", style={'marginBottom': '5px', 'fontWeight': 'bold', 'color': '#495057', 'display': 'block'}),
                dcc.Dropdown(
                    id='coin-dropdown',
                    options=[{'label': label, 'value': label.split(' ')[0]} for label in COINS_LABELS],
                    value=DEFAULT_PAIR_KEY.split(' ')[0], 
                    clearable=False,
                ),
            ]),
            
            html.Div(style={'flexGrow': 1, 'maxWidth': '180px'}, children=[
                html.Label("Välj fiatvaluta:", style={'marginBottom': '5px', 'fontWeight': 'bold', 'color': '#495057', 'display': 'block'}),
                dcc.Dropdown(
                    id='currency-dropdown',
                    options=[{'label': f'{c} ({c})', 'value': c} for c in CURRENCIES],
                    value='EUR',
                    clearable=False,
                ),
            ]),
        ]),

        html.Div(id='current-price', style={'textAlign': 'center', 'fontSize': '3em', 'fontWeight': '800', 'color': '#28a745', 'marginBottom': '5px'}),
        html.Div(id='last-updated', style={'textAlign': 'center', 'fontSize': '0.9em', 'color': '#6c757d', 'marginBottom': '40px'}),
        
        dcc.Loading(
            id="loading-1",
            type="circle",
            children=[
                dcc.Graph(
                    id='live-update-graph',
                    config={'displayModeBar': False} 
                )
            ]
        ),
        
        html.Div(style={'marginTop': '40px', 'paddingTop': '20px', 'borderTop': '1px solid #dee2e6'}, children=[
            html.H3('🔔 Telegram Alert-inställningar', style={'fontSize': '1.3em', 'color': '#0056b3', 'marginBottom': '15px'}),
            
            html.P("Skickar notis när priset når eller överstiger ditt angivna gränsvärde."),
            
            html.Div(style={'display': 'flex', 'gap': '10px', 'alignItems': 'center'}, children=[
                dcc.Input(
                    id='alert-threshold',
                    type='number',
                    placeholder='Ange gränsvärde',
                    style={'flexGrow': 1, 'padding': '10px', 'borderRadius': '6px', 'border': '1px solid #ccc'}
                ),
                html.Button('Aktivera Alert', id='alert-button', n_clicks=0, style={
                    'backgroundColor': '#17a2b8', 
                    'color': 'white', 
                    'padding': '10px 15px', 
                    'borderRadius': '6px', 
                    'border': 'none',
                    'cursor': 'pointer',
                    'fontWeight': 'bold'
                })
            ]),
            html.Div(id='alert-output', style={'marginTop': '10px', 'fontSize': '0.9em', 'minHeight': '20px'})
        ]),

        html.Div(style={'marginTop': '50px', 'paddingTop': '20px', 'borderTop': '1px solid #dee2e6'}, children=[
            html.H3('📊 Sammanfattning av alla valutor', style={'fontSize': '1.3em', 'color': '#0056b3', 'marginBottom': '20px'}),
            
            dcc.Loading(
                id="loading-2",
                type="dot",
                children=[
                    html.Div(id='crypto-summary', style={
                        'display': 'flex',
                        'flexWrap': 'wrap',  
                        'gap': '15px',      
                        'justifyContent': 'flex-start'
                    })
                ]
            )
        ]),
        
    ]),

    dcc.Interval(
        id='interval-component',
        interval=5*1000, 
        n_intervals=0
    )
])


# --- Hämta data från Redis (Oförändrad) ---

def get_data_from_redis():
    # [KOD FÖR HÄMTA FRÅN REDIS]
    if r:
        try:
            cached_data = r.get('crypto_data')
            if cached_data:
                return json.loads(cached_data)
            else:
                logger.warning("Cache 'crypto_data' är tom. Väntar på bakgrundstråd.")
                return None
        except exceptions.ConnectionError as e:
            logger.error(f"Redis-anslutningsfel i callback: {e}")
            return None
    return None

# --- Callback för Pris och Graf (Oförändrad) ---

@app.callback(Output('current-price', 'children'),
              Output('last-updated', 'children'),
              Output('live-update-graph', 'figure'),
              [Input('interval-component', 'n_intervals'),
               Input('coin-dropdown', 'value'),
               Input('currency-dropdown', 'value')])
def update_metrics_and_graph(n, coin_symbol, currency):
    # [KOD FÖR METRICS OCH GRAF]
    data = get_data_from_redis()
    
    if data is None or 'EUR_SEK_RATE' not in data:
        price_text = "Laddar data..."
        updated_text = "Väntar på data från Kraken/Redis..."
        figure = go.Figure(go.Scatter(x=[0], y=[0], mode='text', text=['Laddar...']))
        figure.update_layout(title="Hämtar data...", template="plotly_white", height=400)
        return price_text, updated_text, figure

    price_key = f'{coin_symbol}/{currency}'
    current_price = data.get(price_key)
    timestamp = data.get('timestamp')
    eur_to_sek = data.get('EUR_SEK_RATE', 11.0)
    
    if current_price is None:
        price_text = f"❌ Pris för {coin_symbol}/{currency} saknas."
        updated_text = f"Data saknas eller är inte tillgänglig på Kraken."
        figure = go.Figure(go.Scatter(x=[0], y=[0], mode='text', text=['❌ Kunde inte hämta pris.']))
        figure.update_layout(title="Kunde inte hämta pris.", template="plotly_white", height=400)
        return price_text, updated_text, figure
    
    if current_price < 10:
        price_format = f"{current_price:,.4f}"
    else:
        price_format = f"{current_price:,.2f}"
        
    price_format = price_format.replace(",", "TEMP").replace(".", ",").replace("TEMP", " ") 

    coin_label = SYMBOL_TO_LABEL.get(coin_symbol, coin_symbol)
    price_text = f"{coin_label}: {price_format} {currency}"
    updated_text = f"Senast uppdaterad (Realtime Ticker): {time.strftime('%H:%M:%S', time.gmtime(timestamp))} UTC"

    
    figure = go.Figure()
    ohlc_interval = OHLC_CACHE_INTERVAL_MIN 
    kraken_ticker = CRYPTO_PAIRS[coin_label]
    
    ohlc_cache_key = f'OHLC_CACHED_{ohlc_interval}MIN_{kraken_ticker}'
    historical_data = []
    
    if r:
        cached_ohlc = r.get(ohlc_cache_key)
        if cached_ohlc:
            historical_data = json.loads(cached_ohlc)
            logger.debug(f"Använder cachad {ohlc_interval}-min OHLC data för {kraken_ticker}")
    
    range_data_raw = data.get('ALL_24H_RANGE', {}).get(coin_symbol, {})
    high_24h_eur = range_data_raw.get('high_eur')
    low_24h_eur = range_data_raw.get('low_eur')
    
    
    if historical_data:
        
        times = [time.strftime('%H:%M', time.gmtime(item['time'])) for item in historical_data]
        prices_eur = [item['price'] for item in historical_data]
        
        if currency == 'SEK':
            prices_display = [p * eur_to_sek for p in prices_eur]
            high_24h_display = high_24h_eur * eur_to_sek if high_24h_eur is not None else None
            low_24h_display = low_24h_eur * eur_to_sek if low_24h_eur is not None else None
        else:
            prices_display = prices_eur
            high_24h_display = high_24h_eur
            low_24h_display = low_24h_eur
        
        # Huvudlinje: Kurs
        figure.add_trace(go.Scatter(
            x=times,
            y=prices_display,
            mode='lines',
            name=f'Kurs ({ohlc_interval} min intervall)',
            line=dict(color='#0056b3', width=3),
        ))
        
        # Lägg till 24h Högsta (Grön)
        if high_24h_display is not None:
            figure.add_hline(
                y=high_24h_display, 
                line_dash="dot", 
                line_color="green",
                annotation_text=f"24h Högsta: {high_24h_display:,.4f} {currency}",
                annotation_position="top right",
                name="24h Högsta",
                layer="below"
            )

        # Lägg till 24h Lägsta (Röd)
        if low_24h_display is not None:
            figure.add_hline(
                y=low_24h_display, 
                line_dash="dot", 
                line_color="red",
                annotation_text=f"24h Lägsta: {low_24h_display:,.4f} {currency}",
                annotation_position="bottom right",
                name="24h Lägsta",
                layer="below"
            )

    else:
        msg = f"Laddar historisk OHLC-data (5-min intervall) för {coin_label}. Det kan ta upp till 2 minuter efter appstart."
        current_time = time.strftime('%H:%M:%S', time.gmtime(timestamp))
        
        figure.add_trace(go.Scatter(
            x=[current_time], 
            y=[current_price], 
            mode='markers+text', 
            marker=dict(size=10, color='#28a745'),
            text=[f"Pris: {current_price:,.4f} {currency}"],
            textposition="top center",
            name="Nuvarande Pris",
        ))
        figure.add_trace(go.Scatter(x=[0], y=[0], mode='text', text=[msg], showlegend=False))
    
    figure.update_layout(
        title=f'{coin_label} Prisutveckling ({currency})',
        xaxis_title=f"Tid ({ohlc_interval} min intervall)",
        yaxis_title=f"Pris ({currency})",
        template="plotly_white",
        margin=dict(l=40, r=40, t=40, b=40),
        height=400,
        hovermode="x unified",
        plot_bgcolor='white',
        paper_bgcolor='white'
    )
    
    return price_text, updated_text, figure


# --- Callback för Telegram Alert (Oförändrad) ---
@app.callback(Output('alert-output', 'children'),
              [Input('alert-button', 'n_clicks')],
              [State('alert-threshold', 'value'),
               State('coin-dropdown', 'value'),
               State('currency-dropdown', 'value')])
def handle_telegram_alert(n_clicks, threshold, coin_symbol, currency):
    # [KOD FÖR TELEGRAM ALERT]
    if n_clicks is None or n_clicks == 0:
        return ""
    
    if threshold is None or threshold == '':
        return html.Span("❌ Ange ett giltigt gränsvärde innan du aktiverar alerten.", style={'color': '#dc3545', 'fontWeight': 'bold'})
    
    data = get_data_from_redis()
    
    if data is None:
        return html.Span("❌ Kan inte kontrollera priset just nu (Kraken data saknas).", style={'color': '#dc3545', 'fontWeight': 'bold'})

    price_key = f'{coin_symbol}/{currency}'
    current_price = data.get(price_key)

    if current_price is None:
        return html.Span(f"❌ Prisdata saknas för {coin_symbol}/{currency}.", style={'color': '#dc3545', 'fontWeight': 'bold'})

    try:
        threshold_val = float(threshold)
    except ValueError:
        return html.Span("❌ Gränsvärdet måste vara ett giltigt nummer.", style={'color': '#dc3545', 'fontWeight': 'bold'})

    coin_label = SYMBOL_TO_LABEL.get(coin_symbol, coin_symbol)

    if current_price >= threshold_val:
        success = send_telegram_alert(coin_label, current_price, currency, threshold_val)
        
        if success:
            return html.Span(f"🔔 ALERT AKTIVERAD: {coin_label} är nu {current_price:.4f} {currency}. Telegram-meddelande skickat!", style={'color': '#28a745', 'fontWeight': 'bold'})
        else:
            return html.Span("❌ ALERT: Kunde inte skicka Telegram-meddelande. Kontrollera loggarna.", style={'color': '#dc3545', 'fontWeight': 'bold'})
    else:
        return html.Span(f"✅ Alert satt för {coin_label} > {threshold_val} {currency}. Nuvarande pris: {current_price:.4f}.", style={'color': '#495057'})

# --- Callback för Krypto Sammanfattning (MED Procentrörelse) ---

@app.callback(Output('crypto-summary', 'children'),
              [Input('interval-component', 'n_intervals'),
               Input('currency-dropdown', 'value')])
def update_crypto_summary_cards(n, currency):
    
    data = get_data_from_redis()
    
    if data is None or len(data) <= 3: 
        return html.Div("Laddar kryptoöversikt...", style={'textAlign': 'center', 'width': '100%', 'color': '#6c757d', 'padding': '20px'})

    eur_to_sek = data.get('EUR_SEK_RATE', 11.0)
    all_24h_range = data.get('ALL_24H_RANGE', {})
    all_percent_changes = data.get('ALL_PERCENT_CHANGE', {}) # Hämta de beräknade procentrörelserna
    
    summary_cards = []
    
    card_style = {
        'flex': '0 1 calc(25% - 15px)', 
        'minWidth': '200px',
        'padding': '15px',
        'border': '1px solid #e0e0e0',
        'borderRadius': '8px',
        'backgroundColor': '#ffffff',
        'boxShadow': '0 2px 4px rgba(0, 0, 0, 0.05)',
    }
    
    # Lista över de perioder vi vill visa, i rätt ordning
    periods_to_show = ['30m', '1h', '3h', '6h', '24h']
    
    for label in COINS_LABELS:
        coin_symbol = label.split(' ')[0]
        price_eur = data.get(f'{coin_symbol}/EUR')
        range_data = all_24h_range.get(coin_symbol, {})
        percent_data = all_percent_changes.get(coin_symbol, {}) # Hämta procentdata för myntet
        
        high_24h_eur = range_data.get('high_eur')
        low_224h_eur = range_data.get('low_eur')
        
        price_status_style = {'color': '#6c757d', 'fontWeight': 'normal'} 
        
        if price_eur is not None:
            # Konvertera till SEK/EUR
            if currency == 'SEK':
                current_price = price_eur * eur_to_sek
                high_24h = high_24h_eur * eur_to_sek if high_24h_eur is not None else None
                low_24h = low_224h_eur * eur_to_sek if low_224h_eur is not None else None
            else:
                current_price = price_eur
                high_24h = high_24h_eur
                low_24h = low_224h_eur
                
            # Formateringshjälpfunktion
            def format_price(p):
                if p is None: return "N/A"
                price_format = f"{p:,.4f}" if p < 10 else f"{p:,.2f}"
                return price_format.replace(",", "TEMP").replace(".", ",").replace("TEMP", " ")
            
            def format_change(c):
                if c is None: return "N/A"
                color = 'green' if c >= 0 else 'red'
                sign = '+' if c >= 0 else ''
                return html.Span(f"{sign}{c:.2f}%", style={'color': color, 'fontWeight': 'bold'})
                
            formatted_price = format_price(current_price)
            formatted_high = format_price(high_24h)
            formatted_low = format_price(low_24h)
            
            price_text = f"{formatted_price} {currency}"
            price_status_style['color'] = '#28a745' 
            price_status_style['fontWeight'] = 'bold'
        else:
            price_text = "N/A"
            formatted_high = "N/A"
            formatted_low = "N/A"
            price_status_style['color'] = '#dc3545' 
            
        
        card_content = [
            html.P(label, style={'margin': '0 0 5px 0', 'fontSize': '1.1em', 'fontWeight': '500', 'color': '#0056b3'}),
            html.P(price_text, style={'margin': '0 0 10px 0', 'fontSize': '1.4em'} | price_status_style),
            
            # Tabell för Procentrörelse
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
            
            # 24h High/Low
            html.Small(f"Högsta 24h: ", style={'color': '#6c757d', 'display': 'block', 'marginTop': '5px'}),
            html.Small(f"{formatted_high} {currency}", style={'color': 'green', 'fontWeight': 'bold', 'display': 'block'}),
            html.Small(f"Lägsta 24h: ", style={'color': '#6c757d', 'marginTop': '5px', 'display': 'block'}),
            html.Small(f"{formatted_low} {currency}", style={'color': 'red', 'fontWeight': 'bold', 'display': 'block'}),
        ]
        
        card = html.Div(style=card_style, children=card_content)
        summary_cards.append(card)

    return summary_cards


if __name__ == '__main__':
    # För lokal utveckling
    # app.run_server(debug=True)  
    pass

if __name__ != '__main__':
    # Render (WSGI) kommer att använda 'server' variabeln
    pass