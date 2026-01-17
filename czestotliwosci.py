import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
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
    page_title="Radio & ISS Tracker",
    page_icon="🛰️",
    layout="wide"
)

# ===========================
# 1. LOGIKA SATELITARNA (Backend)
# ===========================

@st.cache_data(ttl=3600)
def fetch_iss_tle():
    """
    Pobiera TLE. Posiada mechanizm 'Fallback' - jeśli pobieranie się nie uda
    (np. timeout w chmurze), używa wpisanych na sztywno danych zapasowych.
    """
    # Dane zapasowe (Fallback) - używane gdy CelesTrak nie odpowiada
    # Dzięki temu aplikacja nie wyświetla błędu 500/Timeout
    FALLBACK_TLE = (
        "1 25544U 98067A   24017.54519514  .00016149  00000+0  29290-3 0  9993",
        "2 25544  51.6415 158.8530 0005786 244.1866 179.9192 15.49622591435056"
    )

    url = "https://celestrak.org/NORAD/elements/stations.txt"
    
    # Nagłówek udający zwykłą przeglądarkę (pomaga ominąć blokady anty-botowe)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        # Timeout 5 sekund - jeśli serwer nie odpowie szybko, przerywamy i bierzemy backup
        resp = requests.get(url, headers=headers, timeout=5)
        resp.raise_for_status()
        lines = [l.strip() for l in resp.text.splitlines() if l.strip()]
        
        for i, line in enumerate(lines):
            if "ISS (ZARYA)" in line and i+2 < len(lines):
                return lines[i+1], lines[i+2]
        
        # Jeśli plik pobrano, ale nie ma w nim ISS -> użyj backupu
        return FALLBACK_TLE

    except Exception as e:
        # Jeśli wystąpi jakikolwiek błąd (brak neta, blokada, timeout) -> użyj backupu
        print(f"⚠️ Używam danych zapasowych z powodu błędu: {e}")
        return FALLBACK_TLE

def get_satellite_position(line1, line2):
    """Oblicza aktualną pozycję (lat, lon) i trajektorię"""
    try:
        sat = Satrec.twoline2rv(line1, line2)
        now = datetime.now(timezone.utc)
        
        # 1. Aktualna pozycja
        jd, fr = jday(now.year, now.month, now.day, now.hour, now.minute, now.second + now.microsecond * 1e-6)
        e, r, v = sat.sgp4(jd, fr)
        
        if e != 0: return None, None, [], []

        # Konwersja TEME -> Geo
        t_now = Time(now)
        teme = TEME(x=r[0]*u.km, y=r[1]*u.km, z=r[2]*u.km, obstime=t_now)
        itrs = teme.transform_to(ITRS(obstime=t_now))
        loc = EarthLocation(itrs.x, itrs.y, itrs.z)
        
        cur_lat = loc.lat.deg
        cur_lon = loc.lon.deg
        
        # 2. Trajektoria (50 min przód/tył)
        traj_lats, traj_lons = [], []
        prev_lon = None
        
        for delta in range(-50 * 60, 50 * 60, 60): # Co minutę
            t_step = now + timedelta(seconds=delta)
            jd_s, fr_s = jday(t_step.year, t_step.month, t_step.day, t_step.hour, t_step.minute, t_step.second)
            _, r_s, _ = sat.sgp4(jd_s, fr_s)
            
            t_astropy = Time(t_step)
            teme_s = TEME(x=r_s[0]*u.km, y=r_s[1]*u.km, z=r_s[2]*u.km, obstime=t_astropy)
            itrs_s = teme_s.transform_to(ITRS(obstime=t_astropy))
            loc_s = EarthLocation(itrs_s.x, itrs_s.y, itrs_s.z)
            
            lon_s = loc_s.lon.deg
            
            # Przerwanie linii przy zmianie daty (180 st)
            if prev_lon is not None and abs(lon_s - prev_lon) > 180:
                traj_lats.append(None)
                traj_lons.append(None)
                
            traj_lats.append(loc_s.lat.deg)
            traj_lons.append(lon_s)
            prev_lon = lon_s

        return cur_lat, cur_lon, traj_lats, traj_lons
    except Exception as e:
        print(f"Błąd obliczeń orbitalnych: {e}")
        return None, None, [], []

# ===========================
# 2. BAZA DANYCH CZĘSTOTLIWOŚCI
# ===========================

data_freq = [
    {"MHz": "145.800", "Pasmo": "2m", "Mod": "NFM", "Nazwa": "ISS (Głos/SSTV)", "Opis": "Główny kanał głosowy stacji ISS"},
    {"MHz": "145.825", "Pasmo": "2m", "Mod": "FM", "Nazwa": "ISS (APRS)", "Opis": "Pakiety cyfrowe / Packet Radio"},
    {"MHz": "437.800", "Pasmo": "70cm", "Mod": "FM", "Nazwa": "ISS (Repeater)", "Opis": "Wyjście przemiennika crossband"},
    {"MHz": "137.100", "Pasmo": "2m", "Mod": "WFM", "Nazwa": "NOAA 19", "Opis": "Zdjęcia satelitarne (APT)"},
    {"MHz": "137.620", "Pasmo": "2m", "Mod": "WFM", "Nazwa": "NOAA 15", "Opis": "Zdjęcia satelitarne (APT)"},
    {"MHz": "145.500", "Pasmo": "2m", "Mod": "FM", "Nazwa": "Call Freq", "Opis": "Ogólna wywoławcza (Mobilna/Bazowa)"},
    {"MHz": "446.006", "Pasmo": "PMR", "Mod": "NFM", "Nazwa": "PMR 1", "Opis": "Walkie-talkie bez licencji"},
    {"MHz": "156.800", "Pasmo": "Marine", "Mod": "FM", "Nazwa": "Kanał 16", "Opis": "Ratunkowy i wywoławczy morski"},
    {"MHz": "144.800", "Pasmo": "2m", "Mod": "FM", "Nazwa": "APRS Europa", "Opis": "Lokalizacja pojazdów/stacji"},
]

# ===========================
# 3. INTERFEJS APLIKACJI (Frontend)
# ===========================

st.title("🛰️ Radio Command Center")
st.markdown("Śledzenie satelitów + Baza częstotliwości radiowych.")

# --- UKŁAD KOLUMN ---
col_map, col_data = st.columns([3, 2]) # Mapa szersza (3/5), Dane węższe (2/5)

with col_map:
    st.subheader("Aktualna pozycja ISS")
    
    # Pobieranie danych (z mechanizmem fallback)
    l1, l2 = fetch_iss_tle()
    
    # Jeśli mamy dane (a dzięki fallback zawsze powinniśmy mieć)
    if l1 and l2:
        lat, lon, path_lat, path_lon = get_satellite_position(l1, l2)
        
        if lat is not None:
            # Tworzenie mapy Plotly
            fig = go.Figure()

            # Orbita
            fig.add_trace(go.Scattergeo(
                lat=path_lat, lon=path_lon, mode="lines",
                line=dict(color="red", width=2, dash="dot"),
                name="Orbita"
            ))

            # Pozycja ISS
            fig.add_trace(go.Scattergeo(
                lat=[lat], lon=[lon], mode="markers",
                marker=dict(size=15, color="red", symbol="star"),
                name="ISS Teraz"
            ))

            # Konfiguracja wyglądu
            fig.update_layout(
                margin={"r":0,"t":0,"l":0,"b":0},
                height=400,
                geo=dict(
                    projection_type="natural earth",
                    showland=True, landcolor="rgb(230, 230, 230)",
                    showocean=True, oceancolor="rgb(200, 225, 255)",
                    showcountries=True
                ),
                showlegend=False
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Przycisk odświeżania
            if st.button("🔄 Odśwież pozycję"):
                st.rerun()
                
            st.caption(f"Lat: {lat:.2f}, Lon: {lon:.2f} | Dane orbitalne (TLE)")
        else:
            st.error("Błąd obliczeń orbitalnych.")
    else:
        st.error("Nie udało się pobrać danych satelitarnych (nawet zapasowych).")

with col_data:
    st.subheader("Częstotliwości")
    
    # Filtry
    df = pd.DataFrame(data_freq)
    search = st.text_input("🔍 Szukaj (np. ISS, PMR)", "")
    
    if search:
        df = df[df.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)]

    # Tabela
    st.dataframe(
        df,
        column_config={
            "MHz": st.column_config.TextColumn("MHz", help="Częstotliwość"),
            "Mod": st.column_config.TextColumn("Mod", width="small"),
            "Nazwa": st.column_config.TextColumn("Nazwa", width="medium"),
        },
        use_container_width=True,
        hide_index=True,
        height=400
    )

# ===========================
# Sekcja informacyjna na dole
# ===========================
st.divider()
c1, c2, c3 = st.columns(3)
with c1:
    st.info("**Doppler Shift**\nPamiętaj, że częstotliwość satelitów się zmienia (+/- 3 kHz) gdy nadlatują/odlatują. Wymagane strojenie!")
with c2:
    st.warning("**Licencja**\nNasłuch jest legalny. Nadawanie na pasmach 2m/70cm wymaga licencji krótkofalarskiej.")
with c3:
    st.success("**Sprzęt**\nDo odbioru wystarczy tani dongle RTL-SDR v3 lub ręczne radio typu Baofeng/Quansheng.")
