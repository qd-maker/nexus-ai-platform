# backend/app/services/orchestrator.py

import asyncio
import os
import time
import uuid
from dotenv import load_dotenv
from openai import AsyncOpenAI
from ..schemas import AgentResult, WorkflowResponse
from typing import Optional, List
from supabase import create_client, Client

# 加载 .env 里的 API Key
load_dotenv()


class NexusOrchestrator:
    def __init__(self):
        # 初始化异步 OpenAI 客户端
        self.client = AsyncOpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
            base_url=os.environ.get("OPENAI_BASE_URL"),  # 可选代理地址
        )

        # 可选初始化 Supabase（未配置时不阻塞应用启动）
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
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"AI 调用出错: {str(e)}"

    async def _plan_tasks(self, topic: str) -> List[str]:
        """
        大脑核心：根据用户输入，自动决定需要哪些角色，以及他们各自的任务
        """
        print(f"🧠 [Planner] 正在思考如何拆解任务: {topic}...")

        prompt = f"""
        你是 Nexus 系统的任务规划官。
        用户输入了主题："{topic}"
        请拆解成 3 个具体的子任务，并为每个任务分配一个合适的角色名称。
        
        格式要求：请直接返回一个 Python 列表字符串，不要废话。
        例如：["市场分析师:分析市场规模", "技术专家:评估核心壁垒", "风险评估员:列出潜在风险"]
        """

        response_text = await self._call_gpt(
            system_prompt="你是一个严格遵循格式输出的 JSON 助手。",
            user_prompt=prompt,
        )

        try:
            import ast

            task_list = ast.literal_eval(response_text)
            return task_list
        except Exception:
            print("⚠️ 规划解析失败，启用默认方案")
            return [f"通用助手:分析 {topic}"]

    async def _run_single_agent(self, agent_name: str, task_desc: str) -> AgentResult:
        """
        根据不同的角色，分配不同的 Prompt
        """
        start_time = time.time()
        print(f"🤖 [{agent_name}] 正在处理: {task_desc}...")

        prompts = {
            "市场调研员": "你是一个资深的市场调研员。请简短地列出关于该主题的3个关键市场数据。语气要客观。",
            "技术分析师": "你是一个硬核的技术极客。请分析该主题背后的1个核心技术难点。使用专业术语。",
            "竞品对比专家": "你是一个毒舌的评论员。请指出该产品最大的竞争对手是谁，并简述原因。",
            "Default": "你是我的助手，请简短回答。",
        }

        system_prompt = prompts.get(agent_name, prompts["Default"])
        content = await self._call_gpt(system_prompt, task_desc)
        duration = time.time() - start_time

        return AgentResult(
            agent_name=agent_name,
            task=f"Analyze {task_desc}",
            status="completed",
            content=content,
            duration=duration,
        )

    async def run_workflow(self, topic: str, user_id: str) -> WorkflowResponse:
        """
        运行工作流：为指定用户执行任务，并将结果写入 Supabase（如已配置）
        """
        workflow_start = time.time()
        workflow_id = str(uuid.uuid4())[:8]

        planned_tasks = await self._plan_tasks(topic)

        tasks = []
        for item in planned_tasks:
            if ":" in item:
                role, task_desc = item.split(":", 1)
            else:
                role, task_desc = "助手", item
            tasks.append(self._run_single_agent(role, task_desc))

        results = await asyncio.gather(*tasks)
        total_time = time.time() - workflow_start

        response = WorkflowResponse(
            workflow_id=workflow_id,
            topic=topic,
            results=results,
            total_time=total_time,
        )

        if self.supabase is not None:
            try:
                self.supabase.table("nexus_workflows").insert(
                    {
                        "user_id": user_id,
                        "topic": topic,
                        "result": response.model_dump(),  # JSONB 保存完整响应
                    }
                ).execute()
            except Exception as e:
                print(f"[WARN] Supabase 插入失败：{e}")

        return response

    def get_workflow_history(self, user_id: str, limit: int = 10):
        """
        查账本：获取当前用户最近的任务记录
        """
        if self.supabase is None:
            print("[INFO] Supabase 未初始化，返回空历史")
            return []
        try:
            response = (
                self.supabase.table("nexus_workflows")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return response.data
        except Exception as e:
            print(f"查询失败: {e}")
            return []

    def delete_workflow(self, workflow_id: str, user_id: str) -> bool:
        """
        删除指定用户的指定工作流记录（防止跨用户删除）
        """
        if self.supabase is None:
            print("[ERROR] Supabase 未初始化，无法删除")
            return False
        try:
            (
                self.supabase.table("nexus_workflows")
                .delete()
                .eq("id", workflow_id)
                .eq("user_id", user_id)
                .execute()
            )
            print(f"[SUCCESS] 用户 {user_id} 的工作流 {workflow_id} 已删除")
            return True
        except Exception as e:
            print(f"[ERROR] 删除工作流失败: {e}")
            return False
