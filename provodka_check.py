#!/usr/bin/env python3
"""
provodka_check.py — birlamchi provodka skrining (yuridik xulosa emas).

AccountingRegister_Хозрасчетный (buxgalteriya registri) yozuvlari bo'yicha
quyidagilarni belgilaydi:
  1. Qo'lda kiritilgan "Операция" (Document_ОперацияБух) yozuvlari
  2. Bir xil schyot bo'yicha Dt = Kt (masalan 5110/5110) — ko'pincha asosiy/qo'shimcha
     bank schyot o'rtasidagi legitim o'tkazma, lekin ko'rib chiqish uchun belgilanadi
  3. Summasi nolga teng yozuvlar
  4. Dam olish kuniga to'g'ri keluvchi QO'LDA kiritilgan (faqat ОперацияБух) yozuvlar —
     avtomatik hujjatlar (kassa chek, bank, realizatsiya) dam olish kunida bo'lishi
     normal, shuning uchun bu band faqat qo'lda kiritilganlarga tegishli.

Natija: output/provodka_check.json
"""
import json
import os
import sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from odata_client import ODataClient, odata_date, days_ago

LOOKBACK_DAYS = 30
MANUAL_RECORDER_TYPE = "StandardODATA.Document_ОперацияБух"

SELECT = ["Recorder", "Recorder_Type", "Period", "LineNumber", "Active",
          "AccountDr_Key", "AccountCr_Key", "Сумма"]


def account_code(client, key):
    if not key or key == "00000000-0000-0000-0000-000000000000":
        return None
    m = client.get_catalog_map("ChartOfAccounts_Хозрасчетный", select=("Ref_Key", "Code", "Description"))
    row = m.get(key)
    return row.get("Code") if row else key


def run(client: ODataClient, lookback_days=LOOKBACK_DAYS):
    since = odata_date(days_ago(lookback_days))
    rows = client.query(
        "AccountingRegister_Хозрасчетный_RecordType",
        select=SELECT,
        filter_=f"Period ge {since} and Active eq true",
        orderby="Period desc",
    )

    manual_entries = []
    same_account = []
    zero_amount = []
    weekend_manual = []

    for r in rows:
        is_manual = r.get("Recorder_Type") == MANUAL_RECORDER_TYPE
        dr = r.get("AccountDr_Key")
        cr = r.get("AccountCr_Key")
        amount = r.get("Сумма") or 0
        period_str = r.get("Period")

        if is_manual:
            manual_entries.append(r)

        if dr and cr and dr == cr:
            same_account.append(r)

        if amount == 0:
            zero_amount.append(r)

        if is_manual and period_str:
            try:
                d = dt.datetime.fromisoformat(period_str)
                if d.weekday() >= 5:  # Saturday=5, Sunday=6
                    weekend_manual.append(r)
            except ValueError:
                pass

    def fmt(items, limit=50):
        out = []
        for r in items[:limit]:
            out.append({
                "recorder": r.get("Recorder"),
                "recorder_type": r.get("Recorder_Type"),
                "period": r.get("Period"),
                "account_dr": account_code(client, r.get("AccountDr_Key")),
                "account_cr": account_code(client, r.get("AccountCr_Key")),
                "amount": r.get("Сумма"),
            })
        return out

    report = {
        "organization": client.org_name,
        "lookback_days": lookback_days,
        "total_records_scanned": len(rows),
        "manual_operations": {
            "count": len(manual_entries),
            "items": fmt(manual_entries),
        },
        "same_account_dr_eq_cr": {
            "count": len(same_account),
            "note": "Ko'pincha asosiy/qo'shimcha bank schyot o'rtasidagi legitim o'tkazma (sub-schyot analitikasi OData orqali ko'rinmaydi) — xato emas, tekshirish uchun.",
            "items": fmt(same_account),
        },
        "zero_amount": {
            "count": len(zero_amount),
            "items": fmt(zero_amount),
        },
        "weekend_manual_postings": {
            "count": len(weekend_manual),
            "note": "Faqat qo'lda kiritilgan (Операция) yozuvlar; avtomatik hujjatlar dam olish kunida normal.",
            "items": fmt(weekend_manual),
        },
    }
    return report


def print_summary(report):
    print(f"=== Provodka skrining — {report['organization']} ({report['lookback_days']} kunlik) ===")
    print(f"Jami tekshirilgan yozuvlar: {report['total_records_scanned']}")
    print(f"  Qo'lda kiritilgan (Операция): {report['manual_operations']['count']}")
    print(f"  Bir xil schyot Dt=Kt: {report['same_account_dr_eq_cr']['count']}")
    print(f"  Summasi 0: {report['zero_amount']['count']}")
    print(f"  Dam olish kunidagi qo'lda yozuvlar: {report['weekend_manual_postings']['count']}")


def main():
    client = ODataClient()
    report = run(client)
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "provodka_check.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print_summary(report)


if __name__ == "__main__":
    main()
