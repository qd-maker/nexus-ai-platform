# backend/app/schemas.py

from pydantic import BaseModel
from typing import List, Optional

# 1. 定义单个智能体的执行结果
class AgentResult(BaseModel):
    agent_name: str
    task: str
    status: str       # "completed", "failed"
    content: str      # 智能体产出的内容
    duration: float   # 耗时

# 2. 定义前端发过来的请求格式
class WorkflowRequest(BaseModel):
    topic: str        # 用户输入的主题，比如 "特斯拉"
    # agents: List[str] = ["Search", "Analysis", "Writer"] # 需要调用的智能体列表

# 3. 定义最终返回给前端的完整报告
class WorkflowResponse(BaseModel):
    workflow_id: str
    topic: str
    results: List[AgentResult]
    total_time: float