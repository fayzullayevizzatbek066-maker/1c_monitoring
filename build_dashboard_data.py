#!/usr/bin/env python3
"""
build_dashboard_data.py — barcha tekshiruvlarni ishga tushirib, Dashboard
artifact uchun bitta birlashtirilgan JSON snapshot hosil qiladi.

(Dashboard artifact bu faylni o'qiydi; u "live" emas, har safar shu skript
qayta ishga tushganda yangilanadi.)

Natija: output/dashboard_data.json
"""
import json
import os
import sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from odata_client import ODataClient, output_dir

import check_1c
import provodka_check
import month_close_check
import activity_report
import pending_work
import error_documents
import settlements_check
import cash_in_transit_check
import payroll_settlement_check
import fixed_assets_materials_check
import provodka_scheme_check


def run_all(client: ODataClient):
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "organization": client.org_name,
        "sections": {
            "1_check_1c": check_1c.run(client),
            "2_provodka_check": provodka_check.run(client),
            "3_month_close_check": month_close_check.run(client),
            "4_activity_report": activity_report.run(client),
            "5_pending_work": pending_work.run(client),
            "6_error_documents": error_documents.run(client),
            "7_settlements_check": settlements_check.run(client),
            "8_cash_in_transit_check": cash_in_transit_check.run(client),
            "9_payroll_settlement_check": payroll_settlement_check.run(client),
            "10_fixed_assets_materials_check": fixed_assets_materials_check.run(client),
            "11_provodka_scheme_check": provodka_scheme_check.run(client),
        },
    }


def main():
    client = ODataClient()
    data = run_all(client)
    out_dir = output_dir()
    out_path = os.path.join(out_dir, "dashboard_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Dashboard snapshot yozildi: {out_path}")
    print(f"Yaratilgan vaqt: {data['generated_at']}")
    for key in data["sections"]:
        print(f"  - {key}: OK")


if __name__ == "__main__":
    main()
