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
        
        # Add default feeds for new user
        default_feeds = [
            "https://www.langchain.dev/rss.xml",
            "https://openai.com/blog/rss.xml",
            "https://pythonweekly.com/rss",
            "https://huggingface.co/blog/feed.xml",
            "https://thehackernews.com/rss.xml"
        ]
        
        for feed_url in default_feeds:
            cursor.execute('''
                INSERT OR IGNORE INTO user_feeds (user_id, feed_url)
                VALUES (?, ?)
            ''', (user_id, feed_url))
        
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

def get_user_feeds(user_id: str) -> List[str]:
    """Get RSS feeds for a specific user"""
    conn = sqlite3.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT feed_url FROM user_feeds WHERE user_id = ?
    ''', (user_id,))
    
    feeds = [row[0] for row in cursor.fetchall()]
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

# Initialize database on import
init_db()
