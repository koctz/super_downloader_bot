from aiogram import Router, types
from aiogram.filters import Command

# Создаем роутер (маршрутизатор)
common_router = Router()

@common_router.message(Command("start"))
async def cmd_start(message: types.Message):
    user_name = message.from_user.first_name
    text = (
        f"👋 Привет, {user_name}!\n\n"
        "Я — универсальный загрузчик видео.\n"
        "Просто отправь мне ссылку, и я попробую скачать видео.\n\n"
        "📥 **Поддерживаю:**\n"
        "• YouTube (Shorts, Video)\n"
        "• TikTok (без водяных знаков)\n"
        "• VK, Instagram Reels\n"
        "• Vimeo, Twitch и многое другое."
    )
    await message.answer(text, parse_mode="Markdown")
