import datetime
import logging
import os
import threading
import time
from collections import defaultdict

import gspread

import sheets_sync
import wb_api

log = logging.getLogger(__name__)

_sync_lock = threading.Lock()

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

    time.sleep(2)  # be gentle with WB's per-endpoint rate limit
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


def preview_week() -> str:
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    date_from = monday.isoformat()

    daily = _aggregate_orders_and_sales(date_from)
    time.sleep(2)
    finance = _aggregate_finance(date_from, today.isoformat())

    lines = [
        "Черновик по Сводному отчёту за эту неделю (никуда не записано, только для сверки):",
        "",
    ]
    d = monday
    while d <= today:
        key = d.isoformat()
        o = daily.get(key, {"order_sum": 0, "order_qty": 0, "sale_sum": 0, "sale_qty": 0, "for_pay": 0})
        f = finance.get(key, {"logistics": 0, "storage": 0})
        buyout_pct = round(o["sale_qty"] / o["order_qty"] * 100) if o["order_qty"] else 0
        lines.append(
            f"{d.strftime('%d.%m')}: заказы {round(o['order_sum'])}₽ ({o['order_qty']} шт) · "
            f"продажи {round(o['sale_sum'])}₽ · выкуп {buyout_pct}% · "
            f"к перечислению {round(o['for_pay'])}₽ · логистика {round(f['logistics'])}₽ · "
            f"хранение {round(f['storage'])}₽"
        )
        d += datetime.timedelta(days=1)

    lines.append("")
    lines.append(
        "Сверь с реальным отчётом в кабинете WB (Аналитика → Отчёты → Сводный по продавцу) — совпадает?"
    )
    return "\n".join(lines)


def apply_report_file(by_date: dict) -> str:
    if not by_date:
        return "В файле не нашлось данных по дням — ничего не записал."

    spreadsheet = sheets_sync.get_spreadsheet()

    by_month = defaultdict(dict)
    for key, v in by_date.items():
        d = datetime.date.fromisoformat(key)
        by_month[(d.year, d.month)][key] = v

    results = []
    for (year, month), month_data in sorted(by_month.items()):
        tab_title = f"месяц-{MONTH_NAMES_RU[month]}"
        try:
            ws = spreadsheet.worksheet(tab_title)
        except gspread.WorksheetNotFound:
            results.append(f"«{tab_title}»: такой вкладки нет, пропустил")
            continue

        updates = []
        filled = 0
        for row_idx, cell in enumerate(ws.col_values(1), start=1):
            if row_idx == 1 or not cell:
                continue
            try:
                row_date = datetime.datetime.strptime(cell.split(" ")[0], "%d.%m.%Y").date()
            except ValueError:
                continue
            v = month_data.get(row_date.isoformat())
            if v is None:
                continue
            updates.append({
                "range": f"B{row_idx}:F{row_idx}",
                "values": [[
                    round(v.get("order_sum", 0)), round(v.get("sale_sum", 0)),
                    round(v.get("buyout_pct", 0)), v.get("order_qty", 0), round(v.get("for_pay", 0)),
                ]],
            })
            updates.append({
                "range": f"H{row_idx}:I{row_idx}",
                "values": [[round(v.get("logistics", 0)), round(v.get("storage", 0))]],
            })
            filled += 1

        if updates:
            ws.batch_update(updates, value_input_option="USER_ENTERED")
        results.append(f"«{tab_title}»: обновлено дней — {filled}")

    return "\n".join(results)


def sync_svodny() -> str:
    if not _sync_lock.acquire(blocking=False):
        return "Синхронизация уже выполняется — подожди, пока закончится текущая."
    try:
        return _sync_svodny()
    finally:
        _sync_lock.release()


def _sync_svodny() -> str:
    today = datetime.date.today()
    date_from = (today - datetime.timedelta(days=SYNC_DAYS_BACK)).isoformat()

    spreadsheet = sheets_sync.get_spreadsheet()
    tab_title = f"месяц-{MONTH_NAMES_RU[today.month]}"
    try:
        ws = spreadsheet.worksheet(tab_title)
    except gspread.WorksheetNotFound:
        return f"Не нашёл вкладку «{tab_title}» в таблице — ничего не менял."

    daily = _aggregate_orders_and_sales(date_from)
    time.sleep(2)
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
