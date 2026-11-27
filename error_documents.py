#!/usr/bin/env python3
"""
error_documents.py — "xatolik aniqlangan hujjatlar" ro'yxati (6-band).

provodka_check.py (birlamchi provodka skrining flaglari) va check_1c.py
(o'chirishga belgilangan hujjatlar) natijalarini birlashtiradi.

Natija: output/error_documents.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from odata_client import ODataClient, output_dir
import check_1c
import provodka_check


def run(client: ODataClient):
    check_report = check_1c.run(client)
    prov_report = provodka_check.run(client)

    items = []

    for key, sec in check_report["sections"].items():
        if "error" in sec:
            continue
        for d in sec.get("deletion_marked", []):
            items.append({
                "type": "deletion_marked_document",
                "doc_type": sec["label"],
                "number": d["number"],
                "date": d["date"],
            })

    for entry in prov_report["manual_operations"]["items"]:
        items.append({
            "type": "manual_operation",
            "period": entry["period"],
            "account_dr": entry["account_dr"],
            "account_cr": entry["account_cr"],
            "amount": entry["amount"],
        })

    for entry in prov_report["zero_amount"]["items"]:
        items.append({
            "type": "zero_amount_posting",
            "period": entry["period"],
            "account_dr": entry["account_dr"],
            "account_cr": entry["account_cr"],
        })

    for entry in prov_report["weekend_manual_postings"]["items"]:
        items.append({
            "type": "weekend_manual_posting",
            "period": entry["period"],
            "account_dr": entry["account_dr"],
            "account_cr": entry["account_cr"],
            "amount": entry["amount"],
        })

    # Same-account Dt=Kt is intentionally excluded from "errors" by default —
    # per prior full-history review it is overwhelmingly legitimate
    # primary<->secondary bank account transfers, not a mistake. Still exposed
    # as its own section for reference.
    same_account = prov_report["same_account_dr_eq_cr"]

    return {
        "organization": client.org_name,
        "total_errors": len(items),
        "items": items,
        "same_account_dr_eq_cr_for_reference": same_account,
    }


def print_summary(report):
    print(f"=== Xatolik aniqlangan hujjatlar — {report['organization']} ===")
    if not report["items"]:
        print("  Xatolik aniqlanmadi.")
    for it in report["items"]:
        t = it["type"]
        if t == "deletion_marked_document":
            print(f"  [O'chirishga belgilangan] {it['doc_type']} №{it['number']} ({it['date']})")
        elif t == "manual_operation":
            print(f"  [Qo'lda operatsiya] {it['period']} Dt{it['account_dr']}/Kt{it['account_cr']} = {it['amount']}")
        elif t == "zero_amount_posting":
            print(f"  [Nol summa] {it['period']} Dt{it['account_dr']}/Kt{it['account_cr']}")
        elif t == "weekend_manual_posting":
            print(f"  [Dam olish kunida qo'lda] {it['period']} Dt{it['account_dr']}/Kt{it['account_cr']} = {it['amount']}")
    print(f"\nJami: {report['total_errors']} ta.")
    ref = report["same_account_dr_eq_cr_for_reference"]
    if ref["count"]:
        print(f"(Ma'lumot uchun: {ref['count']} ta bir xil schyot Dt=Kt yozuvi bor — odatda legitim o'tkazma)")


def main():
    client = ODataClient()
    report = run(client)
    out_dir = output_dir()
    with open(os.path.join(out_dir, "error_documents.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print_summary(report)


if __name__ == "__main__":
    main()
