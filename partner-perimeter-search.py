import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from folium import Popup, IFrame
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
from PIL import Image
from folium.plugins import MarkerCluster
import html
import re

# Hilfsfunktion, um problematische Zeichen zu filtern
def sanitize_text(text):
    # Entferne problematische Zeichen, Emojis, Steuerzeichen etc.
    text = str(text)
    text = re.sub(r"[^\w\s.,\-@&äöüÄÖÜß]", "", text)  # erlaubt: Buchstaben, Zahlen, gewisse Satzzeichen
    text = text.replace("\n", " ").replace("\r", " ")  # Zeilenumbrüche raus
    return html.escape(text.strip())

def get_marker_color(row):
    if str(row.get("Sportnavi")) == "X":
        return "blue"
    elif str(row.get("Egym Wellpass")) == "X":
        return "green"
    elif str(row.get("Hansefit")) == "X":
        return "red"
    elif str(row.get("USC")) == "X":
        return "orange"
    elif str(row.get("Kein Aggregartor")) == "X":
        return "gray"
    else:
        return "cadetblue"

# Beispiel: Farbe als Emoji (für Anzeige)
def farbe_emoji(hex_code):
    if hex_code.lower() == "#ff0000":
        return "🔴"
    elif hex_code.lower() == "#00ff00":
        return "🟢"
    elif hex_code.lower() == "#0000ff":
        return "🔵"
    else:
        return "⚪"

def get_aggregator(row):
    aggregators = []
    if str(row.get("Sportnavi")) == "X":
        aggregators.append("Sportnavi")
    if str(row.get("Egym Wellpass")) == "X":
        aggregators.append("Egym Wellpass")
    if str(row.get("Hansefit")) == "X":
        aggregators.append("Hansefit")
    if str(row.get("USC")) == "X":
        aggregators.append("USC")
    if str(row.get("Kein Aggregartor")) == "X":
        aggregators.append("Kein Aggregator")
    return ", ".join(aggregators) if aggregators else "Unbekannt"

st.set_page_config(page_title="Standortsuche für Partner", layout="wide")

# Bild laden
logo = Image.open("logo/sportnavi-logo.png")
# Bild anzeigen (z. B. ganz oben)
st.image(logo, width=200)

@st.cache_data
def load_data():
    return pd.read_csv("FinalGeocoded.csv", sep=";", engine="python", on_bad_lines='skip')

@st.cache_data
def geocode_plz(plz):
    geolocator = Nominatim(user_agent="geo_search")
    loc = geolocator.geocode(f"{plz}, Germany")
    if loc:
        return (loc.latitude, loc.longitude)
    return None

df = load_data()

# Input-Felder
st.title("📍 Standortsuche für Partner")
with st.form("filters"):
    name = st.text_input("🔍 Name enthält")
    typ = st.text_input("🏷️ Typ enthält")
    ort = st.text_input("📌 Ort enthält")
    plz = st.text_input("🔢 PLZ")
    radius = st.number_input("📏 Umkreis (km)", min_value=1, max_value=100, value=10)
    use_cluster = st.checkbox("📌 Marker gruppieren (Cluster aktivieren)", value=False)
    submitted = st.form_submit_button("🔎 Suche starten")

if submitted:
    with st.spinner("🔄 Deine Suche läuft..."):    
        # Filter anwenden
        filtered = df[
            df["Name"].astype(str).str.contains(name, case=False, na=False) &
            df["Typ"].astype(str).str.contains(typ, case=False, na=False) &
            df["Ort"].astype(str).str.contains(ort, case=False, na=False)
        ].copy()

        if plz:
            # Geokoordinaten ermitteln
            coords = geocode_plz(plz)
            if coords:
                def dist(row):
                    try:
                        lat = float(str(row["Latitude"]).replace(",", "."))
                        lon = float(str(row["Longitute"]).replace(",", "."))
                        # geopy erwartet: (lat, lon)
                        return geodesic((lat, lon), coords).km
                    except:
                        return float("inf")

                filtered["Entfernung_km"] = filtered.apply(dist, axis=1)
                filtered = filtered[filtered["Entfernung_km"] <= radius]
                filtered = filtered.sort_values("Entfernung_km")

                if len(filtered) > 0:
                    st.success(f"{len(filtered)} Treffer im Umkreis von {radius} km um {plz}.")

                    # Nur Anzeige: Spalten umbenennen, Index entfernen
                    anzeige_df = filtered[[
                        "Name", "Typ", "Straße", "PLZ", "Ort", "Egym Wellpass", "Hansefit", "USC", "Sportnavi", "Kein Aggregartor", "Entfernung_km"
                    ]].rename(columns={
                        "Egym Wellpass": "Egym",
                        "Sportnavi": "SN",
                        "Entfernung_km": "Entfernung"
                    }).reset_index(drop=True)

                    anzeige_df = anzeige_df.fillna("")
                    # Entfernung auf Deutsch formatieren: 2 Nachkommastellen mit Komma statt Punkt
                    anzeige_df["Entfernung"] = anzeige_df["Entfernung"].apply(lambda x: f"{x:.2f}".replace(".", ","))

                    st.dataframe(anzeige_df, use_container_width=True)

                    # Nur gültige Koordinaten verwenden
                    filtered = filtered.dropna(subset=["Latitude", "Longitute"])
                    filtered["lat"] = filtered["Latitude"].astype(str).str.replace(",", ".").astype(float)
                    filtered["lon"] = filtered["Longitute"].astype(str).str.replace(",", ".").astype(float)
                    filtered = filtered.dropna(subset=["lat", "lon"])

                    if not filtered.empty:
                        m = folium.Map(location=[filtered["lat"].mean(), filtered["lon"].mean()], zoom_start=10)

                        # Cluster optional hinzufügen
                        if use_cluster:
                            marker_container = MarkerCluster().add_to(m)
                        else:
                            marker_container = m  # direkt auf die Karte

                        for _, row in filtered.iterrows():
                            name = sanitize_text(row.get("Name", ""))
                            strasse = sanitize_text(row.get("Straße", ""))
                            plz_ort = sanitize_text(f'{row.get("PLZ", "")} {row.get("Ort", "")}')
                            entfernung = f'{row.get("Entfernung_km", 0):.1f} km'

                            # Popup komplett als reinen Text ohne HTML/JS
                            aggregator = get_aggregator(row)

                            popup_text = f"""{name}
                            <br>{strasse}
                            <br>{plz_ort}
                            <br>{entfernung}
                            <br>Aggregator: {aggregator}"""

                            popup = Popup(popup_text, max_width=300)

                            color = get_marker_color(row)  # 🔄 Markerfarbe bestimmen

                            folium.Marker(
                                location=[row["lat"], row["lon"]],
                                tooltip=name,
                                popup=popup,
                                icon=folium.Icon(color=color)
                            ).add_to(marker_container)

                        st_folium(m, height=500, width=1200, returned_objects=[])
                    else:
                        st.warning("Keine gültigen Koordinaten für die Kartendarstellung.")
                else:
                    st.info("Die Suche hat keine Partner gefunden.")
            else:
                st.error("PLZ konnte nicht geokodiert werden.")
        else:
            st.info("Bitte eine PLZ für die Suche eingeben.")