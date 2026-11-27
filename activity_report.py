#!/usr/bin/env python3
"""
activity_report.py — "kim nima qildi" taxminiy hisoboti.

1C standart OData interfeysi haqiqiy audit jurnalini (Журнал регистрации)
bermaydi, shuning uchun bu skript har bir asosiy hujjat turidagi
"Ответственный" (mas'ul shaxs) rekvizitidan foydalanib, so'nggi N kun
ichida kim qancha va qanday hujjat kiritganini taxminan hisoblaydi.
Bu real audit-trail emas — faqat hujjatga yozilgan mas'ul shaxs asosida.

Natija: output/activity_report.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from odata_client import ODataClient, odata_date, days_ago, output_dir

LOOKBACK_DAYS = 14

DOC_TYPES = [
    ("Document_ПриходныйКассовыйОрдер", "Kassa kirim"),
    ("Document_РасходныйКассовыйОрдер", "Kassa chiqim"),
    ("Document_ПоступлениеНаРасчетныйСчет", "Bank kirim"),
    ("Document_СписаниеСРасчетногоСчета", "Bank chiqim"),
    ("Document_РеализацияТоваровУслуг", "Realizatsiya"),
    ("Document_СчетФактураВыданный", "EHF chiqarilgan"),
    ("Document_ОтчетОРозничныхПродажах", "Chakana savdo hisoboti"),
    ("Document_АвансовыйОтчет", "Avans hisoboti"),
    ("Document_ОперацияБух", "Qo'lda operatsiya"),
]

SELECT = ["Ref_Key", "Number", "Date", "Ответственный_Key"]


def run(client: ODataClient, lookback_days=LOOKBACK_DAYS):
    since = odata_date(days_ago(lookback_days))
    by_user = {}
    doc_type_totals = {}

    for entity, label in DOC_TYPES:
        try:
            rows = client.query(entity, select=SELECT, filter_=f"Date ge {since}")
        except RuntimeError as e:
            doc_type_totals[label] = {"error": str(e)}
            continue

        doc_type_totals[label] = len(rows)
        for r in rows:
            user_key = r.get("Ответственный_Key")
            user_name = client.describe_ref("Catalog_Пользователи", user_key) or "(belgilanmagan)"
            by_user.setdefault(user_name, {})
            by_user[user_name].setdefault(label, 0)
            by_user[user_name][label] += 1

    user_summary = []
    for user, counts in by_user.items():
        total = sum(counts.values())
        user_summary.append({"user": user, "total_documents": total, "by_doc_type": counts})
    user_summary.sort(key=lambda u: -u["total_documents"])

    return {
        "organization": client.org_name,
        "lookback_days": lookback_days,
        "note": "Taxminiy: har hujjatning 'Ответственный' rekvizitiga asoslangan, haqiqiy audit jurnali emas.",
        "doc_type_totals": doc_type_totals,
        "by_user": user_summary,
    }


def print_summary(report):
    print(f"=== Faoliyat hisoboti (taxminiy) — {report['organization']} ({report['lookback_days']} kunlik) ===")
    for u in report["by_user"]:
        breakdown = ", ".join(f"{k}: {v}" for k, v in u["by_doc_type"].items())
        print(f"  {u['user']}: {u['total_documents']} ta hujjat  ({breakdown})")


def main():
    client = ODataClient()
    report = run(client)
    out_dir = output_dir()
    with open(os.path.join(out_dir, "activity_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print_summary(report)


if __name__ == "__main__":
    main()
