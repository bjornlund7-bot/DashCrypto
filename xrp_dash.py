import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import time
import threading
import os
import requests
import json
import logging
from redis import from_url, exceptions
# Importera SciPy för linjär regression (trendlinjer)
from scipy.stats import linregress 
import numpy as np

# --- Konfiguration och Initialisering ---

logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

# [KONSTANTER OCH REDIS-INSTÄLLNINGAR OFÖRÄNDRADE]
# ...

# Lägg till SciPy-import och definiera trendlinje-konstanter.
TREND_WINDOWS = {
    '1h': {'blocks': 12, 'color': '#ff7f0e', 'name': 'Trend (1h)'}, # Orange
    '3h': {'blocks': 36, 'color': '#2ca02c', 'name': 'Trend (3h)'}, # Grön
    '6h': {'blocks': 72, 'color': '#d62728', 'name': 'Trend (6h)'}, # Röd
}

# [FUNKTIONER FÖR TELEGRAM, EXCHANGE RATE, TICKER DATA, OHLC DATA, PROCENTFÖRÄNDRING OFÖRÄNDRADE]
# ...

# --- NY FUNKTION: Beräkna linjär trendlinje ---

def calculate_trendline(historical_data, blocks):
    """
    Beräknar linjär trendlinje (y = slope * x + intercept) 
    för de senaste 'blocks' datastaplarna.
    Returnerar (slope, intercept, start_index).
    """
    
    if len(historical_data) < blocks:
        return None, None, None

    # Hämta de senaste 'blocks' av data
    data_segment = historical_data[-blocks:]
    
    # Skapa tidsindex (x-värden) baserat på position 0, 1, 2, ...
    # Priset är y-värdena.
    x_values = np.arange(len(data_segment))
    y_values = np.array([item['price'] for item in data_segment])

    # Utför linjär regression
    slope, intercept, r_value, p_value, std_err = linregress(x_values, y_values)
    
    # Startindexet i den totala datamängden för att rita linjen
    start_index_global = len(historical_data) - blocks 
    
    return slope, intercept, start_index_global

# [UPPDATERA REDIS CACHE FUNKTION OFÖRÄNDRAD]
# ...

# --- DASH LAYOUT KOD OFÖRÄNDRAD ---
# ...

# --- Callback för enbart Pris/Tidsstämpel (Snabb uppdatering) OFÖRÄNDRAD ---
@app.callback(Output('current-price', 'children'),
              Output('last-updated', 'children'),
              [Input('interval-component', 'n_intervals'),
               Input('coin-dropdown', 'value'),
               Input('currency-dropdown', 'value')])
def update_price_and_time(n, coin_symbol, currency):
    # [KOD FÖR PRIS OCH TID OFÖRÄNDRAD]
    data = get_data_from_redis()
    
    if data is None or 'EUR_SEK_RATE' not in data:
        return "Laddar data...", "Väntar på data från Kraken/Redis..."

    price_key = f'{coin_symbol}/{currency}'
    current_price = data.get(price_key)
    timestamp = data.get('timestamp')
    
    if current_price is None:
        return f"❌ Pris för {coin_symbol}/{currency} saknas.", "Data saknas eller är inte tillgänglig på Kraken."
    
    if current_price < 10:
        price_format = f"{current_price:,.4f}"
    else:
        price_format = f"{current_price:,.2f}"
        
    price_format = price_format.replace(",", "TEMP").replace(".", ",").replace("TEMP", " ") 

    coin_label = SYMBOL_TO_LABEL.get(coin_symbol, coin_symbol)
    price_text = f"{coin_label}: {price_format} {currency}"
    updated_text = f"Senast uppdaterad (Realtime Ticker): {time.strftime('%H:%M:%S', time.gmtime(timestamp))} UTC"

    return price_text, updated_text

# --- Callback för Grafen (UPPDATERAD MED TRENDLINJER) ---

@app.callback(Output('live-update-graph', 'figure'),
              [Input('interval-component', 'n_intervals')], 
              [State('coin-dropdown', 'value'),
               State('currency-dropdown', 'value')])
def update_graph(n, coin_symbol, currency):
    
    data = get_data_from_redis()
    
    if data is None or 'EUR_SEK_RATE' not in data:
        figure = go.Figure(go.Scatter(x=[0], y=[0], mode='text', text=['Laddar...']))
        figure.update_layout(title="Hämtar data...", template="plotly_white", height=400)
        return figure
    
    coin_label = SYMBOL_TO_LABEL.get(coin_symbol, coin_symbol)
    eur_to_sek = data.get('EUR_SEK_RATE', 11.0)
    current_price = data.get(f'{coin_symbol}/EUR') 
    
    # Läs historisk data från Redis
    ohlc_interval = OHLC_CACHE_INTERVAL_MIN 
    kraken_ticker = CRYPTO_PAIRS[coin_label]
    ohlc_cache_key = f'OHLC_CACHED_{ohlc_interval}MIN_{kraken_ticker}'
    historical_data = []
    
    if r:
        cached_ohlc = r.get(ohlc_cache_key)
        if cached_ohlc:
            historical_data = json.loads(cached_ohlc)
            
    range_data_raw = data.get('ALL_24H_RANGE', {}).get(coin_symbol, {})
    high_24h_eur = range_data_raw.get('high_eur')
    low_24h_eur = range_data_raw.get('low_eur')
    
    figure = go.Figure()
    
    if historical_data:
        
        # --- 1. Konvertera Priser och Tider ---
        prices_eur = [item['price'] for item in historical_data]
        if currency == 'SEK':
            prices_display = [p * eur_to_sek for p in prices_eur]
            high_24h_display = high_24h_eur * eur_to_sek if high_24h_eur is not None else None
            low_24h_display = low_24h_eur * eur_to_sek if low_24h_eur is not None else None
        else:
            prices_display = prices_eur
            high_24h_display = high_24h_eur
            low_24h_display = low_24h_eur
        
        times = [time.strftime('%H:%M', time.gmtime(item['time'])) for item in historical_data]
        
        # Huvudlinje: Kurs
        figure.add_trace(go.Scatter(
            x=times,
            y=prices_display,
            mode='lines',
            name=f'Kurs ({ohlc_interval} min intervall)',
            line=dict(color='#0056b3', width=3),
            hoverinfo='x+y'
        ))
        
        # --- 2. Lägg till Trendlinjer ---
        
        # Skapa en global x-axel för alla datapunkter (används för att placera trendlinjen korrekt)
        global_x_indices = np.arange(len(historical_data)) 

        for trend_key, config in TREND_WINDOWS.items():
            blocks = config['blocks']
            color = config['color']
            name = config['name']
            
            slope, intercept, start_index = calculate_trendline(prices_eur, blocks)
            
            if slope is not None:
                # Beräkna y-värden för trendlinjen
                trend_x_indices = global_x_indices[start_index:]
                trend_y_eur = slope * (trend_x_indices - start_index) + intercept
                
                # Konvertera trendpriser till visningsvaluta (SEK/EUR)
                trend_y_display = trend_y_eur * eur_to_sek if currency == 'SEK' else trend_y_eur
                
                # Hämta tidsstämplarna som motsvarar trendlinjens start och slut
                trend_times = times[start_index:]
                
                figure.add_trace(go.Scatter(
                    x=trend_times,
                    y=trend_y_display,
                    mode='lines',
                    name=name,
                    line=dict(color=color, width=2, dash='dash'),
                    hoverinfo='x+y'
                ))


        # --- 3. Lägg till 24h High/Low (som tidigare) ---
        if high_24h_display is not None:
            figure.add_hline(
                y=high_24h_display, line_dash="dot", line_color="green",
                annotation_text=f"24h Högsta: {high_24h_display:,.4f} {currency}",
                annotation_position="top right", name="24h Högsta", layer="below"
            )

        if low_24h_display is not None:
            figure.add_hline(
                y=low_24h_display, line_dash="dot", line_color="red",
                annotation_text=f"24h Lägsta: {low_24h_display:,.4f} {currency}",
                annotation_position="bottom right", name="24h Lägsta", layer="below"
            )

    else:
        # Visar nuvarande pris om historisk data saknas
        msg = f"Laddar historisk OHLC-data (5-min intervall) för {coin_label}..."
        current_time_ts = data.get('timestamp', time.time())
        current_time = time.strftime('%H:%M:%S', time.gmtime(current_time_ts))
        price_display = current_price * eur_to_sek if currency == 'SEK' else current_price
        
        figure.add_trace(go.Scatter(
            x=[current_time], y=[price_display], mode='markers+text', 
            marker=dict(size=10, color='#28a745'),
            text=[f"Pris: {price_display:,.4f} {currency}"],
            textposition="top center", name="Nuvarande Pris",
        ))
        figure.add_trace(go.Scatter(x=[0], y=[0], mode='text', text=[msg], showlegend=False))
    
    figure.update_layout(
        title=f'{coin_label} Prisutveckling ({currency})',
        xaxis_title=f"Tid ({ohlc_interval} min intervall)",
        yaxis_title=f"Pris ({currency})",
        template="plotly_white",
        margin=dict(l=40, r=40, t=40, b=40),
        height=400,
        hovermode="x unified",
        plot_bgcolor='white',
        paper_bgcolor='white'
    )
    
    return figure

# [ÖVRIGA CALLBACKS FÖR ALERT OCH SAMMANFATTNING OFÖRÄNDRADE]
# ...

if __name__ == '__main__':
    # För lokal utveckling
    # app.run_server(debug=True)  
    pass