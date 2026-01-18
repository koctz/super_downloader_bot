from aiogram import Bot, Dispatcher
from src.config import conf
from src.db import init_db
from src.handlers.common import common_router
from src.handlers.video import video_router, tele_client # Импортируем tele_client

async def start_bot():
    init_db()
    
    # --- ЗАПУСК TELETHON ---
    print("🚀 Запуск Telethon клиента...")
    await tele_client.start(bot_token=conf.bot_token)
    
    bot = Bot(token=conf.bot_token)
    dp = Dispatcher()
    
    dp.include_router(common_router)
    dp.include_router(video_router)
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("🤖 Бот запущен и готов к работе!")
        await dp.start_polling(bot)
    finally:
        print("🛑 Остановка клиента...")
        await tele_client.disconnect() # Отключаем Telethon
        await bot.session.close()
