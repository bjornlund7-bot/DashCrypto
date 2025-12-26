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
from datetime import datetime, timezone

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
}
# (Du kan lägga till alla dina par här igen, jag kortade ner listan för exemplet)

CRYPTO_EMOJIS = {'XRP': '🌊', 'BTC': '💰', 'ETH': '💎', 'SOL': '☀️'}

# --- BAKGRUNDSPROCESS (WORKER) ---
# Denna del hämtar data och sparar i Redis
def data_fetcher_loop():
    logger.info("Startar bakgrundshämtning av data...")
    while True:
        try:
            # 1. Hämta priser (Ticker)
            symbols = [v.replace('/', '') for v in CRYPTO_PAIRS.values()]
            res = requests.get(f"{KRAKEN_TICKER_API_URL}?pair={','.join(symbols)}")
            if res.status_code == 200:
                ticker_data = res.json().get('result', {})
                processed_data = {'EUR_SEK_RATE': 11.2, 'ALL_PERCENT_CHANGE': {}}
                
                for label, pair in CRYPTO_PAIRS.items():
                    s = label.split(' ')[0]
                    k_pair = pair.replace('/', '')
                    if k_pair in ticker_data:
                        price = float(ticker_data[k_pair]['c'][0])
                        processed_data[f'{s}/EUR'] = price
                
                r.set('crypto_data', json.dumps(processed_data))
            
            # 2. Hämta OHLC (för grafer)
            for label, pair in CRYPTO_PAIRS.items():
                s = label.split(' ')[0]
                # Hämta 5m (24h), 180m (7d) och 1440m (30d)
                for interval, key_suffix in [(5, '5MIN'), (180, '180MIN'), (1440, '1440MIN')]:
                    ohlc_res = requests.get(f"{KRAKEN_OHLC_API_URL}?pair={pair}&interval={interval}")
                    if ohlc_res.status_code == 200:
                        raw_ohlc = list(ohlc_res.json()['result'].values())[0]
                        clean_ohlc = [{'time': i[0], 'price': float(i[4])} for i in raw_ohlc[-100:]]
                        r.set(f'OHLC_CACHED_{key_suffix}_{pair}', json.dumps(clean_ohlc))
            
            logger.info("Redis uppdaterad.")
        except Exception as e:
            logger.error(f"Fel i loopen: {e}")
        
        time.sleep(60) # Vänta 1 minut innan nästa hämtning

# Starta workern i en egen tråd
threading.Thread(target=data_fetcher_loop, daemon=True).start()


# --- DASHBOARD (FRONTEND) ---
app = dash.Dash(__name__)
server = app.server

app.layout = html.Div(style={'padding': '20px', 'fontFamily': 'Arial'}, children=[
    html.H1('📈 DJ-Investment Dashboard (Live)'),
    html.Div(style={'display': 'flex', 'gap': '10px'}, children=[
        dcc.Dropdown(id='coin-dropdown', options=[{'label': k, 'value': k.split(' ')[0]} for k in CRYPTO_PAIRS.keys()], value='XRP', style={'width': '200px'}),
        dcc.RadioItems(id='timespan-selector', options=[
            {'label': ' 24h', 'value': '24h'},
            {'label': ' 7d', 'value': '7d'},
            {'label': ' 30d', 'value': '30d'}
        ], value='24h'),
    ]),
    html.Div(id='main-info-box', style={'marginTop': '20px', 'padding': '20px', 'border': '1px solid #ccc'}),
    dcc.Graph(id='live-graph'),
    dcc.Interval(id='interval', interval=30*1000)
])

@app.callback(
    [Output('main-info-box', 'children'), Output('live-graph', 'figure')],
    [Input('interval', 'n_intervals'), Input('coin-dropdown', 'value'), Input('timespan-selector', 'value')]
)
def update_ui(n, coin, timespan):
    cached = r.get('crypto_data') if r else None
    if not cached:
        return html.Div("Väntar på att bakgrundsprocessen ska hämta första datan (kan ta 30 sek)..."), go.Figure()
    
    data = json.loads(cached)
    price = data.get(f'{coin}/EUR', 0)
    
    # Hämta rätt graf-data
    pair = CRYPTO_PAIRS[[k for k in CRYPTO_PAIRS.keys() if k.startswith(coin)][0]]
    ckey = f'OHLC_CACHED_5MIN_{pair}'
    if timespan == '7d': ckey = f'OHLC_CACHED_180MIN_{pair}'
    elif timespan == '30d': ckey = f'OHLC_CACHED_1440MIN_{pair}'
    
    h_raw = r.get(ckey)
    fig = go.Figure()
    if h_raw:
        h = json.loads(h_raw)
        fig.add_trace(go.Scatter(x=[datetime.fromtimestamp(i['time'], tz=timezone.utc) for i in h], y=[i['price'] for i in h]))
    
    fig.update_layout(title=f"{coin} - {timespan}", template="plotly_white")
    
    return html.Div([
        html.H2(f"{coin}: {price:.4f} EUR")
    ]), fig

if __name__ == '__main__':
    app.run_server(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))