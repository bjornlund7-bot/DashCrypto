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

REDIS_URL = os.environ.get('REDIS_URL')
r = from_url(REDIS_URL) if REDIS_URL else None

KRAKEN_TICKER_API_URL = "https://api.kraken.com/0/public/Ticker"
KRAKEN_OHLC_API_URL = "https://api.kraken.com/0/public/OHLC"

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

# --- Hjälpfunktioner ---
def format_price(p):
    return f"{p:,.4f}".replace(",", " ").replace(".", ",").replace(" ", ".") if p else "0,0000"

def format_change(c):
    if c is None: return html.Span("0,00%", style={'color': '#6c757d'})
    color = '#28a745' if c > 0 else '#dc3545'
    symbol = '▲' if c > 0 else '▼'
    return html.Span(f"{symbol} {abs(c):.2f}%", style={'color': color, 'fontWeight': 'bold'})

# --- BAKGRUNDSPROCESS (Hämtar data) ---
def data_fetcher_loop():
    logger.info("Workern startar...")
    while True:
        try:
            # Hämta priser
            ticker_res = requests.get(KRAKEN_TICKER_API_URL)
            if ticker_res.status_code == 200 and 'result' in ticker_res.json():
                res_data = ticker_res.json()['result']
                processed = {'EUR_SEK_RATE': 11.2, 'ALL_PERCENT_CHANGE': {}}
                
                for label, pair in CRYPTO_PAIRS.items():
                    s = label.split(' ')[0]
                    k_pair = pair.replace('/', '')
                    if k_pair in res_data:
                        processed[f'{s}/EUR'] = float(res_data[k_pair]['c'][0])
                
                r.set('crypto_data', json.dumps(processed))

            # Hämta grafer för vald period (Här fixar vi 7d och 30d)
            for label, pair in CRYPTO_PAIRS.items():
                # Vi hämtar 5m (24h), 180m (7d) och 1440m (30d)
                for interval, suffix in [(5, '5MIN'), (180, '180MIN'), (1440, '1440MIN')]:
                    ohlc = requests.get(f"{KRAKEN_OHLC_API_URL}?pair={pair}&interval={interval}")
                    if ohlc.status_code == 200 and 'result' in ohlc.json():
                        raw_data = list(ohlc.json()['result'].values())[0]
                        clean = [{'time': i[0], 'price': float(i[4])} for i in raw_data[-200:]]
                        r.set(f'OHLC_CACHED_{suffix}_{pair}', json.dumps(clean))
                    time.sleep(0.5) # Undvik rate-limit
            
            logger.info("Data uppdaterad i Redis.")
        except Exception as e:
            logger.error(f"Loop-fel: {e}")
        
        time.sleep(120)

threading.Thread(target=data_fetcher_loop, daemon=True).start()

# --- DASHBOARD LAYOUT ---
app = dash.Dash(__name__)
server = app.server

app.layout = html.Div(style={'backgroundColor': '#f8f9fa', 'padding': '20px', 'fontFamily': 'Arial'}, children=[
    html.H1('📈 DJ-Investment Dashboard', style={'textAlign': 'center', 'color': '#0056b3'}),
    
    html.Div(style={'display': 'flex', 'gap': '20px'}, children=[
        html.Div(style={'flex': '0 0 250px', 'backgroundColor': 'white', 'padding': '15px', 'borderRadius': '10px', 'border': '1px solid #ddd'}, children=[
            html.H3("⚙️ Inställningar"),
            html.Label("Valuta:"),
            dcc.Dropdown(id='coin-dropdown', options=[{'label': k, 'value': k.split(' ')[0]} for k in CRYPTO_PAIRS.keys()], value='XRP'),
            html.Br(),
            html.Label("Period:"),
            dcc.RadioItems(id='timespan-selector', options=[
                {'label': ' 24h', 'value': '24h'},
                {'label': ' 7d', 'value': '7d'},
                {'label': ' 30d', 'value': '30d'}
            ], value='24h'),
        ]),
        html.Div(id='main-info-box', style={'flex': '1', 'border': '2px solid #0056b3', 'borderRadius': '10px', 'padding': '20px', 'backgroundColor': 'white'})
    ]),

    dcc.Graph(id='live-graph', style={'marginTop': '20px'}),
    html.Div(id='summary-table', style={'marginTop': '20px'}),
    dcc.Interval(id='interval', interval=30*1000)
])

@app.callback(
    [Output('main-info-box', 'children'), Output('live-graph', 'figure'), Output('summary-table', 'children')],
    [Input('interval', 'n_intervals'), Input('coin-dropdown', 'value'), Input('timespan-selector', 'value')]
)
def update_ui(n, coin, timespan):
    cached = r.get('crypto_data') if r else None
    if not cached:
        return html.Div("Väntar på data från Kraken (ca 30 sek)..."), go.Figure(), ""

    data = json.loads(cached)
    price = data.get(f'{coin}/EUR', 0)
    
    # Graf-logik
    pair = [v for k, v in CRYPTO_PAIRS.items() if k.startswith(coin)][0]
    interval_map = {'24h': '5MIN', '7d': '180MIN', '30d': '1440MIN'}
    ckey = f'OHLC_CACHED_{interval_map[timespan]}_{pair}'
    
    h_raw = r.get(ckey)
    if not h_raw: h_raw = r.get(f'OHLC_CACHED_5MIN_{pair}') # Fallback
    
    fig = go.Figure()
    if h_raw:
        h = json.loads(h_raw)
        fig.add_trace(go.Scatter(x=[datetime.fromtimestamp(i['time'], tz=timezone.utc) for i in h], 
                                 y=[i['price'] for i in h], line=dict(color='#0056b3')))
    
    fig.update_layout(title=f"{coin} - {timespan}", template="plotly_white", height=450)

    # Info box
    box = html.Div([
        html.H2(f"{CRYPTO_EMOJIS.get(coin, '')} {coin}"),
        html.H1(f"{format_price(price)} EUR", style={'color': '#28a745'})
    ])

    return box, fig, "Tabell laddas vid nästa synk..."

if __name__ == '__main__':
    app.run_server(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))