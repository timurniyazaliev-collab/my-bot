import logging
import os
import time

import requests

log = logging.getLogger(__name__)

WB_STATS_BASE = "https://statistics-api.wildberries.ru/api"
TIMEOUT = 60
MAX_RETRIES = 3
DEFAULT_RETRY_WAIT = 65  # WB's statistics endpoints allow ~1 request/minute


def _headers() -> dict:
    return {"Authorization": os.environ["WB_API_TOKEN"]}


def _get(url: str, params: dict) -> list[dict]:
    for attempt in range(MAX_RETRIES):
        r = requests.get(url, headers=_headers(), params=params, timeout=TIMEOUT)
        if r.status_code == 429 and attempt < MAX_RETRIES - 1:
            wait = int(r.headers.get("Retry-After", DEFAULT_RETRY_WAIT))
            log.info(f"WB rate limit hit for {url}, waiting {wait}s (attempt {attempt + 1})")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json() or []
    return []


def get_sales(date_from: str, date_to: str | None = None) -> list[dict]:
    return _get(f"{WB_STATS_BASE}/v1/supplier/sales", {"dateFrom": date_from})


def get_orders(date_from: str, date_to: str | None = None) -> list[dict]:
    return _get(f"{WB_STATS_BASE}/v1/supplier/orders", {"dateFrom": date_from})


def get_stocks(date_from: str, date_to: str | None = None) -> list[dict]:
    return _get(f"{WB_STATS_BASE}/v1/supplier/stocks", {"dateFrom": date_from})


def get_finance_report(date_from: str, date_to: str) -> list[dict]:
    rows: list[dict] = []
    rrdid = 0
    while True:
        batch = _get(
            f"{WB_STATS_BASE}/v5/supplier/reportDetailByPeriod",
            {"dateFrom": date_from, "dateTo": date_to, "rrdid": rrdid, "limit": 100000},
        )
        rows.extend(batch)
        if len(batch) < 100000:
            break
        rrdid = batch[-1]["rrd_id"]
    return rows
