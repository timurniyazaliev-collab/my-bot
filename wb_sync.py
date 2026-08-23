import datetime
import logging
import os

import sheets_sync
import wb_api

log = logging.getLogger(__name__)

SYNC_DAYS = int(os.environ.get("WB_SYNC_DAYS", "30"))

REPORT_CONFIGS = {
    "Продажи": dict(fetch=lambda f, t: wb_api.get_sales(f, t), id_fn=lambda r: str(r.get("srid")), mode="append"),
    "Заказы": dict(fetch=lambda f, t: wb_api.get_orders(f, t), id_fn=lambda r: str(r.get("srid")), mode="append"),
    "Остатки": dict(fetch=lambda f, t: wb_api.get_stocks(f, t), id_fn=None, mode="overwrite"),
    "Финансы": dict(
        fetch=lambda f, t: wb_api.get_finance_report(f, t),
        id_fn=lambda r: f'{r.get("realizationreport_id")}_{r.get("rrd_id")}',
        mode="append",
    ),
}


def sync_all() -> str:
    today = datetime.date.today()
    date_from = (today - datetime.timedelta(days=SYNC_DAYS)).isoformat()
    date_to = today.isoformat()

    spreadsheet = sheets_sync.get_spreadsheet()
    lines = []
    for title, cfg in REPORT_CONFIGS.items():
        try:
            records = cfg["fetch"](date_from, date_to) or []
            if not records:
                lines.append(f"{title}: данных нет")
                continue
            field_names = list(records[0].keys())

            if cfg["mode"] == "overwrite":
                rows = [[str(r.get(h, "")) for h in field_names] for r in records]
                ws, headers = sheets_sync.get_or_create_worksheet(spreadsheet, title, field_names)
                sheets_sync.overwrite_all(ws, headers, rows)
                lines.append(f"{title}: обновлено {len(rows)} строк")
            else:
                headers_wanted = ["_id"] + field_names
                ws, headers = sheets_sync.get_or_create_worksheet(spreadsheet, title, headers_wanted)
                data_headers = headers[1:]
                seen = sheets_sync.existing_ids(ws)
                new_rows = []
                for r in records:
                    rid = cfg["id_fn"](r)
                    if rid in seen:
                        continue
                    seen.add(rid)
                    new_rows.append([rid] + [str(r.get(h, "")) for h in data_headers])
                sheets_sync.append_rows(ws, new_rows)
                lines.append(f"{title}: добавлено {len(new_rows)} новых строк")
        except Exception as e:
            log.exception(f"wb sync error: {title}")
            lines.append(f"{title}: ошибка — {e}")
    return "\n".join(lines)
