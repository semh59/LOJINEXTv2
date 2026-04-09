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

from telegram_service.clients import driver_client, fleet_client, trip_client
from telegram_service.config import settings
from telegram_service.i18n import (
    BTN_BACK,
    BTN_CANCEL,
    BTN_CONFIRM,
    BTN_EDIT,
    FIELD_LABELS,
    MSG_INVALID_NUMBER,
    MSG_NOT_REGISTERED,
    MSG_SLIP_CANCELLED,
    MSG_SLIP_CONFIRM,
    MSG_SLIP_INGEST_ERROR,
    MSG_SLIP_INGEST_FALLBACK,
    MSG_SLIP_INGESTED,
    MSG_SLIP_OCR_FAILED,
    MSG_SLIP_PROMPT_EDIT,
    MSG_SLIP_READ_SUCCESS,
    MSG_SLIP_READING,
)
from telegram_service.observability import BOT_OCR_REQUESTS_TOTAL, get_standard_labels
from telegram_service.ocr.extractor import extract_slip_fields
from telegram_service.schemas import SlipFields

logger = logging.getLogger(__name__)

router = Router(name="slip")


class SlipStates(StatesGroup):
    confirming = State()  # Waiting for confirm / edit selection
    correcting_field = State()  # Waiting for corrected value of one field


# Human-readable field labels for the correction menu are now in i18n.FIELD_LABELS


def _format_confirmation(fields: SlipFields) -> str:
    def v(val: object) -> str:
        return str(val) if val is not None else "—"

    weight_line = ""

    def _format_weight(label_key: str, val: object) -> str:
        label = FIELD_LABELS[label_key].split(" / ")[0]  # Use Turkish label for weight line summary
        return f"⚖️ {label}: <b>{v(val)}</b> kg\n"

    weight_line = (
        _format_weight("tare_kg", fields.tare_kg)
        + _format_weight("gross_kg", fields.gross_kg)
        + _format_weight("net_kg", fields.net_kg)
    )

    confidence_pct = int(fields.ocr_confidence * 100)
    quality = "🟢" if confidence_pct >= 70 else "🟡" if confidence_pct >= 40 else "🔴"

    return (
        f"{MSG_SLIP_READ_SUCCESS} {quality} ({confidence_pct}%)\n\n"
        f"🚛 {FIELD_LABELS['truck_plate']}: <b>{v(fields.truck_plate)}</b>\n"
        f"🚌 {FIELD_LABELS['trailer_plate']}: <b>{v(fields.trailer_plate)}</b>\n"
        f"📍 {FIELD_LABELS['origin']}: <b>{v(fields.origin)}</b>\n"
        f"📍 {FIELD_LABELS['destination']}: <b>{v(fields.destination)}</b>\n"
        f"📅 {FIELD_LABELS['trip_date']}: <b>{v(fields.trip_date)}</b>  "
        f"Saat: <b>{v(fields.trip_time)}</b>\n"
        f"{weight_line}\n"
        f"{MSG_SLIP_CONFIRM}"
    )


def _confirmation_keyboard() -> InlineKeyboardMarkup:
    """Build the main confirmation keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=BTN_CONFIRM, callback_data="slip:confirm"),
                InlineKeyboardButton(text=BTN_EDIT, callback_data="slip:edit"),
            ],
            [InlineKeyboardButton(text=BTN_CANCEL, callback_data="slip:cancel")],
        ]
    )


def _edit_keyboard() -> InlineKeyboardMarkup:
    """Build the field selection keyboard."""
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"slip:field:{key}")] for key, label in FIELD_LABELS.items()
    ]
    buttons.append([InlineKeyboardButton(text=BTN_BACK, callback_data="slip:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(F.photo)
async def handle_photo(message: Message, state: FSMContext) -> None:
    """Entry point: driver sends a photo of the trip slip."""
    if message.from_user is None:
        return

    driver = await driver_client.lookup_by_telegram_id(message.from_user.id)
    if driver is None:
        await message.answer(MSG_NOT_REGISTERED)
        return

    await message.answer(MSG_SLIP_READING)

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
        # Record OCR Success
        BOT_OCR_REQUESTS_TOTAL.labels(status="success", **get_standard_labels()).inc()
    except Exception:
        # Record OCR Failure
        BOT_OCR_REQUESTS_TOTAL.labels(status="failure", **get_standard_labels()).inc()
        logger.exception("OCR failed for driver %s", driver.driver_id)
        await message.answer(MSG_SLIP_OCR_FAILED)
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
    if not data or "fields" not in data or "driver_id" not in data:
        await callback.message.edit_text(MSG_SLIP_CANCELLED)
        await state.clear()
        return

    fields = SlipFields.model_validate(data["fields"])
    driver_id: str = data["driver_id"]
    message_id: str = data["message_id"]
    sent_at_utc: str = data["sent_at_utc"]

    # --- BUG-1 & H-2 FIX: Resolve Plates to ULIDs ---
    vehicle_id = await fleet_client.lookup_vehicle_by_plate(fields.truck_plate)
    if not vehicle_id:
        logger.warning("Vehicle not found for plate: %s", fields.truck_plate)
        await callback.message.edit_text(f"❌ Araç bulunamadı: {fields.truck_plate}\nLütfen plakayı kontrol edin.")
        return

    trailer_id = None
    if fields.trailer_plate:
        trailer_id = await fleet_client.lookup_trailer_by_plate(fields.trailer_plate)
        if not trailer_id:
            logger.warning("Trailer not found for plate: %s", fields.trailer_plate)
            # We treat trailer as optional if it exists in OCR but not in DB?
            # Per H-2 audit, it should be resolved to ULID.
            await callback.message.edit_text(
                f"❌ Dorse bulunamadı: {fields.trailer_plate}\nLütfen plakayı kontrol edin."
            )
            return

    await state.clear()

    assert callback.message is not None

    if fields.ocr_confidence >= settings.ocr_confidence_threshold and _is_full_slip(fields):
        try:
            result = await trip_client.ingest_slip(
                driver_id=driver_id,
                vehicle_id=vehicle_id,  # Now a ULID
                trailer_id=trailer_id,  # Now a ULID
                slip_no=message_id,
                reference_key=f"tg:{message_id}",
                fields=fields,
            )
            await callback.message.edit_text(MSG_SLIP_INGESTED.format(trip_no=result.trip_no))
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", 500)
            logger.exception("Slip ingest failed for driver %s (status %s)", driver_id, status_code)

            error_msg = MSG_SLIP_INGEST_ERROR
            if status_code == 409:
                error_msg = "⚠️ Bu fiş zaten sisteme girilmiş. / This slip is already in the system."
            elif status_code == 422:
                error_msg = (
                    "❌ Veri doğrulama hatası. Lütfen yöneticiye başvurun. / Validation error. Please contact admin."
                )
            elif status_code == 404:
                error_msg = (
                    "❌ Kayıt bulunamadı. Lütfen araç ve dorse plakalarını kontrol edin. / "
                    "Resource not found. Please check plates."
                )

            await callback.message.edit_text(error_msg)
    else:
        # Low confidence or missing required fields → fallback
        reason = (
            "OCR confidence below threshold"
            if fields.ocr_confidence < settings.ocr_confidence_threshold
            else "Missing required fields"
        )
        try:
            result = await trip_client.ingest_fallback(
                driver_id=driver_id,
                reference_key=f"tg:{message_id}",
                sent_at_utc=sent_at_utc,
                fallback_reason=reason,
            )
            await callback.message.edit_text(MSG_SLIP_INGEST_FALLBACK.format(trip_no=result.trip_no))
        except Exception:
            logger.exception("Fallback ingest failed for driver %s", driver_id)
            await callback.message.edit_text(MSG_SLIP_INGEST_ERROR)


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
    label = FIELD_LABELS.get(field_key, field_key)

    await state.set_state(SlipStates.correcting_field)
    await state.update_data(correcting_field=field_key)

    assert callback.message is not None
    await callback.message.answer(MSG_SLIP_PROMPT_EDIT.format(label=label))


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
            await message.answer(MSG_INVALID_NUMBER)
            return
    elif field_key in FIELD_LABELS:
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
    await callback.message.edit_text(MSG_SLIP_CANCELLED)


def _is_full_slip(fields: SlipFields) -> bool:
    """Return True if all fields required for full ingest are present."""
    return all(
        [
            fields.truck_plate,
            fields.origin,
            fields.destination,
            fields.trip_date,
            fields.tare_kg is not None,
            fields.gross_kg is not None,
            fields.net_kg is not None,
        ]
    )
