import asyncio
from typing import Optional, List, Dict, Any
from supabase import create_client, Client
from config import Config
import logging
import json
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

class Database:
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.supabase = None
            self._supabase_ready = False
            Database._initialized = True
    
    def _ensure_initialized(self):
        """Ленивая инициализация Supabase клиента"""
        if not self._supabase_ready:
            if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
                logger.error("Supabase конфигурация не найдена. Проверьте переменные окружения SUPABASE_URL и SUPABASE_KEY")
                raise ValueError("Supabase конфигурация отсутствует")
            
            self.supabase: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
            self._supabase_ready = True
    
    async def get_user(self, telegram_id: int) -> Optional[Dict]:
        """Получить пользователя по telegram_id"""
        try:
            self._ensure_initialized()
            response = self.supabase.table('users').select('*').eq('telegram_id', telegram_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Ошибка получения пользователя {telegram_id}: {e}")
            return None
    
    async def create_user(self, telegram_id: int, username: str = None, 
                         first_name: str = None, last_name: str = None, 
                         is_admin: bool = False) -> bool:
        """Создать нового пользователя"""
        try:
            self._ensure_initialized()
            data = {
                'telegram_id': telegram_id,
                'username': username,
                'first_name': first_name,
                'last_name': last_name,
                'is_admin': is_admin
            }
            response = self.supabase.table('users').insert(data).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Ошибка создания пользователя {telegram_id}: {e}")
            return False
    
    async def update_user_timezone(self, telegram_id: int, timezone: str) -> bool:
        """Обновить часовой пояс пользователя"""
        try:
            self._ensure_initialized()
            response = self.supabase.table('users').update({
                'timezone': timezone
            }).eq('telegram_id', telegram_id).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Ошибка обновления часового пояса для {telegram_id}: {e}")
            return False
    
    async def is_admin(self, telegram_id: int) -> bool:
        """Проверить, является ли пользователь админом"""
        user = await self.get_user(telegram_id)
        return user and user.get('is_admin', False)
    
    async def get_channels(self, active_only: bool = True) -> List[Dict]:
        """Получить список каналов"""
        try:
            self._ensure_initialized()
            query = self.supabase.table('channels').select('*')
            if active_only:
                query = query.eq('is_active', True)
            response = query.execute()
            return response.data
        except Exception as e:
            logger.error(f"Ошибка получения каналов: {e}")
            return []
    
    async def add_channel(self, telegram_id: int, title: str, username: str = None, 
                         description: str = None, added_by: int = None) -> bool:
        """Добавить канал"""
        try:
            self._ensure_initialized()
            data = {
                'telegram_id': telegram_id,
                'title': title,
                'username': username,
                'description': description,
                'added_by': added_by
            }
            response = self.supabase.table('channels').insert(data).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Ошибка добавления канала {telegram_id}: {e}")
            return False
    
    async def remove_channel(self, telegram_id: int) -> bool:
        """Удалить канал (деактивировать)"""
        try:
            self._ensure_initialized()
            response = self.supabase.table('channels').update({
                'is_active': False
            }).eq('telegram_id', telegram_id).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Ошибка удаления канала {telegram_id}: {e}")
            return False
    
    async def create_post(self, channel_id: int, created_by: int, text_content: str = None,
                         media_type: str = None, media_file_id: str = None,
                         media_caption: str = None, parse_mode: str = 'HTML',
                         reply_markup: Dict = None, scheduled_time: datetime = None) -> Optional[int]:
        """Создать пост"""
        try:
            self._ensure_initialized()
            data = {
                'channel_id': channel_id,
                'created_by': created_by,
                'text_content': text_content,
                'media_type': media_type,
                'media_file_id': media_file_id,
                'media_caption': media_caption,
                'parse_mode': parse_mode,
                'reply_markup': reply_markup,
                'scheduled_time': scheduled_time.isoformat() if scheduled_time else None,
                'status': 'scheduled' if scheduled_time else 'draft'
            }
            response = self.supabase.table('posts').insert(data).execute()
            return response.data[0]['id'] if response.data else None
        except Exception as e:
            logger.error(f"Ошибка создания поста: {e}")
            return None
    
    async def get_post(self, post_id: int) -> Optional[Dict]:
        """Получить пост по ID"""
        try:
            self._ensure_initialized()
            response = self.supabase.table('posts').select('*').eq('id', post_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Ошибка получения поста {post_id}: {e}")
            return None
    
    async def get_scheduled_posts(self, channel_id: int = None) -> List[Dict]:
        """Получить отложенные посты"""
        try:
            self._ensure_initialized()
            query = self.supabase.table('posts').select('*').eq('status', 'scheduled')
            if channel_id:
                query = query.eq('channel_id', channel_id)
            response = query.order('scheduled_time').execute()
            return response.data
        except Exception as e:
            logger.error(f"Ошибка получения отложенных постов: {e}")
            return []
    
    async def get_posts_to_publish(self) -> List[Dict]:
        """Получить посты готовые к публикации"""
        try:
            self._ensure_initialized()
            now = datetime.utcnow().isoformat()
            response = self.supabase.table('posts').select('*').eq('status', 'scheduled').lte('scheduled_time', now).execute()
            return response.data
        except Exception as e:
            logger.error(f"Ошибка получения постов к публикации: {e}")
            return []
    
    async def update_post_status(self, post_id: int, status: str, 
                               message_id: int = None, error_message: str = None) -> bool:
        """Обновить статус поста"""
        try:
            self._ensure_initialized()
            data = {'status': status}
            if message_id:
                data['message_id'] = message_id
            if error_message:
                data['error_message'] = error_message
            if status == 'published':
                data['published_time'] = datetime.utcnow().isoformat()
            
            response = self.supabase.table('posts').update(data).eq('id', post_id).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Ошибка обновления статуса поста {post_id}: {e}")
            return False
    
    async def delete_post(self, post_id: int) -> bool:
        """Удалить пост"""
        try:
            self._ensure_initialized()
            response = self.supabase.table('posts').delete().eq('id', post_id).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Ошибка удаления поста {post_id}: {e}")
            return False
    
    async def get_user_state(self, telegram_id: int) -> Optional[Dict]:
        """Получить состояние пользователя"""
        try:
            self._ensure_initialized()
            response = self.supabase.table('user_states').select('*').eq('telegram_id', telegram_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Ошибка получения состояния пользователя {telegram_id}: {e}")
            return None
    
    async def set_user_state(self, telegram_id: int, state: str, data: Dict = None) -> bool:
        """Установить состояние пользователя"""
        try:
            self._ensure_initialized()
            state_data = {
                'telegram_id': telegram_id,
                'state': state,
                'data': data or {}
            }
            
            # Проверяем, существует ли уже состояние
            existing = await self.get_user_state(telegram_id)
            if existing:
                response = self.supabase.table('user_states').update(state_data).eq('telegram_id', telegram_id).execute()
            else:
                response = self.supabase.table('user_states').insert(state_data).execute()
            
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Ошибка установки состояния пользователя {telegram_id}: {e}")
            return False
    
    async def clear_user_state(self, telegram_id: int) -> bool:
        """Очистить состояние пользователя"""
        try:
            self._ensure_initialized()
            response = self.supabase.table('user_states').delete().eq('telegram_id', telegram_id).execute()
            return True
        except Exception as e:
            logger.error(f"Ошибка очистки состояния пользователя {telegram_id}: {e}")
            return False
    
    async def log_action(self, user_id: int, action: str, details: Dict = None) -> bool:
        """Записать действие в лог"""
        try:
            self._ensure_initialized()
            data = {
                'user_id': user_id,
                'action': action,
                'details': details or {}
            }
            response = self.supabase.table('action_logs').insert(data).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Ошибка записи в лог: {e}")
            return False

# Глобальный экземпляр базы данных (синглтон)
db = Database()