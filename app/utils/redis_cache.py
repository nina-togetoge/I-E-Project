"""
Redis 缓存工具类
支持：通用K-V存取、带差异化过期时间、缓存标记删除/主动更新一致性策略
依赖：redis (pip install redis)
"""
import json
import pickle
import threading
import time
from typing import Any, Optional, Callable, Type, Dict
from functools import wraps

try:
    import redis
except ImportError:  # 容错：未安装时提供空实现
    redis = None

from app.core.config import settings


class RedisClient:
    """
    Redis 单例客户端封装
    - 连接自动管理
    - 支持 string / object / json / 计数器 等常用操作
    - 对缓存未命中/Redis未就绪的情况做了降级，直接返回None，不影响主业务
    """
    _instance: Optional["RedisClient"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "RedisClient":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init_client()
        return cls._instance

    def _init_client(self) -> None:
        self._client = None
        if redis is None:
            print("[WARN] redis 包未安装，缓存功能已降级为本地字典")
            self._local_cache: Dict[str, tuple] = {}  # key -> (value, expire_at_ts)
            return
        try:
            self._client = redis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=False,
                socket_connect_timeout=2,
                socket_timeout=3,
                retry_on_timeout=True,
            )
            # 测试连通性
            self._client.ping()
            print("[OK] Redis 缓存连接成功")
        except Exception as e:
            print(f"[WARN] Redis 连接失败({e})，降级为本地内存缓存")
            self._client = None
            self._local_cache: Dict[str, tuple] = {}

    # ---------- 内部辅助 ----------
    def _is_connected(self) -> bool:
        return self._client is not None

    @staticmethod
    def _serialize(value: Any) -> bytes:
        return pickle.dumps(value)

    @staticmethod
    def _deserialize(data: Optional[bytes]) -> Any:
        if data is None:
            return None
        try:
            return pickle.loads(data)
        except Exception:
            return None

    def _local_get(self, key: str) -> Any:
        item = self._local_cache.get(key)
        if not item:
            return None
        value, expire_at = item
        if expire_at and expire_at < time.time():
            self._local_cache.pop(key, None)
            return None
        return value

    def _local_set(self, key: str, value: Any, seconds: Optional[int]) -> None:
        expire_at = time.time() + seconds if seconds else None
        # 本地缓存简单防无限增长：超过10000条则清理过期项
        if len(self._local_cache) > 10000:
            now = time.time()
            self._local_cache = {k: v for k, v in self._local_cache.items()
                                 if not v[1] or v[1] >= now}
        self._local_cache[key] = (value, expire_at)

    # ---------- 通用接口 ----------
    def get(self, key: str) -> Any:
        if self._is_connected():
            try:
                return self._deserialize(self._client.get(key))
            except Exception:
                return None
        return self._local_get(key)

    def set(self, key: str, value: Any, expire_seconds: Optional[int] = None) -> bool:
        try:
            if self._is_connected():
                data = self._serialize(value)
                if expire_seconds:
                    self._client.setex(key, expire_seconds, data)
                else:
                    self._client.set(key, data)
                return True
            self._local_set(key, value, expire_seconds)
            return True
        except Exception:
            return False

    def delete(self, *keys: str) -> int:
        try:
            if self._is_connected():
                return self._client.delete(*keys) or 0
            for k in keys:
                self._local_cache.pop(k, None)
            return len(keys)
        except Exception:
            return 0

    def delete_pattern(self, pattern: str) -> int:
        """按通配符批量删除（如 cache:project:* ）"""
        try:
            if self._is_connected():
                cnt = 0
                for k in self._client.scan_iter(match=pattern, count=200):
                    self._client.delete(k)
                    cnt += 1
                return cnt
            # 本地缓存按前缀匹配
            to_del = [k for k in self._local_cache.keys()
                      if pattern.replace("*", "") in k]
            for k in to_del:
                self._local_cache.pop(k, None)
            return len(to_del)
        except Exception:
            return 0

    def exists(self, key: str) -> bool:
        if self._is_connected():
            try:
                return bool(self._client.exists(key))
            except Exception:
                return False
        return self._local_get(key) is not None

    def incr(self, key: str, amount: int = 1, expire_seconds: Optional[int] = None) -> int:
        try:
            if self._is_connected():
                v = self._client.incrby(key, amount)
                if expire_seconds and v == amount:  # 第一次设置时附加过期
                    self._client.expire(key, expire_seconds)
                return int(v or 0)
            old = self._local_get(key) or 0
            new = old + amount
            self._local_set(key, new, expire_seconds)
            return new
        except Exception:
            return 0

    # ---------- JSON 便捷接口（方便跨语言读取）----------
    def get_json(self, key: str) -> Any:
        raw = None
        if self._is_connected():
            try:
                raw = self._client.get(key)
                if raw is not None:
                    return json.loads(raw.decode("utf-8"))
            except Exception:
                return None
        return self._local_get(key)

    def set_json(self, key: str, value: Any, expire_seconds: Optional[int] = None) -> bool:
        try:
            data = json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")
            if self._is_connected():
                if expire_seconds:
                    self._client.setex(key, expire_seconds, data)
                else:
                    self._client.set(key, data)
                return True
            self._local_set(key, value, expire_seconds)
            return True
        except Exception:
            return False


# ====================================================================
# 全局实例 + 装饰器：带缓存的函数
# ====================================================================
redis_client = RedisClient()

# 推荐 Key 命名规范： biz:module:entity:id
# 过期时间推荐（秒）：
CACHE_5_MIN = 5 * 60          # 5分钟：频繁变化的热点（如公示名单）
CACHE_30_MIN = 30 * 60        # 30分钟：统计报表
CACHE_1_HOUR = 60 * 60        # 1小时：字典
CACHE_1_DAY = 24 * 60 * 60    # 1天：配置类、历史归档数据


def cached(key_pattern: str, expire_seconds: int = CACHE_30_MIN,
           skip_none: bool = True, invalidate_on_false: bool = False):
    """
    函数结果缓存装饰器
    key_pattern 示例： "cache:stats:overview:{data_scope.user_id}"  或 "cache:dict:{_key}"
    支持：格式化变量来自函数的参数名/关键字参数名
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 1. 构造缓存key
            import inspect
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            ctx = dict(bound.arguments)
            try:
                cache_key = key_pattern.format(**ctx)
            except (KeyError, IndexError):
                cache_key = key_pattern  # 格式化失败则用原串

            # 2. 命中缓存直接返回
            cached_val = redis_client.get(cache_key)
            if cached_val is not None:
                return cached_val

            # 3. 未命中 -> 执行原函数
            result = func(*args, **kwargs)

            # 4. 写入缓存（可配置跳过None/假值）
            should_cache = True
            if skip_none and result is None:
                should_cache = False
            if invalidate_on_false and not result:
                should_cache = False
            if should_cache:
                redis_client.set(cache_key, result, expire_seconds)
            return result
        return wrapper
    return decorator


# ====================================================================
# 常用业务缓存键（便于统一管理）
# ====================================================================
class CacheKeys:
    """业务层推荐使用的缓存Key前缀"""
    # 系统字典（长期）
    DICT_ALL = "sys:dict:all"
    DICT_BY_TYPE = "sys:dict:type:{dict_type}"
    DICT_TTL = CACHE_1_HOUR

    # 学院列表
    COLLEGE_LIST = "sys:college:list"
    COLLEGE_LIST_TTL = CACHE_30_MIN

    # 立项公示名单
    PUBLIC_APPROVED_LIST = "proj:public:approved:{year}:{page}"
    PUBLIC_TTL = CACHE_5_MIN

    # 项目统计概览
    STATS_OVERVIEW = "proj:stats:overview:{scope_id}"
    STATS_TREND = "proj:stats:trend:{start_year}_{end_year}_{scope_id}"
    STATS_TTL = CACHE_30_MIN

    # 用户详情
    USER_DETAIL = "sys:user:detail:{user_id}"
    USER_TTL = CACHE_5_MIN

    # 项目详情
    PROJECT_DETAIL = "proj:detail:{project_id}"
    PROJECT_TTL = CACHE_5_MIN
