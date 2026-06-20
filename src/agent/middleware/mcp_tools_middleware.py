"""
MCP 工具动态 Middleware

功能：
- 每次模型调用时，从注册表注入当前 MCP 工具列表
- 拦截 MCP 工具调用，从注册表找到实际工具并执行

原理：
- ToolNode 在编译时固定了工具列表，无法动态修改
- wrap_model_call：每次调用模型前，将注册表中的 MCP 工具注入到 request.tools
- awrap_tool_call：拦截工具调用，用注册表中的实际工具替换 ToolNode 的占位工具

热更新：
- 由 Apollo SDK 内置轮询驱动（每 30 秒自动检测配置变更）
- 检测到变更后设置 _mcp_reload_pending 标记
- 下次 agent 调用时在 async 上下文中执行重载
"""

from typing import Any, Callable, Awaitable

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ContextT,
    ModelRequest,
    ModelResponse,
    ResponseT,
)
from langgraph.prebuilt.tool_node import ToolCallRequest
from tools.mcp_tools_registry import get_tools as get_mcp_tools, get_tool_by_name, load_tools
from common.apollo_config import consume_mcp_reload_pending


class MCPToolsMiddleware(AgentMiddleware[AgentState, ContextT, ResponseT]):
    """
    MCP 工具动态 Middleware

    通过 wrap_model_call + awrap_tool_call 实现 MCP 工具的动态注入和执行。
    热更新由 Apollo SDK 内置轮询驱动，无需额外线程。
    """

    def __init__(self, static_tools: list[BaseTool] | None = None):
        """
        Args:
            static_tools: 非 MCP 的静态工具列表（如 web_search）
        """
        self._static_tools = static_tools or []

    @property
    def name(self) -> str:
        return "MCPToolsMiddleware"

    def _get_all_tools(self) -> list[BaseTool]:
        """合并静态工具和动态 MCP 工具"""
        return self._static_tools + get_mcp_tools()

    def wrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], ModelResponse[ResponseT]],
    ) -> ModelResponse[ResponseT]:
        """每次调用模型前，注入当前 MCP 工具列表"""
        all_tools = self._get_all_tools()
        modified_request = request.override(tools=all_tools)
        return handler(modified_request)

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        """异步版本：每次调用模型前，注入当前 MCP 工具列表"""
        # 检测 Apollo 配置变更，在 async 上下文中执行重载
        if consume_mcp_reload_pending():
            await load_tools()

        all_tools = self._get_all_tools()
        modified_request = request.override(tools=all_tools)
        return await handler(modified_request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        """
        拦截工具调用，如果目标工具在 MCP 注册表中，则替换为实际工具。

        ToolNode 编译时工具固定，MCP 工具不在其中，tool 为 None。
        通过 override(tool=实际工具) 让 ToolNode 执行真正的 MCP 工具。

        如果工具既不在静态列表也不在 MCP 注册表中（说明已被移除），
        直接返回错误消息，避免 ToolNode 报出不友好的错误。
        """
        tool_name = request.tool_call["name"]

        # 如果 ToolNode 已经找到了工具（静态工具），直接执行
        if request.tool is not None:
            return await handler(request)

        # 尝试从 MCP 注册表找到实际工具
        mcp_tool = get_tool_by_name(tool_name)
        if mcp_tool is not None:
            request = request.override(tool=mcp_tool)
            return await handler(request)

        # 工具不存在（可能已被配置移除），返回友好错误消息
        return ToolMessage(
            content=f"工具 {tool_name} 已不可用，可能已被移除。请使用其他可用工具。",
            tool_call_id=request.tool_call["id"],
        )