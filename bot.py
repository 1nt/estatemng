import asyncio
import logging
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.enums.parse_mode import ParseMode
from aiogram.client.default import DefaultBotProperties

from handlers import router
from database import create_db_and_tables
import database as db

# Загружаем переменные окружения из .env файла
load_dotenv()

# Включаем логирование
logging.basicConfig(level=logging.INFO)

# Основная асинхронная функция
async def main():
    # Проверяем и создаем таблицы в БД при запуске
    await create_db_and_tables()

    # Инициализация бота и диспетчера
    bot = Bot(
        token=os.getenv("BOT_TOKEN"),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Подключаем роутер с хэндлерами
    dp.include_router(router)
    
    # Удаляем вебхук, если он был установлен ранее
    await bot.delete_webhook(drop_pending_updates=True)
    # Проставим роли модераторов из .env, если их еще нет
    moderators = os.getenv("MODERATORS", "")
    if moderators:
        for username in [u.strip().lstrip('@') for u in moderators.split(',') if u.strip()]:
            # Пометим известных пользователей (если уже писали боту) как manager
            try:
                await db.set_user_role_by_username(username, 'manager')
            except Exception:
                pass

    # Запускаем бота
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен вручную")