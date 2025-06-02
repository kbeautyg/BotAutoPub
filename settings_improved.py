from aiogram import Router, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
import supabase_db
from __init__ import TEXTS
from zoneinfo import ZoneInfo
from datetime import datetime

router = Router()

# Популярные часовые пояса
POPULAR_TIMEZONES = [
    ("UTC", "UTC (Всемирное время)"),
    ("Europe/Moscow", "Москва (UTC+3)"),
    ("Europe/Kiev", "Киев (UTC+2)"),
    ("Europe/Minsk", "Минск (UTC+3)"),
    ("Asia/Almaty", "Алматы (UTC+6)"),
    ("Asia/Tashkent", "Ташкент (UTC+5)"),
    ("Asia/Yekaterinburg", "Екатеринбург (UTC+5)"),
    ("Asia/Novosibirsk", "Новосибирск (UTC+7)"),
    ("Asia/Krasnoyarsk", "Красноярск (UTC+7)"),
    ("Asia/Irkutsk", "Иркутск (UTC+8)"),
    ("Asia/Vladivostok", "Владивосток (UTC+10)"),
    ("Europe/London", "Лондон (UTC+0)"),
    ("Europe/Berlin", "Берлин (UTC+1)"),
    ("Europe/Paris", "Париж (UTC+1)"),
    ("America/New_York", "Нью-Йорк (UTC-5)"),
    ("America/Los_Angeles", "Лос-Анджелес (UTC-8)"),
    ("Asia/Tokyo", "Токио (UTC+9)"),
    ("Asia/Shanghai", "Шанхай (UTC+8)"),
    ("Asia/Dubai", "Дубай (UTC+4)"),
    ("Australia/Sydney", "Сидней (UTC+11)")
]

def get_settings_main_menu(lang: str = "ru"):
    """Главное меню настроек"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌍 Часовой пояс", callback_data="settings_timezone")],
        [InlineKeyboardButton(text="🌐 Язык", callback_data="settings_language")],
        [InlineKeyboardButton(text="📅 Формат даты", callback_data="settings_date_format")],
        [InlineKeyboardButton(text="⏰ Формат времени", callback_data="settings_time_format")],
        [InlineKeyboardButton(text="🔔 Уведомления", callback_data="settings_notifications")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="settings_stats")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])

def get_timezone_menu(lang: str = "ru"):
    """Меню выбора часового пояса"""
    buttons = []
    
    # Популярные часовые пояса
    for tz_id, tz_name in POPULAR_TIMEZONES[:10]:  # Показываем первые 10
        buttons.append([InlineKeyboardButton(
            text=tz_name, 
            callback_data=f"tz_set:{tz_id}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🌍 Больше часовых поясов", callback_data="tz_more")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="settings_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_more_timezones_menu(lang: str = "ru"):
    """Дополнительные часовые пояса"""
    buttons = []
    
    # Остальные часовые пояса
    for tz_id, tz_name in POPULAR_TIMEZONES[10:]:
        buttons.append([InlineKeyboardButton(
            text=tz_name, 
            callback_data=f"tz_set:{tz_id}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 К основным", callback_data="settings_timezone")])
    buttons.append([InlineKeyboardButton(text="🏠 К настройкам", callback_data="settings_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_language_menu(lang: str = "ru"):
    """Меню выбора языка"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_set:ru")],
        [InlineKeyboardButton(text="🇺🇸 English", callback_data="lang_set:en")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="settings_menu")]
    ])

def get_date_format_menu(lang: str = "ru"):
    """Меню выбора формата даты"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="YYYY-MM-DD (2024-12-25)", callback_data="date_fmt:YYYY-MM-DD")],
        [InlineKeyboardButton(text="DD.MM.YYYY (25.12.2024)", callback_data="date_fmt:DD.MM.YYYY")],
        [InlineKeyboardButton(text="DD/MM/YYYY (25/12/2024)", callback_data="date_fmt:DD/MM/YYYY")],
        [InlineKeyboardButton(text="MM/DD/YYYY (12/25/2024)", callback_data="date_fmt:MM/DD/YYYY")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="settings_menu")]
    ])

def get_time_format_menu(lang: str = "ru"):
    """Меню выбора формата времени"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="24-часовой (15:30)", callback_data="time_fmt:HH:MM")],
        [InlineKeyboardButton(text="12-часовой (3:30 PM)", callback_data="time_fmt:hh:MM AM")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="settings_menu")]
    ])

def get_notifications_menu(user: dict, lang: str = "ru"):
    """Меню настроек уведомлений"""
    # Получаем текущие настройки уведомлений
    notifications = supabase_db.db.get_notification_settings(user['user_id'])
    
    post_published = notifications.get('post_published', True) if notifications else True
    post_failed = notifications.get('post_failed', True) if notifications else True
    daily_summary = notifications.get('daily_summary', False) if notifications else False
    
    buttons = []
    
    # Уведомления о публикации
    pub_status = "✅" if post_published else "❌"
    buttons.append([InlineKeyboardButton(
        text=f"{pub_status} Уведомления о публикации", 
        callback_data="notif_toggle:post_published"
    )])
    
    # Уведомления об ошибках
    fail_status = "✅" if post_failed else "❌"
    buttons.append([InlineKeyboardButton(
        text=f"{fail_status} Уведомления об ошибках", 
        callback_data="notif_toggle:post_failed"
    )])
    
    # Ежедневная сводка
    daily_status = "✅" if daily_summary else "❌"
    buttons.append([InlineKeyboardButton(
        text=f"{daily_status} Ежедневная сводка", 
        callback_data="notif_toggle:daily_summary"
    )])
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="settings_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def format_user_settings(user: dict) -> str:
    """Форматировать текущие настройки пользователя"""
    text = "⚙️ **Ваши настройки**\n\n"
    
    # Часовой пояс
    tz_name = user.get('timezone', 'UTC')
    try:
        tz = ZoneInfo(tz_name)
        current_time = datetime.now(tz)
        time_str = current_time.strftime('%H:%M')
        text += f"🌍 **Часовой пояс:** {tz_name}\n"
        text += f"   Текущее время: {time_str}\n\n"
    except:
        text += f"🌍 **Часовой пояс:** {tz_name}\n\n"
    
    # Язык
    lang_name = "Русский" if user.get('language') == 'ru' else "English"
    text += f"🌐 **Язык:** {lang_name}\n\n"
    
    # Формат даты и времени
    text += f"📅 **Формат даты:** {user.get('date_format', 'YYYY-MM-DD')}\n"
    text += f"⏰ **Формат времени:** {user.get('time_format', 'HH:MM')}\n\n"
    
    # Пример форматирования
    try:
        now = datetime.now(ZoneInfo(tz_name))
        if user.get('date_format') == 'DD.MM.YYYY':
            date_example = now.strftime('%d.%m.%Y')
        elif user.get('date_format') == 'DD/MM/YYYY':
            date_example = now.strftime('%d/%m/%Y')
        elif user.get('date_format') == 'MM/DD/YYYY':
            date_example = now.strftime('%m/%d/%Y')
        else:
            date_example = now.strftime('%Y-%m-%d')
        
        if user.get('time_format') == 'hh:MM AM':
            time_example = now.strftime('%I:%M %p')
        else:
            time_example = now.strftime('%H:%M')
        
        text += f"📝 **Пример:** {date_example} {time_example}\n\n"
    except:
        pass
    
    # Текущий проект
    if user.get('current_project'):
        project = supabase_db.db.get_project(user['current_project'])
        if project:
            text += f"📁 **Текущий проект:** {project['name']}\n"
    
    return text

@router.message(Command("settings"))
async def cmd_settings(message: Message, state: FSMContext):
    """Показать настройки пользователя"""
    user_id = message.from_user.id
    user = supabase_db.db.ensure_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    await show_settings_menu(message, user, lang)

async def show_settings_menu(message: Message, user: dict, lang: str):
    """Показать главное меню настроек"""
    text = format_user_settings(user)
    keyboard = get_settings_main_menu(lang)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data == "settings_menu")
async def callback_settings_menu(callback: CallbackQuery):
    """Вернуться в главное меню настроек"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    text = format_user_settings(user)
    keyboard = get_settings_main_menu(lang)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "settings_timezone")
async def callback_timezone_settings(callback: CallbackQuery):
    """Настройки часового пояса"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    current_tz = user.get('timezone', 'UTC')
    
    text = (
        f"🌍 **Настройка часового пояса**\n\n"
        f"Текущий часовой пояс: **{current_tz}**\n\n"
        f"Выберите новый часовой пояс:"
    )
    
    keyboard = get_timezone_menu(lang)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "tz_more")
async def callback_more_timezones(callback: CallbackQuery):
    """Показать больше часовых поясов"""
    text = "🌍 **Дополнительные часовые пояса**\n\nВыберите часовой пояс:"
    keyboard = get_more_timezones_menu()
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("tz_set:"))
async def callback_set_timezone(callback: CallbackQuery):
    """Установить часовой пояс"""
    user_id = callback.from_user.id
    timezone = callback.data.split(":", 1)[1]
    
    try:
        # Проверяем валидность часового пояса
        tz = ZoneInfo(timezone)
        current_time = datetime.now(tz)
        
        # Обновляем в базе данных
        supabase_db.db.update_user(user_id, {"timezone": timezone})
        
        time_str = current_time.strftime('%H:%M')
        await callback.message.edit_text(
            f"✅ **Часовой пояс обновлен**\n\n"
            f"Новый часовой пояс: **{timezone}**\n"
            f"Текущее время: **{time_str}**\n\n"
            f"Все времена публикации теперь будут отображаться в этом часовом поясе.",
            parse_mode="Markdown"
        )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ **Ошибка**\n\n"
            f"Не удалось установить часовой пояс: {str(e)}",
            parse_mode="Markdown"
        )
    
    await callback.answer()

@router.callback_query(F.data == "settings_language")
async def callback_language_settings(callback: CallbackQuery):
    """Настройки языка"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    current_lang = user.get('language', 'ru')
    
    text = (
        f"🌐 **Настройка языка**\n\n"
        f"Текущий язык: **{'Русский' if current_lang == 'ru' else 'English'}**\n\n"
        f"Выберите язык интерфейса:"
    )
    
    keyboard = get_language_menu()
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("lang_set:"))
async def callback_set_language(callback: CallbackQuery):
    """Установить язык"""
    user_id = callback.from_user.id
    language = callback.data.split(":", 1)[1]
    
    supabase_db.db.update_user(user_id, {"language": language})
    
    lang_name = "Русский" if language == 'ru' else "English"
    await callback.message.edit_text(
        f"✅ **Язык обновлен**\n\n"
        f"Новый язык интерфейса: **{lang_name}**\n\n"
        f"Интерфейс бота теперь будет отображаться на выбранном языке.",
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "settings_date_format")
async def callback_date_format_settings(callback: CallbackQuery):
    """Настройки формата даты"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    current_format = user.get('date_format', 'YYYY-MM-DD')
    
    text = (
        f"📅 **Настройка формата даты**\n\n"
        f"Текущий формат: **{current_format}**\n\n"
        f"Выберите новый формат:"
    )
    
    keyboard = get_date_format_menu()
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("date_fmt:"))
async def callback_set_date_format(callback: CallbackQuery):
    """Установить формат даты"""
    user_id = callback.from_user.id
    date_format = callback.data.split(":", 1)[1]
    
    supabase_db.db.update_user(user_id, {"date_format": date_format})
    
    # Показываем пример
    now = datetime.now()
    if date_format == 'DD.MM.YYYY':
        example = now.strftime('%d.%m.%Y')
    elif date_format == 'DD/MM/YYYY':
        example = now.strftime('%d/%m/%Y')
    elif date_format == 'MM/DD/YYYY':
        example = now.strftime('%m/%d/%Y')
    else:
        example = now.strftime('%Y-%m-%d')
    
    await callback.message.edit_text(
        f"✅ **Формат даты обновлен**\n\n"
        f"Новый формат: **{date_format}**\n"
        f"Пример: **{example}**\n\n"
        f"Все даты теперь будут отображаться в этом формате.",
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "settings_time_format")
async def callback_time_format_settings(callback: CallbackQuery):
    """Настройки формата времени"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    current_format = user.get('time_format', 'HH:MM')
    
    text = (
        f"⏰ **Настройка формата времени**\n\n"
        f"Текущий формат: **{current_format}**\n\n"
        f"Выберите новый формат:"
    )
    
    keyboard = get_time_format_menu()
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("time_fmt:"))
async def callback_set_time_format(callback: CallbackQuery):
    """Установить формат времени"""
    user_id = callback.from_user.id
    time_format = callback.data.split(":", 1)[1]
    
    supabase_db.db.update_user(user_id, {"time_format": time_format})
    
    # Показываем пример
    now = datetime.now()
    if time_format == 'hh:MM AM':
        example = now.strftime('%I:%M %p')
    else:
        example = now.strftime('%H:%M')
    
    await callback.message.edit_text(
        f"✅ **Формат времени обновлен**\n\n"
        f"Новый формат: **{time_format}**\n"
        f"Пример: **{example}**\n\n"
        f"Все времена теперь будут отображаться в этом формате.",
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "settings_notifications")
async def callback_notifications_settings(callback: CallbackQuery):
    """Настройки уведомлений"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    text = (
        f"🔔 **Настройки уведомлений**\n\n"
        f"Управляйте типами уведомлений, которые вы хотите получать:"
    )
    
    keyboard = get_notifications_menu(user, lang)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("notif_toggle:"))
async def callback_toggle_notification(callback: CallbackQuery):
    """Переключить настройку уведомления"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    setting_name = callback.data.split(":", 1)[1]
    
    # Получаем текущие настройки
    notifications = supabase_db.db.get_notification_settings(user_id)
    if not notifications:
        # Создаем настройки по умолчанию
        notifications = {
            'user_id': user_id,
            'post_published': True,
            'post_failed': True,
            'daily_summary': False
        }
        supabase_db.db.create_notification_settings(notifications)
    
    # Переключаем настройку
    current_value = notifications.get(setting_name, False)
    new_value = not current_value
    
    supabase_db.db.update_notification_settings(user_id, {setting_name: new_value})
    
    # Обновляем клавиатуру
    user = supabase_db.db.get_user(user_id)  # Обновляем данные пользователя
    text = (
        f"🔔 **Настройки уведомлений**\n\n"
        f"Управляйте типами уведомлений, которые вы хотите получать:"
    )
    
    keyboard = get_notifications_menu(user, lang)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    status = "включены" if new_value else "отключены"
    setting_names = {
        'post_published': 'Уведомления о публикации',
        'post_failed': 'Уведомления об ошибках',
        'daily_summary': 'Ежедневная сводка'
    }
    
    await callback.answer(f"{setting_names.get(setting_name, setting_name)} {status}")

@router.callback_query(F.data == "settings_stats")
async def callback_settings_stats(callback: CallbackQuery):
    """Показать статистику пользователя"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    project_id = user.get("current_project")
    
    if not project_id:
        text = "📊 **Статистика**\n\n❌ Нет активного проекта."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="settings_menu")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await callback.answer()
        return
    
    # Получаем статистику
    channels = supabase_db.db.list_channels(project_id=project_id)
    all_posts = supabase_db.db.list_posts(project_id=project_id, only_pending=False)
    scheduled_posts = [p for p in all_posts if not p.get('published') and not p.get('draft') and p.get('publish_time')]
    draft_posts = [p for p in all_posts if p.get('draft')]
    published_posts = [p for p in all_posts if p.get('published')]
    
    text = (
        f"📊 **Ваша статистика**\n\n"
        f"📺 **Каналов:** {len(channels)}\n"
        f"📝 **Всего постов:** {len(all_posts)}\n"
        f"⏰ **Запланированных:** {len(scheduled_posts)}\n"
        f"📋 **Черновиков:** {len(draft_posts)}\n"
        f"✅ **Опубликованных:** {len(published_posts)}\n\n"
    )
    
    if user.get('created_at'):
        try:
            created_date = datetime.fromisoformat(user['created_at'].replace('Z', '+00:00'))
            days_using = (datetime.now(created_date.tzinfo) - created_date).days
            text += f"📅 **Используете бота:** {days_using} дней\n"
        except:
            pass
    
    # Статистика по каналам
    if channels:
        text += f"\n**Каналы:**\n"
        for channel in channels[:5]:  # Показываем первые 5
            channel_posts = [p for p in all_posts if p.get('channel_id') == channel['id']]
            admin_status = "✅" if channel.get('is_admin_verified') else "❓"
            text += f"{admin_status} {channel['name']}: {len(channel_posts)} постов\n"
        
        if len(channels) > 5:
            text += f"... и еще {len(channels) - 5} каналов\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="settings_stats")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="settings_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()
