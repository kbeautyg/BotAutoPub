import json
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
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                timezone TEXT DEFAULT 'UTC',
                language TEXT DEFAULT 'ru',
                date_format TEXT DEFAULT 'YYYY-MM-DD',
                time_format TEXT DEFAULT 'HH:MM',
                notify_before INTEGER DEFAULT 0,
                current_project BIGINT
            );
            CREATE TABLE IF NOT EXISTS projects (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                name TEXT,
                owner_id BIGINT
            );
            CREATE TABLE IF NOT EXISTS user_projects (
                user_id BIGINT,
                project_id BIGINT,
                role TEXT,
                PRIMARY KEY (user_id, project_id)
            );
            ALTER TABLE user_projects
              ADD FOREIGN KEY (user_id) REFERENCES users(user_id),
              ADD FOREIGN KEY (project_id) REFERENCES projects(id);
            ALTER TABLE channels 
              ADD COLUMN IF NOT EXISTS project_id BIGINT;
            ALTER TABLE posts 
              ADD COLUMN IF NOT EXISTS project_id BIGINT;
            ALTER TABLE channels 
              DROP CONSTRAINT IF EXISTS channels_user_id_chat_id_key;
            ALTER TABLE channels 
              ADD CONSTRAINT channels_project_chat_unique UNIQUE(project_id, chat_id);
            ALTER TABLE channels 
              ADD FOREIGN KEY (project_id) REFERENCES projects(id);
            ALTER TABLE posts 
              ADD FOREIGN KEY (project_id) REFERENCES projects(id);
            """
            try:
                self.client.postgrest.rpc("sql", {"sql": schema_sql}).execute()
            except Exception:
                # If unable to create/alter via API (e.g., insufficient permissions)
                pass

    # User management
    def get_user(self, user_id: int):
        """Retrieve user settings by Telegram user_id."""
        res = self.client.table("users").select("*").eq("user_id", user_id).execute()
        data = res.data or []
        return data[0] if data else None

    def ensure_user(self, user_id: int, default_lang: str = None):
        """Ensure a user exists in the users table. Creates with defaults if not present, and initializes default project."""
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

    def update_user(self, user_id: int, updates: dict):
        """Update user settings and return the updated record."""
        if not updates:
            return None
        res = self.client.table("users").update(updates).eq("user_id", user_id).execute()
        return res.data[0] if res.data else None

    # Project management
    def create_project(self, owner_id: int, name: str):
        """Create a new project and assign owner as admin."""
        proj_data = {"name": name, "owner_id": owner_id}
        res_proj = self.client.table("projects").insert(proj_data).execute()
        project = res_proj.data[0] if res_proj.data else None
        if project:
            # Add owner to user_projects with role 'owner'
            member_data = {"user_id": owner_id, "project_id": project["id"], "role": "owner"}
            self.client.table("user_projects").insert(member_data).execute()
        return project

    def list_projects(self, user_id: int):
        """List all projects that a user is a member of (with role info)."""
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

    def get_project(self, project_id: int):
        """Retrieve a project by ID."""
        res = self.client.table("projects").select("*").eq("id", project_id).execute()
        data = res.data or []
        return data[0] if data else None

    def is_user_in_project(self, user_id: int, project_id: int):
        """Check if a user is a member of the given project."""
        res = self.client.table("user_projects").select("user_id").eq("user_id", user_id).eq("project_id", project_id).execute()
        return bool(res.data)

    def add_user_to_project(self, user_id: int, project_id: int, role: str = "admin"):
        """Add a user to a project with the given role."""
        data = {"user_id": user_id, "project_id": project_id, "role": role}
        try:
            self.client.table("user_projects").insert(data).execute()
            return True
        except Exception:
            return False

    # Channel management
    def add_channel(self, user_id: int, chat_id: int, name: str, project_id: int, username: str = None, is_admin_verified: bool = False):
        """Add a new channel to the project (or update its name if it exists)."""
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

    def list_channels(self, user_id: int = None, project_id: int = None):
        """List all channels, optionally filtered by project or user (membership)."""
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

    def remove_channel(self, project_id: int, identifier: str):
        """Remove a channel (by chat_id or internal id) from the given project."""
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

    def get_channel(self, channel_id: int):
        """Retrieve a single channel by internal ID."""
        res = self.client.table("channels").select("*").eq("id", channel_id).execute()
        data = res.data or []
        return data[0] if data else None

    def get_channel_by_chat_id(self, chat_id: int):
        """Retrieve a single channel by Telegram chat_id (first match)."""
        res = self.client.table("channels").select("*").eq("chat_id", chat_id).execute()
        data = res.data or []
        return data[0] if data else None

    # Post management
    def add_post(self, post_data: dict):
        """Insert a new post into the database. Returns the inserted record."""
        if "buttons" in post_data and isinstance(post_data["buttons"], list):
            post_data["buttons"] = json.dumps(post_data["buttons"])
        res = self.client.table("posts").insert(post_data).execute()
        return res.data[0] if res.data else None

    def get_post(self, post_id: int):
        """Retrieve a single post by id."""
        res = self.client.table("posts").select("*").eq("id", post_id).execute()
        data = res.data or []
        return data[0] if data else None

    def list_posts(self, user_id: int = None, project_id: int = None, only_pending: bool = True):
        """List posts, optionally filtered by user or project and published status."""
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

    def update_post(self, post_id: int, updates: dict):
        """Update fields of a post and return the updated record."""
        if "buttons" in updates and isinstance(updates["buttons"], list):
            updates["buttons"] = json.dumps(updates["buttons"])
        res = self.client.table("posts").update(updates).eq("id", post_id).execute()
        return res.data[0] if res.data else None

    def delete_post(self, post_id: int):
        """Delete a post by id."""
        self.client.table("posts").delete().eq("id", post_id).execute()

    def get_due_posts(self, current_time):
        """Get all posts due at or before current_time (not published and not drafts)."""
        now_str = current_time.strftime("%Y-%m-%dT%H:%M:%S%z") if hasattr(current_time, "strftime") else str(current_time)
        res = self.client.table("posts").select("*").eq("published", False).eq("draft", False).lte("publish_time", now_str).execute()
        return res.data or []

    def mark_post_published(self, post_id: int):
        """Mark a post as published."""
        self.client.table("posts").update({"published": True}).eq("id", post_id).execute()

    def update_channel_admin_status(self, channel_id: int, is_admin: bool):
        """Update channel admin verification status."""
        update_data = {
            "is_admin_verified": is_admin,
            "admin_check_date": "now()"
        }
        self.client.table("channels").update(update_data).eq("id", channel_id).execute()

    def list_posts_by_channel(self, channel_id: int, only_pending: bool = False):
        """List posts for a specific channel."""
        query = self.client.table("posts").select("*").eq("channel_id", channel_id)
        if only_pending:
            query = query.eq("published", False)
        query = query.order("publish_time", desc=False)
        res = query.execute()
        return res.data or []

    def get_scheduled_posts_by_channel(self, project_id: int = None):
        """Get scheduled posts grouped by channel."""
        query = self.client.table("posts").select("*, channels(name, chat_id)").eq("published", False).eq("draft", False)
        if project_id:
            query = query.eq("project_id", project_id)
        query = query.order("publish_time", desc=False)
        res = query.execute()
        return res.data or []

    def get_draft_posts_by_channel(self, project_id: int = None):
        """Get draft posts grouped by channel."""
        query = self.client.table("posts").select("*, channels(name, chat_id)").eq("draft", True)
        if project_id:
            query = query.eq("project_id", project_id)
        query = query.order("created_at", desc=True)
        res = query.execute()
        return res.data or []

    def get_notification_settings(self, user_id: int):
        """Get notification settings for user."""
        res = self.client.table("notification_settings").select("*").eq("user_id", user_id).execute()
        data = res.data or []
        return data[0] if data else None

    def create_notification_settings(self, settings: dict):
        """Create notification settings for user."""
        res = self.client.table("notification_settings").insert(settings).execute()
        return res.data[0] if res.data else None

    def update_notification_settings(self, user_id: int, updates: dict):
        """Update notification settings for user."""
        res = self.client.table("notification_settings").update(updates).eq("user_id", user_id).execute()
        return res.data[0] if res.data else None
