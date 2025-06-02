# 🚀 Руководство по деплою Telegram-бота

## ✅ Проблемы исправлены!

Все критические ошибки в коде исправлены:
- ✅ Убрана ошибка инициализации Supabase при импорте
- ✅ Исправлены импорты типов
- ✅ Добавлена ленивая инициализация базы данных
- ✅ Улучшена обработка ошибок конфигурации

## 🔧 Переменные окружения для Railway

Скопируйте эти переменные в настройки Railway:

```
TELEGRAM_BOT_TOKEN
SUPABASE_URL
SUPABASE_KEY
ADMIN_TELEGRAM_ID
BOT_USERNAME
DEBUG
```

### Значения переменных:

**TELEGRAM_BOT_TOKEN**
```
1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
```
*Получите от @BotFather*

**SUPABASE_URL**
```
https://abcdefghijklmnop.supabase.co
```
*Из Settings → API в Supabase*

**SUPABASE_KEY**
```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFiY2RlZmdoaWprbG1ub3AiLCJyb2xlIjoiYW5vbiIsImlhdCI6MTYzMjQ4NjQwMCwiZXhwIjoxOTQ4MDYyNDAwfQ.example_key_here
```
*anon public key из Settings → API в Supabase*

**ADMIN_TELEGRAM_ID**
```
123456789
```
*Ваш Telegram ID от @userinfobot*

**BOT_USERNAME**
```
my_channel_bot
```
*Username вашего бота (без @)*

**DEBUG**
```
False
```
*Для продакшена всегда False*

## 📋 Пошаговая инструкция деплоя

### 1. Подготовка Supabase

1. Создайте проект на [supabase.com](https://supabase.com)
2. Перейдите в **SQL Editor**
3. Скопируйте весь код из `database_schema.sql`
4. Выполните SQL код
5. Добавьте первого админа:
   ```sql
   INSERT INTO users (telegram_id, username, first_name, is_admin) 
   VALUES (123456789, 'your_username', 'Your Name', TRUE);
   ```

### 2. Создание Telegram бота

1. Напишите [@BotFather](https://t.me/botfather)
2. Отправьте `/newbot`
3. Следуйте инструкциям
4. Сохраните токен и username

### 3. Деплой на Railway

1. Подключите GitHub репозиторий к Railway
2. В настройках проекта добавьте все переменные окружения
3. Railway автоматически задеплоит бота
4. Проверьте логи на наличие ошибок

### 4. Проверка работы

1. Найдите бота в Telegram
2. Отправьте `/start`
3. Если вы админ, увидите полное меню
4. Добавьте первый канал

## 🔍 Диагностика проблем

### Проверка конфигурации локально:

```bash
# Установите переменные и проверьте
export TELEGRAM_BOT_TOKEN="your_token"
export SUPABASE_URL="your_url"
export SUPABASE_KEY="your_key"
export ADMIN_TELEGRAM_ID="your_id"
export BOT_USERNAME="your_username"
export DEBUG="False"

python test_config.py
```

### Частые ошибки:

**1. Ошибка подключения к Telegram**
- Проверьте правильность токена
- Убедитесь, что бот не заблокирован

**2. Ошибка подключения к Supabase**
- Проверьте URL и ключ
- Убедитесь, что проект активен
- Проверьте выполнение SQL схемы

**3. Нет прав администратора**
- Убедитесь, что ваш ID добавлен в таблицу users
- Проверьте поле is_admin = TRUE

**4. Ошибка публикации в канал**
- Добавьте бота в канал как администратора
- Дайте права на публикацию сообщений

## 📊 Мониторинг

### Логи Railway:
- Проверяйте логи в панели Railway
- Ищите ошибки инициализации
- Следите за ошибками публикации

### Логи бота:
- Все действия логируются в таблицу action_logs
- Ошибки публикации сохраняются в таблицу posts
- Используйте команду `/stats` для статистики

## 🎯 Финальная проверка

После деплоя убедитесь:
- ✅ Бот отвечает на `/start`
- ✅ Админ видит полное меню
- ✅ Можно добавить канал
- ✅ Можно создать тестовый пост
- ✅ Отложенная публикация работает

## 🆘 Поддержка

Если возникли проблемы:
1. Проверьте все переменные окружения
2. Убедитесь в правильности SQL схемы
3. Проверьте права бота в каналах
4. Посмотрите логи Railway
5. Используйте `test_config.py` для диагностики

**Бот готов к работе! 🎉**