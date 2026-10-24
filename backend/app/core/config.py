# ====================================================================
# 核心配置模块（app/core/config.py）
# --------------------------------------------------------------------
# 解决什么问题：
#   把散落在代码中的数据库、JWT、上传、评审、AI 等参数集中到一个强类型
#   配置对象中，避免各模块各自读取 os.environ，导致默认值不一致或漏配。
# 被谁使用：
#   database.session（连接串）、core.security（JWT 密钥/有效期）、
#   middleware（CORS 白名单）、services（评审及格线/上传限制）、
#   main.py（应用元信息/监听地址）、seed_demo_data.py（上传目录）。
# 关键约束：
#   1. 所有配置项都带默认值，保证本地“零配置可启动”；
#   2. 但敏感项默认值是显式标记的 DEV_ONLY 占位符，生产（DEBUG=False）
#      会直接拒绝启动，避免把开发密钥带上线；
#   3. 配置只在进程启动时实例化一次（settings 为模块级单例），
#      运行期间修改环境变量不会生效，需重启。
# ====================================================================
"""
核心配置模块
基于pydantic-settings实现配置管理，支持.env环境变量加载
"""
import os
import warnings
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator


# 开发环境仅用于本地调试的默认值
# 生产环境必须通过 .env 或环境变量覆盖，否则启动报错
_DEV_DB_PASSWORD = "DEV_ONLY_change_in_env"
_DEV_JWT_KEY = "DEV_ONLY_change_this_secret_in_production_env"


class Settings(BaseSettings):
    """
    应用全局配置类。

    继承 pydantic-settings 的 BaseSettings，字段值按以下优先级解析：
    显式传入参数 > 环境变量 > .env 文件 > Field 默认值。
    实例化时会触发字段类型转换与 _validate_production_secrets 校验，
    因此配置写错（如 PORT 非数字）会在启动阶段直接报错，而不是运行中才暴露。
    """

    # .env 读取规则：固定读当前工作目录下的 .env（后端目录），UTF-8 编码；
    # case_sensitive=True 表示环境变量名必须与字段名大小写完全一致；
    # extra="ignore" 允许 .env 中存在与配置类无关的键（如前端变量），不报错。
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    # ========== 应用基本配置 ==========
    # 应用名称会展示在 Swagger 文档标题、启动日志中
    APP_NAME: str = Field(default="校园创新创业项目管理平台", description="应用名称")
    # 学校名称用于公文类导出（申报书、评审表）页眉/落款
    SCHOOL_NAME: str = Field(default="哈尔滨信息工程学院", description="学校名称")
    # 语义化版本号，前端“关于”页与 /docs 版本标识均取自此处
    APP_VERSION: str = Field(default="1.0.0", description="应用版本")
    # 调试模式开关：True 时输出 SQL、异常堆栈、自动建表；
    # 生产环境必须设为 False，否则会泄露敏感堆栈并触发密钥校验逻辑的反向分支
    DEBUG: bool = Field(default=True, description="调试模式")
    # 0.0.0.0 表示监听所有网卡，便于 Docker/内网访问；仅本机调试可改 127.0.0.1
    HOST: str = Field(default="0.0.0.0", description="服务监听地址")
    # 监听端口，默认 8000（与前端 Vite 开发代理的 target 保持一致）
    PORT: int = Field(default=8000, description="服务监听端口")
    # 跨域白名单：必须是具体协议+域名+端口，禁止生产使用 "*"（与 allow_credentials 冲突且不安全）；
    # 默认仅放行 Vite 开发服务器，部署时通过 CORS_ORIGINS 环境变量改为真实前端域名
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        description="允许的CORS域名白名单（生产环境必须精确配置）"
    )

    # ========== 数据库配置 ==========
    # MySQL 主机：本地开发为 127.0.0.1，容器编排中通常是服务名（如 mysql）
    DB_HOST: str = Field(default="127.0.0.1", description="MySQL主机地址")
    # MySQL 端口：3306 为默认端口；容器映射时按实际宿主机端口填写
    DB_PORT: int = Field(default=3306, description="MySQL端口")
    # 数据库账号：生产环境应使用仅授权本库的最小权限账号，避免使用 root
    DB_USER: str = Field(default="root", description="MySQL用户名")
    # 数据库密码：默认值仅为开发占位符，生产环境由 _validate_production_secrets 强制要求覆盖
    DB_PASSWORD: str = Field(
        default=_DEV_DB_PASSWORD,
        description="MySQL密码（生产环境必须从.env或环境变量读取）"
    )
    # 库名：需与 schema.sql 中 CREATE DATABASE 的名称一致
    DB_NAME: str = Field(default="ie_project_db", description="数据库名称")
    # 字符集：utf8mb4 才能完整存储 emoji 与生僻字（utf8 只有 3 字节）
    DB_CHARSET: str = Field(default="utf8mb4", description="数据库字符集")

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        """
        构建 SQLAlchemy 数据库连接字符串。

        返回：
            mysql+pymysql://用户:密码@主机:端口/库名?charset=字符集
        注意：
            该串包含明文密码，仅允许在 engine 内部使用，禁止打印到日志或返回给前端；
            密码中若含 @、/、: 等特殊字符需做 URL 编码，当前按原样拼接。
        """
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            f"?charset={self.DB_CHARSET}"
        )

    # ========== Redis配置 ==========
    # Redis 用于 Token 黑名单与缓存；未部署时 utils.redis_cache 会自动降级为内存缓存
    REDIS_HOST: str = Field(default="127.0.0.1", description="Redis主机地址")
    REDIS_PORT: int = Field(default=6379, description="Redis端口")
    # 无密码时留空；生产环境务必设置密码并限制内网访问
    REDIS_PASSWORD: str = Field(default="", description="Redis密码")
    # 逻辑库编号 0-15：可用不同编号隔离开发/测试环境，避免键互相覆盖
    REDIS_DB: int = Field(default=0, description="Redis数据库编号")

    @property
    def REDIS_URL(self) -> str:
        """
        构建 Redis 连接 URL。

        返回：
            redis://[:密码@]主机:端口/库编号
        说明：
            密码为空时省略认证段，避免出现 redis://:@host 这种非法格式。
        """
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # ========== JWT配置 ==========
    # 签名密钥：泄露即可伪造任意用户令牌，生产环境必须随机生成长字符串并妥善保管；
    # 默认值被 _validate_production_secrets 视为“不安全”，DEBUG=False 时拒绝启动
    JWT_SECRET_KEY: str = Field(
        default=_DEV_JWT_KEY,
        description="JWT签名密钥（生产环境必须从.env或环境变量读取，严禁沿用默认值）"
    )
    # 对称签名算法：HS256 依赖同一密钥签发/校验，适合单体后端；如改 RS256 需同步调整密钥格式
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT签名算法")
    # 访问令牌有效期：120 分钟。过短会导致频繁刷新，过长则会放大令牌泄露风险
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=120, description="访问令牌过期时间(分钟)")
    # 刷新令牌有效期：7 天。仅在访问令牌过期后换取新令牌，不能直接访问业务接口
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, description="刷新令牌过期时间(天)")

    # ========== 评审配置 ==========
    # 专家评分及格线（百分制）：低于该分数的评审结论不得判定为“通过”，
    # 与 review_service 的立项判定逻辑绑定，修改前需同步业务规则文档
    EXPERT_PASS_SCORE: int = Field(default=60, description="专家评审及格线(百分制)，低于该分数不可判定为通过")
    # 单项目最少专家数：用于判断专家评审是否“收齐意见”，未达到时不允许进入下一状态
    EXPERT_MIN_COUNT: int = Field(default=2, description="单个项目最少分配的评审专家人数")

    # ========== 文件上传配置 ==========
    # 上传根目录：相对路径以进程工作目录（backend）为基准；
    # Docker 部署时通过环境变量指向挂载卷，容器重建后文件仍不丢失
    UPLOAD_DIR: str = Field(default="static/uploads", description="文件上传目录")
    # 单文件大小上限 200MB：需与应用层、Nginx client_max_body_size 同时放开，否则请求在网关层被截断
    MAX_UPLOAD_SIZE: int = Field(default=200 * 1024 * 1024, description="最大上传文件大小(200MB)")
    # 扩展名白名单（逗号分隔）：以扩展名做第一道过滤，真实内容校验仍需在服务层完成
    ALLOWED_EXTENSIONS: str = Field(
        default=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.jpg,.jpeg,.png,.zip,.rar",
        description="允许上传的文件扩展名"
    )

    @property
    def ALLOWED_EXTENSIONS_LIST(self) -> List[str]:
        """
        把逗号分隔的扩展名配置解析为小写列表。

        返回：
            去除空白并统一小写的扩展名列表，便于与文件后缀直接比较。
        """
        return [ext.strip().lower() for ext in self.ALLOWED_EXTENSIONS.split(",") if ext.strip()]

    # ========== 火山引擎 Ark (豆包) AI 配置 ==========
    # API Key：留空时 AI 助手接口会降级提示“未配置”，不影响其他业务；
    # 生产环境通过环境变量注入，禁止提交到 Git
    ARK_API_KEY: str = Field(default="", description="火山引擎 Ark API Key")
    # 基础地址：固定为火山引擎方舟 v3 接口；如使用代理网关可覆盖
    ARK_BASE_URL: str = Field(
        default="https://ark.cn-beijing.volces.com/api/v3",
        description="火山引擎 Ark API 基础地址"
    )
    # 模型/推理接入点 ID：更换模型只需改此配置，无需改代码
    ARK_MODEL_ID: str = Field(
        default="doubao-seed-2-0-lite-260428",
        description="豆包模型 ID (Endpoint ID)"
    )

    @model_validator(mode="after")
    def _validate_production_secrets(self):
        """
        启动时校验敏感配置是否仍为开发占位值。

        返回：
            self（Pydantic v2 的 after 校验器必须返回模型自身）。
        异常：
            RuntimeError：DEBUG=False 且 DB_PASSWORD/JWT_SECRET_KEY 为默认占位值时抛出，
            阻止生产环境带着公开密钥启动。
        副作用：
            DEBUG=True 时仅发出告警，方便本地开发零配置运行。
        """
        # 任一敏感项仍等于开发占位值，即视为不安全配置
        using_insecure = (
            self.DB_PASSWORD == _DEV_DB_PASSWORD or
            self.JWT_SECRET_KEY == _DEV_JWT_KEY
        )
        # 生产环境：直接拒绝启动，把安全问题暴露在部署阶段而不是运行阶段
        if not self.DEBUG and using_insecure:
            raise RuntimeError(
                "[SECURITY ERROR] 生产环境(DEBUG=False)必须通过.env文件配置以下敏感字段：\n"
                "  - DB_PASSWORD  (当前使用的是 DEV_ONLY_ 开发占位值)\n"
                "  - JWT_SECRET_KEY (当前使用的是 DEV_ONLY_ 开发占位值)\n"
                "请复制 .env.example 为 .env 并填写生产环境的安全值。"
            )
        # 开发环境：仅告警不阻断，保证新同学 clone 后能直接跑起来
        if self.DEBUG and using_insecure:
            warnings.warn(
                "\n[DEV WARNING] 当前使用开发环境默认密钥，仅用于本地调试。\n"
                "部署到任何非本地环境前，请在 .env 文件中设置强密钥：\n"
                "  DB_PASSWORD / JWT_SECRET_KEY",
                stacklevel=2,
            )
        return self


# 全局配置实例：模块导入时即完成 .env 读取与校验，
# 其他模块统一 from app.core.config import settings 复用同一份配置
settings = Settings()
