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
    return datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

# ===========================
# 1. LOGIKA SATELITARNA
# ===========================
@st.cache_data(ttl=3600)
def fetch_iss_tle():
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
                traj_lats.append(None); traj_lons.append(None)
            traj_lats.append(loc_s.lat.deg); traj_lons.append(lon_s)
            prev_lon = lon_s

        return cur_lat, cur_lon, traj_lats, traj_lons
    except Exception:
        return None, None, [], []

# ===========================
# 2. BAZA DANYCH (MERYTORYCZNA)
# ===========================

data_freq = [
    # --- SATELITY ---
    {"MHz": "145.800", "Pasmo": "2m", "Mod": "NFM", "Kategoria": "Satelity", "Nazwa": "ISS (Głos)", "Opis": "Region 1 Voice - Główny kanał foniczny ISS"},
    {"MHz": "145.825", "Pasmo": "2m", "Mod": "FM", "Kategoria": "Satelity", "Nazwa": "ISS (APRS)", "Opis": "Packet Radio 1200bps / Digipeater"},
    {"MHz": "437.800", "Pasmo": "70cm", "Mod": "FM", "Kategoria": "Satelity", "Nazwa": "ISS (Repeater)", "Opis": "Downlink przemiennika (Uplink: 145.990 z tonem 67.0)"},
    {"MHz": "436.795", "Pasmo": "70cm", "Mod": "FM", "Kategoria": "Satelity", "Nazwa": "SO-50 (SaudiSat)", "Opis": "Popularny satelita FM (Uplink: 145.850 z tonem 67.0)"},
    {"MHz": "137.100", "Pasmo": "VHF", "Mod": "WFM", "Kategoria": "Satelity", "Nazwa": "NOAA 19", "Opis": "APT - Analogowe zdjęcia Ziemi (przeloty popołudniowe)"},
    {"MHz": "137.620", "Pasmo": "VHF", "Mod": "WFM", "Kategoria": "Satelity", "Nazwa": "NOAA 15", "Opis": "APT - Najstarszy satelita, czasem gubi synchronizację"},
    {"MHz": "137.9125", "Pasmo": "VHF", "Mod": "WFM", "Kategoria": "Satelity", "Nazwa": "NOAA 18", "Opis": "APT - Przeloty poranne i wieczorne"},
    {"MHz": "137.900", "Pasmo": "VHF", "Mod": "QPSK", "Kategoria": "Satelity", "Nazwa": "Meteor M2-x", "Opis": "Rosyjski satelita cyfrowy (LRPT) - wymaga dekodera cyfrowego"},

    # --- LOTNICTWO (AM!) ---
    {"MHz": "121.500", "Pasmo": "Air", "Mod": "AM", "Kategoria": "Lotnictwo", "Nazwa": "Air Guard", "Opis": "Międzynarodowy kanał RATUNKOWY (wymaga radia z AM!)"},
    {"MHz": "129.500", "Pasmo": "Air", "Mod": "AM", "Kategoria": "Lotnictwo", "Nazwa": "LPR (Operacyjny)", "Opis": "Częsty kanał Lotniczego Pogotowia (może się różnić lokalnie)"},
    {"MHz": "118-136", "Pasmo": "Air", "Mod": "AM", "Kategoria": "Lotnictwo", "Nazwa": "Pasmo Lotnicze", "Opis": "Skanowanie (TWR, APP). Wymaga radia z AM (nie zwykły Baofeng)"},

    # --- SŁUŻBY ---
    {"MHz": "148.6625", "Pasmo": "VHF", "Mod": "NFM", "Kategoria": "Służby", "Nazwa": "PSP (B028)", "Opis": "Krajowy Kanał Ratowniczo-Gaśniczy (ogólnopolski)"},
    {"MHz": "149.150", "Pasmo": "VHF", "Mod": "NFM", "Kategoria": "Służby", "Nazwa": "PSP (Dowodzenie)", "Opis": "Kanał dowodzenia i współdziałania KDR"},
    {"MHz": "150.100", "Pasmo": "VHF", "Mod": "NFM", "Kategoria": "Kolej", "Nazwa": "PKP (R1)", "Opis": "UWAGA: Kolej przechodzi na cyfrowy GSM-R. Kanał zanikający."},
    {"MHz": "156.800", "Pasmo": "Marine", "Mod": "FM", "Kategoria": "Morskie", "Nazwa": "Kanał 16", "Opis": "Morski kanał ratunkowy i wywoławczy (Bałtyk/Śródlądowe)"},

    # --- CYWILNE / OBYWATELSKIE ---
    {"MHz": "446.00625", "Pasmo": "PMR", "Mod": "NFM", "Kategoria": "PMR", "Nazwa": "PMR 1", "Opis": "Najpopularniejszy kanał 'Walkie-Talkie' (dzieci, budowy, turyści)"},
    {"MHz": "446.03125", "Pasmo": "PMR", "Mod": "NFM", "Kategoria": "PMR", "Nazwa": "PMR 3", "Opis": "Kanał preppersów (Reguła 3-3-3). Kanał górski (Włochy/Alpy)"},
    {"MHz": "27.180", "Pasmo": "CB", "Mod": "AM", "Kategoria": "CB Radio", "Nazwa": "CB Kanał 19", "Opis": "Drogowy. Standard 'PL' (zera). Antymisiek. Głównie AM."},
    {"MHz": "27.060", "Pasmo": "CB", "Mod": "AM", "Kategoria": "CB Radio", "Nazwa": "CB Kanał 9", "Opis": "Ratunkowy. Standard 'PL' (zera)."},
    {"MHz": "145.500", "Pasmo": "2m", "Mod": "FM", "Kategoria": "Ham", "Nazwa": "VHF Call", "Opis": "Wywoławcza krótkofalarska (rozmowy lokalne)"},
    {"MHz": "433.500", "Pasmo": "70cm", "Mod": "FM", "Kategoria": "Ham", "Nazwa": "UHF Call", "Opis": "Wywoławcza krótkofalarska (rzadziej używana)"},
]

# ===========================
# 3. INTERFEJS APLIKACJI
# ===========================

with st.sidebar:
    st.header("🎛️ Panel Kontrolny")
    
    # Zegar UTC
    st.markdown(f"""
    <div style="background-color: #0e1117; padding: 10px; border-radius: 5px; text-align: center; border: 1px solid #333;">
        <div style="font-size: 0.9em; color: #888;">CZAS UTC (ZULU)</div>
        <div style="font-size: 1.8em; font-weight: bold; color: #00ff41; font-family: monospace;">{get_utc_time()}</div>
    </div>
    """, unsafe_allow_html=True)
    
    st.write("---")
    st.write(f"👁️ Odwiedzin: **{visit_count}**")
    
    # ROZBUDOWANY SŁOWNICZEK
    with st.expander("📚 Słowniczek Radiowy", expanded=True):
        st.markdown("""
        * **Squelch (SQ):** Blokada szumów. Ustawiasz tak, aby radio milczało, gdy nikt nie nadaje, a "otwierało się" na rozmowę.
        * **AM:** Modulacja amplitudy. Używana w **Lotnictwie** i na **CB Radio**. Zapewnia brak efektu "wypierania" (słychać dwóch rozmówców naraz).
        * **NFM / WFM:** Wąski (Służby/PMR) i Szeroki (Radio FM/NOAA) FM. Źle dobrany FM powoduje cichy lub charczący dźwięk.
        * **CTCSS / DCS:** "Podtony". Niesłyszalne dla ucha kody, które otwierają przemiennik. Bez nich przemiennik Cię nie usłyszy.
        * **Shift (Offset):** Różnica częstotliwości nadawania i odbioru. Niezbędne do pracy przez przemienniki (np. ISS Repeater).
        * **VFO:** Tryb, gdzie ręcznie wpisujesz częstotliwość z klawiatury.
        * **73:** Krótkofalarskie "Pozdrawiam".
        * **DX:** Łączność na bardzo dużą odległość.
        """)

    # CIEKAWOSTKI
    with st.expander("💡 Czy wiesz że?", expanded=False):
        st.markdown("""
        * **Dlaczego samoloty używają AM?** W modulacji FM silniejszy sygnał całkowicie wycina słabszy (Capture Effect). W lotnictwie to niebezpieczne – w AM kontroler słyszy (jako pisk/zakłócenie), że dwie osoby nadają jednocześnie.
        * **Efekt Dopplera:** Gdy ISS nadlatuje, słyszysz go ok. 3 kHz **wyżej** (np. 145.803), a gdy odlatuje – **niżej** (145.797). Musisz kręcić gałką strojenia!
        * **Zasięg radia ręcznego:** Zależy od horyzontu. Stojąc na ziemi masz zasięg ~5km. Ale z ISS (400 km w górę) usłyszysz sygnał na ponad 2000 km!
        """)

st.title("📡 Centrum Dowodzenia Radiowego")

# Zakładki
tab1, tab2 = st.tabs(["📡 Tracker & Skaner", "🆘 Łączność Kryzysowa"])

# --- ZAKŁADKA 1: MAPA I LISTA ---
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

                # Ikona ISS
                fig.add_trace(go.Scattergeo(
                    lat=[lat], lon=[lon], 
                    mode="text", text=["🛰️"], textfont=dict(size=30),
                    name="ISS Teraz",
                    hoverinfo="text",
                    hovertext=f"ISS (ZARYA)<br>Lat: {lat:.2f}<br>Lon: {lon:.2f}"
                ))

                # Mapa jasna
                fig.update_layout(
                    margin={"r":0,"t":0,"l":0,"b":0}, height=450,
                    geo=dict(
                        projection_type="natural earth", 
                        showland=True, 
                        landcolor="rgb(230, 230, 230)",
                        showocean=True, 
                        oceancolor="rgb(200, 225, 255)",
                        showcountries=True,
                        resolution=110
                    ),
                    showlegend=False
                )
                st.plotly_chart(fig, use_container_width=True)
                if st.button("🔄 Odśwież pozycję"): st.rerun()
            else:
                st.error("Błąd obliczeń orbitalnych.")
        else:
            st.error("Błąd pobierania danych TLE.")

    with col_data:
        st.subheader("Baza Częstotliwości (PL)")
        df = pd.DataFrame(data_freq)
        c_search, c_filter = st.columns([2,1])
        
        # POPRAWIONE: Polski placeholder zamiast "Choose options"
        with c_search: 
            search = st.text_input("🔍 Szukaj...", placeholder="Np. PMR, ISS")
        with c_filter: 
            cat_filter = st.multiselect("Kategorie", df["Kategoria"].unique(), placeholder="Wybierz...")

        if search: df = df[df.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)]
        if cat_filter: df = df[df["Kategoria"].isin(cat_filter)]

        st.dataframe(
            df[["MHz", "Nazwa", "Mod", "Opis"]],
            column_config={
                "MHz": st.column_config.TextColumn("MHz", width="small"),
                "Nazwa": st.column_config.TextColumn("Nazwa", width="medium"),
                "Mod": st.column_config.TextColumn("Mod", width="small"),
                "Opis": st.column_config.TextColumn("Opis", width="large"),
            },
            use_container_width=True, hide_index=True, height=450
        )

# --- ZAKŁADKA 2: KRYZYSOWE ---
with tab2:
    st.header("🆘 Procedury Awaryjne (Polska)")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.error("### 1. Reguła 3-3-3")
        st.markdown("""
        System nasłuchu w sytuacji kryzysowej (brak GSM):
        * **Kiedy?** Co 3 godziny (12:00, 15:00, 18:00...)
        * **Ile?** 3 minuty nasłuchu, potem wywołanie.
        * **Gdzie?** * PMR Kanał 3 (446.031 MHz)
            * CB Kanał 3 (26.980 MHz AM)
        """)
    with c2:
        st.warning("### 2. Ograniczenia Sprzętu")
        st.markdown("""
        * **Baofeng UV-5R:** Nie odbiera pasma lotniczego (AM). Nie nadaje się do nasłuchu CB (inne pasmo).
        * **Zasięg PMR:** W mieście realnie 500m - 1km. W górach do 5-10km.
        * **Antena:** Fabryczna "gumowa" antena to najsłabsze ogniwo. Warto mieć dłuższą (np. Nagoya 771).
        """)
    with c3:
        st.info("### 3. Komunikacja Kryzysowa")
        st.markdown("""
        **RAPORT S.A.L.T:**
        * **S (Size):** Ile osób/wielkość zdarzenia?
        * **A (Activity):** Co się dzieje?
        * **L (Location):** Gdzie jesteście?
        * **T (Time):** Kiedy to się stało?
        """)

st.markdown("---")
st.caption("Radio Command Center v3.2 | Dane satelitarne: CelesTrak | Czas: UTC")
