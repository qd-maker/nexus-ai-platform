# backend/app/services/mock_agent.py

import asyncio

async def simple_agent_task(agent_name: str, delay: int):
    """
    模拟一个 AI 智能体执行任务。
    agent_name: 智能体的名字
    delay: 模拟思考需要的时间 (秒)
    """
    print(f"🤖 [{agent_name}] 开始思考... (预计耗时 {delay}秒)")
    
    # 关键点：await asyncio.sleep() 是非阻塞的睡眠。
    # 它意思是："我先睡会儿，CPU 你去忙别的事吧，不用等我。"
    await asyncio.sleep(delay)
    
    print(f"✅ [{agent_name}] 思考完成！")
    return f"[{agent_name}] 的报告内容"