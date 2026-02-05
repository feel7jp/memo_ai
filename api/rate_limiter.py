import os
import time
from typing import Optional, Dict, List
from collections import defaultdict
from fastapi import Request, HTTPException

class SimpleRateLimiter:
    """
    シンプルなインメモリレート制限
    
    Vercel環境では各関数インスタンスが独立して動作するため、
    完全な制限は保証されませんが、基本的な悪用防止には有効です。
    """
    
    def __init__(self):
        # ハードコードされたデフォルト値（環境変数で上書き可能）
        self.enabled = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
        
        # 設定値の読み込み（デフォルト値をハードコード）
        self.per_minute = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
        self.global_per_hour = int(os.getenv("RATE_LIMIT_GLOBAL_PER_HOUR", "1000"))
        self.cleanup_interval = int(os.getenv("RATE_LIMIT_CLEANUP_INTERVAL", "300"))
        
        # インメモリストレージ: {ip:endpoint: [(timestamp1, timestamp2, ...)]}
        self.request_log: Dict[str, List[float]] = defaultdict(list)
        
        # グローバルカウンター（インスタンス単位）
        self.global_log: Dict[str, List[float]] = defaultdict(list)
        
        # 最後のクリーンアップ時刻
        self.last_cleanup = time.time()
        
        if self.enabled:
            print(f"✅ [RateLimit] Enabled - {self.global_per_hour} requests/hour (global)")
    
    async def check_rate_limit(
        self,
        request: Request,
        endpoint: str = "default",
        custom_limit: Optional[int] = None
    ) -> dict:
        """レート制限をチェック（IP別 + グローバル制限）
        
        戻り値: レート制限ヘッダー
        """
        if not self.enabled:
            return {}
        
        # 定期的にメモリをクリーンアップ
        self._cleanup_old_entries()
        
        # クライアントIPを取得
        client_ip = self._get_client_ip(request)
        
        # IP別制限チェック
        rate_limit_headers = self._check_ip_limit(client_ip, endpoint, custom_limit)
        
        # グローバル制限チェック
        self._check_global_limit(endpoint)
        
        return rate_limit_headers
    
    def _get_client_ip(self, request: Request) -> str:
        """クライアントIPを取得（Vercelのヘッダーを考慮）"""
        # Vercel環境ではx-forwarded-forヘッダーを使用
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        # x-real-ipヘッダーも確認
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # フォールバック
        return request.client.host if request.client else "unknown"
    
    def _check_ip_limit(
        self,
        client_ip: str,
        endpoint: str,
        custom_limit: Optional[int]
    ) -> dict:
        """IP別のレート制限チェック（Sliding Window）"""
        limit = custom_limit or self.per_minute
        window = 60  # 60秒ウィンドウ
        now = time.time()
        
        # ユニークキー
        key = f"{client_ip}:{endpoint}"
        
        # 古いエントリを削除（ウィンドウ外）
        self.request_log[key] = [
            t for t in self.request_log[key] 
            if t > now - window
        ]
        
        # 現在のカウント
        count = len(self.request_log[key])
        
        if count >= limit:
            # 最も古いエントリから次のリセット時刻を計算
            oldest = min(self.request_log[key]) if self.request_log[key] else now
            reset_time = int(oldest + window)
            retry_after = max(1, reset_time - int(now))
            
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "レート制限を超えました",
                    "message": f"1分あたり{limit}リクエストまでです。{retry_after}秒後に再試行してください。",
                    "retry_after": retry_after
                },
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                    "Retry-After": str(retry_after)
                }
            )
        
        # 新しいリクエストを記録
        self.request_log[key].append(now)
        
        # レート制限情報を返す
        return {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(limit - count - 1),
            "X-RateLimit-Reset": str(int(now + window))
        }
    
    def _check_global_limit(self, endpoint: str):
        """グローバルレート制限チェック（1時間1000リクエスト）"""
        if self.global_per_hour <= 0:
            return
        
        window = 3600  # 1時間
        now = time.time()
        key = f"global:{endpoint}"
        
        # 古いエントリを削除
        self.global_log[key] = [
            t for t in self.global_log[key]
            if t > now - window
        ]
        
        count = len(self.global_log[key])
        
        if count >= self.global_per_hour:
            print(f"⚠️ [RateLimit] Global limit reached for {endpoint}: {count}/{self.global_per_hour}")
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "レート制限を超えました",
                    "message": f"現在アクセスが集中しています。1時間あたり{self.global_per_hour}リクエストまでです。しばらく待ってから再試行してください。",
                    "retry_after": 3600
                }
            )
        
        # 記録
        self.global_log[key].append(now)
    
    def _cleanup_old_entries(self):
        """古いエントリを定期的に削除してメモリを節約"""
        now = time.time()
        
        if now - self.last_cleanup < self.cleanup_interval:
            return
        
        # IP別ログのクリーンアップ
        for key in list(self.request_log.keys()):
            self.request_log[key] = [
                t for t in self.request_log[key]
                if t > now - 120  # 2分以上古いエントリは削除
            ]
            # 空になったキーを削除
            if not self.request_log[key]:
                del self.request_log[key]
        
        # グローバルログのクリーンアップ
        for key in list(self.global_log.keys()):
            self.global_log[key] = [
                t for t in self.global_log[key]
                if t > now - 7200  # 2時間以上古いエントリは削除
            ]
            if not self.global_log[key]:
                del self.global_log[key]
        
        self.last_cleanup = now
        
        # ログ出力
        total_ips = len(self.request_log)
        if total_ips > 0:
            print(f"🧹 [RateLimit] Cleanup complete - tracking {total_ips} unique IP:endpoint pairs")

# グローバルインスタンス
rate_limiter = SimpleRateLimiter()
