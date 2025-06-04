from aiogram import Router, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
import supabase_db

router = Router()

def get_main_menu_keyboard(lang: str = "ru"):
    """Главное меню бота"""
    if lang == "ru":
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Создать пост", callback_data="menu_create_post"),
                InlineKeyboardButton(text="📋 Мои посты", callback_data="menu_posts")
            ],
            [
                InlineKeyboardButton(text="📺 Каналы", callback_data="menu_channels"),
                InlineKeyboardButton(text="📁 Проекты", callback_data="menu_projects")
            ],
            [
                InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu_settings"),
                InlineKeyboardButton(text="❓ Помощь", callback_data="menu_help")
            ]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Create Post", callback_data="menu_create_post"),
                InlineKeyboardButton(text="📋 My Posts", callback_data="menu_posts")
            ],
            [
                InlineKeyboardButton(text="📺 Channels", callback_data="menu_channels"),
                InlineKeyboardButton(text="📁 Projects", callback_data="menu_projects")
            ],
            [
                InlineKeyboardButton(text="⚙️ Settings", callback_data="menu_settings"),
                InlineKeyboardButton(text="❓ Help", callback_data="menu_help")
            ]
        ])

def get_welcome_text(user: dict, lang: str = "ru") -> str:
    """Получить приветственный текст"""
    if lang == "ru":
        text = "🤖 **Добро пожаловать в бот управления каналами!**\n\n"
        text += "Этот бот поможет вам:\n"
        text += "• 📝 Создавать и планировать посты\n"
        text += "• 📺 Управлять каналами Telegram\n"
        text += "• ⏰ Автоматически публиковать контент\n"
        text += "• 📊 Отслеживать статистику\n\n"
        
        if user.get('current_project'):
            project = supabase_db.db.get_project(user['current_project'])
            if project:
                text += f"📁 **Текущий проект:** {project['name']}\n"
        
        # Быстрая статистика
        if user.get('current_project'):
            channels = supabase_db.db.list_channels(project_id=user['current_project'])
            posts = supabase_db.db.list_posts(project_id=user['current_project'], only_pending=True)
            text += f"📺 Каналов: {len(channels)} | ⏰ Запланированных постов: {len(posts)}\n\n"
        
        text += "Выберите действие из меню ниже:"
    else:
        text = "🤖 **Welcome to the Channel Management Bot!**\n\n"
        text += "This bot will help you:\n"
        text += "• 📝 Create and schedule posts\n"
        text += "• 📺 Manage Telegram channels\n"
        text += "• ⏰ Automatically publish content\n"
        text += "• 📊 Track statistics\n\n"
        
        if user.get('current_project'):
            project = supabase_db.db.get_project(user['current_project'])
            if project:
                text += f"📁 **Current project:** {project['name']}\n"
        
        # Quick stats
        if user.get('current_project'):
            channels = supabase_db.db.list_channels(project_id=user['current_project'])
            posts = supabase_db.db.list_posts(project_id=user['current_project'], only_pending=True)
            text += f"📺 Channels: {len(channels)} | ⏰ Scheduled posts: {len(posts)}\n\n"
        
        text += "Choose an action from the menu below:"
    
    return text

@router.message(Command("menu"))
async def cmd_main_menu(message: Message, state: FSMContext):
    """Показать главное меню"""
    user_id = message.from_user.id
    user = supabase_db.db.ensure_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    text = get_welcome_text(user, lang)
    keyboard = get_main_menu_keyboard(lang)
    
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data == "main_menu")
async def callback_main_menu(callback: CallbackQuery):
    """Вернуться в главное меню"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    text = get_welcome_text(user, lang)
    keyboard = get_main_menu_keyboard(lang)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "menu_create_post")
async def callback_create_post(callback: CallbackQuery, state: FSMContext):
    """Создать пост - сразу запускаем процесс"""
    from create import cmd_create_post
    # Создаем фейковое сообщение с командой для переиспользования логики
    fake_message = callback.message
    fake_message.text = "/create"
    fake_message.from_user = callback.from_user
    await cmd_create_post(fake_message, state)
    await callback.answer()

@router.callback_query(F.data == "menu_create_post_direct")
async def callback_create_post_direct(callback: CallbackQuery, state: FSMContext):
    """Создать пост напрямую из списка"""
    from create import cmd_create_post
    fake_message = callback.message
    fake_message.text = "/create"
    fake_message.from_user = callback.from_user
    await cmd_create_post(fake_message, state)
    await callback.answer()

@router.callback_query(F.data == "menu_posts")
async def callback_posts_menu(callback: CallbackQuery):
    """Меню постов"""
    # Импортируем функцию из scheduled_posts
    from scheduled_posts import callback_posts_menu as posts_menu_handler
    await posts_menu_handler(callback)

@router.callback_query(F.data == "menu_channels")
async def callback_channels_menu(callback: CallbackQuery):
    """Меню каналов"""
    # Импортируем функцию из channels
    from channels import callback_channels_menu as channels_menu_handler
    await channels_menu_handler(callback)

@router.callback_query(F.data == "menu_projects")
async def callback_projects_menu(callback: CallbackQuery):
    """Меню проектов"""
    await callback.message.answer("Используйте команду /project для управления проектами.")
    await callback.answer()

@router.callback_query(F.data == "menu_settings")
async def callback_settings_menu(callback: CallbackQuery):
    """Меню настроек"""
    # Импортируем функцию из settings_improved
    from settings_improved import callback_settings_menu as settings_menu_handler
    await settings_menu_handler(callback)

@router.callback_query(F.data == "menu_help")
async def callback_help_menu(callback: CallbackQuery):
    """Меню помощи"""
    await callback.message.answer("Используйте команду /help для получения справки.")
    await callback.answer()

# Команды быстрого доступа
@router.message(Command("quick"))
async def cmd_quick_actions(message: Message, state: FSMContext):
    """Быстрые действия"""
    user_id = message.from_user.id
    user = supabase_db.db.ensure_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Быстрый пост", callback_data="quick_post")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="quick_stats")],
        [InlineKeyboardButton(text="⏰ Ближайшие посты", callback_data="quick_upcoming")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    text = "⚡ **Быстрые действия**\n\nВыберите действие:"
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data == "quick_post")
async def callback_quick_post(callback: CallbackQuery):
    """Быстрое создание поста"""
    await callback.message.answer(
        "🚀 **Быстрое создание поста**\n\n"
        "Отправьте текст поста, и он будет опубликован в первом доступном канале через 5 минут.\n\n"
        "Или используйте /create для полного контроля над постом.",
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "quick_stats")
async def callback_quick_stats(callback: CallbackQuery):
    """Быстрая статистика"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    project_id = user.get("current_project")
    
    if not project_id:
        await callback.message.edit_text("❌ Нет активного проекта.")
        await callback.answer()
        return
    
    channels = supabase_db.db.list_channels(project_id=project_id)
    all_posts = supabase_db.db.list_posts(project_id=project_id, only_pending=False)
    scheduled = [p for p in all_posts if not p.get('published') and not p.get('draft') and p.get('publish_time')]
    drafts = [p for p in all_posts if p.get('draft')]
    published = [p for p in all_posts if p.get('published')]
    
    text = (
        f"📊 **Быстрая статистика**\n\n"
        f"📺 Каналов: {len(channels)}\n"
        f"⏰ Запланированных: {len(scheduled)}\n"
        f"📝 Черновиков: {len(drafts)}\n"
        f"✅ Опубликованных: {len(published)}\n"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Подробнее", callback_data="menu_posts")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "quick_upcoming")
async def callback_quick_upcoming(callback: CallbackQuery):
    """Ближайшие посты"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    project_id = user.get("current_project")
    
    if not project_id:
        await callback.message.edit_text("❌ Нет активного проекта.")
        await callback.answer()
        return
    
    posts = supabase_db.db.get_scheduled_posts_by_channel(project_id)
    
    if not posts:
        text = "⏰ **Ближайшие посты**\n\n❌ Нет запланированных постов."
    else:
        text = "⏰ **Ближайшие посты**\n\n"
        for i, post in enumerate(posts[:5], 1):  # Показываем первые 5
            try:
                from datetime import datetime
                from zoneinfo import ZoneInfo
                
                utc_time = datetime.fromisoformat(post['publish_time'].replace('Z', '+00:00'))
                if user.get('timezone'):
                    user_tz = ZoneInfo(user['timezone'])
                    local_time = utc_time.astimezone(user_tz)
                    time_str = local_time.strftime('%m-%d %H:%M')
                else:
                    time_str = utc_time.strftime('%m-%d %H:%M')
                
                channel_name = post.get('channels', {}).get('name', 'Канал')
                post_text = post.get('text', 'Без текста')[:25]
                text += f"{i}. **{time_str}** - {channel_name}\n   {post_text}...\n\n"
            except:
                text += f"{i}. Пост #{post['id']}\n\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Все посты", callback_data="posts_scheduled")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()
