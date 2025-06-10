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
                InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu_settings")
            ],
            [
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
                InlineKeyboardButton(text="⚙️ Settings", callback_data="menu_settings")
            ],
            [
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
        
        # Быстрая статистика
        if user:
            try:
                channels = supabase_db.db.get_user_channels(user['user_id'])
                posts = supabase_db.db.list_posts(user_id=user['user_id'], only_pending=True)
                text += f"📺 Ваших каналов: {len(channels) if channels else 0} | ⏰ Запланированных постов: {len(posts) if posts else 0}\n\n"
            except Exception as e:
                print(f"Error getting stats for user: {e}")
                text += "\n"
        
        text += "Выберите действие из меню ниже:"
    else:
        text = "🤖 **Welcome to the Channel Management Bot!**\n\n"
        text += "This bot will help you:\n"
        text += "• 📝 Create and schedule posts\n"
        text += "• 📺 Manage Telegram channels\n"
        text += "• ⏰ Automatically publish content\n"
        text += "• 📊 Track statistics\n\n"
        
        # Quick stats
        if user:
            try:
                channels = supabase_db.db.get_user_channels(user['user_id'])
                posts = supabase_db.db.list_posts(user_id=user['user_id'], only_pending=True)
                text += f"📺 Your channels: {len(channels) if channels else 0} | ⏰ Scheduled posts: {len(posts) if posts else 0}\n\n"
            except Exception as e:
                print(f"Error getting stats for user: {e}")
                text += "\n"
        
        text += "Choose an action from the menu below:"
    
    return text

@router.message(Command("menu"))
async def cmd_main_menu(message: Message, state: FSMContext):
    """Показать главное меню"""
    user_id = message.from_user.id
    try:
        user = supabase_db.db.ensure_user(user_id)
        lang = user.get("language", "ru") if user else "ru"
        
        text = get_welcome_text(user, lang)
        keyboard = get_main_menu_keyboard(lang)
        
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    except Exception as e:
        print(f"Error in cmd_main_menu: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")

@router.callback_query(F.data == "main_menu")
async def callback_main_menu(callback: CallbackQuery):
    """Вернуться в главное меню"""
    user_id = callback.from_user.id
    try:
        user = supabase_db.db.get_user(user_id)
        if not user:
            user = supabase_db.db.ensure_user(user_id)
        lang = user.get("language", "ru") if user else "ru"
        
        text = get_welcome_text(user, lang)
        keyboard = get_main_menu_keyboard(lang)
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await callback.answer()
    except Exception as e:
        print(f"Error in callback_main_menu: {e}")
        await callback.answer("❌ Произошла ошибка")

@router.callback_query(F.data == "menu_create_post")
async def callback_create_post(callback: CallbackQuery, state: FSMContext):
    """Создать пост напрямую"""
    user_id = callback.from_user.id
    user = supabase_db.db.ensure_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Проверяем наличие каналов у пользователя
    channels = supabase_db.db.get_user_channels(user_id)
    if not channels:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📺 Добавить канал", callback_data="channels_add")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await callback.message.edit_text(
            "❌ **Нет доступных каналов**\n\n"
            "Сначала добавьте канал для публикации постов.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        await callback.answer()
        return
    
    # Инициализируем данные поста и запускаем процесс создания
    await state.set_data({
        "user_id": user_id,
        "text": None,
        "media_type": None,
        "media_file_id": None,
        "parse_mode": "HTML",
        "buttons": None,
        "publish_time": None,
        "repeat_interval": None,
        "channel_id": None,
        "draft": False,
        "step_history": [],
        "current_step": "step_text"
    })
    
    # Импортируем и запускаем первый шаг создания поста
    try:
        from scheduled_posts import start_text_step
        from states import PostCreationFlow
        await state.set_state(PostCreationFlow.step_text)
        await start_text_step(callback.message, state, lang)
        await callback.answer()
    except ImportError:
        await callback.message.edit_text(
            "❌ Ошибка модуля создания постов. Используйте команду `/create`",
            parse_mode="Markdown"
        )
        await callback.answer()

@router.callback_query(F.data == "menu_posts")
async def callback_posts_menu(callback: CallbackQuery):
    """Меню постов"""
    try:
        # Импортируем функцию из list_posts
        from list_posts import callback_posts_menu as posts_menu_handler
        await posts_menu_handler(callback)
    except Exception as e:
        print(f"Error in callback_posts_menu: {e}")
        await callback.answer("❌ Произошла ошибка")

@router.callback_query(F.data == "menu_channels")
async def callback_channels_menu(callback: CallbackQuery):
    """Меню каналов"""
    try:
        # Прямой запуск меню каналов
        user_id = callback.from_user.id
        user = supabase_db.db.get_user(user_id)
        lang = user.get("language", "ru") if user else "ru"
        
        # Показываем главное меню каналов
        from channels import get_channels_main_menu
        text = "🔧 **Управление каналами**\n\nВыберите действие:"
        keyboard = get_channels_main_menu(lang)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await callback.answer()
    except Exception as e:
        print(f"Error in callback_channels_menu: {e}")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
        ])
        
        await callback.message.edit_text(
            "📺 **Управление каналами**\n\n"
            "Используйте команду `/channels` для управления каналами.\n\n"
            "**Команды:**\n"
            "• `/channels` - список каналов\n"
            "• `/channels add` - добавить канал\n"
            "• `/channels remove <ID>` - удалить канал",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        await callback.answer()

@router.callback_query(F.data == "menu_settings")
async def callback_settings_menu(callback: CallbackQuery):
    """Меню настроек"""
    try:
        # Импортируем функцию из settings_improved
        user_id = callback.from_user.id
        user = supabase_db.db.get_user(user_id)
        if not user:
            user = supabase_db.db.ensure_user(user_id)
        lang = user.get("language", "ru") if user else "ru"
        
        # Прямой вызов настроек
        from settings_improved import format_user_settings, get_settings_main_menu
        text = format_user_settings(user)
        keyboard = get_settings_main_menu(lang)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await callback.answer()
    except Exception as e:
        print(f"Error in callback_settings_menu: {e}")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
        ])
        
        await callback.message.edit_text(
            "⚙️ **Настройки**\n\n"
            "Используйте команду `/settings` для настройки бота.\n\n"
            "**Доступные настройки:**\n"
            "• Часовой пояс\n"
            "• Язык интерфейса\n"
            "• Уведомления\n"
            "• Формат даты и времени",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        await callback.answer()

@router.callback_query(F.data == "menu_help")
async def callback_help_menu(callback: CallbackQuery):
    """Меню помощи"""
    try:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
        ])
        
        help_text = """
📖 **Справка по боту**

**Основные команды:**
• `/start` - начать работу с ботом
• `/menu` - главное меню
• `/help` - эта справка

**Управление постами:**
• `/create` - создать новый пост (пошагово)
• `/quickpost <канал> <время> <текст>` - быстрое создание
• `/list` - список всех постов
• `/view <ID>` - просмотр поста
• `/edit <ID>` - редактировать пост
• `/delete <ID>` - удалить пост
• `/publish <ID>` - опубликовать немедленно

**Управление каналами:**
• `/channels` - меню управления каналами
• `/channels add <@канал или ID>` - добавить канал
• `/channels list` - список каналов

**Настройки:**
• `/settings` - настройки профиля

💡 **Совет:** Используйте кнопки меню для быстрого доступа к функциям!
"""
        
        await callback.message.edit_text(
            help_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        await callback.answer()
    except Exception as e:
        print(f"Error in callback_help_menu: {e}")
        await callback.answer("❌ Произошла ошибка")

# Команды быстрого доступа
@router.message(Command("quick"))
async def cmd_quick_actions(message: Message, state: FSMContext):
    """Быстрые действия"""
    try:
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
    except Exception as e:
        print(f"Error in cmd_quick_actions: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")

@router.callback_query(F.data == "quick_post")
async def callback_quick_post(callback: CallbackQuery):
    """Быстрое создание поста"""
    try:
        await callback.message.answer(
            "🚀 **Быстрое создание поста**\n\n"
            "Используйте команду `/quickpost` для быстрого создания:\n\n"
            "**Формат:** `/quickpost <канал> <время> <текст>`\n\n"
            "**Примеры:**\n"
            "• `/quickpost @channel now Текст поста`\n"
            "• `/quickpost 1 draft Черновик поста`\n"
            "• `/quickpost 2 2024-12-25_15:30 Запланированный пост`\n\n"
            "Или используйте `/create` для полного контроля над постом.",
            parse_mode="Markdown"
        )
        await callback.answer()
    except Exception as e:
        print(f"Error in callback_quick_post: {e}")
        await callback.answer("❌ Произошла ошибка")

@router.callback_query(F.data == "quick_stats")
async def callback_quick_stats(callback: CallbackQuery):
    """Быстрая статистика"""
    try:
        user_id = callback.from_user.id
        user = supabase_db.db.get_user(user_id)
        if not user:
            user = supabase_db.db.ensure_user(user_id)
        
        try:
            channels = supabase_db.db.get_user_channels(user_id) or []
            all_posts = supabase_db.db.list_posts(user_id=user_id, only_pending=False) or []
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
        except Exception as e:
            print(f"Error getting stats: {e}")
            text = "📊 **Быстрая статистика**\n\n❌ Ошибка загрузки данных"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Подробнее", callback_data="menu_posts")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await callback.answer()
    except Exception as e:
        print(f"Error in callback_quick_stats: {e}")
        await callback.answer("❌ Произошла ошибка")

@router.callback_query(F.data == "quick_upcoming")
async def callback_quick_upcoming(callback: CallbackQuery):
    """Ближайшие посты"""
    try:
        user_id = callback.from_user.id
        user = supabase_db.db.get_user(user_id)
        if not user:
            user = supabase_db.db.ensure_user(user_id)
        
        try:
            posts = supabase_db.db.get_scheduled_posts_by_channel(user_id) or []
            
            if not posts:
                text = "⏰ **Ближайшие посты**\n\n❌ Нет запланированных постов."
            else:
                text = "⏰ **Ближайшие посты**\n\n"
                for i, post in enumerate(posts[:5], 1):  # Показываем первые 5
                    try:
                        from datetime import datetime
                        from zoneinfo import ZoneInfo
                        
                        if post.get('publish_time'):
                            utc_time = datetime.fromisoformat(post['publish_time'].replace('Z', '+00:00'))
                            if user.get('timezone'):
                                user_tz = ZoneInfo(user['timezone'])
                                local_time = utc_time.astimezone(user_tz)
                                time_str = local_time.strftime('%m-%d %H:%M')
                            else:
                                time_str = utc_time.strftime('%m-%d %H:%M')
                            
                            channel_name = "Канал"
                            if post.get('channels') and isinstance(post['channels'], dict):
                                channel_name = post['channels'].get('name', 'Канал')
                            
                            post_text = post.get('text', 'Без текста')[:25]
                            text += f"{i}. **{time_str}** - {channel_name}\n   {post_text}...\n\n"
                        else:
                            text += f"{i}. Пост #{post.get('id', '?')}\n\n"
                    except Exception as e:
                        print(f"Error formatting post {post}: {e}")
                        text += f"{i}. Пост #{post.get('id', '?')}\n\n"
        except Exception as e:
            print(f"Error getting upcoming posts: {e}")
            text = "⏰ **Ближайшие посты**\n\n❌ Ошибка загрузки данных"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Все посты", callback_data="posts_scheduled")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await callback.answer()
    except Exception as e:
        print(f"Error in callback_quick_upcoming: {e}")
        await callback.answer("❌ Произошла ошибка")
