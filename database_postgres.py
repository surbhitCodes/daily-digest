import os
import psycopg2
import psycopg2.extras
from typing import List, Dict, Optional
import uuid
from datetime import datetime
from urllib.parse import urlparse

def get_db_connection():
    """Get database connection - PostgreSQL for production, SQLite for development"""
    database_url = os.getenv("DATABASE_URL")
    
    if database_url and database_url.startswith("postgres"):
        # Parse PostgreSQL URL
        result = urlparse(database_url)
        return psycopg2.connect(
            database=result.path[1:],
            user=result.username,
            password=result.password,
            host=result.hostname,
            port=result.port
        )
    else:
        # Fallback to SQLite for local development
        import sqlite3
        return sqlite3.connect(database_url or "users.db")

def is_postgres():
    """Check if using PostgreSQL"""
    database_url = os.getenv("DATABASE_URL", "")
    return database_url.startswith("postgres")

def get_placeholder():
    """Get correct SQL placeholder for current database"""
    return "%s" if is_postgres() else "?"

def init_db():
    """Initialize the database with user tables"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    database_url = os.getenv("DATABASE_URL", "")
    is_postgres = database_url.startswith("postgres")
    
    if is_postgres:
        # PostgreSQL schema
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                slack_webhook_url TEXT NOT NULL,
                timezone TEXT DEFAULT 'UTC',
                schedule_hour INTEGER DEFAULT 8,
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_digest_sent TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_feeds (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                feed_url TEXT NOT NULL,
                feed_name TEXT,
                active BOOLEAN DEFAULT TRUE,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id, feed_url)
            )
        ''')
    else:
        # SQLite schema (for local development)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                slack_webhook_url TEXT NOT NULL,
                timezone TEXT DEFAULT 'UTC',
                schedule_hour INTEGER DEFAULT 8,
                active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_digest_sent TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_feeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                feed_url TEXT NOT NULL,
                feed_name TEXT,
                active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id, feed_url)
            )
        ''')
    
    conn.commit()
    conn.close()

def add_user(email: str, slack_webhook_url: str, timezone: str = "UTC", schedule_hour: int = 8) -> str:
    """Add a new user and return their ID"""
    user_id = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()
    
    database_url = os.getenv("DATABASE_URL", "")
    is_postgres = database_url.startswith("postgres")
    
    try:
        if is_postgres:
            cursor.execute('''
                INSERT INTO users (id, email, slack_webhook_url, timezone, schedule_hour)
                VALUES (%s, %s, %s, %s, %s)
            ''', (user_id, email, slack_webhook_url, timezone, schedule_hour))
        else:
            cursor.execute('''
                INSERT INTO users (id, email, slack_webhook_url, timezone, schedule_hour)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, email, slack_webhook_url, timezone, schedule_hour))
        
        # Add default feeds for new user
        default_feeds = [
            ("https://blog.langchain.dev/rss/", "LangChain Blog"),
            ("https://openai.com/blog/rss.xml", "OpenAI Blog"),
            ("https://www.blog.pythonlibrary.org/feed/", "Python Library Blog"),
            ("https://huggingface.co/blog/feed.xml", "Hugging Face Blog"),
            ("https://feeds.feedburner.com/TheHackersNews", "The Hacker News"),
            ("https://javascriptweekly.com/rss", "JavaScript Weekly"),
            ("https://techcrunch.com/feed/", "TechCrunch"),
            ("https://feeds.arstechnica.com/arstechnica/index", "Ars Technica"),
            ("https://stackoverflow.blog/feed/", "Stack Overflow Blog"),
            ("https://news.mit.edu/topic/mitmachine-learning-rss.xml", "MIT ML News")
        ]
        
        database_url = os.getenv("DATABASE_URL", "")
        is_postgres = database_url.startswith("postgres")
        
        for feed_url, feed_name in default_feeds:
            if is_postgres:
                cursor.execute('''
                    INSERT INTO user_feeds (user_id, feed_url, feed_name)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, feed_url) DO NOTHING
                ''', (user_id, feed_url, feed_name))
            else:
                cursor.execute('''
                    INSERT OR IGNORE INTO user_feeds (user_id, feed_url, feed_name)
                    VALUES (?, ?, ?)
                ''', (user_id, feed_url, feed_name))
        
        conn.commit()
        return user_id
    except Exception as e:
        conn.rollback()
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise ValueError("Email already exists")
        raise e
    finally:
        conn.close()

def get_all_active_users() -> List[Dict]:
    """Get all active users for sending digests"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    placeholder = get_placeholder()
    cursor.execute(f'''
        SELECT id, email, slack_webhook_url, timezone, schedule_hour, last_digest_sent
        FROM users WHERE active = {placeholder}
    ''', (True,))
    
    users = []
    for row in cursor.fetchall():
        users.append({
            'id': row[0],
            'email': row[1],
            'slack_webhook_url': row[2],
            'timezone': row[3],
            'schedule_hour': row[4],
            'last_digest_sent': row[5]
        })
    
    conn.close()
    return users

def get_user_feeds(user_id: str) -> List[Dict]:
    """Get RSS feeds for a specific user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, feed_url, feed_name, active FROM user_feeds WHERE user_id = %s AND active = %s
    ''', (user_id, True))
    
    feeds = []
    for row in cursor.fetchall():
        feeds.append({
            'id': row[0],
            'url': row[1],
            'name': row[2] or row[1],
            'active': row[3]
        })
    
    conn.close()
    return feeds

def update_last_digest_sent(user_id: str):
    """Update the last digest sent timestamp"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE users SET last_digest_sent = CURRENT_TIMESTAMP
        WHERE id = %s
    ''', (user_id,))
    
    conn.commit()
    conn.close()

def get_user_by_id(user_id: str) -> Optional[Dict]:
    """Get user details by ID"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, email, slack_webhook_url, timezone, schedule_hour, active
        FROM users WHERE id = %s
    ''', (user_id,))
    
    row = cursor.fetchone()
    if row:
        user = {
            'id': row[0],
            'email': row[1],
            'slack_webhook_url': row[2],
            'timezone': row[3],
            'schedule_hour': row[4],
            'active': row[5]
        }
        conn.close()
        return user
    
    conn.close()
    return None

def add_user_feed(user_id: str, feed_url: str, feed_name: str = None) -> bool:
    """Add a new RSS feed for a user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO user_feeds (user_id, feed_url, feed_name)
            VALUES (%s, %s, %s)
        ''', (user_id, feed_url, feed_name or feed_url))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()

def remove_user_feed(user_id: str, feed_id: int) -> bool:
    """Remove an RSS feed for a user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        DELETE FROM user_feeds WHERE id = %s AND user_id = %s
    ''', (feed_id, user_id))
    
    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return success

def get_all_user_feeds(user_id: str) -> List[Dict]:
    """Get all RSS feeds for a user (including inactive)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, feed_url, feed_name, active FROM user_feeds WHERE user_id = %s
    ''', (user_id,))
    
    feeds = []
    for row in cursor.fetchall():
        feeds.append({
            'id': row[0],
            'url': row[1],
            'name': row[2] or row[1],
            'active': bool(row[3])
        })
    
    conn.close()
    return feeds

# Initialize database on import
init_db()
