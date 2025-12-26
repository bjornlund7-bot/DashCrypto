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
from redis import from_url
from scipy.stats import linregress
import numpy as np
from datetime import datetime, timezone, timedelta

# --- Konfiguration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get('REDIS_URL')
r = from_url(REDIS_URL) if REDIS_URL else None

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
    while True:
        try:
            # 1. Priser
            t_res = requests.get("https://api.kraken.com/0/public/Ticker", timeout=10)
            if t_res.status_code == 200:
                res_data = t_res.json().get('result', {})
                processed = {'EUR_SEK_RATE': 11.2, 'ALL_PERCENT_CHANGE': {}}
                for label, pair in CRYPTO_PAIRS.items():
                    s = label.split(' ')[0]
                    k_pair = pair.replace('/', '')
                    if k_pair in res_data:
                        price = float(res_data[k_pair]['c'][0])
                        open_p = float(res_data[k_pair]['o'])
                        processed[f'{s}/EUR'] = price
                        processed['ALL_PERCENT_CHANGE'][s] = {'24h': ((price - open_p)/open_p*100) if open_p > 0 else 0}
                r.set('crypto_data', json.dumps(processed))

            # 2. OHLC (Långsam för att undvika timeout)
            for label, pair in CRYPTO_PAIRS.items():
                for interval, suffix in [(5, '5MIN'), (180, '180MIN'), (1440, '1440MIN')]:
                    try:
                        o_res = requests.get(f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval={interval}", timeout=10)
                        if o_res.status_code == 200:
                            data = o_res.json().get('result', {})
                            raw = list(data.values())[0]
                            clean = [{'time': i[0], 'price': float(i[4])} for i in raw[-150:]]
                            r.set(f'OHLC_CACHED_{suffix}_{pair}', json.dumps(clean))
                        time.sleep(1.2) # Paus för att servern ska andas
                    except: continue
        except Exception as e: logger.error(f"Loop-fel: {e}")
        time.sleep(60)

threading.Thread(target=data_fetcher_loop, daemon=True).start()

# --- DASH APP ---
app = dash.Dash(__name__)
server = app.server

app.layout = html.Div(style={'backgroundColor': '#f8f9fa', 'padding': '20px', 'fontFamily': 'Arial'}, children=[
    html.H1('📈 DJ-Investment Dashboard', style={'textAlign': 'center', 'color': '#0056b3'}),
    html.Div(style={'display': 'flex', 'gap': '20px'}, children=[
        html.Div(style={'flex': '0 0 250px', 'backgroundColor': 'white', 'padding': '15px', 'borderRadius': '10px', 'border': '1px solid #ddd'}, children=[
            html.H3("⚙️ Inställningar"),
            dcc.Dropdown(id='coin-dropdown', options=[{'label': k, 'value': k.split(' ')[0]} for k in CRYPTO_PAIRS.keys()], value='XRP'),
            html.Br(),
            dcc.RadioItems(id='timespan-selector', options=[
                {'label': ' 24h', 'value': '24h'}, {'label': ' 7d', 'value': '7d'}, {'label': ' 30d', 'value': '30d'}
            ], value='24h'),
        ]),
        html.Div(id='main-info-box', style={'flex': '1', 'border': '2px solid #0056b3', 'borderRadius': '10px', 'padding': '20px', 'backgroundColor': 'white'})
    ]),
    dcc.Graph(id='live-update-graph', style={'marginTop': '20px'}),
    html.Div(id='crypto-summary-table', style={'marginTop': '20px'}),
    dcc.Interval(id='interval-component', interval=30*1000)
])

def format_price(p): return f"{p:,.4f}".replace(",", " ").replace(".", ",").replace(" ", ".") if p else "0,0000"

@app.callback(
    [Output('main-info-box', 'children'), Output('crypto-summary-table', 'children'), Output('live-update-graph', 'figure')],
    [Input('interval-component', 'n_intervals'), Input('coin-dropdown', 'value'), Input('timespan-selector', 'value')]
)
def update_ui(n, coin, timespan):
    cached = r.get('crypto_data') if r else None
    if not cached: return html.Div("Laddar..."), html.Div("Väntar på data..."), go.Figure()
    
    data = json.loads(cached)
    curr_p = data.get(f'{coin}/EUR', 0)
    
    # Graf
    pair = [v for k,v in CRYPTO_PAIRS.items() if k.startswith(coin)][0]
    suffix = {'24h': '5MIN', '7d': '180MIN', '30d': '1440MIN'}[timespan]
    h_raw = r.get(f'OHLC_CACHED_{suffix}_{pair}')
    
    fig = go.Figure()
    if h_raw:
        h = json.loads(h_raw)
        prices = [i['price'] for i in h]
        times = [datetime.fromtimestamp(i['time'], tz=timezone.utc) for i in h]
        fig.add_trace(go.Scatter(x=times, y=prices, line=dict(color='#0056b3', width=2)))
        
        # Enkel trendlinje (Trend 1h)
        if len(prices) > 12:
            y = np.array(prices[-12:])
            slope, intercept, _, _, _ = linregress(np.arange(len(y)), y)
            fig.add_trace(go.Scatter(x=times[-12:], y=slope * np.arange(len(y)) + intercept, 
                                     line=dict(color='orange', dash='dash'), name='Trend 1h'))

    fig.update_layout(title=f"{coin} ({timespan})", template="plotly_white")
    
    # Info Box
    box = html.Div(style={'textAlign': 'center'}, children=[
        html.H2(f"{coin}"),
        html.H1(f"{format_price(curr_p)} EUR", style={'color': '#28a745', 'fontSize': '2.5em'})
    ])

    # Tabell-lista
    rows = []
    for label, p_code in list(CRYPTO_PAIRS.items()):
        sym = label.split(' ')[0]
        p = data.get(f'{sym}/EUR', 0)
        if p > 0:
            rows.append(html.Div(f"{label}: {format_price(p)} EUR", 
                                 style={'padding': '8px', 'borderBottom': '1px solid #eee'}))

    return box, html.Div(rows, style={'backgroundColor': 'white', 'borderRadius': '10px', 'padding': '10px'}), fig

if __name__ == '__main__':
    app.run_server(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))