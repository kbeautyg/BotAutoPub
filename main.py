import asyncio
import os
from aiogram import Bot, Dispatcher, F
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
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
import main_menu as main_menu  # Используем исправленную версию
import channels
import scheduled_posts as create  # Используем исправленную версию
import list_posts  # Импортируем list_posts для работы со списками
import settings_improved
import view_post

# Улучшенные модули
import edit_post  # Используем новый улучшенный редактор

# Модули для совместимости (для работы с существующими постами)
import delete_post

# Регистрируем роутеры в правильном порядке
# Важно: сначала регистрируем модули с командами, потом с общими обработчиками
dp.include_router(start.router)
dp.include_router(help.router)
dp.include_router(projects.router)
dp.include_router(channels.router)
dp.include_router(create.router)  # Улучшенная версия создания постов
dp.include_router(view_post.router)
dp.include_router(list_posts.router)  # Добавляем router для списка постов
dp.include_router(settings_improved.router)
dp.include_router(edit_post.router)  # Новый улучшенный редактор
dp.include_router(delete_post.router)
dp.include_router(main_menu.router)  # В конце, чтобы не перехватывал команды

# Глобальные обработчики callback'ов для управления постами
@dp.callback_query(F.data.startswith("post_edit_cmd:"))
async def callback_edit_post_global(callback: CallbackQuery):
    """Глобальный обработчик команды редактирования поста"""
    post_id = int(callback.data.split(":", 1)[1])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать пост", callback_data=f"post_edit_direct:{post_id}")],
        [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_full_view:{post_id}")],
        [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")]
    ])
    
    # Отправляем сообщение о запуске редактирования
    await callback.message.edit_text(
        f"✏️ **Редактирование поста #{post_id}**\n\n"
        f"Выберите действие:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    await callback.answer()

@dp.callback_query(F.data.startswith("post_publish_cmd:"))
async def callback_publish_post_global(callback: CallbackQuery):
    """Глобальный обработчик команды публикации поста"""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    
    user_id = callback.from_user.id
    post_id = int(callback.data.split(":", 1)[1])
    
    post = supabase_db.db.get_post(post_id)
    if not post:
        await callback.answer("Пост не найден!")
        return
    
    if post.get('published'):
        await callback.answer("Пост уже опубликован!")
        return
    
    # Проверяем доступ
    if not supabase_db.db.is_user_in_project(user_id, post.get("project_id", -1)):
        await callback.answer("У вас нет доступа к этому посту!")
        return
    
    # Обновляем время публикации на текущее
    now = datetime.now(ZoneInfo("UTC"))
    supabase_db.db.update_post(post_id, {
        "publish_time": now,
        "draft": False
    })
    
    # Создаем клавиатуру с действиями
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_full_view:{post_id}")],
        [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(
        f"🚀 **Пост #{post_id} поставлен в очередь на публикацию**\n\n"
        f"Пост будет опубликован в ближайшее время.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer("Пост поставлен в очередь на публикацию!")

@dp.callback_query(F.data.startswith("post_reschedule_cmd:"))
async def callback_reschedule_post_global(callback: CallbackQuery):
    """Глобальный обработчик команды переноса поста"""
    post_id = int(callback.data.split(":", 1)[1])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_full_view:{post_id}")],
        [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(
        f"📅 **Перенос поста #{post_id}**\n\n"
        f"Используйте команду `/reschedule {post_id} YYYY-MM-DD HH:MM` для переноса поста.\n\n"
        f"Пример: `/reschedule {post_id} 2024-12-25 15:30`",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("post_delete_cmd:"))
async def callback_delete_post_global(callback: CallbackQuery):
    """Глобальный обработчик команды удаления поста"""
    post_id = int(callback.data.split(":", 1)[1])
    
    # Подтверждение удаления
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"post_delete_confirm:{post_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"post_view:{post_id}")
        ]
    ])
    
    await callback.message.edit_text(
        f"🗑 **Удаление поста #{post_id}**\n\n"
        f"Вы уверены, что хотите удалить этот пост?\n"
        f"Это действие нельзя отменить.",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("post_delete_confirm:"))
async def callback_confirm_delete_post_global(callback: CallbackQuery):
    """Глобальный обработчик подтверждения удаления поста"""
    user_id = callback.from_user.id
    post_id = int(callback.data.split(":", 1)[1])
    
    # Проверяем доступ
    post = supabase_db.db.get_post(post_id)
    if not post or not supabase_db.db.is_user_in_project(user_id, post.get("project_id", -1)):
        await callback.answer("У вас нет доступа к этому посту!")
        return
    
    try:
        supabase_db.db.delete_post(post_id)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        
        await callback.message.edit_text(
            f"✅ **Пост #{post_id} удален**\n\n"
            f"Пост успешно удален из базы данных.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    except Exception as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await callback.message.edit_text(
            f"❌ **Ошибка удаления**\n\n"
            f"Не удалось удалить пост: {str(e)}",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    
    await callback.answer()

@dp.callback_query(F.data.startswith("post_full_view:"))
async def callback_full_view_post_global(callback: CallbackQuery):
    """Глобальный обработчик полного просмотра поста"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    
    post_id = int(callback.data.split(":", 1)[1])
    post = supabase_db.db.get_post(post_id)
    
    if not post:
        await callback.answer("Пост не найден!")
        return
    
    # Проверяем доступ
    if not supabase_db.db.is_user_in_project(user_id, post.get("project_id", -1)):
        await callback.answer("У вас нет доступа к этому посту!")
        return
    
    # Импортируем функции для просмотра
    from view_post import send_post_preview, format_time_for_user
    
    # Отправляем полный превью поста
    await send_post_preview(callback.message, post)
    
    # Отправляем информацию с кнопками
    channel = supabase_db.db.get_channel(post['channel_id'])
    channel_name = channel['name'] if channel else 'Неизвестный канал'
    
    info_text = f"👀 **Полный просмотр поста #{post_id}**\n\n"
    info_text += f"📺 **Канал:** {channel_name}\n"
    
    if post.get('published'):
        info_text += "✅ **Статус:** Опубликован\n"
    elif post.get('draft'):
        info_text += "📝 **Статус:** Черновик\n"
    elif post.get('publish_time'):
        formatted_time = format_time_for_user(post['publish_time'], user)
        user_tz = user.get('timezone', 'UTC')
        info_text += f"⏰ **Запланировано:** {formatted_time}\n"
    
    # Создаем клавиатуру действий
    buttons = []
    
    if not post.get('published'):
        buttons.append([
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"post_edit_direct:{post_id}"),
            InlineKeyboardButton(text="🚀 Опубликовать", callback_data=f"post_publish_cmd:{post_id}")
        ])
        buttons.append([
            InlineKeyboardButton(text="📅 Перенести", callback_data=f"post_reschedule_cmd:{post_id}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"post_delete_cmd:{post_id}")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.answer(info_text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

# Обработчик для callback кнопки "Создать пост" из меню
@dp.callback_query(F.data == "menu_create_post_direct")
async def callback_create_post_direct(callback: CallbackQuery):
    """Прямое создание поста через callback из меню"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Пошаговое создание", callback_data="create_step_by_step")],
        [InlineKeyboardButton(text="🚀 Быстрое создание", callback_data="create_quick_help")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(
        "📝 **Создание нового поста**\n\n"
        "Выберите способ создания поста:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data == "create_step_by_step")
async def callback_create_step_by_step(callback: CallbackQuery):
    """Пошаговое создание поста"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(
        "📝 **Пошаговое создание поста**\n\n"
        "Используйте команду `/create` для создания поста с пошаговым мастером.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer("Используйте команду /create")

@dp.callback_query(F.data == "create_quick_help")
async def callback_create_quick_help(callback: CallbackQuery):
    """Помощь по быстрому созданию"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Пошаговое создание", callback_data="create_step_by_step")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(
        "🚀 **Быстрое создание поста**\n\n"
        "Используйте команду `/quickpost` для быстрого создания:\n\n"
        "**Формат:** `/quickpost <канал> <время> <текст>`\n\n"
        "**Примеры:**\n"
        "• `/quickpost @channel now Текст поста`\n"
        "• `/quickpost 1 draft Черновик поста`\n"
        "• `/quickpost 2 2024-12-25_15:30 Запланированный пост`\n\n"
        "**Параметры:**\n"
        "• Канал: @username, ID или номер в списке\n"
        "• Время: now, draft или YYYY-MM-DD_HH:MM\n"
        "• Текст: содержимое поста",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()

# Обработчик для меню постов
@dp.callback_query(F.data == "posts_menu")
async def callback_posts_menu_global(callback: CallbackQuery):
    """Глобальный обработчик меню постов"""
    from list_posts import callback_posts_menu
    await callback_posts_menu(callback)

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
