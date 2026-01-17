import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import os
import pytz
import numpy as np
from datetime import datetime, timedelta, timezone

# Biblioteki do obliczeń satelitarnych
from sgp4.api import Satrec, jday
from astropy.coordinates import TEME, EarthLocation, ITRS, AltAz, GCRS
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
# 0. FUNKCJE POMOCNICZE
# ===========================
def update_counter():
    counter_file = "counter.txt"
    if not os.path.exists(counter_file):
        with open(counter_file, "w") as f: f.write("0")
    with open(counter_file, "r") as f:
        try: count = int(f.read())
        except: count = 0
    count += 1
    with open(counter_file, "w") as f: f.write(str(count))
    return count

visit_count = update_counter()

def get_utc_time():
    return datetime.now(timezone.utc).strftime("%H:%M UTC")

def get_time_in_zone(zone_name):
    try:
        tz = pytz.timezone(zone_name)
        return datetime.now(tz).strftime("%H:%M")
    except: return "--:--"

# ===========================
# 1. GENERATORY CZĘSTOTLIWOŚCI
# ===========================
def generate_pmr_list():
    pmr_list = []
    base_freq = 446.00625
    step = 0.0125
    for i in range(16):
        channel = i + 1
        freq = base_freq + (i * step)
        desc = "Kanał ogólny"
        if channel == 1: desc = "Najpopularniejszy kanał (dzieci, nianie, budowy)"
        elif channel == 3: desc = "Kanał PREPPERSÓW (Reguła 3-3-3)."
        pmr_list.append({
            "MHz": f"{freq:.5f}",
            "Pasmo": "PMR",
            "Mod": "NFM",
            "Kategoria": "PMR (Walkie-Talkie)",
            "Nazwa": f"PMR {channel}",
            "Opis": desc
        })
    return pmr_list

def generate_cb_list():
    base_freqs = [
        26.965, 26.975, 26.985, 27.005, 27.015, 27.025, 27.035, 27.055, 27.065, 27.075,
        27.085, 27.105, 27.115, 27.125, 27.135, 27.155, 27.165, 27.175, 27.185, 27.205,
        27.215, 27.225, 27.255, 27.235, 27.245, 27.265, 27.275, 27.285, 27.295, 27.305,
        27.315, 27.325, 27.335, 27.345, 27.355, 27.365, 27.375, 27.385, 27.395, 27.405
    ]
    cb_list = []
    for i, f_eu in enumerate(base_freqs):
        channel = i + 1
        f_pl = f_eu - 0.005
        desc = "Kanał ogólny"
        if channel == 9: desc = "!!! RATUNKOWY !!!"
        elif channel == 19: desc = "!!! DROGOWY !!! (Antymisiek)"
        elif channel == 3: desc = "Kanał Preppersów"
        cb_list.append({
            "MHz": f"{f_pl:.3f}",
            "Pasmo": "CB",
            "Mod": "AM",
            "Kategoria": "CB Radio",
            "Nazwa": f"CB Kanał {channel}",
            "Opis": desc
        })
    return cb_list

global_stations = [
    {"MHz": "0.225", "Pasmo": "LW", "Mod": "AM", "Kategoria": "Polska", "Nazwa": "Polskie Radio Jedynka", "Opis": "Solec Kujawski. Zasięg: cała Europa."},
    {"MHz": "0.198", "Pasmo": "LW", "Mod": "AM", "Kategoria": "Europa", "Nazwa": "BBC Radio 4", "Opis": "UK News."},
    {"MHz": "6.000", "Pasmo": "49m", "Mod": "AM", "Kategoria": "Świat", "Nazwa": "Pasmo 49m", "Opis": "Wieczorne pasmo europejskie."},
    {"MHz": "4.625", "Pasmo": "SW", "Mod": "USB", "Kategoria": "Utility", "Nazwa": "UVB-76 (The Buzzer)", "Opis": "Rosyjska stacja numeryczna."},
]

special_freqs = [
    {"MHz": "145.800", "Pasmo": "2m", "Mod": "NFM", "Kategoria": "Satelity", "Nazwa": "ISS (Głos)", "Opis": "Region 1 Voice"},
    {"MHz": "145.825", "Pasmo": "2m", "Mod": "FM", "Kategoria": "Satelity", "Nazwa": "ISS (APRS)", "Opis": "Packet Radio"},
    {"MHz": "137.100", "Pasmo": "VHF", "Mod": "WFM", "Kategoria": "Satelity", "Nazwa": "NOAA 19", "Opis": "APT Weather"},
    {"MHz": "137.620", "Pasmo": "VHF", "Mod": "WFM", "Kategoria": "Satelity", "Nazwa": "NOAA 15", "Opis": "APT Weather"},
    {"MHz": "121.500", "Pasmo": "Air", "Mod": "AM", "Kategoria": "Lotnictwo", "Nazwa": "Air Guard", "Opis": "Ratunkowy"},
    {"MHz": "156.800", "Pasmo": "Marine", "Mod": "FM", "Kategoria": "Morskie", "Nazwa": "Kanał 16", "Opis": "Ratunkowy"},
]

data_freq = special_freqs + generate_pmr_list() + generate_cb_list()

# ===========================
# 2. LOGIKA SATELITARNA (ZAAWANSOWANA)
# ===========================

SAT_CONFIG = {
    "ISS (ZARYA)": {"url": "https://celestrak.org/NORAD/elements/stations.txt", "name": "ISS (ZARYA)"},
    "NOAA 15": {"url": "https://celestrak.org/NORAD/elements/weather.txt", "name": "NOAA 15"},
    "NOAA 18": {"url": "https://celestrak.org/NORAD/elements/weather.txt", "name": "NOAA 18"},
    "NOAA 19": {"url": "https://celestrak.org/NORAD/elements/weather.txt", "name": "NOAA 19"},
}

@st.cache_data(ttl=3600)
def fetch_tle(sat_key):
    """Pobiera TLE dla konkretnego satelity."""
    config = SAT_CONFIG.get(sat_key)
    if not config: return None
    
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(config["url"], headers=headers, timeout=5)
        resp.raise_for_status()
        lines = [l.strip() for l in resp.text.splitlines() if l.strip()]
        for i, line in enumerate(lines):
            # Szukamy dokładnej nazwy satelity w pliku
            if config["name"] in line and i+2 < len(lines):
                return lines[i+1], lines[i+2]
        return None
    except Exception:
        return None

def calculate_look_angles(satrec, observer_lat, observer_lon, observer_alt=0):
    """Oblicza Azymut i Elewację dla obserwatora."""
    try:
        now = datetime.now(timezone.utc)
        t_astropy = Time(now)
        
        # Obserwator
        loc = EarthLocation(lat=observer_lat*u.deg, lon=observer_lon*u.deg, height=observer_alt*u.m)
        
        # Pozycja satelity (TEME -> ITRS -> AltAz)
        jd, fr = jday(now.year, now.month, now.day, now.hour, now.minute, now.second + now.microsecond * 1e-6)
        e, r, v = satrec.sgp4(jd, fr)
        if e != 0: return None, None
        
        teme = TEME(x=r[0]*u.km, y=r[1]*u.km, z=r[2]*u.km, obstime=t_astropy)
        
        # Konwersja do AltAz (Horyzontalny)
        altaz = teme.transform_to(AltAz(obstime=t_astropy, location=loc))
        
        return altaz.az.deg, altaz.alt.deg
    except Exception as e:
        return None, None

def get_ground_track(satrec):
    """Oblicza ślad na ziemi (Lat/Lon) na +/- 45 minut."""
    now = datetime.now(timezone.utc)
    lats, lons = [], []
    prev_lon = None
    
    for delta in range(-45 * 60, 45 * 60, 60): # Co minutę
        t_step = now + timedelta(seconds=delta)
        jd, fr = jday(t_step.year, t_step.month, t_step.day, t_step.hour, t_step.minute, t_step.second)
        _, r, _ = satrec.sgp4(jd, fr)
        
        t_astropy = Time(t_step)
        teme = TEME(x=r[0]*u.km, y=r[1]*u.km, z=r[2]*u.km, obstime=t_astropy)
        itrs = teme.transform_to(ITRS(obstime=t_astropy))
        loc = EarthLocation(itrs.x, itrs.y, itrs.z)
        
        lon = loc.lon.deg
        # Przerwanie linii na zmianie daty
        if prev_lon is not None and abs(lon - prev_lon) > 180:
            lats.append(None); lons.append(None)
            
        lats.append(loc.lat.deg)
        lons.append(lon)
        prev_lon = lon
        
    # Aktualna pozycja
    jd, fr = jday(now.year, now.month, now.day, now.hour, now.minute, now.second + now.microsecond * 1e-6)
    _, r, _ = satrec.sgp4(jd, fr)
    teme = TEME(x=r[0]*u.km, y=r[1]*u.km, z=r[2]*u.km, obstime=Time(now))
    itrs = teme.transform_to(ITRS(obstime=Time(now)))
    loc = EarthLocation(itrs.x, itrs.y, itrs.z)
    
    return loc.lat.deg, loc.lon.deg, lats, lons

# ===========================
# 3. INTERFEJS APLIKACJI
# ===========================

c_title, c_clock, c_visits = st.columns([3, 1, 1])
with c_title: st.title("📡 Centrum Dowodzenia")
with c_clock: st.markdown(f"<div style='text-align: right; color: #00ff41; font-family: monospace;'><b>ZULU:</b> {get_utc_time()}</div>", unsafe_allow_html=True)
with c_visits: st.markdown(f"<div style='text-align: right; color: gray;'>Odwiedzin: <b>{visit_count}</b></div>", unsafe_allow_html=True)

tabs = st.tabs(["🛰️ Tracker (Radar)", "☀️ Pogoda Kosmiczna", "🆘 Kryzysowe", "🌍 Czas", "📻 Globalne", "📚 Edukacja"])

# --- TAB 1: TRACKER ROZBUDOWANY ---
with tabs[0]:
    # Konfiguracja Trackera
    c_sat, c_loc1, c_loc2 = st.columns([2, 1, 1])
    with c_sat:
        selected_sat = st.selectbox("Wybierz satelitę:", list(SAT_CONFIG.keys()), index=0)
    with c_loc1:
        user_lat = st.number_input("Twoja Lat:", value=52.23, step=0.01, format="%.2f")
    with c_loc2:
        user_lon = st.number_input("Twoja Lon:", value=21.01, step=0.01, format="%.2f")

    l1, l2 = fetch_tle(selected_sat)
    
    if l1 and l2:
        satrec = Satrec.twoline2rv(l1, l2)
        cur_lat, cur_lon, path_lat, path_lon = get_ground_track(satrec)
        az, el = calculate_look_angles(satrec, user_lat, user_lon)
        
        # Wskaźniki Azymut / Elewacja
        col_metrics = st.columns(4)
        col_metrics[0].metric("Satelita", selected_sat)
        col_metrics[1].metric("Azymut (Kierunek)", f"{az:.1f}°", delta=None)
        col_metrics[2].metric("Elewacja (Wysokość)", f"{el:.1f}°", delta_color="normal" if el > 0 else "off")
        col_metrics[3].metric("Widoczność", "WIDOCZNY!" if el > 0 else "Pod horyzontem")

        # Dwie kolumny: Mapa Świata i Radar
        c_world, c_radar = st.columns([2, 1])
        
        with c_world:
            st.subheader("Mapa Świata")
            fig = go.Figure()
            fig.add_trace(go.Scattergeo(lat=path_lat, lon=path_lon, mode="lines", line=dict(color="blue", width=2, dash="dot"), name="Orbita"))
            fig.add_trace(go.Scattergeo(lat=[cur_lat], lon=[cur_lon], mode="text", text=["🛰️"], textfont=dict(size=30), name="Teraz"))
            # Pozycja użytkownika
            fig.add_trace(go.Scattergeo(lat=[user_lat], lon=[user_lon], mode="markers", marker=dict(size=8, color="green"), name="TY"))
            
            fig.update_layout(
                margin={"r":0,"t":0,"l":0,"b":0}, height=400,
                geo=dict(projection_type="natural earth", showland=True, landcolor="rgb(230, 230, 230)", showocean=True, oceancolor="rgb(200, 225, 255)", showcountries=True),
                showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True)

        with c_radar:
            st.subheader("Radar (Skyplot)")
            # Wykres polarny
            # Azymut to kąt (theta), Elewacja to promień (r). Ale w Skyplot środek to 90st (zenit), a brzeg to 0st (horyzont).
            # Więc r = 90 - elewacja. Jeśli el < 0, to satelita jest poza wykresem.
            
            r_val = 90 - el if el > 0 else None
            theta_val = az if el > 0 else None
            
            fig_polar = go.Figure()
            
            # Tło radaru
            fig_polar.add_trace(go.Scatterpolar(
                r=[r_val] if r_val is not None else [],
                theta=[theta_val] if theta_val is not None else [],
                mode='markers+text',
                marker=dict(size=15, color='red', symbol='circle'),
                text=['🛰️'],
                textposition="top center"
            ))
            
            fig_polar.update_layout(
                polar=dict(
                    radialaxis=dict(range=[0, 90], showticklabels=False, tickmode='array', tickvals=[0, 30, 60, 90]),
                    angularaxis=dict(direction="clockwise", rotation=0) # N na górze (0), zgodnie z zegarem (E=90)
                ),
                margin={"r":20,"t":20,"l":20,"b":20},
                height=400,
                showlegend=False
            )
            st.plotly_chart(fig_polar, use_container_width=True)
            if el < 0:
                st.info("Satelita jest pod horyzontem. Radar pokazuje tylko widoczne obiekty.")
                
        if st.button("🔄 Odśwież dane satelitarne"): st.rerun()

    else:
        st.error("Nie udało się pobrać danych TLE dla wybranego satelity.")

    st.divider()
    
    # Lista częstotliwości pod spodem
    st.subheader("Baza Częstotliwości (PL)")
    df = pd.DataFrame(data_freq)
    c_s, c_f = st.columns([2,1])
    with c_s: search = st.text_input("🔍 Szukaj...", placeholder="Np. ISS, PMR")
    with c_f: cat_filter = st.multiselect("Filtr", df["Kategoria"].unique())
    if search: df = df[df.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)]
    if cat_filter: df = df[df["Kategoria"].isin(cat_filter)]
    st.dataframe(df, use_container_width=True, hide_index=True)

# --- TAB 2: POGODA KOSMICZNA ---
with tabs[1]:
    st.header("☀️ Pogoda Kosmiczna")
    c1, c2 = st.columns(2)
    with c1:
        st.image("https://www.hamqsl.com/solar101vhf.php", caption="Dane: N0NBH")
        st.image("https://www.hamqsl.com/solarmap.php", caption="Greyline Map")
    with c2:
        st.info("**SFI (Solar Flux):** >100 = Dobre warunki.\n**K-Index:** <3 = Czysty sygnał.")

# --- TAB 3: KRYZYSOWE ---
with tabs[2]:
    st.header("🆘 Procedury Awaryjne")
    c1, c2, c3 = st.columns(3)
    with c1: st.error("Reguła 3-3-3: Co 3h, 3 minuty, PMR 3"); 
    with c2: st.warning("Sprzęt: Baofeng = PMR/Służby (nie AM)."); 
    with c3: st.info("Raport SALT: Size, Activity, Location, Time.")

# --- TAB 4: CZAS ---
with tabs[3]:
    st.header("🌍 Czas na Świecie")
    cols = st.columns(4)
    zones = [("UTC", "UTC"), ("Warszawa", "Europe/Warsaw"), ("New York", "America/New_York"), ("Tokio", "Asia/Tokyo")]
    for i, (n, z) in enumerate(zones): cols[i].metric(n, get_time_in_zone(z))

# --- TAB 5: GLOBALNE ---
with tabs[4]:
    st.header("📻 Globalne Stacje")
    st.dataframe(pd.DataFrame(global_stations), use_container_width=True, hide_index=True)

# --- TAB 6: EDUKACJA ---
with tabs[5]:
    st.header("📚 Słownik")
    st.markdown("**Squelch:** Blokada szumów. **AM:** Lotnictwo/CB. **FM:** Służby/PMR. **73:** Pozdrawiam.")

st.markdown("---")
st.caption("Centrum Dowodzenia Radiowego v8.0 Ultimate | Dane: CelesTrak, N0NBH | Czas: UTC")
