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
st.set_page_config(page_title="Centrum Dowodzenia Radiowego", page_icon="📡", layout="wide")

# ===========================
# 0. FUNKCJE POMOCNICZE
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
    A = ord('A')
    lon += 180; lat += 90
    f_lon = int(lon/20); f_lat = int(lat/10)
    lon -= f_lon*20; lat -= f_lat*10
    s_lon = int(lon/2); s_lat = int(lat)
    lon -= s_lon*2; lat -= s_lat
    ss_lon = int(lon*12); ss_lat = int(lat*24)
    return f"{chr(A+f_lon)}{chr(A+f_lat)}{s_lon}{s_lat}{chr(A+ss_lon)}{chr(A+ss_lat)}"

# ===========================
# 1. LISTY I DANE
# ===========================
def generate_pmr_list():
    pmr = []
    base = 446.00625
    for i in range(16):
        ch = i+1
        desc = "Preppersi/Góry" if ch==3 else "Popularny" if ch==1 else "Ogólny"
        pmr.append({"MHz": f"{base+(i*0.0125):.5f}", "Pasmo": "PMR", "Mod": "NFM", "Nazwa": f"PMR {ch}", "Opis": desc})
    return pmr

def generate_cb_list():
    freqs = [26.965, 26.975, 26.985, 27.005, 27.015, 27.025, 27.035, 27.055, 27.065, 27.075,
             27.085, 27.105, 27.115, 27.125, 27.135, 27.155, 27.165, 27.175, 27.185, 27.205,
             27.215, 27.225, 27.255, 27.235, 27.245, 27.265, 27.275, 27.285, 27.295, 27.305,
             27.315, 27.325, 27.335, 27.345, 27.355, 27.365, 27.375, 27.385, 27.395, 27.405]
    cb = []
    for i, f in enumerate(freqs):
        ch = i+1
        desc = "!!! RATUNKOWY !!!" if ch==9 else "!!! DROGOWY !!!" if ch==19 else "Preppers" if ch==3 else "Ogólny"
        cb.append({"MHz": f"{f-0.005:.3f}", "Pasmo": "CB", "Mod": "AM", "Nazwa": f"CB {ch}", "Opis": desc})
    return cb

repeater_list = [
    {"Znak": "SR5WA", "Freq": "439.350", "CTCSS": "127.3", "Lat": 52.23, "Lon": 21.01, "Loc": "Warszawa", "Shift": "-7.6"},
    {"Znak": "SR5W", "Freq": "145.600", "CTCSS": "127.3", "Lat": 52.21, "Lon": 20.98, "Loc": "Warszawa", "Shift": "-0.6"},
    {"Znak": "SR6J", "Freq": "145.675", "CTCSS": "94.8", "Lat": 50.78, "Lon": 15.56, "Loc": "Śnieżne Kotły", "Shift": "-0.6"},
    {"Znak": "SR9P", "Freq": "438.900", "CTCSS": "103.5", "Lat": 50.06, "Lon": 19.94, "Loc": "Kraków", "Shift": "-7.6"},
    {"Znak": "SR9C", "Freq": "145.775", "CTCSS": "103.5", "Lat": 49.65, "Lon": 19.88, "Loc": "Kraków", "Shift": "-0.6"},
    {"Znak": "SR2Z", "Freq": "145.725", "CTCSS": "94.8", "Lat": 54.37, "Lon": 18.60, "Loc": "Gdańsk", "Shift": "-0.6"},
    {"Znak": "SR2C", "Freq": "438.800", "CTCSS": "94.8", "Lat": 54.52, "Lon": 18.53, "Loc": "Gdynia", "Shift": "-7.6"},
    {"Znak": "SR3PO", "Freq": "438.850", "CTCSS": "110.9", "Lat": 52.40, "Lon": 16.92, "Loc": "Poznań", "Shift": "-7.6"},
    {"Znak": "SR8L", "Freq": "145.625", "CTCSS": "107.2", "Lat": 51.24, "Lon": 22.57, "Loc": "Lublin", "Shift": "-0.6"},
    {"Znak": "SR4J", "Freq": "439.100", "CTCSS": "88.5", "Lat": 53.77, "Lon": 20.48, "Loc": "Olsztyn", "Shift": "-7.6"},
    {"Znak": "SR7V", "Freq": "145.6875", "CTCSS": "88.5", "Lat": 50.80, "Lon": 19.11, "Loc": "Częstochowa", "Shift": "-0.6"},
    {"Znak": "SR1Z", "Freq": "145.6375", "CTCSS": "118.8", "Lat": 53.42, "Lon": 14.55, "Loc": "Szczecin", "Shift": "-0.6"},
]

global_stations = [
    {"MHz": "0.225", "Pasmo": "LW", "Mod": "AM", "Nazwa": "Polskie Radio 1", "Opis": "Solec Kujawski (Cała PL)."},
    {"MHz": "0.198", "Pasmo": "LW", "Mod": "AM", "Nazwa": "BBC Radio 4", "Opis": "UK News."},
    {"MHz": "0.153", "Pasmo": "LW", "Mod": "AM", "Nazwa": "Radio Romania", "Opis": "Antena Satelor."},
    {"MHz": "6.000", "Pasmo": "49m", "Mod": "AM", "Nazwa": "Pasmo 49m", "Opis": "Wieczór Europa."},
    {"MHz": "9.400", "Pasmo": "31m", "Mod": "AM", "Nazwa": "Pasmo 31m", "Opis": "Całodobowe."},
    {"MHz": "15.100", "Pasmo": "19m", "Mod": "AM", "Nazwa": "Pasmo 19m", "Opis": "Dzień (Daleki zasięg)."},
    {"MHz": "4.625", "Pasmo": "SW", "Mod": "USB", "Nazwa": "UVB-76", "Opis": "The Buzzer (Rosja)."},
    {"MHz": "5.000", "Pasmo": "SW", "Mod": "AM", "Nazwa": "WWV", "Opis": "Wzorzec Czasu."},
    {"MHz": "14.230", "Pasmo": "20m", "Mod": "USB", "Nazwa": "SSTV Call", "Opis": "Obrazki SSTV."},
    {"MHz": "5.450", "Pasmo": "SW", "Mod": "USB", "Nazwa": "RAF Volmet", "Opis": "Pogoda lotnicza."},
]

websdr_list = [
    {"Nazwa": "WebSDR Twente", "Kraj": "Holandia 🇳🇱", "Link": "http://websdr.ewi.utwente.nl:8901/", "Opis": "Najlepszy na świecie (0-30 MHz)."},
    {"Nazwa": "WebSDR Zielona Góra", "Kraj": "Polska 🇵🇱", "Link": "http://websdr.sp3pgx.uz.zgora.pl:8901/", "Opis": "Satelity i VHF/UHF."},
    {"Nazwa": "Klub SP2PMK", "Kraj": "Polska 🇵🇱", "Link": "http://sp2pmk.uni.torun.pl:8901/", "Opis": "Toruń (KF)."},
    {"Nazwa": "KiwiSDR Map", "Kraj": "Świat 🌍", "Link": "http://rx.linkfanel.net/", "Opis": "Mapa odbiorników."},
]

special_freqs = [
    {"MHz": "145.800", "Pasmo": "2m", "Mod": "NFM", "Nazwa": "ISS (Głos)", "Opis": "Region 1 Voice"},
    {"MHz": "145.825", "Pasmo": "2m", "Mod": "FM", "Nazwa": "ISS (APRS)", "Opis": "Packet Radio"},
    {"MHz": "437.800", "Pasmo": "70cm", "Mod": "FM", "Nazwa": "ISS (Repeater)", "Opis": "Uplink: 145.990"},
    {"MHz": "137.100", "Pasmo": "VHF", "Mod": "WFM", "Nazwa": "NOAA 19", "Opis": "APT Weather"},
    {"MHz": "121.500", "Pasmo": "Air", "Mod": "AM", "Nazwa": "Air Guard", "Opis": "Ratunkowy"},
    {"MHz": "129.500", "Pasmo": "Air", "Mod": "AM", "Nazwa": "LPR (Oper)", "Opis": "Pogotowie Lotnicze"},
    {"MHz": "148.6625", "Pasmo": "VHF", "Mod": "NFM", "Nazwa": "PSP (B028)", "Opis": "Krajowy KSRG"},
    {"MHz": "156.800", "Pasmo": "Marine", "Mod": "FM", "Nazwa": "Kanał 16", "Opis": "Ratunkowy"},
    {"MHz": "145.500", "Pasmo": "2m", "Mod": "FM", "Nazwa": "VHF Call", "Opis": "Wywoławcza"},
]

data_freq = special_freqs + generate_pmr_list() + generate_cb_list()

# ===========================
# 3. LOGIKA SATELITARNA (NAPRAWIONA)
# ===========================
@st.cache_data(ttl=3600)
def fetch_iss_tle():
    # TLE Zapasowe (Fallback) na wypadek awarii Celestrak
    FALLBACK_TLE = (
        "1 25544U 98067A   24017.54519514  .00016149  00000+0  29290-3 0  9993",
        "2 25544  51.6415 158.8530 0005786 244.1866 179.9192 15.49622591435056"
    )
    url = "https://celestrak.org/NORAD/elements/stations.txt"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        resp.raise_for_status() # Sprawdź czy nie ma błędu 404/500
        lines = [l.strip() for l in resp.text.splitlines() if l.strip()]
        for i, line in enumerate(lines):
            if "ISS (ZARYA)" in line and i+2 < len(lines):
                return lines[i+1], lines[i+2]
        return FALLBACK_TLE
    except Exception:
        # W razie jakiegokolwiek błędu zwróć stare dane, żeby strona działała
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

# 10 ZAKŁADEK
tabs = st.tabs(["📡 Tracker", "☀️ Pogoda", "🆘 Kryzysowe", "🌍 Czas", "📻 Globalne", "📚 Edukacja", "🗺️ Przemienniki", "🧮 Kalkulatory", "🌐 WebSDR", "📝 Logbook"])

# 1. TRACKER
with tabs[0]:
    c_map, c_data = st.columns([3, 2])
    with c_map:
        st.subheader("ISS Tracker")
        tle_data = fetch_iss_tle() # Teraz zawsze zwróci tuple, nigdy None
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
            else:
                st.error("Błąd obliczeń orbitalnych.")
        else:
            st.error("Błąd krytyczny danych TLE.")

    with c_data:
        st.subheader("Częstotliwości")
        df = pd.DataFrame(data_freq)
        search = st.text_input("Szukaj", placeholder="PMR, CB...")
        if search: df = df[df.apply(lambda r: r.astype(str).str.contains(search, case=False).any(), axis=1)]
        st.dataframe(df, use_container_width=True, hide_index=True, height=450)

# 2. POGODA
with tabs[1]:
    st.header("☀️ Pogoda Kosmiczna")
    c1, c2 = st.columns(2)
    with c1: st.image("https://www.hamqsl.com/solar101vhf.php", caption="N0NBH Data"); st.image("https://www.hamqsl.com/solarmap.php", caption="Greyline")
    with c2: st.info("**SFI:** >100 = Super.\n**K-Index:** <3 = Czysto."); st.markdown("Dane na żywo z N0NBH.")

# 3. KRYZYSOWE
with tabs[2]:
    st.header("🆘 Procedury Awaryjne")
    c1, c2, c3 = st.columns(3)
    with c1: st.error("### 1. Reguła 3-3-3"); st.markdown("Co 3h / 3min / Kanał 3 (PMR/CB).")
    with c2: st.warning("### 2. Sprzęt"); st.markdown("Baofeng = Tylko FM. CB/Lotnictwo = AM.")
    with c3: st.info("### 3. SALT"); st.markdown("Size, Activity, Location, Time.")

# 4. CZAS
with tabs[3]:
    st.header("🌍 Czas Świata")
    zs = [("UTC", "UTC"), ("PL", "Europe/Warsaw"), ("NY", "America/New_York"), ("LA", "America/Los_Angeles"), ("Tokio", "Asia/Tokyo"), ("Sydney", "Australia/Sydney")]
    cols = st.columns(3)
    for i, (n, z) in enumerate(zs):
        cols[i%3].markdown(f"<div style='background:#222;padding:10px;text-align:center;margin:5px;'><div>{n}</div><div style='font-size:1.5em;font-weight:bold;'>{get_time_in_zone(z)}</div></div>", unsafe_allow_html=True)

# 5. GLOBALNE
with tabs[4]:
    st.header("📻 Stacje Globalne")
    st.dataframe(pd.DataFrame(global_stations), use_container_width=True, hide_index=True)

# 6. EDUKACJA
with tabs[5]:
    st.header("📚 Edukacja")
    c1, c2 = st.columns(2)
    with c1: st.markdown("**AM:** Lotnictwo/CB.\n**FM:** Służby/PMR.\n**SSB:** Daleki zasięg.\n**Squelch:** Blokada szumów.")
    with c2: st.markdown("**CB Zera:** Polska 27.180 (końcówka 0).\n**Doppler:** Zmiana freq satelity.\n**QTH:** Lokalizacja.")

# 7. PRZEMIENNIKI
with tabs[6]:
    st.header("🗺️ Przemienniki PL")
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
        f = st.number_input("Freq (MHz)", 145.5)
        st.success(f"Dipol: {142.5/f:.2f}m")
    with c2:
        st.metric("Fala", f"{300/f:.2f}m")
    with c3:
        la = st.number_input("Lat", 52.23); lo = st.number_input("Lon", 21.01)
        st.info(f"QTH: {latlon_to_maidenhead(la, lo)}")

# 9. WEBSDR
with tabs[8]:
    st.header("🌐 WebSDR")
    st.dataframe(pd.DataFrame(websdr_list), column_config={"Link": st.column_config.LinkColumn("Link", display_text="Otwórz 🔗")}, use_container_width=True, hide_index=True)

# 10. LOGBOOK (ULEPSZONY - BAZA PLIKOWA)
with tabs[9]:
    st.header("📝 Dziennik Nasłuchów (Logbook)")
    st.markdown("Twoja osobista baza łączności. Dane są zapisywane w pliku na serwerze.")
    
    # Ładowanie danych
    if 'logbook_df' not in st.session_state:
        st.session_state.logbook_df = load_logbook()

    # Formularz
    with st.form("log_form", clear_on_submit=True):
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1: t_in = st.text_input("Godzina (UTC)", value=datetime.now(timezone.utc).strftime("%H:%M"))
        with c2: f_in = st.text_input("Freq (MHz)")
        with c3: s_in = st.text_input("Stacja / Znak")
        with c4: m_in = st.selectbox("Modulacja", ["FM", "AM", "SSB", "CW", "DMR"])
        with c5: r_in = st.text_input("Raport (RST)", "59")
        
        submitted = st.form_submit_button("➕ Zapisz w Bazie")
        if submitted:
            if f_in and s_in:
                new_entry = pd.DataFrame([{
                    "Data": datetime.now().strftime("%Y-%m-%d"),
                    "Godzina (UTC)": t_in,
                    "Freq (MHz)": f_in,
                    "Stacja": s_in,
                    "Modulacja": m_in,
                    "Raport": r_in
                }])
                st.session_state.logbook_df = pd.concat([st.session_state.logbook_df, new_entry], ignore_index=True)
                save_logbook(st.session_state.logbook_df)
                st.success("Zapisano!")
            else:
                st.error("Podaj przynajmniej częstotliwość i znak.")

    # Wyświetlanie Tabeli
    st.subheader("Ostatnie wpisy")
    st.dataframe(st.session_state.logbook_df, use_container_width=True)
    
    # Przycisk pobierania (Backup)
    csv = st.session_state.logbook_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Pobierz Logbook (CSV)",
        data=csv,
        file_name='radio_logbook.csv',
        mime='text/csv',
    )

st.markdown("---")
st.caption("Centrum Dowodzenia Radiowego v11.0 Stable | Dane: CelesTrak, N0NBH | Czas: UTC")
