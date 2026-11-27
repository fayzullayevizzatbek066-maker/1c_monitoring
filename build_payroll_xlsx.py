import json
import os
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

BASE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(BASE, "output", "payroll_settlement_check.json"), encoding="utf-8") as f:
    report = json.load(f)

bal = report["employee_balances"]
rows = bal["employees"]

wb = Workbook()
ws = wb.active
ws.title = "Ish haqi hisob-kitob"

FONT = "Arial"
header_font = Font(name=FONT, bold=True, color="FFFFFF", size=11)
header_fill = PatternFill("solid", fgColor="1F4E78")
title_font = Font(name=FONT, bold=True, size=14)
sub_font = Font(name=FONT, italic=True, size=10, color="555555")
total_font = Font(name=FONT, bold=True)
normal_font = Font(name=FONT, size=10)
warn_fill = PatternFill("solid", fgColor="FDE9D9")
thin = Side(style="thin", color="D9D9D9")
border = Border(left=thin, right=thin, top=thin, bottom=thin)

ws["A1"] = f"{report['organization']} — Xodimlar bo'yicha ish haqi hisob-kitoblari (rasmiy qoldiq)"
ws["A1"].font = title_font
ws["A2"] = "Manba: AccountingRegister_Хозрасчетный/Balance — 6710 (Ish haqi hisob-kitoblari), 4210 (Berilgan avanslar). Bugungi holat."
ws["A2"].font = sub_font
ws.merge_cells("A1:E1")
ws.merge_cells("A2:E2")

header_row = 4
headers = ["#", "Xodim", "6710 (Ish haqi)", "4210 (Avans)", "Kompaniya qarzi (xodimga)", "Xodim qarzi (kompaniyaga)"]
for col, h in enumerate(headers, start=1):
    cell = ws.cell(row=header_row, column=col, value=h)
    cell.font = header_font
    cell.fill = header_fill
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell.border = border

r = header_row + 1
first_data_row = r
large_threshold = 15_000_000
for i, e in enumerate(rows, start=1):
    acc6710 = e["by_account"].get("6710", {})
    acc4210 = e["by_account"].get("4210", {})
    net6710 = (acc6710.get("debit", 0) or 0) - (acc6710.get("credit", 0) or 0)
    net4210 = (acc4210.get("debit", 0) or 0) - (acc4210.get("credit", 0) or 0)
    ws.cell(row=r, column=1, value=i).font = normal_font
    ws.cell(row=r, column=2, value=e["employee"]).font = normal_font
    c3 = ws.cell(row=r, column=3, value=net6710 if net6710 else None)
    c3.number_format = "#,##0;(#,##0);-"
    c3.font = normal_font
    c4 = ws.cell(row=r, column=4, value=net4210 if net4210 else None)
    c4.number_format = "#,##0;(#,##0);-"
    c4.font = normal_font
    c5 = ws.cell(row=r, column=5, value=e["company_owes_employee"] if e["company_owes_employee"] else None)
    c5.number_format = "#,##0;(#,##0);-"
    c5.font = normal_font
    c6 = ws.cell(row=r, column=6, value=e["employee_owes_company"] if e["employee_owes_company"] else None)
    c6.number_format = "#,##0;(#,##0);-"
    c6.font = normal_font
    if e["company_owes_employee"] >= large_threshold:
        for cc in range(1, 7):
            ws.cell(row=r, column=cc).fill = warn_fill
    for cc in range(1, 7):
        ws.cell(row=r, column=cc).border = border
    r += 1

last_data_row = r - 1
total_row = r + 1
ws.cell(row=total_row, column=2, value="JAMI:").font = total_font
for col in (5, 6):
    letter = get_column_letter(col)
    cell = ws.cell(row=total_row, column=col, value=f"=SUM({letter}{first_data_row}:{letter}{last_data_row})")
    cell.number_format = "#,##0;(#,##0);-"
    cell.font = total_font

note_row = total_row + 2
ws.cell(row=note_row, column=2, value="Och sariq fon = 15,000,000 so'mdan katta qarzdorlik (ko'rib chiqish uchun).").font = sub_font

flags_row = note_row + 2
ws.cell(row=flags_row, column=2, value="ANIQLANGAN XATOLIKLAR / E'TIBOR TALAB QILADIGAN HOLATLAR:").font = Font(name=FONT, bold=True, size=11, color="C00000")
fr = flags_row + 1
for u in bal.get("unidentified_employee_balances", []):
    ws.cell(row=fr, column=2, value=f"Xodimi ko'rsatilmagan qoldiq — {u['label']}: Dt={u['debit']:,.0f}, Kt={u['credit']:,.0f} (subconto bo'sh qoldirilgan hujjat(lar)ni tekshiring)").font = normal_font
    fr += 1
for a in bal.get("register_anomalies", []):
    ws.cell(row=fr, column=2, value=f"Registrda manfiy qiymat — {a['label']}: Dt={a['raw_debit']:,.0f}, Kt={a['raw_credit']:,.0f} (storno/tuzatish yozuvini tekshiring)").font = normal_font
    fr += 1
docs = report["payroll_documents"]["by_doc_type"]
for label, sec in docs.items():
    if "error" in sec:
        continue
    for it in sec.get("unposted_items", []):
        ws.cell(row=fr, column=2, value=f"Provedeniyasiz hujjat — {label} №{it['number']} ({it['date'][:10]})").font = normal_font
        fr += 1
    for it in sec.get("deletion_marked_items", []):
        ws.cell(row=fr, column=2, value=f"O'chirishga belgilangan — {label} №{it['number']} ({it['date'][:10]})").font = normal_font
        fr += 1
if fr == flags_row + 1:
    ws.cell(row=fr, column=2, value="Boshqa xatolik topilmadi.").font = normal_font

widths = [5, 38, 20, 18, 22, 22]
for i, w in enumerate(widths, start=1):
    ws.column_dimensions[get_column_letter(i)].width = w
ws.freeze_panes = f"A{first_data_row}"

out_path = os.path.join(BASE, "output_xlsx", "ALMIRA_SR_ish_haqi_hisobkitob.xlsx")
wb.save(out_path)
print("Saved:", out_path, "rows:", last_data_row - first_data_row + 1)
