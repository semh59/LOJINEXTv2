"""Slip submission FSM handler: photo → OCR → confirm → ingest."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    PhotoSize,
)

from telegram_service.clients import driver_client, trip_client
from telegram_service.config import settings
from telegram_service.ocr.extractor import extract_slip_fields
from telegram_service.schemas import SlipFields

logger = logging.getLogger(__name__)

router = Router(name="slip")


class SlipStates(StatesGroup):
    confirming = State()          # Waiting for confirm / edit selection
    correcting_field = State()    # Waiting for corrected value of one field


# Human-readable field labels for the correction menu
_FIELD_LABELS: dict[str, str] = {
    "truck_plate": "Araç Plakası",
    "trailer_plate": "Dorse Plakası",
    "origin": "Kalkış Yeri",
    "destination": "Varış Yeri",
    "trip_date": "Tarih (GG.AA.YYYY)",
    "trip_time": "Saat (SS:DD)",
    "tare_kg": "Dara Ağırlık (kg)",
    "gross_kg": "Brüt Ağırlık (kg)",
    "net_kg": "Net Ağırlık (kg)",
}


def _format_confirmation(fields: SlipFields) -> str:
    def v(val: object) -> str:
        return str(val) if val is not None else "—"

    weight_line = ""
    if fields.tare_kg is not None and fields.gross_kg is not None and fields.net_kg is not None:
        weight_line = (
            f"⚖️ Dara: <b>{v(fields.tare_kg)}</b> kg\n"
            f"⚖️ Brüt: <b>{v(fields.gross_kg)}</b> kg\n"
            f"⚖️ Net: <b>{v(fields.net_kg)}</b> kg\n"
        )
    else:
        weight_line = (
            f"⚖️ Dara: <b>{v(fields.tare_kg)}</b> kg\n"
            f"⚖️ Brüt: <b>{v(fields.gross_kg)}</b> kg\n"
            f"⚖️ Net: <b>{v(fields.net_kg)}</b> kg\n"
        )

    confidence_pct = int(fields.ocr_confidence * 100)
    quality = "🟢" if confidence_pct >= 70 else "🟡" if confidence_pct >= 40 else "🔴"

    return (
        f"📋 <b>Fiş bilgileri okundu</b> {quality} ({confidence_pct}%)\n\n"
        f"🚛 Araç plakası: <b>{v(fields.truck_plate)}</b>\n"
        f"🚌 Dorse plakası: <b>{v(fields.trailer_plate)}</b>\n"
        f"📍 Kalkış: <b>{v(fields.origin)}</b>\n"
        f"📍 Varış: <b>{v(fields.destination)}</b>\n"
        f"📅 Tarih: <b>{v(fields.trip_date)}</b>  Saat: <b>{v(fields.trip_time)}</b>\n"
        f"{weight_line}\n"
        "Bilgiler doğru mu?"
    )


def _confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Onayla", callback_data="slip:confirm"),
            InlineKeyboardButton(text="✏️ Düzenle", callback_data="slip:edit"),
        ],
        [InlineKeyboardButton(text="❌ İptal", callback_data="slip:cancel")],
    ])


def _edit_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"slip:field:{key}")]
        for key, label in _FIELD_LABELS.items()
    ]
    buttons.append([InlineKeyboardButton(text="◀️ Geri", callback_data="slip:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(F.photo)
async def handle_photo(message: Message, state: FSMContext) -> None:
    """Entry point: driver sends a photo of the trip slip."""
    if message.from_user is None:
        return

    driver = await driver_client.lookup_by_telegram_id(message.from_user.id)
    if driver is None:
        await message.answer(
            "⛔ Telegram hesabınız sisteme kayıtlı değil.\n"
            "Lütfen yöneticinize başvurun."
        )
        return

    await message.answer("⏳ Fiş okunuyor, lütfen bekleyin...")

    # Download highest-resolution photo
    photo: PhotoSize = message.photo[-1]
    bot = message.bot
    assert bot is not None
    file = await bot.get_file(photo.file_id)
    assert file.file_path is not None
    image_bytes = await bot.download_file(file.file_path)
    assert image_bytes is not None

    try:
        fields = extract_slip_fields(image_bytes.read())
    except Exception:
        logger.exception("OCR failed for driver %s", driver.driver_id)
        await message.answer(
            "❌ Fiş okunamadı. Lütfen daha net bir fotoğraf çekerek tekrar deneyin.\n"
            "Ya da metni yazarak /el_ile_gir komutunu kullanın."
        )
        return

    # Store fields + driver context in FSM state
    await state.set_state(SlipStates.confirming)
    await state.update_data(
        fields=fields.model_dump(),
        driver_id=driver.driver_id,
        message_id=str(message.message_id),
        sent_at_utc=datetime.now(tz=timezone.utc).isoformat(),
    )

    await message.answer(
        _format_confirmation(fields),
        reply_markup=_confirmation_keyboard(),
    )


@router.callback_query(SlipStates.confirming, F.data == "slip:confirm")
async def handle_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    """Driver confirmed the parsed fields — submit to trip-service."""
    await callback.answer()
    data = await state.get_data()
    fields = SlipFields.model_validate(data["fields"])
    driver_id: str = data["driver_id"]
    message_id: str = data["message_id"]
    sent_at_utc: str = data["sent_at_utc"]

    await state.clear()

    assert callback.message is not None

    if fields.ocr_confidence >= settings.ocr_confidence_threshold and _is_full_slip(fields):
        try:
            result = await trip_client.ingest_slip(
                driver_id=driver_id,
                vehicle_id=fields.truck_plate or "UNKNOWN",
                slip_no=message_id,
                reference_key=f"tg:{message_id}",
                fields=fields,
            )
            await callback.message.edit_text(
                f"✅ Seferiniz eklendi.\n"
                f"📄 Fiş No: <b>{result.trip_no}</b>\n"
                f"Durum: <b>İnceleme Bekliyor</b>"
            )
        except Exception:
            logger.exception("Slip ingest failed for driver %s", driver_id)
            await callback.message.edit_text(
                "❌ Sefer eklenirken hata oluştu. Lütfen tekrar deneyin."
            )
    else:
        # Low confidence or missing required fields → fallback
        reason = "OCR confidence below threshold" if fields.ocr_confidence < settings.ocr_confidence_threshold else "Missing required fields"
        try:
            result = await trip_client.ingest_fallback(
                driver_id=driver_id,
                reference_key=f"tg:{message_id}",
                sent_at_utc=sent_at_utc,
                fallback_reason=reason,
            )
            await callback.message.edit_text(
                f"⚠️ Fiş eksik bilgilerle kaydedildi.\n"
                f"📄 Fiş No: <b>{result.trip_no}</b>\n"
                "Yöneticiniz eksik bilgileri tamamlayacak."
            )
        except Exception:
            logger.exception("Fallback ingest failed for driver %s", driver_id)
            await callback.message.edit_text(
                "❌ Sefer eklenirken hata oluştu. Lütfen tekrar deneyin."
            )


@router.callback_query(SlipStates.confirming, F.data == "slip:edit")
async def handle_edit(callback: CallbackQuery, state: FSMContext) -> None:
    """Show field selection keyboard for manual correction."""
    await callback.answer()
    assert callback.message is not None
    await callback.message.edit_reply_markup(reply_markup=_edit_keyboard())


@router.callback_query(SlipStates.confirming, F.data.startswith("slip:field:"))
async def handle_field_select(callback: CallbackQuery, state: FSMContext) -> None:
    """Driver selected a field to correct — ask for new value."""
    await callback.answer()
    field_key = callback.data.split("slip:field:")[1]  # type: ignore[union-attr]
    label = _FIELD_LABELS.get(field_key, field_key)

    await state.set_state(SlipStates.correcting_field)
    await state.update_data(correcting_field=field_key)

    assert callback.message is not None
    await callback.message.answer(f"✏️ <b>{label}</b> için yeni değeri yazın:")


@router.message(SlipStates.correcting_field)
async def handle_field_value(message: Message, state: FSMContext) -> None:
    """Apply the corrected field value and return to confirmation."""
    data = await state.get_data()
    field_key: str = data.get("correcting_field", "")
    raw_value = (message.text or "").strip()

    fields = SlipFields.model_validate(data["fields"])

    # Apply the correction
    if field_key in ("tare_kg", "gross_kg", "net_kg"):
        try:
            int_val = int(raw_value.replace(".", "").replace(",", ""))
            setattr(fields, field_key, int_val)
        except ValueError:
            await message.answer("❗ Geçersiz sayı. Lütfen sadece rakam girin:")
            return
    elif field_key in _FIELD_LABELS:
        setattr(fields, field_key, raw_value if raw_value else None)

    # Recalculate confidence
    fields.ocr_confidence = fields.compute_confidence()

    await state.set_state(SlipStates.confirming)
    await state.update_data(fields=fields.model_dump(), correcting_field=None)

    await message.answer(
        _format_confirmation(fields),
        reply_markup=_confirmation_keyboard(),
    )


@router.callback_query(SlipStates.confirming, F.data == "slip:back")
async def handle_back(callback: CallbackQuery, state: FSMContext) -> None:
    """Return to main confirmation keyboard."""
    await callback.answer()
    assert callback.message is not None
    await callback.message.edit_reply_markup(reply_markup=_confirmation_keyboard())


@router.callback_query(SlipStates.confirming, F.data == "slip:cancel")
async def handle_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel the slip submission."""
    await callback.answer()
    await state.clear()
    assert callback.message is not None
    await callback.message.edit_text("❌ Fiş girişi iptal edildi.")


def _is_full_slip(fields: SlipFields) -> bool:
    """Return True if all fields required for full ingest are present."""
    return all([
        fields.truck_plate,
        fields.origin,
        fields.destination,
        fields.trip_date,
        fields.tare_kg is not None,
        fields.gross_kg is not None,
        fields.net_kg is not None,
    ])
