#!/usr/bin/env bash
# 医语桥 - 一键启动脚本 (bash)
# 用法：bash start.sh

set -e

echo "========================================"
echo "  医语桥 - 一键启动脚本"
echo "========================================"
echo ""

# ─── 检查 Python ─────────────────────────────────────────────────────────────
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未检测到 Python，请先安装 Python 3.10+"
    exit 1
fi
echo "[OK] Python: $(python3 --version)"

# ─── 检查 Node.js ────────────────────────────────────────────────────────────
if ! command -v node &> /dev/null; then
    echo "[错误] 未检测到 Node.js，请先安装 Node.js 18+"
    exit 1
fi
echo "[OK] Node.js: $(node --version)"

# ─── 检查 .env 文件 ──────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    echo "[提示] .env 文件不存在，正在从 .env.example 创建..."
    cp .env.example .env
    echo "[提示] 请编辑 .env 文件，填入你的硅基流动 API Key"
    echo ""
    exit 1
fi
echo "[OK] .env 文件已就绪"

# ─── 后端依赖安装 ────────────────────────────────────────────────────────────
echo ""
echo "[1/4] 安装后端依赖..."
if [ ! -d "backend/venv" ]; then
    python3 -m venv backend/venv
fi
source backend/venv/bin/activate
pip install -r backend/requirements.txt --quiet
echo "[OK] 后端依赖安装完成"

# ─── 前端依赖安装 ────────────────────────────────────────────────────────────
echo ""
echo "[2/4] 安装前端依赖..."
if [ ! -d "frontend/node_modules" ]; then
    cd frontend && npm install && cd ..
fi
echo "[OK] 前端依赖安装完成"

# ─── 启动后端服务 ────────────────────────────────────────────────────────────
echo ""
echo "[3/4] 启动后端服务 (端口 8000)..."
source backend/venv/bin/activate
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "[OK] 后端服务已启动 (PID: $BACKEND_PID)"

# ─── 启动前端服务 ────────────────────────────────────────────────────────────
echo ""
echo "[4/4] 启动前端服务 (端口 3000)..."
cd frontend && npm run dev &
FRONTEND_PID=$!
cd ..
echo "[OK] 前端服务已启动 (PID: $FRONTEND_PID)"

# ─── 完成 ────────────────────────────────────────────────────────────────────
echo ""
echo "========================================"
echo "  启动完成！"
echo "========================================"
echo ""
echo "  前端页面: http://localhost:3000"
echo "  后端 API:  http://localhost:8000"
echo "  API 文档: http://localhost:8000/docs"
echo ""
echo "  按 Ctrl+C 停止所有服务"

# 等待中断信号
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
