import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objects as go
import time
import threading
import os
import requests
import json
import logging
from redis import from_url, exceptions

# --- Konfiguration och Initialisering ---

# Konfigurera loggning för att se alla debug-meddelanden
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

# Hämta Redis URL från miljön (Render)
REDIS_URL = os.environ.get('REDIS_URL')

if REDIS_URL:
    try:
        r = from_url(REDIS_URL)
        r.ping()
        logger.debug("✅ Ansluten till Redis!")
    except exceptions.ConnectionError as e:
        logger.error(f"❌ Kunde inte ansluta till Redis: {e}")
        r = None
else:
    logger.warning("REDIS_URL hittades inte. Appen kommer inte att cache:a data.")
    r = None

# Standardvärden om data saknas
DEFAULT_DATA = {
    'XRP/EUR': 0.40,
    'XRP/SEK': 4.50,
    'timestamp': time.time()
}
DEFAULT_TTL = 3600  # 1 timme

# --- Bakgrundstrådens Logik (Datahämtning) ---

def fetch_crypto_data():
    """Simulerar hämtning av krypto-data från en extern API (t.ex. CoinGecko)."""
    try:
        # Ersätt detta med din faktiska API-kod om du har en
        # Exempel på en enkel mock-implementation för att säkerställa att tråden fungerar:
        
        # Simulerar prissvängningar baserat på tid
        current_price_eur = 0.52 + (0.01 * (time.time() % 60) / 60)
        sek_rate = 11.5 
        
        data = {
            'XRP/EUR': current_price_eur,
            'XRP/SEK': current_price_eur * sek_rate,
            'timestamp': time.time()
        }
        return data

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ API-fel vid hämtning av data: {e}. Använder standardvärden.")
        return DEFAULT_DATA # Återgår till standarddata vid API-fel
    except Exception as e:
        logger.error(f"❌ Oväntat fel i datahämtning: {e}")
        return DEFAULT_DATA

def update_redis_cache(redis_instance):
    """Loop som körs i bakgrunden för att uppdatera Redis-cachen."""
    while True:
        try:
            logger.debug("--- Bakgrundstråd: Hämtar ny data ---")
            
            new_data = fetch_crypto_data()
            
            if redis_instance:
                data_json = json.dumps(new_data)
                # Spara data, cachad i 60 sekunder
                redis_instance.set('crypto_data', data_json, ex=60) 
                
                timestamp_str = time.strftime("%H:%M:%S", time.gmtime(new_data['timestamp']))
                logger.debug(f"✅ Data sparad i Redis. XRP/EUR: {new_data['XRP/EUR']:.4f}. Uppdaterad: {timestamp_str} UTC")
            else:
                logger.warning("Redis är inte initialiserad. Hoppar över cachelagring.")

        except Exception as e:
            # Fånga alla fel för att förhindra att tråden dör
            logger.error(f"❌ Kritisk fel i bakgrundstråd: {e}. Fortsätter efter 30s.")
            
        # Vänta 30 sekunder innan nästa körning
        time.sleep(30)


# Starta bakgrundstråden om Redis är ansluten
if r:
    worker_thread = threading.Thread(target=update_redis_cache, args=(r,), daemon=True)
    worker_thread.start()
    logger.debug(">>> Bakgrundstråd startad och snurrar!")
    logger.debug("Startkommando för tråd skickat.")

# --- Dash Applikation ---

app = dash.Dash(__name__, external_stylesheets=['https://codepen.io/chriddyp/pen/bWLwgP.css'])
server = app.server

app.layout = html.Div(style={'maxWidth': '800px', 'margin': 'auto', 'padding': '20px', 'fontFamily': 'Arial, sans-serif'}, children=[
    html.H1('📈 MTS Krypto (Redis)', style={'textAlign': 'center', 'color': '#007BFF'}),

    html.Div([
        html.P("Valuta:", style={'display': 'inline-block', 'marginRight': '10px'}),
        dcc.Dropdown(
            id='currency-dropdown',
            options=[
                {'label': 'Euro (EUR)', 'value': 'EUR'},
                {'label': 'Svenska Kronor (SEK)', 'value': 'SEK'},
            ],
            value='EUR',
            style={'width': '150px', 'display': 'inline-block', 'verticalAlign': 'middle'}
        ),
    ], style={'textAlign': 'center', 'marginBottom': '20px'}),

    html.Div(id='current-price', style={'textAlign': 'center', 'fontSize': '2em', 'fontWeight': 'bold', 'color': '#28A745', 'marginBottom': '10px'}),
    html.Div(id='last-updated', style={'textAlign': 'center', 'fontSize': '0.8em', 'color': '#6C757D', 'marginBottom': '20px'}),
    
    dcc.Loading(
        id="loading-1",
        type="default",
        children=[
            dcc.Graph(id='live-update-graph')
        ]
    ),

    # Intervallkomponent för att uppdatera frontend (var 5:e sekund)
    dcc.Interval(
        id='interval-component',
        interval=5*1000, # 5 sekunder
        n_intervals=0
    )
])

# --- Callbacks ---

def get_data_from_redis():
    """Hämtar data från Redis eller standarddata om cachen är tom."""
    if r:
        try:
            cached_data = r.get('crypto_data')
            if cached_data:
                return json.loads(cached_data)
            else:
                logger.warning("Cache är tom. Väntar på bakgrundstråd.")
                return None
        except exceptions.ConnectionError as e:
            logger.error(f"Redis-anslutningsfel i callback: {e}")
            return None
    return None

@app.callback(Output('current-price', 'children'),
              Output('last-updated', 'children'),
              Output('live-update-graph', 'figure'),
              [Input('interval-component', 'n_intervals'),
               Input('currency-dropdown', 'value')])
def update_metrics_and_graph(n, currency):
    data = get_data_from_redis()
    
    if data is None:
        # Visa laddningsmeddelande om cachen är tom
        price_text = "Laddar data..."
        updated_text = "Väntar på data från Redis..."
        figure = go.Figure(go.Scatter(x=[0], y=[0], mode='text', text=['Laddar...']))
        figure.update_layout(title="Hämtar data...")
        return price_text, updated_text, figure

    # Extrahera data
    price_key = f'XRP/{currency}'
    current_price = data.get(price_key, DEFAULT_DATA.get(price_key))
    timestamp = data.get('timestamp', DEFAULT_DATA['timestamp'])
    
    # Pris och Uppdateringstid
    price_text = f"XRP (Ripple): {current_price:.4f} {currency}"
    updated_text = f"Senast uppdaterad: {time.strftime('%H:%M:%S', time.gmtime(timestamp))} UTC"

    # Skapa graf (simulerad historik för demo)
    # I en riktig app skulle du lagra historiska data i Redis också.
    
    # Skapa en enkel simulerad historik baserat på den aktuella tiden
    # Skalan kommer att vara flytande men visa en trend
    time_series = [timestamp - (i * 300) for i in range(10, 0, -1)] + [timestamp]
    price_series = [current_price * (1 + 0.005 * i / 10 - 0.002) for i in range(11)]
    
    figure = go.Figure()
    figure.add_trace(go.Scatter(
        x=[time.strftime('%H:%M:%S', time.gmtime(t)) for t in time_series],
        y=[p for p in price_series],
        mode='lines+markers',
        name='XRP Pris',
        line=dict(color='#007BFF', width=3),
        marker=dict(size=8, color='#28A745')
    ))

    figure.update_layout(
        title=f'XRP Prisutveckling ({currency})',
        xaxis_title="Tid (UTC)",
        yaxis_title=f"Pris ({currency})",
        template="plotly_white",
        margin=dict(l=40, r=40, t=40, b=40),
        height=400
    )
    
    return price_text, updated_text, figure

if __name__ == '__main__':
    # Detta block körs inte på Render (Gunicorn kör servern), men behålls för lokal testning
    # För lokal testning: app.run_server(debug=True)
    pass