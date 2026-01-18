from aiogram import Router, types
from aiogram.filters import Command

# Создаем роутер (маршрутизатор)
common_router = Router()

@common_router.message(Command("info"))

    await message.answer(text, parse_mode="Markdown")
