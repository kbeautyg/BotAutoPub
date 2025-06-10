import json
from datetime import datetime, timezone
from supabase import create_client, Client

# Global database instance (to be set in main)
db = None

class SupabaseDB:
    def __init__(self, url: str, key: str):
        self.client: Client = create_client(url, key)
    
    def init_schema(self):
        """Ensure the necessary tables exist (or create/alter them if possible)."""
        try:
            # Check if essential tables exist by querying a small portion
            self.client.table("channels").select("id").limit(1).execute()
            self.client.table("posts").select("id").limit(1).execute()
            self.client.table("users").select("user_id").limit(1).execute()
        except Exception:
            # Attempt to create missing tables and columns via SQL
            schema_sql = """
            -- Create tables if they don't exist
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                timezone TEXT DEFAULT 'UTC',
                language TEXT DEFAULT 'ru',
                date_format TEXT DEFAULT 'YYYY-MM-DD',
                time_format TEXT DEFAULT 'HH:MM',
                notify_before INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            
            CREATE TABLE IF NOT EXISTS channels (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                chat_id BIGINT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                username TEXT,
                is_admin_verified BOOLEAN DEFAULT FALSE,
                admin_check_date TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            
            CREATE TABLE IF NOT EXISTS channel_admins (
                channel_id BIGINT,
                user_id BIGINT,
                role TEXT DEFAULT 'admin',
                added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                PRIMARY KEY (channel_id, user_id),
                FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS posts (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                channel_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                created_by BIGINT,
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
            
            CREATE TABLE IF NOT EXISTS notification_settings (
                user_id BIGINT PRIMARY KEY,
                post_published BOOLEAN DEFAULT TRUE,
                post_failed BOOLEAN DEFAULT TRUE,
                daily_summary BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            
            -- Add missing columns if they don't exist
            DO $$ 
            BEGIN
                -- Remove old project-related columns
                IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='current_project') THEN
                    ALTER TABLE users DROP COLUMN current_project;
                END IF;
                
                IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='channels' AND column_name='project_id') THEN
                    ALTER TABLE channels DROP COLUMN project_id;
                END IF;
                
                IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='channels' AND column_name='user_id') THEN
                    ALTER TABLE channels DROP COLUMN user_id;
                END IF;
                
                IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='project_id') THEN
                    ALTER TABLE posts DROP COLUMN project_id;
                END IF;
                
                IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='user_id') THEN
                    ALTER TABLE posts RENAME COLUMN user_id TO created_by;
                END IF;
                
                -- Add new columns if missing
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='created_by') THEN
                    ALTER TABLE posts ADD COLUMN created_by BIGINT;
                END IF;
                
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='chat_id') THEN
                    ALTER TABLE posts ADD COLUMN chat_id BIGINT NOT NULL DEFAULT 0;
                END IF;
            END $$;
            
            -- Create indexes
            CREATE INDEX IF NOT EXISTS idx_posts_channel_id ON posts(channel_id);
            CREATE INDEX IF NOT EXISTS idx_posts_publish_time ON posts(publish_time);
            CREATE INDEX IF NOT EXISTS idx_posts_published_draft ON posts(published, draft);
            CREATE INDEX IF NOT EXISTS idx_channel_admins_user_id ON channel_admins(user_id);
            CREATE INDEX IF NOT EXISTS idx_channels_chat_id ON channels(chat_id);
            """
            try:
                self.client.postgrest.rpc("sql", {"sql": schema_sql}).execute()
            except Exception as e:
                print(f"Warning: Could not execute schema SQL: {e}")

    # User management
    def get_user(self, user_id: int):
        """Retrieve user settings by Telegram user_id."""
        try:
            res = self.client.table("users").select("*").eq("user_id", user_id).execute()
            data = res.data or []
            return data[0] if data else None
        except Exception as e:
            print(f"Error getting user {user_id}: {e}")
            return None

    def ensure_user(self, user_id: int, default_lang: str = None):
        """Ensure a user exists in the users table. Creates with defaults if not present."""
        try:
            user = self.get_user(user_id)
            if user:
                return user
            
            # Create new user with default settings
            lang = default_lang or 'ru'
            new_user = {
                "user_id": user_id,
                "timezone": "UTC",
                "language": lang,
                "date_format": "YYYY-MM-DD",
                "time_format": "HH:MM",
                "notify_before": 0
            }
            res_user = self.client.table("users").insert(new_user).execute()
            return res_user.data[0] if res_user.data else None
        except Exception as e:
            print(f"Error ensuring user {user_id}: {e}")
            return None

    def update_user(self, user_id: int, updates: dict):
        """Update user settings and return the updated record."""
        if not updates:
            return None
        try:
            res = self.client.table("users").update(updates).eq("user_id", user_id).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            print(f"Error updating user {user_id}: {e}")
            return None

    # Channel management
    def add_channel(self, chat_id: int, name: str, username: str = None, is_admin_verified: bool = False):
        """Add a new channel or update existing one."""
        try:
            # Check if channel exists
            res = self.client.table("channels").select("*").eq("chat_id", chat_id).execute()
            if res.data:
                # Update existing channel
                update_data = {
                    "name": name,
                    "username": username,
                    "is_admin_verified": is_admin_verified,
                    "admin_check_date": "now()" if is_admin_verified else None
                }
                res_update = self.client.table("channels").update(update_data).eq("chat_id", chat_id).execute()
                return res_update.data[0] if res_update.data else None
            
            # Create new channel
            data = {
                "chat_id": chat_id,
                "name": name,
                "username": username,
                "is_admin_verified": is_admin_verified,
                "admin_check_date": "now()" if is_admin_verified else None
            }
            res_insert = self.client.table("channels").insert(data).execute()
            return res_insert.data[0] if res_insert.data else None
        except Exception as e:
            print(f"Error adding channel {chat_id}: {e}")
            return None

    def list_channels(self, user_id: int = None):
        """List all channels user has access to."""
        try:
            if user_id:
                # Get channels where user is admin
                res = self.client.table("channel_admins").select("channel_id").eq("user_id", user_id).execute()
                if not res.data:
                    return []
                
                channel_ids = [admin["channel_id"] for admin in res.data]
                res_channels = self.client.table("channels").select("*").in_("id", channel_ids).execute()
                return res_channels.data or []
            else:
                # Return all channels (for admin purposes)
                res = self.client.table("channels").select("*").execute()
                return res.data or []
        except Exception as e:
            print(f"Error listing channels: {e}")
            return []

    def get_channel(self, channel_id: int):
        """Retrieve a single channel by internal ID."""
        try:
            if not channel_id:
                return None
            res = self.client.table("channels").select("*").eq("id", channel_id).execute()
            data = res.data or []
            return data[0] if data else None
        except Exception as e:
            print(f"Error getting channel {channel_id}: {e}")
            return None

    def get_channel_by_chat_id(self, chat_id: int):
        """Retrieve a single channel by Telegram chat_id."""
        try:
            res = self.client.table("channels").select("*").eq("chat_id", chat_id).execute()
            data = res.data or []
            return data[0] if data else None
        except Exception as e:
            print(f"Error getting channel by chat_id {chat_id}: {e}")
            return None

    def remove_channel(self, channel_id: int):
        """Remove a channel and all related data."""
        try:
            # Delete channel (cascade will delete posts and admins)
            self.client.table("channels").delete().eq("id", channel_id).execute()
            return True
        except Exception as e:
            print(f"Error removing channel {channel_id}: {e}")
            return False

    def add_channel_admin(self, channel_id: int, user_id: int, role: str = "admin"):
        """Add user as admin to channel."""
        try:
            data = {"channel_id": channel_id, "user_id": user_id, "role": role}
            self.client.table("channel_admins").insert(data).execute()
            return True
        except Exception:
            return False

    def remove_channel_admin(self, channel_id: int, user_id: int):
        """Remove user from channel admins."""
        try:
            self.client.table("channel_admins").delete().eq("channel_id", channel_id).eq("user_id", user_id).execute()
            return True
        except Exception:
            return False

    def is_channel_admin(self, channel_id: int, user_id: int):
        """Check if user is admin of the channel."""
        try:
            res = self.client.table("channel_admins").select("user_id").eq("channel_id", channel_id).eq("user_id", user_id).execute()
            return bool(res.data)
        except Exception as e:
            print(f"Error checking if user {user_id} is admin of channel {channel_id}: {e}")
            return False

    def get_user_channels(self, user_id: int):
        """Get all channels where user is admin."""
        try:
            res = self.client.table("channel_admins").select("*, channels(*)").eq("user_id", user_id).execute()
            channels = []
            for admin_record in res.data or []:
                if admin_record.get("channels"):
                    channel = admin_record["channels"]
                    channel["admin_role"] = admin_record.get("role", "admin")
                    channels.append(channel)
            return channels
        except Exception as e:
            print(f"Error getting user channels for {user_id}: {e}")
            return []

    # Post management
    def add_post(self, post_data: dict):
        """Insert a new post into the database. Returns the inserted record."""
        try:
            # Handle the format/parse_mode field properly
            if "format" in post_data:
                post_data["parse_mode"] = post_data.pop("format")
            
            # Ensure parse_mode has a valid value
            if not post_data.get("parse_mode"):
                post_data["parse_mode"] = "HTML"
            
            if "buttons" in post_data and isinstance(post_data["buttons"], list):
                post_data["buttons"] = json.dumps(post_data["buttons"])
            
            # Get chat_id from channel if not provided
            if not post_data.get("chat_id") and post_data.get("channel_id"):
                channel = self.get_channel(post_data["channel_id"])
                if channel:
                    post_data["chat_id"] = channel["chat_id"]
            
            print(f"Inserting post data: {post_data}")  # Debug log
            
            res = self.client.table("posts").insert(post_data).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            print(f"Error inserting post: {e}")
            return None

    def get_post(self, post_id: int):
        """Retrieve a single post by id."""
        try:
            if not post_id:
                return None
            res = self.client.table("posts").select("*").eq("id", post_id).execute()
            data = res.data or []
            return data[0] if data else None
        except Exception as e:
            print(f"Error getting post {post_id}: {e}")
            return None

    def list_posts(self, user_id: int = None, channel_id: int = None, only_pending: bool = True):
        """List posts for channels user has access to."""
        try:
            if channel_id:
                # Get posts for specific channel
                query = self.client.table("posts").select("*").eq("channel_id", channel_id)
            elif user_id:
                # Get posts for all channels user is admin of
                user_channels = self.get_user_channels(user_id)
                if not user_channels:
                    return []
                
                channel_ids = [ch["id"] for ch in user_channels]
                query = self.client.table("posts").select("*").in_("channel_id", channel_ids)
            else:
                query = self.client.table("posts").select("*")
            
            if only_pending:
                query = query.eq("published", False)
            
            query = query.order("publish_time", desc=False)
            res = query.execute()
            return res.data or []
        except Exception as e:
            print(f"Error listing posts: {e}")
            return []

    def update_post(self, post_id: int, updates: dict):
        """Update fields of a post and return the updated record."""
        try:
            # Handle the format/parse_mode field properly
            if "format" in updates:
                updates["parse_mode"] = updates.pop("format")
            
            if "buttons" in updates and isinstance(updates["buttons"], list):
                updates["buttons"] = json.dumps(updates["buttons"])
            res = self.client.table("posts").update(updates).eq("id", post_id).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            print(f"Error updating post {post_id}: {e}")
            return None

    def delete_post(self, post_id: int):
        """Delete a post by id."""
        try:
            self.client.table("posts").delete().eq("id", post_id).execute()
            return True
        except Exception as e:
            print(f"Error deleting post {post_id}: {e}")
            return False

    def get_due_posts(self, current_time):
        """Get posts scheduled up to the given time (not published or drafts)."""
        try:
            # Ensure timezone aware value and format in UTC
            if hasattr(current_time, "tzinfo") and current_time.tzinfo is None:
                current_time = current_time.replace(tzinfo=timezone.utc)
            elif not hasattr(current_time, "tzinfo"):
                # Fallback for strings or naive values
                try:
                    current_time = datetime.fromisoformat(str(current_time))
                except Exception:
                    current_time = datetime.now(timezone.utc)
            now_str = current_time.astimezone(timezone.utc).isoformat()
            res = (
                self.client.table("posts")
                .select("*")
                .eq("published", False)
                .eq("draft", False)
                .lte("publish_time", now_str)
                .execute()
            )
            return res.data or []
        except Exception as e:
            print(f"Error getting due posts: {e}")
            return []

    def mark_post_published(self, post_id: int):
        """Mark a post as published."""
        try:
            self.client.table("posts").update({"published": True}).eq("id", post_id).execute()
            return True
        except Exception as e:
            print(f"Error marking post {post_id} as published: {e}")
            return False

    def update_channel_admin_status(self, channel_id: int, is_admin: bool):
        """Update channel admin verification status."""
        try:
            update_data = {
                "is_admin_verified": is_admin,
                "admin_check_date": "now()"
            }
            self.client.table("channels").update(update_data).eq("id", channel_id).execute()
            return True
        except Exception as e:
            print(f"Error updating channel {channel_id} admin status: {e}")
            return False

    def list_posts_by_channel(self, channel_id: int, only_pending: bool = False):
        """List posts for a specific channel."""
        try:
            query = self.client.table("posts").select("*").eq("channel_id", channel_id)
            if only_pending:
                query = query.eq("published", False)
            query = query.order("publish_time", desc=False)
            res = query.execute()
            return res.data or []
        except Exception as e:
            print(f"Error listing posts for channel {channel_id}: {e}")
            return []

    def get_scheduled_posts_by_channel(self, user_id: int = None):
        """Get scheduled posts for channels user has access to."""
        try:
            if user_id:
                user_channels = self.get_user_channels(user_id)
                if not user_channels:
                    return []
                channel_ids = [ch["id"] for ch in user_channels]
                query = self.client.table("posts").select("*, channels(name, chat_id)").eq("published", False).eq("draft", False).in_("channel_id", channel_ids)
            else:
                query = self.client.table("posts").select("*, channels(name, chat_id)").eq("published", False).eq("draft", False)
            
            query = query.order("publish_time", desc=False)
            res = query.execute()
            return res.data or []
        except Exception as e:
            print(f"Error getting scheduled posts by channel: {e}")
            return []

    def get_draft_posts_by_channel(self, user_id: int = None):
        """Get draft posts for channels user has access to."""
        try:
            if user_id:
                user_channels = self.get_user_channels(user_id)
                if not user_channels:
                    return []
                channel_ids = [ch["id"] for ch in user_channels]
                query = self.client.table("posts").select("*, channels(name, chat_id)").eq("draft", True).in_("channel_id", channel_ids)
            else:
                query = self.client.table("posts").select("*, channels(name, chat_id)").eq("draft", True)
            
            query = query.order("created_at", desc=True)
            res = query.execute()
            return res.data or []
        except Exception as e:
            print(f"Error getting draft posts by channel: {e}")
            return []

    def get_notification_settings(self, user_id: int):
        """Get notification settings for user."""
        try:
            res = self.client.table("notification_settings").select("*").eq("user_id", user_id).execute()
            data = res.data or []
            return data[0] if data else None
        except Exception as e:
            print(f"Error getting notification settings for user {user_id}: {e}")
            return None

    def create_notification_settings(self, settings: dict):
        """Create notification settings for user."""
        try:
            res = self.client.table("notification_settings").insert(settings).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            print(f"Error creating notification settings: {e}")
            return None

    def update_notification_settings(self, user_id: int, updates: dict):
        """Update notification settings for user."""
        try:
            res = self.client.table("notification_settings").update(updates).eq("user_id", user_id).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            print(f"Error updating notification settings for user {user_id}: {e}")
            return None

    # Legacy compatibility methods (will be removed later)
    def is_user_in_project(self, user_id: int, project_id: int):
        """Legacy method - now checks if user has any channels."""
        try:
            user_channels = self.get_user_channels(user_id)
            return len(user_channels) > 0
        except:
            return False
