#!/usr/bin/env python3
"""
render_slides.py — output/dashboard_data.json asosida kunlik "1C kunlik
hisobot — ALMIRA SR" Slides deck'ining slayd fayllarini (HTML) qayta
generatsiya qiladi.

Natija: output/slides/*.html (cover, summary, pending-errors,
monthclose-cash, settlements, closing) — bular keyin scheduled task
tomonidan Artifact publish_files orqali Slides artifactga yuboriladi.

Bu skript fayllarni DISKKA yozadi, lekin o'zi hech narsani publish qilmaydi
(chunki buning uchun Artifact MCP tool kerak, u skriptdan emas, agentning
o'zidan chaqiriladi).
"""
import html
import json
import os
import sys
import datetime as dt

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


def render_cover(data):
    today = dt.datetime.fromisoformat(data["generated_at"]).strftime("%d.%m.%Y")
    return f"""<section id="cover" class="dark-bg" data-transition="fade">
<div class="eyebrow">1C kunlik monitoring</div>
<h1 style="font-size:120px; line-height:1.05; max-width:1400px;">ALMIRA SR MCHJ</h1>
<p style="font-size:40px; color:#D7DEEF; margin-top:32px; max-width:1300px;">Kunlik hisobot — {esc(today)}</p>
<p class="source">Manba: 1C OData (Clobus.uz) • Har kuni avtomatik yangilanadi</p>
</section>
"""


def render_summary(data):
    s = data["sections"]
    pw = s["5_pending_work"]["total_pending"]
    ed = s["6_error_documents"]["total_errors"]
    mc = s["3_month_close_check"]["missing_closures"]
    ct = s["8_cash_in_transit_check"]
    cash_balance = ct["monthly_trend_57xx"][-1]["running_balance"] if ct.get("monthly_trend_57xx") else None
    cash_class = "bad" if (cash_balance or 0) < 0 else "ok"
    pw_class = "bad" if pw else "ok"
    ed_class = "bad" if ed else "ok"
    mc_class = "bad" if mc else "ok"
    return f"""<section id="summary" data-transition="fade">
<div class="eyebrow">Umumiy holat</div>
<h2 style="font-size:64px;">Bugungi asosiy ko'rsatkichlar</h2>
<div class="kpi-row">
  <div class="kpi-card"><div class="kpi-label">Qolib ketgan ishlar</div><div class="kpi-value {pw_class}">{fmt_num(pw)}</div></div>
  <div class="kpi-card"><div class="kpi-label">Xatolik aniqlangan hujjatlar</div><div class="kpi-value {ed_class}">{fmt_num(ed)}</div></div>
  <div class="kpi-card"><div class="kpi-label">Yopilmagan oylar</div><div class="kpi-value {mc_class}">{fmt_num(len(mc))}</div></div>
  <div class="kpi-card"><div class="kpi-label">57xx qoldig'i</div><div class="kpi-value {cash_class}" style="font-size:52px;">{fmt_num(cash_balance)}</div></div>
</div>
<p class="source">Manba: build_dashboard_data.py, {esc(data['generated_at'])}</p>
</section>
"""


def render_pending_errors(data):
    s = data["sections"]
    pw_items = s["5_pending_work"]["items"]
    mc_missing = s["3_month_close_check"]["missing_closures"]
    rows = []
    for it in pw_items[:6]:
        if it["type"] == "unposted_document":
            rows.append(f"<div class=\"list-item\"><span class=\"list-tag\">Provedeniyasiz</span><span>{esc(it['doc_type'])} №{esc(it['number'])} ({esc(it['date'])})</span></div>")
        else:
            rows.append(f"<div class=\"list-item\"><span class=\"list-tag\">Oy yopish</span><span>{esc(it['month'])} oyi yopilmagan ({it['regulated_docs_found']} ta hujjat)</span></div>")
    if not rows:
        rows.append("<div class=\"list-item\"><span class=\"list-tag\">Holat</span><span>Qolib ketgan ish topilmadi.</span></div>")
    return f"""<section id="pending-errors" data-transition="fade">
<div class="eyebrow">Qolib ketgan ishlar va xatoliklar</div>
<h2 style="font-size:60px;">Diqqat talab qiladigan hujjatlar</h2>
<div class="list-block">
{chr(10).join(rows)}
</div>
<p class="source">Manba: check_1c.py, month_close_check.py, error_documents.py</p>
</section>
"""


def render_monthclose_cash(data):
    ct = data["sections"]["8_cash_in_transit_check"]
    trend = ct.get("monthly_trend_57xx", [])[-3:]
    diag = {d["month"]: d for d in ct.get("diagnosis_5720", [])}
    rows = []
    for t in trend:
        d = diag.get(t["month"], {})
        bad = " bad-text" if t["net_change"] < 0 else ""
        rows.append(
            f"<tr><td>{esc(t['month'])}</td><td class=\"num\">{fmt_num(d.get('retail_sales_postings_dt'))}</td>"
            f"<td class=\"num\">{fmt_num(d.get('bank_receipts_kt'))}</td>"
            f"<td class=\"num{bad}\">{fmt_num(t['net_change'])}</td>"
            f"<td class=\"num{bad}\">{fmt_num(t['running_balance'])}</td></tr>"
        )
    return f"""<section id="monthclose-cash" data-transition="fade">
<div class="eyebrow">Oy yopish &amp; 57xx trendi</div>
<h2 style="font-size:56px;">"Yo'ldagi pul mablag'lari" (5720) trendi</h2>
<table>
<tr><th>Oy</th><th>Savdo hisoboti (Dt)</th><th>Bank tushumi (Kt)</th><th>Farq</th><th>Qoldiq</th></tr>
{chr(10).join(rows)}
</table>
<p class="source">Manba: cash_in_transit_check.py, AccountingRegister_Хозрасчетный</p>
</section>
"""


def render_settlements(data):
    s = data["sections"]["7_settlements_check"]
    act = data["sections"]["4_activity_report"]
    mc_items = []
    for label, sec in s["missing_contracts"].items():
        if "error" not in sec:
            mc_items.append((label, sec["missing_contract_count"], sec["checked_count"]))
    top_user = act["by_user"][0]["user"] if act["by_user"] else "—"
    cards = "".join(
        f"<div class=\"kpi-card\"><div class=\"kpi-label\">Shartnomasiz {esc(l)}</div><div class=\"kpi-value\" style=\"font-size:56px;\">{m} / {c}</div></div>"
        for l, m, c in mc_items[:2]
    )
    return f"""<section id="settlements" data-transition="fade">
<div class="eyebrow">Hisob-kitoblar &amp; xodimlar</div>
<h2 style="font-size:56px;">Shartnoma va debitor/kreditor (taxminiy)</h2>
<div class="kpi-row" style="margin-top:32px;">
{cards}
  <div class="kpi-card"><div class="kpi-label">Faol xodim</div><div class="kpi-value" style="font-size:44px;">{esc(top_user)}</div></div>
</div>
<p style="font-size:24px; color:var(--muted); margin-top:40px;">Debitor/kreditor qoldig'i hujjat summalaridan TAXMINIY hisoblangan — rasmiy 4010/6010 qoldig'i emas.</p>
<p class="source">Manba: settlements_check.py, activity_report.py</p>
</section>
"""


def render_closing(data):
    s = data["sections"]
    items = []
    if s["3_month_close_check"]["missing_closures"]:
        items.append("Yopilmagan oylarni yopish: " + ", ".join(s["3_month_close_check"]["missing_closures"]))
    pw_items = s["5_pending_work"]["items"]
    for it in pw_items[:2]:
        if it["type"] == "unposted_document":
            items.append(f"{it['doc_type']} №{it['number']} ni ko'rib chiqish")
    if not items:
        items.append("Bugun ustuvor ochiq vazifa topilmadi.")
    rows = "".join(
        f"<div class=\"list-item\" style=\"border-color:rgba(255,255,255,0.14);\"><span class=\"list-tag\" style=\"color:#E8B47A;\">{i+1}</span><span>{esc(t)}</span></div>"
        for i, t in enumerate(items[:4])
    )
    return f"""<section id="closing" class="dark-bg" data-transition="fade">
<div class="eyebrow">Keyingi qadamlar</div>
<h2 style="font-size:56px; max-width:1400px;">Bugungi ustuvor vazifalar</h2>
<div class="list-block">
{rows}
</div>
<p class="source">Manba: 1c_monitoring (GitHub) — har kuni soat 08:12 (Toshkent) avtomatik yangilanadi</p>
</section>
"""


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "output", "dashboard_data.json"), encoding="utf-8") as f:
        data = json.load(f)

    out_dir = os.path.join(base, "output", "slides")
    os.makedirs(out_dir, exist_ok=True)

    files = {
        "cover.html": render_cover(data),
        "summary.html": render_summary(data),
        "pending-errors.html": render_pending_errors(data),
        "monthclose-cash.html": render_monthclose_cash(data),
        "settlements.html": render_settlements(data),
        "closing.html": render_closing(data),
    }
    for name, content in files.items():
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Yozildi: {path}")


if __name__ == "__main__":
    main()
