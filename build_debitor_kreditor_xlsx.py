import json
import os
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

BASE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(BASE, "output", "settlements_check.json"), encoding="utf-8") as f:
    report = json.load(f)

bal = report["counterparty_balances"]
rows = bal["counterparties"]
accounts = [a["code"] for a in bal["accounts_checked"]]  # 4010, 6010, 4310, 6310
acc_labels = {a["code"]: a["label"] for a in bal["accounts_checked"]}

wb = Workbook()
ws = wb.active
ws.title = "Debitor-Kreditor"

FONT = "Arial"
header_font = Font(name=FONT, bold=True, color="FFFFFF", size=11)
header_fill = PatternFill("solid", fgColor="1F4E78")
title_font = Font(name=FONT, bold=True, size=14)
sub_font = Font(name=FONT, italic=True, size=10, color="555555")
total_font = Font(name=FONT, bold=True)
normal_font = Font(name=FONT, size=10)
thin = Side(style="thin", color="D9D9D9")
border = Border(left=thin, right=thin, top=thin, bottom=thin)

ws["A1"] = f"{report['organization']} — Debitor va kreditor qoldiqlari (rasmiy, hisob-kitob registridan)"
ws["A1"].font = title_font
ws["A2"] = "Manba: AccountingRegister_Хозрасчетный/Balance — 4010 (Xaridorlar), 6010 (Yetkazib beruvchilar), 4310 (Berilgan avanslar), 6310 (Olingan avanslar). Bugungi holat bo'yicha."
ws["A2"].font = sub_font
ws.merge_cells("A1:H1")
ws.merge_cells("A2:H2")

header_row = 4
headers = ["#", "Kontragent"] + [f"{c} Dt" for c in accounts] + [f"{c} Kt" for c in accounts] + ["Jami debitor", "Jami kreditor"]
# simplify: show net per account instead of Dt/Kt split, keep it compact
headers = ["#", "Kontragent"] + [acc_labels[c] for c in accounts] + ["Jami debitor", "Jami kreditor"]
for col, h in enumerate(headers, start=1):
    cell = ws.cell(row=header_row, column=col, value=h)
    cell.font = header_font
    cell.fill = header_fill
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell.border = border

r = header_row + 1
first_data_row = r
for i, c in enumerate(rows, start=1):
    ws.cell(row=r, column=1, value=i).font = normal_font
    ws.cell(row=r, column=2, value=c["counterparty"]).font = normal_font
    col = 3
    for code in accounts:
        acc = c["by_account"].get(code)
        val = None
        if acc:
            val = acc["debit"] if acc["debit"] else (-acc["credit"] if acc["credit"] else 0)
            # show signed net for that account: Dt positive, Kt negative
            val = acc["debit"] - acc["credit"]
        cell = ws.cell(row=r, column=col, value=val if val else None)
        cell.number_format = "#,##0;(#,##0);-"
        cell.font = normal_font
        col += 1
    ws.cell(row=r, column=col, value=c["receivable"] if c["receivable"] else None).number_format = "#,##0;(#,##0);-"
    ws.cell(row=r, column=col).font = normal_font
    col += 1
    ws.cell(row=r, column=col, value=c["payable"] if c["payable"] else None).number_format = "#,##0;(#,##0);-"
    ws.cell(row=r, column=col).font = normal_font
    for cc in range(1, col + 1):
        ws.cell(row=r, column=cc).border = border
    r += 1

last_data_row = r - 1
total_row = r + 1
ws.cell(row=total_row, column=2, value="JAMI:").font = total_font
col = 3
for code in accounts:
    letter = get_column_letter(col)
    cell = ws.cell(row=total_row, column=col, value=f"=SUM({letter}{first_data_row}:{letter}{last_data_row})")
    cell.number_format = "#,##0;(#,##0);-"
    cell.font = total_font
    col += 1
for _ in range(2):
    letter = get_column_letter(col)
    cell = ws.cell(row=total_row, column=col, value=f"=SUM({letter}{first_data_row}:{letter}{last_data_row})")
    cell.number_format = "#,##0;(#,##0);-"
    cell.font = total_font
    col += 1

gw_row = total_row + 2
ws.cell(row=gw_row, column=2, value="To'lov tizimlari orqali aylangan (debitor/kreditor emas, jadvaldan chiqarilgan):").font = sub_font
ws.cell(row=gw_row, column=len(headers) - 1, value=bal["payment_gateway_volume_excluded"]).number_format = "#,##0"
ws.cell(row=gw_row, column=len(headers) - 1).font = sub_font

note_row = gw_row + 2
ws.cell(row=note_row, column=2, value=f"Jami {bal['total_counterparties_with_balance']} ta kontragentda qoldiq bor; barchasi shu jadvalda ko'rsatilgan.").font = sub_font

# column widths
widths = [5, 42] + [16] * len(accounts) + [16, 16]
for i, w in enumerate(widths, start=1):
    ws.column_dimensions[get_column_letter(i)].width = w

ws.freeze_panes = f"A{first_data_row}"

out_path = os.path.join(BASE, "output_xlsx", "ALMIRA_SR_debitor_kreditor.xlsx")
wb.save(out_path)
print("Saved:", out_path)
print("Rows:", last_data_row - first_data_row + 1)
