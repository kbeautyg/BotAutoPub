import logging
from typing import Dict, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.error import TelegramError
from database import db
from utils import (
    create_main_menu_keyboard, create_back_button, create_cancel_button,
    TimeZoneManager, TextFormatter, ButtonManager, DateTimeParser,
    truncate_text, validate_url
)
from scheduler import post_scheduler, channel_manager
from config import Config
import re
from datetime import datetime

logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
(WAITING_FOR_TEXT, WAITING_FOR_MEDIA, WAITING_FOR_BUTTONS, 
 WAITING_FOR_SCHEDULE, WAITING_FOR_CHANNEL_ID, WAITING_FOR_CHANNEL_TITLE,
 CONFIRM_POST, EDIT_POST) = range(8)

class BotHandlers:
    """Основные обработчики бота"""
    
    @staticmethod
    async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user = update.effective_user
        
        # Проверяем, есть ли пользователь в базе
        db_user = await db.get_user(user.id)
        
        if not db_user:
            # Создаем нового пользователя
            is_admin = user.id == Config.ADMIN_TELEGRAM_ID
            await db.create_user(
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                is_admin=is_admin
            )
            
            welcome_text = (
                f"👋 Добро пожаловать, {user.first_name}!\n\n"
                "Я бот для управления Telegram каналами.\n"
            )
            
            if is_admin:
                welcome_text += (
                    "🔑 Вы определены как администратор.\n"
                    "Вам доступны все функции управления каналами и постами."
                )
            else:
                welcome_text += (
                    "ℹ️ Для получения прав администратора обратитесь к владельцу бота."
                )
        else:
            welcome_text = f"👋 С возвращением, {user.first_name}!"
        
        is_admin = await db.is_admin(user.id)
        keyboard = create_main_menu_keyboard(is_admin)
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        
        # Логируем действие
        await db.log_action(user.id, 'start_command')
    
    @staticmethod
    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        user = update.effective_user
        is_admin = await db.is_admin(user.id)
        
        help_text = (
            "🤖 <b>Помощь по боту</b>\n\n"
            "<b>Основные команды:</b>\n"
            "/start - Запустить бота\n"
            "/help - Показать эту справку\n"
            "/menu - Главное меню\n"
            "/cancel - Отменить текущее действие\n\n"
        )
        
        if is_admin:
            help_text += (
                "<b>Команды администратора:</b>\n"
                "/post - Создать новый пост\n"
                "/channels - Управление каналами\n"
                "/scheduled - Отложенные посты\n"
                "/stats - Статистика\n\n"
                
                "<b>Функции:</b>\n"
                "📝 Создание постов с текстом, медиа и кнопками\n"
                "⏰ Отложенная публикация\n"
                "📺 Управление каналами\n"
                "🌍 Настройка часового пояса\n"
                "📊 Статистика публикаций\n\n"
                
                "<b>Форматы времени для отложенной публикации:</b>\n"
                "• 15:30 - сегодня в 15:30 (или завтра, если время прошло)\n"
                "• 25.12 15:30 - 25 декабря в 15:30\n"
                "• 25.12.2024 15:30 - полная дата\n"
                "• через 30 мин - через 30 минут\n"
                "• через 2 час - через 2 часа\n"
                "• завтра в 10:00 - завтра в 10:00\n\n"
                
                "<b>Формат кнопок:</b>\n"
                "Текст кнопки - https://example.com\n"
                "Кнопка 1 | Кнопка 2 - https://example.com\n"
                "(каждая строка = новый ряд кнопок)"
            )
        else:
            help_text += (
                "<b>Доступные функции:</b>\n"
                "⚙️ Настройки профиля\n"
                "🌍 Изменение часового пояса\n"
                "ℹ️ Информация о боте"
            )
        
        await update.message.reply_text(help_text, parse_mode='HTML')
    
    @staticmethod
    async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /menu"""
        user = update.effective_user
        is_admin = await db.is_admin(user.id)
        keyboard = create_main_menu_keyboard(is_admin)
        
        await update.message.reply_text(
            "📋 Главное меню:",
            reply_markup=keyboard
        )
    
    @staticmethod
    async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /cancel"""
        user = update.effective_user
        
        # Очищаем состояние пользователя
        await db.clear_user_state(user.id)
        
        is_admin = await db.is_admin(user.id)
        keyboard = create_main_menu_keyboard(is_admin)
        
        await update.message.reply_text(
            "❌ Действие отменено. Возвращаемся в главное меню.",
            reply_markup=keyboard
        )
        
        return ConversationHandler.END

class CallbackHandlers:
    """Обработчики callback запросов"""
    
    @staticmethod
    async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Главное меню"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        is_admin = await db.is_admin(user.id)
        keyboard = create_main_menu_keyboard(is_admin)
        
        await query.edit_message_text(
            "📋 Главное меню:",
            reply_markup=keyboard
        )
    
    @staticmethod
    async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Настройки"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        db_user = await db.get_user(user.id)
        
        keyboard = [
            [InlineKeyboardButton("🌍 Часовой пояс", callback_data="change_timezone")],
            [InlineKeyboardButton("ℹ️ Мой профиль", callback_data="my_profile")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        
        settings_text = (
            "⚙️ <b>Настройки</b>\n\n"
            f"👤 <b>Пользователь:</b> {user.first_name}\n"
            f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
            f"🌍 <b>Часовой пояс:</b> {db_user.get('timezone', 'UTC') if db_user else 'UTC'}\n"
            f"🔑 <b>Статус:</b> {'Администратор' if await db.is_admin(user.id) else 'Пользователь'}"
        )
        
        await query.edit_message_text(
            settings_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    
    @staticmethod
    async def change_timezone_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Изменение часового пояса"""
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith('tz_'):
            # Выбран часовой пояс
            timezone = query.data[3:]
            user_id = query.from_user.id
            
            success = await db.update_user_timezone(user_id, timezone)
            
            if success:
                # Находим название часового пояса
                tz_name = None
                for name, tz in TimeZoneManager.COMMON_TIMEZONES.items():
                    if tz == timezone:
                        tz_name = name
                        break
                
                await query.edit_message_text(
                    f"✅ Часовой пояс изменен на: {tz_name or timezone}",
                    reply_markup=create_back_button("settings")
                )
                
                await db.log_action(user_id, 'timezone_changed', {'timezone': timezone})
            else:
                await query.edit_message_text(
                    "❌ Ошибка при изменении часового пояса",
                    reply_markup=create_back_button("settings")
                )
        else:
            # Показываем список часовых поясов
            keyboard = TimeZoneManager.get_timezone_keyboard()
            
            await query.edit_message_text(
                "🌍 Выберите ваш часовой пояс:",
                reply_markup=keyboard
            )
    
    @staticmethod
    async def back_to_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Возврат к настройкам"""
        await CallbackHandlers.settings_callback(update, context)

class ChannelHandlers:
    """Обработчики управления каналами"""
    
    @staticmethod
    async def manage_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Управление каналами"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        if not await db.is_admin(user.id):
            await query.edit_message_text(
                "❌ У вас нет прав для управления каналами",
                reply_markup=create_back_button()
            )
            return
        
        channels = await db.get_channels()
        
        keyboard = [
            [InlineKeyboardButton("➕ Добавить канал", callback_data="add_channel")],
        ]
        
        if channels:
            keyboard.append([InlineKeyboardButton("📋 Список каналов", callback_data="list_channels")])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])
        
        text = f"📺 <b>Управление каналами</b>\n\nВсего каналов: {len(channels)}"
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    
    @staticmethod
    async def list_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Список каналов"""
        query = update.callback_query
        await query.answer()
        
        channels = await db.get_channels()
        
        if not channels:
            await query.edit_message_text(
                "📺 Каналы не добавлены",
                reply_markup=create_back_button("manage_channels")
            )
            return
        
        text = "📺 <b>Список каналов:</b>\n\n"
        keyboard = []
        
        for channel in channels:
            title = truncate_text(channel['title'], 30)
            text += f"• {title}\n"
            text += f"  ID: <code>{channel['telegram_id']}</code>\n"
            if channel.get('username'):
                text += f"  @{channel['username']}\n"
            text += "\n"
            
            keyboard.append([
                InlineKeyboardButton(
                    f"⚙️ {title}", 
                    callback_data=f"channel_settings_{channel['telegram_id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="manage_channels")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    
    @staticmethod
    async def add_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало добавления канала"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        
        # Устанавливаем состояние
        await db.set_user_state(user.id, 'waiting_channel_id')
        
        text = (
            "➕ <b>Добавление канала</b>\n\n"
            "Отправьте ID канала или перешлите любое сообщение из канала.\n\n"
            "💡 <b>Как получить ID канала:</b>\n"
            "1. Добавьте бота в канал как администратора\n"
            "2. Дайте боту права на публикацию сообщений\n"
            "3. Отправьте ID канала (например: -1001234567890)\n"
            "   или перешлите сообщение из канала\n\n"
            "❌ Для отмены используйте /cancel"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=create_cancel_button(),
            parse_mode='HTML'
        )
        
        return WAITING_FOR_CHANNEL_ID

class PostHandlers:
    """Обработчики создания постов"""
    
    @staticmethod
    async def create_post_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало создания поста"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        if not await db.is_admin(user.id):
            await query.edit_message_text(
                "❌ У вас нет прав для создания постов",
                reply_markup=create_back_button()
            )
            return
        
        # Проверяем наличие каналов
        channels = await db.get_channels()
        if not channels:
            await query.edit_message_text(
                "❌ Сначала добавьте хотя бы один канал",
                reply_markup=create_back_button("manage_channels")
            )
            return
        
        # Выбор канала
        keyboard = []
        for channel in channels:
            title = truncate_text(channel['title'], 30)
            keyboard.append([
                InlineKeyboardButton(
                    title, 
                    callback_data=f"select_channel_{channel['telegram_id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])
        
        await query.edit_message_text(
            "📝 <b>Создание поста</b>\n\nВыберите канал для публикации:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    
    @staticmethod
    async def select_channel_for_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выбор канала для поста"""
        query = update.callback_query
        await query.answer()
        
        channel_id = int(query.data.split('_')[2])
        user = query.from_user
        
        # Сохраняем выбранный канал в состоянии
        await db.set_user_state(user.id, 'creating_post', {
            'channel_id': channel_id,
            'step': 'text'
        })
        
        # Получаем информацию о канале
        channels = await db.get_channels()
        channel = next((c for c in channels if c['telegram_id'] == channel_id), None)
        
        if not channel:
            await query.edit_message_text(
                "❌ Канал не найден",
                reply_markup=create_back_button("create_post")
            )
            return
        
        keyboard = [
            [InlineKeyboardButton("⏭️ Пропустить текст", callback_data="skip_text")],
            [InlineKeyboardButton("❌ Отменить", callback_data="cancel")]
        ]
        
        text = (
            f"📝 <b>Создание поста для канала:</b>\n"
            f"📺 {channel['title']}\n\n"
            "1️⃣ <b>Шаг 1: Текст поста</b>\n\n"
            "Отправьте текст для поста или нажмите 'Пропустить текст'.\n\n"
            "💡 Поддерживается HTML форматирование:\n"
            "• <code>&lt;b&gt;жирный&lt;/b&gt;</code>\n"
            "• <code>&lt;i&gt;курсив&lt;/i&gt;</code>\n"
            "• <code>&lt;u&gt;подчеркнутый&lt;/u&gt;</code>\n"
            "• <code>&lt;code&gt;моноширинный&lt;/code&gt;</code>\n"
            "• <code>&lt;a href=\"url\"&gt;ссылка&lt;/a&gt;</code>"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        return WAITING_FOR_TEXT

# Продолжение в следующем файле...