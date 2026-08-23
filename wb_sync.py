import datetime
import logging
import os
from collections import defaultdict

import gspread

import sheets_sync
import wb_api

log = logging.getLogger(__name__)

MONTH_NAMES_RU = {
    1: "январь", 2: "февраль", 3: "март", 4: "апрель",
    5: "май", 6: "июнь", 7: "июль", 8: "август",
    9: "сентябрь", 10: "октябрь", 11: "ноябрь", 12: "декабрь",
}

SYNC_DAYS_BACK = int(os.environ.get("WB_SYNC_DAYS", "31"))


def _day_key(date_str: str) -> str:
    return (date_str or "")[:10]


def _aggregate_orders_and_sales(date_from: str) -> dict:
    per_day = defaultdict(lambda: {
        "order_sum": 0.0, "order_qty": 0,
        "sale_sum": 0.0, "sale_qty": 0,
        "for_pay": 0.0,
    })

    for o in wb_api.get_orders(date_from):
        if o.get("isCancel"):
            continue
        day = per_day[_day_key(o.get("date"))]
        day["order_sum"] += o.get("priceWithDisc") or 0
        day["order_qty"] += 1

    for s in wb_api.get_sales(date_from):
        sale_id = s.get("saleID") or ""
        sign = 1 if sale_id.startswith("S") else -1 if sale_id.startswith("R") else 0
        if sign == 0:
            continue
        day = per_day[_day_key(s.get("date"))]
        day["sale_sum"] += sign * (s.get("priceWithDisc") or 0)
        day["for_pay"] += sign * (s.get("forPay") or 0)
        if sign == 1:
            day["sale_qty"] += 1

    return per_day


def _aggregate_finance(date_from: str, date_to: str) -> dict:
    per_day = defaultdict(lambda: {"logistics": 0.0, "storage": 0.0})
    for r in wb_api.get_finance_report(date_from, date_to):
        day = per_day[_day_key(r.get("rr_dt"))]
        day["logistics"] += r.get("delivery_rub") or 0
        day["storage"] += r.get("storage_fee") or 0
    return per_day


def sync_svodny() -> str:
    today = datetime.date.today()
    date_from = (today - datetime.timedelta(days=SYNC_DAYS_BACK)).isoformat()

    spreadsheet = sheets_sync.get_spreadsheet()
    tab_title = f"месяц-{MONTH_NAMES_RU[today.month]}"
    try:
        ws = spreadsheet.worksheet(tab_title)
    except gspread.WorksheetNotFound:
        return f"Не нашёл вкладку «{tab_title}» в таблице — ничего не менял."

    daily = _aggregate_orders_and_sales(date_from)
    finance = _aggregate_finance(date_from, today.isoformat())

    updates = []
    filled_days = 0
    for row_idx, cell in enumerate(ws.col_values(1), start=1):
        if row_idx == 1 or not cell:
            continue
        try:
            row_date = datetime.datetime.strptime(cell.split(" ")[0], "%d.%m.%Y").date()
        except ValueError:
            continue
        if row_date.month != today.month or row_date.year != today.year or row_date > today:
            continue

        key = row_date.isoformat()
        if key not in daily and key not in finance:
            continue
        d = daily.get(key, {"order_sum": 0, "order_qty": 0, "sale_sum": 0, "sale_qty": 0, "for_pay": 0})
        f = finance.get(key, {"logistics": 0, "storage": 0})
        buyout_pct = round(d["sale_qty"] / d["order_qty"] * 100) if d["order_qty"] else 0

        updates.append({
            "range": f"B{row_idx}:F{row_idx}",
            "values": [[round(d["order_sum"]), round(d["sale_sum"]), buyout_pct, d["order_qty"], round(d["for_pay"])]],
        })
        updates.append({
            "range": f"H{row_idx}:I{row_idx}",
            "values": [[round(f["logistics"]), round(f["storage"])]],
        })
        filled_days += 1

    if updates:
        ws.batch_update(updates, value_input_option="USER_ENTERED")
    return f"«{tab_title}»: обновлено дней — {filled_days} (колонки B–F и H–I; A, G, J и строки плана не трогал)"
