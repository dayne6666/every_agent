"""
MCP 工具加载器

从配置文件读取 MCP Server 定义，通过 langchain-mcp-adapters 连接 MCP Server，
并将 MCP 工具转换为 LangChain StructuredTool 供 Agent 使用。
"""

import json
from pathlib import Path
from typing import Any

from common.log_utils import log as logger

# MCP 配置文件默认路径
MCP_CONFIG_PATH = Path(__file__).parent.parent / "config" / "mcp_servers.json"


def load_mcp_config(config_path: Path = MCP_CONFIG_PATH) -> dict[str, Any]:
    """
    读取 MCP 服务器配置文件。

    配置文件格式:
    {
        "mcpServers": {
            "server-name": {
                "transport": "stdio" | "sse" | "http" | "websocket",
                ... 其他连接参数取决于 transport 类型
            }
        },
        "toolNamePrefix": true  // 是否给工具名加 server 名称前缀
    }
    """
    if not config_path.exists():
        logger.warning(f"MCP 配置文件不存在: {config_path}，跳过 MCP 工具加载")
        return {"mcpServers": {}, "toolNamePrefix": True}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        logger.info(f"已加载 MCP 配置文件: {config_path}")
        return config
    except json.JSONDecodeError as e:
        logger.error(f"MCP 配置文件解析失败: {e}")
        return {"mcpServers": {}, "toolNamePrefix": True}


async def get_mcp_tools(config_path: Path = MCP_CONFIG_PATH) -> list[Any]:
    """
    从配置文件加载所有 MCP 工具，返回 LangChain StructuredTool 列表。

    每次工具调用会创建新的 MCP Session（无状态模式）。
    """
    config = load_mcp_config(config_path)
    servers = config.get("mcpServers", {})

    if not servers:
        logger.info("未配置任何 MCP Server，跳过 MCP 工具加载")
        return []

    use_prefix = config.get("toolNamePrefix", True)
    server_names = list(servers.keys())
    logger.info(f"发现 {len(server_names)} 个 MCP Server: {server_names}")

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        # 使用 langchain-mcp-adapters 0.3.0+ 的新特性：
        # handle_tool_errors=True（默认）会将 MCP 服务器错误返回给模型，而不是抛出异常
        # 这样当 MCP 服务器返回错误时，模型可以自我纠正，而不是导致整个 agent 运行失败
        client = MultiServerMCPClient(
            servers,
            tool_name_prefix=use_prefix,
            handle_tool_errors=True,  # 启用错误处理，将错误返回给模型
        )
        tools = await client.get_tools()
        logger.info(f"成功加载 {len(tools)} 个 MCP 工具: {[t.name for t in tools]}")
        return tools
    except Exception as e:
        logger.error(f"MCP 工具加载失败: {e}")
        return []