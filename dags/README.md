# IoT Wind Farm — from edge to insights
Telemetry → Kafka → Redis dedup → bronze NDJSON → Airflow + DuckDB → gold KPIs (Parquet/CSV).

## Quick start
```bash
docker compose up -d --build
# Mock producer health\ ncurl http://localhost:8000/health
# Open Airflow: http://localhost:8080