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