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
# 1. GENERATORY CZĘSTOTLIWOŚCI I DANE PSP
# ===========================

def generate_pmr_list():
    pmr = []
    base = 446.00625
    for i in range(16):
        ch = i+1
        desc = "Preppersi/Góry" if ch==3 else "Ogólny"
        pmr.append({"MHz": f"{base+(i*0.0125):.5f}", "Pasmo": "PMR", "Mod": "NFM", "Kategoria": "PMR", "Nazwa": f"PMR {ch}", "Opis": desc})
    return pmr

def generate_cb_list():
    freqs = [26.965, 26.975, 26.985, 27.005, 27.015, 27.025, 27.035, 27.055, 27.065, 27.075,
             27.085, 27.105, 27.115, 27.125, 27.135, 27.155, 27.165, 27.175, 27.185, 27.205,
             27.215, 27.225, 27.255, 27.235, 27.245, 27.265, 27.275, 27.285, 27.295, 27.305,
             27.315, 27.325, 27.335, 27.345, 27.355, 27.365, 27.375, 27.385, 27.395, 27.405]
    cb = []
    for i, f in enumerate(freqs):
        ch = i+1
        desc = "Ratunkowy" if ch==9 else "Drogowy" if ch==19 else "Ogólny"
        cb.append({"MHz": f"{f-0.005:.3f}", "Pasmo": "CB", "Mod": "AM", "Kategoria": "CB Radio", "Nazwa": f"CB {ch}", "Opis": desc})
    return cb

def generate_psp_grid():
    """Generuje siatkę kanałów B (Straż Pożarna) w paśmie VHF."""
    # Uproszczony generator na podstawie standardu (przykładowe zakresy)
    # W rzeczywistości to tabela przypisań, tutaj generujemy poglądowo
    psp = []
    
    # Kanały Krajowe (Stałe)
    psp.append({"Kanał": "B028", "MHz": "148.6625", "Typ": "Krajowy (KSRG)", "Opis": "Kanał Ratowniczo-Gaśniczy (Cała Polska)"})
    psp.append({"Kanał": "B002", "MHz": "149.1500", "Typ": "Współdziałania", "Opis": "Dowodzenie i Współdziałanie"})
    
    # Przykładowe kanały z siatki (Wzór jest skomplikowany, podaję popularne)
    # Zwykle powiaty mają przydzielone kanały z puli B001-B060
    # To jest symulacja dla celów edukacyjnych
    base_freq_low = 148.6750
    for i in range(1, 10):
        f = base_freq_low + (i * 0.0125)
        psp.append({"Kanał": f"B{i+30:03d}", "MHz": f"{f:.4f}", "Typ": "Powiatowy", "Opis": "Przykładowy kanał powiatowy"})
        
    return psp

psp_prefixes = [
    {"Prefix": "250-xxx", "Województwo": "Dolnośląskie (Wrocław)", "Opis": "KW PSP Wrocław"},
    {"Prefix": "300-xxx", "Województwo": "Kujawsko-Pomorskie (Toruń)", "Opis": "KW PSP Toruń"},
    {"Prefix": "330-xxx", "Województwo": "Lubelskie (Lublin)", "Opis": "KW PSP Lublin"},
    {"Prefix": "360-xxx", "Województwo": "Lubuskie (Gorzów Wlkp.)", "Opis": "KW PSP Gorzów"},
    {"Prefix": "400-xxx", "Województwo": "Łódzkie (Łódź)", "Opis": "KW PSP Łódź"},
    {"Prefix": "430-xxx", "Województwo": "Małopolskie (Kraków)", "Opis": "KW PSP Kraków"},
    {"Prefix": "460-xxx", "Województwo": "Mazowieckie (Warszawa)", "Opis": "KW PSP Warszawa"},
    {"Prefix": "500-xxx", "Województwo": "Opolskie (Opole)", "Opis": "KW PSP Opole"},
    {"Prefix": "530-xxx", "Województwo": "Podkarpackie (Rzeszów)", "Opis": "KW PSP Rzeszów"},
    {"Prefix": "560-xxx", "Województwo": "Podlaskie (Białystok)", "Opis": "KW PSP Białystok"},
    {"Prefix": "600-xxx", "Województwo": "Pomorskie (Gdańsk)", "Opis": "KW PSP Gdańsk"},
    {"Prefix": "630-xxx", "Województwo": "Śląskie (Katowice)", "Opis": "KW PSP Katowice"},
    {"Prefix": "660-xxx", "Województwo": "Świętokrzyskie (Kielce)", "Opis": "KW PSP Kielce"},
    {"Prefix": "700-xxx", "Województwo": "Warmińsko-Mazurskie (Olsztyn)", "Opis": "KW PSP Olsztyn"},
    {"Prefix": "730-xxx", "Województwo": "Wielkopolskie (Poznań)", "Opis": "KW PSP Poznań"},
    {"Prefix": "760-xxx", "Województwo": "Zachodniopomorskie (Szczecin)", "Opis": "KW PSP Szczecin"},
]

# ===========================
# 2. BAZA DANYCH (Satelity, Przemienniki...)
# ===========================

repeater_list = [
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

global_stations = [
    {"MHz": "0.225", "Pasmo": "LW", "Mod": "AM", "Kategoria": "Polska", "Nazwa": "Polskie Radio 1", "Opis": "Nadajnik w Solcu Kujawskim. Zasięg: cała Europa."},
    {"MHz": "0.198", "Pasmo": "LW", "Mod": "AM", "Kategoria": "Europa", "Nazwa": "BBC Radio 4", "Opis": "Legendarna stacja brytyjska."},
    {"MHz": "6.000", "Pasmo": "49m", "Mod": "AM", "Kategoria": "Świat", "Nazwa": "Pasmo 49m", "Opis": "Wieczór Europa."},
    {"MHz": "9.400", "Pasmo": "31m", "Mod": "AM", "Kategoria": "Świat", "Nazwa": "Pasmo 31m", "Opis": "Całodobowe."},
    {"MHz": "4.625", "Pasmo": "SW", "Mod": "USB", "Kategoria": "Utility", "Nazwa": "UVB-76", "Opis": "Rosyjska stacja numeryczna (The Buzzer)."},
    {"MHz": "5.450", "Pasmo": "SW", "Mod": "USB", "Kategoria": "Lotnictwo", "Nazwa": "RAF Volmet", "Opis": "Pogoda lotnicza."},
]

websdr_list = [
    {"Nazwa": "WebSDR Twente", "Kraj": "Holandia 🇳🇱", "Link": "http://websdr.ewi.utwente.nl:8901/", "Opis": "Najlepszy na świecie (0-30 MHz)."},
    {"Nazwa": "WebSDR Zielona Góra", "Kraj": "Polska 🇵🇱", "Link": "http://websdr.sp3pgx.uz.zgora.pl:8901/", "Opis": "Satelity i VHF/UHF."},
    {"Nazwa": "Klub SP2PMK", "Kraj": "Polska 🇵🇱", "Link": "http://sp2pmk.uni.torun.pl:8901/", "Opis": "Toruń (KF)."},
    {"Nazwa": "KiwiSDR Map", "Kraj": "Świat 🌍", "Link": "http://rx.linkfanel.net/", "Opis": "Mapa tysięcy amatorskich odbiorników."},
]

special_freqs = [
    {"MHz": "145.800", "Pasmo": "2m", "Mod": "NFM", "Kategoria": "Satelity", "Nazwa": "ISS (Głos)", "Opis": "Region 1 Voice"},
    {"MHz": "145.825", "Pasmo": "2m", "Mod": "FM", "Kategoria": "Satelity", "Nazwa": "ISS (APRS)", "Opis": "Packet Radio"},
    {"MHz": "437.800", "Pasmo": "70cm", "Mod": "FM", "Kategoria": "Satelity", "Nazwa": "ISS (Repeater)", "Opis": "Uplink: 145.990"},
    {"MHz": "137.100", "Pasmo": "VHF", "Mod": "WFM", "Kategoria": "Satelity", "Nazwa": "NOAA 19", "Opis": "APT Weather"},
    {"MHz": "121.500", "Pasmo": "Air", "Mod": "AM", "Kategoria": "Lotnictwo", "Nazwa": "Air Guard", "Opis": "Ratunkowy"},
    {"MHz": "148.6625", "Pasmo": "VHF", "Mod": "NFM", "Kategoria": "Służby", "Nazwa": "PSP (B028)", "Opis": "Krajowy KSRG"},
    {"MHz": "156.800", "Pasmo": "Marine", "Mod": "FM", "Kategoria": "Morskie", "Nazwa": "Kanał 16", "Opis": "Ratunkowy"},
    {"MHz": "145.500", "Pasmo": "2m", "Mod": "FM", "Kategoria": "Ham", "Nazwa": "VHF Call", "Opis": "Wywoławcza"},
]

data_freq = special_freqs + generate_pmr_list() + generate_cb_list()

# ===========================
# 3. LOGIKA SATELITARNA
# ===========================
@st.cache_data(ttl=3600)
def fetch_iss_tle():
    FALLBACK_TLE = ("1 25544U 98067A   24017.54519514  .00016149  00000+0  29290-3 0  9993", "2 25544  51.6415 158.8530 0005786 244.1866 179.9192 15.49622591435056")
    try:
        resp = requests.get("https://celestrak.org/NORAD/elements/stations.txt", headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        lines = [l.strip() for l in resp.text.splitlines() if l.strip()]
        for i, line in enumerate(lines):
            if "ISS (ZARYA)" in line and i+2 < len(lines): return lines[i+1], lines[i+2]
        return FALLBACK_TLE
    except: return FALLBACK_TLE

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
        traj_lats, traj_lons = [], []
        prev_lon = None
        for delta in range(-50*60, 50*60, 60):
            ts = now + timedelta(seconds=delta)
            jd_s, fr_s = jday(ts.year, ts.month, ts.day, ts.hour, ts.minute, ts.second)
            _, r_s, _ = sat.sgp4(jd_s, fr_s)
            itrs_s = TEME(x=r_s[0]*u.km, y=r_s[1]*u.km, z=r_s[2]*u.km, obstime=Time(ts)).transform_to(ITRS(obstime=Time(ts)))
            loc_s = EarthLocation(itrs_s.x, itrs_s.y, itrs_s.z)
            ls = loc_s.lon.deg
            if prev_lon and abs(ls - prev_lon) > 180: traj_lats.append(None); traj_lons.append(None)
            traj_lats.append(loc_s.lat.deg); traj_lons.append(ls); prev_lon = ls
        return loc.lat.deg, loc.lon.deg, traj_lats, traj_lons
    except: return None, None, [], []

# ===========================
# 4. INTERFEJS APLIKACJI
# ===========================

c1, c2, c3 = st.columns([3, 1, 1])
with c1: st.title("📡 Centrum Dowodzenia")
with c2: st.markdown(f"<div style='text-align:right;color:#00ff41;font-family:monospace;'><b>ZULU:</b> {get_utc_time()}</div>", unsafe_allow_html=True)
with c3: st.markdown(f"<div style='text-align:right;color:gray;'>Odwiedzin: <b>{visit_count}</b></div>", unsafe_allow_html=True)

# 11 ZAKŁADEK (DODANO STRAŻ)
tabs = st.tabs([
    "📡 Tracker", "☀️ Pogoda", "🆘 Kryzysowe", "🌍 Czas", "📻 Globalne", 
    "📚 Edukacja", "🗺️ Przemienniki", "🧮 Kalkulatory", "🌐 WebSDR", 
    "📝 Logbook", "🚒 Straż Pożarna" # <--- NOWA ZAKŁADKA
])

# 1. TRACKER
with tabs[0]:
    c_map, c_data = st.columns([3, 2])
    with c_map:
        st.subheader("ISS Tracker")
        tle_data = fetch_iss_tle()
        if tle_data:
            l1, l2 = tle_data
            lat, lon, t_lat, t_lon = get_satellite_position(l1, l2)
            if lat:
                fig = go.Figure()
                fig.add_trace(go.Scattergeo(lat=t_lat, lon=t_lon, mode="lines", line=dict(color="blue", width=2, dash="dot")))
                fig.add_trace(go.Scattergeo(lat=[lat], lon=[lon], mode="text", text=["🛰️"], textfont=dict(size=30)))
                fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=450, geo=dict(projection_type="natural earth", showland=True, landcolor="#333", showocean=True, oceancolor="#111", showcountries=True), showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
                if st.button("🔄 Odśwież"): st.rerun()
    with c_data:
        st.subheader("Częstotliwości (PL)")
        df = pd.DataFrame(data_freq)
        c_s, c_f = st.columns([2, 1])
        with c_s: search = st.text_input("Szukaj", placeholder="PMR, CB...")
        with c_f: cat = st.multiselect("Kategoria", df["Kategoria"].unique())
        if search: df = df[df.apply(lambda r: r.astype(str).str.contains(search, case=False).any(), axis=1)]
        if cat: df = df[df["Kategoria"].isin(cat)]
        st.dataframe(df, use_container_width=True, hide_index=True, height=450)

# 2. POGODA
with tabs[1]:
    st.header("☀️ Pogoda Kosmiczna")
    c1, c2 = st.columns(2)
    with c1: st.image("https://www.hamqsl.com/solar101vhf.php"); st.image("https://www.hamqsl.com/solarmap.php")
    with c2: st.info("**SFI:** >100 = Super.\n**K-Index:** <3 = Czysto."); st.markdown("Dane na żywo z N0NBH.")

# 3. KRYZYSOWE (PEŁNE)
with tabs[2]:
    st.header("🆘 Procedury Awaryjne")
    c1, c2, c3 = st.columns(3)
    with c1: st.error("### 1. Reguła 3-3-3"); st.markdown("System nasłuchu w sytuacji kryzysowej (brak GSM):\n* **Kiedy?** Co 3 godziny (12:00, 15:00...)\n* **Ile?** 3 minuty nasłuchu.\n* **Gdzie?** PMR 3 / CB 3")
    with c2: st.warning("### 2. Sprzęt"); st.markdown("* **Baofeng:** Tylko FM (PMR/Służby). Brak AM (CB/Lotnictwo).\n* **Zasięg:** Miasto ~1km, Góry >100km.\n* **Antena:** Dłuższa = Lepsza.")
    with c3: st.info("### 3. Komunikacja (SALT)"); st.markdown("* **S**ize (Wielkość)\n* **A**ctivity (Zdarzenie)\n* **L**ocation (Miejsce)\n* **T**ime (Czas)")

# 4. CZAS
with tabs[3]:
    st.header("🌍 Czas Świata")
    zs = [("UTC", "UTC"), ("PL", "Europe/Warsaw"), ("NY", "America/New_York"), ("LA", "America/Los_Angeles"), ("Tokio", "Asia/Tokyo"), ("Sydney", "Australia/Sydney")]
    cols = st.columns(3)
    for i, (n, z) in enumerate(zs):
        cols[i%3].markdown(f"<div style='background:#222;padding:10px;text-align:center;margin:5px;border-radius:10px;'><div>{n}</div><div style='font-size:1.5em;font-weight:bold;'>{get_time_in_zone(z)}</div></div>", unsafe_allow_html=True)

# 5. GLOBALNE
with tabs[4]:
    st.header("📻 Stacje Globalne")
    st.dataframe(pd.DataFrame(global_stations), use_container_width=True, hide_index=True)

# 6. EDUKACJA (PEŁNE)
with tabs[5]:
    st.header("📚 Edukacja")
    c1, c2 = st.columns(2)
    with c1: 
        st.subheader("Słownik")
        st.markdown("* **AM:** Modulacja amplitudy (Lotnictwo/CB).\n* **FM:** Modulacja częstotliwości (Służby/PMR).\n* **SSB:** Wstęgowa (Daleki zasięg).\n* **Squelch:** Blokada szumów.\n* **CTCSS:** Ton (Klucz) do przemiennika.\n* **73:** Pozdrawiam.")
    with c2: 
        st.subheader("Ciekawostki")
        st.markdown("* **CB Zera:** Polska 27.180 (końcówka 0), Europa 27.185 (końcówka 5).\n* **Doppler:** Zmiana freq satelity (+/- 3kHz).\n* **Samoloty:** Używają AM dla bezpieczeństwa (słychać nakładki).")

# 7. PRZEMIENNIKI
with tabs[6]:
    st.header("🗺️ Mapa Przemienników PL")
    c1, c2 = st.columns([3,1])
    dfr = pd.DataFrame(repeater_list)
    with c1:
        fig = go.Figure(go.Scattermapbox(lat=dfr['Lat'], lon=dfr['Lon'], mode='markers', marker=dict(size=12, color='orange'), text=dfr['Znak'], hoverinfo='text', hovertext=dfr['Znak']+" "+dfr['Freq']+" "+dfr['Loc']))
        fig.update_layout(mapbox_style="open-street-map", mapbox=dict(center=dict(lat=52, lon=19), zoom=5), margin={"r":0,"t":0,"l":0,"b":0}, height=450)
        st.plotly_chart(fig, use_container_width=True)
    with c2: st.dataframe(dfr[["Znak", "Freq", "Loc"]], hide_index=True)

# 8. KALKULATORY
with tabs[7]:
    st.header("🧮 Narzędzia")
    c1, c2, c3 = st.columns(3)
    with c1:
        with st.container(border=True):
            st.subheader("📡 Dipol")
            f = st.number_input("Freq (MHz)", 145.5, format="%.3f")
            st.success(f"Długość: {142.5/f:.2f}m")
    with c2:
        with st.container(border=True):
            st.subheader("🌊 Fala")
            fw = st.number_input("Freq (MHz)", 27.18, key="w", format="%.3f")
            st.metric("Długość", f"{300/fw:.2f}m" if fw>0 else "0m")
    with c3:
        with st.container(border=True):
            st.subheader("📍 QTH")
            la = st.number_input("Lat", 52.23); lo = st.number_input("Lon", 21.01)
            st.info(f"Locator: {latlon_to_maidenhead(la, lo)}")

# 9. WEBSDR
with tabs[8]:
    st.header("🌐 WebSDR")
    st.dataframe(pd.DataFrame(websdr_list), column_config={"Link": st.column_config.LinkColumn("Link", display_text="Otwórz 🔗")}, use_container_width=True, hide_index=True)

# 10. LOGBOOK
with tabs[9]:
    st.header("📝 Logbook")
    if 'logbook_df' not in st.session_state: st.session_state.logbook_df = load_logbook()
    with st.form("log_form", clear_on_submit=True):
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1: t_in = st.text_input("Godzina (UTC)", datetime.now(timezone.utc).strftime("%H:%M"))
        with c2: f_in = st.text_input("Freq (MHz)")
        with c3: s_in = st.text_input("Znak")
        with c4: m_in = st.selectbox("Mod", ["FM", "AM", "SSB"])
        with c5: r_in = st.text_input("RST", "59")
        if st.form_submit_button("➕ Zapisz"):
            if f_in and s_in:
                new = pd.DataFrame([{"Data": datetime.now().strftime("%Y-%m-%d"), "Godzina (UTC)": t_in, "Freq (MHz)": f_in, "Stacja": s_in, "Modulacja": m_in, "Raport": r_in}])
                st.session_state.logbook_df = pd.concat([st.session_state.logbook_df, new], ignore_index=True)
                save_logbook(st.session_state.logbook_df)
                st.success("OK")
            else: st.error("Brak danych")
    st.dataframe(st.session_state.logbook_df.iloc[::-1], use_container_width=True)
    st.download_button("📥 Pobierz CSV", st.session_state.logbook_df.to_csv(index=False).encode('utf-8'), "logbook.csv", "text/csv")

# 11. STRAŻ POŻARNA (NOWOŚĆ!)
with tabs[10]:
    st.header("🚒 Straż Pożarna (PSP/OSP)")
    st.markdown("Dane operacyjne Państwowej Straży Pożarnej. Znajdź kanał dla swojego powiatu.")
    
    col_grid, col_map_psp = st.columns([1, 1])
    
    with col_grid:
        st.subheader("🎛️ Siatka Radiowa (B)")
        st.info("**Jak to działa?** Straż w całej Polsce pracuje na ujednoliconej siatce kanałów VHF (B001 - Bxxx). Każdy powiat ma przydzielony jeden lub więcej kanałów.")
        # Tabela kanałów (generowana)
        psp_data = generate_psp_grid()
        st.dataframe(pd.DataFrame(psp_data), use_container_width=True, height=400)
        
    with col_map_psp:
        st.subheader("🆔 Kryptonimy Wojewódzkie")
        st.markdown("Pierwsze cyfry kryptonimu (np. **301**-21) oznaczają województwo i powiat.")
        st.dataframe(pd.DataFrame(psp_prefixes), use_container_width=True, hide_index=True)
        
        st.markdown("---")
        with st.expander("🔍 Dekoder Kryptonimów (Przykład)"):
            st.write("""
            Format: **XXX - [Y] - ZZ**
            * **XXX (Prefiks):** Np. 301 (Dolnośląskie, JRG 1 Wrocław)
            * **Y (Rodzaj):** Np. 2 (Gaśniczy), 4 (Techniczny), 9 (Dowódca)
            * **ZZ (Numer):** Numer kolejny pojazdu.
            
            *Przykład:* **301-21** = Dolnośląskie -> JRG 1 -> Pierwszy wóz gaśniczy (GBA).
            """)

st.markdown("---")
st.caption("Centrum Dowodzenia Radiowego v16.0 Ultimate | Dane: CelesTrak, N0NBH | Czas: UTC")
