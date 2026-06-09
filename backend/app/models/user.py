import sqlite3
import json
from typing import Optional, Dict
from datetime import datetime

DB_PATH = "user.db"

class UserDB:
    @staticmethod
    def _get_db():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        # Create table if not exists
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                upload_date TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        return conn
    
    @staticmethod
    def create(username: str, password_hash: str) -> Dict:
        conn = UserDB._get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, password_hash, datetime.now().isoformat())
        )
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return {"id": user_id, "username": username}
    
    @staticmethod
    def get_by_username(username: str) -> Optional[Dict]:
        conn = UserDB._get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    @staticmethod
    def exists(username: str) -> bool:
        conn = UserDB._get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM users WHERE username = ?", (username,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists
    
    @staticmethod
    def add_upload(user_id: int, filename: str):
        conn = UserDB._get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_uploads (user_id, filename, upload_date) VALUES (?, ?, ?)",
            (user_id, filename, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
    
    @staticmethod
    def get_uploads(user_id: int) -> list:
        conn = UserDB._get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT filename, upload_date FROM user_uploads WHERE user_id = ? ORDER BY upload_date DESC",
            (user_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]