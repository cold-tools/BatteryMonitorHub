import streamlit as st
import pandas as pd
from streamlit_autorefresh import st_autorefresh
import wmi
from datetime import datetime
from bs4 import BeautifulSoup
import plotly.express as px
import pyarrow.parquet as pq
import pyarrow as pa
import requests
import qrcode
from io import BytesIO
from PIL import Image, ImageOps
import json

# Auto-refresh every 30 seconds for live data
st_autorefresh(interval=30000)

# Initialize WMI for live battery data
w = wmi.WMI(namespace="root\\WMI")
if "start_time" not in st.session_state:
    st.session_state.start_time = datetime.now()

# Initialize the data storage in session state for live data if it doesn't exist
if "battery_data" not in st.session_state:
    st.session_state.battery_data = pd.DataFrame()

# Path to the battery report HTML file
report_path = 'battery-report.html'

# Function to collect live battery status data
def collect_battery_data():
    new_data = []
    for b in w.query("SELECT * FROM BatteryStatus"):
        timestamp = datetime.now()
        test_time = (timestamp - st.session_state.start_time).total_seconds()

        voltage = getattr(b, 'Voltage', None)
        remaining_capacity = getattr(b, 'RemainingCapacity', None)
        discharge_rate = getattr(b, 'DischargeRate', None)
        charge_rate = getattr(b, 'ChargeRate', None)

        new_data.append({
            "Timestamp": timestamp,
            "TestTime  /  s": test_time,
            "Voltage  /  V": voltage / 1000 if voltage else None,
            "Remaining Capacity  /  Wh": remaining_capacity / 1000 if remaining_capacity else None,
            "Discharge Rate  /  W": discharge_rate / 100000000 if discharge_rate else None,
            "Charge Rate  /  W": charge_rate / 100000000 if charge_rate else None,
        })
    return pd.DataFrame(new_data)

# Collect new live data and append to session state
new_data = collect_battery_data()
if not new_data.empty:
    st.session_state.battery_data = pd.concat([st.session_state.battery_data, new_data], ignore_index=True)

# Function to parse the battery report HTML file for historical data
def parse_battery_report(path):
    with open(path, 'r', encoding='utf-8') as file:
        soup = BeautifulSoup(file, 'html.parser')
    
    battery_info = {}
    tables = soup.find_all("table")
    
    for table in tables:
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            label_cell = row.find("span", class_="label")
            value_cell = cells[1] if len(cells) > 1 else None
            
            if label_cell and value_cell:
                key = label_cell.get_text(strip=True).lower()
                value = value_cell.get_text(strip=True).replace(' mWh', '').replace(',', '')

                if "design capacity" in key:
                    battery_info["Design Capacity  /  Wh"] = str(int(value) / 1000) + " Wh"
                elif "full charge capacity" in key:
                    battery_info["Full Charge Capacity  /  Wh"] = str(int(value) / 1000) + " Wh"
                elif "cycle count" in key:
                    battery_info["Cycle Count"] = int(value)
                elif "chemistry" in key:
                    battery_info["Chemistry"] = value
    
    capacity_data = []
    if len(tables) > 5:
        rows = tables[5].find_all("tr")[1:]
        for row in rows:
            cells = row.find_all("td")
            if len(cells) == 3:
                period = cells[0].get_text(strip=True)
                full_charge = int(cells[1].get_text(strip=True).replace(' mWh', '').replace(',', '')) / 1000
                design_capacity = int(cells[2].get_text(strip=True).replace(' mWh', '').replace(',', '')) / 1000
                capacity_data.append({
                    "Period": period,
                    "Full Charge Capacity  /  Wh": full_charge,
                    "Design Capacity  /  Wh": design_capacity
                })

    capacity_df = pd.DataFrame(capacity_data) if capacity_data else None
    return battery_info, capacity_df

# Load and parse the report data
battery_info, capacity_df = parse_battery_report(report_path)

st.title("Battery Report Dashboard")

# Display main metadata as weather-style indicators inside an expander
with st.expander("Battery Metadata", expanded=True):
    metadata_cols = st.columns(4)
    metadata_cols[0].metric("Design Capacity", battery_info.get("Design Capacity  /  Wh", "Not available"))
    metadata_cols[1].metric("Full Charge Capacity", battery_info.get("Full Charge Capacity  /  Wh", "Not available"))
    metadata_cols[2].metric("Cycle Count", battery_info.get("Cycle Count", "Not available"))
    metadata_cols[3].metric("Chemistry", battery_info.get("Chemistry", "Not available"))

# Display current battery status in an expander
with st.expander("Current Battery Status", expanded=True):
    status_cols = st.columns(4)
    latest_data = st.session_state.battery_data.iloc[-1] if not st.session_state.battery_data.empty else None
    if latest_data is not None:
        status_cols[0].metric("Voltage", f"{latest_data['Voltage  /  V']:.2f} V" if latest_data['Voltage  /  V'] else "N/A")
        status_cols[1].metric("Remaining Capacity", f"{latest_data['Remaining Capacity  /  Wh']:.2f} Wh" if latest_data['Remaining Capacity  /  Wh'] else "N/A")
        status_cols[2].metric("Discharge Rate", f"{latest_data['Discharge Rate  /  W']:.2f} W" if latest_data['Discharge Rate  /  W'] else "N/A")
        status_cols[3].metric("Charge Rate", f"{latest_data['Charge Rate  /  W']:.2f} W" if latest_data['Charge Rate  /  W'] else "N/A")
    else:
        for col in status_cols:
            col.metric("N/A", "No data")

# Live Data Plots with Tabs
st.subheader("Battery Data Over Time")
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Voltage", "Remaining Capacity", "Discharge Rate", "Charge Rate", "Capacity History"
])

# Voltage plot
with tab1:
    fig_voltage = px.line(st.session_state.battery_data, x="TestTime  /  s", y="Voltage  /  V", title="Battery Voltage Over Time")
    fig_voltage.update_layout(xaxis_title="Time  /  s", yaxis_title="Voltage  /  V", showlegend=False)
    st.plotly_chart(fig_voltage)

# Remaining capacity plot
with tab2:
    fig_capacity = px.line(st.session_state.battery_data, x="TestTime  /  s", y="Remaining Capacity  /  Wh", title="Remaining Capacity Over Time")
    fig_capacity.update_layout(xaxis_title="Time  /  s", yaxis_title="Capacity  /  Wh", showlegend=False)
    st.plotly_chart(fig_capacity)

# Discharge rate plot
with tab3:
    fig_discharge = px.line(st.session_state.battery_data, x="TestTime  /  s", y="Discharge Rate  /  W", title="Discharge Rate Over Time")
    fig_discharge.update_layout(xaxis_title="Time  /  s", yaxis_title="Discharge Rate  /  W", showlegend=False)
    st.plotly_chart(fig_discharge)

# Charge rate plot
with tab4:
    fig_charge = px.line(st.session_state.battery_data, x="TestTime  /  s", y="Charge Rate  /  W", title="Charge Rate Over Time")
    fig_charge.update_layout(xaxis_title="Time  /  s", yaxis_title="Charge Rate  /  W", showlegend=False)
    st.plotly_chart(fig_charge)

# Capacity history plot
if capacity_df is not None:
    with tab5:
        fig_capacity_history = px.scatter(
            capacity_df, x="Period", y="Full Charge Capacity  /  Wh", title="Battery Full Charge Capacity Over Time (Report)"
        )
        fig_capacity_history.update_traces(marker=dict(size=8, symbol='circle'))
        fig_capacity_history.update_layout(
            xaxis_title="Period",
            yaxis_title="Full Charge Capacity  /  Wh",
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="rgba(211,211,211,0.3)", gridwidth=0.5),
            title=dict(font=dict(size=18))
        )
        st.plotly_chart(fig_capacity_history)
else:
    with tab5:
        st.warning("No capacity history data found in the battery report.")

# Export to Parquet
def export_to_parquet(df):
    buffer = pa.BufferOutputStream()
    table = pa.Table.from_pandas(df)
    pq.write_table(table, buffer)
    return buffer.getvalue().to_pybytes()

parquet_data = export_to_parquet(st.session_state.battery_data)
st.download_button(
    label="Download Time Series Data as Parquet",
    data=parquet_data,
    file_name="battery_data.parquet",
    mime="application/octet-stream"
)

def generate_jsonld_metadata(zenodo_link):
    metadata = {
        "@context": [
            "http://www.w3.org/ns/csvw",
            {
                "dcat": "http://www.w3.org/ns/dcat#",
                "dcterms": "http://purl.org/dc/terms/",
                "foaf": "http://xmlns.com/foaf/0.1/",
                "schema": "http://schema.org/",
                "xsd": "http://www.w3.org/2001/XMLSchema#"
            }
        ],
        "@type": "dcat:Dataset",
        "dcterms:title": "Battery Data from HP ZBook Fury 15 G7 Mobile Workstation",
        "dcterms:description": "Battery data logged from an HP ZBook Fury 15 G7 Mobile Workstation during ElectRObatt 2024, capturing voltage, remaining capacity, discharge rate, and charge rate over time.",
        "dcterms:issued": datetime.now().strftime("%Y-%m-%d"),
        "dcterms:modified": datetime.now().strftime("%Y-%m-%d"),
        "dcterms:publisher": {
            "@type": "foaf:Organization",
            "foaf:name": "SINTEF"
        },
        "dcterms:creator": {
            "@type": "foaf:Person",
            "foaf:name": "Simon Clark",
            "foaf:orcid": "0000-0002-8758-6109"
        },
        "dcat:keyword": [
            "battery data",
            "HP ZBook Fury 15 G7",
            "voltage",
            "capacity",
            "discharge rate",
            "charge rate"
        ],
        "dcterms:language": {
            "@type": "dcterms:ISO639-2",
            "@value": "eng"
        },
        "dcat:distribution": {
            "@type": "dcat:Distribution",
            "dcat:accessURL": zenodo_link,
            "dcterms:format": {
                "rdf:value": "Parquet",
                "dcterms:mediaType": "application/octet-stream"
            },
            "dcat:downloadURL": f"{zenodo_link}/files/battery_data.parquet"
        },
        "tableSchema": {
            "columns": [
                {"name": "Timestamp", "titles": "Timestamp", "dc:description": "Date and time of data logging event", "datatype": "dateTime", "format": "yyyy-MM-ddTHH:mm:ss"},
                {"name": "TestTime  /  s", "titles": "Test Time", "dc:description": "Elapsed time in seconds since data logging started", "datatype": "integer", "unit": "seconds"},
                {"name": "Voltage  /  V", "titles": "Voltage", "dc:description": "Battery voltage at time of logging", "datatype": "number", "unit": "V"},
                {"name": "Remaining Capacity  /  Wh", "titles": "Remaining Capacity", "dc:description": "Battery remaining capacity in watt-hours", "datatype": "number", "unit": "Wh"},
                {"name": "Discharge Rate  /  W", "titles": "Discharge Rate", "dc:description": "Battery discharge rate in watts", "datatype": "number", "unit": "W"},
                {"name": "Charge Rate  /  W", "titles": "Charge Rate", "dc:description": "Battery charge rate in watts", "datatype": "number", "unit": "W"}
            ],
            "primaryKey": "Timestamp"
        }
    }
    return json.dumps(metadata, indent=2)

def save_metadata_as_jsonld(zenodo_link):
    jsonld_content = generate_jsonld_metadata(zenodo_link)
    jsonld_file = BytesIO()
    jsonld_file.write(jsonld_content.encode('utf-8'))
    jsonld_file.seek(0)
    return jsonld_file

# Zenodo Publish Functionality
def publish_to_zenodo(api_token, title="Battery Data from HP ZBook Fury 15 G7 Mobile Workstatio", description="Battery data logged from an HP ZBook Fury 15 G7 Mobile Workstation during Electrobatt 2024 conference", creators=[{"name": "Simon Clark", "orcid": "0000-0002-8758-6109"}], sandbox=True, publish_draft=True):
    base_url = "https://sandbox.zenodo.org/api/deposit/depositions" if sandbox else "https://zenodo.org/api/deposit/depositions"
    headers = {"Authorization": f"Bearer {api_token}"}
    metadata = {
        "metadata": {
            "title": title,
            "upload_type": "dataset",
            "description": description,
            "creators": creators,
            "keywords": ["battery", "HP ZBook Fury 15 G7"],
            "notes": "Battery logging data from an HP ZBook Fury 15 G7 Mobile Workstation, capturing voltage, remaining capacity, discharge rate, and charge rate over time.",
            "access_right": "open",
            "license": "CC-BY-4.0"
        }
    }
    
    response = requests.post(base_url, json=metadata, headers=headers)
    if response.status_code == 201:
        deposition_id = response.json()["id"]
        files_url = f"{base_url}/{deposition_id}/files"
        
        # Upload Parquet and JSON-LD metadata files
        files = [
            ('file', ('battery_data.parquet', parquet_data, 'application/octet-stream')),
            ('file', ('metadata.jsonld', save_metadata_as_jsonld(response.json()["links"]["html"]).getvalue(), 'application/ld+json'))
        ]
        
        for file in files:
            upload_response = requests.post(files_url, files=[file], headers=headers)
            if upload_response.status_code != 201:
                st.error("Failed to upload file to Zenodo.")
                st.write("Upload response:", upload_response.json())
                return None

        if not publish_draft:
            publish_url = f"{base_url}/{deposition_id}/actions/publish"
            publish_response = requests.post(publish_url, headers=headers)
            if publish_response.status_code == 202:
                st.balloons()
                return publish_response.json()["links"]["html"]
            else:
                st.error("Failed to publish the record on Zenodo.")
        else:
            st.success("Draft record created on Zenodo (not published).")
        return response.json()["links"]["html"]
    else:
        st.error("Failed to create Zenodo record.")
        st.write("Creation response:", response.json())
        return None

# Checkbox to toggle between creating a draft or publishing the record
sandbox = st.checkbox("Use Zenodo Sandbox (for testing)")
publish_draft = st.checkbox("Publish as Draft (for review)")

api_token = st.text_input("Enter Zenodo API Token:", type="password")
if st.button("Publish to Zenodo"):
    if api_token:
        zenodo_link = publish_to_zenodo(api_token, sandbox=sandbox, publish_draft=publish_draft)
        if zenodo_link:
            st.success(f"Data published to Zenodo: [View Record]({zenodo_link})")
            qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L)
            qr.add_data(zenodo_link)
            qr.make(fit=True)
            img_qr = qr.make_image(fill_color="black", back_color="white")
            img_qr_inv = ImageOps.invert(img_qr.convert("RGB"))
            qr_image = BytesIO()
            img_qr_inv.save(qr_image, format="PNG")
            st.session_state.qr_code = qr_image.getvalue()
    else:
        st.warning("Please enter a valid Zenodo API Token.")

# Display QR code for Zenodo record
if "qr_code" in st.session_state:
    qr_img = Image.open(BytesIO(st.session_state.qr_code))
    st.image(qr_img, caption="Scan to view Zenodo record", use_column_width=True)
