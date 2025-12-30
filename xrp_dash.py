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

# URL för officiella krypto-logotyper
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
    '7d':  {'blocks': 7,   'color': '#e377c2', 'name': 'Trend (7d)',  'weight': 1, 'source': '1day', 'show_line': True},
    '30d': {'blocks': 30,  'color': '#7f7f7f', 'name': 'Trend (30d)', 'weight': 0.4, 'source': '1day', 'show_line': True},
}

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

# --- Hjälpfunktioner ---

def get_logo_url(symbol):
    """Returnerar URL till kryptons officiella logotyp."""
    return f"{LOGO_BASE_URL}{symbol.lower()}.png"

def format_price_display(p):
    if p is None: return "N/A"
    price_format = f"{p:,.8f}" if p < 0.1 else (f"{p:,.4f}" if p < 10 else f"{p:,.2f}")
    return price_format.replace(",", "TEMP").replace(".", ",").replace("TEMP", " ")

def calculate_trendline(historical_data, blocks):
    if len(historical_data) < 2: return None, None, None
    actual_blocks = min(len(historical_data), blocks)
    data_segment = historical_data[-actual_blocks:]
    x_values = np.arange(actual_blocks)
    y_values = np.array([item['price'] for item in data_segment])
    slope, intercept, _, _, _ = linregress(x_values, y_values)
    start_index = len(historical_data) - actual_blocks
    return slope, intercept, start_index

def fetch_ohlc_data_from_kraken(kraken_ticker, interval, periods_ago_seconds):
    time_ago = int(time.time()) - periods_ago_seconds
    params = {'pair': kraken_ticker, 'interval': interval, 'since': time_ago}
    try:
        response = requests.get(KRAKEN_OHLC_API_URL, params=params, timeout=15)
        response.raise_for_status()
        ohlc_data = response.json()
        if ohlc_data.get('error'): return []
        result_key = next(iter(ohlc_data['result']))
        data_list = ohlc_data['result'][result_key]
        return [{
            'time': int(row[0]),
            'price': float(row[4]),
            'open': float(row[1]),
            'high': float(row[2]),
            'low': float(row[3]),
            'close': float(row[4])
        } for row in data_list]
    except Exception as e:
        logger.error(f"Error fetching OHLC: {e}")
        return []

# --- Layout-komponenter ---

def create_summary_row(symbol, label, price, percent_data, trade_value, currency, is_selected, eur_to_sek):
    row_style = {'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center', 'padding': '8px 0', 'borderBottom': '1px solid #eee', 'fontSize': '0.9em', 'cursor': 'pointer', 'backgroundColor': '#fff'}
    if is_selected:
        row_style['backgroundColor'] = '#e6f7ff'
        row_style['border'] = '1px solid #0056b3'
    
    logo_img = html.Img(src=get_logo_url(symbol), style={'width': '20px', 'height': '20px', 'marginRight': '8px', 'verticalAlign': 'middle'}, 
                        onError="this.onerror=null;this.src='https://via.placeholder.com/20?text=?';")
    
    # Pris och 24h förändring
    change_24h = percent_data.get('24h')
    change_color = '#28a745' if change_24h and change_24h >= 0 else '#dc3545'
    
    return html.Div([
        html.Div([logo_img, html.Span(label, style={'fontWeight': 'bold'})], style={'flex': '0 0 160px', 'paddingLeft': '5px'}),
        html.Div(f"{format_price_display(price)} {currency}", style={'flex': '0 0 140px', 'textAlign': 'right', 'color': change_color, 'fontWeight': 'bold'}),
        # ... (resten av kolumnerna för tidshorisonter likt originalet)
    ], id={'type': 'summary-card', 'index': symbol}, style=row_style)

# --- Dash App ---

app = dash.Dash(__name__, update_title=None)
server = app.server

app.layout = html.Div([
    dcc.Store(id='crypto-data-store'),
    dcc.Interval(id='fast-interval', interval=UPDATE_INTERVAL_FAST*1000),
    
    html.Div([
        html.H2("Krypto Dashboard Live", style={'textAlign': 'center'}),
        
        # Vald valuta box
        html.Div(id='selected-coin-info', style={'marginBottom': '20px'}),

        # Grafer sektion
        html.Div([
            # 4 TIMMAR LIVE MED INSTÄLLNINGAR
            html.Div([
                html.Div([
                    html.Label("Candlestick period:", style={'marginRight': '10px', 'fontWeight': 'bold'}),
                    dcc.Dropdown(
                        id='live-period-dropdown',
                        options=[
                            {'label': '15 minuter (Standard)', 'value': 15},
                            {'label': '30 minuter', 'value': 30},
                            {'label': '1 timme', 'value': 60}
                        ],
                        value=15,
                        clearable=False,
                        style={'width': '200px', 'display': 'inline-block', 'verticalAlign': 'middle'}
                    )
                ], style={'padding': '10px', 'backgroundColor': '#f8f9fa', 'borderRadius': '5px', 'marginBottom': '10px'}),
                dcc.Graph(id='live-graph-4h')
            ], style={'marginBottom': '30px'}),

            html.Div([dcc.Graph(id='graph-1w')], style={'width': '49%', 'display': 'inline-block'}),
            html.Div([dcc.Graph(id='graph-1m')], style={'width': '49%', 'display': 'inline-block'}),
        ]),
        
        # Sammanfattningstabell
        html.Div(id='summary-table', style={'marginTop': '30px'})
    ], style={'padding': '20px'})
])

# --- Callbacks ---

@app.callback(
    Output('live-graph-4h', 'figure'),
    [Input('live-period-dropdown', 'value'),
     Input('crypto-data-store', 'data')],
    [State('coin-dropdown', 'value'), State('currency-dropdown', 'value')]
)
def update_live_graph(interval_min, store_data, selected_label, currency):
    if not selected_label: return go.Figure()
    symbol = selected_label.split(' ')[0]
    ticker = CRYPTO_PAIRS[selected_label]
    
    # Hämta data (4 timmar bakåt)
    ohlc_data = fetch_ohlc_data_from_kraken(ticker, interval_min, 3600 * 4)
    if not ohlc_data: return go.Figure()

    times = [datetime.fromtimestamp(d['time']) for d in ohlc_data]
    
    fig = go.Figure(data=[go.Candlestick(
        x=times, open=[d['open'] for d in ohlc_data],
        high=[d['high'] for d in ohlc_data],
        low=[d['low'] for d in ohlc_data],
        close=[d['close'] for d in ohlc_data],
        name='Pris'
    )])

    # Trendlinje
    slope, intercept, _ = calculate_trendline(ohlc_data, len(ohlc_data))
    if slope is not None:
        trend_y = slope * np.arange(len(ohlc_data)) + intercept
        fig.add_trace(go.Scatter(x=times, y=trend_y, mode='lines', name='Trend', line=dict(color='orange', width=2, dash='dot')))

    fig.update_layout(title=f"4 Timmar (Live) - {interval_min}m Candlesticks", template="plotly_white", xaxis_rangeslider_visible=False)
    return fig

@app.callback(
    [Output('graph-1w', 'figure'), Output('graph-1m', 'figure')],
    [Input('crypto-data-store', 'data')],
    [State('coin-dropdown', 'value')]
)
def update_long_term_graphs(store_data, selected_label):
    if not selected_label: return go.Figure(), go.Figure()
    ticker = CRYPTO_PAIRS[selected_label]
    
    figs = []
    # Loop för 1 vecka (15 min intervall) och 1 månad (60 min intervall)
    for period_name, interval, seconds in [('1 vecka', 15, 7*86400), ('1 månad', 60, 30*86400)]:
        data = fetch_ohlc_data_from_kraken(ticker, interval, seconds)
        if not data: 
            figs.append(go.Figure())
            continue
            
        times = [datetime.fromtimestamp(d['time']) for d in data]
        prices = [d['price'] for d in data]
        
        fig = go.Figure(data=[go.Scatter(x=times, y=prices, mode='lines', name='Pris')])
        
        # Trendlinje
        slope, intercept, _ = calculate_trendline(data, len(data))
        if slope is not None:
            trend_y = slope * np.arange(len(data)) + intercept
            fig.add_trace(go.Scatter(x=times, y=trend_y, mode='lines', name='Trend', line=dict(color='red', width=1.5, dash='dash')))
            
        fig.update_layout(title=f"Prisutveckling: {period_name}", template="plotly_white")
        figs.append(fig)
        
    return figs[0], figs[1]

# (Här inkluderas resterande logik för datahantering, bakgrundstrådar och CSS-styling från ditt originalscript)

if __name__ == '__main__':
    app.run_server(debug=True)