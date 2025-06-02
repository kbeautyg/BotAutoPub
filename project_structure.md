# Структура проекта Telegram Bot

## 📁 Файловая структура

```
telegram-channel-bot/
├── 📄 bot.py                      # Основной файл бота
├── 📄 config.py                   # Конфигурация и настройки
├── 📄 database.py                 # Работа с базой данных Supabase
├── 📄 handlers.py                 # Основные обработчики команд
├── 📄 conversation_handlers.py    # Обработчики сценариев
├── 📄 scheduler.py                # Планировщик публикаций
├── 📄 utils.py                    # Вспомогательные функции
├── 📄 requirements.txt            # Зависимости Python
├── 📄 .env.example               # Пример переменных окружения
├── 📄 database_schema.sql        # SQL схема для Supabase
├── 📄 Procfile                   # Конфигурация для Railway
├── 📄 runtime.txt                # Версия Python
├── 📄 railway.json               # Настройки Railway
├── 📄 README.md                  # Документация
├── 📄 fix_imports.py             # Скрипт проверки импортов
└── 📄 project_structure.md       # Этот файл
```

## 🗄️ База данных (Supabase)

### Таблицы:

1. **users** - Пользователи и администраторы
   - `id` (BIGSERIAL PRIMARY KEY)
   - `telegram_id` (BIGINT UNIQUE)
   - `username`, `first_name`, `last_name`
   - `is_admin` (BOOLEAN)
   - `timezone` (VARCHAR)
   - `created_at`, `updated_at`

2. **channels** - Каналы для публикации
   - `id` (BIGSERIAL PRIMARY KEY)
   - `telegram_id` (BIGINT UNIQUE)
   - `title`, `username`, `description`
   - `added_by` (BIGINT REFERENCES users)
   - `is_active` (BOOLEAN)
   - `created_at`, `updated_at`

3. **posts** - Посты (черновики, запланированные, опубликованные)
   - `id` (BIGSERIAL PRIMARY KEY)
   - `channel_id` (BIGINT REFERENCES channels)
   - `created_by` (BIGINT REFERENCES users)
   - `text_content`, `media_type`, `media_file_id`
   - `media_caption`, `parse_mode`
   - `reply_markup` (JSONB)
   - `scheduled_time`, `published_time`
   - `status` (VARCHAR) - draft/scheduled/published/failed
   - `message_id`, `error_message`
   - `created_at`, `updated_at`

4. **user_states** - Состояния пользователей для сценариев
   - `id` (BIGSERIAL PRIMARY KEY)
   - `telegram_id` (BIGINT REFERENCES users)
   - `state` (VARCHAR)
   - `data` (JSONB)
   - `created_at`, `updated_at`

5. **action_logs** - Логи действий
   - `id` (BIGSERIAL PRIMARY KEY)
   - `user_id` (BIGINT REFERENCES users)
   - `action` (VARCHAR)
   - `details` (JSONB)
   - `created_at`

## 🔧 Компоненты системы

### bot.py
- Главный файл приложения
- Инициализация бота и обработчиков
- Регистрация команд и callback'ов
- Запуск планировщика
- Обработка ошибок

### config.py
- Загрузка переменных окружения
- Валидация конфигурации
- Константы приложения

### database.py
- Класс Database для работы с Supabase
- CRUD операции для всех таблиц
- Управление состояниями пользователей
- Логирование действий

### handlers.py
- BotHandlers - основные команды (/start, /help, /menu)
- CallbackHandlers - обработка callback кнопок
- ChannelHandlers - управление каналами
- PostHandlers - создание постов

### conversation_handlers.py
- PostConversationHandlers - сценарий создания поста
- ChannelConversationHandlers - сценарий добавления канала
- NavigationHandlers - навигация и отмена

### scheduler.py
- PostScheduler - планировщик публикаций
- ChannelManager - управление каналами
- Автоматическая публикация отложенных постов

### utils.py
- TimeZoneManager - работа с часовыми поясами
- TextFormatter - форматирование текста
- ButtonManager - создание кнопок
- DateTimeParser - парсинг даты/времени
- Вспомогательные функции

## 🚀 Деплой на Railway

### Необходимые файлы:
- `Procfile` - команда запуска
- `runtime.txt` - версия Python
- `railway.json` - настройки Railway
- `requirements.txt` - зависимости

### Переменные окружения:
- `TELEGRAM_BOT_TOKEN` - токен бота
- `BOT_USERNAME` - имя пользователя бота
- `SUPABASE_URL` - URL Supabase проекта
- `SUPABASE_KEY` - Anon key Supabase
- `ADMIN_TELEGRAM_ID` - ID главного администратора
- `DEBUG` - режим отладки (False для продакшена)

## 📋 Функциональность

### Для администраторов:
1. **Создание постов**
   - Пошаговый сценарий
   - Поддержка текста, медиа, кнопок
   - Превью перед публикацией

2. **Отложенная публикация**
   - Гибкие форматы времени
   - Автоматический планировщик
   - Управление отложенными постами

3. **Управление каналами**
   - Добавление/удаление каналов
   - Проверка прав бота
   - Валидация доступа

4. **Статистика и мониторинг**
   - Статистика публикаций
   - Логи действий
   - Информация о каналах

### Для всех пользователей:
1. **Настройки профиля**
   - Изменение часового пояса
   - Просмотр информации

2. **Навигация**
   - Интуитивное меню
   - Кнопки возврата
   - Отмена действий

## 🔒 Безопасность

- Row Level Security в Supabase
- Проверка прав на каждом шаге
- Валидация входных данных
- Логирование всех действий
- Ограничения на размер контента

## 📊 Мониторинг

- Подробное логирование
- Статистика использования
- Отслеживание ошибок
- Аудит действий пользователей

## 🔄 Архитектурные особенности

- **Асинхронность** - все операции асинхронные
- **Модульность** - четкое разделение ответственности
- **Масштабируемость** - легко добавлять новые функции
- **Надежность** - обработка ошибок и восстановление
- **Пользовательский опыт** - интуитивные сценарии