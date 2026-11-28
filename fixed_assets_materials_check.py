"""Asosiy vositalar, materiallar va ishlab chiqarish (WIP) qamrovini tekshirish.

Loyiha instruksiyasining 11-bo'lim (asosiy vositalar), 12-bo'lim (materiallar)
va 13-bo'lim (qurilish ishlab chiqarish) talablariga mos ravishda:
  - Asosiy vositalar (0100-0199 / 0200-0299 schyotlari) bo'yicha rasmiy qoldiq;
  - Materiallar (1000-1090, 2900-2990 schyotlari) bo'yicha rasmiy qoldiq,
    manfiy balans (anomaliya) tekshiruvi;
  - Ishlab chiqarish/tugallanmagan ishlab chiqarish (2000, 2010) qoldig'i.

Agar biror guruh bo'yicha umuman qoldiq topilmasa, bu "xato" sifatida emas,
balki "ma'lumot yo'q / hisobvarag'i bu bazada ishlatilmagan" sifatida alohida
ko'rsatiladi (instruksiya: yetishmayotgan ma'lumotni o'ylab topma, OData orqali
olinmaydigan/mavjud bo'lmagan ma'lumotni alohida ro'yxat qil).
"""
import json
from odata_client import ODataClient, output_dir

FIXED_ASSET_COST_CODES = [
    ("0110", "Yer"), ("0120", "Bino, inshoot"), ("0130", "Mashina va uskunalar"),
    ("0140", "Mebel va ofis anjomlari"), ("0150", "Kompyuter texnikasi"),
    ("0160", "Transport vositalari"), ("0190", "Boshqa ОС"),
]
FIXED_ASSET_DEP_CODES = [
    ("0220", "Amortizatsiya: bino/inshoot"), ("0230", "Amortizatsiya: mashina/uskuna"),
    ("0240", "Amortizatsiya: mebel"), ("0250", "Amortizatsiya: kompyuter"),
    ("0260", "Amortizatsiya: transport"), ("0290", "Amortizatsiya: boshqa"),
]
MATERIAL_CODES = [
    ("1010", "Xom ashyo va materiallar"), ("1030", "Yoqilg'i"),
    ("1040", "Ehtiyot qismlar"), ("1050", "Qurilish materiallari"),
    ("1080", "Inventar va xo'jalik anjomlari"), ("2910", "Omborlardagi tovarlar"),
]
WIP_CODES = [("2010", "Asosiy ishlab chiqarish (TIC)"), ("2000", "Ishlab chiqarish xarajatlari")]


def _account_net(client, code, code_map):
    key = code_map.get(code)
    if not key:
        return None  # hisobvaraq bazada topilmadi
    try:
        rows = client.query(
            "AccountingRegister_Хозрасчетный/Balance",
            select=["ExtDimension1", "ExtDimension1_Type", "СуммаBalanceDr", "СуммаBalanceCr"],
            filter_=f"Account_Key eq guid'{key}'",
        )
    except RuntimeError as e:
        return {"error": str(e)}
    net = sum((r.get("СуммаBalanceDr") or 0.0) - (r.get("СуммаBalanceCr") or 0.0) for r in rows)
    neg_items = sum(1 for r in rows if (r.get("СуммаBalanceDr") or 0.0) - (r.get("СуммаBalanceCr") or 0.0) < -1)
    return {"rows": len(rows), "net": round(net, 2), "negative_items": neg_items}


def _group(client, codes, code_map):
    out = {}
    any_data = False
    for code, label in codes:
        r = _account_net(client, code, code_map)
        out[code] = {"label": label, "result": r}
        if r and r.get("rows"):
            any_data = True
    return out, any_data


def _build_code_map(client):
    """One bulk fetch of the whole chart of accounts, instead of one OData
    request per account code (the 1C server rate-limits at 20 req/min)."""
    cache = client._cache.setdefault("_account_by_code", {})
    rows = client.query("ChartOfAccounts_Хозрасчетный", select=["Ref_Key", "Code"])
    for r in rows:
        if r.get("Code"):
            cache[r["Code"]] = r["Ref_Key"]
    return cache


def run(client):
    code_map = _build_code_map(client)
    fa_cost, fa_cost_has_data = _group(client, FIXED_ASSET_COST_CODES, code_map)
    fa_dep, fa_dep_has_data = _group(client, FIXED_ASSET_DEP_CODES, code_map)
    materials, materials_has_data = _group(client, MATERIAL_CODES, code_map)
    wip, wip_has_data = _group(client, WIP_CODES, code_map)

    total_cost = sum((v["result"] or {}).get("net", 0) for v in fa_cost.values() if v["result"])
    total_dep = sum((v["result"] or {}).get("net", 0) for v in fa_dep.values() if v["result"])
    total_materials = sum((v["result"] or {}).get("net", 0) for v in materials.values() if v["result"])
    total_wip = sum((v["result"] or {}).get("net", 0) for v in wip.values() if v["result"])
    materials_negative = sum((v["result"] or {}).get("negative_items", 0) for v in materials.values() if v["result"])

    is_service_org = getattr(client, "business_type", "construction") == "service"

    flags = []
    if not fa_cost_has_data:
        if is_service_org:
            flags.append({
                "type": "no_fixed_assets_registered",
                "severity": "LOW",
                "note": "0100-0190 (asosiy vositalar) schyotlarida qoldiq topilmadi — bu tashkilot "
                        "xizmat ko'rsatish (qurilish emas) faoliyati bilan shug'ullanadi, shuning uchun "
                        "bu kutilgan holat; faqat ma'lum uchun ko'rsatilmoqda.",
            })
        else:
            flags.append({
                "type": "no_fixed_assets_registered",
                "severity": "MEDIUM",
                "note": "0100-0190 (asosiy vositalar) schyotlarida hech qanday qoldiq topilmadi — "
                        "bazada asosiy vositalar umuman ro'yxatga olinmagan. Qurilish tashkiloti uchun "
                        "bu texnika/uskunalar ijaraga olinganligini yoki ОС hisobi yuritilmayotganini anglatishi mumkin — tasdiqlash kerak.",
            })
    if not materials_has_data:
        if is_service_org:
            flags.append({
                "type": "no_materials_registered",
                "severity": "LOW",
                "note": "1000-1090 / 2910 (materiallar) schyotlarida qoldiq topilmadi — bu tashkilot "
                        "xizmat ko'rsatish faoliyati bilan shug'ullanadi (materiallar sotish/qurilish emas), "
                        "shuning uchun bu kutilgan holat.",
            })
        else:
            flags.append({
                "type": "no_materials_registered",
                "severity": "HIGH",
                "note": "1000-1090 / 2910 (materiallar) schyotlarida hech qanday qoldiq topilmadi — "
                        "bazada materiallar hisobi yuritilmayapti. Qurilish tashkiloti uchun bu jiddiy "
                        "to'liqlik muammosi: materiallar to'g'ridan-to'g'ri xarajatga yozilayotganmi yoki "
                        "boshqa bazada/qog'ozda yuritilayotganmi — tekshirish zarur.",
            })
    if materials_negative:
        flags.append({
            "type": "negative_material_balance",
            "severity": "HIGH",
            "count": materials_negative,
            "note": "Materiallar bo'yicha manfiy (Kt>Dt) qoldiq aniqlandi — ombordan mavjud bo'lmagan "
                    "miqdorda chiqim qilingan bo'lishi mumkin.",
        })
    if not wip_has_data:
        if is_service_org:
            flags.append({
                "type": "no_wip_registered",
                "severity": "LOW",
                "note": "2000/2010 (ishlab chiqarish/TIC) schyotlarida qoldiq topilmadi — bu tashkilot "
                        "xizmat ko'rsatish faoliyati bilan shug'ullanadi, shuning uchun bu kutilgan holat.",
            })
        else:
            flags.append({
                "type": "no_wip_registered",
                "severity": "MEDIUM",
                "note": "2000/2010 (ishlab chiqarish/TIC) schyotlarida qoldiq topilmadi — qurilish "
                        "tashkiloti uchun odatiy emas; buyurtmachi obyektlari bo'yicha xarajatlar boshqa "
                        "usulda (masalan to'g'ridan-to'g'ri xarajat sifatida) yuritilayotgan bo'lishi mumkin.",
            })

    return {
        "organization": client.org_name,
        "note": "Rasmiy qoldiq — AccountingRegister_Хозрасчетный/Balance dan (bugungi holat). "
                "Instruksiya 11/12/13-bo'limlar: asosiy vositalar, materiallar, ishlab chiqarish (TIC).",
        "fixed_assets_cost": fa_cost,
        "fixed_assets_depreciation": fa_dep,
        "fixed_assets_cost_total": round(total_cost, 2),
        "fixed_assets_depreciation_total": round(total_dep, 2),
        "fixed_assets_net_book_value": round(total_cost - total_dep, 2),
        "materials": materials,
        "materials_total": round(total_materials, 2),
        "wip": wip,
        "wip_total": round(total_wip, 2),
        "flags": flags,
    }


def main():
    client = ODataClient()
    result = run(client)
    out_dir = output_dir()
    path = f"{out_dir}/fixed_assets_materials_check.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Yozildi: {path}")
    print(f"ОС qiymati: {result['fixed_assets_cost_total']:,.0f}, amortizatsiya: {result['fixed_assets_depreciation_total']:,.0f}, "
          f"materiallar: {result['materials_total']:,.0f}, TIC: {result['wip_total']:,.0f}")
    print(f"Flags: {len(result['flags'])}")


if __name__ == "__main__":
    main()
