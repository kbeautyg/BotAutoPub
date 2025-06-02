import logging
from typing import Dict, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
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

class PostConversationHandlers:
    """Обработчики сценария создания поста"""
    
    @staticmethod
    async def handle_post_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текста поста"""
        user = update.effective_user
        message = update.message
        
        # Получаем состояние пользователя
        state = await db.get_user_state(user.id)
        if not state or state.get('state') != 'creating_post':
            await message.reply_text(
                "❌ Сессия создания поста не найдена. Начните заново.",
                reply_markup=create_main_menu_keyboard(await db.is_admin(user.id))
            )
            return ConversationHandler.END
        
        post_data = state.get('data', {})
        text = message.text
        
        # Проверяем длину текста
        if len(text) > Config.MAX_TEXT_LENGTH:
            await message.reply_text(
                f"❌ Текст слишком длинный. Максимум {Config.MAX_TEXT_LENGTH} символов.\n"
                f"Ваш текст: {len(text)} символов."
            )
            return WAITING_FOR_TEXT
        
        # Сохраняем текст
        post_data['text'] = text
        post_data['step'] = 'media'
        
        await db.set_user_state(user.id, 'creating_post', post_data)
        
        # Переходим к следующему шагу
        keyboard = [
            [InlineKeyboardButton("⏭️ Пропустить медиа", callback_data="skip_media")],
            [InlineKeyboardButton("🔙 Назад к тексту", callback_data="back_to_text")],
            [InlineKeyboardButton("❌ Отменить", callback_data="cancel")]
        ]
        
        await message.reply_text(
            "2️⃣ <b>Шаг 2: Медиа</b>\n\n"
            "Отправьте фото, видео, документ или другой медиафайл для поста.\n"
            "Или нажмите 'Пропустить медиа' для создания текстового поста.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        return WAITING_FOR_MEDIA
    
    @staticmethod
    async def skip_text_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Пропустить текст"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        state = await db.get_user_state(user.id)
        
        if not state or state.get('state') != 'creating_post':
            await query.edit_message_text(
                "❌ Сессия создания поста не найдена",
                reply_markup=create_main_menu_keyboard(await db.is_admin(user.id))
            )
            return ConversationHandler.END
        
        post_data = state.get('data', {})
        post_data['step'] = 'media'
        
        await db.set_user_state(user.id, 'creating_post', post_data)
        
        keyboard = [
            [InlineKeyboardButton("⏭️ Пропустить медиа", callback_data="skip_media")],
            [InlineKeyboardButton("🔙 Назад к тексту", callback_data="back_to_text")],
            [InlineKeyboardButton("❌ Отменить", callback_data="cancel")]
        ]
        
        await query.edit_message_text(
            "2️⃣ <b>Шаг 2: Медиа</b>\n\n"
            "Отправьте фото, видео, документ или другой медиафайл для поста.\n"
            "Или нажмите 'Пропустить медиа' для создания текстового поста.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        return WAITING_FOR_MEDIA
    
    @staticmethod
    async def handle_post_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка медиа для поста"""
        user = update.effective_user
        message = update.message
        
        # Получаем состояние пользователя
        state = await db.get_user_state(user.id)
        if not state or state.get('state') != 'creating_post':
            await message.reply_text(
                "❌ Сессия создания поста не найдена",
                reply_markup=create_main_menu_keyboard(await db.is_admin(user.id))
            )
            return ConversationHandler.END
        
        post_data = state.get('data', {})
        
        # Определяем тип медиа и file_id
        media_type = None
        file_id = None
        caption = None
        
        if message.photo:
            media_type = 'photo'
            file_id = message.photo[-1].file_id
            caption = message.caption
        elif message.video:
            media_type = 'video'
            file_id = message.video.file_id
            caption = message.caption
        elif message.document:
            media_type = 'document'
            file_id = message.document.file_id
            caption = message.caption
        elif message.audio:
            media_type = 'audio'
            file_id = message.audio.file_id
            caption = message.caption
        elif message.voice:
            media_type = 'voice'
            file_id = message.voice.file_id
            caption = message.caption
        elif message.animation:
            media_type = 'animation'
            file_id = message.animation.file_id
            caption = message.caption
        else:
            await message.reply_text(
                "❌ Неподдерживаемый тип медиа. Попробуйте еще раз."
            )
            return WAITING_FOR_MEDIA
        
        # Проверяем длину подписи
        if caption and len(caption) > Config.MAX_CAPTION_LENGTH:
            await message.reply_text(
                f"❌ Подпись к медиа слишком длинная. Максимум {Config.MAX_CAPTION_LENGTH} символов.\n"
                f"Ваша подпись: {len(caption)} символов."
            )
            return WAITING_FOR_MEDIA
        
        # Сохраняем медиа
        post_data['media_type'] = media_type
        post_data['media_file_id'] = file_id
        post_data['media_caption'] = caption
        post_data['step'] = 'buttons'
        
        await db.set_user_state(user.id, 'creating_post', post_data)
        
        # Переходим к следующему шагу
        keyboard = [
            [InlineKeyboardButton("⏭️ Пропустить кнопки", callback_data="skip_buttons")],
            [InlineKeyboardButton("🔙 Назад к медиа", callback_data="back_to_media")],
            [InlineKeyboardButton("❌ Отменить", callback_data="cancel")]
        ]
        
        await message.reply_text(
            "3️⃣ <b>Шаг 3: Кнопки</b>\n\n"
            "Отправьте кнопки для поста в формате:\n\n"
            "<code>Текст кнопки - https://example.com</code>\n"
            "<code>Кнопка 1 | Кнопка 2 - https://example.com</code>\n\n"
            "Каждая строка = новый ряд кнопок\n"
            "Символ | разделяет кнопки в одном ряду\n\n"
            "Или нажмите 'Пропустить кнопки'.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        return WAITING_FOR_BUTTONS
    
    @staticmethod
    async def skip_media_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Пропустить медиа"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        state = await db.get_user_state(user.id)
        
        if not state or state.get('state') != 'creating_post':
            await query.edit_message_text(
                "❌ Сессия создания поста не найдена",
                reply_markup=create_main_menu_keyboard(await db.is_admin(user.id))
            )
            return ConversationHandler.END
        
        post_data = state.get('data', {})
        post_data['step'] = 'buttons'
        
        await db.set_user_state(user.id, 'creating_post', post_data)
        
        keyboard = [
            [InlineKeyboardButton("⏭️ Пропустить кнопки", callback_data="skip_buttons")],
            [InlineKeyboardButton("🔙 Назад к медиа", callback_data="back_to_media")],
            [InlineKeyboardButton("❌ Отменить", callback_data="cancel")]
        ]
        
        await query.edit_message_text(
            "3️⃣ <b>Шаг 3: Кнопки</b>\n\n"
            "Отправьте кнопки для поста в формате:\n\n"
            "<code>Текст кнопки - https://example.com</code>\n"
            "<code>Кнопка 1 | Кнопка 2 - https://example.com</code>\n\n"
            "Каждая строка = новый ряд кнопок\n"
            "Символ | разделяет кнопки в одном ряду\n\n"
            "Или нажмите 'Пропустить кнопки'.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        return WAITING_FOR_BUTTONS
    
    @staticmethod
    async def handle_post_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка кнопок для поста"""
        user = update.effective_user
        message = update.message
        
        # Получаем состояние пользователя
        state = await db.get_user_state(user.id)
        if not state or state.get('state') != 'creating_post':
            await message.reply_text(
                "❌ Сессия создания поста не найдена",
                reply_markup=create_main_menu_keyboard(await db.is_admin(user.id))
            )
            return ConversationHandler.END
        
        post_data = state.get('data', {})
        buttons_text = message.text
        
        # Парсим кнопки
        try:
            buttons = ButtonManager.parse_buttons_text(buttons_text)
            
            if not buttons:
                await message.reply_text(
                    "❌ Не удалось распознать кнопки. Проверьте формат:\n\n"
                    "<code>Текст кнопки - https://example.com</code>\n"
                    "<code>Кнопка 1 | Кнопка 2 - https://example.com</code>",
                    parse_mode='HTML'
                )
                return WAITING_FOR_BUTTONS
            
            # Проверяем URL в кнопках
            for row in buttons:
                for button in row:
                    url = button.get('url', '')
                    if url and url != '#' and not validate_url(url):
                        await message.reply_text(
                            f"❌ Некорректный URL в кнопке '{button.get('text', '')}': {url}\n"
                            "Проверьте правильность ссылки."
                        )
                        return WAITING_FOR_BUTTONS
            
            # Сохраняем кнопки
            post_data['buttons'] = buttons
            post_data['step'] = 'schedule'
            
            await db.set_user_state(user.id, 'creating_post', post_data)
            
            # Переходим к следующему шагу
            keyboard = [
                [InlineKeyboardButton("📤 Опубликовать сейчас", callback_data="publish_now")],
                [InlineKeyboardButton("⏰ Отложить публикацию", callback_data="schedule_post")],
                [InlineKeyboardButton("🔙 Назад к кнопкам", callback_data="back_to_buttons")],
                [InlineKeyboardButton("❌ Отменить", callback_data="cancel")]
            ]
            
            await message.reply_text(
                "4️⃣ <b>Шаг 4: Время публикации</b>\n\n"
                "Выберите, когда опубликовать пост:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            
            return WAITING_FOR_SCHEDULE
            
        except Exception as e:
            logger.error(f"Ошибка парсинга кнопок: {e}")
            await message.reply_text(
                "❌ Ошибка обработки кнопок. Проверьте формат и попробуйте еще раз."
            )
            return WAITING_FOR_BUTTONS
    
    @staticmethod
    async def skip_buttons_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Пропустить кнопки"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        state = await db.get_user_state(user.id)
        
        if not state or state.get('state') != 'creating_post':
            await query.edit_message_text(
                "❌ Сессия создания поста не найдена",
                reply_markup=create_main_menu_keyboard(await db.is_admin(user.id))
            )
            return ConversationHandler.END
        
        post_data = state.get('data', {})
        post_data['step'] = 'schedule'
        
        await db.set_user_state(user.id, 'creating_post', post_data)
        
        keyboard = [
            [InlineKeyboardButton("📤 Опубликовать сейчас", callback_data="publish_now")],
            [InlineKeyboardButton("⏰ Отложить публикацию", callback_data="schedule_post")],
            [InlineKeyboardButton("🔙 Назад к кнопкам", callback_data="back_to_buttons")],
            [InlineKeyboardButton("❌ Отменить", callback_data="cancel")]
        ]
        
        await query.edit_message_text(
            "4️⃣ <b>Шаг 4: Время публикации</b>\n\n"
            "Выберите, когда опубликовать пост:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        return WAITING_FOR_SCHEDULE
    
    @staticmethod
    async def publish_now_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Опубликовать сейчас"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        state = await db.get_user_state(user.id)
        
        if not state or state.get('state') != 'creating_post':
            await query.edit_message_text(
                "❌ Сессия создания поста не найдена",
                reply_markup=create_main_menu_keyboard(await db.is_admin(user.id))
            )
            return ConversationHandler.END
        
        post_data = state.get('data', {})
        
        # Показываем превью и подтверждение
        await PostConversationHandlers.show_post_preview(query, post_data, immediate=True)
        
        return CONFIRM_POST
    
    @staticmethod
    async def schedule_post_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отложить публикацию"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        db_user = await db.get_user(user.id)
        user_timezone = db_user.get('timezone', 'UTC') if db_user else 'UTC'
        
        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_schedule")],
            [InlineKeyboardButton("❌ Отменить", callback_data="cancel")]
        ]
        
        await query.edit_message_text(
            "⏰ <b>Отложенная публикация</b>\n\n"
            f"Ваш часовой пояс: {user_timezone}\n\n"
            "Отправьте время публикации в одном из форматов:\n\n"
            "• <code>15:30</code> - сегодня в 15:30\n"
            "• <code>25.12 15:30</code> - 25 декабря в 15:30\n"
            "• <code>25.12.2024 15:30</code> - полная дата\n"
            "• <code>через 30 мин</code> - через 30 минут\n"
            "• <code>через 2 час</code> - через 2 часа\n"
            "• <code>завтра в 10:00</code> - завтра в 10:00",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        return WAITING_FOR_SCHEDULE
    
    @staticmethod
    async def handle_schedule_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка времени публикации"""
        user = update.effective_user
        message = update.message
        
        # Получаем состояние пользователя
        state = await db.get_user_state(user.id)
        if not state or state.get('state') != 'creating_post':
            await message.reply_text(
                "❌ Сессия создания поста не найдена",
                reply_markup=create_main_menu_keyboard(await db.is_admin(user.id))
            )
            return ConversationHandler.END
        
        post_data = state.get('data', {})
        time_text = message.text
        
        # Получаем часовой пояс пользователя
        db_user = await db.get_user(user.id)
        user_timezone = db_user.get('timezone', 'UTC') if db_user else 'UTC'
        
        # Парсим время
        scheduled_time = DateTimeParser.parse_datetime_input(time_text, user_timezone)
        
        if not scheduled_time:
            await message.reply_text(
                "❌ Не удалось распознать время. Попробуйте еще раз.\n\n"
                "Примеры правильного формата:\n"
                "• 15:30\n"
                "• 25.12 15:30\n"
                "• через 30 мин\n"
                "• завтра в 10:00"
            )
            return WAITING_FOR_SCHEDULE
        
        # Проверяем, что время в будущем
        if scheduled_time <= datetime.utcnow():
            await message.reply_text(
                "❌ Время публикации должно быть в будущем. Попробуйте еще раз."
            )
            return WAITING_FOR_SCHEDULE
        
        # Сохраняем время
        post_data['scheduled_time'] = scheduled_time
        await db.set_user_state(user.id, 'creating_post', post_data)
        
        # Показываем превью
        await PostConversationHandlers.show_post_preview(message, post_data, immediate=False)
        
        return CONFIRM_POST
    
    @staticmethod
    async def show_post_preview(update_or_message, post_data: Dict, immediate: bool = True):
        """Показать превью поста"""
        # Получаем информацию о канале
        channels = await db.get_channels()
        channel = next((c for c in channels if c['telegram_id'] == post_data['channel_id']), None)
        
        if not channel:
            text = "❌ Канал не найден"
            keyboard = create_main_menu_keyboard(True)
        else:
            # Формируем превью
            preview_text = f"📺 <b>Канал:</b> {channel['title']}\n\n"
            
            if post_data.get('text'):
                preview_text += f"📝 <b>Текст:</b>\n{post_data['text'][:500]}"
                if len(post_data['text']) > 500:
                    preview_text += "..."
                preview_text += "\n\n"
            
            if post_data.get('media_type'):
                media_icons = {
                    'photo': '🖼️', 'video': '🎥', 'document': '📄',
                    'audio': '🎵', 'voice': '🎤', 'animation': '🎬'
                }
                icon = media_icons.get(post_data['media_type'], '📎')
                preview_text += f"{icon} <b>Медиа:</b> {post_data['media_type']}\n"
                
                if post_data.get('media_caption'):
                    preview_text += f"📝 <b>Подпись:</b> {post_data['media_caption'][:200]}"
                    if len(post_data['media_caption']) > 200:
                        preview_text += "..."
                    preview_text += "\n"
                preview_text += "\n"
            
            if post_data.get('buttons'):
                preview_text += "🔘 <b>Кнопки:</b>\n"
                for row in post_data['buttons']:
                    row_text = " | ".join([btn.get('text', 'Кнопка') for btn in row])
                    preview_text += f"• {row_text}\n"
                preview_text += "\n"
            
            if immediate:
                preview_text += "⏰ <b>Публикация:</b> Немедленно"
            else:
                scheduled_time = post_data.get('scheduled_time')
                if scheduled_time:
                    # Получаем часовой пояс пользователя для отображения
                    user_id = update_or_message.from_user.id if hasattr(update_or_message, 'from_user') else update_or_message.chat.id
                    db_user = await db.get_user(user_id)
                    user_timezone = db_user.get('timezone', 'UTC') if db_user else 'UTC'
                    
                    formatted_time = DateTimeParser.format_datetime(scheduled_time, user_timezone)
                    preview_text += f"⏰ <b>Публикация:</b> {formatted_time}"
            
            keyboard = [
                [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_post")],
                [InlineKeyboardButton("✏️ Редактировать", callback_data="edit_post")],
                [InlineKeyboardButton("❌ Отменить", callback_data="cancel")]
            ]
        
        if hasattr(update_or_message, 'edit_message_text'):
            # Это callback query
            await update_or_message.edit_message_text(
                preview_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
        else:
            # Это обычное сообщение
            await update_or_message.reply_text(
                preview_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
    
    @staticmethod
    async def confirm_post_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Подтверждение создания поста"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        state = await db.get_user_state(user.id)
        
        if not state or state.get('state') != 'creating_post':
            await query.edit_message_text(
                "❌ Сессия создания поста не найдена",
                reply_markup=create_main_menu_keyboard(await db.is_admin(user.id))
            )
            return ConversationHandler.END
        
        post_data = state.get('data', {})
        
        try:
            # Создаем пост в базе данных
            post_id = await db.create_post(
                channel_id=post_data['channel_id'],
                created_by=user.id,
                text_content=post_data.get('text'),
                media_type=post_data.get('media_type'),
                media_file_id=post_data.get('media_file_id'),
                media_caption=post_data.get('media_caption'),
                parse_mode='HTML',
                reply_markup=post_data.get('buttons'),
                scheduled_time=post_data.get('scheduled_time')
            )
            
            if not post_id:
                await query.edit_message_text(
                    "❌ Ошибка создания поста",
                    reply_markup=create_main_menu_keyboard(True)
                )
                return ConversationHandler.END
            
            # Если пост должен быть опубликован немедленно
            if not post_data.get('scheduled_time'):
                success = await post_scheduler.publish_post_now(post_id)
                if success:
                    message_text = "✅ Пост успешно опубликован!"
                else:
                    message_text = "⚠️ Пост создан, но возникла ошибка при публикации. Проверьте права бота в канале."
            else:
                # Получаем часовой пояс пользователя для отображения
                db_user = await db.get_user(user.id)
                user_timezone = db_user.get('timezone', 'UTC') if db_user else 'UTC'
                
                formatted_time = DateTimeParser.format_datetime(post_data['scheduled_time'], user_timezone)
                message_text = f"✅ Пост запланирован на {formatted_time}"
            
            # Очищаем состояние
            await db.clear_user_state(user.id)
            
            # Логируем действие
            await db.log_action(user.id, 'post_created', {
                'post_id': post_id,
                'channel_id': post_data['channel_id'],
                'scheduled': bool(post_data.get('scheduled_time'))
            })
            
            await query.edit_message_text(
                message_text,
                reply_markup=create_main_menu_keyboard(True)
            )
            
            return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"Ошибка создания поста: {e}")
            await query.edit_message_text(
                "❌ Ошибка создания поста. Попробуйте еще раз.",
                reply_markup=create_main_menu_keyboard(True)
            )
            return ConversationHandler.END

class ChannelConversationHandlers:
    """Обработчики сценария добавления канала"""
    
    @staticmethod
    async def handle_channel_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ID канала"""
        user = update.effective_user
        message = update.message
        
        # Получаем состояние пользователя
        state = await db.get_user_state(user.id)
        if not state or state.get('state') != 'waiting_channel_id':
            await message.reply_text(
                "❌ Сессия добавления канала не найдена",
                reply_markup=create_main_menu_keyboard(await db.is_admin(user.id))
            )
            return ConversationHandler.END
        
        # Пытаемся получить ID канала
        channel_id = None
        
        if message.forward_from_chat:
            # Переслано из канала
            channel_id = message.forward_from_chat.id
        elif message.text:
            # Введен ID вручную
            text = message.text.strip()
            try:
                # Убираем @ если есть
                if text.startswith('@'):
                    text = text[1:]
                
                # Пытаемся преобразовать в число
                if text.lstrip('-').isdigit():
                    channel_id = int(text)
                else:
                    # Возможно, это username канала
                    try:
                        chat = await context.bot.get_chat(f"@{text}")
                        channel_id = chat.id
                    except TelegramError:
                        pass
            except ValueError:
                pass
        
        if not channel_id:
            await message.reply_text(
                "❌ Не удалось определить ID канала.\n\n"
                "Попробуйте:\n"
                "• Переслать сообщение из канала\n"
                "• Ввести числовой ID (например: -1001234567890)\n"
                "• Ввести username канала (например: @mychannel)"
            )
            return WAITING_FOR_CHANNEL_ID
        
        # Проверяем доступ к каналу
        try:
            access_ok, access_message = await channel_manager.validate_channel_access(channel_id)
            
            if not access_ok:
                await message.reply_text(
                    f"❌ {access_message}\n\n"
                    "Убедитесь, что:\n"
                    "• Бот добавлен в канал как администратор\n"
                    "• У бота есть права на публикацию сообщений\n"
                    "• ID канала указан правильно"
                )
                return WAITING_FOR_CHANNEL_ID
            
            # Получаем информацию о канале
            channel_info = await channel_manager.get_channel_info(channel_id)
            
            if not channel_info:
                await message.reply_text(
                    "❌ Не удалось получить информацию о канале"
                )
                return WAITING_FOR_CHANNEL_ID
            
            # Проверяем, не добавлен ли канал уже
            existing_channels = await db.get_channels()
            if any(ch['telegram_id'] == channel_id for ch in existing_channels):
                await message.reply_text(
                    "❌ Этот канал уже добавлен в бота"
                )
                return WAITING_FOR_CHANNEL_ID
            
            # Добавляем канал в базу данных
            success = await db.add_channel(
                telegram_id=channel_id,
                title=channel_info.get('title', 'Неизвестный канал'),
                username=channel_info.get('username'),
                description=channel_info.get('description'),
                added_by=user.id
            )
            
            if success:
                # Очищаем состояние
                await db.clear_user_state(user.id)
                
                # Логируем действие
                await db.log_action(user.id, 'channel_added', {
                    'channel_id': channel_id,
                    'title': channel_info.get('title')
                })
                
                await message.reply_text(
                    f"✅ Канал успешно добавлен!\n\n"
                    f"📺 <b>Название:</b> {channel_info.get('title')}\n"
                    f"🆔 <b>ID:</b> <code>{channel_id}</code>\n"
                    f"👥 <b>Подписчиков:</b> {channel_info.get('member_count', 'Неизвестно')}",
                    reply_markup=create_main_menu_keyboard(True),
                    parse_mode='HTML'
                )
                
                return ConversationHandler.END
            else:
                await message.reply_text(
                    "❌ Ошибка добавления канала в базу данных"
                )
                return WAITING_FOR_CHANNEL_ID
                
        except Exception as e:
            logger.error(f"Ошибка добавления канала {channel_id}: {e}")
            await message.reply_text(
                "❌ Произошла ошибка при добавлении канала. Попробуйте еще раз."
            )
            return WAITING_FOR_CHANNEL_ID

# Обработчики отмены и возврата
class NavigationHandlers:
    """Обработчики навигации"""
    
    @staticmethod
    async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена текущего действия"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        
        # Очищаем состояние пользователя
        await db.clear_user_state(user.id)
        
        is_admin = await db.is_admin(user.id)
        keyboard = create_main_menu_keyboard(is_admin)
        
        await query.edit_message_text(
            "❌ Действие отменено",
            reply_markup=keyboard
        )
        
        return ConversationHandler.END
    
    @staticmethod
    async def back_to_text_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Возврат к вводу текста"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        state = await db.get_user_state(user.id)
        
        if state and state.get('state') == 'creating_post':
            post_data = state.get('data', {})
            post_data['step'] = 'text'
            
            # Удаляем текст если был
            if 'text' in post_data:
                del post_data['text']
            
            await db.set_user_state(user.id, 'creating_post', post_data)
            
            keyboard = [
                [InlineKeyboardButton("⏭️ Пропустить текст", callback_data="skip_text")],
                [InlineKeyboardButton("❌ Отменить", callback_data="cancel")]
            ]
            
            await query.edit_message_text(
                "1️⃣ <b>Шаг 1: Текст поста</b>\n\n"
                "Отправьте текст для поста или нажмите 'Пропустить текст'.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            
            return WAITING_FOR_TEXT
        
        return ConversationHandler.END