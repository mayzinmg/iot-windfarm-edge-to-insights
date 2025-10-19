import importlib

def test_import():
    mod = importlib.import_module("dags.iot_daily_etl")
    assert hasattr(mod, "iot_daily_etl")