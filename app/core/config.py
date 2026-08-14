"""
核心配置模块
基于pydantic-settings实现配置管理，支持.env环境变量加载
"""
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


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

    # ========== 数据库配置 ==========
    DB_HOST: str = Field(default="127.0.0.1", description="MySQL主机地址")
    DB_PORT: int = Field(default=3306, description="MySQL端口")
    DB_USER: str = Field(default="root", description="MySQL用户名")
    DB_PASSWORD: str = Field(default="2023011630", description="MySQL密码")
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
        default="ie_project_management_secret_key_2024_change_in_production",
        description="JWT签名密钥"
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


# 全局配置实例
settings = Settings()
