"""
Redis 缓存工具类
支持：通用K-V存取、带差异化过期时间、缓存标记删除/主动更新一致性策略
依赖：redis (pip install redis)

调用方：
    app/services 下的查询型服务（统计、字典、学院列表、项目详情等）、
    TokenBlacklist（鉴权中间件校验登出 token）。

关键设计：
    - 单例客户端：进程内只建一个连接池，避免每次请求新建连接；
    - 全链路降级：redis 包缺失或连接失败时自动退化为进程内字典缓存，
      读接口返回 None、写接口返回 False，不把缓存故障扩散成业务 500；
    - 序列化默认 pickle（可存任意 Python 对象），另外提供 JSON 接口
      便于跨语言读取/排查；pickle 只用于本系统自己写入的可信数据；
    - key 统一采用 业务:模块:实体:标识 的层级命名，便于按前缀批量失效；
    - 缓存不可用时不阻塞业务：调用方把 get 的 None 当作未命中，回源查库即可。
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

    线程安全：单例创建用双检锁；redis-py 的连接池本身线程安全，
    本地字典缓存只在「Redis 不可用」时使用，读写都在同一进程内。
    注意：多进程部署时各进程的本地缓存互相独立，仅作临时兜底，
    不能把它当作一致性缓存使用（进程间会读到不同的旧值）。
    """
    _instance: Optional["RedisClient"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "RedisClient":
        """双检锁实现懒加载单例，避免并发初始化时重复建立连接。"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init_client()
        return cls._instance

    def _init_client(self) -> None:
        """初始化连接；任何失败都降级为本地字典缓存，不向外抛异常。

        :side effect: 成功时设置 self._client；失败或未安装 redis 时
                      设置 self._local_cache（进程内 dict，带过期时间戳）。
        连接参数取舍：连接超时 2s、读写超时 3s，宁可快速失败回源数据库，
        也不让请求线程长时间阻塞在缓存上。
        """
        self._client = None
        if redis is None:
            print("[WARN] redis 包未安装，缓存功能已降级为本地字典")
            self._local_cache: Dict[str, tuple] = {}  # key -> (value, expire_at_ts)
            return
        try:
            self._client = redis.Redis.from_url(
                settings.REDIS_URL,
                # decode_responses=False：保持 bytes，pickle 才能正确反序列化；
                # JSON 接口会自行 decode("utf-8")。
                decode_responses=False,
                socket_connect_timeout=2,
                socket_timeout=3,
                retry_on_timeout=True,
            )
            # 测试连通性
            # 启动阶段就 ping 一次，把「配置错误/网络不通」提前暴露并降级，
            # 而不是等第一个业务请求才超时。
            self._client.ping()
            print("[OK] Redis 缓存连接成功")
        except Exception as e:
            # 连接失败同样不抛出：缓存是加速手段，不能成为启动失败的因由。
            print(f"[WARN] Redis 连接失败({e})，降级为本地内存缓存")
            self._client = None
            self._local_cache: Dict[str, tuple] = {}

    # ---------- 内部辅助 ----------
    def _is_connected(self) -> bool:
        """当前是否使用真实 Redis；False 表示走本地字典兜底。"""
        return self._client is not None

    @staticmethod
    def _serialize(value: Any) -> bytes:
        """默认序列化：pickle，可保存 dict/ORM 结果/Decimal 等任意对象。

        安全性：pickle 反序列化可执行任意代码，因此本缓存只能写入系统自身
        产生的可信数据；不要把用户上传内容或外部接口原文经此接口缓存。
        可读性差是代价，需要排查时用 set_json 写、redis-cli 直接看。
        """
        return pickle.dumps(value)

    @staticmethod
    def _deserialize(data: Optional[bytes]) -> Any:
        """反序列化；数据损坏或版本不兼容时返回 None，视为缓存未命中。

        :param data: Redis 返回的原始 bytes，None 表示 key 不存在
        """
        if data is None:
            return None
        try:
            return pickle.loads(data)
        except Exception:
            # 反序列化失败不能把异常抛给业务；上层会回源查库并重新写入。
            return None

    def _local_get(self, key: str) -> Any:
        """本地字典读取：命中但已过期的条目顺手删除，避免占内存。"""
        item = self._local_cache.get(key)
        if not item:
            return None
        value, expire_at = item
        if expire_at and expire_at < time.time():
            self._local_cache.pop(key, None)
            return None
        return value

    def _local_set(self, key: str, value: Any, seconds: Optional[int]) -> None:
        """本地字典写入，expire_at 为绝对时间戳；seconds 为空表示永不过期。

        :side effect: 条目数超过 10000 时先清理已过期项（简单防无限增长）；
                      这不是 LRU，未过期的条目仍会保留，因此本地缓存只适合
                      短 TTL 的热点数据，不能承载大对象长期驻留。
        """
        expire_at = time.time() + seconds if seconds else None
        # 本地缓存简单防无限增长：超过10000条则清理过期项
        if len(self._local_cache) > 10000:
            now = time.time()
            self._local_cache = {k: v for k, v in self._local_cache.items()
                                 if not v[1] or v[1] >= now}
        self._local_cache[key] = (value, expire_at)

    # ---------- 通用接口 ----------
    def get(self, key: str) -> Any:
        """读取缓存。

        :return: 命中返回值；未命中、Redis 异常或反序列化失败均返回 None
        :side effect: 只读。调用方必须把 None 当作「未命中」处理（回源查库），
                      不能据此判断数据不存在，否则会误伤空值场景。
        """
        if self._is_connected():
            try:
                return self._deserialize(self._client.get(key))
            except Exception:
                # 读失败静默降级：本次请求回源，不影响写库与响应。
                return None
        return self._local_get(key)

    def set(self, key: str, value: Any, expire_seconds: Optional[int] = None) -> bool:
        """写入缓存（pickle 序列化）。

        :param expire_seconds: TTL 秒数；为空表示不过期（仅建议用于黑名单等
                               需要显式清理的数据，其余业务必须带 TTL）
        :return: True 写入成功；False 表示缓存不可用或写入异常
        :side effect: 覆盖同 key 旧值。写失败不抛异常，业务照常继续。
        """
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
        """删除一个或多个 key。

        :return: 删除的 key 数量；缓存不可用/异常时返回 0
        :side effect: 主动失效用。更新数据库后应立即删除相关 key，
                      否则旧缓存会在 TTL 内继续被读到（最终一致）。
        """
        try:
            if self._is_connected():
                return self._client.delete(*keys) or 0
            for k in keys:
                self._local_cache.pop(k, None)
            return len(keys)
        except Exception:
            return 0

    def delete_pattern(self, pattern: str) -> int:
        """按通配符批量删除（如 cache:project:* ）

        :return: 删除数量；异常时返回 0
        :side effect: 使用 scan_iter 而非 keys：keys 在大库上会阻塞 Redis，
                      scan 分批遍历（count=200）对线上更友好。
                      本地缓存降级时只做简单的子串匹配，语义弱于通配符。
        """
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
        """判断 key 是否存在（黑名单校验主要用这个）。

        :return: 存在 True；缓存不可用时本地字典仍可判断，读异常返回 False。
        :side effect: 只读。异常返回 False 意味着「不在黑名单」，
                      属于故障时的放行策略，需要在安全与可用性之间权衡。
        """
        if self._is_connected():
            try:
                return bool(self._client.exists(key))
            except Exception:
                return False
        return self._local_get(key) is not None

    def incr(self, key: str, amount: int = 1, expire_seconds: Optional[int] = None) -> int:
        """原子自增（计数器：限流、访问量、失败次数）。

        :param amount: 步长，可为负
        :param expire_seconds: 仅在「第一次创建」时附加 TTL，
                               避免每次自增都把过期时间往后推、导致永不过期
        :return: 自增后的值；异常时返回 0
        :side effect: Redis 的 incrby 是单线程原子操作，多实例并发安全；
                      本地兜底模式的「读-改-写」不是原子的，只作降级近似。
        """
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
        """以 JSON 方式读取（写入方必须用 set_json，两者不能混用）。

        混用 pickle 与 JSON 会导致反序列化失败：JSON 接口读 pickle 数据会
        在 json.loads 处抛异常并返回 None，pickle 接口读 JSON 同理。
        """
        raw = None
        if self._is_connected():
            try:
                raw = self._client.get(key)
                if raw is not None:
                    return json.loads(raw.decode("utf-8"))
            except Exception:
                return None
        # 降级模式下 set_json 直接存 Python 对象，因此这里无需再解析。
        return self._local_get(key)

    def set_json(self, key: str, value: Any, expire_seconds: Optional[int] = None) -> bool:
        """以 JSON 方式写入，便于运维用 redis-cli 直接查看内容。

        :side effect: default=str 让 Decimal/datetime 等不可 JSON 化的值
                      退化为字符串，避免序列化报错；这也意味着读回后类型
                      会变成 str，业务若需要精确类型请改用 set/get（pickle）。
        """
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
# 例如 proj:detail:123、sys:college:list；
# 统一前缀便于 delete_pattern("proj:detail:*") 按业务批量失效。
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

    :param key_pattern: 含 {参数名} 占位符的 key 模板；支持属性访问（data_scope.user_id）
    :param expire_seconds: TTL，默认 30 分钟；按数据变化频率选择，见上方常量
    :param skip_none: 结果为 None 时不写缓存。可避免把「暂时查不到」固化，
                      代价是空结果会反复回源（缓存穿透），恶意查询需另加空值缓存/限流
    :param invalidate_on_false: 结果为假值（空列表/0/False）时不写缓存，
                                适用于「空集也要实时反映」的列表页
    :return: 装饰后的函数，签名通过 functools.wraps 保持

    :side effect: 命中时直接返回缓存中的对象（可能是同一个可变对象引用），
                  调用方不应修改返回值，否则会污染后续命中的调用者。
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 1. 构造缓存key
            # 用 inspect.signature 把位置参数与关键字参数统一绑定成名称，
            # 这样 key_pattern 只依赖参数名，不受调用方式（位置/关键字）影响。
            import inspect
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            # 补上默认值，避免同一调用因省略参数产生不同 key
            bound.apply_defaults()
            ctx = dict(bound.arguments)
            try:
                cache_key = key_pattern.format(**ctx)
            except (KeyError, IndexError):
                # 模板占位符与实际参数不匹配时退化为固定 key，
                # 宁可缓存粒度变粗，也不要让装饰器把业务调用打断。
                cache_key = key_pattern  # 格式化失败则用原串

            # 2. 命中缓存直接返回
            # 缓存故障时 get 返回 None，等价于未命中，继续回源，不影响正确性。
            cached_val = redis_client.get(cache_key)
            if cached_val is not None:
                return cached_val

            # 3. 未命中 -> 执行原函数
            result = func(*args, **kwargs)

            # 4. 写入缓存（可配置跳过None/假值）
            # 写失败只返回 False，不抛异常，保证缓存问题不阻断业务。
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
    """业务层推荐使用的缓存Key前缀。

    命名规则：业务:模块:实体[:维度...]，全部小写英文；
    带 {占位符} 的常量需由调用方 format 后再使用。
    TTL 与数据变化频率匹配：字典/学院几乎不变用长 TTL，
    公示名单/项目详情变化快用 5 分钟，并在写操作后主动 delete 对应 key。
    """
    # 系统字典（长期）
    # 字典变更频率极低，用 1 小时 TTL；管理员修改字典后应主动删除 DICT_ALL。
    DICT_ALL = "sys:dict:all"
    DICT_BY_TYPE = "sys:dict:type:{dict_type}"
    DICT_TTL = CACHE_1_HOUR

    # 学院列表
    # 学院增删改不频繁，30 分钟足够；列表页与下拉框共用同一个 key。
    COLLEGE_LIST = "sys:college:list"
    COLLEGE_LIST_TTL = CACHE_30_MIN

    # 立项公示名单
    # 公示期数据对外可见且要求较新，5 分钟；key 带年份与页码，
    # 因为公示页通常分页展示，不同页应各自缓存。
    PUBLIC_APPROVED_LIST = "proj:public:approved:{year}:{page}"
    PUBLIC_TTL = CACHE_5_MIN

    # 项目统计概览
    # scope_id 用于区分数据权限范围（超管/学院/个人），避免不同角色读到同一份统计。
    STATS_OVERVIEW = "proj:stats:overview:{scope_id}"
    STATS_TREND = "proj:stats:trend:{start_year}_{end_year}_{scope_id}"
    STATS_TTL = CACHE_30_MIN

    # 用户详情
    # 5 分钟，用户修改资料后由 user_service 主动删除 USER_DETAIL。
    USER_DETAIL = "sys:user:detail:{user_id}"
    USER_TTL = CACHE_5_MIN

    # 项目详情
    # 项目状态流转频繁（审核/中期/结题都会改），因此只缓存 5 分钟，
    # 且所有写操作后都应按 project_id 删除，不能只依赖 TTL 过期。
    PROJECT_DETAIL = "proj:detail:{project_id}"
    PROJECT_TTL = CACHE_5_MIN

    # JWT Token 黑名单
    # 黑名单条目不需要固定 TTL：写入时按 token 剩余有效期设置，
    # token 自然过期后黑名单条目也随之消失，避免黑名单表无限增长。
    BLACKLIST_ACCESS = "auth:blacklist:access:{jti}"
    BLACKLIST_REFRESH = "auth:blacklist:refresh:{jti}"


class TokenBlacklist:
    """
    JWT Token 黑名单（用户登出 / 强制下线使用）
    - 存入Redis时 TTL 自动设为 Token 剩余过期时间
    - Redis不可用时降级为本地内存缓存

    降级风险：本地缓存仅在单进程有效，多实例部署或进程重启后黑名单会丢失，
    登出 token 可能重新可用；因此生产环境应保证 Redis 可用，
    本地兜底只用于开发/演示环境。
    """
    @staticmethod
    def _key(token_type: str, jti: str) -> str:
        """按 token 类型拼接黑名单 key；refresh 与 access 必须分开存储，
        否则同 jti 的两种 token 会互相覆盖（实际 jti 不同，但语义上仍应隔离）。
        """
        if token_type == "refresh":
            return CacheKeys.BLACKLIST_REFRESH.format(jti=jti)
        return CacheKeys.BLACKLIST_ACCESS.format(jti=jti)

    @classmethod
    def add(cls, token_type: str, jti: str, ttl_seconds: int) -> None:
        """将指定token加入黑名单（过期时间=token剩余有效期）

        :param ttl_seconds: token 剩余秒数；<=0 表示已过期，无需入黑名单
        :side effect: 写缓存失败不会报错（redis_client.set 返回 False 被忽略），
                      属于「尽力吊销」；对安全性要求更高的场景应结合数据库兜底。
        """
        if not jti or ttl_seconds <= 0:
            return
        key = cls._key(token_type, jti)
        # 值写 1 表示已吊销，TTL 由 Redis 自动清理，过期后该黑名单条目无意义
        redis_client.set(key, 1, expire_seconds=ttl_seconds)

    @classmethod
    def is_blacklisted(cls, token_type: str, jti: str) -> bool:
        """检查 token 是否已被加入黑名单。

        :return: True 表示已吊销；缓存异常时 exists 返回 False（放行）
        :side effect: 只读。鉴权中间件每次请求都会调用，应保持 O(1)。
        """
        if not jti:
            return False
        key = cls._key(token_type, jti)
        return redis_client.exists(key)
