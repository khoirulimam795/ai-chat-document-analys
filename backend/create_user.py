# backend/create_user.py
import sys
import os

# Tambah path biar bisa import module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.models.user import UserDB
from app.utils.auth import hash_password

def create_user(username, password):
    try:
        if UserDB.exists(username):
            print(f"❌ User '{username}' sudah ada!")
            return False
        
        UserDB.create(username, hash_password(password))
        print(f"✅ User '{username}' berhasil dibuat!")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def list_users():
    """Lihat semua user yang udah ada"""
    conn = UserDB._get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, created_at FROM users")
    rows = cursor.fetchall()
    conn.close()
    
    print("\n📋 Daftar User:")
    print("-" * 50)
    for row in rows:
        print(f"ID: {row[0]} | Username: {row[1]} | Created: {row[2]}")
    print("-" * 50)

if __name__ == "__main__":
    # Buat user admin
    create_user("admin", "admin123")
    create_user("user1", "imam123")
    
    # Tampilkan daftar
    list_users()