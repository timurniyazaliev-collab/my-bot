COLUMNS = ["Дата", "Заказы", "Продажи", "Вык%", "Шт", "К.пер", "Лог", "Хран"]
WIDTHS = [6, 8, 9, 6, 4, 8, 6, 6]


def render_table(rows: list[tuple]) -> str:
    header = "".join(name.ljust(w) if i == 0 else name.rjust(w) for i, (name, w) in enumerate(zip(COLUMNS, WIDTHS)))
    lines = [header, "-" * len(header)]
    for date_str, order_sum, sale_sum, buyout_pct, qty, for_pay, logistics, storage in rows:
        values = [date_str, round(order_sum), round(sale_sum), round(buyout_pct), qty, round(for_pay), round(logistics), round(storage)]
        lines.append("".join(
            str(v).ljust(w) if i == 0 else str(v).rjust(w) for i, (v, w) in enumerate(zip(values, WIDTHS))
        ))
    return "\n".join(lines)
