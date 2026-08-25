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
    """应用全局配置类"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    # ========== 应用基本配置 ==========
    APP_NAME: str = Field(default="校园创新创业项目管理平台", description="应用名称")
    APP_VERSION: str = Field(default="1.0.0", description="应用版本")
    DEBUG: bool = Field(default=True, description="调试模式")
    HOST: str = Field(default="0.0.0.0", description="服务监听地址")
    PORT: int = Field(default=8000, description="服务监听端口")
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        description="允许的CORS域名白名单（生产环境必须精确配置）"
    )

    # ========== 数据库配置 ==========
    DB_HOST: str = Field(default="127.0.0.1", description="MySQL主机地址")
    DB_PORT: int = Field(default=3306, description="MySQL端口")
    DB_USER: str = Field(default="root", description="MySQL用户名")
    DB_PASSWORD: str = Field(
        default=_DEV_DB_PASSWORD,
        description="MySQL密码（生产环境必须从.env或环境变量读取）"
    )
    DB_NAME: str = Field(default="ie_project_db", description="数据库名称")
    DB_CHARSET: str = Field(default="utf8mb4", description="数据库字符集")

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        """构建SQLAlchemy数据库连接URI"""
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            f"?charset={self.DB_CHARSET}"
        )

    # ========== Redis配置 ==========
    REDIS_HOST: str = Field(default="127.0.0.1", description="Redis主机地址")
    REDIS_PORT: int = Field(default=6379, description="Redis端口")
    REDIS_PASSWORD: str = Field(default="", description="Redis密码")
    REDIS_DB: int = Field(default=0, description="Redis数据库编号")

    @property
    def REDIS_URL(self) -> str:
        """构建Redis连接URL"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # ========== JWT配置 ==========
    JWT_SECRET_KEY: str = Field(
        default=_DEV_JWT_KEY,
        description="JWT签名密钥（生产环境必须从.env或环境变量读取，严禁沿用默认值）"
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT签名算法")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=120, description="访问令牌过期时间(分钟)")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, description="刷新令牌过期时间(天)")

    # ========== 文件上传配置 ==========
    UPLOAD_DIR: str = Field(default="static/uploads", description="文件上传目录")
    MAX_UPLOAD_SIZE: int = Field(default=10 * 1024 * 1024, description="最大上传文件大小(10MB)")
    ALLOWED_EXTENSIONS: str = Field(
        default=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.jpg,.jpeg,.png,.zip,.rar",
        description="允许上传的文件扩展名"
    )

    @property
    def ALLOWED_EXTENSIONS_LIST(self) -> List[str]:
        """返回允许的扩展名列表(小写)"""
        return [ext.strip().lower() for ext in self.ALLOWED_EXTENSIONS.split(",") if ext.strip()]

    # ========== 全文检索配置 ==========
    WHOOSH_INDEX_DIR: str = Field(default="static/whoosh_index", description="Whoosh索引目录")

    @model_validator(mode="after")
    def _validate_production_secrets(self):
        """启动时校验：生产环境（DEBUG=False）严禁沿用开发默认值"""
        using_insecure = (
            self.DB_PASSWORD == _DEV_DB_PASSWORD or
            self.JWT_SECRET_KEY == _DEV_JWT_KEY
        )
        if not self.DEBUG and using_insecure:
            raise RuntimeError(
                "[SECURITY ERROR] 生产环境(DEBUG=False)必须通过.env文件配置以下敏感字段：\n"
                "  - DB_PASSWORD  (当前使用的是 DEV_ONLY_ 开发占位值)\n"
                "  - JWT_SECRET_KEY (当前使用的是 DEV_ONLY_ 开发占位值)\n"
                "请复制 .env.example 为 .env 并填写生产环境的安全值。"
            )
        if self.DEBUG and using_insecure:
            warnings.warn(
                "\n[DEV WARNING] 当前使用开发环境默认密钥，仅用于本地调试。\n"
                "部署到任何非本地环境前，请在 .env 文件中设置强密钥：\n"
                "  DB_PASSWORD / JWT_SECRET_KEY",
                stacklevel=2,
            )
        return self


# 全局配置实例
settings = Settings()
