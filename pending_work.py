#!/usr/bin/env python3
"""
pending_work.py — "qolib ketgan ishlar" ro'yxati (5-band).

check_1c.py (provedeniya qilinmagan hujjatlar) va month_close_check.py
(yopilmagan oylar) natijalarini birlashtirib, bitta "qolib ketgan ishlar"
ro'yxatini beradi.

Natija: output/pending_work.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from odata_client import ODataClient, output_dir
import check_1c
import month_close_check


def run(client: ODataClient):
    check_report = check_1c.run(client)
    close_report = month_close_check.run(client)

    items = []
    for key, sec in check_report["sections"].items():
        if "error" in sec:
            continue
        for d in sec.get("unposted", []):
            items.append({
                "type": "unposted_document",
                "doc_type": sec["label"],
                "number": d["number"],
                "date": d["date"],
            })

    for m in close_report["months"]:
        if not m["closed"] and not m["is_current_month_in_progress"]:
            items.append({
                "type": "missing_month_close",
                "month": m["month"],
                "regulated_docs_found": m["regulated_docs_total"],
            })

    return {
        "organization": client.org_name,
        "generated_from": {
            "check_1c_lookback_days": check_report["lookback_days"],
            "month_close_lookback_from": close_report["checked_from"],
        },
        "total_pending": len(items),
        "items": items,
    }


def print_summary(report):
    print(f"=== Qolib ketgan ishlar — {report['organization']} ===")
    if not report["items"]:
        print("  Qolib ketgan ish topilmadi.")
        return
    for it in report["items"]:
        if it["type"] == "unposted_document":
            print(f"  [Hujjat] {it['doc_type']} №{it['number']} ({it['date']}) — provedeniya qilinmagan")
        else:
            print(f"  [Oy yopish] {it['month']} oyi yopilmagan ({it['regulated_docs_found']} ta regламент hujjat topildi)")
    print(f"\nJami: {report['total_pending']} ta qolib ketgan ish.")


def main():
    client = ODataClient()
    report = run(client)
    out_dir = output_dir()
    with open(os.path.join(out_dir, "pending_work.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print_summary(report)


if __name__ == "__main__":
    main()
