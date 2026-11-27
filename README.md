# 1C kunlik monitoring — ALMIRA SR

Izzatbekning 1C:Buxgalteriya 3.0 (Clobus.uz) bazasini OData orqali kunlik
tekshirish uchun skriptlar to'plami. Scheduled task ishga tushganda bu repo
clone qilinadi va skriptlar ishga tushiriladi — shunday qilib skriptlar
ephemeral konteyner bilan birga yo'qolib qolmaydi.

## Sozlash

1. `config.example.json` dan nusxa oling va `config.json` nomi bilan saqlang:
   ```bash
   cp config.example.json config.json
   ```
2. `config.json` ichida haqiqiy OData manzili, foydalanuvchi va parolni kiriting.
   **`config.json` git'ga commit qilinmaydi** (`.gitignore`da).

## Skriptlar

| Skript | Vazifasi |
|---|---|
| `odata_client.py` | Umumiy OData ulanish yordamchisi (barcha skriptlar foydalanadi) |
| `check_1c.py` | So'nggi 14 kunda provedeniya qilinmagan / o'chirishga belgilangan hujjatlar (kassa, bank, realizatsiya, EHF, ish haqi, avans) |
| `provodka_check.py` | Birlamchi provodka skrining: qo'lda kiritilgan operatsiyalar, Dt=Kt bir xil schyot, nol summa, dam olish kunidagi qo'lda yozuvlar |
| `month_close_check.py` | Oy yopilishini (Document_РегламентнаяОперация) tekshirish |
| `activity_report.py` | "Kim nima qildi" — taxminiy, hujjatdagi "Ответственный" maydoni asosida |
| `pending_work.py` | "Qolib ketgan ishlar" — provedeniyasiz hujjatlar + yopilmagan oylar |
| `error_documents.py` | "Xatolik aniqlangan hujjatlar" — provodka flaglari + o'chirishga belgilangan hujjatlar |
| `settlements_check.py` | Bank to'lov maqsadi, shartnoma ko'rsatilmagan hujjatlar, 4010/6010/4310/6310 bo'yicha RASMIY debitor/kreditor qoldig'i |
| `cash_in_transit_check.py` | 57xx guruhi (jumladan 5720) oylik qoldiq trendi va diagnostikasi |
| `payroll_settlement_check.py` | Xodimlar bo'yicha ish haqi hisob-kitoblari — 6710/4210 bo'yicha RASMIY qoldiq, xatolik flaglari |
| `build_dashboard_data.py` | Barcha tekshiruvlarni ishga tushirib, Dashboard artifact uchun bitta JSON snapshot hosil qiladi |

Har bir skript mustaqil ishga tushadi va natijani `output/*.json` ga yozadi
(bu papka ham git'ga commit qilinmaydi — har safar qayta generatsiya qilinadi).

## Bir nechta tashkilot (ko'p baza) bilan ishlash

Barcha skriptlar bitta tashkilotga "qattiq bog'langan" emas — ular
`config.json`dagi ma'lumotlarga va schyot kodlariga (Code, masalan "4010")
qarab ishlaydi, GUID'larga emas. **Muhim: har bir 1C bazasida bir xil
schyot kodi (masalan 4010) boshqacha ichki Ref_Key (GUID) ga ega bo'ladi —
shuning uchun hisob-kitob va ish haqi tekshiruvlari schyot GUID'ini har
safar `client.account_key(code)` orqali shu bazadan qayta so'raydi, hech
qachon boshqa tashkilotdan olingan GUID ishlatilmaydi.**

Boshqa tashkilot uchun alohida config fayl yarating (masalan
`config_luxyr.json`, bu ham gitignore qilingan) va skriptlarni shu
muhit o'zgaruvchilari bilan ishga tushiring:

```bash
ODATA_CONFIG_PATH=/path/to/config_luxyr.json \
OUTPUT_DIR=/path/to/output_luxyr \
python3 build_dashboard_data.py
```

`ODATA_CONFIG_PATH` qaysi tashkilotga ulanishni, `OUTPUT_DIR` esa natija
qayerga yozilishini belgilaydi — shu tufayli bir nechta tashkilotning
natijalari bir-birini bosib yubormaydi. Shu ikki o'zgaruvchi bilan
`render_dashboard_html.py` va `render_slides.py` ham ishlaydi.

## Eslatma

`settlements_check.py`dagi debitor/kreditor qoldig'i
`AccountingRegister_Хозрасчетный/Balance` virtual jadvalidan (4010, 6010,
4310, 6310 schyotlari, kontragent bo'yicha) o'qiladi — bu RASMIY 1C
qoldig'i, hujjat summalaridan taxmin emas (to'g'ri OData sintaksisi:
`EntityName/Balance`, `/Turnovers`, `/BalanceAndTurnovers` — pastki chiziq
bilan `EntityName_Balance` emas). `provodka_check.py` yuridik xulosa
emas — faqat birlamchi skrining.
