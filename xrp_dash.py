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

# --- Konfiguration & Logging (Från din originalfil) ---
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

# --- HJÄLPFUNKTIONER (DIN ORIGINAL-LOGIK) ---
def calculate_hv(prices, window=12):
    if len(prices) < window: return 0
    returns = np.log(np.array(prices[1:]) / np.array(prices[:-1]))
    return np.std(returns[-window:]) * np.sqrt(365 * 288) * 100

def get_trendline(prices, blocks):
    if len(prices) < blocks: return 0, 0
    y = np.array(prices[-blocks:])
    x = np.arange(len(y))
    slope, intercept, _, _, _ = linregress(x, y)
    return slope, intercept

# --- OPTIMERAD BAKGRUNDSTRÅD ---
def data_fetcher_loop():
    logger.info("Bakgrundshämtning startad.")
    while True:
        try:
            # 1. Priser (Ticker)
            t_res = requests.get(KRAKEN_TICKER_API_URL, timeout=15)
            if t_res.status_code == 200:
                res_data = t_res.json().get('result', {})
                processed = {'EUR_SEK_RATE': 11.45, 'ALL_PERCENT_CHANGE': {}}
                for label, pair in CRYPTO_PAIRS.items():
                    s = label.split(' ')[0]
                    k_pair = pair.replace('/', '')
                    if k_pair in res_data:
                        price = float(res_data[k_pair]['c'][0])
                        open_p = float(res_data[k_pair]['o'])
                        processed[f'{s}/EUR'] = price
                        processed['ALL_PERCENT_CHANGE'][s] = {'24h': ((price - open_p)/open_p*100) if open_p > 0 else 0}
                r.set('crypto_data', json.dumps(processed))

            # 2. Historik (OHLC) - 24h (5m), 7d (3h), 30d (1d)
            for label, pair in CRYPTO_PAIRS.items():
                for interval, suffix in [(5, '5MIN'), (180, '180MIN'), (1440, '1440MIN')]:
                    try:
                        o_res = requests.get(f"{KRAKEN_OHLC_API_URL}?pair={pair}&interval={interval}", timeout=15)
                        if o_res.status_code == 200:
                            raw = list(o_res.json().get('result', {}).values())[0]
                            clean = [{'time': i[0], 'price': float(i[4])} for i in raw[-300:]]
                            r.set(f'OHLC_CACHED_{suffix}_{pair}', json.dumps(clean))
                        time.sleep(0.6) # Viktig paus för att undvika timeout
                    except: continue
            logger.info("Synk-runda klar.")
        except Exception as e:
            logger.error(f"Fel i loopen: {e}")
        time.sleep(60)

threading.Thread(target=data_fetcher_loop, daemon=True).start()

# --- DASH APP (DIN ORIGINALDESIGN) ---
app = dash.Dash(__name__, suppress_callback_exceptions=True)
server = app.server

app.layout = html.Div(style={'backgroundColor': '#f0f2f5', 'minHeight': '100vh', 'fontFamily': 'Segoe UI, Tahoma, Geneva, Verdana, sans-serif'}, children=[
    # Header
    html.Div(style={'backgroundColor': '#003366', 'padding': '20px', 'color': 'white', 'textAlign': 'center', 'boxShadow': '0 4px 12px rgba(0,0,0,0.1)'}, children=[
        html.H1("📈 DJ-Investment Crypto Dashboard", style={'margin': '0', 'fontSize': '2.5em', 'fontWeight': 'bold'}),
        html.P("Realtidsövervakning av kryptomarknaden", style={'opacity': '0.8', 'marginTop': '5px'})
    ]),

    html.Div(style={'maxWidth': '1400px', 'margin': '0 auto', 'padding': '30px'}, children=[
        # Top Cards & Controls
        html.Div(style={'display': 'grid', 'gridTemplateColumns': '1fr 3fr', 'gap': '30px', 'marginBottom': '30px'}, children=[
            # Kontrollpanel
            html.Div(style={'backgroundColor': 'white', 'padding': '25px', 'borderRadius': '15px', 'boxShadow': '0 4px 20px rgba(0,0,0,0.08)'}, children=[
                html.H3("⚙️ Inställningar", style={'marginTop': '0', 'color': '#003366'}),
                html.Label("Välj kryptovaluta:", style={'fontWeight': '600', 'display': 'block', 'marginBottom': '10px'}),
                dcc.Dropdown(id='coin-dropdown', options=[{'label': k, 'value': k.split(' ')[0]} for k in CRYPTO_PAIRS.keys()], value='XRP', style={'marginBottom': '20px'}),
                
                html.Label("Tidsperiod:", style={'fontWeight': '600', 'display': 'block', 'marginBottom': '10px'}),
                dcc.RadioItems(id='timespan-selector', options=[
                    {'label': ' 24h', 'value': '24h'},
                    {'label': ' 7d', 'value': '7d'},
                    {'label': ' 30d', 'value': '30d'}
                ], value='24h', labelStyle={'display': 'inline-block', 'marginRight': '15px'}, style={'marginBottom': '20px'}),

                html.Label("Valuta:", style={'fontWeight': '600', 'display': 'block', 'marginBottom': '10px'}),
                dcc.RadioItems(id='currency-selector', options=[{'label': ' EUR', 'value': 'EUR'}, {'label': ' SEK', 'value': 'SEK'}], value='EUR')
            ]),

            # Aktuell Info Box
            html.Div(id='main-info-box')
        ]),

        # Graf Sektion
        html.Div(style={'backgroundColor': 'white', 'padding': '25px', 'borderRadius': '15px', 'boxShadow': '0 4px 20px rgba(0,0,0,0.08)', 'marginBottom': '30px'}, children=[
            dcc.Graph(id='live-update-graph', config={'displayModeBar': False})
        ]),

        # Sammanfattningstabell
        html.Div(id='crypto-summary-table')
    ]),

    dcc.Interval(id='interval-component', interval=30000, n_intervals=0),
    dcc.Store(id='initial-coin-symbol-store', data='XRP')
])

# --- CALLBACKS (DIN ORIGINAL-LOGIK ÅTERSTÄLLD) ---

@app.callback(
    [Output('main-info-box', 'children'),
     Output('crypto-summary-table', 'children'),
     Output('live-update-graph', 'figure')],
    [Input('interval-component', 'n_intervals'),
     Input('coin-dropdown', 'value'),
     Input('timespan-selector', 'value'),
     Input('currency-selector', 'value')]
)
def update_all(n, coin, timespan, currency):
    # Hämta data
    cached = r.get('crypto_data') if r else None
    if not cached:
        return html.Div("Laddar priser..."), html.Div("Väntar på data från Kraken..."), go.Figure()

    data = json.loads(cached)
    rate = data.get('EUR_SEK_RATE', 11.45)
    price_eur = data.get(f'{coin}/EUR', 0)
    display_price = price_eur * (rate if currency == 'SEK' else 1)
    
    # --- 1. Info Box ---
    change_24h = data['ALL_PERCENT_CHANGE'].get(coin, {}).get('24h', 0)
    box = html.Div(style={'backgroundColor': 'white', 'padding': '25px', 'borderRadius': '15px', 'height': '100%', 'display': 'flex', 'flexDirection': 'column', 'justifyContent': 'center', 'boxShadow': '0 4px 20px rgba(0,0,0,0.08)'}, children=[
        html.H2(f"{coin}", style={'margin': '0', 'color': '#666'}),
        html.H1(f"{display_price:,.4f} {currency}".replace(",", " "), style={'fontSize': '3.5em', 'margin': '10px 0', 'color': '#003366'}),
        html.Div([
            html.Span(f"{'▲' if change_24h > 0 else '▼'} {abs(change_24h):.2f}%", style={'color': '#28a745' if change_24h > 0 else '#dc3545', 'fontSize': '1.5em', 'fontWeight': 'bold'}),
            html.Span(" (24h)", style={'color': '#999', 'marginLeft': '10px'})
        ])
    ])

    # --- 2. Graf ---
    pair = [v for k,v in CRYPTO_PAIRS.items() if k.startswith(coin)][0]
    # Mappning och trimning för att fixa 7d och 30d
    map_config = {'24h': ('5MIN', 288), '7d': ('180MIN', 56), '30d': ('1440MIN', 30)}
    suffix, num_points = map_config[timespan]
    
    h_raw = r.get(f'OHLC_CACHED_{suffix}_{pair}')
    fig = go.Figure()
    
    if h_raw:
        h_data = json.loads(h_raw)[-num_points:]
        hist_prices = [i['price'] for i in h_data]
        times = [datetime.fromtimestamp(i['time'], tz=timezone.utc) for i in h_data]
        
        y_vals = np.array(hist_prices) * (rate if currency == 'SEK' else 1)
        fig.add_trace(go.Scatter(x=times, y=y_vals, line=dict(color='#003366', width=3), fill='tozeroy', fillcolor='rgba(0,51,102,0.05)'))
        
        # Trendlinje
        if len(y_vals) > 5:
            slope, intercept = get_trendline(y_vals, len(y_vals))
            fig.add_trace(go.Scatter(x=times, y=slope * np.arange(len(y_vals)) + intercept, line=dict(color='orange', dash='dash'), name='Trend'))

    fig.update_layout(title=f"Prisutveckling: {coin} ({timespan})", template="plotly_white", margin=dict(l=0,r=0,t=40,b=0), height=450)

    # --- 3. Tabell ---
    table_rows = []
    # Din snygga tabell-logik här...
    for label, p_code in list(CRYPTO_PAIRS.items()):
        sym = label.split(' ')[0]
        p = data.get(f'{sym}/EUR', 0)
        c = data['ALL_PERCENT_CHANGE'].get(sym, {}).get('24h', 0)
        if p > 0:
            table_rows.append(html.Div(style={'display': 'grid', 'gridTemplateColumns': '2fr 1fr 1fr', 'padding': '15px', 'borderBottom': '1px solid #eee'}, children=[
                html.Span(label, style={'fontWeight': 'bold'}),
                html.Span(f"{p * (rate if currency == 'SEK' else 1):,.2f} {currency}"),
                html.Span(f"{c:+.2f}%", style={'color': '#28a745' if c > 0 else '#dc3545'})
            ]))

    table = html.Div(style={'backgroundColor': 'white', 'borderRadius': '15px', 'boxShadow': '0 4px 20px rgba(0,0,0,0.08)'}, children=[
        html.Div("Marknadsöversikt", style={'padding': '20px', 'fontWeight': 'bold', 'borderBottom': '2px solid #f0f2f5', 'color': '#003366'}),
        html.Div(table_rows, style={'maxHeight': '400px', 'overflowY': 'auto'})
    ])

    return box, table, fig

if __name__ == '__main__':
    app.run_server(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))