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

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

# [KONSTANTER]
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
KRAKEN_TICKER_API_URL = "https://api.kraken.com/0/public/Ticker"
KRAKEN_OHLC_API_URL = "https://api.kraken.com/0/public/OHLC"
EXCHANGE_RATE_URL = "https://api.exchangerate-api.com/v4/latest/EUR"

# URL för logotyper
LOGO_BASE_URL = "https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/"

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

DEFAULT_PAIR_KEY = 'XRP (Ripple)'
DEFAULT_COIN_SYMBOL = DEFAULT_PAIR_KEY.split(' ')[0]
COINS_LABELS = list(CRYPTO_PAIRS.keys())
COINS_SYMBOLS = [label.split(' ')[0] for label in COINS_LABELS]
BASE_CURRENCIES = ['EUR', 'SEK', 'USD'] + [s for s in COINS_SYMBOLS]
SYMBOL_TO_LABEL = {label.split(' ')[0]: label for label in COINS_LABELS}

UPDATE_INTERVAL_FAST = 10
UPDATE_INTERVAL_SLOW = 120
OHLC_FETCH_INTERVAL_SECONDS = 120
OHLC_CACHE_INTERVAL_MIN = 5
SUMMARY_SCHEDULE_HOURS = [7, 9, 12, 15, 18, 21]
REDIS_SUMMARY_KEY = 'summary_last_sent_time'

TIME_WINDOWS = {
    '30m': {'blocks': 6, 'interval': OHLC_CACHE_INTERVAL_MIN},
    '1h': {'blocks': 12, 'interval': OHLC_CACHE_INTERVAL_MIN},
    '3h': {'blocks': 36, 'interval': OHLC_CACHE_INTERVAL_MIN},
    '6h': {'blocks': 72, 'interval': OHLC_CACHE_INTERVAL_MIN},
    '12h': {'blocks': 144, 'interval': OHLC_CACHE_INTERVAL_MIN},
    '18h': {'blocks': 216, 'interval': OHLC_CACHE_INTERVAL_MIN},
    '24h': {'blocks': 288, 'interval': OHLC_CACHE_INTERVAL_MIN},
    '7d': {'blocks': 7, 'interval': 1440},
    '30d': {'blocks': 30, 'interval': 1440},
    '6m': {'blocks': 180, 'interval': 1440},
    '1y': {'blocks': 365, 'interval': 1440},
}

TREND_WINDOWS = {
    '1h':  {'blocks': 12,  'color': '#ff7f0e', 'name': 'Trend (1h)',  'weight': 5, 'source': '5min', 'show_line': True},
    '3h':  {'blocks': 36,  'color': '#2ca02c', 'name': 'Trend (3h)',  'weight': 4, 'source': '5min', 'show_line': True},
    '6h':  {'blocks': 72,  'color': '#d62728', 'name': 'Trend (6h)',  'weight': 3, 'source': '5min', 'show_line': True},
    '12h': {'blocks': 144, 'color': '#9467bd', 'name': 'Trend (12h)', 'weight': 3, 'source': '5min', 'show_line': True},
    '18h': {'blocks': 216, 'color': '#8c564b', 'name': 'Trend (18h)', 'weight': 2, 'source': '5min', 'show_line': True},
    '7d':  {'blocks': 7,   'color': '#e377c2', 'name': 'Trend (7d)',  'weight': 1, 'source': '1day', 'show_line': True},
    '30d': {'blocks': 30,  'color': '#7f7f7f', 'name': 'Trend (30d)', 'weight': 0.4, 'source': '1day', 'show_line': True},
    '6m': {'blocks': 180, 'color': '#17becf', 'name': 'Trend (6m)', 'weight': 0.2, 'source': '1day', 'show_line': False},
    '1y': {'blocks': 365, 'color': '#bcbd22', 'name': 'Trend (1år)', 'weight': 0.1, 'source': '1day', 'show_line': False},
}

ALERT_THRESHOLDS_UP = sorted([10, 20, 30, 40, 50, 75, 100], reverse=True)
ALERT_THRESHOLDS_DOWN = sorted([-10, -20, -25, -30, -50, -75])
ALERT_PERIODS = ['30m', '1h', '3h', '6h', '12h', '24h']
ALERT_DEBOUNCE_SECONDS = 2 * 3600
TRADE_VALUE_ALERTS = sorted([50, 75, 100, 150], reverse=True)
TRADE_VALUE_DEBOUNCE_SECONDS = 2 * 3600

REDIS_URL = os.environ.get('REDIS_URL')
r = None
if REDIS_URL:
    try:
        r = from_url(REDIS_URL)
        r.ping()
        logger.debug("✅ Ansluten till Redis!")
    except exceptions.ConnectionError as e:
        logger.error(f"❌ Kunde inte ansluta till Redis: {e}")
        r = None

# --- Hjälpfunktioner ---

def get_logo_url(symbol):
    s = symbol.lower()
    if s == 'grass': return "https://cryptologos.cc/logos/grass-grass-logo.png" # Specialfall
    return f"{LOGO_BASE_URL}{s}.png"

def format_price_display(p):
    if p is None: return "N/A"
    price_format = f"{p:,.8f}" if p < 0.1 else (f"{p:,.4f}" if p < 10 else f"{p:,.2f}")
    return price_format.replace(",", "TEMP").replace(".", ",").replace("TEMP", " ")

def get_data_from_redis():
    if r:
        try:
            cached_data = r.get('crypto_data')
            if cached_data: return json.loads(cached_data)
        except: pass
    return None

def calculate_trade_value(short_term_data, current_price_eur, long_term_data=None):
    if not short_term_data or current_price_eur is None: return None, {}
    V = current_price_eur
    trade_value = 0.0
    individual_trends = {}
    for key, config in TREND_WINDOWS.items():
        blocks, weight, source = config['blocks'], config['weight'], config.get('source', '5min')
        hist = short_term_data if source == '5min' else long_term_data
        if not hist or len(hist) < blocks:
            individual_trends[key] = None
            continue
        data_segment = hist[-blocks:]
        x = np.arange(blocks)
        y = np.array([item['price'] for item in data_segment])
        slope, intercept, _, _, _ = linregress(x, y)
        Tx = slope * (blocks - 1) + intercept
        if V != 0:
            Hx = (((Tx - V) / V) * 100) * weight
            trade_value += Hx
            individual_trends[key] = {'val': Hx, 'price': Tx}
    return trade_value, individual_trends

def calculate_trendline(historical_data, blocks):
    if len(historical_data) < 2: return None, None, None
    actual_blocks = min(len(historical_data), blocks)
    data_segment = historical_data[-actual_blocks:]
    x = np.arange(actual_blocks)
    y = np.array([item.get('price', item.get('close')) for item in data_segment])
    slope, intercept, _, _, _ = linregress(x, y)
    return slope, intercept, len(historical_data) - actual_blocks

def fetch_ohlc_data_from_kraken(ticker, interval, periods_ago_seconds):
    time_ago = int(time.time()) - periods_ago_seconds
    try:
        res = requests.get(KRAKEN_OHLC_API_URL, params={'pair': ticker, 'interval': interval, 'since': time_ago}, timeout=10)
        data = res.json()
        if data.get('error'): return []
        key = next(iter(data['result']))
        return [{'time': int(r[0]), 'open': float(r[1]), 'high': float(r[2]), 'low': float(r[3]), 'close': float(r[4]), 'price': float(r[4])} for r in data['result'][key]]
    except: return []

# --- Layout Helpers ---

def format_change(c):
    if c is None: return html.Span("N/A", style={'color': '#6c757d'})
    color = '#28a745' if c > 0 else '#dc3545'
    symbol = '▲' if c > 0 else '▼'
    return html.Span(f"{symbol} {abs(c):.2f}%", style={'color': color, 'fontWeight': 'bold', 'fontSize': '0.85em'})

def format_trade_value_display(v):
    if v is None: return html.Span("N/A", style={'color': '#6c757d'})
    val = int(round(v))
    color = '#006400' if val > 0 else '#8B0000'
    symbol = '▲' if val > 0 else '▼'
    return html.Span(f"{symbol} {abs(val)}", style={'color': color, 'fontWeight': 'bold', 'fontSize': '0.85em'})

def create_summary_row(symbol, label, price, percent_data, trade_value, currency, is_selected, eur_to_sek):
    row_style = {'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center', 'padding': '5px 0', 'borderBottom': '1px solid #eee', 'fontSize': '0.85em', 'cursor': 'pointer', 'backgroundColor': '#fff'}
    if is_selected:
        row_style['backgroundColor'] = '#e6f7ff'
        row_style['border'] = '1px solid #0056b3'
    
    logo = html.Img(src=get_logo_url(symbol), style={'width': '18px', 'height': '18px', 'marginRight': '8px', 'verticalAlign': 'middle'},
                    onError="this.onerror=null;this.src='https://via.placeholder.com/18?text=?';")
    
    return html.Div([
        html.Div([logo, html.Span(label, style={'fontWeight': 'bold', 'color': '#0056b3' if is_selected else '#495057'})], style={'flex': '0 0 160px', 'paddingLeft': '5px'}),
        html.Div(f"{format_price_display(price)}", style={'flex': '0 0 140px', 'textAlign': 'right', 'fontWeight': 'bold', 'paddingRight': '5px'}),
        html.Div(format_change(percent_data.get('30m')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('1h')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('3h')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('24h')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_change(percent_data.get('7d')), style={'flex': '1', 'textAlign': 'right'}),
        html.Div(format_trade_value_display(trade_value), style={'flex': '0 0 80px', 'textAlign': 'right', 'fontWeight': 'bold', 'paddingRight': '5px'}),
    ], id={'type': 'summary-card', 'index': symbol}, style=row_style)

def create_selected_coin_box(label, symbol, price, currency, base_price_eur, high_eur, low_eur, percent_data, trade_value=None, individual_trends=None, diff_24h_eur=None):
    logo = html.Img(src=get_logo_url(symbol), style={'width': '40px', 'height': '40px', 'marginRight': '15px', 'verticalAlign': 'middle'},
                    onError="this.onerror=null;this.src='https://via.placeholder.com/40?text=?';")
    
    return html.Div(id='current-price-box', style={'border': '2px solid #0056b3', 'borderRadius': '10px', 'padding': '15px', 'marginBottom': '20px', 'backgroundColor': '#f8f9fa'}, children=[
        html.Div(style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center', 'marginBottom': '10px'}, children=[
            logo, html.H2(f"{label} ({symbol})", style={'margin': '0', 'color': '#0056b3'})
        ]),
        html.Div(style={'textAlign': 'center'}, children=[
            html.P(f"{format_price_display(price)} {currency}", style={'fontSize': '2.5em', 'fontWeight': '800', 'margin': '0', 'color': '#28a745' if percent_data.get('24h', 0) >=0 else '#dc3545'}),
            html.P(format_change(percent_data.get('24h')), style={'fontSize': '1.2em'})
        ]),
        html.Div(style={'textAlign': 'center', 'marginTop': '10px'}, children=[
            html.Span(f"Handelsvärde: ", style={'color': '#6c757d'}),
            format_trade_value_display(trade_value)
        ])
    ])

# --- Dash App ---

app = dash.Dash(__name__, external_stylesheets=['https://codepen.io/chriddyp/cnWqWbL.css'])
server = app.server

app.layout = html.Div(style={'backgroundColor': '#f8f9fa', 'minHeight': '100vh', 'padding': '40px 10px'}, children=[
    html.Div(style={'maxWidth': '1400px', 'margin': '0 auto', 'padding': '30px', 'borderRadius': '12px', 'backgroundColor': 'white', 'boxShadow': '0 4px 12px rgba(0,0,0,0.1)'}, children=[
        html.H1('📈 DJ-Investment Dashboard (Kraken Live)', style={'textAlign': 'center', 'color': '#0056b3'}),
        
        html.Div(style={'display': 'flex', 'gap': '20px', 'marginBottom': '20px'}, children=[
            html.Div(style={'flex': '0 0 250px'}, children=[
                html.Label("Välj kryptovaluta:", style={'fontWeight': 'bold'}),
                dcc.Dropdown(id='coin-dropdown', options=[{'label': l, 'value': l.split(' ')[0]} for l in COINS_LABELS], value=DEFAULT_COIN_SYMBOL, clearable=False),
                html.Br(),
                html.Label("Basvaluta:", style={'fontWeight': 'bold'}),
                dcc.Dropdown(id='currency-dropdown', options=[{'label': c, 'value': c} for c in BASE_CURRENCIES], value='EUR', clearable=False),
            ]),
            html.Div(style={'flex': '1'}, children=[
                html.Div(id='current-price-summary-box-container'),
                html.Div(id='last-updated', style={'textAlign': 'center', 'color': '#6c757d'})
            ])
        ]),

        html.Div(style={'borderTop': '1px solid #dee2e6', 'paddingTop': '20px'}, children=[
            html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center'}, children=[
                html.Div([
                    html.Label("Visa Trendlinjer:", style={'fontWeight': 'bold', 'marginRight': '10px'}),
                    dcc.Checklist(id='trendline-checkboxes', 
                                 options=[{'label': v['name'], 'value': k} for k, v in TREND_WINDOWS.items() if v['show_line']],
                                 value=[k for k, v in TREND_WINDOWS.items() if v['show_line']], inline=True)
                ]),
                html.Div([
                    html.Label("Live Candlestick:", style={'fontWeight': 'bold', 'marginRight': '10px'}),
                    dcc.Dropdown(id='live-candle-period', options=[{'label': '15m', 'value': 15}, {'label': '30m', 'value': 30}, {'label': '1h', 'value': 60}], value=15, clearable=False, style={'width': '80px', 'display': 'inline-block'})
                ]),
                html.Div([
                    html.Label("Tidsintervall:", style={'fontWeight': 'bold', 'marginRight': '10px'}),
                    dcc.RadioItems(id='graph-timeframe', 
                                  options=[{'label': ' 4h (Live)', 'value': '4h_live'}, {'label': ' 1d', 'value': '1d'}, {'label': ' 1w', 'value': '1w'}, {'label': ' 1m', 'value': '1m'}],
                                  value='4h_live', inline=True)
                ])
            ]),
            dcc.Loading(dcc.Graph(id='live-update-graph', config={'displayModeBar': False}))
        ]),

        html.Div(id='crypto-summary-container', style={'marginTop': '30px'}, children=[
             html.H3('📊 Sammanfattning'),
             dcc.Loading(html.Div(id='crypto-summary'))
        ])
    ]),
    dcc.Interval(id='interval-fast', interval=UPDATE_INTERVAL_FAST*1000),
    dcc.Interval(id='interval-slow', interval=UPDATE_INTERVAL_SLOW*1000),
    dcc.Store(id='chart-data-store'),
    dcc.Store(id='current-currency-store'),
    dcc.Store(id='initial-coin-symbol-store', data=DEFAULT_COIN_SYMBOL),
    dcc.Store(id='table-sort-store', data={'key': 's24h', 'asc': False})
])

# --- Callbacks ---

@app.callback(
    [Output('current-price-summary-box-container', 'children'), 
     Output('last-updated', 'children'),
     Output('chart-data-store', 'data'), 
     Output('current-currency-store', 'data')],
    [Input('interval-fast', 'n_intervals'), 
     Input('coin-dropdown', 'value'), 
     Input('currency-dropdown', 'value'),
     Input('graph-timeframe', 'value'),
     Input('live-candle-period', 'value')]
)
def update_fast_components(n, coin_symbol, currency, timeframe, candle_min):
    data = get_data_from_redis()
    if not data: return html.Div("Laddar..."), "", None, currency
    
    rates = data.get('EXCHANGE_RATES', {})
    eur_to_sek = rates.get('SEK', 11.0)
    coin_label = SYMBOL_TO_LABEL.get(coin_symbol, coin_symbol)
    price_eur = data.get(f'{coin_symbol}/EUR')
    
    # Basvaluta-beräkning
    if currency == 'SEK': price_base = price_eur * eur_to_sek if price_eur else 0
    elif currency == 'USD': price_base = price_eur * rates.get('USD', 1.05) if price_eur else 0
    elif currency in COINS_SYMBOLS:
        cp = data.get(f'{currency}/EUR')
        price_base = price_eur / cp if price_eur and cp else 0
    else: price_base = price_eur

    # OHLC hämta
    ticker = CRYPTO_PAIRS[coin_label]
    if timeframe == '4h_live':
        hist = fetch_ohlc_data_from_kraken(ticker, candle_min, 14400)
    elif timeframe == '1w':
        hist = fetch_ohlc_data_from_kraken(ticker, 60, 604800)
    elif timeframe == '1m':
        hist = fetch_ohlc_data_from_kraken(ticker, 240, 2592000)
    else: # 1d
        hist = fetch_ohlc_data_from_kraken(ticker, 5, 86400)

    trade_val, trends = calculate_trade_value(hist, price_eur, hist)
    
    store = {
        'hist': hist, 'price_eur': price_eur, 'eur_to_sek': eur_to_sek, 
        'base_price_eur': (price_base/price_eur if price_eur else 1),
        'timeframe': timeframe, 'candle_min': candle_min
    }
    
    box = create_selected_coin_box(coin_label, coin_symbol, price_base, currency, 1, 0, 0, data.get('ALL_PERCENT_CHANGE', {}).get(coin_symbol, {}), trade_val)
    time_str = f"Senast uppdaterad: {datetime.now().strftime('%H:%M:%S')}"
    
    return box, time_str, store, currency

@app.callback(
    Output('live-update-graph', 'figure'),
    [Input('chart-data-store', 'data'), Input('current-currency-store', 'data'), Input('trendline-checkboxes', 'value')],
    [State('coin-dropdown', 'value')]
)
def update_graph(store, currency, selected_trends, coin_symbol):
    if not store or not store['hist']: return go.Figure()
    
    hist = store['hist']
    mult = store['base_price_eur']
    timeframe = store['timeframe']
    
    fig = go.Figure()
    
    x = [datetime.fromtimestamp(d['time']) for d in hist]
    close = [d['close'] * mult for d in hist]
    
    if timeframe == '4h_live':
        fig.add_trace(go.Candlestick(x=x, open=[d['open']*mult for d in hist], high=[d['high']*mult for d in hist], low=[d['low']*mult for d in hist], close=close, name='Pris'))
    else:
        fig.add_trace(go.Scatter(x=x, y=close, mode='lines', name='Pris', line=dict(color='#0056b3')))

    # Trendlinjer
    if timeframe == '4h_live' or timeframe == '1w' or timeframe == '1m' or timeframe == '1d':
        slope, intercept, start_idx = calculate_trendline(hist, len(hist))
        if slope is not None:
            trend_y = (slope * np.arange(len(hist)) + intercept) * mult
            fig.add_trace(go.Scatter(x=x, y=trend_y, mode='lines', name='Trend (Period)', line=dict(color='#FFD700', width=2, dash='dot')))

    fig.update_layout(template="plotly_white", height=500, xaxis_rangeslider_visible=False, margin=dict(t=30, b=30, l=30, r=30))
    return fig

@app.callback(
    Output('crypto-summary', 'children'),
    [Input('interval-slow', 'n_intervals'), Input('coin-dropdown', 'value'), Input('currency-dropdown', 'value')]
)
def update_table_slow(n, coin_symbol, currency):
    data = get_data_from_redis()
    if not data: return "Laddar..."
    
    rates = data.get('EXCHANGE_RATES', {})
    eur_to_sek = rates.get('SEK', 11.0)
    
    rows = []
    for label in COINS_LABELS:
        s = label.split(' ')[0]
        p_eur = data.get(f'{s}/EUR')
        p_base = p_eur * eur_to_sek if currency == 'SEK' else p_eur
        
        rows.append(create_summary_row(s, label, p_base, data.get('ALL_PERCENT_CHANGE', {}).get(s, {}), 0, currency, s == coin_symbol, eur_to_sek))
    
    return html.Div(rows)

# --- Start ---
if __name__ == '__main__':
    app.run_server(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 8050)))