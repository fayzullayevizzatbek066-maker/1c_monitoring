#!/usr/bin/env python3
"""
check_1c.py — kunlik asosiy tekshiruv.

So'nggi 14 kun ichida kiritilgan hujjatlar orasida:
  - provedeniya qilinmagan (Posted = false)
  - o'chirishga belgilangan (DeletionMark = true)
bo'lganlarini quyidagi hujjat turlari bo'yicha topadi:
  kassa (PKO/RKO), bank (kirim/chiqim), realizatsiya, EHF (chiqarilgan hisob-faktura),
  ish haqi (hisoblash), avans hisoboti.

Natija: output/check_1c.json + konsolga qisqa xulosa (o'zbek tilida).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from odata_client import ODataClient, odata_date, days_ago

LOOKBACK_DAYS = 14

DOC_TYPES = [
    ("kassa_kirim", "Document_ПриходныйКассовыйОрдер", "Kassa — kirim orderi (PKO)"),
    ("kassa_chiqim", "Document_РасходныйКассовыйОрдер", "Kassa — chiqim orderi (RKO)"),
    ("bank_kirim", "Document_ПоступлениеНаРасчетныйСчет", "Bank — kirim"),
    ("bank_chiqim", "Document_СписаниеСРасчетногоСчета", "Bank — chiqim"),
    ("realizatsiya", "Document_РеализацияТоваровУслуг", "Realizatsiya (tovar/xizmat)"),
    ("ehf", "Document_СчетФактураВыданный", "EHF — chiqarilgan hisob-faktura"),
    ("ish_haqi", "Document_НачислениеЗарплаты", "Ish haqi hisoblash"),
    ("avans", "Document_АвансовыйОтчет", "Avans hisoboti"),
]

SELECT = ["Ref_Key", "Number", "Date", "Posted", "DeletionMark"]


def run(client: ODataClient, lookback_days=LOOKBACK_DAYS):
    since = odata_date(days_ago(lookback_days))
    report = {"lookback_days": lookback_days, "organization": client.org_name, "sections": {}}

    totals = {"checked": 0, "unposted": 0, "deletion_marked": 0}

    for key, entity, label in DOC_TYPES:
        try:
            rows = client.query(entity, select=SELECT, filter_=f"Date ge {since}", orderby="Date desc")
        except RuntimeError as e:
            report["sections"][key] = {"label": label, "error": str(e)}
            continue

        unposted = [r for r in rows if not r.get("Posted")]
        deleted = [r for r in rows if r.get("DeletionMark")]

        totals["checked"] += len(rows)
        totals["unposted"] += len(unposted)
        totals["deletion_marked"] += len(deleted)

        report["sections"][key] = {
            "label": label,
            "checked_count": len(rows),
            "unposted_count": len(unposted),
            "deletion_marked_count": len(deleted),
            "unposted": [
                {"number": r["Number"], "date": r["Date"]} for r in unposted
            ],
            "deletion_marked": [
                {"number": r["Number"], "date": r["Date"]} for r in deleted
            ],
        }

    report["totals"] = totals
    return report


def print_summary(report):
    org = report["organization"]
    print(f"=== 1C kunlik monitoring — {org} ({report['lookback_days']} kunlik) ===")
    for key, sec in report["sections"].items():
        if "error" in sec:
            print(f"  ! {sec['label']}: XATOLIK — {sec['error'][:120]}")
            continue
        flag = ""
        if sec["unposted_count"] or sec["deletion_marked_count"]:
            flag = f"  <-- e'tibor: {sec['unposted_count']} provedeniyasiz, {sec['deletion_marked_count']} o'chirishga belgilangan"
        print(f"  {sec['label']}: {sec['checked_count']} ta tekshirildi{flag}")
    t = report["totals"]
    print(f"\nJami: {t['checked']} hujjat tekshirildi, {t['unposted']} provedeniyasiz, {t['deletion_marked']} o'chirishga belgilangan.")


def main():
    client = ODataClient()
    report = run(client)
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "check_1c.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print_summary(report)


if __name__ == "__main__":
    main()
