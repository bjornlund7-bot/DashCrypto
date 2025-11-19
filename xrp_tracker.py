import requests
import time
from datetime import datetime

# Kraken API-adress för Ticker-information
KRAKEN_API_URL = "https://api.kraken.com/0/public/Ticker"
# Vi byter till det mer tillgängliga paret XRP/EUR
KRAKEN_PAIR = 'XRPEUR' 

# Enkel URL för att hämta EUR/SEK växelkurs (använder Googles offentliga data)
# Detta är en enkel, men icke-garanterad metod för ren växelkursdata.
EXCHANGE_RATE_URL = "https://api.exchangerate-api.com/v4/latest/EUR"
# OBS: Denna API-nyckel kan kräva registrering/begränsas. 
# Vi använder en dummy-nyckel här om en riktig API-nyckel skulle behövas.
# För de flesta offentliga tjänster är det tillräckligt att hämta JSON-data.


def get_eur_sek_rate():
    """Hämtar aktuell EUR/SEK växelkurs."""
    try:
        response = requests.get(EXCHANGE_RATE_URL, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        # Kontrollerar om SEK-kursen finns i resultatet
        if 'rates' in data and 'SEK' in data['rates']:
            return data['rates']['SEK']
        else:
            print("Varning: SEK-kurs saknas i växelkursdata. Använder fast kurs 11.50 SEK/EUR.")
            return 11.50 # Fallback-värde om API:et inte svarar
            
    except requests.exceptions.RequestException as e:
        print(f"Varning: Kunde inte hämta EUR/SEK växelkurs: {e}. Använder fast kurs 11.50 SEK/EUR.")
        return 11.50 # Fallback-värde vid nätverksfel
    except Exception as e:
        print(f"Varning: Okänt fel vid hämtning av EUR/SEK: {e}. Använder fast kurs 11.50 SEK/EUR.")
        return 11.50

def get_xrp_sek_price():
    """Hämtar aktuell XRP/EUR från Kraken och konverterar till SEK."""
    
    # Steg 1: Hämta XRP/EUR från Kraken
    try:
        params = {'pair': KRAKEN_PAIR}
        response = requests.get(KRAKEN_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data['error']:
            # Om även XRPEUR misslyckas, prova XXRPZEUR
            if 'Unknown asset pair' in str(data['error']):
                # Prova det äldre Kraken-paret
                alt_pair = 'XXRPZEUR'
                params = {'pair': alt_pair}
                response = requests.get(KRAKEN_API_URL, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                if data['error']:
                    return f"Fel från Kraken API även med {alt_pair}: {data['error']}"

            else:
                 return f"Fel från Kraken API: {data['error']}"


        if data['result']:
            # Hitta den faktiska nyckeln i svaret
            kraken_pair_key = list(data['result'].keys())[0]
            result = data['result'][kraken_pair_key]
            latest_price_eur = float(result['c'][0])
            
            # Steg 2: Konvertera EUR till SEK
            eur_sek_rate = get_eur_sek_rate()
            price_sek = latest_price_eur * eur_sek_rate
            
            return price_sek
        else:
             return f"Fick ett tomt resultat från Kraken för {KRAKEN_PAIR}."

    except requests.exceptions.RequestException as e:
        return f"Nätverksfel eller API-fel mot Kraken: {e}"
    except (KeyError, IndexError, TypeError) as e:
        return f"Fel vid tolkning av API-svar från Kraken: {e}. Fullständigt svar: {data}"
    except Exception as e:
        return f"Ett oväntat fel uppstod: {e}"

def main():
    """Huvudfunktion som kör uppdateringsslingan."""
    print(f"Startar övervakning av aktuell XRP/EUR-kurs från Kraken och konverterar till SEK (uppdatering varje 10:e sekund, avsluta med CTRL+C)...")
    
    while True:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        price_or_error = get_xrp_sek_price()
        
        if isinstance(price_or_error, float):
            print(f"[{timestamp}] Aktuell kurs för XRP/SEK: {price_or_error:.4f} SEK")
        else:
            print(f"[{timestamp}] Fel vid hämtning: {price_or_error}")
        
        # Vänta i 10 sekunder innan nästa uppdatering
        time.sleep(10)

if __name__ == "__main__":
    main()