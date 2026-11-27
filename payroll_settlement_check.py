#!/usr/bin/env python3
"""
payroll_settlement_check.py — xodimlar bo'yicha ish haqi hisob-kitoblari
(qarzdorlik/ortiqcha to'lov) tekshiruvi.

Qamrov:
  (a) Har bir xodim bo'yicha RASMIY qoldiq — AccountingRegister_Хозрасчетный/Balance
      dan, 6710 (Ish haqi bo'yicha hisob-kitoblar) va 4210 (Ish haqiga oid
      berilgan avanslar) schyotlari bo'yicha, ExtDimension1=xodim (Catalog_ФизическиеЛица).
      Kreditor qoldiq (6710 Kt) = kompaniya xodimga qarzdor (hali to'lanmagan ish haqi).
      Debitor qoldiq (6710 Dt yoki 4210 Dt) = xodim kompaniyaga qarzdor (ortiqcha
      to'langan yoki yopilmagan avans).
  (b) Xatolik/anomaliya tekshiruvi:
      - 6710 da Dt (debet) qoldiq bo'lgan xodimlar — bu normal holat emas
        (hisoblangandan ko'p to'langan bo'lishi mumkin) -> "ortiqcha to'lov" deb belgilanadi
      - G'ayrioddiy katta kreditor qoldiq (THRESHOLD dan yuqori) — ko'rib chiqish uchun
      - Document_НачислениеЗарплаты va Document_ВедомостьНаВыплатуЗарплатыВБанк/ВКассу
        orasida provedeniya qilinmagan / o'chirishga belgilangan hujjatlar (365 kun)

Natija: output/payroll_settlement_check.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from odata_client import ODataClient, odata_date, days_ago, output_dir

LOOKBACK_DAYS = 365
REGISTER = "AccountingRegister_Хозрасчетный"

# (code, label) — Ref_Key is resolved per-organization via client.account_key(code);
# account GUIDs are NOT shared across different 1C bases.
PAYROLL_ACCOUNTS = [
    ("6710", "Ish haqi bo'yicha hisob-kitoblar"),
    ("4210", "Ish haqiga oid berilgan avanslar"),
]

PAYROLL_DOC_TYPES = [
    ("Document_НачислениеЗарплаты", "Ish haqi hisoblash"),
    ("Document_ВедомостьНаВыплатуЗарплатыВБанк", "Ish haqi to'lovi (bank orqali)"),
    ("Document_ВедомостьНаВыплатуЗарплатыВКассу", "Ish haqi to'lovi (kassa orqali)"),
]

LARGE_ARREARS_THRESHOLD = 15_000_000  # so'm — ko'rib chiqish uchun belgilanadigan chegara
EMPTY_GUID = "00000000-0000-0000-0000-000000000000"


def check_employee_balances(client):
    per_emp = {}  # name -> {"by_account": {code: {"dr":..,"cr":..}}}
    errors = []
    unidentified = []  # rows where ExtDimension1 is empty/missing — can't tell which employee
    register_anomalies = []  # raw negative Dr/Cr component on a row (unusual for a Balance table)
    for code, label in PAYROLL_ACCOUNTS:
        ref_key = client.account_key(code)
        if not ref_key:
            errors.append({"account": code, "error": f"ChartOfAccounts_Хозрасчетный da Code={code} topilmadi"})
            continue
        try:
            rows = client.query(
                REGISTER + "/Balance",
                select=["ExtDimension1", "ExtDimension1_Type", "СуммаBalanceDr", "СуммаBalanceCr"],
                filter_=f"Account_Key eq guid'{ref_key}'",
            )
        except RuntimeError as e:
            errors.append({"account": code, "error": str(e)})
            continue
        for r in rows:
            ext1, ext1_type = r.get("ExtDimension1"), r.get("ExtDimension1_Type") or ""
            dr, cr = r.get("СуммаBalanceDr") or 0.0, r.get("СуммаBalanceCr") or 0.0
            if dr < 0 or cr < 0:
                register_anomalies.append({
                    "account": code, "label": label,
                    "raw_debit": dr, "raw_credit": cr,
                    "note": "Balans jadvalida manfiy qiymat — odatiy emas, storno/tuzatish yozuvi tekshirilishi kerak",
                })
            if not ext1 or ext1 == EMPTY_GUID or "ФизическиеЛица" not in ext1_type:
                if dr or cr:
                    unidentified.append({"account": code, "label": label, "debit": dr, "credit": cr})
                continue
            name = client.describe_ref("Catalog_ФизическиеЛица", ext1) or ext1
            entry = per_emp.setdefault(name, {"by_account": {}})
            acc = entry["by_account"].setdefault(code, {"dr": 0.0, "cr": 0.0, "label": label})
            acc["dr"] += dr
            acc["cr"] += cr

    table = []
    overpayments = []
    large_arrears = []
    for name, entry in per_emp.items():
        arrears = 0.0   # kompaniya xodimga qarzdor (6710 Kt net)
        advance = 0.0   # xodim kompaniyaga qarzdor (6710 Dt + 4210 Dt net)
        by_account_out = {}
        for code, acc in entry["by_account"].items():
            net = acc["dr"] - acc["cr"]
            by_account_out[code] = {"label": acc["label"], "debit": round(acc["dr"], 2), "credit": round(acc["cr"], 2)}
            if code == "6710":
                arrears += acc["cr"] - acc["dr"]
                if acc["dr"] > 0:
                    overpayments.append({
                        "employee": name,
                        "account": code,
                        "overpayment_amount": round(acc["dr"], 2),
                    })
            else:
                advance += acc["dr"] - acc["cr"]
        if abs(arrears) < 1 and abs(advance) < 1:
            continue
        row = {
            "employee": name,
            "by_account": by_account_out,
            "company_owes_employee": round(max(arrears, 0), 2),
            "employee_owes_company": round(max(advance, 0) + max(-arrears, 0), 2),
        }
        table.append(row)
        if row["company_owes_employee"] >= LARGE_ARREARS_THRESHOLD:
            large_arrears.append({"employee": name, "amount": row["company_owes_employee"]})

    table.sort(key=lambda x: -(x["company_owes_employee"] + x["employee_owes_company"]))
    large_arrears.sort(key=lambda x: -x["amount"])

    total_arrears = sum(r["company_owes_employee"] for r in table)
    total_advance = sum(r["employee_owes_company"] for r in table)

    result = {
        "note": "Rasmiy qoldiq — 6710/4210 schyotlari bo'yicha hisob-kitob registridan (bugungi holat).",
        "total_employees_with_balance": len(table),
        "total_company_owes_employees": round(total_arrears, 2),
        "total_employees_owe_company": round(total_advance, 2),
        "employees": table,
        "overpayment_flags": overpayments,
        "large_arrears_flags": large_arrears,
        "unidentified_employee_balances": unidentified,
        "register_anomalies": register_anomalies,
    }
    if errors:
        result["errors"] = errors
    return result


def check_payroll_documents(client, since):
    out = {}
    totals = {"checked": 0, "unposted": 0, "deletion_marked": 0}
    for entity, label in PAYROLL_DOC_TYPES:
        try:
            rows = client.query(
                entity,
                select=["Ref_Key", "Number", "Date", "Posted", "DeletionMark"],
                filter_=f"Date ge {since}",
                orderby="Date desc",
            )
        except RuntimeError as e:
            out[label] = {"error": str(e)}
            continue
        unposted = [r for r in rows if not r.get("Posted")]
        deleted = [r for r in rows if r.get("DeletionMark")]
        totals["checked"] += len(rows)
        totals["unposted"] += len(unposted)
        totals["deletion_marked"] += len(deleted)
        out[label] = {
            "checked_count": len(rows),
            "unposted_count": len(unposted),
            "deletion_marked_count": len(deleted),
            "unposted_items": [{"number": r["Number"], "date": r["Date"]} for r in unposted[:50]],
            "deletion_marked_items": [{"number": r["Number"], "date": r["Date"]} for r in deleted[:50]],
        }
    return {"by_doc_type": out, "totals": totals}


def run(client: ODataClient, lookback_days=LOOKBACK_DAYS):
    since = odata_date(days_ago(lookback_days))
    return {
        "organization": client.org_name,
        "lookback_days": lookback_days,
        "employee_balances": check_employee_balances(client),
        "payroll_documents": check_payroll_documents(client, since),
    }


def print_summary(report):
    print(f"=== Ish haqi hisob-kitoblari — {report['organization']} ===")
    bal = report["employee_balances"]
    print(f"Jami {bal['total_employees_with_balance']} xodimda qoldiq bor.")
    print(f"Kompaniya xodimlarga jami qarzi: {bal['total_company_owes_employees']:,.0f} so'm")
    print(f"Xodimlar kompaniyaga jami qarzi: {bal['total_employees_owe_company']:,.0f} so'm")
    if bal["overpayment_flags"]:
        print(f"OGOHLANTIRISH — ortiqcha to'lov (6710 da debet qoldiq): {len(bal['overpayment_flags'])} ta xodim")
        for o in bal["overpayment_flags"][:10]:
            print(f"  {o['employee']}: {o['overpayment_amount']:,.0f} so'm")
    if bal["large_arrears_flags"]:
        print(f"Katta qarzdorlik (>={LARGE_ARREARS_THRESHOLD:,.0f} so'm):")
        for a in bal["large_arrears_flags"][:10]:
            print(f"  {a['employee']}: {a['amount']:,.0f} so'm")
    if bal["unidentified_employee_balances"]:
        print("OGOHLANTIRISH — xodimi ko'rsatilmagan qoldiq (subconto bo'sh):")
        for u in bal["unidentified_employee_balances"]:
            print(f"  {u['label']}: Dt={u['debit']:,.0f}  Kt={u['credit']:,.0f}")
    if bal["register_anomalies"]:
        print(f"OGOHLANTIRISH — registrda manfiy qiymat (tekshirish kerak): {len(bal['register_anomalies'])} ta")
        for a in bal["register_anomalies"][:10]:
            print(f"  {a['label']}: Dt={a['raw_debit']:,.0f}  Kt={a['raw_credit']:,.0f}")
    docs = report["payroll_documents"]["totals"]
    print(f"Ish haqi hujjatlari ({report['lookback_days']} kun): {docs['checked']} ta tekshirildi, "
          f"{docs['unposted']} provedeniyasiz, {docs['deletion_marked']} o'chirishga belgilangan")
    for label, sec in report["payroll_documents"]["by_doc_type"].items():
        if "error" in sec:
            continue
        for it in sec.get("unposted_items", []):
            print(f"  ! Provedeniyasiz — {label} №{it['number']} ({it['date']})")
        for it in sec.get("deletion_marked_items", []):
            print(f"  ! O'chirishga belgilangan — {label} №{it['number']} ({it['date']})")


def main():
    client = ODataClient()
    report = run(client)
    out_dir = output_dir()
    with open(os.path.join(out_dir, "payroll_settlement_check.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print_summary(report)


if __name__ == "__main__":
    main()
