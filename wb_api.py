import os
import requests

WB_STATS_BASE = "https://statistics-api.wildberries.ru/api"
TIMEOUT = 60


def _headers() -> dict:
    return {"Authorization": os.environ["WB_API_TOKEN"]}


def get_sales(date_from: str, date_to: str | None = None) -> list[dict]:
    r = requests.get(
        f"{WB_STATS_BASE}/v1/supplier/sales",
        headers=_headers(),
        params={"dateFrom": date_from},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json() or []


def get_orders(date_from: str, date_to: str | None = None) -> list[dict]:
    r = requests.get(
        f"{WB_STATS_BASE}/v1/supplier/orders",
        headers=_headers(),
        params={"dateFrom": date_from},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json() or []


def get_stocks(date_from: str, date_to: str | None = None) -> list[dict]:
    r = requests.get(
        f"{WB_STATS_BASE}/v1/supplier/stocks",
        headers=_headers(),
        params={"dateFrom": date_from},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json() or []


def get_finance_report(date_from: str, date_to: str) -> list[dict]:
    rows: list[dict] = []
    rrdid = 0
    while True:
        r = requests.get(
            f"{WB_STATS_BASE}/v5/supplier/reportDetailByPeriod",
            headers=_headers(),
            params={"dateFrom": date_from, "dateTo": date_to, "rrdid": rrdid, "limit": 100000},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        batch = r.json() or []
        rows.extend(batch)
        if len(batch) < 100000:
            break
        rrdid = batch[-1]["rrd_id"]
    return rows
