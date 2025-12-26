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
from datetime import datetime, timezone

# --- Konfiguration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get('REDIS_URL')
r = from_url(REDIS_URL) if REDIS_URL else None

# Vi fokuserar på de viktigaste paren först för att spara minne/tid
CRYPTO_PAIRS = {
    'XRP (Ripple)': 'XRP/EUR', 'BTC (Bitcoin)': 'BTC/EUR', 'ETH (Ethereum)': 'ETH/EUR',
    'SOL (Solana)': 'SOL/EUR', 'GRASS (Grass)': 'GRASS/EUR', 'ADA (Cardano)': 'ADA/EUR',
    'DOT (Polkadot)': 'DOT/EUR', 'DOGE (Dogecoin)': 'DOGE/EUR', 'PUMP (PUMP)': 'PUMP/EUR',
    'Cookie DAO': 'COOKIE/EUR', 'Moonwalk (MF)': 'MF/EUR', 'YALA': 'YALA/EUR',
    'WIF (dogwifhat)': 'WIF/EUR', 'YFI (Yearn Finance)': 'YFI/EUR', 'BNB (BNB Chain)': 'BNB/EUR',
    'TRX (Tron)': 'TRX/EUR', 'PEPE (Pepe)': 'PEPE/EUR', 'LTC (LTC)': 'LTC/EUR'
}

# --- OPTIMERAD BAKGRUNDSPROCESS ---
def data_fetcher_loop():
    logger.info("Startar optimerad hämtning...")
    while True:
        try:
            # 1. Snabb hämtning av alla priser
            ticker_res = requests.get("https://api.kraken.com/0/public/Ticker", timeout=10)
            if ticker_res.status_code == 200:
                res_data = ticker_res.json().get('result', {})
                processed = {'EUR_SEK_RATE': 11.2, 'ALL_PERCENT_CHANGE': {}}
                for label, pair in CRYPTO_PAIRS.items():
                    s = label.split(' ')[0]
                    k_pair = pair.replace('/', '')
                    if k_pair in res_data:
                        price = float(res_data[k_pair]['c'][0])
                        processed[f'{s}/EUR'] = price
                        processed['ALL_PERCENT_CHANGE'][s] = {'24h': 0} # Förenklat
                r.set('crypto_data', json.dumps(processed))
            
            # 2. Långsam hämtning av OHLC (en i taget med paus)
            # Detta förhindrar "Worker Timeout"
            for label, pair in CRYPTO_PAIRS.items():
                for interval, suffix in [(5, '5MIN'), (180, '180MIN'), (1440, '1440MIN')]:
                    try:
                        ohlc_res = requests.get(f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval={interval}", timeout=10)
                        if ohlc_res.status_code == 200:
                            data = ohlc_res.json().get('result', {})
                            raw = list(data.values())[0]
                            clean = [{'time': i[0], 'price': float(i[4])} for i in raw[-100:]]
                            r.set(f'OHLC_CACHED_{suffix}_{pair}', json.dumps(clean))
                        time.sleep(1.5) # VIKTIG PAUS: Ger servern tid att svara på dashboard-anrop
                    except:
                        continue
            
            logger.info("Synk-runda klar.")
        except Exception as e:
            logger.error(f"Loop-fel: {e}")
        
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
                {'label': ' 24h', 'value': '24h'},
                {'label': ' 7d', 'value': '7d'},
                {'label': ' 30d', 'value': '30d'}
            ], value='24h'),
        ]),
        html.Div(id='main-info-box', style={'flex': '1', 'border': '2px solid #0056b3', 'borderRadius': '10px', 'padding': '20px', 'backgroundColor': 'white'})
    ]),

    dcc.Graph(id='live-graph', style={'marginTop': '20px'}),
    dcc.Interval(id='interval', interval=20*1000)
])

@app.callback(
    [Output('main-info-box', 'children'), Output('live-graph', 'figure')],
    [Input('interval', 'n_intervals'), Input('coin-dropdown', 'value'), Input('timespan-selector', 'value')]
)
def update_ui(n, coin, timespan):
    cached = r.get('crypto_data') if r else None
    if not cached: return html.Div("Laddar priser..."), go.Figure()
    
    data = json.loads(cached)
    price = data.get(f'{coin}/EUR', 0)
    
    pair = [v for k,v in CRYPTO_PAIRS.items() if k.startswith(coin)][0]
    mapping = {'24h': '5MIN', '7d': '180MIN', '30d': '1440MIN'}
    h_raw = r.get(f'OHLC_CACHED_{mapping[timespan]}_{pair}')
    
    fig = go.Figure()
    if h_raw:
        h = json.loads(h_raw)
        fig.add_trace(go.Scatter(x=[datetime.fromtimestamp(i['time'], tz=timezone.utc) for i in h], 
                                 y=[i['price'] for i in h], line=dict(color='#0056b3')))
    
    fig.update_layout(title=f"{coin} ({timespan})", template="plotly_white")
    return html.H2(f"{coin}: {price:.4f} EUR"), fig

if __name__ == '__main__':
    app.run_server(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))