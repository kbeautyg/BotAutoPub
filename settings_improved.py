from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
import supabase_db
from zoneinfo import available_timezones
import re

router = Router()

def get_settings_main_menu(lang: str = "ru"):
    """Главное меню настроек"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌍 Часовой пояс", callback_data="settings_timezone"),
            InlineKeyboardButton(text="🗣 Язык", callback_data="settings_language")
        ],
        [
            InlineKeyboardButton(text="📅 Формат даты", callback_data="settings_date_format"),
            InlineKeyboardButton(text="🕐 Формат времени", callback_data="settings_time_format")
        ],
        [
            InlineKeyboardButton(text="🔔 Уведомления", callback_data="settings_notifications")
        ],
        [
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
        ]
    ])

def format_user_settings(user: dict) -> str:
    """Форматировать текущие настройки пользователя"""
    if not user:
        return "❌ Ошибка загрузки настроек"
    
    text = "⚙️ **Настройки профиля**\n\n"
    
    # Часовой пояс
    timezone = user.get("timezone", "UTC")
    text += f"🌍 **Часовой пояс:** {timezone}\n"
    
    # Язык
    language = user.get("language", "ru")
    lang_name = "Русский" if language == "ru" else "English"
    text += f"🗣 **Язык:** {lang_name}\n"
    
    # Формат даты
    date_format = user.get("date_format", "YYYY-MM-DD")
    text += f"📅 **Формат даты:** {date_format}\n"
    
    # Формат времени
    time_format = user.get("time_format", "HH:MM")
    text += f"🕐 **Формат времени:** {time_format}\n"
    
    # Уведомления
    notify_before = user.get("notify_before", 0)
    if notify_before > 0:
        text += f"🔔 **Уведомления:** за {notify_before} мин. до публикации\n"
    else:
        text += f"🔔 **Уведомления:** отключены\n"
    
    text += "\n**Выберите что изменить:**"
    
    return text

@router.message(Command("settings"))
async def cmd_settings(message: Message):
    """Показать настройки пользователя"""
    user_id = message.from_user.id
    user = supabase_db.db.get_user(user_id)
    if not user:
        user = supabase_db.db.ensure_user(user_id)
    
    lang = user.get("language", "ru") if user else "ru"
    
    text = format_user_settings(user)
    keyboard = get_settings_main_menu(lang)
    
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data == "settings_timezone")
async def callback_settings_timezone(callback: CallbackQuery):
    """Настройка часового пояса"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    
    current_tz = user.get("timezone", "UTC") if user else "UTC"
    
    # Популярные часовые пояса
    popular_timezones = [
        ("UTC", "UTC (Всемирное время)"),
        ("Europe/Moscow", "Москва (UTC+3)"),
        ("Europe/Kiev", "Киев (UTC+2)"),
        ("Europe/Minsk", "Минск (UTC+3)"),
        ("Asia/Almaty", "Алматы (UTC+6)"),
        ("Asia/Yekaterinburg", "Екатеринбург (UTC+5)"),
        ("Asia/Novosibirsk", "Новосибирск (UTC+7)"),
        ("Europe/London", "Лондон (UTC+0)"),
        ("America/New_York", "Нью-Йорк (UTC-5)"),
        ("Asia/Tokyo", "Токио (UTC+9)")
    ]
    
    text = f"🌍 **Настройка часового пояса**\n\n"
    text += f"**Текущий:** {current_tz}\n\n"
    text += f"**Выберите часовой пояс:**\n\n"
    
    buttons = []
    for tz_id, tz_name in popular_timezones:
        is_current = tz_id == current_tz
        button_text = f"{'✅ ' if is_current else ''}{tz_name}"
        buttons.append([InlineKeyboardButton(
            text=button_text,
            callback_data=f"set_timezone:{tz_id}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="settings_menu")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "settings_language")
async def callback_settings_language(callback: CallbackQuery):
    """Настройка языка"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    
    current_lang = user.get("language", "ru") if user else "ru"
    
    text = f"🗣 **Настройка языка**\n\n"
    text += f"**Текущий:** {'Русский' if current_lang == 'ru' else 'English'}\n\n"
    text += f"**Выберите язык интерфейса:**"
    
    buttons = [
        [InlineKeyboardButton(
            text=f"{'✅ ' if current_lang == 'ru' else ''}🇷🇺 Русский",
            callback_data="set_language:ru"
        )],
        [InlineKeyboardButton(
            text=f"{'✅ ' if current_lang == 'en' else ''}🇺🇸 English",
            callback_data="set_language:en"
        )],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="settings_menu")]
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "settings_date_format")
async def callback_settings_date_format(callback: CallbackQuery):
    """Настройка формата даты"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    
    current_format = user.get("date_format", "YYYY-MM-DD") if user else "YYYY-MM-DD"
    
    date_formats = [
        ("YYYY-MM-DD", "2024-12-25"),
        ("DD.MM.YYYY", "25.12.2024"),
        ("DD/MM/YYYY", "25/12/2024"),
        ("MM/DD/YYYY", "12/25/2024")
    ]
    
    text = f"📅 **Настройка формата даты**\n\n"
    text += f"**Текущий:** {current_format}\n\n"
    text += f"**Выберите формат даты:**\n\n"
    
    buttons = []
    for format_id, example in date_formats:
        is_current = format_id == current_format
        button_text = f"{'✅ ' if is_current else ''}{format_id} ({example})"
        buttons.append([InlineKeyboardButton(
            text=button_text,
            callback_data=f"set_date_format:{format_id}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="settings_menu")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "settings_time_format")
async def callback_settings_time_format(callback: CallbackQuery):
    """Настройка формата времени"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    
    current_format = user.get("time_format", "HH:MM") if user else "HH:MM"
    
    time_formats = [
        ("HH:MM", "15:30 (24-часовой)"),
        ("hh:MM AM", "3:30 PM (12-часовой)")
    ]
    
    text = f"🕐 **Настройка формата времени**\n\n"
    text += f"**Текущий:** {current_format}\n\n"
    text += f"**Выберите формат времени:**\n\n"
    
    buttons = []
    for format_id, example in time_formats:
        is_current = format_id == current_format
        button_text = f"{'✅ ' if is_current else ''}{example}"
        buttons.append([InlineKeyboardButton(
            text=button_text,
            callback_data=f"set_time_format:{format_id}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="settings_menu")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "settings_notifications")
async def callback_settings_notifications(callback: CallbackQuery):
    """Настройка уведомлений"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    
    current_notify = user.get("notify_before", 0) if user else 0
    
    text = f"🔔 **Настройка уведомлений**\n\n"
    
    if current_notify > 0:
        text += f"**Текущая настройка:** за {current_notify} минут до публикации\n\n"
    else:
        text += f"**Текущая настройка:** отключены\n\n"
    
    text += f"**Уведомлять за сколько минут до публикации?**\n\n"
    
    notify_options = [
        (0, "🔕 Отключить уведомления"),
        (5, "5 минут"),
        (15, "15 минут"),
        (30, "30 минут"),
        (60, "1 час"),
        (120, "2 часа")
    ]
    
    buttons = []
    for minutes, label in notify_options:
        is_current = minutes == current_notify
        button_text = f"{'✅ ' if is_current else ''}{label}"
        buttons.append([InlineKeyboardButton(
            text=button_text,
            callback_data=f"set_notifications:{minutes}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="settings_menu")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "settings_menu")
async def callback_settings_menu(callback: CallbackQuery):
    """Вернуться в главное меню настроек"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    if not user:
        user = supabase_db.db.ensure_user(user_id)
    
    lang = user.get("language", "ru") if user else "ru"
    
    text = format_user_settings(user)
    keyboard = get_settings_main_menu(lang)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

# Обработчики установки настроек
@router.callback_query(F.data.startswith("set_timezone:"))
async def callback_set_timezone(callback: CallbackQuery):
    """Установить часовой пояс"""
    timezone = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    
    # Проверяем, что часовой пояс существует
    if timezone not in available_timezones():
        await callback.answer("❌ Неверный часовой пояс")
        return
    
    # Обновляем настройки
    success = supabase_db.db.update_user(user_id, {"timezone": timezone})
    
    if success:
        user = supabase_db.db.get_user(user_id)
        text = format_user_settings(user)
        keyboard = get_settings_main_menu(user.get("language", "ru"))
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await callback.answer(f"✅ Часовой пояс изменен на {timezone}")
    else:
        await callback.answer("❌ Ошибка сохранения настроек")

@router.callback_query(F.data.startswith("set_language:"))
async def callback_set_language(callback: CallbackQuery):
    """Установить язык"""
    language = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    
    if language not in ["ru", "en"]:
        await callback.answer("❌ Неподдерживаемый язык")
        return
    
    # Обновляем настройки
    success = supabase_db.db.update_user(user_id, {"language": language})
    
    if success:
        user = supabase_db.db.get_user(user_id)
        text = format_user_settings(user)
        keyboard = get_settings_main_menu(language)
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        lang_name = "русский" if language == "ru" else "английский"
        await callback.answer(f"✅ Язык изменен на {lang_name}")
    else:
        await callback.answer("❌ Ошибка сохранения настроек")

@router.callback_query(F.data.startswith("set_date_format:"))
async def callback_set_date_format(callback: CallbackQuery):
    """Установить формат даты"""
    date_format = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    
    valid_formats = ["YYYY-MM-DD", "DD.MM.YYYY", "DD/MM/YYYY", "MM/DD/YYYY"]
    if date_format not in valid_formats:
        await callback.answer("❌ Неверный формат даты")
        return
    
    # Обновляем настройки
    success = supabase_db.db.update_user(user_id, {"date_format": date_format})
    
    if success:
        user = supabase_db.db.get_user(user_id)
        text = format_user_settings(user)
        keyboard = get_settings_main_menu(user.get("language", "ru"))
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await callback.answer(f"✅ Формат даты изменен на {date_format}")
    else:
        await callback.answer("❌ Ошибка сохранения настроек")

@router.callback_query(F.data.startswith("set_time_format:"))
async def callback_set_time_format(callback: CallbackQuery):
    """Установить формат времени"""
    time_format = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    
    valid_formats = ["HH:MM", "hh:MM AM"]
    if time_format not in valid_formats:
        await callback.answer("❌ Неверный формат времени")
        return
    
    # Обновляем настройки
    success = supabase_db.db.update_user(user_id, {"time_format": time_format})
    
    if success:
        user = supabase_db.db.get_user(user_id)
        text = format_user_settings(user)
        keyboard = get_settings_main_menu(user.get("language", "ru"))
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await callback.answer(f"✅ Формат времени изменен на {time_format}")
    else:
        await callback.answer("❌ Ошибка сохранения настроек")

@router.callback_query(F.data.startswith("set_notifications:"))
async def callback_set_notifications(callback: CallbackQuery):
    """Установить уведомления"""
    try:
        notify_minutes = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("❌ Неверное значение")
        return
    
    user_id = callback.from_user.id
    
    if notify_minutes < 0 or notify_minutes > 1440:  # Максимум 24 часа
        await callback.answer("❌ Неверное значение времени")
        return
    
    # Обновляем настройки
    success = supabase_db.db.update_user(user_id, {"notify_before": notify_minutes})
    
    if success:
        user = supabase_db.db.get_user(user_id)
        text = format_user_settings(user)
        keyboard = get_settings_main_menu(user.get("language", "ru"))
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        
        if notify_minutes == 0:
            await callback.answer("✅ Уведомления отключены")
        else:
            await callback.answer(f"✅ Уведомления: за {notify_minutes} мин.")
    else:
        await callback.answer("❌ Ошибка сохранения настроек")
