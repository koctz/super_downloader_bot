from aiogram import Bot, Dispatcher
from src.config import conf
from src.handlers.common import common_router
from src.handlers.video import video_router

async def start_bot():
    bot = Bot(token=conf.bot_token, parse_mode="HTML")
    dp = Dispatcher()

    dp.include_router(video_router)
    dp.include_router(common_router)

    await bot.delete_webhook(drop_pending_updates=True)
    print("🤖 Бот запущен и готов к работе!")
    await dp.start_polling(bot)
