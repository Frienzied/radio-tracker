import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import os
import pytz
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

def get_time_in_zone(zone_name):
    try:
        tz = pytz.timezone(zone_name)
        return datetime.now(tz).strftime("%H:%M")
    except: return "--:--"

def get_date_in_zone(zone_name):
    try:
        tz = pytz.timezone(zone_name)
        return datetime.now(tz).strftime("%d.%m.%Y")
    except: return ""

# ===========================
# 1. GENERATORY CZĘSTOTLIWOŚCI
# ===========================

def generate_pmr_list():
    """Generuje listę 16 kanałów PMR446."""
    pmr_list = []
    base_freq = 446.00625
    step = 0.0125
    
    for i in range(16):
        channel = i + 1
        freq = base_freq + (i * step)
        desc = "Kanał ogólny"
        
        # Opisy specjalne
        if channel == 1: desc = "Najpopularniejszy kanał (dzieci, nianie, budowy)"
        elif channel == 3: desc = "Kanał PREPPERSÓW (Reguła 3-3-3). Kanał górski (Alpy/Włochy)"
        elif channel == 8: desc = "Często używany jako wywoławczy (stary standard)"
        
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
    """Generuje listę 40 kanałów CB w standardzie PL ('zera')."""
    # Bazowa lista EU ("piątki") - w Polsce odejmujemy 5 kHz (0.005 MHz)
    # Zauważ "dziury" między kanałami (alpha channels) - dlatego lista jest "na sztywno" lub z logiką
    # Dla uproszczenia i pewności używamy tabeli wzorcowej
    
    cb_freqs_eu = [
        26.965, 26.975, 26.985, 27.005, 27.015, 27.025, 27.035, 27.055, 27.065, 27.075, # 1-10
        27.085, 27.105, 27.115, 27.125, 27.135, 27.155, 27.165, 27.175, 27.185, 27.205, # 11-20
        27.215, 27.225, 27.255, 27.235, 27.245, 27.265, 27.275, 27.285, 27.295, 27.305, # 21-30 (Uwaga: ch23-25 są pomieszane w standardzie!)
        27.315, 27.325, 27.335, 27.345, 27.355, 27.365, 27.375, 27.385, 27.395, 27.405  # 31-40
    ]
    
    # Korekta kolejności dla kanałów 23, 24, 25 (Standard CB jest dziwny)
    # Powyższa lista 21-30: 21, 22, 25, 23, 24... tak to wygląda w częstotliwościach rosnąco,
    # ale my chcemy po numerach kanałów.
    # Prawidłowa sekwencja częstotliwości dla kanałów 1-40:
    base_freqs = [
        26.965, 26.975, 26.985, 27.005, 27.015, 27.025, 27.035, 27.055, 27.065, 27.075,
        27.085, 27.105, 27.115, 27.125, 27.135, 27.155, 27.165, 27.175, 27.185, 27.205,
        27.215, 27.225, 27.255, 27.235, 27.245, 27.265, 27.275, 27.285, 27.295, 27.305,
        27.315, 27.325, 27.335, 27.345, 27.355, 27.365, 27.375, 27.385, 27.395, 27.405
    ]

    cb_list = []
    for i, f_eu in enumerate(base_freqs):
        channel = i + 1
        # Konwersja na PL (minus 5 kHz)
        f_pl = f_eu - 0.005
        
        desc = "Kanał ogólny"
        if channel == 9: desc = "!!! RATUNKOWY !!!"
        elif channel == 19: desc = "!!! DROGOWY !!! (Antymisiek)"
        elif channel == 2: desc = "Zwyczajowy kanał TAXI / Piguła"
        elif channel == 28: desc = "Często stacje bazowe / Wywoławczy w niektórych regionach"
        elif channel == 3: desc = "Kanał Preppersów (System 3-3-3)"

        cb_list.append({
            "MHz": f"{f_pl:.3f}",
            "Pasmo": "CB",
            "Mod": "AM", # W Polsce głównie AM
            "Kategoria": "CB Radio (Obywatelskie)",
            "Nazwa": f"CB Kanał {channel}",
            "Opis": desc
        })
    return cb_list

# ===========================
# 2. LOGIKA SATELITARNA
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
# 3. GŁÓWNA BAZA DANYCH
# ===========================

# Lista specjalna (Satelity, Służby, Lotnictwo)
special_freqs = [
    # --- SATELITY ---
    {"MHz": "145.800", "Pasmo": "2m", "Mod": "NFM", "Kategoria": "Satelity", "Nazwa": "ISS (Głos)", "Opis": "Region 1 Voice - Główny kanał foniczny ISS"},
    {"MHz": "145.825", "Pasmo": "2m", "Mod": "FM", "Kategoria": "Satelity", "Nazwa": "ISS (APRS)", "Opis": "Packet Radio 1200bps / Digipeater"},
    {"MHz": "437.800", "Pasmo": "70cm", "Mod": "FM", "Kategoria": "Satelity", "Nazwa": "ISS (Repeater)", "Opis": "Downlink przemiennika (Uplink: 145.990 z tonem 67.0)"},
    {"MHz": "436.795", "Pasmo": "70cm", "Mod": "FM", "Kategoria": "Satelity", "Nazwa": "SO-50 (SaudiSat)", "Opis": "Popularny satelita FM (Uplink: 145.850 z tonem 67.0)"},
    {"MHz": "137.100", "Pasmo": "VHF", "Mod": "WFM", "Kategoria": "Satelity", "Nazwa": "NOAA 19", "Opis": "APT - Analogowe zdjęcia Ziemi (przeloty popołudniowe)"},
    {"MHz": "137.620", "Pasmo": "VHF", "Mod": "WFM", "Kategoria": "Satelity", "Nazwa": "NOAA 15", "Opis": "APT - Najstarszy satelita, czasem gubi synchronizację"},
    
    # --- LOTNICTWO (AM!) ---
    {"MHz": "121.500", "Pasmo": "Air", "Mod": "AM", "Kategoria": "Lotnictwo", "Nazwa": "Air Guard", "Opis": "Międzynarodowy kanał RATUNKOWY (wymaga radia z AM!)"},
    {"MHz": "129.500", "Pasmo": "Air", "Mod": "AM", "Kategoria": "Lotnictwo", "Nazwa": "LPR (Operacyjny)", "Opis": "Częsty kanał Lotniczego Pogotowia (może się różnić lokalnie)"},
    {"MHz": "118-136", "Pasmo": "Air", "Mod": "AM", "Kategoria": "Lotnictwo", "Nazwa": "Pasmo Lotnicze", "Opis": "Skanowanie (TWR, APP). Wymaga radia z AM."},

    # --- SŁUŻBY ---
    {"MHz": "148.6625", "Pasmo": "VHF", "Mod": "NFM", "Kategoria": "Służby", "Nazwa": "PSP (B028)", "Opis": "Krajowy Kanał Ratowniczo-Gaśniczy (ogólnopolski)"},
    {"MHz": "149.150", "Pasmo": "VHF", "Mod": "NFM", "Kategoria": "Służby", "Nazwa": "PSP (Dowodzenie)", "Opis": "Kanał dowodzenia i współdziałania KDR"},
    {"MHz": "156.800", "Pasmo": "Marine", "Mod": "FM", "Kategoria": "Morskie", "Nazwa": "Kanał 16", "Opis": "Morski kanał ratunkowy i wywoławczy"},

    # --- HAM ---
    {"MHz": "145.500", "Pasmo": "2m", "Mod": "FM", "Kategoria": "Krótkofalarskie", "Nazwa": "VHF Call", "Opis": "Wywoławcza (rozmowy lokalne)"},
    {"MHz": "433.500", "Pasmo": "70cm", "Mod": "FM", "Kategoria": "Krótkofalarskie", "Nazwa": "UHF Call", "Opis": "Wywoławcza (rzadziej używana)"},
]

# Łączymy wszystko w jedną wielką listę
data_freq = special_freqs + generate_pmr_list() + generate_cb_list()

# ===========================
# 4. INTERFEJS APLIKACJI
# ===========================

with st.sidebar:
    st.header("🎛️ Panel Kontrolny")
    
    # Zegar UTC (Sidebar)
    st.markdown(f"""
    <div style="background-color: #0e1117; padding: 10px; border-radius: 5px; text-align: center; border: 1px solid #333;">
        <div style="font-size: 0.9em; color: #888;">CZAS UTC (ZULU)</div>
        <div style="font-size: 1.8em; font-weight: bold; color: #00ff41; font-family: monospace;">{get_utc_time()}</div>
    </div>
    """, unsafe_allow_html=True)
    
    st.write("---")
    st.write(f"👁️ Odwiedzin: **{visit_count}**")
    
    with st.expander("📚 Słowniczek Radiowy", expanded=True):
        st.markdown("""
        * **Squelch (SQ):** Blokada szumów. Wycisza szum tła.
        * **AM:** Modulacja amplitudy (Lotnictwo, CB Radio).
        * **NFM:** Wąski FM (PMR, Służby).
        * **WFM:** Szeroki FM (Radio komercyjne, NOAA).
        * **CTCSS:** Kody otwierające przemienniki.
        * **Shift:** Przesunięcie nadawania (dla przemienników).
        * **73:** Pozdrowienia.
        * **QTH:** Lokalizacja.
        * **DX:** Łączność dalekiego zasięgu.
        """)

    with st.expander("💡 Ciekawostki", expanded=False):
        st.markdown("""
        * **Dlaczego polskie CB to 'Zera'?** Większość świata używa częstotliwości kończących się na 5 (np. 27.185). W Polsce historycznie przyjęto końcówki 0 (27.180). Nowoczesne radia mają przełącznik "EU/PL".
        * **PMR zasięg:** Rekord łączności PMR446 to ponad 500 km (z góry na górę). W mieście to często tylko 300 metrów.
        """)

st.title("📡 Centrum Dowodzenia Radiowego")

# Zakładki
tab1, tab2, tab3 = st.tabs(["📡 Tracker & Skaner", "🆘 Łączność Kryzysowa", "🌍 Czas na Świecie"])

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
                fig.add_trace(go.Scattergeo(
                    lat=path_lat, lon=path_lon, mode="lines",
                    line=dict(color="blue", width=2, dash="dot"), name="Orbita"
                ))
                fig.add_trace(go.Scattergeo(
                    lat=[lat], lon=[lon], 
                    mode="text", text=["🛰️"], textfont=dict(size=30),
                    name="ISS Teraz",
                    hoverinfo="text",
                    hovertext=f"ISS (ZARYA)<br>Lat: {lat:.2f}<br>Lon: {lon:.2f}"
                ))
                fig.update_layout(
                    margin={"r":0,"t":0,"l":0,"b":0}, height=450,
                    geo=dict(
                        projection_type="natural earth", 
                        showland=True, landcolor="rgb(230, 230, 230)",
                        showocean=True, oceancolor="rgb(200, 225, 255)",
                        showcountries=True, resolution=110
                    ),
                    showlegend=False
                )
                st.plotly_chart(fig, use_container_width=True)
                if st.button("🔄 Odśwież pozycję"): st.rerun()
            else:
                st.error("Błąd obliczeń.")
        else:
            st.error("Błąd TLE.")

    with col_data:
        st.subheader("Baza Częstotliwości")
        df = pd.DataFrame(data_freq)
        c_search, c_filter = st.columns([2,1])
        with c_search: 
            search = st.text_input("🔍 Szukaj...", placeholder="Np. Kanał 19, PMR 3")
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
        * **Ile?** 3 minuty nasłuchu.
        * **Gdzie?** PMR Kanał 3 / CB Kanał 3
        """)
    with c2:
        st.warning("### 2. Sprzęt")
        st.markdown("""
        * **Baofeng UV-5R:** Nie odbiera AM (Lotnictwo/CB). Dobre do PMR i Służb.
        * **Zasięg:** Miasto: 1km. Otwarty teren: 5km. Góry/Kosmos: >100km.
        * **Antena:** Długa antena (np. Nagoya) poprawia odbiór o 50%.
        """)
    with c3:
        st.info("### 3. Komunikacja")
        st.markdown("""
        **RAPORT S.A.L.T:**
        * **S (Size):** Ile osób?
        * **A (Activity):** Co się dzieje?
        * **L (Location):** Gdzie?
        * **T (Time):** Kiedy?
        """)

# --- ZAKŁADKA 3: STREFY CZASOWE ---
with tab3:
    st.header("🌍 Czas na Świecie")
    
    zones = [
        ("UTC (Zulu)", "UTC"),
        ("Polska (Warszawa)", "Europe/Warsaw"),
        ("USA (New York)", "America/New_York"),
        ("USA (Los Angeles)", "America/Los_Angeles"),
        ("Japonia (Tokio)", "Asia/Tokyo"),
        ("Australia (Sydney)", "Australia/Sydney")
    ]

    cols = st.columns(3)
    for i, (name, zone) in enumerate(zones):
        with cols[i % 3]:
            time_str = get_time_in_zone(zone)
            date_str = get_date_in_zone(zone)
            st.markdown(f"""
            <div style="
                background-color: #1E1E1E; 
                padding: 15px; 
                border-radius: 10px; 
                border: 1px solid #444; 
                text-align: center;
                margin-bottom: 20px;">
                <div style="color: #888; font-size: 0.9em; margin-bottom: 5px;">{name}</div>
                <div style="color: #FFF; font-size: 2.2em; font-family: monospace; font-weight: bold;">{time_str}</div>
                <div style="color: #666; font-size: 0.8em;">{date_str}</div>
            </div>
            """, unsafe_allow_html=True)

st.markdown("---")
st.caption("Centrum Dowodzenia Radiowego v4.1 | Dane: CelesTrak | Czas: UTC")
