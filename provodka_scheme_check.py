"""1C provodka skill (anthropic-skills:1c-provodka-audit) bo'yicha tekshiruv.

Operatsiya turi (hujjat, Recorder_Type) bo'yicha guruhlab, har bir guruh
ichida Debet/Kredit schyot guruhi (2 xonali kod) juftligining CHASTOTASINI
hisoblaydi va shu guruh ichida KAM uchraydigan (statistik noodatiy) juftlarni
"ko'rib chiqish tavsiya etiladi" sifatida belgilaydi.

MUHIM: bu qat'iy "to'g'ri/noto'g'ri" sxema solishtiruvi EMAS — chunki har bir
tashkilotning hisob siyosati va subkonto tuzilishi turlicha (masalan 2500 —
umumishlab chiqarish xarajatlari, 4200 — xodimga berilgan avans — ikkalasi
ham qonuniy, lekin standart o'quv jadvalida yo'q edi). Shu sababli natija
statistik chastotaga asoslangan: bir hujjat turi ichida 95%+ hollarda
ishlatiladigan schyot juftligi "odatiy", juda kam (masalan <1% yoki ≤2 marta)
uchraydigan juftlik "noodatiy — tekshirish tavsiya etiladi" deb belgilanadi.
Bu HECH QACHON "xato" sifatida taqdim etilmaydi — faqat e'tibor qaratish
uchun signal. Rasmiy auditorlik xulosasi emas, o'z-o'zini tekshirish vositasi.
"""
import collections
import os
import sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from odata_client import ODataClient, odata_date, days_ago, output_dir

LOOKBACK_DAYS = 180
RARE_THRESHOLD_COUNT = 2     # within a doc type, a pair seen this many times or fewer...
RARE_THRESHOLD_SHARE = 0.01  # ...or less than 1% of that doc type's lines, is "unusual"

DOC_LABELS = {
    "ПоступлениеТоваровУслуг": "Tovar/xizmat qabul qilish",
    "НачислениеЗарплаты": "Ish haqi hisoblash",
    "СписаниеСРасчетногоСчета": "Bank — chiqim",
    "ТребованиеНакладная": "Material sarflash (talabnoma-nakladnoy)",
    "ПоступлениеНаРасчетныйСчет": "Bank — kirim",
    "РеализацияТоваровУслуг": "Realizatsiya (tushum)",
    "ПеремещениеТоваров": "Omborlar orasida ko'chirish",
    "КорректировкаДолга": "Qarzni to'g'rilash",
    "ПередачаОС": "Asosiy vositani topshirish",
    "РегламентнаяОперация": "Regламент operatsiya (oy yopish)",
    "ОперацияБух": "Qo'lda kiritilgan operatsiya",
}


def _doc_short(recorder_type):
    # "StandardODATA.Document_ПоступлениеТоваровУслуг" -> "ПоступлениеТоваровУслуг"
    return (recorder_type or "").split("Document_")[-1]


def run(client: ODataClient, lookback_days=LOOKBACK_DAYS):
    since = odata_date(days_ago(lookback_days))
    rows = client.query(
        "AccountingRegister_Хозрасчетный_RecordType",
        select=["Recorder", "Recorder_Type", "Period", "AccountDr_Key", "AccountCr_Key", "Сумма"],
        filter_=f"Period ge {since} and Active eq true",
    )

    acct_map = client.get_catalog_map("ChartOfAccounts_Хозрасчетный", select=("Ref_Key", "Code"))

    def code_of(key):
        if not key or key == "00000000-0000-0000-0000-000000000000":
            return None
        row = acct_map.get(key)
        return (row.get("Code") or "")[:2] if row else None

    doc_type_totals = collections.Counter()
    pair_counts_by_type = collections.defaultdict(collections.Counter)
    sample_by_pair = {}

    for r in rows:
        short = _doc_short(r.get("Recorder_Type"))
        doc_type_totals[short] += 1
        dr2 = code_of(r.get("AccountDr_Key"))
        cr2 = code_of(r.get("AccountCr_Key"))
        if dr2 is None or cr2 is None:
            continue
        key = (short, dr2, cr2)
        pair_counts_by_type[short][(dr2, cr2)] += 1
        if key not in sample_by_pair:
            sample_by_pair[key] = {
                "recorder": r.get("Recorder"), "period": r.get("Period"), "amount": r.get("Сумма"),
            }

    unusual_by_type = {}
    total_unusual = 0
    for short, counter in pair_counts_by_type.items():
        type_total = sum(counter.values())
        unusual = []
        for (dr2, cr2), n in counter.items():
            if n <= RARE_THRESHOLD_COUNT or (n / type_total) < RARE_THRESHOLD_SHARE:
                sample = sample_by_pair.get((short, dr2, cr2), {})
                unusual.append({
                    "dr_group": dr2, "cr_group": cr2, "count": n,
                    "share_pct": round(100 * n / type_total, 3),
                    "example": sample,
                })
        if unusual:
            unusual.sort(key=lambda x: x["count"])
            unusual_by_type[short] = {
                "label": DOC_LABELS.get(short, short),
                "type_total": type_total,
                "dominant_pairs": [
                    {"dr_group": d, "cr_group": c, "count": n}
                    for (d, c), n in counter.most_common(5) if n > RARE_THRESHOLD_COUNT and (n / type_total) >= RARE_THRESHOLD_SHARE
                ],
                "unusual_pairs": unusual,
            }
            total_unusual += len(unusual)

    return {
        "organization": client.org_name,
        "note": "anthropic-skills:1c-provodka-audit bo'yicha — har bir hujjat turi ichida "
                "Debet/Kredit schyot guruhi juftliklarining chastotasi hisoblangan. Kam uchraydigan "
                "(statistik noodatiy) juftliklar \"tekshirish tavsiya etiladi\" deb belgilangan — bu "
                "XATO degani EMAS, faqat shu tashkilotning odatiy amaliyotidan farq qiladigan, e'tibor "
                "talab qiluvchi yozuv. Qat'iy to'g'ri/noto'g'ri sxema solishtiruvi emas, chunki har bir "
                "tashkilotning hisob siyosati va subkonto tuzilishi individual. O'z-o'zini tekshirish "
                "vositasi, rasmiy auditorlik xulosasi emas.",
        "lookback_days": lookback_days,
        "doc_type_totals": dict(doc_type_totals),
        "total_unusual_pairs": total_unusual,
        "unusual_by_type": unusual_by_type,
    }


def main():
    client = ODataClient()
    result = run(client)
    out_dir = output_dir()
    import json
    path = f"{out_dir}/provodka_scheme_check.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Yozildi: {path}")
    print(f"Hujjat turlari: {result['doc_type_totals']}")
    print(f"Noodatiy juftliklar: {result['total_unusual_pairs']}")


if __name__ == "__main__":
    main()
