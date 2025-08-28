import sqlite3
import os
from typing import List, Dict, Optional
import uuid
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "users.db")

def init_db():
    """Initialize the database with user table"""
    conn = sqlite3.connect(DATABASE_URL)
    cursor = conn.cursor()
    
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
    conn = sqlite3.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO users (id, email, slack_webhook_url, timezone, schedule_hour)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, email, slack_webhook_url, timezone, schedule_hour))
        
        # Add default feeds for new user (more feeds for 10+ articles)
        default_feeds = [
            ("https://www.langchain.dev/rss.xml", "LangChain Blog"),
            ("https://openai.com/blog/rss.xml", "OpenAI Blog"),
            ("https://pythonweekly.com/rss", "Python Weekly"),
            ("https://huggingface.co/blog/feed.xml", "Hugging Face Blog"),
            ("https://thehackernews.com/rss.xml", "The Hacker News"),
            ("https://javascriptweekly.com/rss", "JavaScript Weekly"),
            ("https://techcrunch.com/feed/", "TechCrunch"),
            ("https://feeds.arstechnica.com/arstechnica/index", "Ars Technica"),
            ("https://www.wired.com/feed/rss", "Wired"),
            ("https://venturebeat.com/feed/", "VentureBeat")
        ]
        
        for feed_url, feed_name in default_feeds:
            cursor.execute('''
                INSERT OR IGNORE INTO user_feeds (user_id, feed_url, feed_name)
                VALUES (?, ?, ?)
            ''', (user_id, feed_url, feed_name))
        
        conn.commit()
        return user_id
    except sqlite3.IntegrityError:
        raise ValueError("Email already exists")
    finally:
        conn.close()

def get_all_active_users() -> List[Dict]:
    """Get all active users for sending digests"""
    conn = sqlite3.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, email, slack_webhook_url, timezone, schedule_hour
        FROM users WHERE active = 1
    ''')
    
    users = []
    for row in cursor.fetchall():
        users.append({
            'id': row[0],
            'email': row[1],
            'slack_webhook_url': row[2],
            'timezone': row[3],
            'schedule_hour': row[4]
        })
    
    conn.close()
    return users

def get_user_feeds(user_id: str) -> List[Dict]:
    """Get RSS feeds for a specific user"""
    conn = sqlite3.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, feed_url, feed_name, active FROM user_feeds WHERE user_id = ? AND active = 1
    ''', (user_id,))
    
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
    conn = sqlite3.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE users SET last_digest_sent = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (user_id,))
    
    conn.commit()
    conn.close()

def get_user_by_id(user_id: str) -> Optional[Dict]:
    """Get user details by ID"""
    conn = sqlite3.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, email, slack_webhook_url, timezone, schedule_hour, active
        FROM users WHERE id = ?
    ''', (user_id,))
    
    row = cursor.fetchone()
    if row:
        return {
            'id': row[0],
            'email': row[1],
            'slack_webhook_url': row[2],
            'timezone': row[3],
            'schedule_hour': row[4],
            'active': row[5]
        }
    
    conn.close()
    return None

def add_user_feed(user_id: str, feed_url: str, feed_name: str = None) -> bool:
    """Add a new RSS feed for a user"""
    conn = sqlite3.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO user_feeds (user_id, feed_url, feed_name)
            VALUES (?, ?, ?)
        ''', (user_id, feed_url, feed_name or feed_url))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def remove_user_feed(user_id: str, feed_id: int) -> bool:
    """Remove an RSS feed for a user"""
    conn = sqlite3.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    cursor.execute('''
        DELETE FROM user_feeds WHERE id = ? AND user_id = ?
    ''', (feed_id, user_id))
    
    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return success

def get_all_user_feeds(user_id: str) -> List[Dict]:
    """Get all RSS feeds for a user (including inactive)"""
    conn = sqlite3.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, feed_url, feed_name, active FROM user_feeds WHERE user_id = ?
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
