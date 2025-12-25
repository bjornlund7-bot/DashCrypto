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

# --- Konfiguration & Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get('REDIS_URL')
KRAKEN_TICKER_API_URL = "https://api.kraken.com/0/public/Ticker"

# Samma par som tidigare
CRYPTO_PAIRS = {
    'XRP (Ripple)': 'XRP/EUR', 'BTC (Bitcoin)': 'BTC/EUR', 'ETH (Ethereum)': 'ETH/EUR',
    'SOL (Solana)': 'SOL/EUR', 'GRASS (Grass)': 'GRASS/EUR', 'ADA (Cardano)': 'ADA/EUR',
    'DOT (Polkadot)': 'DOT/EUR', 'DOGE (Dogecoin)': 'DOGE/EUR', 'PUMP (PUMP)': 'PUMP/EUR',
    'AAVE (Aave)': 'AAVE/EUR', 'LINK (Chainlink)': 'LINK/EUR', 'SUI (SUI)': 'SUI/EUR',
    'DASH (Dash)': 'DASH/EUR', 'ATOM (Cosmos)': 'ATOM/EUR', 'ADA (Cardano)': 'ADA/EUR',
    'TRX (Tron)': 'TRX/EUR', 'LPT (LivePeer)': 'LPT/EUR', 'ALCX (Alchemix)': 'ALCX/EUR',
    'AERO (Aerodrome Finance)': 'AERO/EUR', 'EUL (Euler)': 'EUL/EUR', 'IP (Story)': 'IP/EUR'
}

CRYPTO_EMOJIS = {'XRP': '🌊', 'BTC': '💰', 'ETH': '💎', 'SOL': '☀️', 'ADA': '₳', 'DOT': '🟣', 'DOGE': '🐕'}

# --- Redis Anslutning ---
r = None
if REDIS_URL:
    try:
        r = from_url(REDIS_URL)
        r.ping()
        logger.info("Ansluten till Redis")
    except Exception as e:
        logger.error(f"Redis-fel: {e}")

# --- Hjälpfunktioner ---
def format_price_display(p):
    if p is None or p == 0: return "0,00"
    if p < 1: return f"{p:.4f}".replace(".", ",")
    return f"{p:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")

def format_change(c):
    if c is None: return html.Span("0,00%", style={'color': '#6c757d'})
    color = '#28a745' if c > 0 else '#dc3545'
    symbol = '▲' if c > 0 else '▼'
    return html.Span(f"{symbol} {abs(c):.2f}%", style={'color': color, 'fontWeight': 'bold'})

# --- Dash App ---
app = dash.Dash(__name__)
server = app.server

app.layout = html.Div(style={'backgroundColor': '#f8f9fa', 'padding': '20px', 'fontFamily': 'Arial'}, children=[
    html.H1('📈 DJ-Investment Dashboard', style={'textAlign': 'center', 'color': '#0056b3'}),
    
    html.Div(style={'display': 'flex', 'gap': '20px'}, children=[
        html.Div(style={'flex': '0 0 250px', 'backgroundColor': 'white', 'padding': '15px', 'borderRadius': '8px', 'border': '1px solid #ddd'}, children=[
            html.H3("⚙️ Kontroller"),
            html.Label("Välj kryptovaluta:"),
            dcc.Dropdown(id='coin-dropdown', options=[{'label': k, 'value': k.split(' ')[0]} for k in CRYPTO_PAIRS.keys()], value='XRP'),
            html.Br(),
            html.Label("Basvaluta:"),
            dcc.Dropdown(id='currency-dropdown', options=[{'label': 'EUR', 'value': 'EUR'}, {'label': 'SEK', 'value': 'SEK'}], value='EUR'),
            html.Br(),
            html.Label("Tidsfönster:"),
            dcc.RadioItems(id='timespan-selector', options=[{'label': ' 24h', 'value': '24h'}, {'label': ' 7d', 'value': '7d'}], value='24h'),
        ]),
        html.Div(id='main-info-box', style={'flex': '1', 'border': '2px solid #0056b3', 'borderRadius': '10px', 'padding': '20px', 'backgroundColor': 'white'})
    ]),

    html.Div(style={'marginTop': '20px', 'backgroundColor': 'white', 'padding': '15px', 'borderRadius': '8px', 'border': '1px solid #ddd'}, children=[
        dcc.Graph(id='live-update-graph', style={'height': '500px'})
    ]),
    
    html.Div(id='crypto-summary-table', style={'marginTop': '20px', 'backgroundColor': 'white', 'borderRadius': '8px', 'border': '1px solid #ddd'}),
    
    dcc.Store(id='table-sort-store', data={'key': 'H.V.', 'asc': False}),
    dcc.Interval(id='interval-component', interval=30*1000) # Uppdatera var 30:e sekund
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
    if not triggered or not any(n_clicks): return current_sort
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
def update_ui(n, selected_coin, base_curr, sort_config, timespan):
    # Hämta data från Redis med fallback
    raw_data = r.get('crypto_data') if r else None
    data = json.loads(raw_data) if raw_data else {"ALL_PERCENT_CHANGE": {}, "EUR_SEK_RATE": 11.0}
    
    all_changes = data.get('ALL_PERCENT_CHANGE', {})
    eur_sek = data.get('EUR_SEK_RATE', 11.20)
    
    # 1. Bygg Tabellen
    headers = ["Valuta", "Pris (EUR)", "30m", "1h", "3h", "6h", "12h", "24h", "7d", "30d", "H.V."]
    header_div = html.Div(style={'display': 'flex', 'fontWeight': 'bold', 'padding': '10px', 'borderBottom': '2px solid #ddd', 'backgroundColor': '#f0f0f0'}, children=[
        html.Div(h, id={'type': 'sort-header', 'index': h}, style={'flex': '1', 'textAlign': 'center', 'cursor': 'pointer'}) for h in headers
    ])

    sortable_list = []
    for label, ticker in CRYPTO_PAIRS.items():
        sym = label.split(' ')[0]
        price_eur = data.get(f'{sym}/EUR', 0)
        c = all_changes.get(sym, {})
        
        # Simulera/Hämta Handelsvärde (H.V.)
        hv_val = 0
        # Om du har sparat trade_value i Redis, hämta det här:
        # hv_val = data.get(f'{sym}/TRADE_VALUE', 0)

        sortable_list.append({
            "Valuta": f"{CRYPTO_EMOJIS.get(sym, '')} {label}",
            "Pris (EUR)": price_eur,
            "30m": c.get('30m', 0), "1h": c.get('1h', 0), "3h": c.get('3h', 0),
            "6h": c.get('6h', 0), "12h": c.get('12h', 0), "24h": c.get('24h', 0),
            "7d": c.get('7d', 0), "30d": c.get('30d', 0), "H.V.": hv_val, "raw_sym": sym
        })

    # Sortering
    sk = sort_config['key']
    sortable_list.sort(key=lambda x: x.get(sk, 0) if x.get(sk) is not None else -999, reverse=not sort_config['asc'])

    rows = []
    for item in sortable_list:
        is_sel = item['raw_sym'] == selected_coin
        rows.append(html.Div(id={'type': 'summary-card', 'index': item['raw_sym']},
            style={'display': 'flex', 'padding': '8px', 'borderBottom': '1px solid #eee', 'backgroundColor': '#e6f7ff' if is_sel else 'white', 'cursor': 'pointer'},
            children=[
                html.Div(item["Valuta"], style={'flex': '1', 'fontWeight': 'bold'}),
                html.Div(format_price_display(item["Pris (EUR)"]), style={'flex': '1', 'textAlign': 'right'}),
                *[html.Div(format_change(item[k]), style={'flex': '1', 'textAlign': 'right'}) for k in ["30m", "1h", "3h", "6h", "12h", "24h", "7d", "30d"]],
                html.Div(f"▲ {item['H.V.']}", style={'flex': '1', 'textAlign': 'right', 'color': 'green', 'fontWeight': 'bold'})
            ]
        ))

    # 2. Bygg Huvudbox
    sel_price = data.get(f'{selected_coin}/EUR', 0)
    display_price = sel_price * (eur_sek if base_curr == 'SEK' else 1)
    sel_c = all_changes.get(selected_coin, {})
    
    main_box = html.Div(style={'display': 'flex', 'justifyContent': 'space-between'}, children=[
        html.Div(style={'textAlign': 'center', 'flex': '1'}, children=[
            html.H2(f"{CRYPTO_EMOJIS.get(selected_coin, '')} {selected_coin}"),
            html.H1(f"{format_price_display(display_price)} {base_curr}", style={'color': '#28a745', 'fontSize': '3em'}),
            html.H3(f"Handelsvärde: {item.get('H.V.', 0)}", style={'color': '#0056b3'})
        ]),
        html.Div(style={'flex': '1', 'padding': '0 20px', 'borderLeft': '1px solid #ddd', 'borderRight': '1px solid #ddd'}, children=[
            html.H4("Prisrörelser (%)"),
            html.Div(style={'display': 'grid', 'gridTemplateColumns': '1fr 1fr', 'gap': '5px'}, children=[
                html.P(["30m: ", format_change(sel_c.get('30m'))]),
                html.P(["24h: ", format_change(sel_c.get('24h'))]),
                html.P(["1h: ", format_change(sel_c.get('1h'))]),
                html.P(["7d: ", format_change(sel_c.get('7d'))]),
                html.P(["3h: ", format_change(sel_c.get('3h'))]),
                html.P(["30d: ", format_change(sel_c.get('30d'))]),
            ])
        ]),
        html.Div(style={'flex': '1', 'paddingLeft': '20px'}, children=[
            html.H4("Trendvärden (Hx)"),
            html.P("(1h): 0,38", style={'color': 'green'}),
            html.P("(3h): -0,86", style={'color': 'red'}),
            html.P("(24h): 0,49", style={'color': 'green'})
        ])
    ])

    # 3. Graf
    fig = go.Figure()
    # Hämta historik för grafen
    ticker = CRYPTO_PAIRS.get(f"{selected_coin} (Ripple)", CRYPTO_PAIRS.get(next(k for k in CRYPTO_PAIRS if selected_coin in k)))
    hist_raw = r.get(f'OHLC_CACHED_5MIN_{ticker}') if r else None
    if hist_raw:
        hist = json.loads(hist_raw)
        x = [time.strftime('%H:%M', time.gmtime(i['time'])) for i in hist]
        y = [i['price'] * (eur_sek if base_curr == 'SEK' else 1) for i in hist]
        fig.add_trace(go.Scatter(x=x, y=y, mode='lines', line=dict(color='#0056b3', width=3), name="Pris"))
    
    fig.update_layout(height=500, margin=dict(l=20, r=20, t=40, b=20), template="plotly_white")

    return main_box, html.Div([header_div] + rows), fig

@app.callback(
    Output('coin-dropdown', 'value'),
    Input({'type': 'summary-card', 'index': ALL}, 'n_clicks'),
    prevent_initial_call=True
)
def select_coin(n):
    if not any(n): return dash.no_update
    return ctx.triggered_id['index']

if __name__ == '__main__':
    app.run_server(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 8050)))