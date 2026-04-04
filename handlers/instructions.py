from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from utils.happ_shared import (
    device_selection_keyboard,
    instruction_action_keyboard,
    instructions_menu_text,
    platform_instruction_text,
    support_contact_keyboard,
    support_intro_text,
)

router = Router()


def instructions_keyboard():
    return device_selection_keyboard()


@router.message(F.text == "Как подключить")
@router.message(F.text == "Инструкции")
async def instructions_menu(message: Message):
    await message.answer(
        instructions_menu_text(),
        reply_markup=device_selection_keyboard(),
    )


@router.callback_query(F.data == "instr_ios")
async def instr_ios(callback: CallbackQuery):
    await callback.message.answer(
        platform_instruction_text("ios"),
        reply_markup=instruction_action_keyboard("ios"),
    )
    await callback.answer()


@router.callback_query(F.data == "instr_android")
async def instr_android(callback: CallbackQuery):
    await callback.message.answer(
        platform_instruction_text("android"),
        reply_markup=instruction_action_keyboard("android"),
    )
    await callback.answer()


@router.callback_query(F.data == "instr_windows")
async def instr_windows(callback: CallbackQuery):
    await callback.message.answer(
        platform_instruction_text("windows"),
        reply_markup=instruction_action_keyboard("windows"),
    )
    await callback.answer()


@router.callback_query(F.data == "instr_mac")
async def instr_mac(callback: CallbackQuery):
    await callback.message.answer(
        platform_instruction_text("macos"),
        reply_markup=instruction_action_keyboard("macos"),
    )
    await callback.answer()


@router.callback_query(F.data == "open_instructions_from_support")
async def open_instructions_from_support(callback: CallbackQuery):
    await callback.message.answer(
        instructions_menu_text(),
        reply_markup=device_selection_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "open_support_from_instructions")
async def open_support_from_instructions(callback: CallbackQuery):
    await callback.message.answer(
        support_intro_text(),
        reply_markup=support_contact_keyboard(),
    )
    await callback.answer()
