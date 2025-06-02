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

# Улучшенные модули
import main_menu
import channels
import create_post_improved
import scheduled_posts
import settings_improved

# Старые модули (для совместимости)
import create_post
import edit_post
import list_posts
import delete_post
import settings

# Регистрируем роутеры
dp.include_router(start.router)
dp.include_router(help.router)
dp.include_router(main_menu.router)  # Главное меню
dp.include_router(channels.router)  # Улучшенное управление каналами
dp.include_router(create_post_improved.router)  # Улучшенное создание постов
dp.include_router(scheduled_posts.router)  # Управление отложенными постами
dp.include_router(settings_improved.router)  # Улучшенные настройки
dp.include_router(projects.router)

# Старые модули для совместимости
dp.include_router(create_post.router)
dp.include_router(edit_post.router)
dp.include_router(list_posts.router)
dp.include_router(delete_post.router)
dp.include_router(settings.router)

# Import and start the scheduler
import auto_post

async def main():
    print("🚀 Запуск бота...")
    print(f"📊 База данных: {SUPABASE_URL}")
    
    # Start background task for auto-posting
    asyncio.create_task(auto_post.start_scheduler(bot))
    print("⏰ Планировщик запущен")
    
    # Start polling
    print("🔄 Начинаем получение обновлений...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
