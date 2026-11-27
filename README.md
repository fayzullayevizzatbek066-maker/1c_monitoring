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
| `settlements_check.py` | Bank to'lov maqsadi, shartnoma ko'rsatilmagan hujjatlar, taxminiy debitor/kreditor |
| `cash_in_transit_check.py` | 57xx guruhi (jumladan 5720) oylik qoldiq trendi va diagnostikasi |
| `build_dashboard_data.py` | Barcha tekshiruvlarni ishga tushirib, Dashboard artifact uchun bitta JSON snapshot hosil qiladi |

Har bir skript mustaqil ishga tushadi va natijani `output/*.json` ga yozadi
(bu papka ham git'ga commit qilinmaydi — har safar qayta generatsiya qilinadi).

## Eslatma

`settlements_check.py`dagi debitor/kreditor qoldig'i hujjat summalaridan
TAXMINIY hisoblangan — rasmiy 4010/6010 qoldig'i emas, chunki standart
OData interfeysi hisob-kitob registrining Остатки virtual jadvalini
ochmaydi. `provodka_check.py` ham yuridik xulosa emas — faqat birlamchi
skrining.
