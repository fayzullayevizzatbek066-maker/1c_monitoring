#!/usr/bin/env python3
"""
cash_in_transit_check.py — 57xx guruhi ("Yo'ldagi pul mablag'lari", jumladan
5720 "Продажи по платежным картам") bo'yicha oylik qoldiq trendi va diagnostika.

G'oya: 5720 schyotiga Dt tomondan "Отчет о розничных продажах" (kartadagi
savdo) hujjatlari, Kt tomondan esa bank orqali kelgan pul (ПоступлениеНаРасчетныйСчет,
terminal to'lovlari) tushadi. Agar Dt tomon Kt tomondan sezilarli orqada qolsa —
demak savdo hisobotlari kiritilmagan yoki kech kiritilmoqda.

Natija: output/cash_in_transit_check.json
"""
import json
import os
import sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from odata_client import ODataClient, odata_date, days_ago

LOOKBACK_DAYS = 420  # ~14 months, so a trend break is visible
ACCOUNT_PREFIX = "57"
FOCUS_ACCOUNT_PREFIX = "5720"

SELECT = ["Recorder", "Recorder_Type", "Period", "AccountDr_Key", "AccountCr_Key", "Сумма", "Active"]


def accounts_with_prefix(client, prefix):
    m = client.get_catalog_map("ChartOfAccounts_Хозрасчетный", select=("Ref_Key", "Code"))
    return {k for k, v in m.items() if (v.get("Code") or "").startswith(prefix)}


def run(client: ODataClient, lookback_days=LOOKBACK_DAYS):
    since = odata_date(days_ago(lookback_days))
    code_map = {k: v.get("Code") for k, v in
                client.get_catalog_map("ChartOfAccounts_Хозрасчетный", select=("Ref_Key", "Code")).items()}
    accounts_57 = accounts_with_prefix(client, ACCOUNT_PREFIX)
    accounts_5720 = {k for k in accounts_57 if (code_map.get(k) or "").startswith(FOCUS_ACCOUNT_PREFIX)}

    if not accounts_57:
        return {"organization": client.org_name, "error": "57xx guruhidagi schyotlar topilmadi"}

    rows = client.query(
        "AccountingRegister_Хозрасчетный_RecordType",
        select=SELECT,
        filter_=f"Period ge {since} and Active eq true",
        orderby="Period asc",
    )

    monthly = {}  # "YYYY-MM" -> {"dt":0.0,"kt":0.0}
    monthly_5720_by_source = {}  # "YYYY-MM" -> {"dt_retail":0.0, "kt_bank":0.0, "dt_other":0.0, "kt_other":0.0}

    for r in rows:
        period_str = r.get("Период") if "Период" in r else r.get("Period")
        if not period_str:
            continue
        d = dt.datetime.fromisoformat(period_str)
        key = f"{d.year:04d}-{d.month:02d}"
        amount = r.get("Сумма") or 0.0
        dr, cr = r.get("AccountDr_Key"), r.get("AccountCr_Key")
        rtype = r.get("Recorder_Type") or ""

        if dr in accounts_57:
            monthly.setdefault(key, {"dt": 0.0, "kt": 0.0})
            monthly[key]["dt"] += amount
        if cr in accounts_57:
            monthly.setdefault(key, {"dt": 0.0, "kt": 0.0})
            monthly[key]["kt"] += amount

        if dr in accounts_5720 or cr in accounts_5720:
            monthly_5720_by_source.setdefault(
                key, {"dt_retail": 0.0, "kt_bank": 0.0, "dt_other": 0.0, "kt_other": 0.0})
            is_retail = "ОтчетОРозничныхПродажах" in rtype
            is_bank_in = "ПоступлениеНаРасчетныйСчет" in rtype
            if dr in accounts_5720:
                if is_retail:
                    monthly_5720_by_source[key]["dt_retail"] += amount
                else:
                    monthly_5720_by_source[key]["dt_other"] += amount
            if cr in accounts_5720:
                if is_bank_in:
                    monthly_5720_by_source[key]["kt_bank"] += amount
                else:
                    monthly_5720_by_source[key]["kt_other"] += amount

    months_sorted = sorted(monthly.keys())
    trend = []
    running_balance = 0.0
    for key in months_sorted:
        v = monthly[key]
        change = v["dt"] - v["kt"]
        running_balance += change
        trend.append({
            "month": key,
            "debit_turnover": round(v["dt"], 2),
            "credit_turnover": round(v["kt"], 2),
            "net_change": round(change, 2),
            "running_balance": round(running_balance, 2),
        })

    diagnosis_5720 = []
    for key in sorted(monthly_5720_by_source.keys()):
        v = monthly_5720_by_source[key]
        diagnosis_5720.append({
            "month": key,
            "retail_sales_postings_dt": round(v["dt_retail"], 2),
            "bank_receipts_kt": round(v["kt_bank"], 2),
            "other_dt": round(v["dt_other"], 2),
            "other_kt": round(v["kt_other"], 2),
            "lag": round(v["kt_bank"] - v["dt_retail"], 2),
        })

    sharp_negative_months = [t["month"] for t in trend if t["running_balance"] < -50_000_000]

    return {
        "organization": client.org_name,
        "lookback_days": lookback_days,
        "monthly_trend_57xx": trend,
        "diagnosis_5720": diagnosis_5720,
        "flagged_months_balance_below_-50mln": sharp_negative_months,
    }


def print_summary(report):
    if "error" in report:
        print(report["error"])
        return
    print(f"=== 57xx (yo'ldagi pul mablag'lari) trendi — {report['organization']} ===")
    for t in report["monthly_trend_57xx"][-6:]:
        print(f"  {t['month']}: o'zgarish {t['net_change']:,.0f}, qoldiq {t['running_balance']:,.0f}")
    if report["flagged_months_balance_below_-50mln"]:
        print(f"\n⚠ Qoldiq -50 mln so'mdan past bo'lgan oylar: {', '.join(report['flagged_months_balance_below_-50mln'])}")
    print("\n5720 diagnostikasi (so'nggi 3 oy):")
    for d in report["diagnosis_5720"][-3:]:
        print(f"  {d['month']}: savdo hisoboti(Dt)={d['retail_sales_postings_dt']:,.0f}  bank tushumi(Kt)={d['bank_receipts_kt']:,.0f}  farq={d['lag']:,.0f}")


def main():
    client = ODataClient()
    report = run(client)
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "cash_in_transit_check.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print_summary(report)


if __name__ == "__main__":
    main()
