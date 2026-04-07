import logging
import re
from datetime import date

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, Message

from telegram_service.clients import driver_client, trip_client
from telegram_service.config import settings
from telegram_service.observability import (
    BOT_COMMANDS_TOTAL,
    BOT_PDF_GENERATED_TOTAL,
    get_standard_labels,
)
from telegram_service.pdf.generator import generate_statement_pdf

logger = logging.getLogger(__name__)

router = Router(name="statement")

# Accept DD.MM.YYYY or DD/MM/YYYY
_DATE_RE = re.compile(r"^(\d{2})[./](\d{2})[./](\d{4})$")


class StatementStates(StatesGroup):
    waiting_date_from = State()
    waiting_date_to = State()


def _parse_date(text: str) -> date | None:
    m = _DATE_RE.match(text.strip())
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


@router.message(Command("seferlerim"))
async def cmd_seferlerim(message: Message, state: FSMContext) -> None:
    """Entry point: driver requests their trip statement."""
    BOT_COMMANDS_TOTAL.labels(command="/seferlerim", **get_standard_labels()).inc()
    if message.from_user is None:
        return

    driver = await driver_client.lookup_by_telegram_id(message.from_user.id)
    if driver is None:
        await message.answer("⛔ Telegram hesabınız sisteme kayıtlı değil.\nLütfen yöneticinize başvurun.")
        return

    await state.set_state(StatementStates.waiting_date_from)
    await state.update_data(driver_id=driver.driver_id, driver_name=driver.full_name)
    await message.answer("📅 Başlangıç tarihini girin:\n<i>Örnek: 01.03.2026</i>")


@router.message(StatementStates.waiting_date_from)
async def handle_date_from(message: Message, state: FSMContext) -> None:
    date_from = _parse_date(message.text or "")
    if date_from is None:
        await message.answer("❗ Geçersiz tarih. Lütfen GG.AA.YYYY formatında girin:\n<i>Örnek: 01.03.2026</i>")
        return

    await state.update_data(date_from=date_from.isoformat())
    await state.set_state(StatementStates.waiting_date_to)
    await message.answer("📅 Bitiş tarihini girin:\n<i>Örnek: 31.03.2026</i>")


@router.message(StatementStates.waiting_date_to)
async def handle_date_to(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    date_from = date.fromisoformat(data["date_from"])
    driver_id: str = data["driver_id"]
    driver_name: str = data["driver_name"]

    date_to = _parse_date(message.text or "")
    if date_to is None:
        await message.answer("❗ Geçersiz tarih. Lütfen GG.AA.YYYY formatında girin:\n<i>Örnek: 31.03.2026</i>")
        return

    if date_to < date_from:
        await message.answer("❗ Bitiş tarihi başlangıç tarihinden önce olamaz.")
        return

    if (date_to - date_from).days >= settings.max_date_range_days:
        await message.answer(f"❗ Tarih aralığı en fazla {settings.max_date_range_days} gün olabilir.")
        return

    await state.clear()
    await message.answer("⏳ Seferleriniz hazırlanıyor...")

    try:
        rows = await trip_client.get_driver_statement(
            driver_id=driver_id,
            date_from=date_from,
            date_to=date_to,
        )
    except Exception:
        logger.exception("Statement fetch failed for driver %s", driver_id)
        await message.answer("❌ Seferler alınırken hata oluştu. Lütfen tekrar deneyin.")
        return

    if not rows:
        await message.answer(
            f"ℹ️ <b>{date_from.strftime('%d.%m.%Y')}</b> – <b>{date_to.strftime('%d.%m.%Y')}</b> "
            "tarihleri arasında tamamlanmış sefer bulunamadı."
        )
        return

    try:
        pdf_bytes = generate_statement_pdf(
            rows=rows,
            driver_name=driver_name,
            date_from=date_from,
            date_to=date_to,
        )
        BOT_PDF_GENERATED_TOTAL.labels(**get_standard_labels()).inc()
    except Exception:
        logger.exception("PDF generation failed for driver %s", driver_id)
        await message.answer("❌ PDF oluşturulurken hata oluştu. Lütfen tekrar deneyin.")
        return

    filename = f"seferler_{date_from.strftime('%d%m%Y')}_{date_to.strftime('%d%m%Y')}.pdf"
    await message.answer_document(
        document=BufferedInputFile(pdf_bytes, filename=filename),
        caption=(
            f"📄 <b>{driver_name}</b> — Sefer Raporu\n"
            f"📅 {date_from.strftime('%d.%m.%Y')} – {date_to.strftime('%d.%m.%Y')}\n"
            f"🚛 Toplam: <b>{len(rows)}</b> sefer"
        ),
    )
