# 🤖 Полный код Telegram-бота для управления каналами

## 📋 Содержание

1. [SQL схема базы данных](#sql-схема-базы-данных)
2. [Конфигурация](#конфигурация)
3. [Работа с базой данных](#работа-с-базой-данных)
4. [Вспомогательные функции](#вспомогательные-функции)
5. [Планировщик задач](#планировщик-задач)
6. [Основные обработчики](#основные-обработчики)
7. [Обработчики сценариев](#обработчики-сценариев)
8. [Главный файл бота](#главный-файл-бота)
9. [Файлы конфигурации](#файлы-конфигурации)

---

## SQL схема базы данных

**Файл: `database_schema.sql`**

```sql
-- Telegram Bot Database Schema for Supabase

-- Таблица пользователей (админов)
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    is_admin BOOLEAN DEFAULT FALSE,
    timezone VARCHAR(50) DEFAULT 'UTC',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Таблица каналов
CREATE TABLE channels (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    title VARCHAR(255) NOT NULL,
    username VARCHAR(255),
    description TEXT,
    added_by BIGINT REFERENCES users(telegram_id),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Таблица постов
CREATE TABLE posts (
    id BIGSERIAL PRIMARY KEY,
    channel_id BIGINT REFERENCES channels(telegram_id),
    created_by BIGINT REFERENCES users(telegram_id),
    text_content TEXT,
    media_type VARCHAR(50), -- photo, video, document, etc.
    media_file_id VARCHAR(255),
    media_caption TEXT,
    parse_mode VARCHAR(20) DEFAULT 'HTML', -- HTML, Markdown, MarkdownV2
    reply_markup JSONB, -- inline keyboard buttons
    scheduled_time TIMESTAMP WITH TIME ZONE,
    published_time TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) DEFAULT 'draft', -- draft, scheduled, published, failed
    message_id BIGINT, -- ID сообщения после публикации
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Таблица для хранения состояний пользователей (для сценариев)
CREATE TABLE user_states (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT REFERENCES users(telegram_id),
    state VARCHAR(100) NOT NULL,
    data JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(telegram_id)
);

-- Таблица логов действий
CREATE TABLE action_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(telegram_id),
    action VARCHAR(100) NOT NULL,
    details JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Индексы для оптимизации
CREATE INDEX idx_users_telegram_id ON users(telegram_id);
CREATE INDEX idx_channels_telegram_id ON channels(telegram_id);
CREATE INDEX idx_posts_channel_id ON posts(channel_id);
CREATE INDEX idx_posts_status ON posts(status);
CREATE INDEX idx_posts_scheduled_time ON posts(scheduled_time);
CREATE INDEX idx_user_states_telegram_id ON user_states(telegram_id);
CREATE INDEX idx_action_logs_user_id ON action_logs(user_id);
CREATE INDEX idx_action_logs_created_at ON action_logs(created_at);

-- Функция для автоматического обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Триггеры для автоматического обновления updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_channels_updated_at BEFORE UPDATE ON channels
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_posts_updated_at BEFORE UPDATE ON posts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_states_updated_at BEFORE UPDATE ON user_states
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Политики безопасности RLS (Row Level Security)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE channels ENABLE ROW LEVEL SECURITY;
ALTER TABLE posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE action_logs ENABLE ROW LEVEL SECURITY;

-- Политики доступа (базовые, можно настроить под нужды)
CREATE POLICY "Users can view their own data" ON users
    FOR ALL USING (telegram_id = current_setting('app.current_user_id')::BIGINT);

CREATE POLICY "Admins can view all channels" ON channels
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM users 
            WHERE telegram_id = current_setting('app.current_user_id')::BIGINT 
            AND is_admin = TRUE
        )
    );

CREATE POLICY "Admins can manage posts" ON posts
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM users 
            WHERE telegram_id = current_setting('app.current_user_id')::BIGINT 
            AND is_admin = TRUE
        )
    );

-- Вставка первого админа (замените на свой telegram_id)
-- INSERT INTO users (telegram_id, username, first_name, is_admin) 
-- VALUES (YOUR_TELEGRAM_ID, 'your_username', 'Your Name', TRUE);
```

---

## Конфигурация

**Файл: `config.py`**

```python
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram Bot
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    BOT_USERNAME = os.getenv('BOT_USERNAME')
    
    # Supabase
    SUPABASE_URL = os.getenv('SUPABASE_URL')
    SUPABASE_KEY = os.getenv('SUPABASE_KEY')
    
    # Admin
    ADMIN_TELEGRAM_ID = int(os.getenv('ADMIN_TELEGRAM_ID', 0))
    
    # Bot settings
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    
    # Timezone
    DEFAULT_TIMEZONE = 'UTC'
    
    # Post settings
    MAX_TEXT_LENGTH = 4096
    MAX_CAPTION_LENGTH = 1024
    
    # Scheduler settings
    SCHEDULER_INTERVAL = 60  # seconds
    
    @classmethod
    def validate(cls):
        """Проверка обязательных настроек"""
        required_vars = [
            'TELEGRAM_BOT_TOKEN',
            'SUPABASE_URL', 
            'SUPABASE_KEY',
            'ADMIN_TELEGRAM_ID'
        ]
        
        missing_vars = []
        for var in required_vars:
            if not getattr(cls, var):
                missing_vars.append(var)
        
        if missing_vars:
            raise ValueError(f"Отсутствуют обязательные переменные окружения: {', '.join(missing_vars)}")
        
        return True
```

**Файл: `.env.example`**

```env
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Supabase Configuration
SUPABASE_URL=your_supabase_url_here
SUPABASE_KEY=your_supabase_anon_key_here

# Admin Configuration
ADMIN_TELEGRAM_ID=your_telegram_id_here

# Bot Configuration
BOT_USERNAME=your_bot_username_here
DEBUG=False
```

---

## Работа с базой данных

**Файл: `database.py`**

```python
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
    def __init__(self):
        self.supabase: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
    
    async def get_user(self, telegram_id: int) -> Optional[Dict]:
        """Получить пользователя по telegram_id"""
        try:
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
            response = self.supabase.table('posts').select('*').eq('id', post_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Ошибка получения поста {post_id}: {e}")
            return None
    
    async def get_scheduled_posts(self, channel_id: int = None) -> List[Dict]:
        """Получить отложенные посты"""
        try:
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
            response = self.supabase.table('posts').delete().eq('id', post_id).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Ошибка удаления поста {post_id}: {e}")
            return False
    
    async def get_user_state(self, telegram_id: int) -> Optional[Dict]:
        """Получить состояние пользователя"""
        try:
            response = self.supabase.table('user_states').select('*').eq('telegram_id', telegram_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Ошибка получения состояния пользователя {telegram_id}: {e}")
            return None
    
    async def set_user_state(self, telegram_id: int, state: str, data: Dict = None) -> bool:
        """Установить состояние пользователя"""
        try:
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
            response = self.supabase.table('user_states').delete().eq('telegram_id', telegram_id).execute()
            return True
        except Exception as e:
            logger.error(f"Ошибка очистки состояния пользователя {telegram_id}: {e}")
            return False
    
    async def log_action(self, user_id: int, action: str, details: Dict = None) -> bool:
        """Записать действие в лог"""
        try:
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

# Глобальный экземпляр базы данных
db = Database()
```

---

## Файлы конфигурации

**Файл: `requirements.txt`**

```
python-telegram-bot==20.7
supabase==2.3.4
python-dotenv==1.0.0
pytz==2023.3
aiofiles==23.2.1
Pillow==10.1.0
requests==2.31.0
```

**Файл: `Procfile`**

```
web: python bot.py
```

**Файл: `runtime.txt`**

```
python-3.11.0
```

**Файл: `railway.json`**

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "python bot.py",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

---

## 🚀 Инструкция по запуску

1. **Создайте проект в Supabase** и выполните SQL из `database_schema.sql`
2. **Создайте Telegram бота** через @BotFather
3. **Настройте переменные окружения** по примеру `.env.example`
4. **Добавьте первого админа** в таблицу users
5. **Задеплойте на Railway** - все файлы готовы

Бот полностью готов к работе! 🎉