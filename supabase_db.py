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
                current_project BIGINT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            
            CREATE TABLE IF NOT EXISTS projects (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                name TEXT NOT NULL,
                owner_id BIGINT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            
            CREATE TABLE IF NOT EXISTS user_projects (
                user_id BIGINT,
                project_id BIGINT,
                role TEXT DEFAULT 'admin',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                PRIMARY KEY (user_id, project_id)
            );
            
            CREATE TABLE IF NOT EXISTS channels (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                user_id BIGINT,
                project_id BIGINT,
                name TEXT NOT NULL,
                chat_id BIGINT NOT NULL,
                username TEXT,
                is_admin_verified BOOLEAN DEFAULT FALSE,
                admin_check_date TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            
            CREATE TABLE IF NOT EXISTS channel_admins (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                channel_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                added_by BIGINT,
                is_active BOOLEAN DEFAULT TRUE,
                UNIQUE(channel_id, user_id)
            );
            
            CREATE TABLE IF NOT EXISTS posts (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                user_id BIGINT,
                project_id BIGINT,
                channel_id BIGINT,
                chat_id BIGINT,
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
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            
            CREATE TABLE IF NOT EXISTS notification_settings (
                user_id BIGINT PRIMARY KEY,
                post_published BOOLEAN DEFAULT TRUE,
                post_failed BOOLEAN DEFAULT TRUE,
                daily_summary BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
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
                "notify_before": 0,
                "current_project": None
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

    # Project management (legacy, поддерживаем для совместимости)
    def create_project(self, owner_id: int, name: str):
        """Create a new project and assign owner as admin."""
        try:
            proj_data = {"name": name, "owner_id": owner_id}
            res_proj = self.client.table("projects").insert(proj_data).execute()
            project = res_proj.data[0] if res_proj.data else None
            if project:
                # Add owner to user_projects with role 'owner'
                member_data = {"user_id": owner_id, "project_id": project["id"], "role": "owner"}
                self.client.table("user_projects").insert(member_data).execute()
            return project
        except Exception as e:
            print(f"Error creating project for user {owner_id}: {e}")
            return None

    def list_projects(self, user_id: int):
        """List all projects that a user is a member of."""
        try:
            res = self.client.table("user_projects").select("*").eq("user_id", user_id).execute()
            memberships = res.data or []
            project_ids = [m["project_id"] for m in memberships]
            if not project_ids:
                return []
            res_proj = self.client.table("projects").select("*").in_("id", project_ids).execute()
            projects = res_proj.data or []
            for proj in projects:
                for m in memberships:
                    if m["project_id"] == proj["id"]:
                        proj["role"] = m.get("role")
                        break
            return projects
        except Exception as e:
            print(f"Error listing projects for user {user_id}: {e}")
            return []

    def get_project(self, project_id: int):
        """Retrieve a project by ID."""
        try:
            res = self.client.table("projects").select("*").eq("id", project_id).execute()
            data = res.data or []
            return data[0] if data else None
        except Exception as e:
            print(f"Error getting project {project_id}: {e}")
            return None

    def is_user_in_project(self, user_id: int, project_id: int):
        """Check if a user is a member of the given project."""
        try:
            res = self.client.table("user_projects").select("user_id").eq("user_id", user_id).eq("project_id", project_id).execute()
            return bool(res.data)
        except Exception as e:
            print(f"Error checking if user {user_id} in project {project_id}: {e}")
            return False

    def add_user_to_project(self, user_id: int, project_id: int, role: str = "admin"):
        """Add a user to a project with the given role."""
        try:
            data = {"user_id": user_id, "project_id": project_id, "role": role}
            self.client.table("user_projects").insert(data).execute()
            return True
        except Exception:
            return False

    # Channel management (новая логика с администраторами)
    def add_channel(self, user_id: int, chat_id: int, name: str, project_id: int = None, username: str = None, is_admin_verified: bool = False):
        """Add a new channel (or update its name if it exists) and add user as admin."""
        try:
            # Проверяем, существует ли канал с таким chat_id
            res = self.client.table("channels").select("*").eq("chat_id", chat_id).execute()
            if res.data:
                # Обновляем существующий канал
                channel = res.data[0]
                update_data = {
                    "name": name,
                    "username": username,
                    "is_admin_verified": is_admin_verified,
                    "admin_check_date": "now()" if is_admin_verified else None
                }
                self.client.table("channels").update(update_data).eq("id", channel["id"]).execute()
                
                # Добавляем пользователя как администратора, если его там нет
                self.add_channel_admin(channel["id"], user_id, user_id)
                
                # Обновляем данные канала
                res_updated = self.client.table("channels").select("*").eq("id", channel["id"]).execute()
                return res_updated.data[0] if res_updated.data else channel
            
            # Создаем новый канал
            data = {
                "user_id": user_id, 
                "project_id": project_id, 
                "name": name, 
                "chat_id": chat_id,
                "username": username,
                "is_admin_verified": is_admin_verified,
                "admin_check_date": "now()" if is_admin_verified else None
            }
            res_insert = self.client.table("channels").insert(data).execute()
            channel = res_insert.data[0] if res_insert.data else None
            
            if channel:
                # Добавляем создателя как администратора (триггер должен сделать это автоматически, но на всякий случай)
                self.add_channel_admin(channel["id"], user_id, user_id)
            
            return channel
        except Exception as e:
            print(f"Error adding channel {chat_id}: {e}")
            return None

    def add_channel_admin(self, channel_id: int, user_id: int, added_by: int):
        """Add user as channel administrator."""
        try:
            data = {
                "channel_id": channel_id,
                "user_id": user_id,
                "added_by": added_by,
                "is_active": True
            }
            self.client.table("channel_admins").insert(data).execute()
            return True
        except Exception as e:
            # Если пользователь уже администратор, это нормально
            if "duplicate key" in str(e).lower() or "unique constraint" in str(e).lower():
                return True
            print(f"Error adding channel admin {user_id} to channel {channel_id}: {e}")
            return False

    def remove_channel_admin(self, channel_id: int, user_id: int):
        """Remove user from channel administrators."""
        try:
            self.client.table("channel_admins").update({"is_active": False}).eq("channel_id", channel_id).eq("user_id", user_id).execute()
            return True
        except Exception as e:
            print(f"Error removing channel admin {user_id} from channel {channel_id}: {e}")
            return False

    def is_channel_admin(self, channel_id: int, user_id: int):
        """Check if user is administrator of the channel."""
        try:
            res = self.client.table("channel_admins").select("id").eq("channel_id", channel_id).eq("user_id", user_id).eq("is_active", True).execute()
            return bool(res.data)
        except Exception as e:
            print(f"Error checking channel admin {user_id} for channel {channel_id}: {e}")
            return False

    def get_channel_admins(self, channel_id: int):
        """Get all administrators of a channel."""
        try:
            res = self.client.table("channel_admins").select("user_id, added_at, added_by").eq("channel_id", channel_id).eq("is_active", True).execute()
            return res.data or []
        except Exception as e:
            print(f"Error getting channel admins for channel {channel_id}: {e}")
            return []

    def list_channels(self, user_id: int = None, project_id: int = None):
        """List channels accessible to user (as admin) or by project."""
        try:
            if user_id is not None:
                # Получаем каналы, где пользователь является администратором
                res = self.client.rpc("get_user_accessible_channels", {"check_user_id": user_id}).execute()
                return res.data or []
            elif project_id is not None:
                # Legacy: получаем каналы по проекту
                query = self.client.table("channels").select("*").eq("project_id", project_id)
                res = query.execute()
                return res.data or []
            else:
                return []
        except Exception as e:
            print(f"Error listing channels: {e}")
            return []

    def remove_channel(self, project_id: int, identifier: str):
        """Remove a channel (by chat_id or internal id) - legacy method."""
        try:
            # Для совместимости оставляем метод, но теперь удаляем по channel_id
            channel_to_delete = None
            try:
                cid = int(identifier)
            except ValueError:
                return False
            
            # Try identifier as chat_id
            res = self.client.table("channels").select("*").eq("chat_id", cid).execute()
            if res.data:
                channel_to_delete = res.data[0]
            else:
                # Try identifier as internal channel id
                res = self.client.table("channels").select("*").eq("id", cid).execute()
                if res.data:
                    channel_to_delete = res.data[0]
            
            if not channel_to_delete:
                return False
            
            chan_id = channel_to_delete.get("id")
            # Delete channel and any related posts
            self.client.table("channels").delete().eq("id", chan_id).execute()
            self.client.table("posts").delete().eq("channel_id", chan_id).execute()
            self.client.table("channel_admins").delete().eq("channel_id", chan_id).execute()
            return True
        except Exception as e:
            print(f"Error removing channel {identifier}: {e}")
            return False

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
        """Retrieve a single channel by Telegram chat_id (first match)."""
        try:
            res = self.client.table("channels").select("*").eq("chat_id", chat_id).execute()
            data = res.data or []
            return data[0] if data else None
        except Exception as e:
            print(f"Error getting channel by chat_id {chat_id}: {e}")
            return None

    # Post management (новая логика с проверкой прав через каналы)
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
            
            print(f"Inserting post data: {post_data}")
            
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

    def can_user_access_post(self, user_id: int, post_id: int):
        """Check if user can access post (is admin of the channel)."""
        try:
            # Используем функцию базы данных для проверки прав
            res = self.client.rpc("user_can_access_post", {
                "check_user_id": user_id,
                "check_post_id": post_id
            }).execute()
            return res.data if res.data is not None else False
        except Exception as e:
            print(f"Error checking post access for user {user_id}, post {post_id}: {e}")
            return False

    def list_posts(self, user_id: int = None, project_id: int = None, only_pending: bool = True):
        """List posts accessible to user (through channel admin rights)."""
        try:
            if user_id is not None:
                # Используем новую функцию для получения доступных постов
                res = self.client.rpc("get_user_accessible_posts", {
                    "check_user_id": user_id,
                    "only_pending": only_pending
                }).execute()
                return res.data or []
            elif project_id is not None:
                # Legacy: получаем посты по проекту
                query = self.client.table("posts").select("*")
                if only_pending:
                    query = query.eq("published", False)
                query = query.eq("project_id", project_id)
                query = query.order("publish_time", desc=False)
                res = query.execute()
                return res.data or []
            else:
                return []
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

    def get_scheduled_posts_by_channel(self, project_id: int = None, user_id: int = None):
        """Get scheduled posts grouped by channel (accessible to user)."""
        try:
            if user_id:
                # Получаем посты через права доступа пользователя
                res = self.client.rpc("get_user_accessible_posts", {
                    "check_user_id": user_id,
                    "only_pending": True
                }).execute()
                posts = res.data or []
                # Фильтруем только запланированные (не черновики)
                return [p for p in posts if not p.get('draft') and p.get('publish_time')]
            elif project_id:
                # Legacy: получаем по проекту
                query = self.client.table("posts").select("*, channels(name, chat_id)").eq("published", False).eq("draft", False).eq("project_id", project_id)
                query = query.order("publish_time", desc=False)
                res = query.execute()
                return res.data or []
            else:
                return []
        except Exception as e:
            print(f"Error getting scheduled posts by channel: {e}")
            return []

    def get_draft_posts_by_channel(self, project_id: int = None, user_id: int = None):
        """Get draft posts grouped by channel (accessible to user)."""
        try:
            if user_id:
                # Получаем посты через права доступа пользователя
                res = self.client.rpc("get_user_accessible_posts", {
                    "check_user_id": user_id,
                    "only_pending": False
                }).execute()
                posts = res.data or []
                # Фильтруем только черновики
                return [p for p in posts if p.get('draft')]
            elif project_id:
                # Legacy: получаем по проекту
                query = self.client.table("posts").select("*, channels(name, chat_id)").eq("draft", True).eq("project_id", project_id)
                query = query.order("created_at", desc=True)
                res = query.execute()
                return res.data or []
            else:
                return []
        except Exception as e:
            print(f"Error getting draft posts by channel: {e}")
            return []

    # Notification settings (без изменений)
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

    # Helper methods for backward compatibility
    def is_user_in_project(self, user_id: int, project_id: int):
        """Legacy method - check if user has access to project posts via channels."""
        try:
            # Получаем каналы пользователя
            channels = self.list_channels(user_id=user_id)
            # Проверяем, есть ли среди них каналы с указанным project_id
            for channel in channels:
                if channel.get("project_id") == project_id:
                    return True
            return False
        except Exception as e:
            print(f"Error checking user {user_id} in project {project_id}: {e}")
            return False
