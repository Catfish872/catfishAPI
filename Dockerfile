# 使用官方的 Python 3.11 slim 镜像作为基础
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 将 requirements.txt 复制到容器中
COPY requirements.txt .

# 安装项目依赖
# --no-cache-dir: 不存储缓存，减小镜像大小
# --upgrade pip: 确保使用最新版本的pip
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 将整个 src 目录复制到容器的 /app/src 目录下
COPY ./src ./src

# 暴露端口，告诉Docker容器在运行时监听8000端口
EXPOSE 8000

# 容器启动时运行的命令
# 使用 uvicorn 启动 FastAPI 应用
# --host 0.0.0.0: 监听所有网络接口，这是容器化应用所必需的
# --port 8000: 在容器内部使用8000端口
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]