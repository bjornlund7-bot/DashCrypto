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

# --- Konfiguration & Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get('REDIS_URL')
r = from_url(REDIS_URL) if REDIS_URL else None

KRAKEN_TICKER_API_URL = "https://api.kraken.com/0/public/Ticker"
KRAKEN_OHLC_API_URL = "https://api.kraken.com/0/public/OHLC"

# Dina original-par
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
}

# --- BAKGRUNDSPROCESS (WORKER) ---
def data_fetcher_loop():
    logger.info("Bakgrundstråd startad.")
    while True:
        try:
            # 1. Hämta Ticker-priser
            res = requests.get(KRAKEN_TICKER_API_URL)
            if res.status_code == 200 and 'result' in res.json():
                ticker_data = res.json()['result']
                processed = {'EUR_SEK_RATE': 11.2, 'ALL_PERCENT_CHANGE': {}}
                
                for label, pair in CRYPTO_PAIRS.items():
                    s = label.split(' ')[0]
                    k_pair = pair.replace('/', '')
                    if k_pair in ticker_data:
                        price = float(ticker_data[k_pair]['c'][0])
                        processed[f'{s}/EUR'] = price
                        # Enkel beräkning av 24h ändring för tabellen
                        open_p = float(ticker_data[k_pair]['o'])
                        processed['ALL_PERCENT_CHANGE'][s] = {'24h': ((price - open_p) / open_p) * 100}
                
                r.set('crypto_data', json.dumps(processed))

            # 2. Hämta OHLC för graferna (5m, 180m, 1440m)
            for label, pair in CRYPTO_PAIRS.items():
                for interval, suffix in [(5, '5MIN'), (180, '180MIN'), (1440, '1440MIN')]:
                    ohlc_res = requests.get(f"{KRAKEN_OHLC_API_URL}?pair={pair}&interval={interval}")
                    if ohlc_res.status_code == 200 and 'result' in ohlc_res.json():
                        raw_ohlc = list(ohlc_res.json()['result'].values())[0]
                        clean_ohlc = [{'time': i[0], 'price': float(i[4])} for i in raw_ohlc[-200:]]
                        r.set(f'OHLC_CACHED_{suffix}_{pair}', json.dumps(clean_ohlc))
                    time.sleep(0.3) # Rate limit skydd
            
            logger.info("Redis uppdaterad med priser och grafer.")
        except Exception as e:
            logger.error(f"Fel i hämtningsloopen: {e}")
        
        time.sleep(120)

# Starta hämtningen i bakgrunden direkt
threading.Thread(target=data_fetcher_loop, daemon=True).start()

# --- HJÄLPFUNKTIONER FÖR UI ---
def format_price(p):
    return f"{p:,.4f}".replace(",", " ").replace(".", ",").replace(" ", ".") if p else "0,0000"

def format_pct(c):
    if c is None: return html.Span("0,00%", style={'color': '#6c757d'})
    col = '#28a745' if c > 0 else '#dc3545'
    sym = '▲' if c > 0 else '▼'
    return html.Span(f"{sym} {abs(c):.2f}%", style={'color': col, 'fontWeight': 'bold'})

def calculate_hv(hist, curr_p):
    if not hist or not curr_p: return 0.0
    y = np.array([i['price'] for i in hist[-36:]]) # Kolla senaste 3h (baserat på 5m)
    if len(y) < 36: return 0.0
    slope, intercept, _, _, _ = linregress(np.arange(len(y)), y)
    target = slope * (len(y) - 1) + intercept
    return ((target - curr_p) / curr_p) * 100 * 5

# --- DASHBOARD FRONTEND ---
app = dash.Dash(__name__)
server = app.server

app.layout = html.Div(style={'backgroundColor': '#f8f9fa', 'padding': '20px', 'fontFamily': 'Arial'}, children=[
    html.H1('📈 DJ-Investment Dashboard', style={'textAlign': 'center', 'color': '#0056b3'}),
    
    html.Div(style={'display': 'flex', 'gap': '20px'}, children=[
        html.Div(style={'flex': '0 0 250px', 'backgroundColor': 'white', 'padding': '15px', 'borderRadius': '10px', 'border': '1px solid #ddd'}, children=[
            html.H3("⚙️ Kontroller"),
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

@app.callback(
    [Output('main-info-box', 'children'), Output('crypto-summary-table', 'children'), Output('live-update-graph', 'figure')],
    [Input('interval-component', 'n_intervals'), Input('coin-dropdown', 'value'), Input('timespan-selector', 'value')]
)
def update_ui(n, coin, timespan):
    cached = r.get('crypto_data') if r else None
    if not cached:
        return html.Div("Hämtar data från Kraken... Vänta ca 30 sekunder."), html.Div(), go.Figure()
    
    data = json.loads(cached)
    changes = data.get('ALL_PERCENT_CHANGE', {})
    
    # Bygg tabellen
    summary_list = []
    for label, pair in CRYPTO_PAIRS.items():
        s = label.split(' ')[0]
        p_eur = data.get(f'{s}/EUR', 0)
        h5_raw = r.get(f'OHLC_CACHED_5MIN_{pair}')
        h5 = json.loads(h5_raw) if h5_raw else []
        hv = calculate_hv(h5, p_eur)
        summary_list.append({'sym': s, 'label': label, 'p': p_eur, 'c24': changes.get(s, {}).get('24h', 0), 'hv': hv})

    header = html.Div(style={'display': 'flex', 'backgroundColor': '#eee', 'padding': '10px', 'fontWeight': 'bold'}, children=[
        html.Div("Valuta", style={'flex': '1'}), html.Div("Pris (EUR)", style={'flex': '1'}), html.Div("24h %", style={'flex': '1'}), html.Div("H.V.", style={'flex': '1'})
    ])
    rows = [html.Div(style={'display': 'flex', 'padding': '10px', 'borderBottom': '1px solid #eee', 'backgroundColor': 'white'}, children=[
        html.Div(i['label'], style={'flex': '1'}), html.Div(format_price(i['p']), style={'flex': '1'}), 
        html.Div(format_pct(i['c24']), style={'flex': '1'}), html.Div(f"{i['hv']:.1f}", style={'flex': '1', 'color': 'green'})
    ]) for i in summary_list]

    # Graf
    pair = [v for k,v in CRYPTO_PAIRS.items() if k.startswith(coin)][0]
    interval_map = {'24h': '5MIN', '7d': '180MIN', '30d': '1440MIN'}
    ckey = f'OHLC_CACHED_{interval_map[timespan]}_{pair}'
    h_raw = r.get(ckey) or r.get(f'OHLC_CACHED_5MIN_{pair}')
    
    fig = go.Figure()
    if h_raw:
        h = json.loads(h_raw)
        fig.add_trace(go.Scatter(x=[datetime.fromtimestamp(i['time'], tz=timezone.utc) for i in h], y=[i['price'] for i in h], line=dict(color='#0056b3')))
    
    fig.update_layout(title=f"{coin} - {timespan}", template="plotly_white", height=400)

    # Info Box
    curr_p = data.get(f'{coin}/EUR', 0)
    box = html.Div(style={'textAlign': 'center'}, children=[
        html.H2(f"{coin}"),
        html.H1(f"{format_price(curr_p)} EUR", style={'color': '#28a745', 'fontSize': '3em'})
    ])

    return box, html.Div([header] + rows), fig

if __name__ == '__main__':
    app.run_server(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))