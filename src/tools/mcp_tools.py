"""
MCP 工具加载器

从 Apollo 配置中心读取 MCP Server 定义，通过 langchain-mcp-adapters 连接 MCP Server，
并将 MCP 工具转换为 LangChain StructuredTool 供 Agent 使用。
"""

from typing import Any

from common.log_utils import log as logger


async def get_mcp_tools() -> list[Any]:
    """
    从 Apollo 获取 MCP 配置，连接所有 MCP Server，返回 LangChain StructuredTool 列表。

    每次工具调用会创建新的 MCP Session（无状态模式）。
    """
    from common.apollo_config import get_mcp_servers_config

    config = get_mcp_servers_config()
    servers = config.get("mcpServers", {})

    if not servers:
        logger.info("未配置任何 MCP Server，跳过 MCP 工具加载")
        return []

    use_prefix = config.get("toolNamePrefix", True)
    server_names = list(servers.keys())
    logger.info(f"发现 {len(server_names)} 个 MCP Server: {server_names}")

    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(servers, tool_name_prefix=use_prefix)
    tools = await client.get_tools()
    logger.info(f"成功加载 {len(tools)} 个 MCP 工具: {[t.name for t in tools]}")
    return tools