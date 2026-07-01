# ─── 阶段 1：构建前端 ─────────────────────────────────────────────────────────
FROM node:20-slim AS frontend-builder
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci || npm install
COPY frontend/ ./
# 生产构建，输出到 /build/dist（vite 默认 outDir=dist）
RUN npm run build

# ─── 阶段 2：后端运行时（同时托管前端 dist）─────────────────────────────────────
FROM python:3.11-slim
WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖（精简版：移除未使用的 sentence-transformers/torch 以加速构建）
COPY backend/requirements.deploy.txt ./backend/requirements.deploy.txt
RUN pip install --no-cache-dir -r backend/requirements.deploy.txt

# 应用代码
COPY backend/ ./backend/
COPY agents/ ./agents/
COPY eval/ ./eval/

# 拷入前端构建产物（main.py 会从 ../frontend/dist 托管）
COPY --from=frontend-builder /build/dist ./frontend/dist

# 创空间强制端口 7860
ENV APP_ENV=production
EXPOSE 7860

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "7860"]
