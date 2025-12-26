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

# Din original-lista (förkortad här för plats, men behåll alla i din fil)
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

# --- BAKGRUNDSTRÅD ---
def data_fetcher_loop():
    logger.info("Bakgrundshämtning startad.")
    while True:
        try:
            # 1. Hämta Ticker
            t_res = requests.get("https://api.kraken.com/0/public/Ticker", timeout=15)
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

            # 2. Hämta OHLC för 24h, 7d, 30d
            # Intervall: 5 (24h), 180 (7d), 1440 (30d)
            for label, pair in CRYPTO_PAIRS.items():
                for interval, suffix in [(5, '5MIN'), (180, '180MIN'), (1440, '1440MIN')]:
                    try:
                        o_res = requests.get(f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval={interval}", timeout=15)
                        if o_res.status_code == 200:
                            raw = list(o_res.json().get('result', {}).values())[0]
                            # Vi sparar de senaste 300 punkterna för att ha marginal
                            clean = [{'time': i[0], 'price': float(i[4])} for i in raw[-300:]]
                            r.set(f'OHLC_CACHED_{suffix}_{pair}', json.dumps(clean))
                        time.sleep(0.8) # Paus för att inte trigga Render-timeout
                    except: continue
            logger.info("Synk-runda klar.")
        except Exception as e:
            logger.error(f"Fel i loopen: {e}")
        time.sleep(60)

threading.Thread(target=data_fetcher_loop, daemon=True).start()

# --- DASH APP (Layout från din backup) ---
app = dash.Dash(__name__)
server = app.server

app.layout = html.Div(style={'backgroundColor': '#f0f2f5', 'fontFamily': 'Segoe UI'}, children=[
    # Här behåller du hela din stora layout-kod från backup_xrp_dash.py...
    # För tidsväljaren, se till att den ser ut så här:
    html.Div([
        dcc.RadioItems(
            id='timespan-selector',
            options=[
                {'label': ' 24h', 'value': '24h'},
                {'label': ' 7d', 'value': '7d'},
                {'label': ' 30d', 'value': '30d'}
            ],
            value='24h',
            inline=True
        )
    ]),
    # ... Resten av din layout (Gärna kopierad direkt från backupen)
    dcc.Graph(id='live-update-graph'),
    html.Div(id='crypto-summary-table'),
    dcc.Interval(id='interval-component', interval=30000)
])

# --- DIN ORIGINAL-LOGIK (H.V. Beräkningar etc.) ---
# Kopiera in alla dina funktioner: calculate_hv, get_trend_color etc.

@app.callback(
    Output('live-update-graph', 'figure'),
    [Input('interval-component', 'n_intervals'),
     Input('coin-dropdown', 'value'),
     Input('timespan-selector', 'value')]
)
def update_graph(n, coin, timespan):
    pair = [v for k,v in CRYPTO_PAIRS.items() if k.startswith(coin)][0]
    
    # Mappa knapp till rätt cache och antal punkter
    # 24h = 5min (288 punkter), 7d = 180min (56 punkter), 30d = 1440min (30 punkter)
    mapping = {
        '24h': ('5MIN', 288),
        '7d': ('180MIN', 56), 
        '30d': ('1440MIN', 30)
    }
    
    suffix, num_points = mapping[timespan]
    h_raw = r.get(f'OHLC_CACHED_{suffix}_{pair}')
    
    fig = go.Figure()
    if h_raw:
        h = json.loads(h_raw)[-num_points:] # Här trimmar vi så 30d bara blir 30 dagar
        times = [datetime.fromtimestamp(i['time'], tz=timezone.utc) for i in h]
        prices = [i['price'] for i in h]
        
        fig.add_trace(go.Scatter(x=times, y=prices, name=timespan, line=dict(color='#0056b3', width=3)))
        
        # Lägg till dina trendlinjer här precis som i backup-filen
        # Använd prices och times för att räkna ut slope/intercept
        
    fig.update_layout(template="plotly_white", hovermode="x unified")
    return fig

# ... Fortsätt med dina andra callbacks (update_info_box, update_table)
# Se till att de använder ID:n från din backup-fil.

if __name__ == '__main__':
    app.run_server(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))