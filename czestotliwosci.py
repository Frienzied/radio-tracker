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
# 1. KONFIGURACJA I STYL (CSS)
# ===========================
st.set_page_config(
    page_title="Centrum Dowodzenia Radiowego",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS dla wyglądu "Command Center"
st.markdown("""
    <style>
        /* Główne tło */
        .stApp {
            background-color: #0e1117;
        }
        /* Nagłówki */
        h1, h2, h3 {
            color: #e0e0e0;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        /* Karty i kontenery */
        .stContainer {
            border: 1px solid #303030;
            border-radius: 10px;
            padding: 15px;
            background-color: #161b22;
        }
        /* Przyciski */
        div.stButton > button {
            background-color: #238636;
            color: white;
            border-radius: 8px;
            border: none;
            padding: 0.5rem 1rem;
            transition: all 0.3s;
        }
        div.stButton > button:hover {
            background-color: #2ea043;
            box-shadow: 0 0 10px #2ea043;
        }
        /* Zegar w nagłówku */
        .digital-clock {
            font-family: 'Courier New', monospace;
            background-color: #000;
            color: #00ff41;
            padding: 5px 10px;
            border-radius: 5px;
            border: 1px solid #00ff41;
            display: inline-block;
            box-shadow: 0 0 5px #00ff41;
        }
        /* Tabele */
        .dataframe {
            font-size: 14px;
        }
    </style>
""", unsafe_allow_html=True)

# ===========================
# 2. FUNKCJE POMOCNICZE (CACHED)
# ===========================
LOGBOOK_FILE = "radio_logbook.csv"

def load_logbook():
    if os.path.exists(LOGBOOK_FILE):
        return pd.read_csv(LOGBOOK_FILE)
    return pd.DataFrame(columns=["Data", "Godzina (UTC)", "Freq (MHz)", "Stacja", "Modulacja", "Raport"])

def save_logbook(df):
    df.to_csv(LOGBOOK_FILE, index=False)

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

def get_utc_time(): return datetime.now(timezone.utc).strftime("%H:%M UTC")

def get_time_in_zone(zone_name):
    try: return datetime.now(pytz.timezone(zone_name)).strftime("%H:%M")
    except: return "--:--"

def latlon_to_maidenhead(lat, lon):
    try:
        A = ord('A')
        lon += 180; lat += 90
        f_lon = int(lon/20); f_lat = int(lat/10)
        lon -= f_lon*20; lat -= f_lat*10
        s_lon = int(lon/2); s_lat = int(lat)
        lon -= s_lon*2; lat -= s_lat
        ss_lon = int(lon*12); ss_lat = int(lat*24)
        return f"{chr(A+f_lon)}{chr(A+f_lat)}{s_lon}{s_lat}{chr(A+ss_lon)}{chr(A+ss_lat)}"
    except: return "Error"

# ===========================
# 3. GENERATORY DANYCH (CACHED FOR PERFORMANCE)
# ===========================

@st.cache_data
def get_all_frequencies_data():
    """Generuje wszystkie statyczne listy raz przy starcie aplikacji."""
    
    # 1. PMR
    pmr_list = []
    base = 446.00625
    for i in range(16):
        ch = i+1
        desc = "Kanał ogólny"
        if ch==1: desc = "Najpopularniejszy (budowy, dzieci)"
        elif ch==3: desc = "Preppersi / Góry (3-3-3)"
        pmr_list.append({"MHz": f"{base+(i*0.0125):.5f}", "Pasmo": "PMR", "Mod": "NFM", "Kategoria": "PMR", "Nazwa": f"PMR {ch}", "Opis": desc})

    # 2. CB
    cb_list = []
    cb_freqs = [26.965, 26.975, 26.985, 27.005, 27.015, 27.025, 27.035, 27.055, 27.065, 27.075,
                27.085, 27.105, 27.115, 27.125, 27.135, 27.155, 27.165, 27.175, 27.185, 27.205,
                27.215, 27.225, 27.255, 27.235, 27.245, 27.265, 27.275, 27.285, 27.295, 27.305,
                27.315, 27.325, 27.335, 27.345, 27.355, 27.365, 27.375, 27.385, 27.395, 27.405]
    for i, f in enumerate(cb_freqs):
        ch = i+1
        desc = "Kanał ogólny"
        if ch==9: desc = "!!! RATUNKOWY !!!"
        elif ch==19: desc = "!!! DROGOWY !!! (Antymisiek)"
        elif ch==28: desc = "Wywoławczy (Baza)"
        cb_list.append({"MHz": f"{f-0.005:.3f}", "Pasmo": "CB", "Mod": "AM", "Kategoria": "CB Radio", "Nazwa": f"CB {ch}", "Opis": desc})

    # 3. Specjalne
    special_freqs = [
        {"MHz": "145.800", "Pasmo": "2m", "Mod": "NFM", "Kategoria": "Satelity", "Nazwa": "ISS (Głos)", "Opis": "Region 1 Voice"},
        {"MHz": "145.825", "Pasmo": "2m", "Mod": "FM", "Kategoria": "Satelity", "Nazwa": "ISS (APRS)", "Opis": "Packet Radio"},
        {"MHz": "437.800", "Pasmo": "70cm", "Mod": "FM", "Kategoria": "Satelity", "Nazwa": "ISS (Repeater)", "Opis": "Uplink: 145.990"},
        {"MHz": "137.100", "Pasmo": "VHF", "Mod": "WFM", "Kategoria": "Satelity", "Nazwa": "NOAA 19", "Opis": "APT Weather"},
        {"MHz": "121.500", "Pasmo": "Air", "Mod": "AM", "Kategoria": "Lotnictwo", "Nazwa": "Air Guard", "Opis": "Międzynarodowy Ratunkowy"},
        {"MHz": "129.500", "Pasmo": "Air", "Mod": "AM", "Kategoria": "Lotnictwo", "Nazwa": "LPR (Operacyjny)", "Opis": "Lotnicze Pogotowie"},
        {"MHz": "148.6625", "Pasmo": "VHF", "Mod": "NFM", "Kategoria": "Służby", "Nazwa": "PSP (B028)", "Opis": "Krajowy Kanał Ratowniczo-Gaśniczy"},
        {"MHz": "156.800", "Pasmo": "Marine", "Mod": "FM", "Kategoria": "Morskie", "Nazwa": "Kanał 16", "Opis": "Morski Ratunkowy"},
        {"MHz": "145.500", "Pasmo": "2m", "Mod": "FM", "Kategoria": "Ham", "Nazwa": "VHF Call", "Opis": "Wywoławcza (2m)"},
    ]

    return pd.DataFrame(special_freqs + pmr_list + cb_list)

@st.cache_data
def get_static_lists():
    """Zwraca statyczne listy (przemienniki, stacje globalne, websdr)."""
    repeaters = [
        {"Znak": "SR5WA", "Freq": "439.350", "CTCSS": "127.3", "Lat": 52.23, "Lon": 21.01, "Loc": "Warszawa (PKiN)", "Shift": "-7.6"},
        {"Znak": "SR5W", "Freq": "145.600", "CTCSS": "127.3", "Lat": 52.21, "Lon": 20.98, "Loc": "Warszawa", "Shift": "-0.6"},
        {"Znak": "SR6J", "Freq": "145.675", "CTCSS": "94.8", "Lat": 50.78, "Lon": 15.56, "Loc": "Śnieżne Kotły", "Shift": "-0.6"},
        {"Znak": "SR9P", "Freq": "438.900", "CTCSS": "103.5", "Lat": 50.06, "Lon": 19.94, "Loc": "Kraków", "Shift": "-7.6"},
        {"Znak": "SR9C", "Freq": "145.775", "CTCSS": "103.5", "Lat": 49.65, "Lon": 19.88, "Loc": "Chorągwica", "Shift": "-0.6"},
        {"Znak": "SR2Z", "Freq": "145.725", "CTCSS": "94.8", "Lat": 54.37, "Lon": 18.60, "Loc": "Gdańsk", "Shift": "-0.6"},
        {"Znak": "SR2C", "Freq": "438.800", "CTCSS": "94.8", "Lat": 54.52, "Lon": 18.53, "Loc": "Gdynia", "Shift": "-7.6"},
        {"Znak": "SR3PO", "Freq": "438.850", "CTCSS": "110.9", "Lat": 52.40, "Lon": 16.92, "Loc": "Poznań", "Shift": "-7.6"},
        {"Znak": "SR8L", "Freq": "145.625", "CTCSS": "107.2", "Lat": 51.24, "Lon": 22.57, "Loc": "Lublin", "Shift": "-0.6"},
        {"Znak": "SR4J", "Freq": "439.100", "CTCSS": "88.5", "Lat": 53.77, "Lon": 20.48, "Loc": "Olsztyn", "Shift": "-7.6"},
        {"Znak": "SR7V", "Freq": "145.6875", "CTCSS": "88.5", "Lat": 50.80, "Lon": 19.11, "Loc": "Częstochowa", "Shift": "-0.6"},
        {"Znak": "SR1Z", "Freq": "145.6375", "CTCSS": "118.8", "Lat": 53.42, "Lon": 14.55, "Loc": "Szczecin", "Shift": "-0.6"},
    ]
    
    global_s = [
        {"MHz": "0.225", "Pasmo": "LW", "Mod": "AM", "Nazwa": "Polskie Radio 1", "Opis": "Solec Kujawski. Zasięg: cała Europa."},
        {"MHz": "0.198", "Pasmo": "LW", "Mod": "AM", "Nazwa": "BBC Radio 4", "Opis": "UK News."},
        {"MHz": "0.153", "Pasmo": "LW", "Mod": "AM", "Nazwa": "Radio Romania", "Opis": "Antena Satelor."},
        {"MHz": "6.000", "Pasmo": "49m", "Mod": "AM", "Nazwa": "Pasmo 49m", "Opis": "Wieczór Europa."},
        {"MHz": "9.400", "Pasmo": "31m", "Mod": "AM", "Nazwa": "Pasmo 31m", "Opis": "Całodobowe."},
        {"MHz": "4.625", "Pasmo": "SW", "Mod": "USB", "Nazwa": "UVB-76", "Opis": "The Buzzer (Rosyjska stacja numeryczna)."},
        {"MHz": "5.450", "Pasmo": "SW", "Mod": "USB", "Nazwa": "RAF Volmet", "Opis": "Pogoda lotnicza."},
    ]
    
    websdr = [
        {"Nazwa": "WebSDR Twente", "Kraj": "Holandia 🇳🇱", "Link": "http://websdr.ewi.utwente.nl:8901/", "Opis": "Absolutny nr 1 na świecie (0-30 MHz)."},
        {"Nazwa": "WebSDR Zielona Góra", "Kraj": "Polska 🇵🇱", "Link": "http://websdr.sp3pgx.uz.zgora.pl:8901/", "Opis": "Satelity, VHF/UHF, Służby."},
        {"Nazwa": "Klub SP2PMK", "Kraj": "Polska 🇵🇱", "Link": "http://sp2pmk.uni.torun.pl:8901/", "Opis": "Toruń. Rozmowy krajowe (KF)."},
        {"Nazwa": "KiwiSDR Map", "Kraj": "Świat 🌍", "Link": "http://rx.linkfanel.net/", "Opis": "Mapa tysięcy odbiorników."},
    ]
    return pd.DataFrame(repeaters), pd.DataFrame(global_s), pd.DataFrame(websdr)

@st.cache_data
def get_psp_data():
    psp = []
    # KSRG i Współdziałanie
    psp.append({"Kanał": "B028", "MHz": "148.6625", "Typ": "Krajowy (KSRG)", "Opis": "Ratowniczo-Gaśniczy (Cała Polska)"})
    psp.append({"Kanał": "B002", "MHz": "149.1500", "Typ": "Współdziałania", "Opis": "Dowodzenie i Współdziałanie"})
    # Symulacja siatki
    base = 148.6750
    for i in range(1, 10):
        f = base + (i * 0.0125)
        psp.append({"Kanał": f"B{i+30:03d}", "MHz": f"{f:.4f}", "Typ": "Powiatowy", "Opis": "Kanał operacyjny"})
        
    prefixes = [
        {"Prefix": "250", "Woj": "Dolnośląskie", "Miasto": "Wrocław"},
        {"Prefix": "300", "Woj": "Kujawsko-Pom.", "Miasto": "Toruń"},
        {"Prefix": "460", "Woj": "Mazowieckie", "Miasto": "Warszawa"},
        {"Prefix": "600", "Woj": "Pomorskie", "Miasto": "Gdańsk"},
        {"Prefix": "630", "Woj": "Śląskie", "Miasto": "Katowice"},
        {"Prefix": "730", "Woj": "Wielkopolskie", "Miasto": "Poznań"},
    ]
    return pd.DataFrame(psp), pd.DataFrame(prefixes)

# ===========================
# 4. LOGIKA SATELITARNA (CACHED & ROBUST)
# ===========================
@st.cache_data(ttl=3600)
def fetch_iss_tle():
    """Zwraca TLE ISS z cache (ważne 1h) lub fallback."""
    FALLBACK = ("1 25544U 98067A   24017.54519514  .00016149  00000+0  29290-3 0  9993", 
                "2 25544  51.6415 158.8530 0005786 244.1866 179.9192 15.49622591435056")
    try:
        r = requests.get("https://celestrak.org/NORAD/elements/stations.txt", headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
        lines = [l.strip() for l in r.text.splitlines() if l.strip()]
        for i, l in enumerate(lines):
            if "ISS (ZARYA)" in l and i+2 < len(lines): return lines[i+1], lines[i+2]
        return FALLBACK
    except: return FALLBACK

@st.cache_data(ttl=60) # Cache pozycji na 1 minutę
def get_cached_satellite_position(l1, l2):
    """Oblicza trajektorię. Cache na 60s aby nie liczyć przy każdym odświeżeniu UI."""
    try:
        sat = Satrec.twoline2rv(l1, l2)
        now = datetime.now(timezone.utc)
        jd, fr = jday(now.year, now.month, now.day, now.hour, now.minute, now.second)
        e, r, v = sat.sgp4(jd, fr)
        if e != 0: return None, None, [], []
        
        t = Time(now)
        teme = TEME(x=r[0]*u.km, y=r[1]*u.km, z=r[2]*u.km, obstime=t)
        itrs = teme.transform_to(ITRS(obstime=t))
        loc = EarthLocation(itrs.x, itrs.y, itrs.z)
        
        # Trajektoria
        lats, lons = [], []
        prev_lon = None
        for d in range(-50*60, 50*60, 120): # Co 2 minuty dla wydajności
            ts = now + timedelta(seconds=d)
            j, f = jday(ts.year, ts.month, ts.day, ts.hour, ts.minute, ts.second)
            _, rs, _ = sat.sgp4(j, f)
            loc_s = EarthLocation(TEME(x=rs[0]*u.km, y=rs[1]*u.km, z=rs[2]*u.km, obstime=Time(ts)).transform_to(ITRS(obstime=Time(ts))).x,
                                  TEME(x=rs[0]*u.km, y=rs[1]*u.km, z=rs[2]*u.km, obstime=Time(ts)).transform_to(ITRS(obstime=Time(ts))).y,
                                  TEME(x=rs[0]*u.km, y=rs[1]*u.km, z=rs[2]*u.km, obstime=Time(ts)).transform_to(ITRS(obstime=Time(ts))).z)
            ln = loc_s.lon.deg
            if prev_lon and abs(ln - prev_lon) > 180: lats.append(None); lons.append(None)
            lats.append(loc_s.lat.deg); lons.append(ln); prev_lon = ln
            
        return loc.lat.deg, loc.lon.deg, lats, lons
    except: return None, None, [], []

# ===========================
# 5. GŁÓWNY LAYOUT
# ===========================

# Nagłówek i Zegar
c1, c2, c3 = st.columns([4, 2, 1])
with c1: st.title("📡 Centrum Dowodzenia")
with c2: st.markdown(f"<div class='digital-clock'>ZULU: {get_utc_time()}</div>", unsafe_allow_html=True)
with c3: st.caption(f"Odwiedzin: {visit_count}")

# POBRANIE DANYCH (SZYBKIE)
df_freq = get_all_frequencies_data()
df_rep, df_glob, df_sdr = get_static_lists()
df_psp, df_pref = get_psp_data()

# ZAKŁADKI
tabs = st.tabs([
    "📡 Tracker", "☀️ Pogoda", "🆘 Kryzysowe", "🌍 Czas", "📻 Globalne", 
    "📚 Edukacja", "🗺️ Przemienniki", "🧮 Kalkulatory", "🌐 WebSDR", 
    "📝 Logbook", "🚒 Straż"
])

# --- TRACKER ---
with tabs[0]:
    c_map, c_list = st.columns([3, 2])
    with c_map:
        with st.container():
            st.subheader("Orbita ISS")
            l1, l2 = fetch_iss_tle()
            lat, lon, t_lat, t_lon = get_cached_satellite_position(l1, l2)
            if lat:
                fig = go.Figure()
                fig.add_trace(go.Scattergeo(lat=t_lat, lon=t_lon, mode="lines", line=dict(color="#00ff41", width=1), name="Orbita"))
                fig.add_trace(go.Scattergeo(lat=[lat], lon=[lon], mode="text", text=["🛰️"], textfont=dict(size=40), name="ISS"))
                fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=400, 
                                  geo=dict(projection_type="natural earth", showland=True, landcolor="#1f2630", showocean=True, oceancolor="#0e1117", showcountries=True, countrycolor="#444"))
                st.plotly_chart(fig, use_container_width=True)
                if st.button("🔄 Odśwież pozycję"): st.rerun()
    with c_list:
        with st.container():
            st.subheader("Baza Częstotliwości")
            col_s, col_f = st.columns([2,1])
            search = col_s.text_input("Szukaj", placeholder="Wpisz frazę...")
            cat = col_f.multiselect("Filtr", df_freq["Kategoria"].unique())
            
            df_view = df_freq
            if search: df_view = df_view[df_view.apply(lambda r: r.astype(str).str.contains(search, case=False).any(), axis=1)]
            if cat: df_view = df_view[df_view["Kategoria"].isin(cat)]
            
            st.dataframe(df_view, height=400, hide_index=True, use_container_width=True)

# --- POGODA ---
with tabs[1]:
    st.header("☀️ Pogoda Kosmiczna")
    c1, c2 = st.columns(2)
    with c1: st.image("https://www.hamqsl.com/solar101vhf.php", caption="Propagacja (N0NBH)")
    with c2: st.image("https://www.hamqsl.com/solarmap.php", caption="Greyline (Dzień/Noc)")

# --- KRYZYSOWE ---
with tabs[2]:
    st.header("🆘 Procedury Awaryjne")
    c1, c2, c3 = st.columns(3)
    with c1: 
        with st.container():
            st.error("1. Reguła 3-3-3")
            st.markdown("**Kiedy?** Co 3 godziny\n**Ile?** 3 minuty nasłuchu\n**Gdzie?** PMR 3 / CB 3")
    with c2:
        with st.container():
            st.warning("2. Sprzęt")
            st.markdown("Baofeng = FM (Służby/PMR). Nie odbiera AM (Lotnictwo). Antena jest kluczowa.")
    with c3:
        with st.container():
            st.info("3. Raport SALT")
            st.markdown("**S**ize (Wielkość)\n**A**ctivity (Zdarzenie)\n**L**ocation (Miejsce)\n**T**ime (Czas)")

# --- CZAS ---
with tabs[3]:
    st.header("🌍 Czas Świata")
    zones = [("UTC", "UTC"), ("Warszawa", "Europe/Warsaw"), ("New York", "America/New_York"), 
             ("Los Angeles", "America/Los_Angeles"), ("Tokio", "Asia/Tokyo"), ("Sydney", "Australia/Sydney")]
    cols = st.columns(3)
    for i, (n, z) in enumerate(zones):
        cols[i%3].markdown(f"<div style='background:#161b22;padding:10px;margin:5px;border-radius:10px;border:1px solid #303030;text-align:center;'><div style='color:#888'>{n}</div><div style='font-size:1.8em;font-weight:bold;color:#e0e0e0'>{get_time_in_zone(z)}</div></div>", unsafe_allow_html=True)

# --- GLOBALNE ---
with tabs[4]:
    st.header("📻 Globalne Stacje")
    st.dataframe(df_glob, use_container_width=True, hide_index=True)

# --- EDUKACJA ---
with tabs[5]:
    c1, c2 = st.columns(2)
    with c1:
        with st.container():
            st.subheader("Słownik")
            st.markdown("* **AM:** Amplituda (Lotnictwo/CB). Słychać nakładki.\n* **FM:** Częstotliwość (PMR/Służby). Czysty dźwięk.\n* **Squelch:** Blokada szumów.\n* **CTCSS:** Ton otwierający przemiennik.")
    with c2:
        with st.container():
            st.subheader("Ciekawostki")
            st.markdown("* **CB Zera:** Polska (27.180), Europa Piątki (27.185).\n* **Doppler:** Zmiana tonu satelity (+/- 3kHz) podczas przelotu.")

# --- PRZEMIENNIKI ---
with tabs[6]:
    st.header("🗺️ Przemienniki PL")
    c1, c2 = st.columns([2, 1])
    with c1:
        fig = go.Figure(go.Scattermapbox(lat=df_rep['Lat'], lon=df_rep['Lon'], mode='markers', marker=dict(size=12, color='#ffa500'), text=df_rep['Znak'], hoverinfo='text', hovertext=df_rep['Znak']+" "+df_rep['Freq']))
        fig.update_layout(mapbox_style="carto-darkmatter", mapbox=dict(center=dict(lat=52, lon=19), zoom=5.5), margin={"r":0,"t":0,"l":0,"b":0}, height=500)
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.dataframe(df_rep[["Znak", "Freq", "Loc"]], hide_index=True, use_container_width=True, height=500)

# --- KALKULATORY ---
with tabs[7]:
    st.header("🧮 Narzędzia")
    c1, c2, c3 = st.columns(3)
    with c1:
        with st.container():
            st.subheader("📡 Dipol")
            f = st.number_input("Freq (MHz)", 145.5, format="%.3f")
            st.success(f"Długość: **{142.5/f:.2f} m**")
            st.caption("Dla dipola półfalowego (k=0.95)")
    with c2:
        with st.container():
            st.subheader("🌊 Fala")
            fw = st.number_input("Freq (MHz)", 27.18, key="w", format="%.3f")
            l = 300/fw if fw>0 else 0
            st.metric("Długość fali", f"{l:.2f} m")
    with c3:
        with st.container():
            st.subheader("📍 QTH")
            la = st.number_input("Lat", 52.23); lo = st.number_input("Lon", 21.01)
            st.info(f"Locator: **{latlon_to_maidenhead(la, lo)}**")

# --- WEBSDR ---
with tabs[8]:
    st.header("🌐 WebSDR")
    st.dataframe(df_sdr, column_config={"Link": st.column_config.LinkColumn("Link", display_text="Otwórz 🔗")}, use_container_width=True, hide_index=True)

# --- LOGBOOK ---
with tabs[9]:
    st.header("📝 Logbook")
    if 'logbook_df' not in st.session_state: st.session_state.logbook_df = load_logbook()
    
    with st.container():
        with st.form("log", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            t = c1.text_input("Czas (UTC)", datetime.now(timezone.utc).strftime("%H:%M"))
            f = c2.text_input("Freq")
            s = c3.text_input("Znak")
            m = c4.selectbox("Mod", ["FM", "AM", "SSB"])
            if st.form_submit_button("Zapisz"):
                if f and s:
                    new = pd.DataFrame([{"Data": datetime.now().strftime("%Y-%m-%d"), "Godzina (UTC)": t, "Freq (MHz)": f, "Stacja": s, "Modulacja": m, "Raport": "59"}])
                    st.session_state.logbook_df = pd.concat([st.session_state.logbook_df, new], ignore_index=True)
                    save_logbook(st.session_state.logbook_df)
                    st.success("Dodano")
    
    st.dataframe(st.session_state.logbook_df.iloc[::-1], use_container_width=True)
    st.download_button("📥 Pobierz CSV", st.session_state.logbook_df.to_csv(index=False).encode(), "log.csv", "text/csv")

# --- STRAŻ ---
with tabs[10]:
    st.header("🚒 Straż Pożarna")
    c1, c2 = st.columns([1, 1])
    with c1:
        st.subheader("Siatka B")
        st.dataframe(df_psp, use_container_width=True, height=400, hide_index=True)
    with c2:
        st.subheader("Kryptonimy")
        st.dataframe(df_pref, use_container_width=True, height=400, hide_index=True)

st.markdown("---")
st.caption("Centrum Dowodzenia Radiowego v17.0 Performance Edition | Czas: UTC")
