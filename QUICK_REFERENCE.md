# 快速参考卡片

## 🎯 核心概念

| 概念 | 说明 | 示例 |
|------|------|------|
| **user_id** | 用户的唯一标识符 | `550e8400-e29b-41d4-a716-446655440000` |
| **JWT Token** | 用户认证凭证 | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...` |
| **RLS** | 行级安全，数据库级别的访问控制 | 用户只能访问自己的行 |
| **软删除** | 标记为删除但不真正删除 | `is_deleted = true` |
| **Authorization Header** | HTTP 请求头，包含 Token | `Authorization: Bearer <token>` |

---

## 📋 API 端点速查表

### 认证相关

```bash
# 用户登录
POST /api/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123"
}

Response: 200 OK
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### 工作流相关

```bash
# 创建新工作流
POST /api/workflow
Authorization: Bearer <token>
Content-Type: application/json

{
  "topic": "如何做好市场营销"
}

Response: 200 OK
{
  "workflow_id": "a1b2c3d4",
  "topic": "如何做好市场营销",
  "results": [...],
  "total_time": 7.8
}

─────────────────────────────────────────────────────

# 获取历史记录
GET /api/history
Authorization: Bearer <token>

Response: 200 OK
[
  {
    "id": "uuid-1",
    "user_id": "550e8400...",
    "topic": "市场营销",
    "result": {...},
    "is_deleted": false,
    "created_at": "2024-01-15T10:30:00Z"
  },
  ...
]

─────────────────────────────────────────────────────

# 删除工作流
DELETE /api/workflow/{workflow_id}
Authorization: Bearer <token>

Response: 200 OK
{
  "message": "Workflow deleted successfully"
}

─────────────────────────────────────────────────────

# 恢复工作流
POST /api/workflow/{workflow_id}/restore
Authorization: Bearer <token>

Response: 200 OK
{
  "message": "Workflow restored successfully"
}
```

---

## 🔑 关键代码片段

### 前端：获取认证头

```typescript
import { getAuthHeader, getFullHeaders } from '@/lib/auth';

// 方式 1：只获取 Authorization Header
const headers = getAuthHeader();
// { Authorization: "Bearer <token>" }

// 方式 2：获取完整的请求头
const headers = getFullHeaders();
// { "Content-Type": "application/json", Authorization: "Bearer <token>" }

// 使用
const res = await fetch('/api/history', {
  headers: getAuthHeader()
});
```

### 后端：验证用户

```python
from fastapi import Depends
from app.middleware.auth import jwt_handler

def get_current_user(credentials: HTTPAuthCredentials = Depends(security)) -> str:
    result = jwt_handler.verify_token(credentials)
    return result["user_id"]

# 在路由中使用
@app.get("/api/history")
async def get_history(user_id: str = Depends(get_current_user)):
    # user_id 会自动注入
    return orchestrator.get_workflow_history(user_id)
```

### 后端：查询用户数据

```python
# ✅ 正确：过滤 user_id
response = self.supabase.table("nexus_workflows")\
    .select("*")\
    .eq("user_id", user_id)\  # 关键！
    .eq("is_deleted", False)\
    .order("created_at", desc=True)\
    .limit(10)\
    .execute()

# ❌ 错误：没有过滤 user_id
response = self.supabase.table("nexus_workflows")\
    .select("*")\
    .order("created_at", desc=True)\
    .limit(10)\
    .execute()
# 这样会返回所有用户的数据！
```

### 后端：删除前验证权限

```python
def delete_workflow(self, workflow_id: str, user_id: str) -> bool:
    try:
        # 第一步：验证权限
        record = self.supabase.table("nexus_workflows")\
            .select("id")\
            .eq("id", workflow_id)\
            .eq("user_id", user_id)\  # 关键！
            .single()\
            .execute()
        
        if not record.data:
            return False  # 没有权限
        
        # 第二步：执行删除
        self.supabase.table("nexus_workflows")\
            .update({"is_deleted": True, "deleted_at": "now()"})\
            .eq("id", workflow_id)\
            .eq("user_id", user_id)\  # 再次确认
            .execute()
        
        return True
    except Exception as e:
        return False
```

---

## 🚨 常见错误

### ❌ 错误 1：忘记添加 Authorization Header

```typescript
// ❌ 错误
const res = await fetch('/api/workflow', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ topic: '...' })
});
// 返回 401 Unauthorized

// ✅ 正确
const res = await fetch('/api/workflow', {
  method: 'POST',
  headers: getFullHeaders(),
  body: JSON.stringify({ topic: '...' })
});
```

### ❌ 错误 2：查询时忘记过滤 user_id

```python
# ❌ 错误
def get_workflow_history(self):
    response = self.supabase.table("nexus_workflows")\
        .select("*")\
        .order("created_at", desc=True)\
        .execute()
    return response.data
# 返回所有用户的数据！

# ✅ 正确
def get_workflow_history(self, user_id: str):
    response = self.supabase.table("nexus_workflows")\
        .select("*")\
        .eq("user_id", user_id)\
        .order("created_at", desc=True)\
        .execute()
    return response.data
```

### ❌ 错误 3：删除时不验证权限

```python
# ❌ 错误
def delete_workflow(self, workflow_id: str):
    self.supabase.table("nexus_workflows")\
        .update({"is_deleted": True})\
        .eq("id", workflow_id)\
        .execute()
    # 任何用户都可以删除任何记录！

# ✅ 正确
def delete_workflow(self, workflow_id: str, user_id: str):
    # 先验证权限
    record = self.supabase.table("nexus_workflows")\
        .select("id")\
        .eq("id", workflow_id)\
        .eq("user_id", user_id)\
        .single()\
        .execute()
    
    if not record.data:
        return False
    
    # 再删除
    self.supabase.table("nexus_workflows")\
        .update({"is_deleted": True})\
        .eq("id", workflow_id)\
        .eq("user_id", user_id)\
        .execute()
    return True
```

### ❌ 错误 4：真正删除数据而不是软删除

```python
# ❌ 错误：真正删除，无法恢复
DELETE FROM nexus_workflows WHERE id = 'uuid-1'

# ✅ 正确：软删除，可以恢复
UPDATE nexus_workflows
SET is_deleted = true, deleted_at = now()
WHERE id = 'uuid-1'
```

---

## 📊 数据库表结构速查

```sql
-- nexus_workflows 表
CREATE TABLE nexus_workflows (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,              -- ⭐️ 用户 ID
  topic TEXT NOT NULL,                -- 用户输入的主题
  result JSONB NOT NULL,              -- AI 执行结果
  is_deleted BOOLEAN DEFAULT FALSE,   -- ⭐️ 软删除标记
  deleted_at TIMESTAMP,               -- ⭐️ 删除时间
  created_at TIMESTAMP DEFAULT now(), -- 创建时间
  updated_at TIMESTAMP DEFAULT now()  -- 更新时间
);

-- 索引
CREATE INDEX idx_nexus_workflows_user_id 
ON nexus_workflows(user_id);

CREATE INDEX idx_nexus_workflows_user_created 
ON nexus_workflows(user_id, created_at DESC);

CREATE INDEX idx_nexus_workflows_deleted 
ON nexus_workflows(user_id, is_deleted);

-- RLS 策略
ALTER TABLE nexus_workflows ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own workflows"
  ON nexus_workflows FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own workflows"
  ON nexus_workflows FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own workflows"
  ON nexus_workflows FOR UPDATE
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete their own workflows"
  ON nexus_workflows FOR DELETE
  USING (auth.uid() = user_id);
```

---

## 🔄 工作流速查

### 用户登录流程

```
1. 用户访问应用
   ↓
2. 检查 localStorage 中的 Token
   ├─ 有 Token → 进入主页
   └─ 没有 Token → 跳转到登录页
   ↓
3. 用户输入邮箱和密码
   ↓
4. 前端发送 POST /api/auth/login
   ↓
5. 后端验证凭证，返回 Token
   ↓
6. 前端保存 Token 到 localStorage
   ↓
7. 跳转到主页面
```

### 创建工作流流程

```
1. 用户输入主题，点击"开始"
   ↓
2. 前端发送 POST /api/workflow（带 Token）
   ↓
3. 后端验证 Token，提取 user_id
   ↓
4. 调用 orchestrator.run_workflow(topic, user_id)
   ↓
5. 规划任务、并发执行、汇总结果
   ↓
6. 保存到 Supabase（带 user_id）
   ↓
7. 返回结果给前端
   ↓
8. 前端显示结果，刷新历史列表
```

### 删除工作流流程

```
1. 用户点击历史记录的"删除"按钮
   ↓
2. 弹出确认对话框
   ↓
3. 用户点击"确定"
   ↓
4. 前端发送 DELETE /api/workflow/{id}（带 Token）
   ↓
5. 后端验证 Token，提取 user_id
   ↓
6. 验证该记录属于该用户
   ↓
7. 执行软删除（is_deleted = true）
   ↓
8. 返回成功响应
   ↓
9. 前端刷新历史列表
   ↓
10. 用户看到该记录消失
```

---

## 🛡️ 安全检查清单

在部署前检查以下项目：

- [ ] 所有 API 端点都使用 `Depends(get_current_user)`
- [ ] 所有数据库查询都过滤 `user_id`
- [ ] 删除操作都验证权限
- [ ] 启用了数据库 RLS 策略
- [ ] 创建了必要的索引
- [ ] JWT_SECRET 使用强密码
- [ ] 生产环境使用 HTTPS
- [ ] CORS 只允许你的域名
- [ ] Token 有过期时间
- [ ] 实现了 Token 刷新机制

---

## 📈 性能优化检查清单

- [ ] 创建了 user_id 索引
- [ ] 创建了 (user_id, created_at) 复合索引
- [ ] 创建了 (user_id, is_deleted) 复合索引
- [ ] 查询时只选择需要的列
- [ ] 实现了分页
- [ ] 添加了缓存（可选）
- [ ] 监控查询性能

---

## 🚀 部署步骤速查

```bash
# 1. 数据库迁移
# 在 Supabase 控制台执行 SQL 脚本

# 2. 后端部署
cd backend
pip install -r requirements.txt
# 配置 .env
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 3. 前端部署
cd frontend
npm install
npm run build
npm start

# 4. 验证
# 访问 https://your-domain/login
# 登录后访问 https://your-domain/
```

---

## 💡 提示

1. **开发时**：使用 `JWT_SECRET=dev-secret` 即可
2. **生产时**：使用强密码：`openssl rand -hex 32`
3. **测试**：用不同账户登录，验证数据隔离
4. **监控**：记录所有删除操作，便于审计
5. **备份**：定期备份数据库

---

## 📞 常见问题

**Q: 如何重置用户密码？**
A: 实现 `/api/auth/forgot-password` 端点，发送重置链接到邮箱

**Q: 如何支持第三方登录（Google、GitHub）？**
A: 使用 Supabase Auth 的 OAuth 提供商集成

**Q: 如何导出用户数据？**
A: 实现 `/api/export` 端点，返回用户的所有数据

**Q: 如何处理数据隐私（GDPR）？**
A: 实现 `/api/delete-account` 端点，真正删除用户的所有数据

**Q: 如何限制用户操作频率？**
A: 使用 FastAPI 的速率限制中间件

---

## 🎓 学习资源

- [JWT 认证详解](https://jwt.io/)
- [Supabase RLS 文档](https://supabase.com/docs/guides/auth/row-level-security)
- [FastAPI 依赖注入](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [Next.js 认证最佳实践](https://nextjs.org/docs/authentication)
- [数据库安全最佳实践](https://owasp.org/www-project-top-ten/)


