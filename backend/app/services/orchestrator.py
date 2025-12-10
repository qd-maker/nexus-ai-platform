# backend/app/services/orchestrator.py

import asyncio
import os
import time
import uuid
from dotenv import load_dotenv
from openai import AsyncOpenAI  # 👈 注意：这里引入的是异步客户端
from ..schemas import AgentResult, WorkflowResponse
from typing import Optional
from pathlib import Path
from supabase import create_client, Client

# 加载 .env 里的 API Key
load_dotenv()

        # 👇 新增：初始化数据库连接
       

class NexusOrchestrator:
    def __init__(self):
        # 初始化异步客户端
        # 这就像雇佣了一个支持"多线程操作"的接线员
        self.client = AsyncOpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
            base_url=os.environ.get("OPENAI_BASE_URL")  # 如果你用了代理地址，加上这个；没有就忽略
        )

        # 可选初始化 Supabase（如果未配置，不应阻塞应用启动）
        url = os.environ.get("SUPABASE_URL")
        # 优先使用服务端写入密钥（如提供），否则回退到 anon key
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
        self.supabase: Optional[Client] = None
        if url and key:
            try:
                self.supabase = create_client(url, key)
                if os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
                    print("[INFO] Supabase 已使用 service_role key（具备写入权限）")
                else:
                    print("[INFO] Supabase 使用 anon key，可能受 RLS 限制写入")
            except Exception as e:
                print(f"[WARN] Supabase 初始化失败：{e}. 将在无数据库模式下运行。")
        else:
            print("[INFO] 未检测到 SUPABASE_URL/SUPABASE_KEY，跳过 Supabase 初始化。")
    async def _call_gpt(self, system_prompt: str, user_prompt: str) -> str:
        """
        封装好的底层 AI 调用函数
        """
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",  # 或者 gpt-3.5-turbo
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"AI 调用出错: {str(e)}"

    # 把它加在 _call_gpt 和 _run_single_agent 之间
    
    async def _plan_tasks(self, topic: str) -> list:
        """
        大脑核心：根据用户输入，自动决定需要哪些角色，以及他们各自的任务
        """
        print(f"🧠 [Planner] 正在思考如何拆解任务: {topic}...")
        
        # 1. 写一个专门用来"分派任务"的 Prompt
        prompt = f"""
        你是 Nexus 系统的任务规划官。
        用户输入了主题："{topic}"
        请拆解成 3 个具体的子任务，并为每个任务分配一个合适的角色名称。
        
        格式要求：请直接返回一个 Python 列表字符串，不要废话。
        例如：["市场分析师:分析市场规模", "技术专家:评估核心壁垒", "风险评估员:列出潜在风险"]
        """
        
        # 2. 调用 AI
        response_text = await self._call_gpt(
            system_prompt="你是一个严格遵循格式输出的 JSON 助手。",
            user_prompt=prompt
        )
    
        # 3. 简单的清洗数据 (把 AI 返回的字符串变成真的列表)
        # 实际生产中我们会用更高级的 Output Parser，这里先用简单粗暴的方法
        try:
            # 假设 AI 很听话，返回了 '["A:任务1", "B:任务2"]'
            # eval 是个危险函数，生产环境慎用，但学习阶段用来解析 Python 格式字符串最快
            import ast
            task_list = ast.literal_eval(response_text) 
            return task_list
        except:
            # 如果 AI 犯蠢了，就用默认方案兜底
            print("⚠️ 规划解析失败，启用默认方案")
            return [f"通用助手:分析 {topic}"]

    async def _run_single_agent(self, agent_name: str, topic: str) -> AgentResult:
        """
        根据不同的角色，分配不同的 Prompt
        """
        start_time = time.time()
        print(f"🤖 [{agent_name}] 正在处理: {topic}...")

        # 1. 定义不同角色的“人设”
        prompts = {
            "市场调研员": "你是一个资深的市场调研员。请简短地列出关于该主题的3个关键市场数据。语气要客观。",
            "技术分析师": "你是一个硬核的技术极客。请分析该主题背后的1个核心技术难点。使用专业术语。",
            "竞品对比专家": "你是一个毒舌的评论员。请指出该产品最大的竞争对手是谁，并简述原因。",
            "Default": "你是我的助手，请简短回答。"
        }

        # 2. 选取对应的 System Prompt
        # 如果找不到名字，就用 Default
        system_prompt = prompts.get(agent_name, prompts["Default"])
        
        # 3. ⭐️ 真正的 AI 调用 (非阻塞)
        content = await self._call_gpt(system_prompt, topic)
        
        duration = time.time() - start_time
        
        return AgentResult(
            agent_name=agent_name,
            task=f"Analyze {topic}",
            status="completed",
            content=content,
            duration=duration
        )

    # 修改 run_workflow 方法
    async def run_workflow(self, topic: str) -> WorkflowResponse: # 注意：这里删掉了 agent_list 参数
        workflow_start = time.time()
        workflow_id = str(uuid.uuid4())[:8]

        # ⭐️ 第一步：先问大脑，要雇谁？(这是新增的步骤)
        # 这里的 tasks_plan 可能是 ["财务:分析...", "技术:分析..."]
        planned_tasks = await self._plan_tasks(topic)
        
        # ⭐️ 第二步：根据大脑的计划，创建并发任务
        # 我们把 "角色:任务" 这种字符串拆开
        tasks = []
        for item in planned_tasks:
            # 假设格式是 "角色名:任务描述"
            if ":" in item:
                role, task_desc = item.split(":", 1)
            else:
                role, task_desc = "助手", item
            
            # 创建任务
            tasks.append(self._run_single_agent(role, task_desc)) # 注意 _run_single_agent 里的 topic 参数现在变成了具体的 task_desc
        
        # 第三步：并发执行 (和以前一样)
        results = await asyncio.gather(*tasks)

        total_time = time.time() - workflow_start

        response = WorkflowResponse(
            workflow_id=workflow_id,
            topic=topic,
            results=results,
            total_time=total_time
        )

        # 持久化到 Supabase（如已配置）
        if self.supabase is not None:
            try:
                self.supabase.table("nexus_workflows").insert({
                    "topic": topic,
                    "result": response.model_dump()  # JSONB 将保存完整响应
                }).execute()
            except Exception as e:
                print(f"[WARN] Supabase 插入失败：{e}")

        return response

    
    def get_workflow_history(self, limit: int = 10):
        """
        查账本：获取最近的 10 条任务记录
        """
        try:
            # 这里的 .order("created_at", desc=True) 意思是：最新的排在最前面
            response = self.supabase.table("nexus_workflows")\
                .select("*")\
                .order("created_at", desc=True)\
                .limit(limit)\
                .execute()
            return response.data
        except Exception as e:
            print(f"查询失败: {e}")
            return []

    def delete_workflow(self, workflow_id: str) -> bool:
        """
        删除指定的工作流记录
        
        Args:
            workflow_id: 要删除的工作流ID
            
        Returns:
            bool: 删除是否成功
        """
        if self.supabase is None:
            print("[ERROR] Supabase 未初始化，无法删除")
            return False
        
        try:
            # 根据 workflow_id 删除记录
            response = self.supabase.table("nexus_workflows")\
                .delete()\
                .eq("id", workflow_id)\
                .execute()
            
            print(f"[SUCCESS] 工作流 {workflow_id} 已删除")
            return True
        except Exception as e:
            print(f"[ERROR] 删除工作流失败: {e}")
            return False

    def delete_workflow(self, workflow_id: str) -> bool:
        """
        删除指定的工作流记录
        """
        try:
            if self.supabase is None:
                print("[ERROR] Supabase 未初始化，无法删除")
                return False
            
            # 从数据库中删除指定 ID 的记录
            response = self.supabase.table("nexus_workflows")\
                .delete()\
                .eq("id", workflow_id)\
                .execute()
            
            print(f"[SUCCESS] 工作流 {workflow_id} 已删除")
            return True
        except Exception as e:
            print(f"[ERROR] 删除失败: {e}")
            return False