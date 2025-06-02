-- Полная SQL схема для Telegram-бота управления каналами
-- Для использования в Supabase

-- Таблица пользователей с расширенными настройками
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    timezone TEXT DEFAULT 'UTC',
    language TEXT DEFAULT 'ru',
    date_format TEXT DEFAULT 'YYYY-MM-DD',
    time_format TEXT DEFAULT 'HH:MM',
    notify_before INTEGER DEFAULT 0,
    current_project BIGINT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Таблица проектов
CREATE TABLE IF NOT EXISTS projects (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    owner_id BIGINT NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Таблица участников проектов
CREATE TABLE IF NOT EXISTS user_projects (
    user_id BIGINT NOT NULL,
    project_id BIGINT NOT NULL,
    role TEXT DEFAULT 'admin' CHECK (role IN ('owner', 'admin', 'editor', 'viewer')),
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (user_id, project_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- Таблица каналов с проверкой прав администратора
CREATE TABLE IF NOT EXISTS channels (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL,
    project_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    username TEXT, -- @username канала
    type TEXT DEFAULT 'channel' CHECK (type IN ('channel', 'group', 'supergroup')),
    is_admin_verified BOOLEAN DEFAULT FALSE, -- проверен ли статус админа
    admin_check_date TIMESTAMP WITH TIME ZONE,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    CONSTRAINT channels_project_chat_unique UNIQUE(project_id, chat_id)
);

-- Таблица постов с расширенными возможностями
CREATE TABLE IF NOT EXISTS posts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL,
    project_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    text TEXT,
    media_type TEXT CHECK (media_type IN ('photo', 'video', 'document', 'animation')),
    media_file_id TEXT,
    media_caption TEXT,
    parse_mode TEXT DEFAULT 'HTML' CHECK (parse_mode IN ('HTML', 'Markdown', 'MarkdownV2', NULL)),
    buttons JSONB, -- кнопки в формате JSON
    publish_time TIMESTAMP WITH TIME ZONE,
    repeat_interval TEXT, -- интервал повтора (1d, 12h, 30m, etc.)
    published BOOLEAN DEFAULT FALSE,
    draft BOOLEAN DEFAULT FALSE,
    failed BOOLEAN DEFAULT FALSE,
    failure_reason TEXT,
    published_message_id BIGINT, -- ID опубликованного сообщения
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE
);

-- Таблица для логирования публикаций
CREATE TABLE IF NOT EXISTS publication_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    post_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT,
    published_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status TEXT DEFAULT 'success' CHECK (status IN ('success', 'failed', 'retry')),
    error_message TEXT,
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE
);

-- Таблица для хранения медиафайлов
CREATE TABLE IF NOT EXISTS media_files (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_id TEXT NOT NULL UNIQUE,
    file_type TEXT NOT NULL CHECK (file_type IN ('photo', 'video', 'document', 'animation')),
    file_size BIGINT,
    file_name TEXT,
    mime_type TEXT,
    uploaded_by BIGINT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (uploaded_by) REFERENCES users(user_id) ON DELETE SET NULL
);

-- Таблица для настроек уведомлений
CREATE TABLE IF NOT EXISTS notification_settings (
    user_id BIGINT PRIMARY KEY,
    post_published BOOLEAN DEFAULT TRUE,
    post_failed BOOLEAN DEFAULT TRUE,
    daily_summary BOOLEAN DEFAULT FALSE,
    weekly_summary BOOLEAN DEFAULT FALSE,
    summary_time TIME DEFAULT '09:00:00',
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Индексы для оптимизации запросов
CREATE INDEX IF NOT EXISTS idx_posts_publish_time ON posts(publish_time) WHERE NOT published AND NOT draft;
CREATE INDEX IF NOT EXISTS idx_posts_user_project ON posts(user_id, project_id);
CREATE INDEX IF NOT EXISTS idx_posts_channel ON posts(channel_id);
CREATE INDEX IF NOT EXISTS idx_channels_project ON channels(project_id);
CREATE INDEX IF NOT EXISTS idx_channels_chat_id ON channels(chat_id);
CREATE INDEX IF NOT EXISTS idx_user_projects_user ON user_projects(user_id);
CREATE INDEX IF NOT EXISTS idx_user_projects_project ON user_projects(project_id);
CREATE INDEX IF NOT EXISTS idx_publication_log_post ON publication_log(post_id);

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

CREATE TRIGGER update_projects_updated_at BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_channels_updated_at BEFORE UPDATE ON channels
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_posts_updated_at BEFORE UPDATE ON posts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Функция для проверки прав доступа к проекту
CREATE OR REPLACE FUNCTION check_project_access(p_user_id BIGINT, p_project_id BIGINT)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM user_projects 
        WHERE user_id = p_user_id AND project_id = p_project_id
    );
END;
$$ LANGUAGE plpgsql;

-- Функция для получения роли пользователя в проекте
CREATE OR REPLACE FUNCTION get_user_project_role(p_user_id BIGINT, p_project_id BIGINT)
RETURNS TEXT AS $$
DECLARE
    user_role TEXT;
BEGIN
    SELECT role INTO user_role 
    FROM user_projects 
    WHERE user_id = p_user_id AND project_id = p_project_id;
    
    RETURN COALESCE(user_role, 'none');
END;
$$ LANGUAGE plpgsql;

-- Вставка начальных данных (если нужно)
-- Можно добавить стандартные настройки, роли и т.д.

-- Комментарии к таблицам
COMMENT ON TABLE users IS 'Пользователи бота с их настройками';
COMMENT ON TABLE projects IS 'Проекты для группировки каналов';
COMMENT ON TABLE user_projects IS 'Связь пользователей с проектами и их роли';
COMMENT ON TABLE channels IS 'Каналы Telegram с проверкой прав администратора';
COMMENT ON TABLE posts IS 'Посты для публикации в каналах';
COMMENT ON TABLE publication_log IS 'Лог публикаций для отслеживания';
COMMENT ON TABLE media_files IS 'Медиафайлы для переиспользования';
COMMENT ON TABLE notification_settings IS 'Настройки уведомлений пользователей';

-- Политики безопасности Row Level Security (RLS)
-- Включаем RLS для всех таблиц
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE channels ENABLE ROW LEVEL SECURITY;
ALTER TABLE posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE publication_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE media_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_settings ENABLE ROW LEVEL SECURITY;

-- Политики для пользователей (каждый видит только свои данные)
CREATE POLICY "Users can view own data" ON users
    FOR ALL USING (user_id = current_setting('app.current_user_id')::BIGINT);

-- Политики для проектов (пользователи видят только проекты, в которых участвуют)
CREATE POLICY "Users can view accessible projects" ON projects
    FOR ALL USING (
        id IN (
            SELECT project_id FROM user_projects 
            WHERE user_id = current_setting('app.current_user_id')::BIGINT
        )
    );

-- Аналогичные политики для других таблиц...
-- (В реальном проекте нужно будет настроить все политики безопасности)