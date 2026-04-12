from datetime import datetime

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import Client
from keyboards.reply import main_reply_keyboard

router = Router()

REFERRAL_START_PREFIX = "ref_"
REFERRAL_BONUS_DAYS = 20


def client_has_trial_used(client: Client | None) -> bool:
    return bool(client and client.notes and "trial_used=true" in client.notes)


def client_has_active_access(client: Client | None) -> bool:
    if client is None:
        return False

    if client.is_active and client.subscription_link:
        return True

    if client.paid_until and client.paid_until > datetime.utcnow() and client.subscription_link:
        return True

    return False


def keyboard_for_client(client: Client | None, user_id: int):
    return main_reply_keyboard(
        user_id,
        has_active_access=client_has_active_access(client),
        trial_used=client_has_trial_used(client),
    )


def extract_start_argument(message_text: str | None) -> str | None:
    if not message_text:
        return None

    parts = message_text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return None

    return parts[1].strip() or None


def extract_referral_code(message_text: str | None) -> str | None:
    start_arg = extract_start_argument(message_text)
    if not start_arg:
        return None

    if not start_arg.startswith(REFERRAL_START_PREFIX):
        return None

    code = start_arg[len(REFERRAL_START_PREFIX):].strip()
    return code or None


@router.message(CommandStart())
async def cmd_start(message: Message):
    telegram_id = str(message.from_user.id)
    full_name = message.from_user.full_name
    referral_code = extract_referral_code(message.text)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == telegram_id)
        )
        client = result.scalar_one_or_none()

        is_new_user = client is None
        referrer = None

        if referral_code:
            referrer_result = await session.execute(
                select(Client).where(Client.referral_code == referral_code)
            )
            possible_referrer = referrer_result.scalar_one_or_none()
            if possible_referrer and possible_referrer.telegram_id != telegram_id:
                referrer = possible_referrer

        if client is None:
            now = datetime.utcnow()
            client = Client(
                telegram_id=telegram_id,
                full_name=full_name,
                is_active=False,
                is_paid=False,
                created_at=now,
                updated_at=now,
                referrer_client_id=referrer.id if referrer else None,
                referral_joined_at=now if referrer else None,
            )
            session.add(client)
            await session.commit()
        elif client.full_name != full_name:
            client.full_name = full_name
            client.updated_at = datetime.utcnow()
            await session.commit()

    referral_note = ""
    if is_new_user and client.referrer_client_id:
        referral_note = (
            "\n\n"
            "Вы пришли по приглашению друга.\n"
            f"После вашей первой успешной оплаты пригласившему автоматически начислится <b>+{REFERRAL_BONUS_DAYS} дней</b> подписки."
        )

    if is_new_user:
        await message.answer(
            f"Здравствуйте, {full_name}!\n\n"
            "Добро пожаловать в <b>Freeth</b>.\n\n"
            "Здесь вы можете:\n"
            "• получить пробный доступ\n"
            "• подключить телефон или компьютер\n"
            "• управлять устройствами и подпиской\n"
            "• войти в приложение через Telegram\n"
            "• приглашать друзей по реферальной ссылке\n\n"
            "Чтобы начать:\n"
            "1. Откройте <b>«Мой доступ»</b>\n"
            "2. При необходимости активируйте пробный период\n"
            "3. Для входа в приложение выберите <b>«Войти в приложение»</b>\n"
            "4. Для реферальной программы откройте <b>«Рефералы»</b>\n\n"
            "Если вы открыли бот после удаления переписки — просто продолжайте через кнопки ниже."
            f"{referral_note}",
            reply_markup=keyboard_for_client(client, message.from_user.id),
        )
        return

    if client_has_active_access(client):
        text = (
            f"С возвращением, {full_name}!\n\n"
            "Откройте <b>«Мой доступ»</b>, чтобы:\n"
            "• посмотреть статус доступа\n"
            "• открыть ссылки для подключения\n"
            "• управлять устройствами\n"
            "• войти в приложение через Telegram\n\n"
            "Для входа в приложение используйте кнопку <b>«Войти в приложение»</b>."
        )
    else:
        text = (
            f"С возвращением, {full_name}!\n\n"
            "Сейчас вы можете:\n"
            "• открыть <b>«Мой доступ»</b>\n"
            "• активировать пробный период\n"
            "• продлить доступ\n"
            "• после активации войти в приложение\n"
            "• открыть <b>«Рефералы»</b> и пригласить друзей\n\n"
            "Если вы открыли бот после удаления переписки, просто используйте кнопки ниже."
        )

    await message.answer(
        text,
        reply_markup=keyboard_for_client(client, message.from_user.id),
    )
