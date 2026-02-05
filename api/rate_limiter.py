import os
import time
from typing import Dict, List
from collections import defaultdict
from fastapi import Request, HTTPException

class SimpleRateLimiter:
    """
    シンプルなグローバルレート制限（1時間1000リクエスト）
    
    Vercel環境では各関数インスタンスが独立して動作するため、
    完全な制限は保証されませんが、AI API乱用防止には有効です。
    """
    
    def __init__(self):
        self.enabled = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
        self.global_per_hour = int(os.getenv("RATE_LIMIT_GLOBAL_PER_HOUR", "1000"))
        
        # グローバルカウンター
        self.global_log: Dict[str, List[float]] = defaultdict(list)
        self.last_cleanup = time.time()
        
        if self.enabled:
            print(f"✅ [RateLimit] Enabled - {self.global_per_hour} requests/hour (global)")
    
    async def check_rate_limit(self, request: Request, endpoint: str = "default") -> dict:
        """グローバルレート制限をチェック（1000 req/時間）"""
        if not self.enabled:
            return {}
        
        self._cleanup_old_entries()
        self._check_global_limit(endpoint)
        return {}
    
    def _check_global_limit(self, endpoint: str):
        """グローバルレート制限チェック（1時間1000リクエスト）"""
        if self.global_per_hour <= 0:
            return
        
        window = 3600  # 1時間
        now = time.time()
        key = f"global:{endpoint}"
        
        # 古いエントリを削除
        self.global_log[key] = [t for t in self.global_log[key] if t > now - window]
        count = len(self.global_log[key])
        
        if count >= self.global_per_hour:
            print(f"⚠️ [RateLimit] Global limit reached for {endpoint}: {count}/{self.global_per_hour}")
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "レート制限を超えました",
                    "message": f"1時間あたり{self.global_per_hour}リクエストまでです。しばらく待ってから再試行してください。",
                    "retry_after": 3600
                }
            )
        
        self.global_log[key].append(now)
    
    def _cleanup_old_entries(self):
        """古いエントリを定期的に削除してメモリを節約（1時間ごと）"""
        now = time.time()
        cleanup_interval = 3600  # 1時間ごとにクリーンアップ
        if now - self.last_cleanup < cleanup_interval:
            return
        
        # 2時間以上古いデータを削除
        for key in list(self.global_log.keys()):
            self.global_log[key] = [t for t in self.global_log[key] if t > now - 7200]
            if not self.global_log[key]:
                del self.global_log[key]
        
        self.last_cleanup = now

# グローバルインスタンス
rate_limiter = SimpleRateLimiter()
