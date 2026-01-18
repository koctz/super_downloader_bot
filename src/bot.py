from aiogram import Bot, Dispatcher
from src.config import conf
from src.db import init_db
from src.handlers.common import common_router
from src.handlers.video import video_router

async def start_bot():
    init_db()
    # Инициализация бота
    bot = Bot(token=conf.bot_token, parse_mode="HTML")
    
    # Инициализация диспетчера
    dp = Dispatcher()
    
    # Регистрируем роутеры
    # Порядок важен: специфичные обработчики лучше ставить раньше, общие - позже
    dp.include_router(common_router)
    dp.include_router(video_router)

    
    # Удаляем вебхуки (если были) и запускаем поллинг
    await bot.delete_webhook(drop_pending_updates=True)
    print("🤖 Бот запущен и готов к работе!")
    await dp.start_polling(bot)
