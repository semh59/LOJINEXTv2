"""Common handlers: /start, /yardim, unrecognized messages."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from telegram_service.observability import BOT_COMMANDS_TOTAL, get_standard_labels

router = Router(name="common")

_WELCOME = (
    "👋 Merhaba! <b>Lojinext Sürücü Botu</b>'na hoş geldiniz.\n\n"
    "📋 <b>Kullanılabilir komutlar:</b>\n"
    "📸 <b>Fotoğraf gönder</b> — Sefer fişini göndererek sefer ekleyin\n"
    "/seferlerim — Sefer raporunuzu PDF olarak alın\n"
    "/yardim — Yardım menüsü\n\n"
    "<i>Fiş göndermek için: Fişin fotoğrafını çekip bu sohbete gönderin.</i>"
)

_HELP = (
    "ℹ️ <b>Yardım</b>\n\n"
    "<b>Sefer Fişi Göndermek:</b>\n"
    "1. Fişin net bir fotoğrafını çekin\n"
    "2. Fotoğrafı bu sohbete gönderin\n"
    "3. Bot okunan bilgileri gösterir — doğrulayın veya düzeltin\n"
    "4. 'Onayla' tuşuna basın\n\n"
    "<b>Sefer Raporu:</b>\n"
    "1. /seferlerim komutunu gönderin\n"
    "2. Başlangıç ve bitiş tarihlerini girin (GG.AA.YYYY)\n"
    "3. PDF raporunuz otomatik gönderilir\n\n"
    "⚠️ Tarih aralığı en fazla 31 gün olabilir.\n\n"
    "❓ Sorun yaşıyorsanız yöneticinize başvurun."
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    BOT_COMMANDS_TOTAL.labels(command="/start", **get_standard_labels()).inc()
    await message.answer(_WELCOME)


@router.message(Command("yardim"))
async def cmd_yardim(message: Message) -> None:
    BOT_COMMANDS_TOTAL.labels(command="/yardim", **get_standard_labels()).inc()
    await message.answer(_HELP)


@router.message()
async def handle_unknown(message: Message) -> None:
    """Catch-all for unrecognized messages."""
    await message.answer(
        "❓ Anlamadım.\nSefer fişi eklemek için fotoğraf gönderin.\n/yardim yazarak komutları görebilirsiniz."
    )
