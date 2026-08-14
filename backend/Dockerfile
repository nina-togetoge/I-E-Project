# ============================================================
# 校园创新创业项目管理平台 - Dockerfile
# 基于 Python 3.10-slim 构建 FastAPI 应用镜像
# ============================================================

FROM python:3.10-slim

# 设置时区为东八区（避免日志时间与业务时间不一致）
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 设置工作目录
WORKDIR /app

# 设置环境变量：禁止Python生成.pyc文件 + 实时日志输出
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 安装系统依赖（gcc用于编译某些Python包如bcrypt/cryptography）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    default-libmysqlclient-dev \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖文件，利用Docker缓存层加速构建
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目所有源码
COPY . /app/

# 创建必要的目录
RUN mkdir -p /app/static/uploads /app/static/whoosh_index

# 声明端口
EXPOSE 8000

# 声明数据卷（附件上传 + 全文索引）
VOLUME ["/app/static/uploads", "/app/static/whoosh_index"]

# 健康检查：每30秒检查一次FastAPI是否正常响应
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# 启动命令：使用uvicorn运行，绑定0.0.0.0:8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
