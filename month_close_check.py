#!/usr/bin/env python3
"""
month_close_check.py — oy yopilishini tekshirish.

Har oy uchun Document_РегламентнаяОперация (regламент operatsiyalari — "Закрытие месяца"
protsedurasi natijasida yaratiladigan hujjatlar) mavjudligini tekshiradi. Agar biror
oyda provedeniya qilingan regламент operatsiyasi topilmasa — bu oy yopilmagan
(oyni yopish bajarilmagan) deb belgilanadi.

Natija: output/month_close_check.json
"""
import json
import os
import sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from odata_client import ODataClient, odata_date, month_bounds, iter_months, output_dir

LOOKBACK_MONTHS = 12

SELECT = ["Ref_Key", "Number", "Date", "Posted", "DeletionMark", "ВидОперации", "Состояние"]
DONE_STATE = "Выполнено"  # 1C marks a successfully completed regulated operation this way;
                           # these documents do not use the generic Posted flag.


def run(client: ODataClient, lookback_months=LOOKBACK_MONTHS):
    today = dt.datetime.now()
    start_year, start_month = today.year, today.month - lookback_months
    while start_month <= 0:
        start_month += 12
        start_year -= 1
    start_date = dt.datetime(start_year, start_month, 1)

    rows = client.query(
        "Document_РегламентнаяОперация",
        select=SELECT,
        filter_=f"Date ge {odata_date(start_date)}",
        orderby="Date asc",
    )

    by_month = {}
    for r in rows:
        if not r.get("Date"):
            continue
        d = dt.datetime.fromisoformat(r["Date"])
        key = f"{d.year:04d}-{d.month:02d}"
        by_month.setdefault(key, {"total": 0, "posted": 0, "ops": set()})
        by_month[key]["total"] += 1
        if r.get("Состояние") == DONE_STATE and not r.get("DeletionMark"):
            by_month[key]["posted"] += 1
        if r.get("ВидОперации"):
            by_month[key]["ops"].add(r["ВидОперации"])

    current_month_key = f"{today.year:04d}-{today.month:02d}"
    months_report = []
    missing = []
    for y, m in iter_months(start_date, today.replace(day=1) + dt.timedelta(days=32)):
        key = f"{y:04d}-{m:02d}"
        if key > current_month_key:
            break
        info = by_month.get(key, {"total": 0, "posted": 0, "ops": set()})
        is_current = key == current_month_key
        closed = info["posted"] > 0
        entry = {
            "month": key,
            "regulated_docs_total": info["total"],
            "regulated_docs_posted": info["posted"],
            "operation_types": sorted(info["ops"]),
            "closed": closed,
            "is_current_month_in_progress": is_current,
        }
        months_report.append(entry)
        if not closed and not is_current:
            missing.append(key)

    return {
        "organization": client.org_name,
        "checked_from": f"{start_year:04d}-{start_month:02d}",
        "months": months_report,
        "missing_closures": missing,
    }


def print_summary(report):
    print(f"=== Oy yopilishi tekshiruvi — {report['organization']} ===")
    for m in report["months"]:
        status = "YOPILGAN" if m["closed"] else ("JARAYONDA" if m["is_current_month_in_progress"] else "YOPILMAGAN!")
        print(f"  {m['month']}: {status} (regламент hujjatlar: {m['regulated_docs_posted']}/{m['regulated_docs_total']})")
    if report["missing_closures"]:
        print(f"\n⚠ Yopilmagan oylar: {', '.join(report['missing_closures'])}")
    else:
        print("\nBarcha o'tgan oylar yopilgan.")


def main():
    client = ODataClient()
    report = run(client)
    out_dir = output_dir()
    with open(os.path.join(out_dir, "month_close_check.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print_summary(report)


if __name__ == "__main__":
    main()
