
from datetime import datetime
from airflow.decorators import dag, task
import os, glob, duckdb, pandas as pd

@dag(dag_id="iot_daily_etl", start_date=datetime(2024,1,1), schedule="@daily", catchup=False,
     tags=["iot","kafka","redis","duckdb"])
def iot_daily_etl():

    @task
    def build_daily(ds=None, **_):
        # Collect NDJSON files for this ds (UTC day)
        day = ds.replace('-', '')
        pattern = f"/opt/airflow/data/bronze/iot_{day}_*.ndjson"
        files = sorted(glob.glob(pattern))
        if not files:
            print("No bronze files for", ds)
            return ""
        # Read all lines into a pandas DataFrame
        rows = []
        for fp in files:
            with open(fp, 'r', encoding='utf-8') as f:
                for line in f:
                    rows.append(pd.json.loads(line)) if hasattr(pd, 'json') else rows.append(__import__('json').loads(line))
        
        df = pd.DataFrame(rows)
        # normalize nested metrics
        m = pd.json_normalize(df['metrics'])
        df = pd.concat([df.drop(columns=['metrics']), m], axis=1)

        os.makedirs('/opt/airflow/data/silver', exist_ok=True)
        silver_path = f"/opt/airflow/data/silver/iot_{ds}.parquet"
        df.to_parquet(silver_path, index=False)

        con = duckdb.connect()
        con.execute("CREATE TABLE f AS SELECT * FROM read_parquet(?)", [silver_path])
        # minute medians per device
        con.execute(
            """
            CREATE TABLE minute AS
            SELECT device_id,
                   site,
                   date_trunc('minute', CAST(ts AS TIMESTAMP)) AS t_min,
                   median(wind_ms) AS wind_ms,
                   median(rpm) AS rpm,
                   median(power_kw) AS power_kw,
                   median(temp_c) AS temp_c,
                   median(vibration_mm_s) AS vibration_mm_s
            FROM f
            GROUP BY device_id, site, t_min
            """
        )
        con.execute(
            """
            CREATE TABLE daily AS
            SELECT site,
                   CAST(date_trunc('day', t_min) AS DATE) AS day,
                   COUNT(*) AS samples,
                   COUNT(DISTINCT device_id) AS devices,
                   AVG(wind_ms) AS avg_wind,
                   SUM(power_kw)/60.0 AS kwh_total,
                   (SUM(power_kw)/60.0) / NULLIF(COUNT(DISTINCT device_id),0) AS kwh_per_device,
                   SUM(CASE WHEN vibration_mm_s>2.0 OR temp_c>70 THEN 1 ELSE 0 END) AS anomaly_cnt
            FROM minute
            GROUP BY site, day
            ORDER BY day
            """
        )
        os.makedirs('/opt/airflow/data/gold', exist_ok=True)
        gold_parquet = f"/opt/airflow/data/gold/daily_{ds}.parquet"
        gold_csv     = f"/opt/airflow/data/gold/daily_{ds}.csv"
        con.execute("COPY daily TO ? (FORMAT PARQUET)", [gold_parquet])
        con.execute("COPY daily TO ? (HEADER, DELIMITER ',')", [gold_csv])
        return gold_csv

    build_daily()

iot_daily_etl()