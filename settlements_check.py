#!/usr/bin/env python3
"""
settlements_check.py — hisob-kitoblar (bank operatsiyalari, shartnomalar,
debitor/kreditor) tekshiruvi (7-band).

Qamrov:
  (a) Shartnomasi ko'rsatilmagan hujjatlar: bank kirim/chiqim, realizatsiya,
      tovar/xizmat qabul qilish
  (b) Bank chiqim hujjatlarida "To'lov maqsadi" (НазначениеПлатежа) bo'sh
      qolgan holatlar
  (c) Kontragentlar bo'yicha debitor/kreditor qoldiqlari — RASMIY qoldiq,
      AccountingRegister_Хозрасчетный/Balance virtual jadvalidan (4010, 6010,
      4310, 6310 schyotlari bo'yicha, ExtDimension1=kontragent orqali
      guruhlangan). Bu 1C balansidagi rasmiy qoldiqning o'zi — hujjat
      summalaridan taxminiy hisoblash emas.

Natija: output/settlements_check.json
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from odata_client import ODataClient, odata_date, days_ago, output_dir

LOOKBACK_DAYS = 180
EMPTY_GUID = "00000000-0000-0000-0000-000000000000"

# Counterparties that are payment-routing intermediaries, not real debtors/creditors.
PAYMENT_GATEWAY_KEYWORDS = [
    "uzum", "click", "paynet", "tbc", "payme", "upay", "apelsin",
]

BANK_IN = "Document_ПоступлениеНаРасчетныйСчет"
BANK_OUT = "Document_СписаниеСРасчетногоСчета"
SALES = "Document_РеализацияТоваровУслуг"
PURCHASES = "Document_ПоступлениеТоваровУслуг"

REGISTER = "AccountingRegister_Хозрасчетный"

# Settlement accounts to pull official register balances for.
# (code, label, side) — side: "receivable" (debitor, Dr=qarz bizga) or
# "payable" (kreditor, Cr=qarz bizdan). Ref_Key is resolved per-organization
# via client.account_key(code) — account GUIDs are NOT shared across 1C bases.
SETTLEMENT_ACCOUNTS = [
    ("4010", "Xaridorlar bilan hisob-kitoblar", "receivable"),
    ("6010", "Yetkazib beruvchilar bilan hisob-kitoblar", "payable"),
    ("4310", "Berilgan avanslar", "receivable"),
    ("6310", "Olingan avanslar", "payable"),
]


def contragent_name_from_dynamic_field(client, value, type_str):
    if not value or value == EMPTY_GUID:
        return None
    if type_str and "Контрагенты" not in type_str:
        return value  # not a counterparty reference (e.g. a free-text string)
    return client.describe_ref("Catalog_Контрагенты", value) or value


def check_missing_contracts(client, since):
    results = {}
    # (entity, label, contract key field, counterparty field mode)
    # mode "dynamic": Контрагент (string) + Контрагент_Type -> resolve via contragent_name_from_dynamic_field
    # mode "key": Контрагент_Key (Guid) -> resolve directly against Catalog_Контрагенты
    specs = [
        (BANK_OUT, "Bank chiqim", "ДоговорКонтрагента_Key", "dynamic"),
        (BANK_IN, "Bank kirim", "ДоговорКонтрагента_Key", "dynamic"),
        (SALES, "Realizatsiya", "ДоговорКонтрагента_Key", "key"),
        (PURCHASES, "Tovar/xizmat qabul qilish", "ДоговорКонтрагента_Key", "key"),
    ]
    for entity, label, key_field, mode in specs:
        cp_fields = ["Контрагент", "Контрагент_Type"] if mode == "dynamic" else ["Контрагент_Key"]
        try:
            rows = client.query(
                entity,
                select=["Number", "Date", "СуммаДокумента", key_field] + cp_fields,
                filter_=f"Date ge {since} and Posted eq true",
            )
        except RuntimeError as e:
            results[label] = {"error": str(e)}
            continue
        missing = [r for r in rows if not r.get(key_field) or r.get(key_field) == EMPTY_GUID]

        def resolve_cp(r):
            if mode == "dynamic":
                return contragent_name_from_dynamic_field(client, r.get("Контрагент"), r.get("Контрагент_Type"))
            return client.describe_ref("Catalog_Контрагенты", r.get("Контрагент_Key"))

        results[label] = {
            "checked_count": len(rows),
            "missing_contract_count": len(missing),
            "items": [
                {
                    "number": r["Number"],
                    "date": r["Date"],
                    "amount": r.get("СуммаДокумента"),
                    "counterparty": resolve_cp(r),
                }
                for r in missing[:200]
            ],
        }
    return results


def check_empty_payment_purpose(client, since):
    out = {}
    for entity, label in [(BANK_OUT, "Bank chiqim"), (BANK_IN, "Bank kirim")]:
        rows = client.query(
            entity,
            select=["Number", "Date", "СуммаДокумента", "НазначениеПлатежа"],
            filter_=f"Date ge {since} and Posted eq true",
        )
        empty = [r for r in rows if not (r.get("НазначениеПлатежа") or "").strip()]
        out[label] = {
            "checked_count": len(rows),
            "empty_purpose_count": len(empty),
            "items": [{"number": r["Number"], "date": r["Date"], "amount": r.get("СуммаДокумента")}
                      for r in empty[:200]],
        }
    return out


def is_payment_gateway(name):
    if not name:
        return False
    low = name.lower()
    return any(kw in low for kw in PAYMENT_GATEWAY_KEYWORDS)


def check_counterparty_balances(client, since=None):
    """Official per-counterparty receivable/payable balances, read straight from
    AccountingRegister_Хозрасчетный/Balance for the key settlement accounts
    (4010, 6010, 4310, 6310), grouped by ExtDimension1 (kontragent). `since` is
    accepted for interface symmetry but ignored — a register Balance query
    with no Period filter returns the current (today's) balance, which is what
    a debitor/kreditor check needs; a historical cutoff would need Period."""
    # name -> per-account accumulators + totals
    per_cp = {}  # name -> {"by_account": {code: {"dr":.., "cr":..}}, "gateway": bool}

    for code, label, side in SETTLEMENT_ACCOUNTS:
        ref_key = client.account_key(code)
        if not ref_key:
            per_cp.setdefault("__errors__", []).append({"account": code, "error": f"ChartOfAccounts_Хозрасчетный da Code={code} topilmadi"})
            continue
        try:
            rows = client.query(
                REGISTER + "/Balance",
                select=["ExtDimension1", "ExtDimension1_Type", "СуммаBalanceDr", "СуммаBalanceCr"],
                filter_=f"Account_Key eq guid'{ref_key}'",
            )
        except RuntimeError as e:
            per_cp.setdefault("__errors__", []).append({"account": code, "error": str(e)})
            continue
        for r in rows:
            ext1, ext1_type = r.get("ExtDimension1"), r.get("ExtDimension1_Type") or ""
            if not ext1 or "Контрагенты" not in ext1_type:
                continue  # dimension not a counterparty on this account/row
            name = client.describe_ref("Catalog_Контрагенты", ext1) or ext1
            entry = per_cp.setdefault(name, {"by_account": {}})
            acc = entry["by_account"].setdefault(code, {"dr": 0.0, "cr": 0.0, "label": label, "side": side})
            acc["dr"] += r.get("СуммаBalanceDr") or 0.0
            acc["cr"] += r.get("СуммаBalanceCr") or 0.0

    errors = per_cp.pop("__errors__", [])

    table = []
    gateway_volume = 0.0
    for name, entry in per_cp.items():
        receivable = 0.0  # we are owed (Dr on 4010/4310)
        payable = 0.0     # we owe (Cr on 6010/6310)
        by_account_out = {}
        for code, acc in entry["by_account"].items():
            by_account_out[code] = {
                "label": acc["label"],
                "debit": round(acc["dr"], 2),
                "credit": round(acc["cr"], 2),
            }
            if acc["side"] == "receivable":
                receivable += acc["dr"] - acc["cr"]
            else:
                payable += acc["cr"] - acc["dr"]
        volume = abs(receivable) + abs(payable)
        if is_payment_gateway(name):
            gateway_volume += volume
            continue
        if abs(receivable) < 1 and abs(payable) < 1:
            continue
        table.append({
            "counterparty": name,
            "by_account": by_account_out,
            "receivable": round(receivable, 2),
            "payable": round(payable, 2),
        })
    table.sort(key=lambda x: -abs(x["receivable"] + x["payable"]))

    result = {
        "note": "Rasmiy qoldiq — 4010/6010/4310/6310 schyotlari bo'yicha hisob-kitob registridan (bugungi holat).",
        "accounts_checked": [{"code": c, "label": l} for c, l, _ in SETTLEMENT_ACCOUNTS],
        "payment_gateway_volume_excluded": round(gateway_volume, 2),
        "total_counterparties_with_balance": len(table),
        "counterparties": table[:200],
    }
    if errors:
        result["errors"] = errors
    return result


def run(client: ODataClient, lookback_days=LOOKBACK_DAYS):
    since = odata_date(days_ago(lookback_days))
    return {
        "organization": client.org_name,
        "lookback_days": lookback_days,
        "missing_contracts": check_missing_contracts(client, since),
        "empty_payment_purpose": check_empty_payment_purpose(client, since),
        "counterparty_balances": check_counterparty_balances(client),
    }


def print_summary(report):
    print(f"=== Hisob-kitoblar tekshiruvi — {report['organization']} ({report['lookback_days']} kunlik) ===")
    print("Shartnoma ko'rsatilmagan hujjatlar:")
    for label, sec in report["missing_contracts"].items():
        if "error" in sec:
            print(f"  ! {label}: XATOLIK")
            continue
        print(f"  {label}: {sec['missing_contract_count']}/{sec['checked_count']}")
    print("To'lov maqsadi bo'sh:")
    for label, sec in report["empty_payment_purpose"].items():
        print(f"  {label}: {sec['empty_purpose_count']}/{sec['checked_count']}")
    bal = report["counterparty_balances"]
    print(f"Debitor/kreditor (rasmiy qoldiq, top {len(bal['counterparties'])} kontragent ko'rsatilgan):")
    for c in bal["counterparties"][:10]:
        print(f"  {c['counterparty']}: debitor={c['receivable']:,.0f}  kreditor={c['payable']:,.0f}")


def main():
    client = ODataClient()
    report = run(client)
    out_dir = output_dir()
    with open(os.path.join(out_dir, "settlements_check.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print_summary(report)


if __name__ == "__main__":
    main()
