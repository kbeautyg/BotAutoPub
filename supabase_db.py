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
            
            -- Add missing columns if they don't exist
            DO $$ 
            BEGIN
                -- Add project_id to channels if missing
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='channels' AND column_name='project_id') THEN
                    ALTER TABLE channels ADD COLUMN project_id BIGINT;
                END IF;
                
                -- Add project_id to posts if missing
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='project_id') THEN
                    ALTER TABLE posts ADD COLUMN project_id BIGINT;
                END IF;
                
                -- Rename format to parse_mode if format exists
                IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='format') THEN
                    ALTER TABLE posts RENAME COLUMN format TO parse_mode;
                END IF;
                
                -- Add parse_mode if missing
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='parse_mode') THEN
                    ALTER TABLE posts ADD COLUMN parse_mode TEXT DEFAULT 'HTML';
                END IF;
                
                -- Add other missing columns
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='notified') THEN
                    ALTER TABLE posts ADD COLUMN notified BOOLEAN DEFAULT FALSE;
                END IF;
                
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='channels' AND column_name='is_admin_verified') THEN
                    ALTER TABLE channels ADD COLUMN is_admin_verified BOOLEAN DEFAULT FALSE;
                END IF;
                
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='channels' AND column_name='admin_check_date') THEN
                    ALTER TABLE channels ADD COLUMN admin_check_date TIMESTAMP WITH TIME ZONE;
                END IF;
                
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='created_at') THEN
                    ALTER TABLE users ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
                END IF;
            END $$;
            
            -- Create constraints and indexes
            DO $$
            BEGIN
                -- Foreign key constraints
                IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='user_projects_user_id_fkey') THEN
                    ALTER TABLE user_projects ADD CONSTRAINT user_projects_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(user_id);
                END IF;
                
                IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='user_projects_project_id_fkey') THEN
                    ALTER TABLE user_projects ADD CONSTRAINT user_projects_project_id_fkey FOREIGN KEY (project_id) REFERENCES projects(id);
                END IF;
                
                IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='channels_project_id_fkey') THEN
                    ALTER TABLE channels ADD CONSTRAINT channels_project_id_fkey FOREIGN KEY (project_id) REFERENCES projects(id);
                END IF;
                
                IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='posts_project_id_fkey') THEN
                    ALTER TABLE posts ADD CONSTRAINT posts_project_id_fkey FOREIGN KEY (project_id) REFERENCES projects(id);
                END IF;
                
                -- Unique constraints
                IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='channels_project_chat_unique') THEN
                    ALTER TABLE channels ADD CONSTRAINT channels_project_chat_unique UNIQUE(project_id, chat_id);
                END IF;
            END $$;
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
        """Ensure a user exists in the users table. Creates with defaults if not present, and initializes default project."""
        try:
            user = self.get_user(user_id)
            if user:
                # If user exists but has no current_project (older data), create default project
                if not user.get("current_project"):
                    # Create a default project for existing user
                    lang = user.get("language", "ru")
                    proj_name = "Мой проект" if lang == "ru" else "My Project"
                    project = self.create_project(user_id, proj_name)
                    if project:
                        user = self.update_user(user_id, {"current_project": project["id"]})
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
            created_user = res_user.data[0] if res_user.data else None
            if created_user:
                # Create default project for new user
                proj_name = "Мой проект" if lang == "ru" else "My Project"
                project = self.create_project(user_id, proj_name)
                if project:
                    created_user = self.update_user(user_id, {"current_project": project["id"]})
            return created_user
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

    # Project management
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
        """List all projects that a user is a member of (with role info)."""
        try:
            # Get all project memberships for the user
            res = self.client.table("user_projects").select("*").eq("user_id", user_id).execute()
            memberships = res.data or []
            project_ids = [m["project_id"] for m in memberships]
            if not project_ids:
                return []
            res_proj = self.client.table("projects").select("*").in_("id", project_ids).execute()
            projects = res_proj.data or []
            # Optionally attach role info
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

    # Channel management
    def add_channel(self, user_id: int, chat_id: int, name: str, project_id: int, username: str = None, is_admin_verified: bool = False):
        """Add a new channel to the project (or update its name if it exists)."""
        try:
            res = self.client.table("channels").select("*").eq("project_id", project_id).eq("chat_id", chat_id).execute()
            if res.data:
                # Update channel info if it exists in this project
                update_data = {
                    "name": name,
                    "username": username,
                    "is_admin_verified": is_admin_verified,
                    "admin_check_date": "now()"
                }
                self.client.table("channels").update(update_data).eq("project_id", project_id).eq("chat_id", chat_id).execute()
                return res.data[0]
            
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
            return res_insert.data[0] if res_insert.data else None
        except Exception as e:
            print(f"Error adding channel {chat_id} to project {project_id}: {e}")
            return None

    def list_channels(self, user_id: int = None, project_id: int = None):
        """List all channels, optionally filtered by project or user (membership)."""
        try:
            query = self.client.table("channels").select("*")
            if project_id is not None:
                query = query.eq("project_id", project_id)
            elif user_id is not None:
                # Find all projects for this user and list channels in those projects
                res = self.client.table("user_projects").select("project_id").eq("user_id", user_id).execute()
                memberships = res.data or []
                proj_ids = [m["project_id"] for m in memberships]
                if proj_ids:
                    query = query.in_("project_id", proj_ids)
                else:
                    query = query.eq("project_id", -1)  # no projects, will return empty
            res = query.execute()
            return res.data or []
        except Exception as e:
            print(f"Error listing channels: {e}")
            return []

    def remove_channel(self, project_id: int, identifier: str):
        """Remove a channel (by chat_id or internal id) from the given project."""
        try:
            channel_to_delete = None
            if identifier.startswith("@"):
                return False  # Removing by username not supported
            try:
                cid = int(identifier)
            except ValueError:
                return False
            # Try identifier as chat_id
            res = self.client.table("channels").select("*").eq("project_id", project_id).eq("chat_id", cid).execute()
            if res.data:
                channel_to_delete = res.data[0]
            else:
                # Try identifier as internal channel id
                res = self.client.table("channels").select("*").eq("project_id", project_id).eq("id", cid).execute()
                if res.data:
                    channel_to_delete = res.data[0]
            if not channel_to_delete:
                return False
            chan_id = channel_to_delete.get("id")
            # Delete channel and any related posts
            self.client.table("channels").delete().eq("id", chan_id).execute()
            self.client.table("posts").delete().eq("channel_id", chan_id).execute()
            return True
        except Exception as e:
            print(f"Error removing channel {identifier} from project {project_id}: {e}")
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

    def list_posts(self, user_id: int = None, project_id: int = None, only_pending: bool = True):
        """List posts, optionally filtered by user or project and published status."""
        try:
            query = self.client.table("posts").select("*")
            if only_pending:
                query = query.eq("published", False)
            if project_id is not None:
                query = query.eq("project_id", project_id)
            elif user_id is not None:
                query = query.eq("user_id", user_id)
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

    def get_scheduled_posts_by_channel(self, project_id: int = None):
        """Get scheduled posts grouped by channel."""
        try:
            query = self.client.table("posts").select("*, channels(name, chat_id)").eq("published", False).eq("draft", False)
            if project_id:
                query = query.eq("project_id", project_id)
            query = query.order("publish_time", desc=False)
            res = query.execute()
            return res.data or []
        except Exception as e:
            print(f"Error getting scheduled posts by channel: {e}")
            return []

    def get_draft_posts_by_channel(self, project_id: int = None):
        """Get draft posts grouped by channel."""
        try:
            query = self.client.table("posts").select("*, channels(name, chat_id)").eq("draft", True)
            if project_id:
                query = query.eq("project_id", project_id)
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
