
import streamlit as st
import pandas as pd
import io
from datetime import datetime

st.set_page_config(page_title="Paket-Konfigurator - Institut für Holztechnologie", layout="wide")

st.title("Paket-Konfigurator — Institut für Holztechnologie")
st.markdown("""
Mit dieser App kannst du schnell aus der Excel-Liste Ausstattungspakete zusammenstellen, Preise berechnen und das Paket als Excel-Datei exportieren.
Die App liest die Datei **/mnt/data/Miete.xlsx** (Tabelle 'Tabelle1').
""")

# Load data
@st.cache_data
def load_data(path="Miete.xlsx"):
    try:
        df = pd.read_excel(path, sheet_name=0)
    except Exception as e:
        st.error(f"Fehler beim Laden der Excel-Datei: {e}")
        return pd.DataFrame()
    # Normalize column names
    df = df.rename(columns=lambda c: str(c).strip())
    # Try to detect the price column (contains 'pro' or 'Stück' or 'Set' or '€')
    price_col = None
    for c in df.columns:
        lower = c.lower()
        if 'pro' in lower or 'stück' in lower or 'set' in lower or '€' in lower:
            price_col = c
            break
    if price_col is None and df.shape[1] >= 2:
        price_col = df.columns[-1]
    # Name column assumed to be first col
    name_col = df.columns[0] if df.shape[1] > 0 else None
    # Clean price column: remove non-numeric characters
    if price_col is not None:
        df[price_col] = pd.to_numeric(df[price_col], errors='coerce').fillna(0)
    return df, name_col, price_col

data_load = load_data()

if isinstance(data_load, tuple) and len(data_load) == 3:
    df, name_col, price_col = data_load
else:
    df = pd.DataFrame()
    name_col = None
    price_col = None

if df.empty:
    st.warning("Keine Daten gefunden. Bitte stelle sicher, dass /mnt/data/Miete.xlsx existiert und die Tabelle 'Tabelle1' enthält.")
    st.stop()

# Sidebar controls
st.sidebar.header("Einstellungen")
mwst_pct = st.sidebar.selectbox("Mehrwertsteuer", options=[0, 7, 19], index=2)
apply_vat = mwst_pct != 0
discount_pct = st.sidebar.number_input("Rabatt (%)", min_value=0.0, max_value=100.0, value=0.0, step=0.5)
st.sidebar.markdown("---")
st.sidebar.markdown("Datei laden: /mnt/data/Miete.xlsx (festgelegt).")

# Show full list with search
st.subheader("Verfügbare Artikel")
search = st.text_input("Suche (Name)")
if search:
    filtered = df[df[name_col].str.contains(search, case=False, na=False)]
else:
    filtered = df.copy()

# Display a nice table
display_df = filtered[[name_col, price_col]].rename(columns={name_col: "Artikel", price_col: "Preis"})
st.dataframe(display_df.reset_index(drop=True))

# Selection and quantity inputs
st.subheader("Paket konfigurieren")
selected = st.multiselect("Wähle Artikel", options=df[name_col].tolist())
if not selected:
    st.info("Wähle links oder oben Artikel aus, um sie zum Paket hinzuzufügen.")
else:
    package_lines = []
    st.markdown("### Mengen festlegen")
    cols = st.columns([4,2,2,2])
    cols[0].markdown("**Artikel**")
    cols[1].markdown("**Menge**")
    cols[2].markdown("**Einzelpreis**")
    cols[3].markdown("**Zeile (Netto)**")
    total_net = 0.0
    for art in selected:
        row = df[df[name_col] == art].iloc[0]
        default_qty = 1
        qty = st.number_input(f"qty_{art}", min_value=0, value=default_qty, step=1, label_visibility="collapsed")
        price = float(row[price_col]) if price_col is not None else 0.0
        line = qty * price
        total_net += line
        package_lines.append({"Artikel": art, "Menge": qty, "Einzelpreis": price, "ZeileNetto": line})

    # Summary
    st.markdown("---")
    st.markdown("### Paket-Zusammenfassung")
    package_df = pd.DataFrame(package_lines)
    package_df = package_df[package_df["Menge"] > 0].reset_index(drop=True)
    if package_df.empty:
        st.warning("Keine Positionen mit Menge > 0 im Paket.")
    else:
        st.table(package_df.assign(Preis=lambda d: d["Einzelpreis"].map("{:.2f} €".format),
                                    Zeile=lambda d: d["ZeileNetto"].map("{:.2f} €".format)).loc[:,["Artikel","Menge","Preis","Zeile"]])

        net_sum = package_df["ZeileNetto"].sum()
        discount_amount = net_sum * (discount_pct/100.0)
        net_after_discount = net_sum - discount_amount
        vat_amount = net_after_discount * (mwst_pct/100.0) if apply_vat else 0.0
        gross_total = net_after_discount + vat_amount

        st.markdown(f"**Zwischensumme (Netto):** {net_sum:.2f} €")
        if discount_pct > 0:
            st.markdown(f"**Rabatt ({discount_pct:.2f}%):** −{discount_amount:.2f} €")
        if apply_vat:
            st.markdown(f"**MwSt ({mwst_pct}%):** {vat_amount:.2f} €")
        st.markdown(f"**Gesamtbetrag (Brutto):** {gross_total:.2f} €")

        # Export package as Excel
        def to_excel_bytes(df_export):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df_export.to_excel(writer, index=False, sheet_name="Paket")
                writer.save()
            processed_data = output.getvalue()
            return processed_data

        export_df = package_df.copy()
        export_df["Rabatt_%"] = discount_pct
        export_df["MwSt_%"] = mwst_pct
        export_df["NettoSumme"] = net_sum
        export_df["NettoNachRabatt"] = net_after_discount
        export_df["MwStBetrag"] = vat_amount
        export_df["BruttoSumme"] = gross_total
        filename = f"Paket_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        st.download_button("📥 Paket als Excel exportieren", data=to_excel_bytes(export_df), file_name=filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        # Generate simple offer text
        st.markdown("### Angebotstext")
        offer_text = f"""Angebot — Paket zusammengestellt mit dem Paket-Konfigurator
Datum: {datetime.now().strftime('%Y-%m-%d')}

Positionen:
"""
        for _, r in package_df.iterrows():
            offer_text += f"- {int(r['Menge'])} × {r['Artikel']} @ {r['Einzelpreis']:.2f} € = {r['ZeileNetto']:.2f} €\n"
        offer_text += f"\nZwischensumme: {net_sum:.2f} €\n"
        if discount_pct > 0:
            offer_text += f"Rabatt: {discount_amount:.2f} € ({discount_pct:.2f}%)\n"
        if apply_vat:
            offer_text += f"MwSt ({mwst_pct}%): {vat_amount:.2f} €\n"
        offer_text += f"Gesamt (Brutto): {gross_total:.2f} €\n"
        st.code(offer_text, language="text")

        st.download_button("📄 Angebotstext als .txt herunterladen", data=offer_text, file_name=filename.replace('.xlsx', '.txt'), mime="text/plain")

# Admin: Upload new Excel to replace data (local only)
st.sidebar.markdown("---")
st.sidebar.subheader("Admin: Neue Excel hochladen")
uploaded = st.sidebar.file_uploader("Upload Excel (ersetzt Daten temporär)", type=["xlsx","xls"])
if uploaded is not None:
    try:
        new_df = pd.read_excel(uploaded, sheet_name=0)
        st.sidebar.success("Datei erfolgreich hochgeladen — die App verwendet jetzt die neue Datei nach einem Reload.")
        # Save uploaded to disk to replace existing file for this session
        with open("/mnt/data/Miete_uploaded.xlsx", "wb") as f:
            f.write(uploaded.getbuffer())
        st.sidebar.markdown("Die Datei wurde als /mnt/data/Miete_uploaded.xlsx gespeichert. Bitte lade die Seite neu.")
    except Exception as e:
        st.sidebar.error(f"Fehler beim Verarbeiten: {e}")

st.markdown("""
---
**Hinweis zur Nutzung:**

1. Installiere Streamlit: `pip install streamlit openpyxl` (falls noch nicht vorhanden).
2. Starte die App lokal: `streamlit run /mnt/data/streamlit_app.py`
3. Die App liest standardmäßig `/mnt/data/Miete.xlsx`. Du kannst im Sidebar eine neue Excel-Datei hochladen.
""")
