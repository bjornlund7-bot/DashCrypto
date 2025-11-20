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

# Konfigurera loggning
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

# --- API Konstanter ---
KRAKEN_TICKER_API_URL = "https://api.kraken.com/0/public/Ticker"
KRAKEN_OHLC_API_URL = "https://api.kraken.com/0/public/OHLC"
EXCHANGE_RATE_URL = "https://api.exchangerate-api.com/v4/latest/EUR"

### ÄNDRING: Uppdaterade etiketter till EUR som standard ###
# Lista över tillgängliga kryptopar och deras Kraken-tickers (baserade i EUR)
CRYPTO_PAIRS = {
    'XRP (Ripple)': 'XRPEUR',
    'BTC (Bitcoin)': 'BTCEUR',
    'ETH (Ethereum)': 'ETHEUR',
    'SOL (Solana)': 'SOLEUR',
    'GRASS (Grass)': 'GRASSEUR',
    'ADA (Cardano)': 'ADAEUR',
    'DOT (Polkadot)': 'DOTEUR',
    'DOGE (Dogecoin)': 'DOGEEUR',
    'PUMP (PUMP)': 'PUMPEUR',
    'Cookie DAO': 'COOKIEEUR',
    'Moonwalk (MF)': 'MFEUR', 
    'YALA': 'YALAEUR', 
    'WIF (dogwifhat)': 'WIFEUR',
    'YFI (Yearn Finance)': 'YFIEUR',
    'BNB (BNB Chain)': 'BNBEUR',
    'TRX (Tron)': 'TRXEUR',
    'PEPE (Pepe)': 'PEPEEUR',
    'LTC (Litecoin)': 'LTCEUR',
    'TRUMP (Official Trump)': 'TRUMPEUR',
    'XTZ (Tezos)': 'XTZEUR',
    'DASH (Dash)': 'DASHEUR',
    'ZRO (LayerZero)': 'ZROEUR',
    'WOO (Woo Network)': 'WOOEUR',
    'GALA (Gala Games)': 'GALAEUR',
    'SUI (SUI)': 'SUIEUR',
    'BCH (Bitcoin Cash)': 'BCHEUR',
    'ATOM (Cosmos)': 'ATOMEUR',
    'AVAX (Avalanche)': 'AVAXEUR',
    'ICP (Internet Computer Protocol)': 'ICPEUR',
    'ZEC (Zcash)': 'ZECEUR',
    '0G (ZeroGravity)': '0G/EUR', 
    'XDC (XDC Network)': 'XDCEUR',
    'UNI (Uniswap)': 'UNIEUR',
    'IP (Story)': 'IPEUR',
    'INJ (Injective)': 'INJEUR',
    'AR (Arweave)': 'AREUR',
    'EGLD (MultiversX)': 'EGLDEUR',
    'LPT (LivePeer)': 'LPTEUR',
    'KSM (Kusama)': 'KSMEUR',
    'EUL (Euler)': 'EULEUR',
    'GMX (GMX)': 'GMXEUR',
    'AUCTION (Bounce)': 'AUCTIONEUR',
    'MOVR (Moonriver)': 'MOVREUR',
    'SSV (SSV Network)': 'SSVEUR',
    'MLN (Enzyme Finance)': 'MLNEUR',
    'ALCX (Alchemix)': 'ALCXEUR',
    'AERO (Aerodrome Finance)': 'AEROEUR',
    'MYX (MYX Finance)': 'MYXEUR',
    'GNO (Gnosis)': 'GNOEUR',
}
DEFAULT_PAIR_KEY = 'XRP (Ripple)'
### SLUT PÅ ÄNDRING ###

# Filnamn för permanent datalagring (XLSX)
EXCEL_FILE_PATH = os.environ.get("EXCEL_FILE_PATH", "crypto_data_log.xlsx")

# Inställningar för Dash
UPDATE_INTERVAL_SECONDS_DATA = 60 # 60 sekunder - DATA HÄMTAS ENDAST I BAKGRUNDSTRÅDEN
MAX_DASH_POINTS = 1440         # 24 h historik
SUMMARY_TREND_POINTS_30M = 30    # 30 minuter
SUMMARY_TREND_POINTS_360M = 360  # 360 minuter (6 timmar)
OHLC_INTERVAL_MIN = 1 # Använd 5 minuters intervall för grafen


# SMA-fönster för grafen
SMA_WINDOWS = [SUMMARY_TREND_POINTS_30M, MAX_DASH_POINTS, SUMMARY_TREND_POINTS_360M]

CURRENCIES = ['EUR', 'SEK']


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

# Fallback/Standarddata (Endast för att undvika fel om API-anrop misslyckas)
DEFAULT_DATA = {
    'XRP/EUR': 0.50, 'XRP/SEK': 5.50,
    'timestamp': time.time(),
    'EUR_SEK_RATE': 11.0 # Standardväxelkurs
}


# --- Telegram Mock-funktion ---

def mock_telegram_send(coin_label, price, currency, threshold):
    """Simulerar utskick av Telegram-notis."""
    logger.info(f"--- TELEGRAM MOCK: Alert! {coin_label} ({currency}) nådde gränsvärde {threshold:.4f}. Nuvarande pris: {price:.4f} ---")
    # I en verklig app skulle detta anropa en bot API.
    pass

# --- API Data Hämtning ---

def fetch_exchange_rate():
    """Hämtar EUR/SEK växelkurs från ExchangeRate-API."""
    try:
        response = requests.get(EXCHANGE_RATE_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        sek_rate = data['rates'].get('SEK')
        if sek_rate:
            logger.debug(f"Hämtad SEK-kurs: {sek_rate}")
            return sek_rate
        else:
            logger.error("SEK rate not found in exchange API response. Using fallback 11.0.")
            return 11.0
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching exchange rate: {e}. Using fallback 11.0.")
        return 11.0


def fetch_crypto_data():
    """Hämtar realtidsdata för alla par från Kraken och beräknar SEK-priser."""
    try:
        t = time.time()
        
        # 1. Hämta växelkurs EUR/SEK
        sek_rate = fetch_exchange_rate()
        
        # 2. Förbered Kraken-anropet
        kraken_tickers = ','.join(CRYPTO_PAIRS.values())
        
        # Hämta Ticker-data från Kraken
        response = requests.get(KRAKEN_TICKER_API_URL, params={'pair': kraken_tickers}, timeout=15)
        response.raise_for_status()
        kraken_data = response.json()

        if kraken_data.get('error'):
            logger.error(f"Kraken API error: {kraken_data['error']}")
            return DEFAULT_DATA

        # 3. Bearbeta och lagra data
        current_data = {'timestamp': t, 'EUR_SEK_RATE': sek_rate}
        
        for label, ticker in CRYPTO_PAIRS.items():
            coin_symbol = label.split(' ')[0]
            
            # Hitta data i Kraksens svar (tickern är nyckeln)
            coin_info = kraken_data['result'].get(ticker)
            
            if coin_info:
                # 'c' står för last trade closed (price and volume)
                try:
                    price_eur = float(coin_info['c'][0])
                    price_sek = price_eur * sek_rate
                    
                    current_data[f'{coin_symbol}/EUR'] = price_eur
                    current_data[f'{coin_symbol}/SEK'] = price_sek
                except (ValueError, IndexError) as e:
                    logger.warning(f"Failed to parse price for {ticker}: {e}")
            else:
                logger.warning(f"Kraken data missing for ticker: {ticker}")
                
        if len(current_data) > 2: # Kontrollera att minst en krypto-post har lagts till
            return current_data
        else:
            logger.warning("Kraken returned data but failed to parse prices for any coin. Using default data.")
            return DEFAULT_DATA

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ API-fel vid hämtning av data (Kraken/ExchangeRate): {e}. Använder standardvärden.")
        return DEFAULT_DATA
    except Exception as e:
        logger.error(f"❌ Oväntat fel i datahantering: {e}")
        return DEFAULT_DATA

# --- Bakgrundstrådens Logik (Cache) ---

def update_redis_cache(redis_instance):
    """Loop som körs i bakgrunden för att uppdatera Redis-cachen."""
    while True:
        try:
            logger.debug("--- Bakgrundstråd: Hämtar ny data ---")
            
            new_data = fetch_crypto_data()
            
            if redis_instance:
                data_json = json.dumps(new_data)
                # Spara data, cachad i 60 sekunder
                redis_instance.set('crypto_data', data_json, ex=UPDATE_INTERVAL_SECONDS_DATA) 
                
                timestamp_str = time.strftime("%H:%M:%S", time.gmtime(new_data['timestamp']))
                # Logga ett representativt värde, t.ex. BTC/EUR
                btc_eur_price = new_data.get('BTC/EUR', 'N/A')
                logger.debug(f"✅ Data sparad i Redis. BTC/EUR: {btc_eur_price}. Uppdaterad: {timestamp_str} UTC")
            else:
                logger.warning("Redis är inte initialiserad. Hoppar över cachelagring.")

        except Exception as e:
            logger.error(f"❌ Kritisk fel i bakgrundstråd: {e}. Fortsätter efter {UPDATE_INTERVAL_SECONDS_DATA}s.")
            
        time.sleep(UPDATE_INTERVAL_SECONDS_DATA)

# Starta bakgrundstråden om Redis är ansluten
if r:
    worker_thread = threading.Thread(target=update_redis_cache, args=(r,), daemon=True)
    worker_thread.start()
    logger.debug(">>> Bakgrundstråd startad och snurrar!")

# --- Dash Applikation ---

app = dash.Dash(__name__, external_stylesheets=[
    'https://codepen.io/chriddyp/pen/bWLwgP.css' # Grundläggande CSS
])
server = app.server

# Förbättrad Layout med bättre styling (kortbaserad design)
app.layout = html.Div(style={
    'backgroundColor': '#f8f9fa', 
    'minHeight': '100vh', 
    'padding': '40px 10px',
    'fontFamily': 'Roboto, Arial, sans-serif'
}, children=[
    
    html.Div(style={
        'maxWidth': '700px',
        'margin': '40px auto',
        'padding': '30px',
        'borderRadius': '12px',
        'boxShadow': '0 4px 12px rgba(0, 0, 0, 0.1)',
        'backgroundColor': 'white',
        'border': '1px solid #dee2e6'
    }, children=[
        
        html.H1('📈 MTS Krypto Dashboard (Kraken Live)', style={'textAlign': 'center', 'color': '#0056b3', 'marginBottom': '30px', 'fontSize': '1.8em'}),

        # Valutaväljare (Coin and Currency Selectors)
        html.Div(style={'display': 'flex', 'justifyContent': 'center', 'gap': '20px', 'alignItems': 'center', 'marginBottom': '30px'}, children=[
            
            html.Div(style={'flexGrow': 1, 'maxWidth': '300px'}, children=[
                html.Label("Välj kryptovaluta:", style={'marginBottom': '5px', 'fontWeight': 'bold', 'color': '#495057', 'display': 'block'}),
                dcc.Dropdown(
                    id='coin-dropdown',
                    # Uppdaterade options för att visa fullständiga namn, men skicka symbolen som värde
                    options=[{'label': label, 'value': label.split(' ')[0]} for label in COINS_LABELS],
                    value=DEFAULT_PAIR_KEY.split(' ')[0], # Standardvärde (t.ex. 'XRP')
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

        # Nuvarande pris och Uppdaterad tid
        html.Div(id='current-price', style={'textAlign': 'center', 'fontSize': '3em', 'fontWeight': '800', 'color': '#28a745', 'marginBottom': '5px'}),
        html.Div(id='last-updated', style={'textAlign': 'center', 'fontSize': '0.9em', 'color': '#6c757d', 'marginBottom': '40px'}),
        
        # Laddningsindikator och graf (Graph)
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
        
        # --- Telegram Alert Section ---
        html.Div(style={'marginTop': '40px', 'paddingTop': '20px', 'borderTop': '1px solid #dee2e6'}, children=[
            html.H3('🔔 Telegram Alert-inställningar', style={'fontSize': '1.3em', 'color': '#0056b3', 'marginBottom': '15px'}),
            
            html.P("Simulera en notis när priset når eller överstiger ditt angivna gränsvärde."),
            
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
    ]),

    # Intervallkomponent för att uppdatera frontend (var 5:e sekund)
    dcc.Interval(
        id='interval-component',
        interval=5*1000, # 5 sekunder
        n_intervals=0
    )
])

# --- Hämta data från Redis ---

def get_data_from_redis():
    """Hämtar data från Redis eller standarddata om cachen är tom."""
    if r:
        try:
            cached_data = r.get('crypto_data')
            if cached_data:
                return json.loads(cached_data)
            else:
                logger.warning("Cache är tom. Väntar på bakgrundstråd.")
                return None
        except exceptions.ConnectionError as e:
            logger.error(f"Redis-anslutningsfel i callback: {e}")
            return None
    return None

def fetch_ohlc_data(kraken_ticker, interval=OHLC_INTERVAL_MIN):
    """Hämtar historisk OHLC-data från Kraken (max 720 punkter för 5 min intervall)."""
    # Vi hämtar OHLC-data direkt här, istället för i bakgrundstråden, eftersom det beror på användarens valda mynt.
    # interval=5 är 5 minuter
    params = {'pair': kraken_ticker, 'interval': interval}
        
    try:
        response = requests.get(KRAKEN_OHLC_API_URL, params=params, timeout=15)
        response.raise_for_status()
        ohlc_data = response.json()
        
        if ohlc_data.get('error'):
            logger.error(f"Kraken OHLC API error: {ohlc_data['error']}")
            return []

        # Hitta den dynamiska nyckeln i resultatet
        result_key = next(iter(ohlc_data['result'])) 
        
        # data format: [[time, open, high, low, close, vwap, volume, count], ...]
        data_list = ohlc_data['result'][result_key]
        
        # Extrahera timestamp och closing price
        # [time (s), open (1), high (2), low (3), close (4)]
        return [{'time': int(row[0]), 'price': float(row[4])} for row in data_list]

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching OHLC data for {kraken_ticker}: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error processing OHLC data: {e}")
        return []

# --- Callback för Pris och Graf ---

@app.callback(Output('current-price', 'children'),
              Output('last-updated', 'children'),
              Output('live-update-graph', 'figure'),
              [Input('interval-component', 'n_intervals'),
               Input('coin-dropdown', 'value'),
               Input('currency-dropdown', 'value')])
def update_metrics_and_graph(n, coin_symbol, currency):
    data = get_data_from_redis()
    
    # 1. Kontrollera om data finns
    if data is None or 'EUR_SEK_RATE' not in data:
        price_text = "Laddar data..."
        updated_text = "Väntar på data från Kraken/Redis..."
        figure = go.Figure(go.Scatter(x=[0], y=[0], mode='text', text=['Laddar...']))
        figure.update_layout(title="Hämtar data...", template="plotly_white", height=400)
        return price_text, updated_text, figure

    # 2. Hämta pris och konstanter
    price_key = f'{coin_symbol}/{currency}'
    current_price = data.get(price_key)
    timestamp = data.get('timestamp')
    eur_to_sek = data.get('EUR_SEK_RATE', 11.0)
    
    if current_price is None:
        price_text = f"❌ Pris för {coin_symbol}/{currency} saknas."
        updated_text = f"Data saknas eller är inte tillgänglig på Kraken."
        figure = go.Figure(go.Scatter(x=[0], y=[0], mode='text', text=['❌ Data saknas för valt par.']))
        figure.update_layout(title="Kunde inte hämta pris.", template="plotly_white", height=400)
        return price_text, updated_text, figure
    
    # 3. Formatera priset
    # Högre precision för lågvärdesmynt
    if current_price < 10:
        price_format = f"{current_price:.4f}"
    # Standard formatering för högvärdesmynt
    else:
        # Ersätter punkt med komma för decimaler, och lägger till tusentalsavgränsare (space)
        price_format = f"{current_price:,.2f}".replace(",", "TEMP").replace(".", ",").replace("TEMP", " ") 

    # Hitta fullständigt namn för visning
    coin_label = SYMBOL_TO_LABEL.get(coin_symbol, coin_symbol)
    
    price_text = f"{coin_label}: {price_format} {currency}"
    updated_text = f"Senast uppdaterad (Realtime Ticker): {time.strftime('%H:%M:%S', time.gmtime(timestamp))} UTC"

    
    # 4. Hämta och rita OHLC-graf
    
    # Hitta Kraksens ticker (t.ex. 'XRPEUR' eller 'BTCEUR') för OHLC-anropet
    kraken_ticker = CRYPTO_PAIRS.get(coin_label)
    
    historical_data = []
    if kraken_ticker:
        historical_data = fetch_ohlc_data(kraken_ticker)
    
    
    figure = go.Figure()
    
    if historical_data:
        # Extrahera tider och priser
        times = [time.strftime('%H:%M', time.gmtime(item['time'])) for item in historical_data]
        prices_eur = [item['price'] for item in historical_data]
        
        # Konvertera EUR till SEK om SEK valts
        if currency == 'SEK':
            prices_display = [p * eur_to_sek for p in prices_eur]
        else:
            prices_display = prices_eur
        
        figure.add_trace(go.Scatter(
            x=times,
            y=prices_display,
            mode='lines',
            name=f'{coin_symbol} Pris',
            line=dict(color='#0056b3', width=3),
        ))
    else:
        # Visa laddningsmeddelande om OHLC-data misslyckas
        figure.add_trace(go.Scatter(x=[0], y=[0], mode='text', text=['❌ Kunde inte hämta historisk data.']))
    
    figure.update_layout(
        title=f'{coin_label} Prisutveckling ({currency})',
        xaxis_title=f"Tid ({OHLC_INTERVAL_MIN} min intervall)",
        yaxis_title=f"Pris ({currency})",
        template="plotly_white",
        margin=dict(l=40, r=40, t=40, b=40),
        height=400,
        hovermode="x unified",
        plot_bgcolor='white',
        paper_bgcolor='white'
    )
    
    return price_text, updated_text, figure


# --- Callback för Telegram Alert ---

@app.callback(Output('alert-output', 'children'),
              [Input('alert-button', 'n_clicks')],
              [State('alert-threshold', 'value'),
               State('coin-dropdown', 'value'),
               State('currency-dropdown', 'value')])
def handle_telegram_alert(n_clicks, threshold, coin_symbol, currency):
    # n_clicks = 0 vid initiering, ignorera
    if n_clicks is None or n_clicks == 0:
        return ""
    
    if threshold is None or threshold == '':
        return html.Span("❌ Ange ett giltigt gränsvärde innan du aktiverar alerten.", style={'color': '#dc3545', 'fontWeight': 'bold'})
    
    # Hämta aktuell data
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
        # Priset har nått/överskridit gränsvärdet
        mock_telegram_send(coin_label, current_price, currency, threshold_val)
        return html.Span(f"🔔 ALERT AKTIVERAD: {coin_label} är nu {current_price:.4f} {currency}. Telegram-meddelande simulerat!", style={'color': '#28a745', 'fontWeight': 'bold'})
    else:
        # Priset är fortfarande under gränsvärdet
        return html.Span(f"✅ Alert satt för {coin_label} > {threshold_val} {currency}. Nuvarande pris: {current_price:.4f}.", style={'color': '#495057'})

if __name__ == '__main__':
    # Detta block används endast för lokal utveckling
    pass