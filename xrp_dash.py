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

# --- Konfiguration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# [API & KEYS]
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
KRAKEN_TICKER_API_URL = "https://api.kraken.com/0/public/Ticker"
KRAKEN_OHLC_API_URL = "https://api.kraken.com/0/public/OHLC"

# [INTERVALL]
UPDATE_INTERVAL_SECONDS = 10 # Snabb uppdatering för vald valuta
OHLC_FETCH_INTERVAL_SECONDS = 120 # Bakgrundshämtning för alla andra (API skydd)

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

CRYPTO_EMOJIS = {'XRP': '🌊', 'BTC': '💰', 'ETH': '💎', 'SOL': '☀️', 'GRASS': '🌱', 'ADA': '₳'} # Exempel

# --- Hjälpfunktioner för Tid ---
def get_current_time_cet():
    now_utc = datetime.now(timezone.utc)
    # Enkel CET/CEST logik (Standard +1, Sommartid +2)
    offset = 2 if (3 <= now_utc.month <= 10) else 1 
    return now_utc + timedelta(hours=offset)

# --- API Anrop ---
def fetch_single_ticker(ticker):
    """Hämtar priset för en specifik valuta snabbt."""
    try:
        res = requests.get(KRAKEN_TICKER_API_URL, params={'pair': ticker}, timeout=5)
        data = res.json()
        if not data.get('error'):
            res_key = next(iter(data['result']))
            return float(data['result'][res_key]['c'][0])
    except:
        return None

# --- Dash App Layout ---
app = dash.Dash(__name__)
server = app.server

app.layout = html.Div([
    dcc.Store(id='live-price-store', data={'price': None, 'time': None}),
    html.H1("Live Crypto Focus"),
    
    html.Div([
        dcc.Dropdown(
            id='coin-dropdown', 
            options=[{'label': k, 'value': v} for k, v in CRYPTO_PAIRS.items()],
            value='XRP/EUR'
        ),
        html.Div(id='live-price-display', style={'fontSize': '2em', 'fontWeight': 'bold'})
    ], style={'padding': '20px'}),

    dcc.Graph(id='main-graph'),
    
    # Intervall var 10:e sekund
    dcc.Interval(id='fast-interval', interval=UPDATE_INTERVAL_SECONDS * 1000, n_intervals=0)
])

# --- Callback för att hämta live-pris var 10:e sekund ---
@app.callback(
    Output('live-price-store', 'data'),
    Input('fast-interval', 'n_intervals'),
    State('coin-dropdown', 'value')
)
def update_live_price(n, selected_ticker):
    price = fetch_single_ticker(selected_ticker)
    # Vi skickar med en ren timestamp för att undvika "bakåt-hopp" i grafen
    return {'price': price, 'time': time.time()}

# --- Callback för att rita grafen ---
@app.callback(
    [Output('main-graph', 'figure'),
     Output('live-price-display', 'children')],
    [Input('live-price-store', 'data')],
    [State('coin-dropdown', 'value')]
)
def update_graph(live_data, ticker):
    if not live_data['price']:
        return go.Figure(), "Laddar..."

    # 1. Hämta historik (Här kan du lägga till Redis-hämtning för 1-dagars data)
    # För exemplet skapar vi en dummy-historik för att visa tidsaxeln
    now = get_current_time_cet()
    
    # Skapa tidsaxel för grafen
    # Vi använder den faktiska tiden från live-data för att sista punkten ska vara rätt
    current_time_dt = datetime.fromtimestamp(live_data['time'], tz=timezone.utc) + timedelta(hours=2)
    
    # Skapa en enkel graf
    fig = go.Figure()
    
    # Lägg till en markör för nuvarande pris
    fig.add_trace(go.Scatter(
        x=[current_time_dt], 
        y=[live_data['price']],
        mode='markers+text',
        text=[f"{live_data['price']:.4f}"],
        textposition="top center",
        marker=dict(size=12, color='red'),
        name='Live Pris'
    ))

    fig.update_layout(
        title=f"Live Fokus: {ticker}",
        xaxis_title="Tid (Lokal)",
        yaxis_title="Pris EUR",
        # Fixa axeln så den inte hoppar
        xaxis=dict(range=[current_time_dt - timedelta(minutes=30), current_time_dt + timedelta(minutes=2)])
    )

    display_text = f"{live_data['price']:.4f} EUR"
    return fig, display_text

if __name__ == '__main__':
    app.run_server(debug=True)