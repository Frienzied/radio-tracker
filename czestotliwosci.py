import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import os
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
    page_title="Radio & Crisis Center",
    page_icon="📡",
    layout="wide"
)

# ===========================
# 0. LICZNIK ODWIEDZIN
# ===========================
def update_counter():
    counter_file = "counter.txt"
    if not os.path.exists(counter_file):
        with open(counter_file, "w") as f:
            f.write("0")
    
    with open(counter_file, "r") as f:
        try:
            count = int(f.read())
        except ValueError:
            count = 0
            
    count += 1
    
    with open(counter_file, "w") as f:
        f.write(str(count))
        
    return count

visit_count = update_counter()

# ===========================
# 1. LOGIKA SATELITARNA (Backend)
# ===========================

@st.cache_data(ttl=3600)
def fetch_iss_tle():
    """Pobiera TLE z mechanizmem Fallback."""
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
        for i, line in enumerate(lines):
            if "ISS (ZARYA)" in line and i+2 < len(lines):
                return lines[i+1], lines[i+2]
        return FALLBACK_TLE
    except Exception:
        return FALLBACK_TLE

def get_satellite_position(line1, line2):
    """Oblicza pozycję i trajektorię ISS."""
    try:
        sat = Satrec.twoline2rv(line1, line2)
        now = datetime.now(timezone.utc)
        jd, fr = jday(now.year, now.month, now.day, now.hour, now.minute, now.second + now.microsecond * 1e-6)
        e, r, v = sat.sgp4(jd, fr)
        if e != 0: return None, None, [], []

        t_now = Time(now)
        teme = TEME(x=r[0]*u.km, y=r[1]*u.km, z=r[2]*u.km, obstime=t_now)
        itrs = teme.transform_to(ITRS(obstime=t_now))
        loc = EarthLocation(itrs.x, itrs.y, itrs.z)
        cur_lat, cur_lon = loc.lat.deg, loc.lon.deg
        
        traj_lats, traj_lons = [], []
        prev_lon = None
        for delta in range(-50 * 60, 50 * 60, 60):
            t_step = now + timedelta(seconds=delta)
            jd_s, fr_s = jday(t_step.year, t_step.month, t_step.day, t_step.hour, t_step.minute, t_step.second)
            _, r_s, _ = sat.sgp4(jd_s, fr_s)
            t_astropy = Time(t_step)
            teme_s = TEME(x=r_s[0]*u.km, y=r_s[1]*u.km, z=r_s[2]*u.km, obstime=t_astropy)
            itrs_s = teme_s.transform_to(ITRS(obstime=t_astropy))
            loc_s = EarthLocation(itrs_s.x, itrs_s.y, itrs_s.z)
            lon_s = loc_s.lon.deg
            if prev_lon is not None and abs(lon_s - prev_lon) > 180:
                traj_lats.append(None)
                traj_lons.append(None)
            traj_lats.append(loc_s.lat.deg)
            traj_lons.append(lon_s)
            prev_lon = lon_s

        return cur_lat, cur_lon, traj_lats, traj_lons
    except Exception:
        return None, None, [], []

# ===========================
# 2. BAZA DANYCH CZĘSTOTLIWOŚCI
# ===========================

data_freq = [
    # --- SATELITY ---
    {"MHz": "145.800", "Pasmo": "2m", "Mod": "NFM", "Kategoria": "Satelity", "Nazwa": "ISS (Głos)", "Opis": "Międzynarodowa Stacja Kosmiczna"},
    {"MHz": "137.100", "Pasmo": "2m", "Mod": "WFM", "Kategoria": "Satelity", "Nazwa": "NOAA 19", "Opis": "Mapy pogodowe (APT)"},
    
    # --- SŁUŻBY ---
    {"MHz": "148.6625", "Pasmo": "VHF", "Mod": "NFM", "Kategoria": "Służby", "Nazwa": "PSP (Krajowy)", "Opis": "Kanał Ratowniczo-Gaśniczy (B028)"},
    {"MHz": "149.150", "Pasmo": "VHF", "Mod": "NFM", "Kategoria": "Służby", "Nazwa": "PSP (Współdziałanie)", "Opis": "Kanał dowodzenia/współdziałania"},
    {"MHz": "150.100", "Pasmo": "VHF", "Mod": "NFM", "Kategoria": "Kolej", "Nazwa": "PKP (R1)", "Opis": "Radio-Stop / Szlakowy (Znika na rzecz GSM-R!)"},
    {"MHz": "150.150", "Pasmo": "VHF", "Mod": "NFM", "Kategoria": "Kolej", "Nazwa": "PKP (R2)", "Opis": "Radio-Stop / Szlakowy"},
    {"MHz": "169.000", "Pasmo": "VHF", "Mod": "NFM", "Kategoria": "Medyczne", "Nazwa": "Współdz. Med.", "Opis": "Lotnicze Pogotowie / Karetki"},
    {"MHz": "129.500", "Pasmo": "Air", "Mod": "AM", "Kategoria": "Lotnictwo", "Nazwa": "LPR (Ope.)", "Opis": "Przykładowy kanał operacyjny LPR"},

    # --- CYWILNE ---
    {"MHz": "446.006", "Pasmo": "PMR", "Mod": "NFM", "Kategoria": "PMR", "Nazwa": "PMR 1", "Opis": "Walkie-talkie bez licencji"},
    {"MHz": "446.031", "Pasmo": "PMR", "Mod": "NFM", "Kategoria": "PMR", "Nazwa": "PMR 3", "Opis": "Kanał preppersów (Reguła 3-3-3)"},
    {"MHz": "156.800", "Pasmo": "Marine", "Mod": "FM", "Kategoria": "Morskie", "Nazwa": "Kanał 16", "Opis": "Ratunkowy morski"},
    {"MHz": "145.500", "Pasmo": "2m", "Mod": "FM", "Kategoria": "Ham", "Nazwa": "Call Freq", "Opis": "Wywoławcza krótkofalarska"},
]

# ===========================
# 3. INTERFEJS APLIKACJI
# ===========================

st.title("📡 Radio Command Center")

# --- LICZNIK ---
st.markdown(
    f"""
    <div style="text-align: right; padding: 5px; font-size: 0.8em; color: gray;">
    Odwiedzin: <b>{visit_count}</b>
    </div>
    """,
    unsafe_allow_html=True
)

tab1, tab2 = st.tabs(["📡 Tracker & Skaner", "🆘 Łączność Kryzysowa"])

# ===========================
# ZAKŁADKA 1: Tracker ISS
# ===========================
with tab1:
    col_map, col_data = st.columns([3, 2])

    with col_map:
        st.subheader("Aktualna pozycja ISS")
        l1, l2 = fetch_iss_tle()
        if l1 and l2:
            lat, lon, path_lat, path_lon = get_satellite_position(l1, l2)
            if lat is not None:
                fig = go.Figure()
                
                # Trajektoria
                fig.add_trace(go.Scattergeo(
                    lat=path_lat, lon=path_lon, mode="lines",
                    line=dict(color="blue", width=2, dash="dot"), name="Orbita"
                ))

                # POZYCJA ISS - ZMIANA NA EMOJI 🛰️
                fig.add_trace(go.Scattergeo(
                    lat=[lat], lon=[lon], 
                    mode="text",  # Tryb tekstowy (emoji)
                    text=["🛰️"],  # Ikona satelity
                    textfont=dict(size=25), # Rozmiar ikony
                    name="ISS Teraz",
                    hoverinfo="text",
                    hovertext=f"ISS (ZARYA)<br>Lat: {lat:.2f}<br>Lon: {lon:.2f}"
                ))

                fig.update_layout(
                    margin={"r":0,"t":0,"l":0,"b":0}, height=400,
                    geo=dict(
                        projection_type="natural earth", showland=True,
                        landcolor="rgb(230, 230, 230)", showocean=True,
                        oceancolor="rgb(200, 225, 255)", showcountries=True
                    ), showlegend=False
                )
                st.plotly_chart(fig, use_container_width=True)
                if st.button("🔄 Odśwież pozycję"): st.rerun()
                st.caption(f"Lat: {lat:.2f}, Lon: {lon:.2f}")
            else:
                st.error("Błąd obliczeń orbitalnych.")
        else:
            st.error("Błąd pobierania danych TLE.")

    with col_data:
        st.subheader("Baza Częstotliwości")
        df = pd.DataFrame(data_freq)
        
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            search = st.text_input("🔍 Szukaj", "")
        with col_f2:
            cat_filter = st.multiselect("Kategoria", df["Kategoria"].unique())

        if search:
            df = df[df.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)]
        if cat_filter:
            df = df[df["Kategoria"].isin(cat_filter)]

        st.dataframe(
            df[["MHz", "Nazwa", "Mod", "Opis"]],
            column_config={
                "MHz": st.column_config.TextColumn("MHz", width="small"),
                "Nazwa": st.column_config.TextColumn("Nazwa", width="medium"),
                "Mod": st.column_config.TextColumn("Mod", width="small"),
            },
            use_container_width=True,
            hide_index=True,
            height=400
        )

# ===========================
# ZAKŁADKA 2: Łączność Kryzysowa
# ===========================
with tab2:
    st.header("🆘 Łączność w Sytuacjach Kryzysowych")
    c1, c2 = st.columns(2)

    with c1:
        st.info("### 📻 Reguła 3-3-3")
        st.markdown("""
        * **Kiedy:** Co **3 godziny** (3:00, 6:00, 9:00...)
        * **Jak długo:** Przez **3 minuty**.
        * **PMR:** Kanał **3** (446.031 MHz).
        * **CB:** Kanał **3**.
        """)

    with c2:
        st.warning("### 🚓 Służby i Prawo")
        st.markdown("""
        * **Nasłuch:** Legalny (pasma analogowe).
        * **Nadawanie:** Tylko PMR i CB bez licencji.
        * **PKP/PSP:** Zakłócanie surowo karane!
        """)

    st.divider()
    st.subheader("📋 Kluczowe kanały (Bez licencji)")
    
    k1, k2, k3 = st.columns(3)
    with k1:
        st.success("**PMR 446**")
        st.markdown("* **CH 3:** Preppersi\n* **CH 1:** Ogólny")
    with k2:
        st.success("**CB Radio**")
        st.markdown("* **CH 19:** Drogowy\n* **CH 9:** Ratunkowy")
    with k3:
        st.error("**Alarmy**")
        st.markdown("* **S.O.S:** ... --- ...\n* **MAYDAY:** Życie")

st.markdown("---")
st.caption("Aplikacja edukacyjna. Autor nie ponosi odpowiedzialności za niewłaściwe użycie sprzętu radiowego.")
