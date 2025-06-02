import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Tuple
from telegram import Bot
from telegram.error import TelegramError
from database import db
from utils import ButtonManager
import threading
import time

logger = logging.getLogger(__name__)

class PostScheduler:
    """Планировщик публикации постов"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.running = False
        self.thread = None
    
    def start(self):
        """Запустить планировщик"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.thread.start()
        logger.info("Планировщик постов запущен")
    
    def stop(self):
        """Остановить планировщик"""
        self.running = False
        if self.thread:
            self.thread.join()
        logger.info("Планировщик постов остановлен")
    
    def _run_scheduler(self):
        """Основной цикл планировщика"""
        while self.running:
            try:
                # Проверяем, есть ли уже event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        raise RuntimeError("Loop is closed")
                except RuntimeError:
                    # Создаем новый event loop для этого потока
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                # Выполняем проверку и публикацию постов
                if not loop.is_running():
                    loop.run_until_complete(self._check_and_publish_posts())
                else:
                    # Если loop уже запущен, создаем задачу
                    asyncio.create_task(self._check_and_publish_posts())
                
            except Exception as e:
                logger.error(f"Ошибка в планировщике: {e}")
            
            # Ждем 60 секунд перед следующей проверкой
            time.sleep(60)
    
    async def _check_and_publish_posts(self):
        """Проверить и опубликовать готовые посты"""
        try:
            posts_to_publish = await db.get_posts_to_publish()
            
            for post in posts_to_publish:
                await self._publish_post(post)
                
        except Exception as e:
            logger.error(f"Ошибка при проверке постов к публикации: {e}")
    
    async def _publish_post(self, post: Dict):
        """Опубликовать пост"""
        try:
            channel_id = post['channel_id']
            post_id = post['id']
            
            # Подготавливаем контент
            text = post.get('text_content')
            media_type = post.get('media_type')
            media_file_id = post.get('media_file_id')
            media_caption = post.get('media_caption')
            parse_mode = post.get('parse_mode', 'HTML')
            reply_markup_data = post.get('reply_markup')
            
            # Создаем клавиатуру если есть
            reply_markup = None
            if reply_markup_data:
                try:
                    buttons = reply_markup_data if isinstance(reply_markup_data, list) else []
                    reply_markup = ButtonManager.create_inline_keyboard(buttons)
                except Exception as e:
                    logger.error(f"Ошибка создания клавиатуры для поста {post_id}: {e}")
            
            message = None
            
            # Публикуем в зависимости от типа контента
            if media_type and media_file_id:
                # Пост с медиа
                caption = media_caption or text
                
                if media_type == 'photo':
                    message = await self.bot.send_photo(
                        chat_id=channel_id,
                        photo=media_file_id,
                        caption=caption,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup
                    )
                elif media_type == 'video':
                    message = await self.bot.send_video(
                        chat_id=channel_id,
                        video=media_file_id,
                        caption=caption,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup
                    )
                elif media_type == 'document':
                    message = await self.bot.send_document(
                        chat_id=channel_id,
                        document=media_file_id,
                        caption=caption,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup
                    )
                elif media_type == 'audio':
                    message = await self.bot.send_audio(
                        chat_id=channel_id,
                        audio=media_file_id,
                        caption=caption,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup
                    )
                elif media_type == 'voice':
                    message = await self.bot.send_voice(
                        chat_id=channel_id,
                        voice=media_file_id,
                        caption=caption,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup
                    )
                elif media_type == 'animation':
                    message = await self.bot.send_animation(
                        chat_id=channel_id,
                        animation=media_file_id,
                        caption=caption,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup
                    )
                else:
                    # Неизвестный тип медиа, отправляем как документ
                    message = await self.bot.send_document(
                        chat_id=channel_id,
                        document=media_file_id,
                        caption=caption,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup
                    )
            
            elif text:
                # Текстовый пост
                message = await self.bot.send_message(
                    chat_id=channel_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
            
            else:
                # Пост без контента
                raise ValueError("Пост не содержит ни текста, ни медиа")
            
            # Обновляем статус поста
            if message:
                await db.update_post_status(
                    post_id=post_id,
                    status='published',
                    message_id=message.message_id
                )
                logger.info(f"Пост {post_id} успешно опубликован в канале {channel_id}")
                
                # Логируем действие
                await db.log_action(
                    user_id=post['created_by'],
                    action='post_published',
                    details={
                        'post_id': post_id,
                        'channel_id': channel_id,
                        'message_id': message.message_id
                    }
                )
            
        except TelegramError as e:
            error_message = f"Telegram ошибка: {e}"
            logger.error(f"Ошибка публикации поста {post['id']}: {error_message}")
            
            # Обновляем статус поста с ошибкой
            await db.update_post_status(
                post_id=post['id'],
                status='failed',
                error_message=error_message
            )
            
        except Exception as e:
            error_message = f"Общая ошибка: {e}"
            logger.error(f"Ошибка публикации поста {post['id']}: {error_message}")
            
            # Обновляем статус поста с ошибкой
            await db.update_post_status(
                post_id=post['id'],
                status='failed',
                error_message=error_message
            )
    
    async def publish_post_now(self, post_id: int) -> bool:
        """Опубликовать пост немедленно"""
        try:
            post = await db.get_post(post_id)
            if not post:
                return False
            
            await self._publish_post(post)
            return True
            
        except Exception as e:
            logger.error(f"Ошибка немедленной публикации поста {post_id}: {e}")
            return False

class ChannelManager:
    """Менеджер каналов"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
    
    async def check_bot_permissions(self, channel_id: int) -> Dict[str, bool]:
        """Проверить права бота в канале"""
        try:
            chat_member = await self.bot.get_chat_member(channel_id, self.bot.id)
            
            permissions = {
                'can_post_messages': False,
                'can_edit_messages': False,
                'can_delete_messages': False,
                'can_manage_chat': False
            }
            
            if chat_member.status in ['administrator', 'creator']:
                permissions['can_post_messages'] = getattr(chat_member, 'can_post_messages', True)
                permissions['can_edit_messages'] = getattr(chat_member, 'can_edit_messages', True)
                permissions['can_delete_messages'] = getattr(chat_member, 'can_delete_messages', True)
                permissions['can_manage_chat'] = getattr(chat_member, 'can_manage_chat', False)
            
            return permissions
            
        except TelegramError as e:
            logger.error(f"Ошибка проверки прав в канале {channel_id}: {e}")
            return {
                'can_post_messages': False,
                'can_edit_messages': False,
                'can_delete_messages': False,
                'can_manage_chat': False
            }
    
    async def get_channel_info(self, channel_id: int) -> Dict:
        """Получить информацию о канале"""
        try:
            chat = await self.bot.get_chat(channel_id)
            
            return {
                'id': chat.id,
                'title': chat.title,
                'username': chat.username,
                'description': chat.description,
                'type': chat.type,
                'member_count': getattr(chat, 'member_count', None)
            }
            
        except TelegramError as e:
            logger.error(f"Ошибка получения информации о канале {channel_id}: {e}")
            return {}
    
    async def validate_channel_access(self, channel_id: int) -> Tuple[bool, str]:
        """Проверить доступ к каналу"""
        try:
            # Получаем информацию о канале
            chat_info = await self.get_channel_info(channel_id)
            if not chat_info:
                return False, "Не удалось получить информацию о канале"
            
            # Проверяем права бота
            permissions = await self.check_bot_permissions(channel_id)
            if not permissions['can_post_messages']:
                return False, "Бот не имеет права публиковать сообщения в этом канале"
            
            return True, "Доступ к каналу подтвержден"
            
        except Exception as e:
            logger.error(f"Ошибка валидации доступа к каналу {channel_id}: {e}")
            return False, f"Ошибка проверки доступа: {e}"

# Глобальные экземпляры
post_scheduler = None
channel_manager = None

def init_scheduler(bot: Bot):
    """Инициализировать планировщик"""
    global post_scheduler, channel_manager
    post_scheduler = PostScheduler(bot)
    channel_manager = ChannelManager(bot)
    return post_scheduler, channel_manager