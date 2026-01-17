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

def latlon_to_maidenhead(lat, lon):
    """Zamienia współrzędne na QTH Locator (np. JO92LE)."""
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
# 2. BAZA DANYCH
# ===========================

repeater_list = [
    {"Znak": "SR5WA", "Freq": "439.350", "CTCSS": "127.3", "Lat": 52.23, "Lon": 21.01, "Loc": "Warszawa (Pałac Kultury)", "Shift": "-7.6"},
    {"Znak": "SR5W", "Freq": "145.600", "CTCSS": "127.3", "Lat": 52.21, "Lon": 20.98, "Loc": "Warszawa", "Shift": "-0.6"},
    {"Znak": "SR6J", "Freq": "145.675", "CTCSS": "94.8", "Lat": 50.78, "Lon": 15.56, "Loc": "Śnieżne Kotły (Ogromny Zasięg!)", "Shift": "-0.6"},
    {"Znak": "SR9P", "Freq": "438.900", "CTCSS": "103.5", "Lat": 50.06, "Lon": 19.94, "Loc": "Kraków", "Shift": "-7.6"},
    {"Znak": "SR9C", "Freq": "145.775", "CTCSS": "103.5", "Lat": 49.65, "Lon": 19.88, "Loc": "Chorągwica (Kraków)", "Shift": "-0.6"},
    {"Znak": "SR2Z", "Freq": "145.725", "CTCSS": "94.8", "Lat": 54.37, "Lon": 18.60, "Loc": "Gdańsk (Olivia Star)", "Shift": "-0.6"},
    {"Znak": "SR2C", "Freq": "438.800", "CTCSS": "94.8", "Lat": 54.52, "Lon": 18.53, "Loc": "Gdynia (Chwaszczyno)", "Shift": "-7.6"},
    {"Znak": "SR3PO", "Freq": "438.850", "CTCSS": "110.9", "Lat": 52.40, "Lon": 16.92, "Loc": "Poznań", "Shift": "-7.6"},
    {"Znak": "SR8L", "Freq": "145.625", "CTCSS": "107.2", "Lat": 51.24, "Lon": 22.57, "Loc": "Lublin", "Shift": "-0.6"},
    {"Znak": "SR4J", "Freq": "439.100", "CTCSS": "88.5", "Lat": 53.77, "Lon": 20.48, "Loc": "Olsztyn (Pieczewo)", "Shift": "-7.6"},
    {"Znak": "SR7V", "Freq": "145.6875", "CTCSS": "88.5", "Lat": 50.80, "Lon": 19.11, "Loc": "Częstochowa", "Shift": "-0.6"},
    {"Znak": "SR1Z", "Freq": "145.6375", "CTCSS": "118.8", "Lat": 53.42, "Lon": 14.55, "Loc": "Szczecin", "Shift": "-0.6"},
]

global_stations = [
    {"MHz": "0.225", "Pasmo": "LW (Długie)", "Mod": "AM", "Kategoria": "Polska", "Nazwa": "Polskie Radio Jedynka", "Opis": "Nadajnik w Solcu Kujawskim. Zasięg: cała Europa. Kluczowy w sytuacjach kryzysowych."},
    {"MHz": "0.198", "Pasmo": "LW (Długie)", "Mod": "AM", "Kategoria": "Europa", "Nazwa": "BBC Radio 4", "Opis": "Legendarna stacja brytyjska. Zasięg zachodnia Europa."},
    {"MHz": "0.153", "Pasmo": "LW (Długie)", "Mod": "AM", "Kategoria": "Europa", "Nazwa": "Radio Romania Antena Satelor", "Opis": "Bardzo silny sygnał z Rumunii (muzyka ludowa)."},
    {"MHz": "6.000-6.200", "Pasmo": "49m (SW)", "Mod": "AM", "Kategoria": "Świat", "Nazwa": "Pasmo 49m (Wieczór)", "Opis": "Główne pasmo wieczorne dla stacji europejskich (BBC, RFI)."},
    {"MHz": "9.400-9.900", "Pasmo": "31m (SW)", "Mod": "AM", "Kategoria": "Świat", "Nazwa": "Pasmo 31m (Całodobowe)", "Opis": "Najpopularniejsze pasmo międzynarodowe."},
    {"MHz": "15.100-15.800", "Pasmo": "19m (SW)", "Mod": "AM", "Kategoria": "Świat", "Nazwa": "Pasmo 19m (Dzień)", "Opis": "Stacje dalekiego zasięgu (Chiny, USA) w ciągu dnia."},
    {"MHz": "4.625", "Pasmo": "SW", "Mod": "USB/AM", "Kategoria": "Utility", "Nazwa": "UVB-76 (The Buzzer)", "Opis": "Rosyjska stacja numeryczna. Nadaje 'brzęczenie' i czasem szyfry."},
    {"MHz": "5.000 / 10.000", "Pasmo": "SW", "Mod": "AM", "Kategoria": "Wzorzec Czasu", "Nazwa": "WWV / WWVH", "Opis": "Amerykański wzorzec czasu."},
    {"MHz": "14.230", "Pasmo": "20m", "Mod": "SSTV (USB)", "Kategoria": "Ham Radio", "Nazwa": "SSTV Call Freq", "Opis": "Krótkofalowcy przesyłający obrazki (Analogowo)."},
    {"MHz": "5.450", "Pasmo": "SW", "Mod": "USB", "Kategoria": "Lotnictwo", "Nazwa": "RAF Volmet", "Opis": "Pogoda dla lotnictwa (Royal Air Force)."},
]

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
# 4. GŁÓWNA BAZA DANYCH
# ===========================

special_freqs = [
    {"MHz": "145.800", "Pasmo": "2m", "Mod": "NFM", "Kategoria": "Satelity", "Nazwa": "ISS (Głos)", "Opis": "Region 1 Voice - Główny kanał foniczny ISS"},
    {"MHz": "145.825", "Pasmo": "2m", "Mod": "FM", "Kategoria": "Satelity", "Nazwa": "ISS (APRS)", "Opis": "Packet Radio 1200bps / Digipeater"},
    {"MHz": "437.800", "Pasmo": "70cm", "Mod": "FM", "Kategoria": "Satelity", "Nazwa": "ISS (Repeater)", "Opis": "Downlink przemiennika (Uplink: 145.990 z tonem 67.0)"},
    {"MHz": "137.100", "Pasmo": "VHF", "Mod": "WFM", "Kategoria": "Satelity", "Nazwa": "NOAA 19", "Opis": "APT - Analogowe zdjęcia Ziemi (przeloty popołudniowe)"},
    {"MHz": "121.500", "Pasmo": "Air", "Mod": "AM", "Kategoria": "Lotnictwo", "Nazwa": "Air Guard", "Opis": "Międzynarodowy kanał RATUNKOWY (wymaga radia z AM!)"},
    {"MHz": "129.500", "Pasmo": "Air", "Mod": "AM", "Kategoria": "Lotnictwo", "Nazwa": "LPR (Operacyjny)", "Opis": "Częsty kanał Lotniczego Pogotowia (może się różnić lokalnie)"},
    {"MHz": "148.6625", "Pasmo": "VHF", "Mod": "NFM", "Kategoria": "Służby", "Nazwa": "PSP (B028)", "Opis": "Krajowy Kanał Ratowniczo-Gaśniczy (ogólnopolski)"},
    {"MHz": "156.800", "Pasmo": "Marine", "Mod": "FM", "Kategoria": "Morskie", "Nazwa": "Kanał 16", "Opis": "Morski kanał ratunkowy i wywoławczy"},
    {"MHz": "145.500", "Pasmo": "2m", "Mod": "FM", "Kategoria": "Ham", "Nazwa": "VHF Call", "Opis": "Wywoławcza (rozmowy lokalne)"},
]

data_freq = special_freqs + generate_pmr_list() + generate_cb_list()

# ===========================
# 5. INTERFEJS APLIKACJI
# ===========================

# --- NAGŁÓWEK ---
c_title, c_clock, c_visits = st.columns([3, 1, 1])
with c_title: st.title("📡 Centrum Dowodzenia")
with c_clock: st.markdown(f"<div style='text-align: right; font-family: monospace; color: #00ff41;'><b>ZULU TIME (UTC):</b> {get_utc_time()}</div>", unsafe_allow_html=True)
with c_visits: st.markdown(f"<div style='text-align: right; color: gray;'>Odwiedzin: <b>{visit_count}</b></div>", unsafe_allow_html=True)


# --- ZAKŁADKI (8 ZAKŁADEK - DODANO NARZĘDZIA) ---
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "📡 Tracker & Skaner", 
    "☀️ Pogoda Kosmiczna", 
    "🆘 Łączność Kryzysowa", 
    "🌍 Czas na Świecie", 
    "📻 Stacje Globalne",
    "📚 Słownik & Ciekawostki",
    "🗺️ Przemienniki",
    "🧮 Kalkulatory"
])

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
                fig.add_trace(go.Scattergeo(lat=path_lat, lon=path_lon, mode="lines", line=dict(color="blue", width=2, dash="dot"), name="Orbita"))
                fig.add_trace(go.Scattergeo(lat=[lat], lon=[lon], mode="text", text=["🛰️"], textfont=dict(size=30), name="ISS Teraz"))
                fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=450, geo=dict(projection_type="natural earth", showland=True, landcolor="rgb(230, 230, 230)", showocean=True, oceancolor="rgb(200, 225, 255)", showcountries=True), showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
                if st.button("🔄 Odśwież pozycję"): st.rerun()
            else: st.error("Błąd obliczeń.")
        else: st.error("Błąd TLE.")

    with col_data:
        st.subheader("Baza Częstotliwości (PL)")
        df = pd.DataFrame(data_freq)
        c_search, c_filter = st.columns([2,1])
        with c_search: search = st.text_input("🔍 Szukaj...", placeholder="Np. Kanał 19, PMR 3")
        with c_filter: cat_filter = st.multiselect("Kategorie", df["Kategoria"].unique(), placeholder="Wybierz...")
        if search: df = df[df.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)]
        if cat_filter: df = df[df["Kategoria"].isin(cat_filter)]
        st.dataframe(df[["MHz", "Nazwa", "Mod", "Opis"]], use_container_width=True, hide_index=True, height=450)

# --- ZAKŁADKA 2: POGODA KOSMICZNA ---
with tab2:
    st.header("☀️ Pogoda Kosmiczna & Propagacja")
    col_solar, col_info = st.columns([1, 1])
    with col_solar:
        st.image("https://www.hamqsl.com/solar101vhf.php", caption="Dane na żywo: N0NBH", use_container_width=False)
        st.markdown("---")
        st.image("https://www.hamqsl.com/solarmap.php", caption="Mapa Dzień/Noc (Greyline)", use_container_width=True)
    with col_info:
        st.success("### SFI (Solar Flux Index)")
        st.markdown("""
        "Paliwo" dla fal radiowych. Im wyższa liczba, tym lepsze odbicia od jonosfery.
        * **< 70:** Słabe warunki (Drut kolczasty zamiast anteny).
        * **70 - 100:** Średnie warunki.
        * **> 100:** Dobre warunki (Europa/USA słyszalne głośno).
        """)
        st.error("### K-Index (Burze Magnetyczne)")
        st.markdown("""
        Poziom zakłóceń ziemskiego pola magnetycznego. Tu chcemy jak najmniej!
        * **0 - 2:** Cisza, czysty odbiór (Super!).
        * **3 - 4:** Lekkie zakłócenia.
        * **> 5:** Burza geomagnetyczna. Szumy, zaniki sygnału.
        """)

# --- ZAKŁADKA 3: KRYZYSOWE (PEŁNE DANE PRZYWRÓCONE) ---
with tab3:
    st.header("🆘 Procedury Awaryjne (Polska)")
    
    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.error("### 1. Reguła 3-3-3")
        st.markdown("""
        System nasłuchu w sytuacji kryzysowej (brak GSM):
        * **Kiedy?** Co 3 godziny (12:00, 15:00, 18:00...)
        * **Ile?** 3 minuty nasłuchu, potem wywołanie.
        * **Gdzie?** * **PMR:** Kanał 3 (446.03125 MHz)
            * **CB:** Kanał 3 (26.980 MHz AM)
        
        *Włącz radio o pełnej godzinie. Najpierw słuchaj, potem nadawaj komunikat "Mayday" lub informacyjny.*
        """)

    with c2:
        st.warning("### 2. Sprzęt")
        st.markdown("""
        * **Baofeng UV-5R:** Nie odbiera AM (Lotnictwo/CB). Dobre do PMR i Służb.
        * **Zasięg (PMR):** * Miasto: 500m - 1km. 
            * Otwarty teren: do 5km. 
            * Góry/Kosmos: >100km.
        * **Antena:** Fabryczna "gumowa" antena to najsłabsze ogniwo. Warto wymienić na dłuższą (np. Nagoya 771), co poprawia zasięg nawet o 50%.
        """)

    with c3:
        st.info("### 3. Komunikacja (Raport SALT)")
        st.markdown("""
        W sytuacji kryzysowej meldunki muszą być krótkie i konkretne. Użyj formatu **S.A.L.T**:
        
        * **S (Size):** Wielkość zdarzenia / Liczba poszkodowanych.
        * **A (Activity):** Co się dzieje? Czego potrzeba?
        * **L (Location):** Gdzie jesteście? (Adres, charakterystyczny punkt).
        * **T (Time):** Kiedy to się stało?
        """)

# --- ZAKŁADKA 4: STREFY CZASOWE ---
with tab4:
    st.header("🌍 Czas na Świecie")
    zones = [("UTC", "UTC"), ("Warszawa", "Europe/Warsaw"), ("New York", "America/New_York"), ("Los Angeles", "America/Los_Angeles"), ("Tokio", "Asia/Tokyo"), ("Sydney", "Australia/Sydney")]
    cols = st.columns(3)
    for i, (name, zone) in enumerate(zones):
        with cols[i % 3]:
            st.markdown(f"<div style='background:#1E1E1E;padding:15px;border-radius:10px;text-align:center;margin-bottom:20px;'><div style='color:#888;'>{name}</div><div style='color:#FFF;font-size:2em;font-weight:bold;'>{get_time_in_zone(zone)}</div></div>", unsafe_allow_html=True)

# --- ZAKŁADKA 5: STACJE GLOBALNE ---
with tab5:
    st.header("📻 Globalne Stacje Radiowe")
    st.dataframe(pd.DataFrame(global_stations), use_container_width=True, hide_index=True)

# --- ZAKŁADKA 6: SŁOWNIK I CIEKAWOSTKI (PEŁNE DANE PRZYWRÓCONE) ---
with tab6:
    st.header("📚 Edukacja Radiowa")
    
    col_dict, col_facts = st.columns(2)
    
    with col_dict:
        st.subheader("📖 Słownik Pojęć")
        st.markdown("""
        * **AM (Amplituda):** Modulacja używana w lotnictwie i na CB. Odporna na efekt "zjadania" słabszego sygnału.
        * **FM / NFM (Częstotliwość):** Modulacja "czysta", ale działająca zero-jedynkowo (albo słyszysz, albo nie).
        * **SSB (LSB/USB):** Modulacja jednowstęgowa. Pozwala na łączności międzykontynentalne na falach krótkich.
        * **Squelch (SQ):** Bramka szumów. Wycisza radio, gdy sygnał jest zbyt słaby.
        * **CTCSS / DCS:** Kody (tony) dodawane do głosu. Działają jak klucz do drzwi - otwierają przemiennik.
        * **Shift (Offset):** Różnica między częstotliwością, na której słuchasz, a tą, na której nadajesz (niezbędne przy przemiennikach).
        * **73:** Międzynarodowy kod oznaczający "Pozdrawiam".
        * **QTH:** Kod oznaczający "Moja lokalizacja".
        * **DX:** Łączność dalekiego zasięgu (poza granice kraju/kontynentu).
        """)

    with col_facts:
        st.subheader("💡 Ciekawostki")
        st.markdown("""
        * **Dlaczego polskie CB to 'Zera'?**
          Większość świata używa częstotliwości kończących się na 5 (np. 27.185 MHz). W Polsce historycznie przyjęto końcówki 0 (27.180 MHz). Aby rozmawiać z polskimi kierowcami, musisz mieć radio przestawione w standard "PL".
        
        * **PMR - Zasięg to mit?**
          Producenci piszą "zasięg do 10 km". To prawda, ale tylko ze szczytu góry na inną górę. W gęstej zabudowie miejskiej realny zasięg to często 300-500 metrów.
        
        * **Dlaczego samoloty używają AM?**
          W modulacji FM, gdy dwie osoby nadają naraz, radio odtwarza tylko silniejszy sygnał (słabszy znika). W lotnictwie to niebezpieczne - kontroler musi wiedzieć, że ktoś próbuje się wciąć. W AM słychać obu naraz jako pisk/interferencję.
          
        * **Efekt Dopplera:**
          Gdy ISS nadlatuje w Twoją stronę z prędkością 28 000 km/h, fale radiowe są "ściskane" i słyszysz je na wyższej częstotliwości (+3 kHz). Gdy odlatuje - na niższej.
        """)

# --- ZAKŁADKA 7: PRZEMIENNIKI ---
with tab7:
    st.header("🗺️ Mapa Przemienników (Polska)")
    col_map_rep, col_info_rep = st.columns([3, 1])
    df_rep = pd.DataFrame(repeater_list)
    with col_map_rep:
        fig_rep = go.Figure(go.Scattermapbox(lat=df_rep['Lat'], lon=df_rep['Lon'], mode='markers', marker=go.scattermapbox.Marker(size=14, color='orange'), text=df_rep['Znak'], hoverinfo='text', hovertext=df_rep.apply(lambda row: f"<b>{row['Znak']}</b><br>{row['Loc']}<br>Freq: {row['Freq']} MHz", axis=1)))
        fig_rep.update_layout(mapbox_style="open-street-map", mapbox=dict(center=go.layout.mapbox.Center(lat=52.00, lon=19.00), zoom=5), margin={"r":0,"t":0,"l":0,"b":0}, height=500)
        st.plotly_chart(fig_rep, use_container_width=True)
    with col_info_rep:
        st.dataframe(df_rep[["Znak", "Freq", "Loc"]], hide_index=True, use_container_width=True)

# --- ZAKŁADKA 8: KALKULATORY (NOWA!) ---
with tab8:
    st.header("🧮 Narzędzia Radiowe (Toolbox)")
    
    col_ant, col_wave, col_qth = st.columns(3)
    
    # 1. Kalkulator Anteny (Dipol)
    with col_ant:
        st.subheader("📡 Kalkulator Dipola")
        st.markdown("Oblicz długość anteny (dipol półfalowy) dla danej częstotliwości.")
        freq_input = st.number_input("Częstotliwość (MHz):", value=145.500, step=0.001, format="%.3f")
        
        if freq_input > 0:
            # Wzór: 142.5 / f (dla dipola półfalowego ze współczynnikiem 0.95)
            total_len = 142.5 / freq_input
            arm_len = total_len / 2
            st.success(f"**Cała antena:** {total_len*100:.1f} cm")
            st.info(f"**Jedno ramię:** {arm_len*100:.1f} cm")
        else:
            st.error("Wpisz poprawną częstotliwość.")

    # 2. Kalkulator Długości Fali
    with col_wave:
        st.subheader("🌊 Długość Fali")
        st.markdown("Przelicz częstotliwość na długość fali (pasmo).")
        freq_wave = st.number_input("Częstotliwość (MHz)", value=27.180, step=0.001, format="%.3f")
        
        if freq_wave > 0:
            wavelength = 300 / freq_wave
            band_name = ""
            if 26 <= freq_wave <= 28: band_name = "(Pasmo CB / 11m)"
            elif 144 <= freq_wave <= 146: band_name = "(Pasmo 2m)"
            elif 430 <= freq_wave <= 446: band_name = "(Pasmo 70cm)"
            
            st.metric("Długość fali", f"{wavelength:.2f} m")
            if band_name: st.caption(band_name)

    # 3. Lokalizator QTH
    with col_qth:
        st.subheader("📍 Lokalizator QTH")
        st.markdown("Zamień współrzędne GPS na kod Maidenhead.")
        qth_lat = st.number_input("Szerokość (Lat):", value=52.23, step=0.01)
        qth_lon = st.number_input("Długość (Lon):", value=21.01, step=0.01)
        
        locator = latlon_to_maidenhead(qth_lat, qth_lon)
        st.success(f"Twój Locator: **{locator}**")
        st.caption("Podawaj ten kod przy potwierdzaniu łączności.")

st.markdown("---")
st.caption("Centrum Dowodzenia Radiowego v8.1 FULL | Dane: CelesTrak, N0NBH | Czas: UTC")
