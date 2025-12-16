# backend/app/main.py

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# 引入新写的模块
from app.schemas import WorkflowRequest, WorkflowResponse
from app.services.orchestrator import NexusOrchestrator
from app.middleware.auth import verify_token

app = FastAPI(title="Nexus AI API", version="0.1.0")

# CORS 配置保持不变...
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.168.52.1:3000",
        "http://192.168.10.24:3000",
    ],
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+):3000$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Authorization"],
)

# 初始化编排器实例
orchestrator = NexusOrchestrator()

# 依赖：获取当前用户 ID（从 JWT 中解码）
def get_current_user(user_id: str = Depends(verify_token)) -> str:
    return user_id


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# ✅ 新增：正式的业务接口（需要鉴权）
@app.post("/api/workflow", response_model=WorkflowResponse)
async def create_workflow(request: WorkflowRequest, user_id: str = Depends(get_current_user)):
    """
    接收前端的任务请求 -> 唤醒编排器 -> 并行处理 -> 返回报告
    """
    response = await orchestrator.run_workflow(
        topic=request.topic,
        user_id=user_id,
    )
    return response

# 历史记录（需要鉴权）
@app.get("/api/history")
async def get_history(user_id: str = Depends(get_current_user)):
    """
    前端页面加载时，会自动调用这个接口，获取当前用户历史记录
    """
    return orchestrator.get_workflow_history(user_id=user_id)

# 删除工作流（需要鉴权）
@app.delete("/api/workflow/{workflow_id}")
async def delete_workflow(workflow_id: str, user_id: str = Depends(get_current_user)):
    """
    删除当前用户的指定工作流记录
    """
    success = orchestrator.delete_workflow(workflow_id, user_id)
    if success:
        return {"status": "success", "message": f"工作流 {workflow_id} 已删除"}
    else:
        return {"status": "error", "message": "删除失败"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)