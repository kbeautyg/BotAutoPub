-- Удаляем старые таблицы в правильном порядке (сначала зависимые)
DROP TABLE IF EXISTS notification_settings CASCADE;
DROP TABLE IF EXISTS posts CASCADE;
DROP TABLE IF EXISTS user_projects CASCADE;
DROP TABLE IF EXISTS channels CASCADE;
DROP TABLE IF EXISTS projects CASCADE;
-- users оставляем, но уберем current_project

-- Удаляем столбец current_project из users
ALTER TABLE users DROP COLUMN IF EXISTS current_project;

-- Создаем упрощенную структуру без проектов
CREATE TABLE IF NOT EXISTS channels (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chat_id BIGINT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    username TEXT,
    is_admin_verified BOOLEAN DEFAULT FALSE,
    admin_check_date TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Таблица для связи пользователей с каналами (кто имеет доступ)
CREATE TABLE IF NOT EXISTS channel_admins (
    channel_id BIGINT,
    user_id BIGINT,
    role TEXT DEFAULT 'admin', -- admin, owner
    added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (channel_id, user_id),
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE
);

-- Посты привязываются только к каналам
CREATE TABLE IF NOT EXISTS posts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    channel_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL, -- дублируем для быстрого доступа
    created_by BIGINT, -- кто создал пост (для истории)
    text TEXT,
    media_type TEXT,
    media_id TEXT,
    parse_mode TEXT DEFAULT 'HTML',
    buttons JSONB,
    publish_time TIMESTAMP WITH TIME ZONE,
    repeat_interval INTEGER DEFAULT 0,
    draft BOOLEAN DEFAULT FALSE,
    published BOOLEAN DEFAULT FALSE,
    notified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE
);

-- Настройки уведомлений (оставляем как есть)
CREATE TABLE IF NOT EXISTS notification_settings (
    user_id BIGINT PRIMARY KEY,
    post_published BOOLEAN DEFAULT TRUE,
    post_failed BOOLEAN DEFAULT TRUE,
    daily_summary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Индексы для производительности
CREATE INDEX IF NOT EXISTS idx_posts_channel_id ON posts(channel_id);
CREATE INDEX IF NOT EXISTS idx_posts_publish_time ON posts(publish_time);
CREATE INDEX IF NOT EXISTS idx_posts_published_draft ON posts(published, draft);
CREATE INDEX IF NOT EXISTS idx_channel_admins_user_id ON channel_admins(user_id);
CREATE INDEX IF NOT EXISTS idx_channels_chat_id ON channels(chat_id);
