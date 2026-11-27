#!/usr/bin/env python3
"""
render_dashboard_html.py — output/dashboard_data.json asosida Dashboard
artifact uchun TO'LIQ statik, o'zida hamma narsani saqlagan HTML fayl
yaratadi (hech qanday tashqi "jonli" ma'lumot manbasiga bog'liq emas —
har kuni qayta generatsiya qilinib, artifact'ning files/index.html fayliga
qayta publish qilinadi).

Natija: output/dashboard_index.html
"""
import html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def esc(s):
    return html.escape(str(s if s is not None else "—"))


def fmt_num(n):
    if n is None:
        return "—"
    try:
        return f"{n:,.0f}".replace(",", " ")
    except (TypeError, ValueError):
        return str(n)


def pending_text(items):
    if not items:
        return "Qolib ketgan ish topilmadi."
    lines = []
    for it in items:
        if it["type"] == "unposted_document":
            lines.append(f"- [Hujjat] {it['doc_type']} №{it['number']} ({it['date']}) — provedeniya qilinmagan")
        else:
            lines.append(f"- [Oy yopish] {it['month']} oyi yopilmagan ({it['regulated_docs_found']} ta regламент hujjat)")
    return "\n".join(lines)


def error_text(items):
    if not items:
        return "Xatolik aniqlangan hujjat topilmadi."
    lines = []
    for it in items:
        t = it["type"]
        if t == "deletion_marked_document":
            lines.append(f"- [O'chirishga belgilangan] {it['doc_type']} №{it['number']} ({it['date']})")
        elif t == "manual_operation":
            lines.append(f"- [Qo'lda operatsiya] {it['period']} Dt{it['account_dr']}/Kt{it['account_cr']} = {fmt_num(it['amount'])}")
        elif t == "zero_amount_posting":
            lines.append(f"- [Nol summa] {it['period']} Dt{it['account_dr']}/Kt{it['account_cr']}")
        elif t == "weekend_manual_posting":
            lines.append(f"- [Dam olish kunida qo'lda] {it['period']} Dt{it['account_dr']}/Kt{it['account_cr']} = {fmt_num(it['amount'])}")
    return "\n".join(lines)


def month_close_text(report):
    lines = []
    for m in report["months"]:
        status = "YOPILGAN" if m["closed"] else ("JARAYONDA" if m["is_current_month_in_progress"] else "YOPILMAGAN!")
        lines.append(f"{m['month']}: {status} ({m['regulated_docs_posted']}/{m['regulated_docs_total']})")
    if report["missing_closures"]:
        lines.append("")
        lines.append("DIQQAT — yopilmagan oylar: " + ", ".join(report["missing_closures"]))
    return "\n".join(lines)


def provodka_text(report):
    return (
        f"Jami tekshirilgan yozuvlar: {report['total_records_scanned']}\n"
        f"Qo'lda kiritilgan (Операция): {report['manual_operations']['count']}\n"
        f"Bir xil schyot Dt=Kt: {report['same_account_dr_eq_cr']['count']}\n"
        f"Summasi 0: {report['zero_amount']['count']}\n"
        f"Dam olish kunidagi qo'lda yozuvlar: {report['weekend_manual_postings']['count']}"
    )


def activity_text(report):
    if not report["by_user"]:
        return "Faoliyat topilmadi."
    lines = []
    for u in report["by_user"]:
        breakdown = ", ".join(f"{k}: {v}" for k, v in u["by_doc_type"].items())
        lines.append(f"{u['user']}: {u['total_documents']} ta hujjat ({breakdown})")
    return "\n".join(lines)


def settlements_text(report):
    lines = ["Shartnoma ko'rsatilmagan hujjatlar:"]
    for label, sec in report["missing_contracts"].items():
        if "error" in sec:
            lines.append(f"  {label}: XATOLIK")
        else:
            lines.append(f"  {label}: {sec['missing_contract_count']}/{sec['checked_count']}")
    lines.append("To'lov maqsadi bo'sh:")
    for label, sec in report["empty_payment_purpose"].items():
        lines.append(f"  {label}: {sec['empty_purpose_count']}/{sec['checked_count']}")
    bal = report["counterparty_balances"]
    lines.append(f"Debitor/kreditor (rasmiy qoldiq, 4010/6010/4310/6310, top {min(10, len(bal['counterparties']))} ko'rsatilgan):")
    for c in bal["counterparties"][:10]:
        lines.append(f"  {c['counterparty']}: debitor={fmt_num(c['receivable'])}  kreditor={fmt_num(c['payable'])}")
    return "\n".join(lines)


def cash_transit_text(report):
    if "error" in report:
        return report["error"]
    lines = ["Oylik trend (so'nggi 6 oy):"]
    for t in report["monthly_trend_57xx"][-6:]:
        lines.append(f"  {t['month']}: o'zgarish {fmt_num(t['net_change'])}, qoldiq {fmt_num(t['running_balance'])}")
    if report["flagged_months_balance_below_-50mln"]:
        lines.append("")
        lines.append("Qoldiq -50 mln so'mdan past: " + ", ".join(report["flagged_months_balance_below_-50mln"][-6:]))
    lines.append("")
    lines.append("5720 diagnostikasi (so'nggi 3 oy):")
    for d in report["diagnosis_5720"][-3:]:
        lines.append(f"  {d['month']}: savdo(Dt)={fmt_num(d['retail_sales_postings_dt'])}  bank(Kt)={fmt_num(d['bank_receipts_kt'])}  farq={fmt_num(d['lag'])}")
    return "\n".join(lines)


def payroll_text(report):
    bal = report["employee_balances"]
    lines = [
        f"Jami {bal['total_employees_with_balance']} xodimda qoldiq bor.",
        f"Kompaniya xodimlarga qarzi: {fmt_num(bal['total_company_owes_employees'])} so'm",
        f"Xodimlar kompaniyaga qarzi: {fmt_num(bal['total_employees_owe_company'])} so'm",
    ]
    if bal["large_arrears_flags"]:
        lines.append("")
        lines.append(f"Katta qarzdorlik (top {min(10, len(bal['large_arrears_flags']))}):")
        for a in bal["large_arrears_flags"][:10]:
            lines.append(f"  {a['employee']}: {fmt_num(a['amount'])}")
    if bal["unidentified_employee_balances"] or bal["register_anomalies"]:
        lines.append("")
        lines.append("ANIQLANGAN XATOLIKLAR:")
        for u in bal["unidentified_employee_balances"]:
            lines.append(f"  ! Xodimi ko'rsatilmagan qoldiq — {u['label']}: Dt={fmt_num(u['debit'])} Kt={fmt_num(u['credit'])}")
        for a in bal["register_anomalies"]:
            lines.append(f"  ! Registrda manfiy qiymat — {a['label']}: Dt={fmt_num(a['raw_debit'])} Kt={fmt_num(a['raw_credit'])}")
    docs = report["payroll_documents"]["totals"]
    lines.append("")
    lines.append(f"Ish haqi hujjatlari: {docs['checked']} tekshirildi, {docs['unposted']} provedeniyasiz, {docs['deletion_marked']} o'chirishga belgilangan")
    return "\n".join(lines)


def render(data):
    s = data["sections"]
    c1 = s["1_check_1c"]
    pw = s["5_pending_work"]
    ed = s["6_error_documents"]
    mc = s["3_month_close_check"]
    ct = s["8_cash_in_transit_check"]

    total_unposted = c1["totals"]["unposted"]
    total_marked = c1["totals"]["deletion_marked"]
    month_close_issue = bool(mc["missing_closures"])
    lookback_days = c1["lookback_days"]
    pending_count = pw["total_pending"]
    error_count = ed["total_errors"]

    cash_balance = ct["monthly_trend_57xx"][-1]["running_balance"] if ct.get("monthly_trend_57xx") else None
    cash_negative = (cash_balance or 0) < 0

    close_status_class = "dm-bad" if month_close_issue else "dm-ok"
    close_status_text = "Muammo bor" if month_close_issue else "Joyida"
    cash_class = "dm-bad" if cash_negative else "dm-ok"

    summary = ("Diqqat: oylik yopish bo'yicha muammo topildi — tafsilotlar pastda."
               if month_close_issue else "Barcha asosiy tekshiruvlarda jiddiy muammo topilmadi.")

    return f"""<!-- dash-one-writer-marker -->
<meta name="dash-form" content="dashboard">
<style>
  #dash-root {{ font-family: var(--font-anthropic-sans); color: var(--color-fg); }}
  .dm-wrap {{ max-width: 100%; }}
  .dm-title {{ font-family: var(--font-anthropic-serif); font-weight: 400; font-size: var(--cds-font-size-title); margin: 0 0 var(--cds-gap-sm) 0; }}
  .dm-sub {{ color: var(--color-fg-muted); margin: 0 0 var(--cds-gap-lg) 0; }}
  .dm-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: var(--cds-gap-md); margin-bottom: var(--cds-gap-lg); }}
  .dm-card {{ background: var(--color-panel); border: 1px solid var(--color-border-line); border-radius: var(--cds-radius); padding: var(--cds-pad-lg); }}
  .dm-card-label {{ font-size: var(--cds-font-size-caption); color: var(--color-fg-muted); margin-bottom: var(--cds-gap-xs); }}
  .dm-card-value {{ font-family: var(--font-anthropic-serif); font-weight: 400; font-size: var(--cds-font-size-title); font-variant-numeric: tabular-nums; }}
  .dm-ok {{ color: var(--color-ok); }}
  .dm-bad {{ color: var(--color-bad); }}
  .dm-section {{ background: var(--color-panel); border: 1px solid var(--color-border-line); border-radius: var(--cds-radius); padding: var(--cds-pad-lg); margin-bottom: var(--cds-gap-md); }}
  .dm-section h3 {{ margin-top: 0; font-size: var(--cds-font-size-heading); }}
  .dm-pre {{ white-space: pre-wrap; font-family: var(--font-anthropic-sans); font-size: var(--cds-font-size-body); line-height: 1.5; }}
  .dm-foot {{ color: var(--color-fg-muted); font-size: var(--cds-font-size-caption); margin-top: var(--cds-gap-lg); }}
</style>
<div class="dm-wrap">
  <h1 class="dm-title">1C kunlik monitoring — ALMIRA SR MCHJ</h1>
  <p class="dm-sub">{esc(summary)} (yangilangan: {esc(data['generated_at'])})</p>

  <div class="dm-cards">
    <div class="dm-card"><div class="dm-card-label">O'tkazilmagan hujjatlar</div><div class="dm-card-value">{fmt_num(total_unposted)}</div></div>
    <div class="dm-card"><div class="dm-card-label">O'chirishga belgilangan</div><div class="dm-card-value">{fmt_num(total_marked)}</div></div>
    <div class="dm-card"><div class="dm-card-label">Oylik yopish holati</div><div class="dm-card-value {close_status_class}">{close_status_text}</div></div>
    <div class="dm-card"><div class="dm-card-label">Tekshirilgan davr</div><div class="dm-card-value">{lookback_days} kun</div></div>
    <div class="dm-card"><div class="dm-card-label">Qolib ketgan ishlar</div><div class="dm-card-value">{fmt_num(pending_count)}</div></div>
    <div class="dm-card"><div class="dm-card-label">Xatolik aniqlangan hujjatlar</div><div class="dm-card-value">{fmt_num(error_count)}</div></div>
    <div class="dm-card"><div class="dm-card-label">Yo'ldagi pul mablag'lari (57-guruh)</div><div class="dm-card-value {cash_class}">{fmt_num(cash_balance)} so'm</div></div>
  </div>

  <div class="dm-section"><h3>5) Qilinishi kerak bo'lgan, hali bajarilmagan ishlar ro'yxati</h3><div class="dm-pre">{esc(pending_text(pw['items']))}</div></div>
  <div class="dm-section"><h3>6) Xatolik aniqlangan hujjatlar ro'yxati</h3><div class="dm-pre">{esc(error_text(ed['items']))}</div></div>
  <div class="dm-section"><h3>Oylik yopish (regламент operatsiyalar)</h3><div class="dm-pre">{esc(month_close_text(mc))}</div></div>
  <div class="dm-section"><h3>Provodkalar bo'yicha birlamchi skrining</h3><div class="dm-pre">{esc(provodka_text(s['2_provodka_check']))}</div></div>
  <div class="dm-section"><h3>Xodimlar faoliyati (taxminiy)</h3><div class="dm-pre">{esc(activity_text(s['4_activity_report']))}</div></div>
  <div class="dm-section"><h3>Yo'ldagi pul mablag'lari (57-guruh hisoblar) — qizil/manfiy qoldiq tekshiruvi</h3><div class="dm-pre">{esc(cash_transit_text(ct))}</div></div>
  <div class="dm-section"><h3>7) Shartnomalar, bank to'lov maqsadi va debitor/kreditorlar</h3><div class="dm-pre">{esc(settlements_text(s['7_settlements_check']))}</div></div>
  <div class="dm-section"><h3>9) Xodimlar bo'yicha ish haqi hisob-kitoblari</h3><div class="dm-pre">{esc(payroll_text(s['9_payroll_settlement_check']))}</div></div>

  <div class="dm-section">
    <h3>Keyingi qadamlar / ochiq savollar</h3>
    <div class="dm-pre">- Bu dashboard hozircha faqat ALMIRA SR MCHJ bazasi uchun shablon sifatida ishlab chiqilgan — natija yaxshi bo'lsa, qolgan 1C bazalariga ham moslashtiriladi.
- Provodka skrining hozircha: qo'lda kiritilgan operatsiyalar, bir xil hisobda debet=kredit, nol summa, g'ayrioddiy dam olish kuni yozuvlarini tekshiradi — bu to'liq qonunchilik muvofiqligi tekshiruvi emas, birlamchi skrining.
- "Kim nima qildi" bo'limi hujjatdagi "Ответственный" rekvizitiga asoslangan — 1C'ning to'liq foydalanuvchi audit jurnali (Журнал регистрации) standart OData orqali olinmaydi.
- Debitor/kreditor qoldig'i hujjat summalaridan taxminiy hisoblangan, rasmiy 4010/6010 qoldig'i emas.</div>
  </div>

  <p class="dm-foot">Manba: 1C OData (Clobus.uz) — oxirgi yangilanish: {esc(data['generated_at'])}. Har kuni soat 08:12 (Toshkent) avtomatik yangilanadi (GitHub: 1c_monitoring repo).</p>
</div>
"""


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from odata_client import output_dir as _output_dir
    base_out = _output_dir()
    with open(os.path.join(base_out, "dashboard_data.json"), encoding="utf-8") as f:
        data = json.load(f)
    html_out = render(data)
    out_path = os.path.join(base_out, "dashboard_index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"Yozildi: {out_path}")


if __name__ == "__main__":
    main()
