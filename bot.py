import logging
import asyncio
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)
from telegram.error import TelegramError

from config import Config
from database import db
from scheduler import init_scheduler, post_scheduler
from handlers import BotHandlers, CallbackHandlers, ChannelHandlers, PostHandlers
from utils import create_back_button, create_main_menu_keyboard
from conversation_handlers import (
    PostConversationHandlers, ChannelConversationHandlers, NavigationHandlers,
    WAITING_FOR_TEXT, WAITING_FOR_MEDIA, WAITING_FOR_BUTTONS, 
    WAITING_FOR_SCHEDULE, WAITING_FOR_CHANNEL_ID, WAITING_FOR_CHANNEL_TITLE,
    CONFIRM_POST, EDIT_POST
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TelegramBot:
    """Основной класс Telegram бота"""
    
    def __init__(self):
        self.application = None
        self.scheduler = None
        
    async def initialize(self):
        """Инициализация бота"""
        try:
            # Проверяем конфигурацию
            Config.validate()
            
            
            
            # Создаем приложение
            self.application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
            
            # Инициализируем планировщик
            self.scheduler, _ = init_scheduler(self.application.bot)
            
            # Регистрируем обработчики
            self._register_handlers()
            
            logger.info("Бот успешно инициализирован")
            
        except ValueError as e:
            logger.error(f"Ошибка конфигурации: {e}")
            logger.error("Проверьте переменные окружения в .env файле или настройках Railway")
            raise
        except Exception as e:
            logger.error(f"Ошибка инициализации бота: {e}")
            raise
    
    def _register_handlers(self):
        """Регистрация обработчиков"""
        
        # Обработчик создания поста
        post_conversation = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(PostHandlers.create_post_start, pattern="^create_post$"),
                CallbackQueryHandler(PostHandlers.select_channel_for_post, pattern="^select_channel_"),
                CommandHandler("post", PostHandlers.create_post_start)
            ],
            states={
                WAITING_FOR_TEXT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, PostConversationHandlers.handle_post_text),
                    CallbackQueryHandler(PostConversationHandlers.skip_text_callback, pattern="^skip_text$"),
                ],
                WAITING_FOR_MEDIA: [
                    MessageHandler(
                        (filters.PHOTO | filters.VIDEO | filters.DOCUMENT | 
                         filters.AUDIO | filters.VOICE | filters.ANIMATION) & ~filters.COMMAND,
                        PostConversationHandlers.handle_post_media
                    ),
                    CallbackQueryHandler(PostConversationHandlers.skip_media_callback, pattern="^skip_media$"),
                    CallbackQueryHandler(NavigationHandlers.back_to_text_callback, pattern="^back_to_text$"),
                ],
                WAITING_FOR_BUTTONS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, PostConversationHandlers.handle_post_buttons),
                    CallbackQueryHandler(PostConversationHandlers.skip_buttons_callback, pattern="^skip_buttons$"),
                    CallbackQueryHandler(NavigationHandlers.back_to_text_callback, pattern="^back_to_media$"),
                ],
                WAITING_FOR_SCHEDULE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, PostConversationHandlers.handle_schedule_time),
                    CallbackQueryHandler(PostConversationHandlers.publish_now_callback, pattern="^publish_now$"),
                    CallbackQueryHandler(PostConversationHandlers.schedule_post_callback, pattern="^schedule_post$"),
                ],
                CONFIRM_POST: [
                    CallbackQueryHandler(PostConversationHandlers.confirm_post_callback, pattern="^confirm_post$"),
                ]
            },
            fallbacks=[
                CallbackQueryHandler(NavigationHandlers.cancel_callback, pattern="^cancel$"),
                CommandHandler("cancel", BotHandlers.cancel_command)
            ]
        )
        
        # Обработчик добавления канала
        channel_conversation = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(ChannelHandlers.add_channel_start, pattern="^add_channel$")
            ],
            states={
                WAITING_FOR_CHANNEL_ID: [
                    MessageHandler(
                        (filters.TEXT | filters.FORWARDED) & ~filters.COMMAND,
                        ChannelConversationHandlers.handle_channel_id
                    ),
                ]
            },
            fallbacks=[
                CallbackQueryHandler(NavigationHandlers.cancel_callback, pattern="^cancel$"),
                CommandHandler("cancel", BotHandlers.cancel_command)
            ]
        )
        
        # Основные команды
        self.application.add_handler(CommandHandler("start", BotHandlers.start_command))
        self.application.add_handler(CommandHandler("help", BotHandlers.help_command))
        self.application.add_handler(CommandHandler("menu", BotHandlers.menu_command))
        self.application.add_handler(CommandHandler("cancel", BotHandlers.cancel_command))
        
        # Команды для админов (нужно создать обертки для команд)
        self.application.add_handler(CommandHandler("channels", self._channels_command))
        self.application.add_handler(CommandHandler("scheduled", self._scheduled_posts_command))
        self.application.add_handler(CommandHandler("stats", self._stats_command))
        
        # Conversation handlers
        self.application.add_handler(post_conversation)
        self.application.add_handler(channel_conversation)
        
        # Callback handlers
        self.application.add_handler(CallbackQueryHandler(CallbackHandlers.main_menu_callback, pattern="^main_menu$"))
        self.application.add_handler(CallbackQueryHandler(CallbackHandlers.settings_callback, pattern="^settings$"))
        self.application.add_handler(CallbackQueryHandler(CallbackHandlers.change_timezone_callback, pattern="^(change_timezone|tz_.+)$"))
        self.application.add_handler(CallbackQueryHandler(CallbackHandlers.back_to_settings_callback, pattern="^back_to_settings$"))
        
        # Управление каналами
        self.application.add_handler(CallbackQueryHandler(ChannelHandlers.manage_channels_callback, pattern="^manage_channels$"))
        self.application.add_handler(CallbackQueryHandler(ChannelHandlers.list_channels_callback, pattern="^list_channels$"))
        
        # Отложенные посты
        self.application.add_handler(CallbackQueryHandler(self._scheduled_posts_callback, pattern="^scheduled_posts$"))
        self.application.add_handler(CallbackQueryHandler(self._view_scheduled_post, pattern="^view_post_"))
        self.application.add_handler(CallbackQueryHandler(self._delete_scheduled_post, pattern="^delete_post_"))
        
        # Статистика
        self.application.add_handler(CallbackQueryHandler(self._stats_callback, pattern="^statistics$"))
        
        # Информация
        self.application.add_handler(CallbackQueryHandler(self._info_callback, pattern="^info$"))
        
        # Обработчик ошибок
        self.application.add_error_handler(self._error_handler)
        
        logger.info("Обработчики зарегистрированы")
    
    async def _channels_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда управления каналами"""
        await ChannelHandlers.manage_channels_callback(update, context)
    
    async def _scheduled_posts_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда просмотра отложенных постов"""
        await self._scheduled_posts_callback(update, context)
    
    async def _scheduled_posts_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Просмотр отложенных постов"""
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            user = query.from_user
        else:
            user = update.effective_user
        
        if not await db.is_admin(user.id):
            text = "❌ У вас нет прав для просмотра отложенных постов"
            keyboard = [[]]
        else:
            # Получаем отложенные посты
            scheduled_posts = await db.get_scheduled_posts()
            
            if not scheduled_posts:
                text = "📋 Отложенных постов нет"
                keyboard = [[]]
            else:
                text = f"📋 <b>Отложенные посты ({len(scheduled_posts)}):</b>\n\n"
                keyboard = []
                
                # Получаем информацию о каналах
                channels = await db.get_channels()
                channel_dict = {ch['telegram_id']: ch for ch in channels}
                
                # Получаем часовой пояс пользователя
                db_user = await db.get_user(user.id)
                user_timezone = db_user.get('timezone', 'UTC') if db_user else 'UTC'
                
                for post in scheduled_posts[:10]:  # Показываем только первые 10
                    channel = channel_dict.get(post['channel_id'])
                    channel_name = channel['title'] if channel else 'Неизвестный канал'
                    
                    # Форматируем время
                    from utils import DateTimeParser
                    from datetime import datetime
                    scheduled_time = datetime.fromisoformat(post['scheduled_time'].replace('Z', '+00:00'))
                    formatted_time = DateTimeParser.format_datetime(scheduled_time, user_timezone)
                    
                    # Краткое описание поста
                    post_text = post.get('text_content', '')
                    if post_text:
                        preview = post_text[:50] + "..." if len(post_text) > 50 else post_text
                    else:
                        preview = f"[{post.get('media_type', 'медиа')}]" if post.get('media_type') else "[пустой пост]"
                    
                    text += f"• {channel_name}\n"
                    text += f"  {formatted_time}\n"
                    text += f"  {preview}\n\n"
                    
                    keyboard.append([
                        InlineKeyboardButton(f"👁️ {channel_name[:20]}", callback_data=f"view_post_{post['id']}")
                    ])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])
        
        from telegram import InlineKeyboardMarkup
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
    
    async def _view_scheduled_post(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Просмотр конкретного отложенного поста"""
        query = update.callback_query
        await query.answer()
        
        post_id = int(query.data.split('_')[2])
        user = query.from_user
        
        if not await db.is_admin(user.id):
            await query.edit_message_text(
                "❌ У вас нет прав для просмотра постов",
                reply_markup=create_back_button("scheduled_posts")
            )
            return
        
        # Получаем пост
        post = await db.get_post(post_id)
        if not post:
            await query.edit_message_text(
                "❌ Пост не найден",
                reply_markup=create_back_button("scheduled_posts")
            )
            return
        
        # Получаем информацию о канале
        channels = await db.get_channels()
        channel = next((c for c in channels if c['telegram_id'] == post['channel_id']), None)
        
        # Формируем детальную информацию
        text = f"📋 <b>Детали поста #{post_id}</b>\n\n"
        text += f"📺 <b>Канал:</b> {channel['title'] if channel else 'Неизвестный'}\n"
        
        # Время публикации
        if post.get('scheduled_time'):
            from utils import DateTimeParser
            from datetime import datetime
            
            db_user = await db.get_user(user.id)
            user_timezone = db_user.get('timezone', 'UTC') if db_user else 'UTC'
            
            scheduled_time = datetime.fromisoformat(post['scheduled_time'].replace('Z', '+00:00'))
            formatted_time = DateTimeParser.format_datetime(scheduled_time, user_timezone)
            text += f"⏰ <b>Время публикации:</b> {formatted_time}\n\n"
        
        # Контент
        if post.get('text_content'):
            text += f"📝 <b>Текст:</b>\n{post['text_content'][:500]}"
            if len(post['text_content']) > 500:
                text += "..."
            text += "\n\n"
        
        if post.get('media_type'):
            text += f"📎 <b>Медиа:</b> {post['media_type']}\n"
            if post.get('media_caption'):
                text += f"📝 <b>Подпись:</b> {post['media_caption'][:200]}"
                if len(post['media_caption']) > 200:
                    text += "..."
                text += "\n"
            text += "\n"
        
        if post.get('reply_markup'):
            text += "🔘 <b>Кнопки:</b> Да\n\n"
        
        text += f"📊 <b>Статус:</b> {post['status']}"
        
        keyboard = [
            [InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_post_{post_id}")],
            [InlineKeyboardButton("🔙 К списку", callback_data="scheduled_posts")]
        ]
        
        from telegram import InlineKeyboardMarkup
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    
    async def _delete_scheduled_post(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Удаление отложенного поста"""
        query = update.callback_query
        await query.answer()
        
        post_id = int(query.data.split('_')[2])
        user = query.from_user
        
        if not await db.is_admin(user.id):
            await query.edit_message_text(
                "❌ У вас нет прав для удаления постов",
                reply_markup=create_back_button("scheduled_posts")
            )
            return
        
        # Удаляем пост
        success = await db.delete_post(post_id)
        
        if success:
            # Логируем действие
            await db.log_action(user.id, 'post_deleted', {'post_id': post_id})
            
            await query.edit_message_text(
                "✅ Пост успешно удален",
                reply_markup=create_back_button("scheduled_posts")
            )
        else:
            await query.edit_message_text(
                "❌ Ошибка удаления поста",
                reply_markup=create_back_button("scheduled_posts")
            )
    
    async def _stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда статистики"""
        await self._stats_callback(update, context)
    
    async def _stats_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика бота"""
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            user = query.from_user
        else:
            user = update.effective_user
        
        if not await db.is_admin(user.id):
            text = "❌ У вас нет прав для просмотра статистики"
        else:
            try:
                # Получаем статистику
                channels = await db.get_channels()
                all_posts = await db.get_scheduled_posts()
                
                # Считаем статистику по статусам
                published_count = 0
                scheduled_count = 0
                failed_count = 0
                
                # Получаем все посты для подсчета
                response = db.supabase.table('posts').select('status').execute()
                for post in response.data:
                    status = post.get('status', 'draft')
                    if status == 'published':
                        published_count += 1
                    elif status == 'scheduled':
                        scheduled_count += 1
                    elif status == 'failed':
                        failed_count += 1
                
                text = (
                    "📊 <b>Статистика бота</b>\n\n"
                    f"📺 <b>Каналов:</b> {len(channels)}\n"
                    f"📝 <b>Всего постов:</b> {len(response.data)}\n"
                    f"✅ <b>Опубликовано:</b> {published_count}\n"
                    f"⏰ <b>Запланировано:</b> {scheduled_count}\n"
                    f"❌ <b>Ошибок:</b> {failed_count}\n\n"
                )
                
                # Статистика по каналам
                if channels:
                    text += "<b>По каналам:</b>\n"
                    for channel in channels[:5]:  # Показываем только первые 5
                        # Считаем посты для канала
                        channel_posts = db.supabase.table('posts').select('id').eq('channel_id', channel['telegram_id']).execute()
                        text += f"• {channel['title']}: {len(channel_posts.data)} постов\n"
                
            except Exception as e:
                logger.error(f"Ошибка получения статистики: {e}")
                text = "❌ Ошибка получения статистики"
        
        keyboard = create_back_button("main_menu")
        
        if update.callback_query:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode='HTML')
        else:
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode='HTML')
    
    async def _info_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Информация о боте"""
        query = update.callback_query
        await query.answer()
        
        text = (
            "ℹ️ <b>Информация о боте</b>\n\n"
            "🤖 Бот для управления Telegram каналами\n"
            "📝 Создание и планирование постов\n"
            "⏰ Отложенная публикация\n"
            "📊 Статистика публикаций\n\n"
            "💡 Для получения прав администратора обратитесь к владельцу бота.\n\n"
            "🔧 Версия: 1.0.0"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=create_back_button("main_menu"),
            parse_mode='HTML'
        )
    
    async def _error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок"""
        logger.error(f"Exception while handling an update: {context.error}")
        
        # Пытаемся отправить сообщение об ошибке пользователю
        if isinstance(update, Update) and update.effective_user:
            try:
                await context.bot.send_message(
                    chat_id=update.effective_user.id,
                    text="❌ Произошла ошибка. Попробуйте еще раз или обратитесь к администратору."
                )
            except Exception:
                pass
    
    async def start(self):
        """Запуск бота"""
        try:
            await self.initialize()
            
            # Запускаем планировщик
            if self.scheduler:
                self.scheduler.start()
            
            # Запускаем бота
            logger.info("Запуск бота...")
            await self.application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )
            
        except Exception as e:
            logger.error(f"Ошибка запуска бота: {e}")
            raise
        finally:
            # Останавливаем планировщик при завершении
            if self.scheduler:
                self.scheduler.stop()
    
    async def stop(self):
        """Остановка бота"""
        if self.scheduler:
            self.scheduler.stop()
        
        if self.application:
            await self.application.stop()
        
        logger.info("Бот остановлен")

async def main():
    """Главная функция"""
    bot = TelegramBot()
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())