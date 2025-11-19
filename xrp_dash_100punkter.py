import requests
import time
from datetime import datetime, timedelta
import pandas as pd
from dash import Dash, dcc, html, Input, Output
import plotly.graph_objects as go
import collections
import os
from scipy.stats import linregress
import numpy as np

# --- Konstanter ---
KRAKEN_TICKER_API_URL = "https://api.kraken.com/0/public/Ticker"
KRAKEN_OHLC_API_URL = "https://api.kraken.com/0/public/OHLC"
KRAKEN_PAIR = 'XRPEUR'
EXCHANGE_RATE_URL = "https://api.exchangerate-api.com/v4/latest/EUR"

# Filnamn för permanent datalagring (lagras i samma katalog som skriptet körs)
CSV_FILE_PATH = 'xrp_data_log.csv'

# Inställningar för Dash
UPDATE_INTERVAL_MS = 60000    # Uppdateringsfrekvens i millisekunder (60 sekunder)
MAX_DASH_POINTS = 100         # Max antal datapunkter att visa i Dash-grafiken (100 minuter historik)

# Globalt lagringsutrymme för Dash-historik (visuell, temporär)
data_history = collections.deque(maxlen=MAX_DASH_POINTS)

# --- Funktioner för Datahantering ---

def load_historical_data():
    """Laddar de senaste MAX_DASH_POINTS från CSV-filen vid start."""
    global data_history
    
    if os.path.exists(CSV_FILE_PATH):
        try:
            df = pd.read_csv(CSV_FILE_PATH)
            
            if len(df) > MAX_DASH_POINTS:
                df = df.tail(MAX_DASH_POINTS)
            
            for index, row in df.iterrows():
                time_obj = datetime.strptime(row['time'], "%Y-%m-%d %H:%M:%S")
                data_history.append({'time': time_obj, 'price_sek': row['price_sek']})
                
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Laddade {len(data_history)} historiska datapunkter från CSV.")
            
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Varning: Kunde inte läsa historik från CSV: {e}")
            
    if not data_history:
        data_history.append({'time': datetime.now() - timedelta(minutes=MAX_DASH_POINTS), 'price_sek': 0.0})


def get_eur_sek_rate():
    """Hämtar aktuell EUR/SEK växelkurs. Använder 11.50 SEK som fallback."""
    try:
        response = requests.get(EXCHANGE_RATE_URL, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if 'rates' in data and 'SEK' in data['rates']:
            return data['rates']['SEK']
        return 11.50
            
    except requests.exceptions.RequestException:
        return 11.50
    except Exception:
        return 11.50

def get_ohlc_price(since_days_ago, eur_sek_rate):
    """
    Hämtar historiskt slutpris (stängningspris) från Kraken OHLC API.
    """
    since_time = datetime.now() - timedelta(days=since_days_ago)
    since_unix = int((since_time - timedelta(days=10)).timestamp())
    
    params = {
        'pair': KRAKEN_PAIR,
        'interval': 1440,
        'since': since_unix
    }
    
    try:
        response = requests.get(KRAKEN_OHLC_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('error') and data['error']:
            return None, f"OHLC Fel: {data['error']}"

        kraken_pair_key = list(data['result'].keys())[0]
        ohlc_data = data['result'][kraken_pair_key]

        target_timestamp = since_time.timestamp()
        best_match_price_eur = None

        for entry in reversed(ohlc_data):
            timestamp = entry[0]
            if timestamp < target_timestamp:
                best_match_price_eur = float(entry[4])
                break

        if best_match_price_eur is not None:
            return best_match_price_eur * eur_sek_rate, None
        
        return None, f"Ingen tillförlitlig OHLC-data hittades före {since_days_ago} dagar sedan."

    except Exception as e:
        return None, f"Fel vid hämtning av OHLC-data: {e}"

def get_xrp_sek_data():
    """Hämtar Aktuellt pris och beräknar %-ändringar."""
    
    eur_sek_rate = get_eur_sek_rate()
    
    # --- 2. Hämta Ticker-data för 24h KPI:er och aktuellt pris ---
    try:
        params = {'pair': KRAKEN_PAIR}
        response = requests.get(KRAKEN_TICKER_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get('error') and data['error']:
            return None, f"Ticker Fel: {data['error']}"

        if data.get('result'):
            kraken_pair_key = list(data['result'].keys())[0]
            result = data['result'][kraken_pair_key]
            
            latest_price_eur = float(result['c'][0]) 
            open_24h_eur = float(result['o']) 
            
            price_sek = latest_price_eur * eur_sek_rate
            high_sek = float(result['h'][1]) * eur_sek_rate
            low_sek = float(result['l'][1]) * eur_sek_rate
            open_sek = open_24h_eur * eur_sek_rate
            
            percent_change_24h = ((price_sek - open_sek) / open_sek) * 100 if open_sek != 0 else 0

        else:
            return None, f"Fick ett tomt Ticker-resultat."

    except Exception as e:
        return None, f"Fel vid hämtning av Ticker-data: {e}"

    # --- 3. Hämta historiska priser för 7 dagar och 30 dagar ---
    
    price_7d_ago, error_7d = get_ohlc_price(7, eur_sek_rate)
    price_30d_ago, error_30d = get_ohlc_price(30, eur_sek_rate)
    
    if price_7d_ago is not None and price_7d_ago != 0:
        percent_change_7d = ((price_sek - price_7d_ago) / price_7d_ago) * 100
    else:
        print(f"Varning: Kunde inte hämta 7d data. {error_7d}")
        percent_change_7d = 0.0
        
    if price_30d_ago is not None and price_30d_ago != 0:
        percent_change_30d = ((price_sek - price_30d_ago) / price_30d_ago) * 100
    else:
        print(f"Varning: Kunde inte hämta 30d data. {error_30d}")
        percent_change_30d = 0.0

    return {
        'price': price_sek, 
        'high_24h': high_sek, 
        'low_24h': low_sek,
        'percent_change_24h': percent_change_24h,
        'percent_change_7d': percent_change_7d,
        'percent_change_30d': percent_change_30d
    }, None

def append_to_csv(data_point):
    """Lägger till en ny datapunkt i CSV-filen."""
    try:
        new_df = pd.DataFrame([data_point])
        
        if os.path.exists(CSV_FILE_PATH):
            new_df.to_csv(CSV_FILE_PATH, mode='a', index=False, header=False)
        else:
            new_df.to_csv(CSV_FILE_PATH, mode='w', index=False, header=True)
            
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] FEL vid skrivning till CSV: {e}")

# --- Dash Applikation ---

app = Dash(__name__)

app.layout = html.Div(
    style={'backgroundColor': '#111111', 'color': '#FFFFFF', 'padding': '20px', 'fontFamily': 'Arial, sans-serif'},
    children=[
        html.H1(children='XRP/SEK Realtidsspårare',
                style={'textAlign': 'center', 'color': '#00BFFF'}),
        
        # Aktuellt pris
        html.Div(id='current-price-display', style={'textAlign': 'center', 'fontSize': '40px', 'marginBottom': '10px', 'fontWeight': 'bold', 'color': '#FFFFFF'}),
        
        # KPI-display container
        html.Div(id='kpi-display', style={
            'display': 'flex',
            'justifyContent': 'space-around',
            'marginBottom': '30px',
            'padding': '10px',
        }),
        
        # Komponenten som kommer att visa diagrammet
        dcc.Graph(id='live-update-graph', config={'displayModeBar': False}),
        
        # Komponenten som triggar uppdateringen
        dcc.Interval(
            id='interval-component',
            interval=UPDATE_INTERVAL_MS,
            n_intervals=0
        )
    ]
)

# Hjälpfunktion för att skapa KPI-kort
def create_kpi_card(title, value, unit, is_percent=False):
    """Skapar en stiliserad KPI-kortkomponent."""
    
    if is_percent:
        color = '#3CB371' if value >= 0 else '#FF6347'
        arrow = '▲' if value >= 0 else '▼'
        display_value = f"{arrow} {value:+.2f}{unit}"
        value_style = {'fontSize': '24px', 'fontWeight': 'bold', 'color': color, 'margin': '5px 0'}
    else:
        display_value = f"{value:.4f} {unit}"
        value_style = {'fontSize': '24px', 'fontWeight': 'bold', 'color': '#FFFFFF', 'margin': '5px 0'}

    return html.Div(
        style={
            'backgroundColor': '#1E1E1E',
            'padding': '15px',
            'borderRadius': '8px',
            'textAlign': 'center',
            'width': '20%',
            'boxShadow': '0 4px 8px rgba(0, 0, 0, 0.2)'
        },
        children=[
            html.P(title, style={'fontSize': '14px', 'color': '#BBBBBB', 'margin': '0 0 5px 0'}),
            html.P(display_value, style=value_style)
        ]
    )


# CALLBACK: Funktion som körs varje gång dcc.Interval tickar
@app.callback(
    [Output('live-update-graph', 'figure'),
     Output('current-price-display', 'children'),
     Output('kpi-display', 'children')],
    [Input('interval-component', 'n_intervals')]
)
def update_graph_live(n):
    
    price_data, error = get_xrp_sek_data()
    
    if error:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] FEL: {error}")
        return (
            go.Figure(layout=go.Layout(plot_bgcolor='#111111', paper_bgcolor='#111111')), 
            f"Fel vid hämtning: {error}", 
            html.Div("KPI-data ej tillgänglig på grund av API-fel.", style={'color': '#FF6347', 'textAlign': 'center'})
        )
    
    if price_data is not None:
        
        price_sek = price_data['price']
        high_sek = price_data['high_24h']
        low_sek = price_data['low_24h']
        
        percent_24h = price_data['percent_change_24h']
        percent_7d = price_data['percent_change_7d']
        percent_30d = price_data['percent_change_30d']
        
        current_time = datetime.now()
        
        # 1. Lagra data permanent (CSV)
        new_data_point_csv = {
            'time': current_time.strftime("%Y-%m-%d %H:%M:%S"),
            'price_sek': price_sek
        }
        append_to_csv(new_data_point_csv)
        
        # 2. Lagra data temporärt (Dash-historik)
        data_history.append({'time': current_time, 'price_sek': price_sek}) 

        # 3. Skapa DataFrame och Figur (Graf)
        df = pd.DataFrame(list(data_history))
        
        # Kalkylera den linjära trenden (Regression)
        trend_trace = None
        if len(df) >= 2:
            x_time_numeric = np.array([t.timestamp() for t in df['time']])
            y_price = df['price_sek']
            
            # Utför linjär regression
            slope, intercept, r_value, p_value, std_err = linregress(x_time_numeric, y_price)
            
            # Beräkna de y-värden som trendlinjen ska ha
            trend_line = slope * x_time_numeric + intercept
            
            # --- NY LOGIK FÖR PROCENTUELL FÖRÄNDRING ---
            
            # Värdet vid trendlinjens start (första datapunktens timestamp)
            start_price_trend = slope * x_time_numeric.min() + intercept
            # Värdet vid trendlinjens slut (sista datapunktens timestamp)
            end_price_trend = slope * x_time_numeric.max() + intercept

            # Total procentuell förändring över de 100 punkterna/minuterna
            # Använd start_price_trend som bas
            if start_price_trend != 0:
                trend_percent_change = ((end_price_trend - start_price_trend) / start_price_trend) * 100
            else:
                trend_percent_change = 0.0

            # Välj färg och namn baserat på lutningen
            if slope >= 0:
                trend_color = '#3CB371'  # Grön
                trend_name = f'POSITIV TREND (+{trend_percent_change:.2f} % / {MAX_DASH_POINTS} min)'
            else:
                trend_color = '#FF6347'  # Röd
                trend_name = f'NEGATIV TREND ({trend_percent_change:+.2f} % / {MAX_DASH_POINTS} min)'


            # Lägg till trendlinjen som en trace
            trend_trace = go.Scatter(
                x=df['time'], 
                y=trend_line, 
                mode='lines', 
                name=trend_name, 
                line=dict(color=trend_color, dash='dash', width=4),
                hoverinfo='name'
            )

        
        # Bygg listan med alla spårningar
        data_traces = [
            go.Scatter(x=df['time'], y=df['price_sek'], mode='lines+markers', name='Aktuellt Pris (XRP/SEK)', line=dict(color='#00BFFF', width=2), marker=dict(size=8)),
            go.Scatter(x=df['time'], y=[high_sek] * len(df), mode='lines', name='24h Högsta', line=dict(color='#3CB371', dash='dot', width=1.5), hoverinfo='name+y'),
            go.Scatter(x=df['time'], y=[low_sek] * len(df), mode='lines', name='24h Lägsta', line=dict(color='#FF6347', dash='dot', width=1.5), hoverinfo='name+y')
        ]
        
        if trend_trace:
            # Lägg trendlinjen sist, så den ligger överst och är mest framträdande
            data_traces.append(trend_trace)
        
        fig = go.Figure(
            data=data_traces,
            layout=go.Layout(
                xaxis_title="Tid", yaxis_title="Pris i SEK", title=f"XRP/SEK Prisutveckling de senaste {MAX_DASH_POINTS} minuterna",
                plot_bgcolor='#111111', paper_bgcolor='#111111', font=dict(color='#FFFFFF', size=14),
                legend=dict(x=0, y=1.0, orientation='h'),
                margin=dict(l=40, r=40, t=40, b=40)
            )
        )
        
        # 4. KPI LOGIK: Skapa de visuella KPI-korten
        kpi_cards = [
            create_kpi_card("24h HÖGSTA", high_sek, "SEK", is_percent=False),
            create_kpi_card("24h LÄGSTA", low_sek, "SEK", is_percent=False),
            create_kpi_card("24h ÄNDRING", percent_24h, "%", is_percent=True),
            create_kpi_card("7 DAGAR", percent_7d, "%", is_percent=True),
            create_kpi_card("30 DAGAR", percent_30d, "%", is_percent=True),
        ]
        
        # 5. Uppdatera det aktuella priset
        display_text = f"Aktuell kurs: {price_sek:.4f} SEK"
        
        return fig, display_text, kpi_cards

    # Fallback om price_data mot förmodan är None
    return (
        go.Figure(layout=go.Layout(plot_bgcolor='#111111', paper_bgcolor='#111111')), 
        "Väntar på data...", 
        html.Div("KPI-data ej tillgänglig.", style={'color': '#888888', 'textAlign': 'center'})
    )

# Starta servern
if __name__ == '__main__':
    load_historical_data()
    
    print(f"XRP/SEK Realtidsspårare startar...")
    print(f"Data loggas till: {os.path.abspath(CSV_FILE_PATH)}")
    print(f"Dash-grafen kommer att visa de senaste {MAX_DASH_POINTS} minuternas historik, plus en trendlinje.")
    print(f"Vänta 1-2 minuter på första datainsamlingen...")
    
    app.run(debug=True, host='0.0.0.0')