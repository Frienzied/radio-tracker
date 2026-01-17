import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import os
import pytz
import math
from datetime import datetime, timedelta, timezone

# Biblioteki do obliczeń satelitarnych
from sgp4.api import Satrec, jday
from astropy.coordinates import TEME, EarthLocation, ITRS
from astropy.time import Time
import astropy.units as u

# ===========================
# Konfiguracja Strony
# ===========================
st.set_page_config(
    page_title="Centrum Dowodzenia Radiowego",
    page_icon="📡",
    layout="wide"
)

# ===========================
# 0. FUNKCJE POMOCNICZE I BAZA DANYCH
# ===========================
LOGBOOK_FILE = "radio_logbook.csv"

def load_logbook():
    """Wczytuje logbook z pliku CSV lub tworzy nowy, jeśli plik nie istnieje."""
    if os.path.exists(LOGBOOK_FILE):
        return pd.read_csv(LOGBOOK_FILE)
    else:
        return pd.DataFrame(columns=["Data", "Godzina (UTC)", "Freq (MHz)", "Stacja", "Modulacja", "Raport"])

def save_logbook(df):
    """Zapisuje logbook do pliku CSV."""
    df.to_csv(LOGBOOK_FILE, index=False)

def update_counter():
    """Prosty licznik odwiedzin oparty na pliku tekstowym."""
    counter_file = "counter.txt"
    if not os.path.exists(counter_file):
        with open(counter_file, "w") as f:
            f.write("0")
    
    with open(counter_file, "r") as f:
        try:
            count = int(f.read())
        except:
            count = 0
            
    count += 1
    
    with open(counter_file, "w") as f:
        f.write(str(count))
        
    return count

visit_count = update_counter()

def get_utc_time():
    """Zwraca aktualny czas UTC w formacie HH:MM."""
    return datetime.now(timezone.utc).strftime("%H:%M UTC")

def get_time_in_zone(zone_name):
    """Zwraca czas w podanej strefie czasowej."""
    try:
        tz = pytz.timezone(zone_name)
        return datetime.now(tz).strftime("%H:%M")
    except:
        return "--:--"

def latlon_to_maidenhead(lat, lon):
    """Konwertuje współrzędne GPS na lokator QTH (Maidenhead)."""
    try:
        A = ord('A')
        lon += 180
        lat += 90
        
        f_lon = int(lon / 20)
        f_lat = int(lat / 10)
        lon -= f_lon * 20
        lat -= f_lat * 10
        
        s_lon = int(lon / 2)
        s_lat = int(lat)
        lon -= s_lon * 2
        lat -= s_lat
        
        ss_lon = int(lon * 12)
        ss_lat = int(lat * 24)
        
        return f"{chr(A+f_lon)}{chr(A+f_lat)}{s_lon}{s_lat}{chr(A+ss_lon)}{chr(A+ss_lat)}"
    except:
        return "Error"

# ===========================
# 1. GENERATORY CZĘSTOTLIWOŚCI
# ===========================

def generate_pmr_list():
    """Generuje listę kanałów PMR."""
    pmr_list = []
    base_freq = 446.00625
    step = 0.0125
    
    for i in range(16):
        channel = i + 1
        freq = base_freq + (i * step)
        desc = "Kanał ogólny"
        
        if channel == 1:
            desc = "Najpopularniejszy kanał (dzieci, nianie, budowy)"
        elif channel == 3:
            desc = "Kanał PREPPERSÓW (Reguła 3-3-3). Kanał górski (Alpy/Włochy)"
            
        pmr_list.append({
            "MHz": f"{freq:.5f}",
            "Pasmo": "PMR",
            "Mod": "NFM",
            "Kategoria": "PMR",
            "Nazwa": f"PMR {channel}",
            "Opis": desc
        })
    return pmr_list

def generate_cb_list():
    """Generuje listę kanałów CB Radio."""
    freqs = [
        26.965, 26.975, 26.985, 27.005, 27.015, 27.025, 27.035, 27.055, 27.065, 27.075,
        27.085, 27.105, 27.115, 27.125, 27.135, 27.155, 27.165, 27.175, 27.185, 27.205,
        27.215, 27.225, 27.255, 27.235, 27.245, 27.265, 27.275, 27.285, 27.295, 27.305,
        27.315, 27.325, 27.335, 27.345, 27.355, 27.365, 27.375, 27.385, 27.395, 27.405
    ]
    cb_list = []
    
    for i, f in enumerate(freqs):
        channel = i + 1
        # Odejmujemy 0.005 MHz dla standardu polskiego ("zera")
        f_pl = f - 0.005
        desc = "Kanał ogólny"
        
        if channel == 9:
            desc = "!!! RATUNKOWY !!!"
        elif channel == 19:
            desc = "!!! DROGOWY !!! (Antymisiek)"
        elif channel == 3:
            desc = "Kanał Preppersów (System 3-3-3)"
            
        cb_list.append({
            "MHz": f"{f_pl:.3f}",
            "Pasmo": "CB",
            "Mod": "AM",
            "Kategoria": "CB Radio",
            "Nazwa": f"CB {channel}",
            "Opis": desc
        })
    return cb_list

# ===========================
# 2. BAZA DANYCH (Pełna lista)
# ===========================

repeater_list = [
    {"Znak": "SR5WA", "Freq": "439.350", "CTCSS": "127.3", "Lat": 52.23, "Lon": 21.01, "Loc": "Warszawa (PKiN)", "Shift": "-7.6"},
    {"Znak": "SR5W", "Freq": "145.600", "CTCSS": "127.3", "Lat": 52.21, "Lon": 20.98, "Loc": "Warszawa", "Shift": "-0.6"},
    {"Znak": "SR6J", "Freq": "145.675", "CTCSS": "94.8", "Lat": 50.78, "Lon": 15.56, "Loc": "Śnieżne Kotły (Ogromny Zasięg!)", "Shift": "-0.6"},
    {"Znak": "SR9P", "Freq": "438.900", "CTCSS": "103.5", "Lat": 50.06, "Lon": 19.94, "Loc": "Kraków", "Shift": "-7.6"},
    {"Znak": "SR9C", "Freq": "145.775", "CTCSS": "103.5", "Lat": 49.65, "Lon": 19.88, "Loc": "Chorągwica", "Shift": "-0.6"},
    {"Znak": "SR2Z", "Freq": "145.725", "CTCSS": "94.8", "Lat": 54.37, "Lon": 18.60, "Loc": "Gdańsk (Olivia Star)", "Shift": "-0.6"},
    {"Znak": "SR2C", "Freq": "438.800", "CTCSS": "94.8", "Lat": 54.52, "Lon": 18.53, "Loc": "Gdynia", "Shift": "-7.6"},
    {"Znak": "SR3PO", "Freq": "438.850", "CTCSS": "110.9", "Lat": 52.40, "Lon": 16.92, "Loc": "Poznań", "Shift": "-7.6"},
    {"Znak": "SR8L", "Freq": "145.625", "CTCSS": "107.2", "Lat": 51.24, "Lon": 22.57, "Loc": "Lublin", "Shift": "-0.6"},
    {"Znak": "SR4J", "Freq": "439.100", "CTCSS": "88.5", "Lat": 53.77, "Lon": 20.48, "Loc": "Olsztyn", "Shift": "-7.6"},
    {"Znak": "SR7V", "Freq": "145.6875", "CTCSS": "88.5", "Lat": 50.80, "Lon": 19.11, "Loc": "Częstochowa", "Shift": "-0.6"},
    {"Znak": "SR1Z", "Freq": "145.6375", "CTCSS": "118.8", "Lat": 53.42, "Lon": 14.55, "Loc": "Szczecin", "Shift": "-0.6"},
]

global_stations = [
    {"MHz": "0.225", "Pasmo": "LW (Długie)", "Mod": "AM", "Kategoria": "Polska", "Nazwa": "Polskie Radio 1", "Opis": "Nadajnik w Solcu Kujawskim. Zasięg: cała Europa. Kluczowy w sytuacjach kryzysowych."},
    {"MHz": "0.198", "Pasmo": "LW (Długie)", "Mod": "AM", "Kategoria": "Europa", "Nazwa": "BBC Radio 4", "Opis": "Legendarna stacja brytyjska. Zasięg zachodnia Europa."},
    {"MHz": "0.153", "Pasmo": "LW (Długie)", "Mod": "AM", "Kategoria": "Europa", "Nazwa": "Radio Romania", "Opis": "Antena Satelor. Bardzo silny sygnał z Rumunii (muzyka ludowa)."},
    {"MHz": "6.000-6.200", "Pasmo": "49m (SW)", "Mod": "AM", "Kategoria": "Świat", "Nazwa": "Pasmo 49m", "Opis": "Główne pasmo wieczorne dla stacji europejskich (BBC, RFI)."},
    {"MHz": "9.400-9.900", "Pasmo": "31m (SW)", "Mod": "AM", "Kategoria": "Świat", "Nazwa": "Pasmo 31m", "Opis": "Najpopularniejsze pasmo międzynarodowe (Całodobowe)."},
    {"MHz": "15.100-15.800", "Pasmo": "19m (SW)", "Mod": "AM", "Kategoria": "Świat", "Nazwa": "Pasmo 19m", "Opis": "Stacje dalekiego zasięgu (Chiny, USA) w ciągu dnia."},
    {"MHz": "4.625", "Pasmo": "SW", "Mod": "USB/AM", "Kategoria": "Utility", "Nazwa": "UVB-76", "Opis": "Rosyjska stacja numeryczna (The Buzzer). Nadaje od lat 70-tych."},
    {"MHz": "5.000", "Pasmo": "SW", "Mod": "AM", "Kategoria": "Wzorzec", "Nazwa": "WWV", "Opis": "Amerykański wzorzec czasu. Służy do testowania propagacji."},
    {"MHz": "14.230", "Pasmo": "20m", "Mod": "USB", "Kategoria": "Ham", "Nazwa": "SSTV Call", "Opis": "Krótkofalowcy przesyłający obrazki (Analogowo)."},
    {"MHz": "5.450", "Pasmo": "SW", "Mod": "USB", "Kategoria": "Lotnictwo", "Nazwa": "RAF Volmet", "Opis": "Pogoda dla lotnictwa (Royal Air Force)."},
]

websdr_list = [
    {"Nazwa": "WebSDR Twente", "Kraj": "Holandia 🇳🇱", "Link": "http://websdr.ewi.utwente.nl:8901/", "Opis": "Absolutny nr 1 na świecie. Odbiera wszystko od stacji numerycznych po Radio China."},
    {"Nazwa": "WebSDR Zielona Góra", "Kraj": "Polska 🇵🇱", "Link": "http://websdr.sp3pgx.uz.zgora.pl:8901/", "Opis": "Idealny do nasłuchu satelitów (ISS, NOAA) oraz lokalnych przemienników."},
    {"Nazwa": "Klub SP2PMK", "Kraj": "Polska 🇵🇱", "Link": "http://sp2pmk.uni.torun.pl:8901/", "Opis": "Toruń. Świetny do słuchania polskich rozmów krótkofalarskich (wieczorami na 3.7 MHz)."},
    {"Nazwa": "KiwiSDR Map", "Kraj": "Świat 🌍", "Link": "http://rx.linkfanel.net/", "Opis": "Mapa tysięcy amatorskich odbiorników na całym świecie."},
]

special_freqs = [
    {"MHz": "145.800", "Pasmo": "2m", "Mod": "NFM", "Kategoria": "Satelity", "Nazwa": "ISS (Głos)", "Opis": "Region 1 Voice - Główny kanał foniczny ISS"},
    {"MHz": "145.825", "Pasmo": "2m", "Mod": "FM", "Kategoria": "Satelity", "Nazwa": "ISS (APRS)", "Opis": "Packet Radio 1200bps / Digipeater"},
    {"MHz": "437.800", "Pasmo": "70cm", "Mod": "FM", "Kategoria": "Satelity", "Nazwa": "ISS (Repeater)", "Opis": "Downlink przemiennika (Uplink: 145.990 z tonem 67.0)"},
    {"MHz": "137.100", "Pasmo": "VHF", "Mod": "WFM", "Kategoria": "Satelity", "Nazwa": "NOAA 19", "Opis": "APT - Analogowe zdjęcia Ziemi (przeloty popołudniowe)"},
    {"MHz": "121.500", "Pasmo": "Air", "Mod": "AM", "Kategoria": "Lotnictwo", "Nazwa": "Air Guard", "Opis": "Międzynarodowy kanał RATUNKOWY (wymaga radia z AM!)"},
    {"MHz": "129.500", "Pasmo": "Air", "Mod": "AM", "Kategoria": "Lotnictwo", "Nazwa": "LPR (Operacyjny)", "Opis": "Częsty kanał Lotniczego Pogotowia (może się różnić lokalnie)"},
    {"MHz": "148.6625", "Pasmo": "VHF", "Mod": "NFM", "Kategoria": "Służby", "Nazwa": "PSP (B028)", "Opis": "Krajowy Kanał Ratowniczo-Gaśniczy (ogólnopolski)"},
    {"MHz": "156.800", "Pasmo": "Marine", "Mod": "FM", "Kategoria": "Morskie", "Nazwa": "Kanał 16", "Opis": "Morski kanał ratunkowy i wywoławczy"},
    {"MHz": "145.500", "Pasmo": "2m", "Mod": "FM", "Kategoria": "Ham", "Nazwa": "VHF Call", "Opis": "Wywoławcza krótkofalarska (rozmowy lokalne)"},
]

# Łączymy listy w jedną
data_freq = special_freqs + generate_pmr_list() + generate_cb_list()

# ===========================
# 3. LOGIKA SATELITARNA (Z ZABEZPIECZENIEM TLE)
# ===========================
@st.cache_data(ttl=3600)
def fetch_iss_tle():
    """
    Pobiera dane TLE (Two-Line Element) dla ISS.
    W razie awarii Celestrak zwraca dane zapasowe (Fallback),
    dzięki czemu aplikacja się nie zawiesza.
    """
    FALLBACK_TLE = (
        "1 25544U 98067A   24017.54519514  .00016149  00000+0  29290-3 0  9993",
        "2 25544  51.6415 158.8530 0005786 244.1866 179.9192 15.49622591435056"
    )
    url = "https://celestrak.org/NORAD/elements/stations.txt"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        resp.raise_for_status() 
        lines = [l.strip() for l in resp.text.splitlines() if l.strip()]
        for
