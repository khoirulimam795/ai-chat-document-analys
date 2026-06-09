# backend/app/utils/rate_limiter.py
from collections import defaultdict
import time
from typing import Tuple


class RateLimiter:
    """
    Rate limiter sederhana untuk mencegah spam request
    """
    def __init__(self, max_requests: int = 30, time_window: int = 60):
        """
        Args:
            max_requests: Maksimal request dalam time_window
            time_window: Jendela waktu dalam detik (default 60 detik)
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = defaultdict(list)
    
    def can_request(self, user_id: int) -> Tuple[bool, int]:
        """
        Cek apakah user boleh request
        
        Returns:
            (allowed, wait_seconds)
            allowed: True jika boleh, False jika kena limit
            wait_seconds: Berapa detik harus tunggu (0 jika allowed)
        """
        now = time.time()
        cutoff = now - self.time_window
        
        # Bersihkan request lama
        self.requests[user_id] = [t for t in self.requests[user_id] if t > cutoff]
        
        # Cek limit
        if len(self.requests[user_id]) >= self.max_requests:
            # Hitung berapa detik lagi bisa request
            oldest = min(self.requests[user_id]) if self.requests[user_id] else now
            wait_seconds = int(self.time_window - (now - oldest)) + 1
            return False, wait_seconds
        
        # Catat request baru
        self.requests[user_id].append(now)
        return True, 0
    
    def reset_user(self, user_id: int):
        """Reset limit untuk user tertentu"""
        if user_id in self.requests:
            del self.requests[user_id]
    
    def reset_all(self):
        """Reset semua limit"""
        self.requests.clear()


# Instance global
rate_limiter = RateLimiter(max_requests=30, time_window=60)