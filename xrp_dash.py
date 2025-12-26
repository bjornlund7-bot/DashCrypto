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

# Använd din fullständiga lista här
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

# --- BAKGRUNDSPROCESS ---
def data_fetcher_loop():
    logger.info("Bakgrundshämtning startad.")
    while True:
        try:
            # 1. Hämta Ticker (Aktuella priser)
            ticker_res = requests.get("https://api.kraken.com/0/public/Ticker")
            if ticker_res.status_code == 200 and 'result' in ticker_res.json():
                res_data = ticker_res.json()['result']
                processed = {'EUR_SEK_RATE': 11.2, 'ALL_PERCENT_CHANGE': {}}
                
                for label, pair in CRYPTO_PAIRS.items():
                    s = label.split(' ')[0]
                    k_pair = pair.replace('/', '')
                    if k_pair in res_data:
                        price = float(res_data[k_pair]['c'][0])
                        open_p = float(res_data[k_pair]['o'])
                        processed[f'{s}/EUR'] = price
                        # Skydd mot division med noll
                        change = ((price - open_p) / open_p * 100) if open_p > 0 else 0
                        processed['ALL_PERCENT_CHANGE'][s] = {'24h': change}
                
                r.set('crypto_data', json.dumps(processed))

            # 2. Hämta OHLC för alla fönster
            for label, pair in CRYPTO_PAIRS.items():
                for interval, suffix in [(5, '5MIN'), (180, '180MIN'), (1440, '1440MIN')]:
                    ohlc_res = requests.get(f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval={interval}")
                    if ohlc_res.status_code == 200 and 'result' in ohlc_res.json():
                        res_json = ohlc_res.json()
                        if 'result' in res_json:
                            raw_data = list(res_json['result'].values())[0]
                            clean_ohlc = [{'time': i[0], 'price': float(i[4])} for i in raw_data[-200:]]
                            r.set(f'OHLC_CACHED_{suffix}_{pair}', json.dumps(clean_ohlc))
                    time.sleep(0.3) # Rate limit skydd
            
            logger.info("Redis-synk slutförd.")
        except Exception as e:
            logger.error(f"Hämtningsfel: {e}")
        
        time.sleep(120)

threading.Thread(target=data_fetcher_loop, daemon=True).start()

# --- DASH APP ---
app = dash.Dash(__name__)
server = app.server

# Återställ layouten till din snygga design
app.layout = html.Div(style={'backgroundColor': '#f8f9fa', 'padding': '20px', 'fontFamily': 'Arial'}, children=[
    html.H1('📈 DJ-Investment Dashboard', style={'textAlign': 'center', 'color': '#0056b3'}),
    
    html.Div(style={'display': 'flex', 'gap': '20px'}, children=[
        html.Div(style={'flex': '0 0 250px', 'backgroundColor': 'white', 'padding': '15px', 'borderRadius': '10px', 'border': '1px solid #ddd'}, children=[
            html.H3("⚙️ Inställningar"),
            html.Label("Välj krypto:"),
            dcc.Dropdown(id='coin-dropdown', options=[{'label': k, 'value': k.split(' ')[0]} for k in CRYPTO_PAIRS.keys()], value='XRP'),
            html.Br(),
            html.Label("Tidsfönster:"),
            dcc.RadioItems(id='timespan-selector', options=[
                {'label': ' 24h (5m)', 'value': '24h'},
                {'label': ' 7d (3h)', 'value': '7d'},
                {'label': ' 30d (1d)', 'value': '30d'}
            ], value='24h'),
        ]),
        html.Div(id='main-info-box', style={'flex': '1', 'border': '2px solid #0056b3', 'borderRadius': '10px', 'padding': '20px', 'backgroundColor': 'white'})
    ]),

    dcc.Graph(id='live-update-graph', style={'marginTop': '20px'}),
    html.Div(id='crypto-summary-table', style={'marginTop': '20px'}),
    dcc.Interval(id='interval-component', interval=30*1000)
])

# Hjälpfunktioner för UI
def format_price(p): return f"{p:,.4f}".replace(",", " ").replace(".", ",").replace(" ", ".") if p else "0,0000"

@app.callback(
    [Output('main-info-box', 'children'), Output('crypto-summary-table', 'children'), Output('live-update-graph', 'figure')],
    [Input('interval-component', 'n_intervals'), Input('coin-dropdown', 'value'), Input('timespan-selector', 'value')]
)
def update_ui(n, coin, timespan):
    cached = r.get('crypto_data') if r else None
    if not cached: return html.Div("Väntar på data från Kraken..."), html.Div(), go.Figure()
    
    data = json.loads(cached)
    price = data.get(f'{coin}/EUR', 0)
    
    # Graf-logik med korrekt mappning
    pair = [v for k,v in CRYPTO_PAIRS.items() if k.startswith(coin)][0]
    mapping = {'24h': '5MIN', '7d': '180MIN', '30d': '1440MIN'}
    h_raw = r.get(f'OHLC_CACHED_{mapping[timespan]}_{pair}')
    
    # Fallback om vald period saknas
    if not h_raw: h_raw = r.get(f'OHLC_CACHED_5MIN_{pair}')
    
    fig = go.Figure()
    if h_raw:
        h = json.loads(h_raw)
        fig.add_trace(go.Scatter(x=[datetime.fromtimestamp(i['time'], tz=timezone.utc) for i in h], 
                                 y=[i['price'] for i in h], line=dict(color='#0056b3', width=2)))
    
    fig.update_layout(title=f"Prisutveckling: {coin} ({timespan})", template="plotly_white", height=500)

    # Info Box
    box = html.Div(style={'textAlign': 'center'}, children=[
        html.H2(f"{coin}"),
        html.H1(f"{format_price(price)} EUR", style={'color': '#28a745', 'fontSize': '3em'})
    ])

    return box, "Tabell laddas...", fig

if __name__ == '__main__':
    app.run_server(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))