# backend/app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# 引入新写的模块
from app.schemas import WorkflowRequest, WorkflowResponse
from app.services.orchestrator import NexusOrchestrator

app = FastAPI(title="Nexus AI API", version="0.1.0")

# CORS 配置保持不变...
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.168.52.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化编排器实例
orchestrator = NexusOrchestrator()

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# ✅ 新增：正式的业务接口
@app.post("/api/workflow", response_model=WorkflowResponse)
async def create_workflow(request: WorkflowRequest):
    """
    接收前端的任务请求 -> 唤醒编排器 -> 并行处理 -> 返回报告
    """
    # 直接调用编排器的业务逻辑（现在只需要 topic，agent 会自动规划）
    response = await orchestrator.run_workflow(
        topic=request.topic
    )
    return response

# 加在 @app.post("/api/workflow") 的后面

@app.get("/api/history")
async def get_history():
    """
    前端页面加载时，会自动调用这个接口，获取历史记录
    """
    return orchestrator.get_workflow_history()

@app.delete("/api/workflow/{workflow_id}")
async def delete_workflow(workflow_id: str):
    """
    删除指定的工作流记录
    """
    success = orchestrator.delete_workflow(workflow_id)
    if success:
        return {"status": "success", "message": f"工作流 {workflow_id} 已删除"}
    else:
        return {"status": "error", "message": "删除失败"}

if __name__ == "__main__":
    uvicorn.run('app.main:app', host="127.0.0.1", port=8000)