from pathlib import Path
import sys

import pandas as pd

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.config import load_config
from src.database import create_sql_engine


script_dir = Path(__file__).resolve().parent
config = load_config(project_root, require_admin=True)

data_path = project_root / "data" / "raw" / "dynamic_supply_chain_logistics_dataset.csv"

print(f"Loading CSV from {data_path}...")
df = pd.read_csv(data_path)

legacy_mapping = {
    "timestamp": "TS_UTC",
    "vehicle_gps_latitude": "V_LAT",
    "vehicle_gps_longitude": "V_LON",
    "iot_temperature": "IOT_TEMP_VAL_C",
    "cargo_condition_status": "CGO_COND_CD",
    "risk_classification": "RISK_CLS_TXT",
    "delay_probability": "DELAY_PROB_DEC",
    "port_congestion_level": "PRT_CNG_LVL",
    "route_risk_level": "RT_RSK_IDX",
}

df_legacy = df[list(legacy_mapping)].rename(columns=legacy_mapping)
df_legacy["SYS_INGEST_FLAG"] = "Y"

print("Connecting to legacy MSSQL Database...")
engine = create_sql_engine(
    config,
    username=config.sql_admin_user,
    password=config.sql_admin_password,
)

table_name = "TBL_SC_FLEET_HIST_RAW"
print(f"Ingesting into {table_name}. This may take a minute...")
df_legacy.to_sql(
    table_name,
    engine,
    if_exists="replace",
    index=False,
    schema="dbo",
)

print("Legacy data ingestion complete.")
