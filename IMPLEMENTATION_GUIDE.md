# 多用户数据隔离实现指南

## 快速开始（5个步骤）

### 步骤 1️⃣：修改数据库表结构（5分钟）

在 Supabase 控制台执行以下 SQL：

```sql
-- 1. 添加用户隔离字段
ALTER TABLE nexus_workflows 
ADD COLUMN user_id UUID NOT NULL DEFAULT auth.uid();

ALTER TABLE nexus_workflows 
ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE;

ALTER TABLE nexus_workflows 
ADD COLUMN deleted_at TIMESTAMP;

-- 2. 创建索引
CREATE INDEX idx_nexus_workflows_user_id 
ON nexus_workflows(user_id);

CREATE INDEX idx_nexus_workflows_user_created 
ON nexus_workflows(user_id, created_at DESC);

CREATE INDEX idx_nexus_workflows_deleted 
ON nexus_workflows(user_id, is_deleted);

-- 3. 启用 RLS
ALTER TABLE nexus_workflows ENABLE ROW LEVEL SECURITY;

-- 4. 创建 RLS 策略
CREATE POLICY "Users can view their own workflows"
  ON nexus_workflows
  FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own workflows"
  ON nexus_workflows
  FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own workflows"
  ON nexus_workflows
  FOR UPDATE
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete their own workflows"
  ON nexus_workflows
  FOR DELETE
  USING (auth.uid() = user_id);
```

---

### 步骤 2️⃣：后端改造（15分钟）

#### 2.1 创建认证中间件

**文件：`backend/app/middleware/__init__.py`**

```python
# 空文件，用于标记这是一个包
```

**文件：`backend/app/middleware/auth.py`**

```python
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthCredentials
import jwt
import os
from typing import Dict

class JWTHandler:
    """JWT Token 处理器"""
    
    def __init__(self):
        self.secret = os.environ.get("JWT_SECRET", "dev-secret-key")
        self.algorithm = "HS256"
    
    def verify_token(self, credentials: HTTPAuthCredentials) -> Dict[str, str]:
        """
        验证 JWT Token 并返回 user_id
        
        Args:
            credentials: HTTPAuthCredentials 对象
            
        Returns:
            包含 user_id 的字典
            
        Raises:
            HTTPException: Token 无效时抛出 401 异常
        """
        try:
            payload = jwt.decode(
                credentials.credentials,
                self.secret,
                algorithms=[self.algorithm]
            )
            user_id: str = payload.get("sub")
            if user_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token: missing user_id"
                )
            return {"user_id": user_id}
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired"
            )
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}"
            )

# 全局实例
jwt_handler = JWTHandler()
```

#### 2.2 修改 `orchestrator.py`

在 `run_workflow` 方法中添加 `user_id` 参数：

```python
# 在 run_workflow 方法中找到这一行：
async def run_workflow(self, topic: str) -> WorkflowResponse:

# 改为：
async def run_workflow(self, topic: str, user_id: str) -> WorkflowResponse:

# 然后在保存到 Supabase 的地方修改：
if self.supabase is not None:
    try:
        self.supabase.table("nexus_workflows").insert({
            "user_id": user_id,  # ⭐️ 添加这一行
            "topic": topic,
            "result": response.model_dump(),
            "is_deleted": False
        }).execute()
    except Exception as e:
        print(f"[WARN] Supabase 插入失败：{e}")
```

在 `get_workflow_history` 方法中添加用户过滤：

```python
# 修改这个方法：
def get_workflow_history(self, limit: int = 10):
    """获取最近的 10 条任务记录"""
    try:
        response = self.supabase.table("nexus_workflows")\
            .select("*")\
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()
        return response.data
    except Exception as e:
        print(f"查询失败: {e}")
        return []

# 改为：
def get_workflow_history(self, user_id: str, limit: int = 10):
    """获取特定用户的历史记录"""
    try:
        response = self.supabase.table("nexus_workflows")\
            .select("*")\
            .eq("user_id", user_id)\  # ⭐️ 添加这一行
            .eq("is_deleted", False)\  # ⭐️ 添加这一行
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()
        return response.data
    except Exception as e:
        print(f"查询失败: {e}")
        return []
```

添加删除和恢复方法：

```python
def delete_workflow(self, workflow_id: str, user_id: str) -> bool:
    """
    软删除工作流记录
    
    Args:
        workflow_id: 工作流 ID
        user_id: 用户 ID（用于权限验证）
    
    Returns:
        是否删除成功
    """
    try:
        # 验证该记录属于该用户
        record = self.supabase.table("nexus_workflows")\
            .select("id")\
            .eq("id", workflow_id)\
            .eq("user_id", user_id)\
            .single()\
            .execute()
        
        if not record.data:
            return False
        
        # 执行软删除
        self.supabase.table("nexus_workflows")\
            .update({
                "is_deleted": True,
                "deleted_at": "now()"
            })\
            .eq("id", workflow_id)\
            .eq("user_id", user_id)\
            .execute()
        
        return True
    except Exception as e:
        print(f"删除失败: {e}")
        return False

def restore_workflow(self, workflow_id: str, user_id: str) -> bool:
    """
    恢复已删除的工作流记录
    
    Args:
        workflow_id: 工作流 ID
        user_id: 用户 ID
    
    Returns:
        是否恢复成功
    """
    try:
        self.supabase.table("nexus_workflows")\
            .update({
                "is_deleted": False,
                "deleted_at": None
            })\
            .eq("id", workflow_id)\
            .eq("user_id", user_id)\
            .execute()
        
        return True
    except Exception as e:
        print(f"恢复失败: {e}")
        return False
```

#### 2.3 修改 `main.py`

```python
# 在文件顶部添加导入
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthCredentials
from app.middleware.auth import jwt_handler

# 初始化 security
security = HTTPBearer()

# 创建依赖注入函数
def get_current_user(credentials: HTTPAuthCredentials = Depends(security)) -> str:
    """
    从 Authorization Header 中提取并验证 user_id
    
    使用方式：
    @app.get("/api/some-endpoint")
    async def some_endpoint(user_id: str = Depends(get_current_user)):
        # user_id 会自动注入
        pass
    """
    result = jwt_handler.verify_token(credentials)
    return result["user_id"]

# 修改 create_workflow 端点
@app.post("/api/workflow", response_model=WorkflowResponse)
async def create_workflow(
    request: WorkflowRequest,
    user_id: str = Depends(get_current_user)  # ⭐️ 自动注入 user_id
):
    """创建新的工作流"""
    response = await orchestrator.run_workflow(
        topic=request.topic,
        user_id=user_id  # ⭐️ 传递 user_id
    )
    return response

# 修改 get_history 端点
@app.get("/api/history")
async def get_history(user_id: str = Depends(get_current_user)):
    """获取当前用户的历史记录"""
    return orchestrator.get_workflow_history(user_id=user_id)

# 添加删除端点
@app.delete("/api/workflow/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    user_id: str = Depends(get_current_user)
):
    """删除工作流记录（软删除）"""
    success = orchestrator.delete_workflow(workflow_id, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found or you don't have permission"
        )
    return {"message": "Workflow deleted successfully"}

# 添加恢复端点
@app.post("/api/workflow/{workflow_id}/restore")
async def restore_workflow(
    workflow_id: str,
    user_id: str = Depends(get_current_user)
):
    """恢复已删除的工作流记录"""
    success = orchestrator.restore_workflow(workflow_id, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )
    return {"message": "Workflow restored successfully"}
```

---

### 步骤 3️⃣：前端改造（15分钟）

#### 3.1 创建认证工具

**文件：`frontend/lib/auth.ts`**

```typescript
/**
 * 认证相关的工具函数
 */

const TOKEN_KEY = 'auth_token';

/**
 * 保存 JWT Token 到本地存储
 */
export const setToken = (token: string): void => {
  localStorage.setItem(TOKEN_KEY, token);
};

/**
 * 从本地存储获取 JWT Token
 */
export const getToken = (): string | null => {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
};

/**
 * 删除本地存储的 Token
 */
export const removeToken = (): void => {
  localStorage.removeItem(TOKEN_KEY);
};

/**
 * 检查是否已认证
 */
export const isAuthenticated = (): boolean => {
  return !!getToken();
};

/**
 * 获取 Authorization Header
 */
export const getAuthHeader = (): Record<string, string> => {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
};

/**
 * 获取完整的请求头（包含认证和 Content-Type）
 */
export const getFullHeaders = (contentType = 'application/json'): Record<string, string> => {
  return {
    'Content-Type': contentType,
    ...getAuthHeader(),
  };
};
```

#### 3.2 修改 `page.tsx`

关键改动：

```typescript
// 在 useEffect 中添加认证检查
useEffect(() => {
  if (!getToken()) {
    router.push('/login');
  }
}, [router]);

// 修改 fetchHistory
const fetchHistory = async () => {
  try {
    const res = await fetch("http://127.0.0.1:8000/api/history", {
      headers: getAuthHeader()  // ⭐️ 添加认证头
    });
    if (!res.ok) {
      if (res.status === 401) {
        removeToken();
        router.push('/login');
        return;
      }
      throw new Error(`获取历史失败: ${res.status}`);
    }
    const list = await res.json();
    setHistory(list);
  } catch (err) {
    console.error("获取历史失败:", err);
  }
};

// 修改 startWorkflow
const startWorkflow = async () => {
  if (!topic) return;
  setLoading(true);
  setData(null);

  try {
    const res = await fetch("http://127.0.0.1:8000/api/workflow", {
      method: "POST",
      headers: getFullHeaders(),  // ⭐️ 使用完整的请求头
      body: JSON.stringify({ topic }),
    });

    if (!res.ok) {
      if (res.status === 401) {
        removeToken();
        router.push('/login');
        return;
      }
      const errorText = await res.text();
      throw new Error(`后端返回错误 (${res.status}): ${errorText}`);
    }

    const result = await res.json();
    setData(result);
    fetchHistory();
  } catch (error) {
    console.error("报错啦:", error);
    alert(error instanceof Error ? error.message : "调用后端失败");
  } finally {
    setLoading(false);
  }
};

// 添加删除函数
const deleteWorkflow = async (workflowId: string) => {
  if (!confirm("确定要删除这条记录吗？")) return;

  try {
    const res = await fetch(`http://127.0.0.1:8000/api/workflow/${workflowId}`, {
      method: "DELETE",
      headers: getAuthHeader()
    });

    if (!res.ok) {
      throw new Error(`删除失败: ${res.status}`);
    }

    fetchHistory();
    setData(null);
    setSelectedHistoryId(null);
    alert("删除成功");
  } catch (error) {
    console.error("删除失败:", error);
    alert(error instanceof Error ? error.message : "删除失败");
  }
};
```

---

### 步骤 4️⃣：创建登录页面（10分钟）

**文件：`frontend/app/login/page.tsx`**

```typescript
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { setToken } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const response = await fetch("http://127.0.0.1:8000/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "登录失败");
      }

      const data = await response.json();
      setToken(data.access_token);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center">
      <div className="bg-white rounded-2xl shadow-2xl p-8 w-full max-w-md">
        <h1 className="text-3xl font-bold text-center text-gray-900 mb-8">
          🚀 Nexus AI
        </h1>

        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              邮箱
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="your@email.com"
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none text-black"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              密码
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none text-black"
              required
            />
          </div>

          {error && (
            <div className="bg-red-100 text-red-700 p-3 rounded-lg text-sm">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 text-white py-2 rounded-lg font-bold hover:bg-blue-700 transition disabled:bg-gray-400 disabled:cursor-not-allowed"
          >
            {loading ? "登录中..." : "登录"}
          </button>
        </form>
      </div>
    </div>
  );
}
```

---

### 步骤 5️⃣：配置环境变量（2分钟）

**文件：`backend/.env`**

```bash
# OpenAI 配置
OPENAI_API_KEY=sk-your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1

# Supabase 配置
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# JWT 配置（生产环境务必修改）
JWT_SECRET=your-super-secret-key-change-this-in-production
```

**文件：`frontend/.env.local`**

```bash
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

---

## 验证清单

### ✅ 数据库层面
- [ ] 表中有 `user_id` 字段
- [ ] 表中有 `is_deleted` 字段
- [ ] 创建了索引
- [ ] 启用了 RLS 策略
- [ ] 测试 RLS 是否生效（用不同用户查询）

### ✅ 后端层面
- [ ] `orchestrator.py` 中 `run_workflow` 接收 `user_id`
- [ ] `get_workflow_history` 过滤 `user_id`
- [ ] 添加了 `delete_workflow` 和 `restore_workflow` 方法
- [ ] `main.py` 中所有 API 都使用 `Depends(get_current_user)`
- [ ] 测试删除操作是否验证权限

### ✅ 前端层面
- [ ] 创建了 `lib/auth.ts`
- [ ] `page.tsx` 中添加了认证检查
- [ ] 所有 API 请求都携带 Authorization Header
- [ ] 添加了删除按钮和删除逻辑
- [ ] 创建了登录页面

### ✅ 功能测试
- [ ] 用户 A 登录后只能看到自己的历史记录
- [ ] 用户 A 删除记录后，用户 B 的记录不受影响
- [ ] 删除后可以恢复
- [ ] Token 过期后自动跳转到登录页

---

## 常见问题

### Q1: 如何生成 JWT Token？

```python
# 在你的认证端点中
import jwt
from datetime import datetime, timedelta

def create_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    token = jwt.encode(
        payload,
        os.environ.get("JWT_SECRET"),
        algorithm="HS256"
    )
    return token
```

### Q2: 如何与 Supabase Auth 集成？

```python
# 使用 Supabase 的认证系统
from supabase import create_client

supabase = create_client(url, key)

# 用户登录
response = supabase.auth.sign_in_with_password({
    "email": email,
    "password": password
})

# 获取 user_id
user_id = response.user.id
```

### Q3: 生产环境如何保护 JWT_SECRET？

```bash
# 使用环境变量，不要硬编码
export JWT_SECRET=$(openssl rand -hex 32)

# 或使用密钥管理服务
# AWS Secrets Manager / Azure Key Vault / HashiCorp Vault
```

### Q4: 如何处理 Token 刷新？

```python
@app.post("/api/auth/refresh")
async def refresh_token(user_id: str = Depends(get_current_user)):
    new_token = create_token(user_id)
    return {"access_token": new_token}
```

---

## 性能优化建议

### 1. 添加缓存

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_user_workflows_cached(user_id: str):
    # 缓存用户的工作流列表
    pass
```

### 2. 分页查询

```python
@app.get("/api/history")
async def get_history(
    user_id: str = Depends(get_current_user),
    page: int = 1,
    page_size: int = 10
):
    offset = (page - 1) * page_size
    response = orchestrator.supabase.table("nexus_workflows")\
        .select("*")\
        .eq("user_id", user_id)\
        .eq("is_deleted", False)\
        .order("created_at", desc=True)\
        .range(offset, offset + page_size - 1)\
        .execute()
    return response.data
```

### 3. 批量删除

```python
def delete_workflows_batch(workflow_ids: list, user_id: str) -> bool:
    """批量删除多个工作流"""
    try:
        orchestrator.supabase.table("nexus_workflows")\
            .update({"is_deleted": True, "deleted_at": "now()"})\
            .in_("id", workflow_ids)\
            .eq("user_id", user_id)\
            .execute()
        return True
    except Exception as e:
        print(f"批量删除失败: {e}")
        return False
```

---

## 下一步

1. **实现用户注册** - 创建 `/api/auth/register` 端点
2. **添加用户资料** - 创建 `users` 表，存储用户信息
3. **实现分享功能** - 允许用户分享工作流给其他用户
4. **添加权限管理** - 支持不同的用户角色（admin, user, viewer）
5. **实现审计日志** - 记录所有操作（创建、删除、恢复）

---

## 支持

如有问题，请检查：
1. 环境变量是否正确配置
2. Supabase RLS 策略是否启用
3. JWT Token 是否有效
4. 数据库表结构是否正确


