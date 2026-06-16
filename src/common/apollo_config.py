"""
Apollo 配置中心客户端

功能：
- 初始化 Apollo 客户端
- 内置轮询机制自动检测配置变更（热更新）
- 提供 get_system_prompt() 接口
- 优雅降级：Apollo 不可用时回退到本地文件

使用 pyapollo-zenkilan SDK:
- https://github.com/OuterCloud/pyapollo
- 支持热更新：默认每 30 秒轮询一次
- 支持故障容灾：自动切换可用节点
"""

import os
from typing import Optional

from common.env_utils import APOLLO_META_SERVER, APOLLO_APP_ID

# 全局缓存
_system_prompt_cache: Optional[str] = None
_apollo_client = None
_sandbox_backend = None


def init_apollo(sandbox_backend=None):
    """
    初始化 Apollo 客户端

    Args:
        sandbox_backend: 沙箱后端，用于更新 AGENTS.md（可选）
    """
    global _apollo_client, _sandbox_backend

    _sandbox_backend = sandbox_backend

    try:
        from pyapollo.client import ApolloClient

        # 创建 Apollo 客户端（内置轮询热更新，默认 30 秒刷新一次）
        _apollo_client = ApolloClient(
            meta_server_address=APOLLO_META_SERVER,
            app_id=APOLLO_APP_ID,
            # cycle_time=30,  # 可选：配置刷新周期（秒），默认 30
        )

        # 初始化缓存
        _reload_config()

        print(f"[Apollo] 已初始化，AppID: {APOLLO_APP_ID}")
        print(f"[Apollo] 热更新已启用，轮询周期: 30 秒")
        return _apollo_client

    except ImportError:
        print("[Apollo] pyapollo-zenkilan 未安装，请运行: pip install pyapollo-zenkilan")
        print("[Apollo] 将使用本地默认配置")
        return None
    except Exception as e:
        print(f"[Apollo] 初始化失败: {e}")
        print("[Apollo] 将使用本地默认配置")
        return None


def _reload_config():
    """重新加载配置"""
    global _system_prompt_cache

    if _apollo_client is None:
        return

    try:
        _system_prompt_cache = _apollo_client.get_value("system_prompt")
        version = _apollo_client.get_value("prompt_version")
        print(f"[Apollo] 已加载配置，版本: {version}")
    except Exception as e:
        print(f"[Apollo] 加载配置失败: {e}")


def get_system_prompt() -> str:
    """
    获取系统提示词

    优先级：Apollo 配置 > 本地默认值

    Returns:
        系统提示词字符串
    """
    global _system_prompt_cache

    print("[Apollo] 正在获取 system_prompt...")

    # 如果 Apollo 客户端已初始化，直接从客户端获取（自动获取最新值）
    if _apollo_client:
        try:
            value = _apollo_client.get_value("system_prompt")
            if value:
                _system_prompt_cache = value
                # 打印前 100 个字符作为日志
                preview = value[:100].replace('\n', ' ')
                print(f"[Apollo] ✅ 成功从 Apollo 获取 system_prompt")
                print(f"[Apollo] 内容预览: {preview}...")
                return value
            else:
                print("[Apollo] ⚠️ Apollo 返回的 system_prompt 为空")
        except Exception as e:
            print(f"[Apollo] ❌ 获取 system_prompt 失败: {e}")
    else:
        print("[Apollo] ⚠️ Apollo 客户端未初始化")

    # 如果缓存有值，直接返回
    if _system_prompt_cache:
        print("[Apollo] 使用缓存的 system_prompt")
        return _system_prompt_cache

    # 降级到本地默认值
    print("[Apollo] ⬇️ 降级使用本地默认 system_prompt")
    from agent.memory.prompts import get_default_system_prompt
    return get_default_system_prompt()


def refresh_config():
    """
    手动刷新配置

    当需要立即获取最新配置时调用（正常情况下轮询会自动刷新）
    """
    print("[Apollo] 正在手动刷新配置...")
    if _apollo_client:
        try:
            _apollo_client.update_config()
            _reload_config()
            print("[Apollo] ✅ 配置已手动刷新")
        except Exception as e:
            print(f"[Apollo] ❌ 手动刷新失败: {e}")
    else:
        print("[Apollo] ⚠️ Apollo 客户端未初始化，无法刷新")


def get_apollo_status() -> dict:
    """
    获取 Apollo 连接状态

    Returns:
        状态字典
    """
    return {
        "initialized": _apollo_client is not None,
        "app_id": APOLLO_APP_ID,
        "meta_server": APOLLO_META_SERVER,
        "cache_valid": _system_prompt_cache is not None,
        "hot_reload": True,
        "cycle_time": 30,
    }