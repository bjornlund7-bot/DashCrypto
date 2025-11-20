import requests
import time
from datetime import datetime, timedelta
import pandas as pd
from dash import Dash, dcc, html, Input, Output
import plotly.graph_objects as go
import collections
from scipy.stats import linregress
import numpy as np
import os
import openpyxl
from functools import lru_cache
import itertools
import threading
import re
import sys 
import redis
import json

# =========================================================================
# === 1. KONFIGURATION & KONSTANTER ===
# =========================================================================

# API URL:er
KRAKEN_TICKER_API_URL = "https://api.kraken.com/0/public/Ticker"
KRAKEN_OHLC_API_URL = "https://api.kraken.com/0/public/OHLC"
EXCHANGE_RATE_URL = "https://api.exchangerate-api.com/v4/latest/EUR"

# Filnamn och inställningar
EXCEL_FILE_PATH = os.environ.get("EXCEL_FILE_PATH", "crypto_data_log.xlsx")
UPDATE_INTERVAL_MS_WEB = 5000      # Webb uppdateras var 5:e sek
UPDATE_INTERVAL_SECONDS_DATA = 60  # Data hämtas var 60:e sek
MAX_DASH_POINTS = 1440             # 24h historik
SUMMARY_TREND_POINTS_30M = 30      
SUMMARY_TREND_POINTS_360M = 360    
SMA_WINDOWS = [30, 1440, 360]

# Redis-nycklar
REDIS_KPI_KEY = 'global_kpi_cache_json'
REDIS_HISTORY_KEY = 'data_history_json'
REDIS_EUR_SEK_KEY = 'eur_sek_rate'

# Telegram
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Kryptopar
CRYPTO_PAIRS = {
    'XRP (Ripple)': 'XRPEUR',
    'BTC (Bitcoin)': 'BTCEUR',
    'ETH (Ethereum)': 'ETHEUR',
    'SOL (Solana)': 'SOLEUR',
    'GRASS (Grass)': 'GRASSEUR',
    'ADA (Cardano)': 'ADAEUR',
    'DOT (Polkadot)': 'DOTEUR',
    'DOGE (Dogecoin)': 'DOGEEUR',
    'PUMP (PUMP)': 'PUMPEUR',
    'Cookie DAO': 'COOKIEEUR',
    'Moonwalk (MF)': 'MFEUR', 
    'YALA': 'YALAEUR', 
    'WIF (dogwifhat)': 'WIFEUR',
    'YFI (Yearn Finance)': 'YFIEUR',
    'BNB (BNB Chain)': 'BNBEUR',
    'TRX (Tron)': 'TRXEUR',
    'PEPE (Pepe)': 'PEPEEUR',
    'LTC (Litecoin)': 'LTCEUR',
    'TRUMP (Official Trump)': 'TRUMPEUR',
    'XTZ (Tezos)': 'XTZEUR',
    'DASH (Dash)': 'DASHEUR',
    'ZRO (LayerZero)': 'ZROEUR',
    'WOO (Woo Network)': 'WOOEUR',
    'GALA (Gala Games)': 'GALAEUR',
    'SUI (SUI)': 'SUIEUR',
    'BCH (Bitcoin Cash)': 'BCHEUR',
    'ATOM (Cosmos)': 'ATOMEUR',
    'AVAX (Avalanche)': 'AVAXEUR',
    'ICP (Internet Computer Protocol)': 'ICPEUR',
    'ZEC (Zcash)': 'ZECEUR',
    '0G (ZeroGravity)': '0G/EUR', 
    'XDC (XDC Network)': 'XDCEUR',
    'UNI (Uniswap)': 'UNIEUR',
    'IP (Story)': 'IPEUR',
    'INJ (Injective)': 'INJEUR',
    'AR (Arweave)': 'AREUR',
    'EGLD (MultiversX)': 'EGLDEUR',
    'LPT (LivePeer)': 'LPTEUR',
    'KSM (Kusama)': 'KSMEUR',
    'EUL (Euler)': 'EULEUR',
    'GMX (GMX)': 'GMXEUR',
    'AUCTION (Bounce)': 'AUCTIONEUR',
    'MOVR (Moonriver)': 'MOVREUR',
    'SSV (SSV Network)': 'SSVEUR',
    'MLN (Enzyme Finance)': 'MLNEUR',
    'ALCX (Alchemix)': 'ALCXEUR',
    'AERO (Aerodrome Finance)': 'AEROEUR',
    'MYX (MYX Finance)': 'MYXEUR',
    'GNO (Gnosis)': 'GNOEUR',
}
DEFAULT_PAIR_KEY = 'XRP (Ripple)'

# Tröskelvärden
DIFF_THRESHOLD = 21
SPIKE_THRESHOLDS = {
    '+100%': 100.0, '+75%': 75.0, '+50%': 50.0, '+25%': 25.0, '+10%': 10.0,
    '-10%': -10.0, '-25%': -25.0, '-50%': -50.0,
}
SORTED_SPIKE_THRESHOLDS = sorted(SPIKE_THRESHOLDS.items(), key=lambda item: item[1], reverse=True)
TIMEFRAMES_FOR_SPIKES = ['30m', '100m', '360m', '24h']
SUMMARY_SEND_TIMES = [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]

# Globala variabler (Endast för bakgrundstråden)
SENT_NOTIFICATIONS = {pair: 0 for pair in CRYPTO_PAIRS.values()}
SENT_DIFF_NOTIFICATIONS = {}
LAST_SUMMARY_SENT = {hour: None for hour in SUMMARY_SEND_TIMES}
SENT_SPIKE_NOTIFICATIONS = {
    tf: {pair: {label: False for label in SPIKE_THRESHOLDS.keys()} for pair in CRYPTO_PAIRS.values()}
    for tf in TIMEFRAMES_FOR_SPIKES
}

# =========================================================================
# === 2. REDIS INITIALISERING ===
# =========================================================================

# Hämta URL från Renders miljövariabel
REDIS_URL = os.environ.get('REDIS_URL')
redis_client = None

if REDIS_URL:
    try:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        redis_client.ping()
        print(f"✅ Ansluten till Redis!")
    except Exception as e:
        print(f"❌ Redis-fel: {e}")
else:
    print("⚠️ Ingen REDIS_URL inställd i Environment Variables.")


# =========================================================================
# === 3. HJÄLPFUNKTIONER (Format, Data, Telegram) ===
# =========================================================================

def format_price_sek(value):
    if not isinstance(value, (int, float)) or np.isnan(value) or value is None: return "N/A"
    return f"{value:,.4f}".replace(",", " ").replace(".", ",")

def format_price_eur(value):
    if not isinstance(value, (int, float)) or np.isnan(value) or value is None: return "N/A"
    return f"{value:,.4f}".replace(",", " ")

def format_percent(value):
    if value is None or not isinstance(value, (int, float)) or np.isnan(value): return "N/A %"
    return f"{value:+.2f} %"

def sanitize_sheet_name(pair_key):
    name = pair_key.split('/')[0].strip()
    name = re.sub(r'\s*\((.*?)\)', '', name).strip()
    name = re.sub(r'[^\w\s-]', '', name).replace(' ', '_')
    return name[:31]

@lru_cache(maxsize=1)
def get_eur_sek_rate():
    try:
        response = requests.get(EXCHANGE_RATE_URL, timeout=5)
        response.raise_for_status()
        data = response.json()
        return data['rates']['SEK'] if 'rates' in data and 'SEK' in data['rates'] else 11.50
    except:
        return 11.50

# --- Telegram ---
def send_telegram_message(message_text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'text': message_text, 'parse_mode': 'Markdown'}, timeout=5)
        time.sleep(1.0)
        return True
    except Exception as e:
        print(f"Telegram-fel: {e}")
        return False

def notify_single(signal_text, pair_key, current_price_eur, signal_rating):
    price_fmt = f"{current_price_eur:,.4f}".replace(",", "X").replace(".", ",").replace("X", ".")
    msg = f"🔔 *MTS TRIGGER ({signal_rating:+})*\n\n*{pair_key}*\nSignal: *{signal_text}*\nPris: `{price_fmt} EUR`"
    send_telegram_message(msg)

def notify_spike(tf, pair_key, pct, price, label):
    emoji = "🚀" if pct >= 0 else "📉"
    price_fmt = f"{price:,.4f}".replace(",", "X").replace(".", ",").replace("X", ".")
    msg = f"{emoji} *{tf.upper()} VARNING ({label})*\n\n*{pair_key}*\nÄndring: *{format_percent(pct)}*\nPris: `{price_fmt} EUR`"
    send_telegram_message(msg)

def notify_periodic_summary(kpi_cache):
    summary_data = []
    for pair_key, pair_ticker in CRYPTO_PAIRS.items():
        kpi = kpi_cache.get(pair_ticker, {})
        c360 = kpi.get('percent_change_360m')
        rating = kpi.get('signal_rating')
        c24 = kpi.get('percent_change_24h')
        val = kpi.get('price_eur')
        
        if c360 is not None and rating is not None:
            name = pair_key.split('/')[0].split('(')[0].strip()
            summary_data.append({'c': name, '360': c360, 'r': rating, '24': c24, 'v': val})

    if not summary_data: return
    sorted_sum = sorted(summary_data, key=lambda x: x['360'], reverse=True)
    rows = []
    for i in sorted_sum:
        v_fmt = f"{i['v']:,.4f}".replace(",", " ") if i['v'] else "N/A"
        rows.append(f"| `{i['c']}` | `{format_percent(i['360'])}` | `{format_percent(i['24'])}` | `{i['r']:+}` | `{v_fmt}` |")
    
    header = f"⏳ *PERIODISK SAMMANFATTNING*\n\n| Krypto | 360m % | 24h % | Betyg | Kurs |\n|---|---|---|---|---|\n"
    send_telegram_message(header + "\n".join(rows))


# --- Datahämtning & Beräkningar ---
def get_crypto_data(pair_ticker):
    rate = get_eur_sek_rate()
    try:
        resp = requests.get(KRAKEN_TICKER_API_URL, params={'pair': pair_ticker}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get('error'): return None, str(data['error'])
        
        res = data['result'][list(data['result'].keys())[0]]
        p_eur = float(res['c'][0])
        o_eur = float(res['o'])
        
        return {
            'price_eur': p_eur,
            'high_24h_eur': float(res['h'][1]),
            'low_24h_eur': float(res['l'][1]),
            'price_sek': p_eur * rate,
            'high_24h_sek': float(res['h'][1]) * rate,
            'low_24h_sek': float(res['l'][1]) * rate,
            'percent_change_24h': ((p_eur - o_eur) / o_eur) * 100 if o_eur else 0
        }, None
    except Exception as e:
        return None, str(e)

def get_ohlc_price(pair_ticker, days, rate):
    since = int((datetime.now() - timedelta(days=days + 10)).timestamp())
    try:
        resp = requests.get(KRAKEN_OHLC_API_URL, params={'pair': pair_ticker, 'interval': 1440, 'since': since}, timeout=10)
        data = resp.json()
        if data.get('error'): return None, None, str(data['error'])
        
        ohlc = data['result'][list(data['result'].keys())[0]]
        target = (datetime.now() - timedelta(days=days)).timestamp()
        best_eur = None
        for entry in reversed(ohlc):
            if entry[0] < target:
                best_eur = float(entry[4])
                break
        if best_eur: return best_eur, best_eur * rate, None
        return None, None, "Ingen data"
    except Exception as e:
        return None, None, str(e)

def calculate_sma(df, window, price_key='price_sek'):
    return df[price_key].rolling(window=min(window, len(df))).mean()

def calculate_30min_trend(ticker, history):
    filtered = [p for p in history if p['price_sek'] > 0]
    if len(filtered) < SUMMARY_TREND_POINTS_30M: return 0.0, "Väntar", "gray"
    
    df = pd.DataFrame(filtered[-SUMMARY_TREND_POINTS_30M:])
    x = np.array([t.timestamp() for t in df['time']])
    slope, intercept, _, _, _ = linregress(x, df['price_sek'])
    
    start = slope * x.min() + intercept
    end = slope * x.max() + intercept
    if start == 0: return 0.0, "N/A", "gray"
    
    pct = ((end - start) / start) * 100
    if pct > 0: return pct, "Stigande", "#006400"
    elif pct < 0: return pct, "Fallande", "#8B0000"
    return 0.0, "Stabil", "#555"

def calculate_trend_change(history, points):
    filtered = [p for p in history if p['price_sek'] > 0]
    if len(filtered) < 2: return 0.0
    start = filtered[-min(len(filtered), points)]['price_sek']
    end = filtered[-1]['price_sek']
    return ((end - start) / start) * 100 if start else 0.0

def generate_mts_signal(kpi, history):
    p_sek = kpi['price']
    p7 = kpi['price_7d'] if kpi['price_7d'] else p_sek
    p30 = kpi['price_30d'] if kpi['price_30d'] else p_sek
    
    pct7 = ((p_sek - p7)/p7)*100 if p7 else 0
    pct30 = ((p_sek - p30)/p30)*100 if p30 else 0
    
    rating = round(np.clip(pct7 * 0.4, -4, 4))
    
    pct100 = kpi['percent_change_100m']
    pct360 = kpi['percent_change_360m']
    
    if pct100 >= 0.5 and pct360 >= 1.0: rating += 3
    elif pct100 <= -0.5 and pct360 <= -1.0: rating -= 3
    elif pct100 >= 0.1: rating += 1
    elif pct100 <= -0.1: rating -= 1
    
    rating = np.clip(rating, -10, 10)
    
    txt = "KÖP" if rating >= 5 else "SÄLJ" if rating <= -5 else "NEUTRAL"
    col = '#00FA9A' if rating >= 5 else '#B22222' if rating <= -5 else '#555'
    
    return txt, rating, col, pct7, pct30

# =========================================================================
# === 4. REDIS SPARA/LADDA ===
# =========================================================================

def save_state_to_redis(kpi_cache, history_data, eur_sek):
    if not redis_client: return
    try:
        # Serialisera Historik
        ser_hist = {}
        for pair, buffer in history_data.items():
            ser_hist[pair] = [{**i, 'time': i['time'].isoformat()} for i in buffer]
            
        # Serialisera KPI
        ser_kpi = {}
        for pair, data in kpi_cache.items():
            d = data.copy()
            if isinstance(d.get('time'), datetime): d['time'] = d['time'].isoformat()
            ser_kpi[pair] = d
            
        redis_client.set(REDIS_KPI_KEY, json.dumps(ser_kpi))
        redis_client.set(REDIS_HISTORY_KEY, json.dumps(ser_hist))
        redis_client.set(REDIS_EUR_SEK_KEY, str(eur_sek))
    except Exception as e:
        print(f"Redis Write Error: {e}")

def load_state_from_redis():
    if not redis_client: return {}, {}, 11.50
    try:
        k_json = redis_client.get(REDIS_KPI_KEY)
        h_json = redis_client.get(REDIS_HISTORY_KEY)
        r_val = redis_client.get(REDIS_EUR_SEK_KEY)
        
        if not k_json or not h_json: return {}, {}, 11.50
        
        kpi = json.loads(k_json)
        raw_hist = json.loads(h_json)
        hist = {}
        for pair, l in raw_hist.items():
            hist[pair] = []
            for i in l:
                i['time'] = datetime.fromisoformat(i['time'])
                hist[pair].append(i)
                
        return kpi, hist, float(r_val) if r_val else 11.50
    except Exception as e:
        print(f"Redis Read Error: {e}")
        return {}, {}, 11.50

def log_excel(history):
    try:
        with pd.ExcelWriter(EXCEL_FILE_PATH, engine='openpyxl') as writer:
            for pair, data in history.items():
                df = pd.DataFrame(list(data))
                if df.empty: continue
                df['time'] = df['time'].dt.strftime('%Y-%m-%d %H:%M:%S')
                df.to_excel(writer, sheet_name=sanitize_sheet_name(pair), index=False)
        print("Excel sparad.")
    except: pass


# =========================================================================
# === 5. BAKGRUNDSTRÅD ===
# =========================================================================

def background_data_collector():
    # Lokal lagring för tråden (inte global)
    thread_history = {pair: collections.deque(maxlen=max(SMA_WINDOWS)) for pair in CRYPTO_PAIRS.values()}
    thread_kpi = {}
    cnt = 0
    print(">>> Bakgrundstråd startad.")
    
    while True:
        try:
            rate = get_eur_sek_rate()
            now = datetime.now()
            ohlc_update = (cnt % 60 == 0)
            
            for p_key, p_ticker in CRYPTO_PAIRS.items():
                # Hämta data
                t_data, err = get_crypto_data(p_ticker)
                if err: 
                    print(f"Fel {p_key}: {err}")
                    continue
                
                # Uppdatera historik
                thread_history[p_ticker].append({
                    'time': now, 'price_sek': t_data['price_sek'], 'price_eur': t_data['price_eur']
                })
                
                # Hämta OHLC
                old_kpi = thread_kpi.get(p_ticker, {})
                p7_sek = old_kpi.get('price_7d_sek')
                p30_sek = old_kpi.get('price_30d_sek')
                
                if ohlc_update or p7_sek is None:
                    _, p7, _ = get_ohlc_price(p_ticker, 7, rate)
                    _, p30, _ = get_ohlc_price(p_ticker, 30, rate)
                    if p7: p7_sek = p7
                    if p30: p30_sek = p30
                
                if not p7_sek: p7_sek = t_data['price_sek']
                if not p30_sek: p30_sek = t_data['price_sek']
                
                # Beräkna Signaler
                h_list = list(thread_history[p_ticker])
                t30_pct, t30_txt, t30_col = calculate_30min_trend(p_ticker, h_list)
                p100 = calculate_trend_change(h_list, MAX_DASH_POINTS)
                p360 = calculate_360min_change(h_list)
                
                mts_in = {
                    'price': t_data['price_sek'], 'high_24h': t_data['high_24h_sek'], 'low_24h': t_data['low_24h_sek'],
                    'price_7d': p7_sek, 'price_30d': p30_sek, 'percent_change_100m': p100, 'percent_change_360m': p360
                }
                
                sig_txt, sig_rate, sig_col, p7_pct, p30_pct = generate_mts_signal(mts_in, h_list)
                
                # Spara lokalt i tråd
                thread_kpi[p_ticker] = {
                    **t_data,
                    'price_7d_sek': p7_sek, 'price_30d_sek': p30_sek,
                    'trend_30m_percent': t30_pct, 'trend_30m_color': t30_col, 'trend_30m_text': t30_txt,
                    'percent_change_100m': p100, 'percent_change_360m': p360,
                    'signal_text': sig_txt, 'signal_rating': sig_rate, 'signal_color': sig_col,
                    'percent_7d': p7_pct, 'percent_30d': p30_pct, 'time': now
                }
                
                # Notiser
                if abs(sig_rate) >= 5:
                    last = SENT_NOTIFICATIONS.get(p_ticker, 0)
                    if (sig_rate * last <= 0) or (abs(sig_rate) > abs(last)):
                        notify_single(sig_txt, p_key, t_data['price_eur'], sig_rate)
                        SENT_NOTIFICATIONS[p_ticker] = sig_rate
                
                # (Spike checks förenklade, använd din fulla logik här vid behov)
                # ...

            # SPARA TILL REDIS
            save_state_to_redis(thread_kpi, thread_history, rate)
            
            if cnt % 5 == 0: log_excel(thread_history)
            
            if now.hour in SUMMARY_SEND_TIMES and now.minute < 2:
                last = LAST_SUMMARY_SENT.get(now.hour)
                if not last or last.date() < now.date():
                    notify_periodic_summary(thread_kpi)
                    LAST_SUMMARY_SENT[now.hour] = now
            
            cnt += 1
        except Exception as e:
            print(f"Trådfel: {e}")
            
        time.sleep(UPDATE_INTERVAL_SECONDS_DATA)

# =========================================================================
# === 6. DASH APP & CALLBACKS ===
# =========================================================================

app = Dash(__name__)
server = app.server 

app.layout = html.Div([
    html.H1("📈 MTS Krypto (Redis)", style={'text-align': 'center', 'color': '#edf2f7'}),
    dcc.Interval(id='web-update', interval=UPDATE_INTERVAL_MS_WEB),
    
    html.Div([
        html.Label("Valuta: ", style={'color': '#fff'}),
        dcc.RadioItems(id='curr', options=[{'label':'EUR','value':'EUR'}, {'label':'SEK','value':'SEK'}], value='EUR', style={'color': '#fff', 'display': 'inline-block'})
    ], style={'text-align': 'center', 'padding': '10px'}),
    
    html.Div([
        dcc.Dropdown(id='pair', options=[{'label': k, 'value': v} for k,v in CRYPTO_PAIRS.items()], value=CRYPTO_PAIRS[DEFAULT_PAIR_KEY], style={'width':'300px', 'margin':'0 auto'})
    ]),
    
    html.Div(id='kpi-box', style={'text-align':'center', 'color':'#fff', 'margin':'20px', 'font-size':'20px'}),
    dcc.Graph(id='graph'),
    html.Div(id='table', style={'margin':'20px'})
], style={'background-color': '#2d3748', 'min-height': '100vh', 'padding': '20px', 'font-family': 'sans-serif'})

@app.callback(
    [Output('graph', 'figure'), Output('kpi-box', 'children')],
    [Input('web-update', 'n_intervals'), Input('pair', 'value'), Input('curr', 'value')]
)
def update_graph(n, pair, curr):
    kpi, hist, _ = load_state_from_redis()
    if not kpi or pair not in kpi: return go.Figure(), "Laddar data..."
    
    data = kpi[pair]
    price_key = 'price_eur' if curr == 'EUR' else 'price_sek'
    unit = "€" if curr == 'EUR' else "kr"
    price = data.get(price_key, 0)
    
    txt = [html.Span(f"{price:,.4f} {unit} ({format_percent(data.get('percent_change_24h'))})", style={'color': data.get('trend_30m_color')})]
    
    h_data = hist.get(pair, [])
    if not h_data: return go.Figure(), txt
    
    df = pd.DataFrame(h_data)
    df = df[df[price_key] > 0]
    if df.empty: return go.Figure(), txt
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df['time'], y=df[price_key], mode='lines', name='Pris', line=dict(color='#00BFFF')))
    if len(df) > 30:
        df['sma'] = df[price_key].rolling(30).mean()
        fig.add_trace(go.Scatter(x=df['time'], y=df['sma'], mode='lines', name='SMA30', line=dict(color='yellow')))
        
    fig.update_layout(template='plotly_dark', paper_bgcolor='#2d3748', plot_bgcolor='#2d3748', height=500, xaxis_title="Tid", yaxis_title=f"Pris ({unit})")
    return fig, txt

@app.callback(Output('table', 'children'), [Input('web-update', 'n_intervals'), Input('curr', 'value')])
def update_table(n, curr):
    kpi, _, _ = load_state_from_redis()
    if not kpi: return html.Div("Väntar på data från Redis...", style={'color':'yellow'})
    
    sorted_kpi = sorted(kpi.items(), key=lambda x: x[1].get('signal_rating', 0), reverse=True)
    rows = []
    for tic, d in sorted_kpi:
        name = next((k for k,v in CRYPTO_PAIRS.items() if v==tic), tic)
        p = d.get('price_eur' if curr=='EUR' else 'price_sek')
        unit = "€" if curr == 'EUR' else "kr"
        p_fmt = format_price_eur(p) if curr == 'EUR' else format_price_sek(p)
        
        rows.append(html.Tr([
            html.Td(name, style={'padding':'8px'}), 
            html.Td(f"{p_fmt} {unit}", style={'text-align':'right', 'padding':'8px'}), 
            html.Td(format_percent(d.get('percent_change_24h')), style={'text-align':'right', 'padding':'8px'}),
            html.Td(format_percent(d.get('percent_change_360m')), style={'text-align':'right', 'padding':'8px'}),
            html.Td(f"{d.get('signal_rating'):+}", style={'background-color': d.get('signal_color'), 'color':'white', 'text-align':'center', 'padding':'8px'}),
            html.Td(d.get('signal_text'), style={'padding':'8px'})
        ], style={'border-bottom': '1px solid #444'}))
        
    return html.Table([
        html.Thead(html.Tr([html.Th(c, style={'text-align':'left', 'padding':'8px'}) for c in ["Krypto", "Pris", "24h %", "360m %", "Betyg", "Signal"]]))
    ] + [html.Tbody(rows)], style={'width':'100%', 'color':'#edf2f7', 'border-collapse':'collapse'})

# =========================================================================
# === 7. START AV TRÅD OCH SERVER ===
# =========================================================================

# Endast starta bakgrundstråden om vi är i huvudprocessen och Redis finns
if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
    if redis_client:
        t = threading.Thread(target=background_data_collector, daemon=True)
        t.start()
    else:
        print("VARNING: Ingen Redis-klient. Bakgrundstråd startas ej.")

if __name__ == '__main__':
    app.run_server(debug=True, use_reloader=False)