#!/usr/bin/env python3
"""
settlements_check.py — hisob-kitoblar (bank operatsiyalari, shartnomalar,
debitor/kreditor) tekshiruvi (7-band).

Qamrov:
  (a) Shartnomasi ko'rsatilmagan hujjatlar: bank kirim/chiqim, realizatsiya,
      tovar/xizmat qabul qilish
  (b) Bank chiqim hujjatlarida "To'lov maqsadi" (НазначениеПлатежа) bo'sh
      qolgan holatlar
  (c) Kontragentlar bo'yicha debitor/kreditor qoldiqlari — FAQAT hujjat
      summalari asosida TAXMINIY hisoblanadi (OData orqali standart
      hisob-kitob registri/Остатки virtual jadvali ochilmagan — rasmiy
      4010/6010 qoldig'i EMAS). To'lov tizimlari (Uzum, Click, Paynet va h.k.)
      pul o'tkazish vositachisi sifatida bu jadvaldan chiqarib tashlanadi.

Natija: output/settlements_check.json
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from odata_client import ODataClient, odata_date, days_ago

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


def check_counterparty_balances(client, since):
    """Approximate receivable (sales - bank receipts) / payable (purchases - bank payments)
    per counterparty, from document sums only. NOT an official 4010/6010 balance."""
    balances = {}  # name -> {"sales":..,"receipts":..,"purchases":..,"payments":..}

    def add(name, field, amount):
        if not name:
            return
        balances.setdefault(name, {"sales": 0.0, "receipts": 0.0, "purchases": 0.0, "payments": 0.0})
        balances[name][field] += amount or 0.0

    sales_rows = client.query(SALES, select=["СуммаДокумента", "Контрагент_Key"],
                               filter_=f"Date ge {since} and Posted eq true")
    for r in sales_rows:
        name = client.describe_ref("Catalog_Контрагенты", r.get("Контрагент_Key"))
        add(name, "sales", r.get("СуммаДокумента"))

    purchase_rows = client.query(PURCHASES, select=["СуммаДокумента", "Контрагент_Key"],
                                  filter_=f"Date ge {since} and Posted eq true")
    for r in purchase_rows:
        name = client.describe_ref("Catalog_Контрагенты", r.get("Контрагент_Key"))
        add(name, "purchases", r.get("СуммаДокумента"))

    bank_in_rows = client.query(BANK_IN, select=["СуммаДокумента", "Контрагент", "Контрагент_Type"],
                                 filter_=f"Date ge {since} and Posted eq true")
    for r in bank_in_rows:
        name = contragent_name_from_dynamic_field(client, r.get("Контрагент"), r.get("Контрагент_Type"))
        add(name, "receipts", r.get("СуммаДокумента"))

    bank_out_rows = client.query(BANK_OUT, select=["СуммаДокумента", "Контрагент", "Контрагент_Type"],
                                  filter_=f"Date ge {since} and Posted eq true")
    for r in bank_out_rows:
        name = contragent_name_from_dynamic_field(client, r.get("Контрагент"), r.get("Контрагент_Type"))
        add(name, "payments", r.get("СуммаДокумента"))

    table = []
    gateway_volume = 0.0
    for name, v in balances.items():
        receivable = v["sales"] - v["receipts"]
        payable = v["purchases"] - v["payments"]
        if is_payment_gateway(name):
            gateway_volume += v["receipts"] + v["payments"]
            continue
        if abs(receivable) < 1 and abs(payable) < 1:
            continue
        table.append({
            "counterparty": name,
            "sales": v["sales"],
            "receipts": v["receipts"],
            "purchases": v["purchases"],
            "payments": v["payments"],
            "approx_receivable": round(receivable, 2),
            "approx_payable": round(payable, 2),
        })
    table.sort(key=lambda x: -abs(x["approx_receivable"] + x["approx_payable"]))

    return {
        "note": "Hujjat summalaridan taxminiy hisoblangan, rasmiy 4010/6010 qoldig'i EMAS (sub-schyot/analitika registri OData orqali ochilmagan).",
        "payment_gateway_volume_excluded": round(gateway_volume, 2),
        "counterparties": table[:100],
    }


def run(client: ODataClient, lookback_days=LOOKBACK_DAYS):
    since = odata_date(days_ago(lookback_days))
    return {
        "organization": client.org_name,
        "lookback_days": lookback_days,
        "missing_contracts": check_missing_contracts(client, since),
        "empty_payment_purpose": check_empty_payment_purpose(client, since),
        "counterparty_balances_approx": check_counterparty_balances(client, since),
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
    bal = report["counterparty_balances_approx"]
    print(f"Debitor/kreditor (taxminiy, top {len(bal['counterparties'])} kontragent ko'rsatilgan):")
    for c in bal["counterparties"][:10]:
        print(f"  {c['counterparty']}: debitor≈{c['approx_receivable']:,.0f}  kreditor≈{c['approx_payable']:,.0f}")


def main():
    client = ODataClient()
    report = run(client)
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "settlements_check.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print_summary(report)


if __name__ == "__main__":
    main()
