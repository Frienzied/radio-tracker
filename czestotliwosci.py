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
    return datetime.now(timezone.utc).strftime("%H:%M UTC")

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
    pmr_list = []
    base_freq = 446.00625
    step = 0.0125
    for i in range(16):
        channel = i + 1
        freq = base_freq + (i * step)
        desc = "Kanał ogólny"
        if channel == 1: desc = "Najpopularniejszy kanał (dzieci, nianie, budowy)"
        elif channel == 3: desc = "Kanał PREPPERSÓW (Reguła 3-3-3). Kanał górski (Alpy/Włochy)"
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
        elif channel == 3: desc = "Kanał Preppersów (System 3-3-3)"
        cb_list.append({
            "MHz": f"{f_pl:.3f}",
            "Pasmo": "CB",
            "Mod": "AM",
            "Kategoria": "CB Radio (Obywatelskie)",
            "Nazwa": f"CB Kanał {channel}",
            "Opis": desc
        })
    return cb_list

# ===========================
# 2. DANE STACJI
# ===========================
global_stations = [
    {"MHz": "0.225", "Pasmo": "LW", "Mod": "AM", "Kategoria": "Polska", "Nazwa": "Polskie Radio Jedynka", "Opis": "Solec Kujawski. Zasięg: cała Europa. Kluczowy w sytuacjach kryzysowych."},
    {"MHz": "0.198", "Pasmo": "LW", "Mod": "AM", "Kategoria": "Europa", "Nazwa": "BBC Radio 4", "Opis": "Wielka Brytania. Newsy i słuchowiska."},
    {"MHz": "6.000-6.200", "Pasmo": "49m", "Mod": "AM", "Kategoria": "Świat", "Nazwa": "Pasmo 49m (Wieczór)", "Opis": "Główne pasmo wieczorne dla stacji europejskich."},
    {"MHz": "9.400-9.900", "Pasmo": "31m", "Mod": "AM", "Kategoria": "Świat", "Nazwa": "Pasmo 31m (Całodobowe)", "Opis": "Najpopularniejsze pasmo międzynarodowe."},
    {"MHz": "4.625", "Pasmo": "SW", "Mod": "USB", "Kategoria": "Utility", "Nazwa": "UVB-76 (The Buzzer)", "Opis": "Rosyjska stacja numeryczna."},
    {"MHz": "14.230", "Pasmo": "20m", "Mod": "SSTV", "Kategoria": "Ham Radio", "Nazwa": "SSTV Call Freq", "Opis": "Przesyłanie obrazków (SSTV)."},
]

special_freqs = [
    {"MHz": "145.800", "Pasmo": "2m", "Mod": "NFM", "Kategoria": "Satelity", "Nazwa": "ISS (Głos)", "Opis": "Główny kanał foniczny ISS"},
    {"MHz": "145.825", "Pasmo": "2m", "Mod": "FM", "Kategoria": "Satelity", "Nazwa": "ISS (APRS)", "Opis": "Packet Radio / Digipeater"},
    {"MHz": "437.800", "Pasmo": "70cm", "Mod": "FM", "Kategoria": "Satelity", "Nazwa": "ISS (Repeater)", "Opis": "Downlink (Odbiór z ISS)"},
    {"MHz": "137.100", "Pasmo": "VHF", "Mod": "WFM", "Kategoria": "Satelity", "Nazwa": "NOAA 19", "Opis": "Zdjęcia APT"},
    {"MHz": "121.500", "Pasmo": "Air", "Mod": "AM", "Kategoria": "Lotnictwo", "Nazwa": "Air Guard", "Opis": "Ratunkowy lotniczy"},
    {"MHz": "148.6625", "Pasmo": "VHF", "Mod": "NFM", "Kategoria": "Służby", "Nazwa": "PSP (B028)", "Opis": "Krajowy Ratowniczo-Gaśniczy"},
    {"MHz": "156.800", "Pasmo": "Marine", "Mod": "FM", "Kategoria": "Morskie", "Nazwa": "Kanał 16", "Opis": "Ratunkowy morski"},
    {"MHz": "145.500", "Pasmo": "2m", "Mod": "FM", "Kategoria": "Ham", "Nazwa": "VHF Call", "Opis": "Wywoławcza (lokalna)"},
]

data_freq = special_freqs + generate_pmr_list() + generate_cb_list()

# ===========================
# 3. LOGIKA SATELITARNA
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
# 4. INTERFEJS APLIKACJI
# ===========================

# HEADER
c_title, c_clock, c_visits = st.columns([3, 1, 1])
with c_title: st.title("📡 Centrum Dowodzenia")
with c_clock: 
    st.markdown(f"<div style='text-align: right; color: #00ff41; font-family: monospace;'><b>ZULU (UTC):</b> {get_utc_time()}</div>", unsafe_allow_html=True)
with c_visits:
    st.markdown(f"<div style='text-align: right; color: gray;'>Odwiedzin: <b>{visit_count}</b></div>", unsafe_allow_html=True)

# ZAKŁADKI (6 ZAKŁADEK)
tabs = st.tabs([
    "📡 Tracker", 
    "☀️ Pogoda Kosmiczna",  # NOWA ZAKŁADKA
    "🆘 Kryzysowe", 
    "🌍 Czas", 
    "📻 Globalne",
    "📚 Słownik"
])

# --- TAB 1: TRACKER ---
with tabs[0]:
    col_map, col_data = st.columns([3, 2])
    with col_map:
        st.subheader("Pozycja ISS")
        l1, l2 = fetch_iss_tle()
        if l1 and l2:
            lat, lon, path_lat, path_lon = get_satellite_position(l1, l2)
            if lat:
                fig = go.Figure()
                fig.add_trace(go.Scattergeo(lat=path_lat, lon=path_lon, mode="lines", line=dict(color="blue", width=2, dash="dot")))
                fig.add_trace(go.Scattergeo(lat=[lat], lon=[lon], mode="text", text=["🛰️"], textfont=dict(size=30)))
                fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=450, geo=dict(projection_type="natural earth", showland=True, showocean=True, showcountries=True))
                st.plotly_chart(fig, use_container_width=True)
                if st.button("🔄 Odśwież"): st.rerun()
    with col_data:
        st.subheader("Częstotliwości (PL)")
        df = pd.DataFrame(data_freq)
        search = st.text_input("🔍 Szukaj...", placeholder="Np. Kanał 19")
        if search: df = df[df.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)]
        st.dataframe(df, use_container_width=True, hide_index=True, height=450)

# --- TAB 2: POGODA KOSMICZNA (NOWOŚĆ) ---
with tabs[1]:
    st.header("☀️ Pogoda Kosmiczna & Propagacja")
    st.markdown("Aktualne warunki do łączności dalekiego zasięgu (DX) na falach krótkich (HF) i VHF.")
    
    col_solar, col_info = st.columns([1, 1])
    
    with col_solar:
        # Widget N0NBH - standard branżowy
        st.image("https://www.hamqsl.com/solar101vhf.php", caption="Dane na żywo: N0NBH", use_container_width=False)
        st.markdown("---")
        # Mapa Greyline (Dzień/Noc)
        st.image("https://www.hamqsl.com/solarmap.php", caption="Mapa Dzień/Noc (Greyline)", use_container_width=True)

    with col_info:
        st.subheader("📉 Jak czytać dane?")
        
        st.success("### SFI (Solar Flux Index)")
        st.markdown("""
        "Paliwo" dla fal radiowych. Im wyższa liczba, tym lepsze odbicia od jonosfery.
        * **< 70:** Słabe warunki (Drut kolczasty zamiast anteny).
        * **70 - 100:** Średnie warunki.
        * **> 100:** Dobre warunki (Europa/USA słyszalne głośno).
        * **> 150:** Rewelacja! Łączności z Antypodami.
        """)
        
        st.error("### K-Index (Burze Magnetyczne)")
        st.markdown("""
        Poziom zakłóceń ziemskiego pola magnetycznego. Tu chcemy jak najmniej!
        * **0 - 2:** Cisza, czysty odbiór (Super!).
        * **3 - 4:** Lekkie zakłócenia.
        * **> 5:** Burza geomagnetyczna. Szumy, zaniki sygnału, możliwe zorze polarne.
        """)
        
        st.info("### Wskazówka")
        st.markdown("""
        **Szara Linia (Greyline):** Popatrz na mapę. Pasmo zmierzchu/świtu (przejście dzień-noc) to magiczny czas. Wzdłuż tej linii sygnał radiowy może okrążyć Ziemię! Wtedy najlepiej słuchać dalekich stacji.
        """)

# --- TAB 3: KRYZYSOWE ---
with tabs[2]:
    st.header("🆘 Procedury Awaryjne (Polska)")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.error("### 1. Reguła 3-3-3")
        st.markdown("* **Kiedy?** Co 3h (12:00, 15:00...)\n* **Gdzie?** PMR 3 / CB 3")
    with c2:
        st.warning("### 2. Sprzęt")
        st.markdown("* **Baofeng:** Dobry na PMR/Służby. Nie działa na CB/Lotnictwo (AM).\n* **Antena:** Dłuższa = Lepsza.")
    with c3:
        st.info("### 3. Raport SALT")
        st.markdown("* **S**ize (Ile osób?)\n* **A**ctivity (Co się dzieje?)\n* **L**ocation (Gdzie?)\n* **T**ime (Kiedy?)")

# --- TAB 4: CZAS ---
with tabs[3]:
    st.header("🌍 Czas na Świecie")
    zones = [("UTC", "UTC"), ("Warszawa", "Europe/Warsaw"), ("New York", "America/New_York"), ("Tokio", "Asia/Tokyo")]
    cols = st.columns(4)
    for i, (name, zone) in enumerate(zones):
        with cols[i]:
            st.markdown(f"<div style='background:#1E1E1E;padding:10px;border-radius:5px;text-align:center;border:1px solid #444;'> <div style='color:#888;'>{name}</div> <div style='color:#FFF;font-size:1.8em;font-family:monospace;'>{get_time_in_zone(zone)}</div></div>", unsafe_allow_html=True)

# --- TAB 5: GLOBALNE ---
with tabs[4]:
    st.header("📻 Stacje Globalne")
    st.dataframe(pd.DataFrame(global_stations), use_container_width=True, hide_index=True)

# --- TAB 6: SŁOWNIK ---
with tabs[5]:
    st.header("📚 Edukacja")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
        * **AM:** Modulacja amplitudy (Lotnictwo/CB).
        * **FM:** Modulacja częstotliwości (Służby/PMR).
        * **Squelch (SQ):** Blokada szumów.
        * **73:** Pozdrawiam.
        """)
    with c2:
        st.markdown("""
        * **Dlaczego samoloty w AM?** Aby słyszeć "nakładki" (dwa sygnały naraz).
        * **Doppler:** Zmiana częstotliwości ruchomego satelity (+/- 3kHz).
        """)

st.markdown("---")
st.caption("Centrum Dowodzenia Radiowego v7.0 | Dane: CelesTrak, N0NBH | Czas: UTC")
