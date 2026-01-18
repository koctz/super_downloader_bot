from aiogram import Bot, Dispatcher
from src.config import conf
from src.db import init_db
from src.handlers.common import common_router
from src.handlers.video import video_router, pyro_app  # Добавили импорт pyro_app

async def start_bot():
    init_db()
    
    # --- ШАГ 2: Запуск Pyrogram клиента ---
    print("🚀 Запуск MTProto клиента (для больших файлов)...")
    await pyro_app.start()
    
    # Инициализация aiogram бота
    bot = Bot(token=conf.bot_token)
    
    # Инициализация диспетчера
    dp = Dispatcher()
    
    # Регистрируем роутеры
    dp.include_router(common_router)
    dp.include_router(video_router)
    
    try:
        # Удаляем вебхуки и запускаем поллинг
        await bot.delete_webhook(drop_pending_updates=True)
        print("🤖 Бот запущен и готов к работе!")
        await dp.start_polling(bot)
    finally:
        # --- ВАЖНО: Останавливаем клиент при выключении бота ---
        print("🛑 Остановка клиента...")
        await pyro_app.stop()
        # Также закрываем сессию бота
        await bot.session.close()
