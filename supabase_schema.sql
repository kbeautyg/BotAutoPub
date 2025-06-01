-- Create the 'users' table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chat_id BIGINT UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    timezone TEXT DEFAULT 'UTC',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create the 'channels' table
CREATE TABLE channels (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    telegram_channel_id BIGINT NOT NULL,
    channel_name TEXT NOT NULL, -- e.g., @mychannel or channel title
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (user_id, telegram_channel_id)
);

-- Create the 'posts' table
CREATE TABLE posts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    text TEXT,
    media_group_id TEXT, -- To group media files in Telegram
    status TEXT DEFAULT 'draft' NOT NULL, -- draft, scheduled, sent, cancelled
    schedule_type TEXT, -- 'one_time', 'daily', 'weekly', 'monthly', 'yearly', NULL for instant
    scheduled_at TIMESTAMP WITH TIME ZONE, -- For one_time posts
    cron_schedule TEXT, -- For recurring posts (e.g., "0 10 * * *" for daily at 10:00 UTC)
    start_date DATE,
    end_date DATE,
    delete_after_publish_type TEXT, -- 'never', 'hours', 'days', 'specific_date'
    delete_after_publish_value INTEGER, -- N for hours/days
    delete_at TIMESTAMP WITH TIME ZONE, -- Specific date for deletion
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create the 'post_media' table
CREATE TABLE post_media (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    post_id UUID REFERENCES posts(id) ON DELETE CASCADE,
    telegram_file_id TEXT NOT NULL,
    media_type TEXT NOT NULL, -- 'photo', 'video', 'document'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create the 'post_buttons' table
CREATE TABLE post_buttons (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    post_id UUID REFERENCES posts(id) ON DELETE CASCADE,
    button_text TEXT NOT NULL,
    button_url TEXT NOT NULL,
    button_order INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create the 'post_channels' table (many-to-many relationship)
CREATE TABLE post_channels (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    post_id UUID REFERENCES posts(id) ON DELETE CASCADE,
    channel_id UUID REFERENCES channels(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (post_id, channel_id)
);

-- Create the 'scheduled_tasks' table for managing background tasks
CREATE TABLE scheduled_tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    post_id UUID REFERENCES posts(id) ON DELETE CASCADE,
    task_type TEXT NOT NULL, -- 'send_post', 'delete_post'
    scheduled_time TIMESTAMP WITH TIME ZONE, -- For one-time tasks
    cron_expression TEXT, -- For recurring tasks
    is_active BOOLEAN DEFAULT TRUE,
    last_executed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enable Row Level Security (RLS) for all tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE channels ENABLE ROW LEVEL SECURITY;
ALTER TABLE posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE post_media ENABLE ROW LEVEL SECURITY;
ALTER TABLE post_buttons ENABLE ROW LEVEL SECURITY;
ALTER TABLE post_channels ENABLE ROW LEVEL SECURITY;
ALTER TABLE scheduled_tasks ENABLE ROW LEVEL SECURITY;

-- Create RLS policies for 'users' table
CREATE POLICY "Allow all users to read their own user data" ON users
  FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Allow users to insert their own user data" ON users
  FOR INSERT WITH CHECK (auth.uid() = id);
CREATE POLICY "Allow users to update their own user data" ON users
  FOR UPDATE USING (auth.uid() = id);

-- Create RLS policies for 'channels' table
CREATE POLICY "Allow users to manage their own channels" ON channels
  FOR ALL USING (user_id = (SELECT id FROM users WHERE chat_id = auth.jwt() ->> 'sub')::uuid);

-- Create RLS policies for 'posts' table
CREATE POLICY "Allow users to manage their own posts" ON posts
  FOR ALL USING (user_id = (SELECT id FROM users WHERE chat_id = auth.jwt() ->> 'sub')::uuid);

-- Create RLS policies for 'post_media' table
CREATE POLICY "Allow users to manage media for their own posts" ON post_media
  FOR ALL USING (post_id IN (SELECT id FROM posts WHERE user_id = (SELECT id FROM users WHERE chat_id = auth.jwt() ->> 'sub')::uuid));

-- Create RLS policies for 'post_buttons' table
CREATE POLICY "Allow users to manage buttons for their own posts" ON post_buttons
  FOR ALL USING (post_id IN (SELECT id FROM posts WHERE user_id = (SELECT id FROM users WHERE chat_id = auth.jwt() ->> 'sub')::uuid));

-- Create RLS policies for 'post_channels' table
CREATE POLICY "Allow users to manage channels for their own posts" ON post_channels
  FOR ALL USING (post_id IN (SELECT id FROM posts WHERE user_id = (SELECT id FROM users WHERE chat_id = auth.jwt() ->> 'sub')::uuid));

-- Create RLS policies for 'scheduled_tasks' table
CREATE POLICY "Allow users to manage their own scheduled tasks" ON scheduled_tasks
  FOR ALL USING (post_id IN (SELECT id FROM posts WHERE user_id = (SELECT id FROM users WHERE chat_id = auth.jwt() ->> 'sub')::uuid));

-- Optional: Add a function to update 'updated_at' column automatically
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_channels_updated_at
BEFORE UPDATE ON channels
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_posts_updated_at
BEFORE UPDATE ON posts
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_scheduled_tasks_updated_at
BEFORE UPDATE ON scheduled_tasks
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();