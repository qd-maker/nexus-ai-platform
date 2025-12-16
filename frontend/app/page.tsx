"use client"; // 👈 必须加这一行，因为我们要用 useState/useEffect (客户端交互)

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import supabase from "@/lib/supabaseClient";

// 控制台调试开关：在 .env.local 中设置 NEXT_PUBLIC_DEBUG=true 可开启控制台错误输出
const DEBUG = process.env.NEXT_PUBLIC_DEBUG === 'true';

// 定义后端返回的数据结构 (和 Python 里的 Schema 对应)
interface AgentResult {
  agent_name?: string;
  content: string;
  duration: number;
}

interface WorkflowResponse {
  workflow_id: string;
  total_time?: number; // 历史记录可能没有该字段
  results: AgentResult[] | any[]; // 历史记录里 result 可能是 any[]
}

// 历史记录项
interface HistoryItem {
  id: string;
  topic: string;
  status: string;
  created_at: string;
  result: any[]; // 存具体内容
}

// 删除确认对话框的状态
interface DeleteConfirmState {
  isOpen: boolean;
  workflowId: string | null;
  topic: string | null;
}

export default function Home() {
  const router = useRouter();
  const [topic, setTopic] = useState("");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<WorkflowResponse | null>(null); // 当前展示的报告
  const [history, setHistory] = useState<HistoryItem[]>([]); // 左侧历史列表
  const [sidebarOpen, setSidebarOpen] = useState(true); // 👈 侧边栏开关
  const [deleteConfirm, setDeleteConfirm] = useState<DeleteConfirmState>({
    isOpen: false,
    workflowId: null,
    topic: null,
  }); // 删除确认对话框状态
  const [deletingId, setDeletingId] = useState<string | null>(null); // 正在删除的项目ID（用于破碎动画）
  const [session, setSession] = useState<import("@supabase/supabase-js").Session | null>(null);
  const [authChecking, setAuthChecking] = useState(true);

  const signOut = async () => {
    try {
      await supabase.auth.signOut();
    } finally {
      setSession(null);
      setData(null);
      setHistory([]);
      router.push('/login');
    }
  };

  // 为渲染层准备一个安全的 results 数组（兼容历史记录多种存储形态）
  const safeResults: any[] = Array.isArray(data?.results)
    ? (data!.results as any[])
    : (data && Array.isArray((data as any).results?.results)
        ? (data as any).results.results
        : []);

  // 在关闭 DEBUG 时，抑制控制台的 error/warn，避免 Next.js 开发模式左下角错误提示干扰
  useEffect(() => {
    if (!DEBUG) {
      const originalError = console.error;
      const originalWarn = console.warn;
      // @ts-ignore
      console.error = (..._args: any[]) => {};
      // @ts-ignore
      console.warn = (..._args: any[]) => {};
      return () => {
        console.error = originalError;
        console.warn = originalWarn;
      };
    }
  }, []);

  // 当获得 session 后，拉取历史
  useEffect(() => {
    if (session?.access_token) {
      fetchHistory();
    }
  }, [session]);

  // 路由保护：检查是否已登录
  useEffect(() => {
    let mounted = true;
    (async () => {
      const { data } = await supabase.auth.getSession();
      const s = data.session ?? null;
      if (!s) {
        setAuthChecking(false);
        router.push('/login');
        return;
      }
      if (mounted) {
        setSession(s);
        setAuthChecking(false);
      }
    })();

    const { data: sub } = supabase.auth.onAuthStateChange((_event, sess) => {
      if (!sess) {
        router.push('/login');
      } else {
        setSession(sess);
      }
    });

    return () => {
      mounted = false;
      sub?.subscription?.unsubscribe?.();
    };
  }, []);

  const fetchHistory = async () => {
    if (!session?.access_token) return;
    try {
      const res = await fetch("http://127.0.0.1:8000/api/history", {
        headers: {
          Authorization: `Bearer ${session.access_token}`,
        },
      });
      if (!res.ok) {
        throw new Error(`获取历史失败: ${res.status}`);
      }
      const list = await res.json();
      setHistory(list);
    } catch (err) {
      console.error("获取历史失败:", err);
    }
  };

  // 打开删除确认对话框
  const openDeleteConfirm = (e: React.MouseEvent, item: HistoryItem) => {
    e.stopPropagation(); // 防止触发 loadHistoryItem
    setDeleteConfirm({
      isOpen: true,
      workflowId: item.id,
      topic: item.topic,
    });
  };

  // 关闭删除确认对话框
  const closeDeleteConfirm = () => {
    setDeleteConfirm({
      isOpen: false,
      workflowId: null,
      topic: null,
    });
  };

  // 执行删除操作
  const confirmDelete = async () => {
    if (!deleteConfirm.workflowId) return;
    if (!session?.access_token) {
      router.push('/login');
      return;
    }

    const workflowId = deleteConfirm.workflowId;
    
    // 触发破碎动画
    setDeletingId(workflowId);

    // 立刻关闭确认弹窗，让用户看到破碎动画
    closeDeleteConfirm();
    
    // 等待动画完成后再删除
    setTimeout(async () => {
      try {
        const res = await fetch(
          `http://127.0.0.1:8000/api/workflow/${workflowId}`,
          {
            method: "DELETE",
            headers: {
              Authorization: `Bearer ${session.access_token}`,
            },
          }
        );

        if (!res.ok) {
          throw new Error(`删除失败: ${res.status}`);
        }

        // 删除成功后，更新历史列表
        setHistory((prev) => prev.filter((item) => item.id !== workflowId));
        
        // 如果删除的是当前展示的数据，清空展示
        if (data?.workflow_id === workflowId) {
          setData(null);
        }

        console.log(`✅ 工作流 ${workflowId} 已删除`);
      } catch (err) {
        console.error("删除失败:", err);
        alert("删除失败，请重试");
        setDeletingId(null);
      }
    }, 600); // 等待动画完成（600ms）
  };

  // 核心逻辑：调用 FastAPI
  const startWorkflow = async () => {
    if (!topic) return;
    if (!session?.access_token) {
      router.push('/login');
      return;
    }
    setLoading(true);
    setData(null); // 清空旧数据

    try {
      const res = await fetch("http://127.0.0.1:8000/api/workflow", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({
          topic: topic,
        }),
      });

      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(`后端返回错误 (${res.status}): ${errorText}`);
      }

      const result = await res.json();
      setData(result); // 把数据存起来，页面会自动刷新

      // 任务完成后刷新历史
      fetchHistory();
    } catch (error) {
      console.error("报错啦:", error);
      const errorMessage = error instanceof Error
        ? error.message
        : "调用后端失败，请检查：\n1. 后端服务是否在运行\n2. 端口 8000 是否被占用\n3. 网络连接是否正常";
      alert(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  // 点击左侧历史记录，展示历史报告到右侧
  const loadHistoryItem = (item: HistoryItem) => {
    // 兼容两种存储形态：
    // 1) result 为数组（直接是智能体结果列表）
    // 2) result 为对象，且包含 result.results 数组（我们曾经保存过整个响应对象）
    const normalized = Array.isArray(item.result)
      ? item.result
      : (item.result && Array.isArray((item.result as any).results)
          ? (item.result as any).results
          : []);

    const historyAsResponse: WorkflowResponse = {
      workflow_id: item.id,
      total_time: 0, // 历史记录里可能没有该字段
      results: normalized,
    };
    setData(historyAsResponse);
  };

  if (authChecking) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="flex items-center gap-3 text-gray-600">
          <div className="h-6 w-6 rounded-full border-4 border-blue-600 border-t-transparent animate-spin" aria-hidden="true" />
          正在验证登录状态...
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-50 flex" aria-busy={loading}>
      {/* 加载中全屏遮罩 + Spinner（不可手动关闭） */}
      {loading && (
        <div className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm flex items-center justify-center select-none">
          <div className="bg-white dark:bg-neutral-900 rounded-2xl p-6 shadow-xl border border-white/20 max-w-md w-[90%]">
            <div className="flex items-center gap-4">
              <div className="h-8 w-8 rounded-full border-4 border-blue-600 border-t-transparent animate-spin" aria-hidden="true" />
              <div className="text-gray-800 dark:text-gray-100 font-semibold">AI 正在思考中...</div>
            </div>
            <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">请稍候，系统正在处理您的请求。</p>
          </div>
        </div>
      )}

      {!sidebarOpen && (
        <button
          aria-label="打开侧边栏"
          onClick={() => { if (!loading) setSidebarOpen(true); }}
          disabled={loading}
          aria-disabled={loading}
          className="fixed top-4 left-4 z-40 bg-white border rounded-full p-2 shadow hover:bg-gray-50 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          title={loading ? '任务进行中，暂不可展开侧边栏' : '打开侧边栏'}
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" className="w-5 h-5">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
      )}

      {/* 右上角：用户邮箱 + 登出按钮 */}
      {session && (
        <div className="fixed top-4 right-4 z-40 flex items-center gap-3">
          <span className="text-sm text-gray-700 bg-white border rounded-full px-3 py-1 shadow" title={session.user?.email || undefined}>
            {session.user?.email || '已登录'}
          </span>
          <button
            onClick={signOut}
            className="bg-white border rounded-full px-4 py-2 shadow hover:bg-gray-50 text-gray-700"
            title="登出"
          >
            退出登录
          </button>
        </div>
      )}

      {/* 👈 左侧：侧边栏（可开合） */}
      <aside aria-hidden={!sidebarOpen} className={`fixed top-0 left-0 h-screen w-64 bg-white border-r border-gray-200 p-4 z-40 transform transition-transform duration-300 ease-in-out ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="flex items-center justify-between mb-4 px-2">
          <h2 className="font-bold text-gray-700">📜 历史记录</h2>
          <button
            aria-label="关闭侧边栏"
            onClick={() => { if (!loading) setSidebarOpen(false); }}
            disabled={loading}
            aria-disabled={loading}
            className="p-2 rounded hover:bg-gray-100 text-gray-600 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            title={loading ? '任务进行中，暂不可关闭侧边栏' : '关闭侧边栏'}
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" className="w-5 h-5">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" />
            </svg>
          </button>
        </div>
        <div className="space-y-2 overflow-y-auto h-[calc(100vh-64px)]">
          {history.map((item) => (
            <div
              key={item.id}
              onClick={() => loadHistoryItem(item)}
              className={`group p-3 rounded-lg hover:bg-blue-50 cursor-pointer text-sm text-gray-600 border border-transparent hover:border-blue-100 transition relative ${
                deletingId === item.id ? "history-item-deleting" : ""
              }`}
              title={item.topic}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 truncate">
                  <div className="truncate">{item.topic}</div>
                  <div className="text-xs text-gray-400 mt-1">
                    {new Date(item.created_at).toLocaleDateString()}
                  </div>
                </div>
                {/* 删除按钮 - 右侧 */}
                <button
                  onClick={(e) => openDeleteConfirm(e, item)}
                  className="flex-shrink-0 p-1.5 rounded hover:bg-red-100 text-gray-400 hover:text-red-600 transition opacity-0 group-hover:opacity-100"
                  title="删除此记录"
                  aria-label="删除"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    className="w-4 h-4"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                    />
                  </svg>
                </button>
              </div>
            </div>
          ))}
          {history.length === 0 && (
            <div className="text-xs text-gray-400 px-2">暂无历史</div>
          )}
        </div>
      </aside>

      {/* 点击侧边栏外部的透明遮罩，自动关闭侧边栏 */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30"
          aria-hidden="true"
          onClick={() => { if (!loading) setSidebarOpen(false); }}
          title={loading ? '任务进行中，暂不可关闭侧边栏' : undefined}
        />
      )}

      {/* 删除确认对话框 */}
      {deleteConfirm.isOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center select-none">
          <div className="bg-white rounded-2xl p-6 shadow-xl border border-gray-200 max-w-md w-[90%] animate-fade-in">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 flex items-center justify-center h-12 w-12 rounded-full bg-red-100">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  className="w-6 h-6 text-red-600"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M12 9v2m0 4v2m0 0v2m0-6v-2m0 0V9m0 0h2m-2 0h-2m0 0V7m0 2v2m0 0v2m0-6v-2m0 0V9m0 0h2m-2 0h-2"
                  />
                </svg>
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-bold text-gray-900 mb-2">确认删除</h3>
                <p className="text-sm text-gray-600 mb-4">
                  确定要删除这条记录吗？
                  <br />
                  <span className="font-semibold text-gray-800">"{deleteConfirm.topic}"</span>
                  <br />
                  <span className="text-red-600">此操作不可撤销</span>
                </p>
                <div className="flex gap-3 justify-end">
                  <button
                    onClick={closeDeleteConfirm}
                    className="px-4 py-2 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 transition font-medium"
                  >
                    取消
                  </button>
                  <button
                    onClick={confirmDelete}
                    className="px-4 py-2 rounded-lg bg-red-600 text-white hover:bg-red-700 transition font-medium"
                  >
                    删除
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 👉 右侧：主操作区 */}
      <section className="flex-1 p-10 h-screen overflow-y-auto">
        <div className="max-w-4xl mx-auto">
          {/* 标题区 */}
          <div className="text-center mb-10">
            <h1 className="text-4xl font-bold text-gray-900 mb-2">Nexus AI Orchestrator</h1>
            <p className="text-gray-500">输入一个主题，唤醒多个智能体为您工作</p>
          </div>

          {/* 输入区 */}
          <div className="flex gap-4 mb-10">
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  if (!loading && topic.trim()) {
                    startWorkflow();
                  }
                }
              }}
              placeholder="输入主题..."
              disabled={loading}
              aria-disabled={loading}
              className="flex-1 p-4 rounded-xl border border-gray-300 shadow-sm focus:ring-2 focus:ring-blue-500 outline-none text-black disabled:bg-gray-100 disabled:text-gray-500 disabled:cursor-not-allowed"
            />
            <button
              onClick={startWorkflow}
              disabled={loading}
              className="bg-blue-600 text-white px-8 py-4 rounded-xl font-bold hover:bg-blue-700 transition cursor-pointer disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {loading ? "分析中..." : "开始"}
            </button>
          </div>

          {/* 结果展示区 */}
          {data && (
            <div className="space-y-6 animate-fade-in">
              {/* 历史数据兼容：只有当 total_time > 0 才显示耗时卡片 */}
              {typeof data.total_time === "number" && data.total_time > 0 && (
                <div className="bg-white p-6 rounded-xl shadow-sm border border-green-100">
                  <h2 className="text-green-600 font-bold">✅ 任务完成</h2>
                  <p className="text-gray-600">
                    本次耗时: {data.total_time.toFixed(2)}秒 | 任务ID: {data.workflow_id}
                  </p>
                </div>
              )}

              {/* 渲染智能体卡片 */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {safeResults.map((agent: any, index: number) => (
                  <div key={index} className="bg-white p-6 rounded-xl shadow-md border border-gray-100 hover:shadow-lg transition">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="font-bold text-lg text-gray-800">{agent.agent_name || "智能体"}</h3>
                      {typeof agent.duration === "number" && (
                        <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
                          {agent.duration.toFixed(1)}s
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap">
                      {agent.content}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
