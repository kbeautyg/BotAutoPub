import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not BOT_TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing BOT_TOKEN or SUPABASE_URL or SUPABASE_KEY in environment")

# Initialize Supabase database interface
import supabase_db
supabase_db.db = supabase_db.SupabaseDB(SUPABASE_URL, SUPABASE_KEY)
supabase_db.db.init_schema()

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN, parse_mode=None)
dp = Dispatcher(storage=MemoryStorage())

# Include routers from command modules
# Основные модули
import start
import help
import projects

# Основные функциональные модули
import main_menu
import channels
import create_post_fixed as create_post  # Используем исправленную версию
import scheduled_posts
import settings_improved
import view_post

# Модули для совместимости (для работы с существующими постами)
import edit_post
import delete_post

# Регистрируем роутеры в правильном порядке
# Важно: сначала регистрируем модули с командами, потом с общими обработчиками
dp.include_router(start.router)
dp.include_router(help.router)
dp.include_router(projects.router)
dp.include_router(channels.router)
dp.include_router(create_post.router)  # Исправленная версия
dp.include_router(view_post.router)
dp.include_router(scheduled_posts.router)
dp.include_router(settings_improved.router)
dp.include_router(edit_post.router)
dp.include_router(delete_post.router)
dp.include_router(main_menu.router)  # В конце, чтобы не перехватывал команды

# Import and start the scheduler
import auto_post_fixed as auto_post

async def main():
    print("🚀 Запуск бота...")
    print(f"📊 База данных: {SUPABASE_URL}")
    
    # Start background task for auto-posting
    asyncio.create_task(auto_post.start_scheduler(bot))
    print("⏰ Планировщик запущен")
    
    # Start polling
    print("🔄 Начинаем получение обновлений...")
    
    # Удаляем webhook если он был установлен
    await bot.delete_webhook(drop_pending_updates=True)
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        print(f"❌ Ошибка при запуске бота: {e}")
        # Если ошибка связана с другим экземпляром бота, ждем и пробуем снова
        if "terminated by other getUpdates request" in str(e):
            print("⏳ Ожидание завершения другого экземпляра бота...")
            await asyncio.sleep(5)
            await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
