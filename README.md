![ci](https://github.com/mayzinmg/iot-windfarm-edge-to-insights/actions/workflows/ci.yml/badge.svg)

# IoT Wind Farm — from Edge to Insights

**Stack:** Kafka · Redis · Airflow · DuckDB · Python · Docker — *no external DB required*

Mock IoT devices emit telemetry → **Kafka**. A lightweight consumer deduplicates with **Redis** and writes time‑bucketed **NDJSON** to `data/bronze/`. **Airflow** runs a daily job that uses **DuckDB** to build **silver** (flattened Parquet) and **gold** KPIs (Parquet/CSV).

> Windows‑friendly. One command to run. No cloud creds.

---

## Contents

* [Architecture](#architecture)
* [Quick Start](#quick-start)
* [Prerequisites](#prerequisites)
* [Project Structure](#project-structure)
* [How It Works](#how-it-works)
* [Inspect Results](#inspect-results)
* [Configuration](#configuration)
* [Troubleshooting](#troubleshooting)
* [Development (local lint/tests)](#development-local-linttests)
* [Roadmap](#roadmap)
* [License](#license)

---

## Architecture

```
Mock IoT → Kafka → Redis (dedup) → Bronze NDJSON
                               │
                               └→ Airflow (daily) → DuckDB (silver/gold) → Parquet/CSV KPIs
```

**Key guarantees**

* Idempotent ingest via Redis `SETNX iot:seen:{msg_id}` + TTL (2 days)
* Time‑bucketed files (5‑minute rotation) to avoid concurrent write contention
* Daily aggregates per site: `kwh_total`, `kwh_per_device`, `avg_wind`, and a simple anomaly count (`vibration_mm_s > 2.0` OR `temp_c > 70`)

---

## Quick Start

```bash
# from repo root
docker compose up -d --build

# health of mock producer (expect {"ok": true, "devices": 30})
curl http://localhost:8000/health

# open Airflow UI
# http://localhost:8080 → trigger DAG "iot_daily_etl"
```

Outputs after the first successful run:

* `data/silver/iot_<YYYY-MM-DD>.parquet`
* `data/gold/daily_<YYYY-MM-DD>.parquet`
* `data/gold/daily_<YYYY-MM-DD>.csv`

> Tip: the consumer rotates files every ~5 minutes; give it a minute to generate `data/bronze/*.ndjson` before triggering.

---

## Prerequisites

* Docker Desktop (or Docker Engine) running
* Ports available: `8080` (Airflow), `8000` (mock IoT)
* (Optional) Python 3.11 if you want to run local scripts/tests outside containers

---

## Project Structure

```
iot-windfarm-edge-to-insights/
├─ dags/
│  └─ iot_daily_etl.py            # Airflow DAG: bronze → silver → gold
├─ services/
│  ├─ mock_iot_edge/              # FastAPI app producing IoT events to Kafka
│  │  ├─ app.py
│  │  └─ requirements.txt
│  └─ stream_consumer/            # Kafka consumer → Redis dedup → NDJSON files
│     ├─ main.py
│     └─ requirements.txt
├─ data/                          # mounted volume (bronze/silver/gold live here)
├─ tests/
│  └─ test_dag_import.py          # smoke test for CI
├─ .github/workflows/ci.yml       # GitHub Actions (pytest)
├─ docker-compose.yaml            # stack: zookeeper, kafka, redis, airflow, services
├─ requirements.txt               # Airflow/DAG deps
├─ LICENSE                        # MIT
└─ README.md
```

---

## How It Works

1. **Mock IoT Producer** (`services/mock_iot_edge/`)

   * Emits JSON messages like:

   ```json
   {
     "device_id":"turbine-042","ts":"2025-10-16T02:05:31Z",
     "metrics":{"rpm":1327.4,"wind_ms":8.9,"power_kw":486.2,"temp_c":54.1,"vibration_mm_s":1.3},
     "firmware":"1.3.2","site":"aegean-north","msg_id":"<uuid>"
   }
   ```

   * Env vars control device count and send interval.

2. **Stream Consumer** (`services/stream_consumer/`)

   * Deduplicates with Redis: `SETNX iot:seen:{msg_id}` → skip if seen; sets TTL 2 days
   * Rotates **NDJSON** files by 5‑minute buckets: `data/bronze/iot_YYYYMMDD_HHMM.ndjson`

3. **Airflow DAG** (`dags/iot_daily_etl.py`)

   * Reads today’s NDJSON into **silver** Parquet (flattened metrics)
   * Computes **gold** per‑site/per‑day KPIs with **DuckDB**
   * Writes gold as Parquet + CSV

---

## Inspect Results

**List latest gold file and view it:**

```bash
python - <<'PY'
import glob, duckdb
p = sorted(glob.glob('data/gold/daily_*.parquet'))[-1]
print(duckdb.sql(f"SELECT * FROM read_parquet('{p}')").df())
PY
```

**Bronze peek:**

```bash
ls -l data/bronze | tail -n 5
head -n 3 data/bronze/iot_*.ndjson
```

---

## Configuration

Set via `docker-compose.yaml` service env vars:

* **Producer**

  * `DEVICE_COUNT` (default `30`)
  * `SEND_INTERVAL_MS` (default `500`)
* **Consumer**

  * `ROTATE_MINUTES` (default `5`)
  * `OUT_DIR` (default `/data/bronze`)

Change the **host** port mapping if 8080/8000 are in use, e.g. `8081:8080`.

---

## Troubleshooting

* **Airflow shows no DAGs** → confirm mount `./dags:/opt/airflow/dags`; check logs:

  ```bash
  docker compose logs -f airflow
  ```
* **No bronze files yet** → wait 1–2 minutes; follow logs:

  ```bash
  docker compose logs -f stream_consumer mock_iot_edge
  ```
* **Port already in use** → change left side of the port mapping in `docker-compose.yaml` and `docker compose up -d --build` again.
* **Kafka connect issues** → restart dependent services:

  ```bash
  docker compose restart kafka mock_iot_edge stream_consumer
  ```

---

## Development (local lint/tests)

You can run tests without containers:

```bash
python -m pip install -r requirements.txt pytest
pytest -q
```

*(Ruff/linting optional; not required to run the project.)*

**CI (GitHub Actions):** `.github/workflows/ci.yml` installs deps and runs `pytest`. The badge at the top reflects the current status.

---

## Roadmap

* **Path A — Data Quality:** Great Expectations on silver (non‑null `device_id`, `power_kw ≥ 0`, `temp_c ≤ 90`)
* **Path B — Alerting:** Slack webhook alert when `anomaly_cnt` exceeds threshold
* **Path C — Visibility:** Tiny FastAPI dashboard plotting `kwh_total` and `anomaly_cnt`

---

## License

MIT © M
