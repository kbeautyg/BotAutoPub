from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
import supabase_db
from __init__ import TEXTS

router = Router()

def get_main_menu_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Получить клавиатуру главного меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Создать пост", callback_data="menu_create_post"),
            InlineKeyboardButton(text="📋 Мои посты", callback_data="posts_menu")
        ],
        [
            InlineKeyboardButton(text="📺 Каналы", callback_data="menu_channels"),
            InlineKeyboardButton(text="📅 Расписание", callback_data="menu_scheduled")
        ],
        [
            InlineKeyboardButton(text="📁 Проекты", callback_data="menu_projects"),
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu_settings")
        ],
        [
            InlineKeyboardButton(text="📖 Помощь", callback_data="menu_help")
        ]
    ])

@router.message(Command("menu"))
async def cmd_menu(message: Message):
    """Показать главное меню"""
    user_id = message.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Проверяем наличие проекта
    project_id = user.get("current_project") if user else None
    
    if not project_id:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📁 Создать проект", callback_data="menu_projects")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu_settings")],
            [InlineKeyboardButton(text="📖 Помощь", callback_data="menu_help")]
        ])
        
        await message.answer(
            "🏠 **Главное меню**\n\n"
            "❗ У вас нет активного проекта. Создайте проект для начала работы.",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    else:
        keyboard = get_main_menu_keyboard(lang)
        
        await message.answer(
            "🏠 **Главное меню**\n\n"
            "Выберите действие:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

@router.callback_query(F.data == "main_menu")
async def callback_main_menu(callback: CallbackQuery):
    """Возврат в главное меню"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Проверяем наличие проекта
    project_id = user.get("current_project") if user else None
    
    if not project_id:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📁 Создать проект", callback_data="menu_projects")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu_settings")],
            [InlineKeyboardButton(text="📖 Помощь", callback_data="menu_help")]
        ])
        
        await callback.message.edit_text(
            "🏠 **Главное меню**\n\n"
            "❗ У вас нет активного проекта. Создайте проект для начала работы.",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    else:
        keyboard = get_main_menu_keyboard(lang)
        
        await callback.message.edit_text(
            "🏠 **Главное меню**\n\n"
            "Выберите действие:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    await callback.answer()

@router.callback_query(F.data == "menu_create_post")
async def callback_create_post(callback: CallbackQuery, state: FSMContext):
    """Создать пост - сразу запускаем процесс"""
    from create import cmd_create_post
    # Создаем сообщение для переиспользования логики
    await cmd_create_post(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "menu_create_post_direct")
async def callback_create_post_direct(callback: CallbackQuery, state: FSMContext):
    """Создать пост напрямую из списка"""
    from create import cmd_create_post
    await cmd_create_post(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "menu_scheduled")
async def callback_scheduled_menu(callback: CallbackQuery):
    """Меню расписания - показываем запланированные посты"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    project_id = user.get("current_project") if user else None
    
    if not project_id:
        await callback.answer("Нет активного проекта")
        return
    
    # Получаем запланированные посты
    posts = supabase_db.db.get_scheduled_posts_by_channel(project_id)
    
    if not posts:
        text = "📅 **Расписание постов**\n\n❌ Нет запланированных постов."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Создать пост", callback_data="menu_create_post_direct")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
    else:
        text = f"📅 **Расписание постов**\n\nЗапланировано: {len(posts)} постов\n\n"
        
        # Показываем первые 5 постов
        for i, post in enumerate(posts[:5], 1):
            channel_info = post.get("channels", {})
            channel_name = channel_info.get("name", "Неизвестный канал")
            post_text = post.get("text", "Без текста")[:30]
            text += f"{i}. #{post['id']} • {channel_name}\n   {post_text}...\n"
        
        if len(posts) > 5:
            text += f"\n_...и еще {len(posts) - 5} постов_"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Все посты", callback_data="posts_menu")],
            [InlineKeyboardButton(text="📝 Создать пост", callback_data="menu_create_post_direct")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "menu_channels")
async def callback_channels_menu(callback: CallbackQuery, state: FSMContext):
    """Меню каналов - открываем напрямую"""
    from channels import show_channels_menu
    await show_channels_menu(callback.message, callback.from_user.id)
    await callback.answer()

@router.callback_query(F.data == "menu_projects")
async def callback_projects_menu(callback: CallbackQuery, state: FSMContext):
    """Меню проектов - открываем напрямую"""
    from projects import show_projects_menu
    await show_projects_menu(callback.message, callback.from_user.id)
    await callback.answer()

@router.callback_query(F.data == "menu_settings")
async def callback_settings_menu(callback: CallbackQuery, state: FSMContext):
    """Меню настроек - открываем напрямую"""
    from settings_improved import show_settings_menu
    await show_settings_menu(callback.message, callback.from_user.id)
    await callback.answer()

@router.callback_query(F.data == "menu_help")
async def callback_help_menu(callback: CallbackQuery, state: FSMContext):
    """Меню помощи - открываем напрямую"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Расширенная справка
    help_text = """
📖 **Справка по боту**

**Основные команды:**
• `/start` - начать работу с ботом
• `/menu` - главное меню
• `/help` - эта справка

**Управление постами:**
• `/create` - создать новый пост
• `/list` - список всех постов
• `/edit <ID>` - редактировать пост
• `/delete <ID>` - удалить пост

**Управление каналами:**
• `/channels` - управление каналами

**Настройки:**
• `/settings` - настройки профиля

💡 **Совет:** Используйте кнопки для быстрой навигации!
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Создать пост", callback_data="menu_create_post_direct"),
            InlineKeyboardButton(text="📋 Мои посты", callback_data="posts_menu")
        ],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(help_text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()
