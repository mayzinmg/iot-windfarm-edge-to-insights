
import os, json, time, redis, pathlib
from datetime import datetime
from confluent_kafka import Consumer

BROKER = os.getenv("KAFKA_BROKER", "kafka:9092")
TOPIC  = os.getenv("TOPIC", "iot.telemetry")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
OUT_DIR = os.getenv("OUT_DIR", "/data/bronze")
ROTATE_MIN = int(os.getenv("ROTATE_MINUTES", "5"))

r = redis.from_url(REDIS_URL)
c = Consumer({
    "bootstrap.servers": BROKER,
    "group.id": "iot-consumer-1",
    "auto.offset.reset": "earliest"
})
c.subscribe([TOPIC])

pathlib.Path(OUT_DIR).mkdir(parents=True, exist_ok=True)
current_path = None
current_open = None
current_bucket_min = None

def rotate_if_needed(ts_iso: str):
    global current_path, current_open, current_bucket_min
    ts = datetime.strptime(ts_iso, "%Y-%m-%dT%H:%M:%SZ")
    bucket = ts.replace(second=0, microsecond=0)
    minute = bucket.minute - (bucket.minute % ROTATE_MIN)
    bucket = bucket.replace(minute=minute)
    if bucket != current_bucket_min:
        if current_open:
            current_open.flush(); current_open.close()
        fname = f"iot_{bucket.strftime('%Y%m%d_%H%M')}.ndjson"
        current_path = os.path.join(OUT_DIR, fname)
        current_open = open(current_path, "a", encoding="utf-8")
        current_bucket_min = bucket

# --- counters / rate reporting ---
processed = 0
dupes = 0
last_report = time.monotonic()

while True:
    msg = c.poll(1.0)
    if not msg:
        continue
    if msg.error():
        continue
    try:
        data = json.loads(msg.value())
    except Exception:
        continue

    msg_id = data.get("msg_id")
    if not msg_id:
        continue

    # Redis SETNX for idempotency (TTL 2 days)
    key = f"iot:seen:{msg_id}"
    if not r.setnx(key, 1):
        # duplicate -> count and skip
        dupes += 1
        # periodic report
        now = time.monotonic()
        if now - last_report >= 60:
            elapsed = now - last_report
            rate = processed / elapsed if elapsed > 0 else 0.0
            print(f"[consumer] rate={rate:.1f}/s processed={processed} dupes={dupes}", flush=True)
            processed = 0
            dupes = 0
            last_report = now
        continue
    r.expire(key, 172800)

    ts_iso = data.get("ts") or datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    rotate_if_needed(ts_iso)
    current_open.write(json.dumps(data, ensure_ascii=False) + "\n")

    # count processed & emit periodic report
    processed += 1
    now = time.monotonic()
    if now - last_report >= 60:
        elapsed = now - last_report
        rate = processed / elapsed if elapsed > 0 else 0.0
        print(f"[consumer] rate={rate:.1f}/s processed={processed} dupes={dupes}", flush=True)
        processed = 0
        dupes = 0
        last_report = now
