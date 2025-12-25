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
from datetime import datetime

# --- Konfiguration ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# [Hämta miljövariabler för API och Redis]
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
REDIS_URL = os.environ.get('REDIS_URL')

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
    'BRICK (Bricks)': 'BRICK/EUR',
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

# Tidskonfigurationer för beräkningar
TIME_WINDOWS = {
    '30m': {'blocks': 6, 'interval': 5},
    '1h': {'blocks': 12, 'interval': 5},
    '3h': {'blocks': 36, 'interval': 5},
    '6h': {'blocks': 72, 'interval': 5},
    '12h': {'blocks': 144, 'interval': 5},
    '18h': {'blocks': 216, 'interval': 5},
    '24h': {'blocks': 288, 'interval': 5},
    '7d': {'blocks': 7, 'interval': 1440},
    '30d': {'blocks': 30, 'interval': 1440},
}

TREND_WINDOWS = {
    '1h':  {'blocks': 12,  'weight': 5, 'source': '5min'},
    '3h':  {'blocks': 36,  'weight': 4, 'source': '5min'},
    '6h':  {'blocks': 72,  'weight': 3, 'source': '5min'},
    '12h': {'blocks': 144, 'weight': 3, 'source': '5min'},
    '18h': {'blocks': 216, 'weight': 2, 'source': '5min'},
    '7d':  {'blocks': 7,   'weight': 1, 'source': '1day'},
    '30d': {'blocks': 30,  'weight': 0.4, 'source': '1day'},
    '6m': {'blocks': 180, 'weight': 0.2, 'source': '1day'},
    '1y': {'blocks': 365, 'weight': 0.1, 'source': '1day'},
}

# --- Redis Anslutning ---
r = None
if REDIS_URL:
    try:
        r = from_url(REDIS_URL)
        r.ping()
    except exceptions.ConnectionError:
        r = None

# --- Hjälpfunktioner för formatering ---
def format_price_display(p):
    if p is None: return "N/A"
    # Använd punkt för tusentalsavgränsare och komma för decimaler enligt bilden
    return f"{p:,.4f}".replace(",", " ").replace(".", ",").replace(" ", ".")

def format_change(c):
    if c is None: return html.Span("0,00%", style={'color': '#6c757d'})
    color = '#28a745' if c > 0 else '#dc3545'
    symbol = '▲' if c > 0 else '▼'
    return html.Span(f"{symbol} {abs(c):.2f}%", style={'color': color, 'fontWeight': 'bold'})

# --- Dash Layout ---
app = dash.Dash(__name__)
server = app.server

app.layout = html.Div(style={'backgroundColor': '#f8f9fa', 'padding': '20px', 'fontFamily': 'Arial'}, children=[
    html.H1('📈 DJ-Investment Dashboard (Kraken Live)', style={'textAlign': 'center', 'color': '#0056b3'}),
    
    # Kontroller och Huvudbox
    html.Div(style={'display': 'flex', 'gap': '20px'}, children=[
        html.Div(style={'flex': '0 0 250px', 'backgroundColor': 'white', 'padding': '15px', 'borderRadius': '8px', 'border': '1px solid #ddd'}, children=[
            html.H3("⚙️ Kontroller"),
            html.Label("Välj kryptovaluta:"),
            dcc.Dropdown(id='coin-dropdown', options=[{'label': k, 'value': k.split(' ')[0]} for k in CRYPTO_PAIRS.keys()], value='XRP'),
            html.Br(),
            html.Label("Välj basvaluta/krypto:"),
            dcc.Dropdown(id='currency-dropdown', options=[{'label': 'EUR (EUR)', 'value': 'EUR'}, {'label': 'SEK (SEK)', 'value': 'SEK'}], value='EUR'),
            html.Br(),
            html.Label("Tidsfönster i graf:"),
            dcc.RadioItems(id='timespan-selector', options=[{'label': ' 24h (5m)', 'value': '24h'}, {'label': ' 7d (15m)', 'value': '7d'}], value='24h'),
        ]),
        
        # Sektion för Huvudbox (Växlar dynamiskt)
        html.Div(id='main-info-box', style={'flex': '1', 'border': '2px solid #0056b3', 'borderRadius': '10px', 'padding': '20px', 'backgroundColor': 'white'})
    ]),

    # Graf-sektion med fast höjd
    html.Div(style={'marginTop': '20px', 'backgroundColor': 'white', 'padding': '15px', 'borderRadius': '8px', 'border': '1px solid #ddd'}, children=[
        dcc.Graph(id='live-update-graph', style={'height': '500px'})
    ]),
    
    # Sammanställningstabell
    html.Div(id='crypto-summary-table', style={'marginTop': '20px', 'backgroundColor': 'white', 'borderRadius': '8px', 'border': '1px solid #ddd'}),
    
    dcc.Store(id='table-sort-store', data={'key': 'H.V.', 'asc': False}),
    dcc.Interval(id='interval-component', interval=60*1000)
])

# --- Callbacks ---

@app.callback(
    Output('table-sort-store', 'data'),
    Input({'type': 'sort-header', 'index': ALL}, 'n_clicks'),
    State('table-sort-store', 'data'),
    prevent_initial_call=True
)
def update_sort_state(n_clicks, current_sort):
    triggered = ctx.triggered_id
    if not triggered: return current_sort
    new_key = triggered['index']
    is_asc = not current_sort['asc'] if new_key == current_sort['key'] else False
    return {'key': new_key, 'asc': is_asc}

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
def update_all_components(n, selected_coin, base_curr, sort_config, timespan):
    # Hämta data från Redis
    raw_data = r.get('crypto_data') if r else None
    if not raw_data: return html.Div("Laddar data..."), html.Div(), go.Figure()
    data = json.loads(raw_data)
    
    all_changes = data.get('ALL_PERCENT_CHANGE', {})
    
    # 1. Bygg Sammanställning (Tabell)
    table_rows = []
    headers = ["Valuta", "Pris (EUR)", "30m", "1h", "3h", "6h", "12h", "24h", "7d", "30d", "H.V."]
    
    # Skapa sorterbar header
    header_div = html.Div(style={'display': 'flex', 'fontWeight': 'bold', 'padding': '10px', 'borderBottom': '2px solid #ddd', 'backgroundColor': '#f0f0f0'}, children=[
        html.Div(h, id={'type': 'sort-header', 'index': h}, style={'flex': '1', 'textAlign': 'center', 'cursor': 'pointer'}) for h in headers
    ])

    # Förbered data för sortering
    sortable_list = []
    for label, ticker in CRYPTO_PAIRS.items():
        sym = label.split(' ')[0]
        price = data.get(f'{sym}/EUR', 0)
        changes = all_changes.get(sym, {})
        
        # Beräkna H.V. (Handelsvärde/Trade Value)
        hv = 0 # Förenklat för exemplet, bör hämtas från din beräkningslogik
        
        row_data = {
            "Valuta": f"{CRYPTO_EMOJIS.get(sym, '')} {label}",
            "Pris (EUR)": price,
            "30m": changes.get('30m', 0),
            "1h": changes.get('1h', 0),
            "3h": changes.get('3h', 0),
            "6h": changes.get('6h', 0),
            "12h": changes.get('12h', 0),
            "24h": changes.get('24h', 0),
            "7d": changes.get('7d', 0),
            "30d": changes.get('30d', 0),
            "H.V.": hv,
            "raw_sym": sym
        }
        sortable_list.append(row_data)

    # Utför Sortering
    sort_key = sort_config['key']
    sortable_list.sort(key=lambda x: x.get(sort_key, 0) if x.get(sort_key) is not None else -999, reverse=not sort_config['asc'])

    for item in sortable_list:
        is_sel = item['raw_sym'] == selected_coin
        table_rows.append(html.Div(id={'type': 'summary-card', 'index': item['raw_sym']},
            style={'display': 'flex', 'padding': '8px', 'borderBottom': '1px solid #eee', 'backgroundColor': '#e6f7ff' if is_sel else 'white', 'cursor': 'pointer'},
            children=[
                html.Div(item["Valuta"], style={'flex': '1', 'fontWeight': 'bold'}),
                html.Div(format_price_display(item["Pris (EUR)"]), style={'flex': '1', 'textAlign': 'right'}),
                html.Div(format_change(item["30m"]), style={'flex': '1', 'textAlign': 'right'}),
                html.Div(format_change(item["1h"]), style={'flex': '1', 'textAlign': 'right'}),
                html.Div(format_change(item["3h"]), style={'flex': '1', 'textAlign': 'right'}),
                html.Div(format_change(item["6h"]), style={'flex': '1', 'textAlign': 'right'}),
                html.Div(format_change(item["12h"]), style={'flex': '1', 'textAlign': 'right'}),
                html.Div(format_change(item["24h"]), style={'flex': '1', 'textAlign': 'right'}),
                html.Div(format_change(item["7d"]), style={'flex': '1', 'textAlign': 'right'}),
                html.Div(format_change(item["30d"]), style={'flex': '1', 'textAlign': 'right'}),
                html.Div(f"▲ {item['H.V.']}", style={'flex': '1', 'textAlign': 'right', 'color': 'green', 'fontWeight': 'bold'})
            ]
        ))

    # 2. Bygg Huvudbox
    selected_changes = all_changes.get(selected_coin, {})
    curr_price = data.get(f'{selected_coin}/EUR', 0)
    
    main_box_content = html.Div(style={'display': 'flex', 'justifyContent': 'space-between'}, children=[
        # Vänster: Pris & H.V.
        html.Div(style={'textAlign': 'center', 'flex': '1'}, children=[
            html.H2(f"{CRYPTO_EMOJIS.get(selected_coin, '')} {selected_coin}"),
            html.H1(f"{format_price_display(curr_price)} EUR", style={'color': '#28a745', 'fontSize': '3em'}),
            html.H3(f"Handelsvärde: 2.86", style={'color': '#0056b3'})
        ]),
        # Mitten: Prisrörelser Grid
        html.Div(style={'flex': '1', 'padding': '0 20px', 'borderLeft': '1px solid #ddd', 'borderRight': '1px solid #ddd'}, children=[
            html.H4("Prisrörelser (%) & 24h Intervall", style={'textAlign': 'center'}),
            html.Div(style={'display': 'grid', 'gridTemplateColumns': '1fr 1fr', 'gap': '10px'}, children=[
                html.P(["30min: ", format_change(selected_changes.get('30m'))]),
                html.P(["18h: ", format_change(selected_changes.get('18h'))]),
                html.P(["1h: ", format_change(selected_changes.get('1h'))]),
                html.P(["7dgr: ", format_change(selected_changes.get('7d'))]),
                html.P(["3h: ", format_change(selected_changes.get('3h'))]),
                html.P(["30dgr: ", format_change(selected_changes.get('30d'))]),
                html.P(["6h: ", format_change(selected_changes.get('6h'))]),
                html.P(["6mån: ", format_change(0)]), # Exempelvärde
                html.P(["12h: ", format_change(selected_changes.get('12h'))]),
                html.P(["1år: ", format_change(0)]),
            ])
        ]),
        # Höger: Trendvärden
        html.Div(style={'flex': '1', 'paddingLeft': '20px'}, children=[
            html.H4("Trendvärden (Hx) - Vikt/Riktning"),
            html.P("Kort Sikt (5m data):", style={'fontWeight': 'bold'}),
            html.P("(1h): 0.38", style={'color': 'green'}),
            html.P("(3h): -0.86", style={'color': 'red'}),
            html.Br(),
            html.P("Lång Sikt (1d data):", style={'fontWeight': 'bold'}),
            html.P("(7d): -1.01", style={'color': 'red'})
        ])
    ])

    # 3. Graf
    fig = go.Figure()
    # Logik för att hämta OHLC-data från Redis och rita grafen läggs här (samma som tidigare)
    fig.update_layout(height=500, margin=dict(l=20, r=20, t=40, b=20), template="plotly_white")

    return main_box_content, html.Div([header_div] + table_rows), fig

# Callback för att välja krypto via klick i tabell
@app.callback(
    Output('coin-dropdown', 'value'),
    Input({'type': 'summary-card', 'index': ALL}, 'n_clicks'),
    prevent_initial_call=True
)
def select_from_table(n_clicks):
    if not any(n_clicks): return dash.no_update
    return ctx.triggered_id['index']

if __name__ == '__main__':
    app.run_server(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 8050)))