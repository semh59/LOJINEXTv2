"""Internationalization constants for Telegram bot UI.

Provides English keys mapping to bilingual messages as per production requirements:
'UI GÖRÜNEN İKİ DİL OLACAK HEM TÜRKÇE HEM İNGİLİZCE'.
"""

# Common
WAITING = "⏳ Seferleriniz hazırlanıyor... / Preparing your trips..."
ERROR_GENERIC = "❌ Bir hata oluştu. Lütfen tekrar deneyin. / An error occurred. Please try again."

# Statement Handler
MSG_NOT_REGISTERED = (
    "⛔ Telegram hesabınız sisteme kayıtlı değil.\nLütfen yöneticinize başvurun.\n\n"
    "Your Telegram account is not registered.\nPlease contact your administrator."
)
MSG_PROMPT_DATE_FROM = (
    "📅 Başlangıç tarihini girin (GG.AA.YYYY):\n<i>Örnek: 01.03.2026</i>\n\n"
    "Enter start date (DD.MM.YYYY):\n<i>Example: 01.03.2026</i>"
)
MSG_PROMPT_DATE_TO = (
    "📅 Bitiş tarihini girin (GG.AA.YYYY):\n<i>Örnek: 31.03.2026</i>\n\n"
    "Enter end date (DD.MM.YYYY):\n<i>Example: 31.03.2026</i>"
)
MSG_INVALID_DATE = (
    "❗ Geçersiz tarih. Lütfen GG.AA.YYYY formatında girin:\n<i>Örnek: 01.03.2026</i>\n\n"
    "Invalid date. Please use DD.MM.YYYY format:\n<i>Example: 01.03.2026</i>"
)
MSG_DATE_RANGE_ORDER = "❗ Bitiş tarihi başlangıç tarihinden önce olamaz. / End date cannot be before start date."
MSG_DATE_RANGE_MAX = "❗ Tarih aralığı en fazla {max_days} gün olabilir. / Date range can be at most {max_days} days."
MSG_NO_TRIPS_FOUND = (
    "ℹ️ {date_from} – {date_to} tarihleri arasında tamamlanmış sefer bulunamadı. / "
    "No completed trips found between {date_from} – {date_to}."
)
MSG_REPORT_CAPTION = (
    "📄 <b>{driver_name}</b> — Sefer Raporu / Trip Report\n📅 {date_from} – {date_to}\n"
    "🚛 Toplam: <b>{count}</b> sefer / trips"
)

# Slip Handler
MSG_SLIP_READING = "⏳ Fiş okunuyor, lütfen bekleyin... / Reading slip, please wait..."
MSG_SLIP_OCR_FAILED = (
    "❌ Fiş okunamadı. Lütfen daha net bir fotoğraf çekerek tekrar deneyin.\n"
    "Ya da metni yazarak /el_ile_gir komutunu kullanın.\n\n"
    "Could not read slip. Please try again with a clearer photo,\n"
    "or use /el_ile_gir to enter manually."
)
MSG_SLIP_READ_SUCCESS = "📋 <b>Fiş bilgileri okundu</b> / Slip data extracted"
MSG_SLIP_CONFIRM = "Bilgiler doğru mu? / Is the information correct?"
MSG_SLIP_INGESTED = (
    "✅ Seferiniz eklendi.\n📄 Fiş No: <b>{trip_no}</b>\nDurum: <b>İnceleme Bekliyor</b>\n\n"
    "Trip added.\nSlip No: <b>{trip_no}</b>\nStatus: Pending Review"
)
MSG_SLIP_INGEST_FALLBACK = (
    "⚠️ Fiş eksik bilgilerle kaydedildi.\n"
    "📄 Fiş No: <b>{trip_no}</b>\n"
    "Yöneticiniz eksik bilgileri tamamlayacak.\n\n"
    "Slip saved with missing info.\n"
    "Slip No: <b>{trip_no}</b>\n"
    "Your manager will complete the details."
)
MSG_SLIP_INGEST_ERROR = "❌ Sefer eklenirken hata oluştu. Lütfen tekrar deneyin. / Error adding trip. Please try again."
MSG_SLIP_PROMPT_EDIT = "✏️ <b>{label}</b> için yeni değeri yazın: / Enter new value for <b>{label}</b>:"
MSG_INVALID_NUMBER = "❗ Geçersiz sayı. Lütfen sadece rakam girin: / Invalid number. Please enter digits only:"
MSG_SLIP_CANCELLED = "❌ Fiş girişi iptal edildi. / Slip entry cancelled."

FIELD_LABELS = {
    "truck_plate": "Araç Plakası / Truck Plate",
    "trailer_plate": "Dorse Plakası / Trailer Plate",
    "origin": "Kalkış Yeri / Origin",
    "destination": "Varış Yeri / Destination",
    "trip_date": "Tarih (GG.AA.YYYY) / Date (DD.MM.YYYY)",
    "trip_time": "Saat (SS:DD) / Time (HH:MM)",
    "tare_kg": "Dara Ağırlık (kg) / Tare Weight",
    "gross_kg": "Brüt Ağırlık (kg) / Gross Weight",
    "net_kg": "Net Ağırlık (kg) / Net Weight",
}

BTN_EDIT = "✏️ Düzenle / Edit"
BTN_CONFIRM = "✅ Onayla / Confirm"
BTN_CANCEL = "❌ İptal / Cancel"
BTN_BACK = "◀️ Geri / Back"
