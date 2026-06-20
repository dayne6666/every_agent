"""
MCP 工具注册表

管理动态 MCP 工具的生命周期：
- 维护当前可用的 MCP 工具列表（可变）
- 线程安全，支持并发访问
"""

import hashlib
import json
import threading

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from common.apollo_config import get_mcp_servers_config
from common.log_utils import log as logger

# 当前可用的 MCP 工具（线程安全访问）
_tools: dict[str, BaseTool] = {}
_lock = threading.Lock()

# 当前配置的哈希值，用于检测变更
_config_hash: str = ""


def get_tools() -> list[BaseTool]:
    """获取当前所有 MCP 工具列表"""
    with _lock:
        return list(_tools.values())


def get_tool_by_name(name: str) -> BaseTool | None:
    """根据名称获取 MCP 工具实例"""
    with _lock:
        return _tools.get(name)


def get_tool_names() -> list[str]:
    """获取当前所有 MCP 工具名称"""
    with _lock:
        return list(_tools.keys())


def _compute_config_hash(config: dict) -> str:
    """计算配置的哈希值，用于变更检测"""
    raw = json.dumps(config, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(raw.encode()).hexdigest()


async def load_tools() -> list[BaseTool]:
    """
    从 Apollo 加载 MCP 工具（启动时调用）。

    Returns:
        加载到的工具列表
    """
    global _tools, _config_hash

    config = get_mcp_servers_config()
    servers = config.get("mcpServers", {})

    if not servers:
        logger.info("未配置任何 MCP Server，跳过 MCP 工具加载")
        return []

    use_prefix = config.get("toolNamePrefix", True)
    server_names = list(servers.keys())
    logger.info(f"发现 {len(server_names)} 个 MCP Server: {server_names}")

    client = MultiServerMCPClient(servers, tool_name_prefix=use_prefix)
    tools_list = await client.get_tools()

    # 更新注册表
    with _lock:
        _tools.clear()
        for tool in tools_list:
            _tools[tool.name] = tool
        _config_hash = _compute_config_hash(config)

    logger.info(f"成功加载 {len(tools_list)} 个 MCP 工具: {list(_tools.keys())}")
    return tools_list