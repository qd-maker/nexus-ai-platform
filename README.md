# Nexus AI - AI Agent 服务平台

一个现代化的 AI Agent 服务平台，采用 FastAPI 后端 + Next.js 前端的技术栈。

## 📋 项目概述

Nexus AI 是一个全栈应用，旨在提供强大的 AI Agent 功能，包括：

- 🤖 AI Agent 服务 - 智能代理处理复杂任务
- 🔌 RESTful API - 完整的后端接口
- 💻 现代化前端 - 使用 Next.js 构建的用户界面
- 🔐 API 密钥和权限管理
- 📊 可扩展架构 - 模块化设计便于扩展

## 🏗️ 项目结构

```
nexus-ai/
├── backend/                    # Python FastAPI 后端
│   ├── app/
│   │   ├── api/               # API 路由和端点
│   │   │   ├── endpoints/     # 具体的端点实现
│   │   │   └── router.py      # 路由聚合
│   │   ├── core/              # 核心配置
│   │   │   ├── config.py      # 应用配置
│   │   │   └── security.py    # 安全认证
│   │   ├── services/          # 业务逻辑服务
│   │   │   └── ai_agent.py    # AI Agent 实现
│   │   └── __init__.py
│   ├── main.py                # 应用入口
│   ├── requirements.txt       # Python 依赖
│   └── .env.example           # 环境变量示例
│
├── frontend/                   # Next.js 前端
│   └── (待实现)
│
└── README.md                   # 项目文档
```

## 🚀 快速开始

### 前置要求

- Python 3.9+
- Node.js 18+
- pip 或 conda

### 后端启动

1. 安装依赖
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. 配置环境变量
   ```bash
   cp .env.example .env
   # 编辑 .env 文件，配置必要的环境变量
   ```

3. 启动服务
   ```bash
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```
   服务将在 http://localhost:8000 启动

4. 查看 API 文档
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

### 前端启动

```bash
cd frontend
npm install
npm run dev
```

前端将在 http://localhost:3000 启动

## 📚 API 文档

### 健康检查

```
GET /api/v1/health/
```

响应:
```json
{
  "status": "healthy",
  "message": "Nexus AI 服务正常运行"
}
```

## 🔧 开发指南

### 添加新的 API 端点

1. 在 backend/app/api/endpoints/ 中创建新文件
2. 定义路由和处理函数
3. 在 backend/app/api/router.py 中注册路由

示例：
```python
# backend/app/api/endpoints/tasks.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def list_tasks():
    return {"tasks": []}
```

### 添加业务逻辑服务

在 backend/app/services/ 中创建服务类，处理复杂的业务逻辑和 AI Agent 相关的功能。

## 🔐 安全性

- API 密钥认证
- CORS 跨域配置
- 环境变量管理
- 请求验证

## 📦 依赖管理

### 后端依赖

- FastAPI - 现代化 Web 框架
- Uvicorn - ASGI 服务器
- Pydantic - 数据验证
- python-dotenv - 环境变量管理

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

## 📝 许可证

MIT License

## 👨‍💼 关于项目

这是一个展示现代全栈开发能力的项目，适合作为面试作品集的一部分。

---

最后更新: 2025年12月
