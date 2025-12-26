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

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

# [KONSTANTER]
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
KRAKEN_TICKER_API_URL = "https://api.kraken.com/0/public/Ticker"
KRAKEN_OHLC_API_URL = "https://api.kraken.com/0/public/OHLC"
EXCHANGE_RATE_URL = "https://api.exchangerate-api.com/v4/latest/EUR"

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

COINS_LABELS = list(CRYPTO_PAIRS.keys())
SYMBOL_TO_LABEL = {label.split(' ')[0]: label for label in COINS_LABELS}

# --- Redis ---
REDIS_URL = os.environ.get('REDIS_URL')
r = from_url(REDIS_URL) if REDIS_URL else None

# --- Hjälpfunktioner ---
def format_price(p):
    return f"{p:,.4f}".replace(",", " ").replace(".", ",").replace(" ", ".") if p else "N/A"

def format_pct(c):
    if c is None: return html.Span("0,00%", style={'color': '#6c757d'})
    col = '#28a745' if c > 0 else '#dc3545'
    sym = '▲' if c > 0 else '▼'
    return html.Span(f"{sym} {abs(c):.2f}%", style={'color': col, 'fontWeight': 'bold', 'fontSize': '0.9em'})

def calculate_trade_value(short_h, curr_p):
    if not short_h or curr_p is None: return 0.0
    v = curr_p
    tv = 0.0
    # Originalvikter från din fil
    for b, w in [(12, 5), (36, 4)]:
        if len(short_h) < b: continue
        y = np.array([i['price'] for i in short_h[-b:]])
        slope, intercept, _, _, _ = linregress(np.arange(b), y)
        tx = slope * (b - 1) + intercept
        tv += (((tx - v) / v) * 100) * w
    return tv

# --- Dash App ---
app = dash.Dash(__name__)
server = app.server

app.layout = html.Div(style={'backgroundColor': '#f8f9fa', 'padding': '20px', 'fontFamily': 'Arial'}, children=[
    html.H1('📈 DJ-Investment Dashboard', style={'textAlign': 'center', 'color': '#0056b3'}),
    
    html.Div(style={'display': 'flex', 'gap': '20px'}, children=[
        html.Div(style={'flex': '0 0 250px', 'backgroundColor': 'white', 'padding': '15px', 'borderRadius': '10px', 'border': '1px solid #ddd'}, children=[
            html.H3("⚙️ Kontroller"),
            html.Label("Välj krypto:"),
            dcc.Dropdown(id='coin-dropdown', options=[{'label': k, 'value': k.split(' ')[0]} for k in COINS_LABELS], value='XRP'),
            html.Br(),
            html.Label("Basvaluta:"),
            dcc.Dropdown(id='currency-dropdown', options=[{'label': 'EUR', 'value': 'EUR'}, {'label': 'SEK', 'value': 'SEK'}], value='EUR'),
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

    html.Div(style={'marginTop': '20px', 'backgroundColor': 'white', 'padding': '15px', 'borderRadius': '10px', 'border': '1px solid #ddd'}, children=[
        dcc.Graph(id='live-update-graph', style={'height': '500px'})
    ]),
    
    html.Div(id='crypto-summary-table', style={'marginTop': '20px'}),
    
    dcc.Store(id='table-sort-store', data={'key': 'H.V.', 'asc': False}),
    dcc.Interval(id='interval-component', interval=30*1000)
])

@app.callback(
    Output('table-sort-store', 'data'),
    Input({'type': 'sort-header', 'index': ALL}, 'n_clicks'),
    State('table-sort-store', 'data'),
    prevent_initial_call=True
)
def update_sort(n, current):
    triggered = ctx.triggered_id
    if not triggered or not any(n): return current
    key = triggered['index']
    return {'key': key, 'asc': not current['asc'] if key == current['key'] else False}

@app.callback(
    [Output('main-info-box', 'children'),
     Output('crypto-summary-table', 'children'),
     Output('live-update-graph', 'figure')],
    [Input('interval-component', 'n_intervals'),
     Input('coin-dropdown', 'value'),
     Input('currency-dropdown', 'value'),
     Input('table-sort-store', 'data'),
     Input('timespan-selector', 'value')]
)
def update_ui(n, coin, curr, sort, timespan):
    cached = r.get('crypto_data') if r else None
    if not cached: return html.Div("Laddar data från Redis..."), html.Div(), go.Figure()
    
    data = json.loads(cached)
    rate = data.get('EUR_SEK_RATE', 11.2)
    changes = data.get('ALL_PERCENT_CHANGE', {})
    
    summary_list = []
    for label in COINS_LABELS:
        s = label.split(' ')[0]
        ticker = CRYPTO_PAIRS[label]
        pe = data.get(f'{s}/EUR', 0)
        h5 = json.loads(r.get(f'OHLC_CACHED_5MIN_{ticker}') or '[]') if r else []
        tv = calculate_trade_value(h5, pe)
        c = changes.get(s, {})
        summary_list.append({
            'Valuta': f"{CRYPTO_EMOJIS.get(s,'')} {label}", 'Pris (EUR)': pe,
            '30m': c.get('30m',0), '1h': c.get('1h',0), '3h': c.get('3h',0), '6h': c.get('6h',0),
            '12h': c.get('12h',0), '24h': c.get('24h',0), '7d': c.get('7d',0), '30d': c.get('30d',0),
            'H.V.': tv, 'raw_sym': s
        })

    summary_list.sort(key=lambda x: x.get(sort['key'], 0), reverse=not sort['asc'])
    
    cols = ["Valuta", "Pris (EUR)", "30m", "1h", "3h", "6h", "12h", "24h", "7d", "30d", "H.V."]
    header = html.Div(style={'display': 'flex', 'fontWeight': 'bold', 'padding': '10px', 'backgroundColor': '#eee'}, children=[
        html.Div(h, id={'type': 'sort-header', 'index': h}, style={'flex': '1', 'textAlign': 'center', 'cursor': 'pointer'}) for h in cols
    ])
    
    rows = [html.Div(style={'display': 'flex', 'padding': '8px', 'borderBottom': '1px solid #eee', 'backgroundColor': '#e6f7ff' if i['raw_sym']==coin else 'white', 'cursor': 'pointer'},
        id={'type': 'summary-card', 'index': i['raw_sym']},
        children=[
            html.Div(i['Valuta'], style={'flex': '1', 'fontWeight': 'bold'}),
            html.Div(format_price(i['Pris (EUR)']), style={'flex': '1', 'textAlign': 'right'}),
            *[html.Div(format_pct(i[k]), style={'flex': '1', 'textAlign': 'right'}) for k in cols[2:-1]],
            html.Div(f"▲ {i['H.V.']:.0f}", style={'flex': '1', 'textAlign': 'right', 'color': 'green', 'fontWeight': 'bold'})
        ]) for i in summary_list]

    sel = next(i for i in summary_list if i['raw_sym'] == coin)
    mult = rate if curr == 'SEK' else 1
    
    box = html.Div(style={'display': 'flex', 'justifyContent': 'space-between'}, children=[
        html.Div(style={'flex': '1', 'textAlign': 'center'}, children=[
            html.H2(f"{CRYPTO_EMOJIS.get(coin,'')} {coin}"),
            html.H1(f"{format_price(sel['Pris (EUR)']*mult)} {curr}", style={'color': '#28a745', 'fontSize': '2.5em'}),
            html.H3(f"Handelsvärde: {sel['H.V.']:.2f}")
        ]),
        html.Div(style={'flex': '1', 'borderLeft': '1px solid #ddd', 'borderRight': '1px solid #ddd', 'padding': '0 20px'}, children=[
            html.H4("Prisrörelser (%)", style={'textAlign': 'center'}),
            html.Div(style={'display': 'grid', 'gridTemplateColumns': '1fr 1fr', 'gap': '5px'}, children=[
                html.P(["30min: ", format_pct(sel['30m'])]), html.P(["18h: ", format_pct(changes.get(coin,{}).get('18h',0))]),
                html.P(["1h: ", format_pct(sel['1h'])]), html.P(["7dgr: ", format_pct(sel['7d'])]),
                html.P(["3h: ", format_pct(sel['3h'])]), html.P(["30dgr: ", format_pct(sel['30d'])]),
                html.P(["6h: ", format_pct(sel['6h'])]), html.P(["6mån: ", format_pct(changes.get(coin,{}).get('6m',0))]),
                html.P(["12h: ", format_pct(sel['12h'])]), html.P(["1år: ", format_pct(changes.get(coin,{}).get('1y',0))]),
            ])
        ]),
        html.Div(style={'flex': '1', 'paddingLeft': '20px'}, children=[
            html.H4("Trendvärden (Hx)"),
            html.P("(1h): 0,38", style={'color': 'green'}),
            html.P("(3h): -0,86", style={'color': 'red'})
        ])
    ])

    # GRAF-LOGIK
    ticker = CRYPTO_PAIRS[SYMBOL_TO_LABEL[coin]]
    
    # Välj nyckel baserat på val (7d = 180min, 30d = 1440min)
    if timespan == '7d':
        ckey = f'OHLC_CACHED_180MIN_{ticker}'
    elif timespan == '30d':
        ckey = f'OHLC_CACHED_1440MIN_{ticker}'
    else:
        ckey = f'OHLC_CACHED_5MIN_{ticker}'

    h_raw = r.get(ckey) if r else None
    
    # Fallback: Om specialdatan saknas, visa 5min så att den inte bara "laddar"
    if not h_raw:
        h_raw = r.get(f'OHLC_CACHED_5MIN_{ticker}')

    fig = go.Figure()
    if h_raw:
        h = json.loads(h_raw)
        fig.add_trace(go.Scatter(x=[datetime.fromtimestamp(i['time'], tz=timezone.utc) for i in h], 
                                 y=[i['price']*mult for i in h], 
                                 line=dict(color='#0056b3', width=2)))
    
    fig.update_layout(height=500, margin=dict(l=20,r=20,t=40,b=20), template="plotly_white")

    return box, html.Div([header] + rows), fig

@app.callback(Output('coin-dropdown', 'value'), Input({'type': 'summary-card', 'index': ALL}, 'n_clicks'), prevent_initial_call=True)
def select_coin(n):
    if not any(n): return dash.no_update
    return ctx.triggered_id['index']

if __name__ == '__main__':
    app.run_server(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 8050)))