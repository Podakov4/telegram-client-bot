from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from handlers.common import client_has_active_access, client_has_trial_used
from keyboards.reply import main_reply_keyboard
from services.client_access import get_client_by_telegram_id

router = Router()


@router.message(Command("menu"))
@router.message(F.text == "Меню")
async def show_menu(message: Message):
    client = await get_client_by_telegram_id(str(message.from_user.id))

    await message.answer(
        "<b>Главное меню Freeth</b>\n\n"
        "Основные разделы вынесены ниже. Откройте «Мой доступ», чтобы управлять подпиской, "
        "подключением, устройствами и входом в приложение.",
        reply_markup=main_reply_keyboard(
            message.from_user.id,
            has_active_access=client_has_active_access(client),
            trial_used=client_has_trial_used(client),
        ),
    )
