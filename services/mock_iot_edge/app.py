from fastapi import FastAPI
import asyncio, os, json, random, time, uuid
from confluent_kafka import Producer

BROKER=os.getenv("KAFKA_BROKER", "kafka:9092")
TOPIC=os.getenv("KAFKA_TOPIC", "iot.telemetry") 
N      = int(os.getenv("DEVICE_COUNT", "30"))
INTERVAL_MS = int(os.getenv("SEND_INTERVAL_MS", "500"))
p = Producer({"bootstrap.servers": BROKER})
app = FastAPI()

sites = ["aegean-north", "aegean-south", "anatolia"]
devices = [f"device-{i+1:03d}" for i in range(N+1)]
random.seed(42)

def make_event(device_id: str):
    wind = max(0.0, random.gauss(8.0, 2.0))
    rpm  = max(0.0, wind*150 + random.gauss(0, 40))
    power= max(0.0, wind*55 + random.gauss(0, 8))
    return {
        "device_id": device_id,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "metrics": {
            "wind_ms": round(wind, 2),
            "rpm": round(rpm, 1),
            "power_kw": round(power, 1),
            "temp_c": round(random.gauss(52, 4), 1),
            "vibration_mm_s": round(random.uniform(0.5, 2.6), 2)
        },
        "firmware": "1.3.2",
        "site": random.choice(sites),
        "msg_id": str(uuid.uuid4())
    }
async def loop_send():
    while True:
        for d in devices:
            evt = make_event(d)
            p.produce(TOPIC, json.dumps(evt).encode("utf-8"))
        p.poll(0)
        await asyncio.sleep(INTERVAL_MS/1000)
@app.on_event("startup")
async def _start():
    asyncio.create_task(loop_send())
@app.get("/health")
def health():
    return {"ok": True, "devices": len(devices)}