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

# 全局变量
_apollo_client = None
_sandbox_backend = None
_last_apollo_prompt = None  # 上一次成功获取的 Apollo 配置


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
    """
    重新加载配置（由 Apollo SDK 轮询触发）

    当 Apollo 检测到配置变更时，自动调用此函数
    SDK 内部会自动更新内存缓存，我们只需打印日志
    """
    if _apollo_client is None:
        return

    try:
        version = _apollo_client.get_value("prompt_version")
        print(f"[Apollo] 🔄 配置已更新，版本: {version}")
    except Exception as e:
        print(f"[Apollo] ❌ 加载配置失败: {e}")


def get_system_prompt() -> str:
    """
    获取系统提示词

    优先级：Apollo SDK 缓存 > 本地 Apollo 缓存 > 本地默认值

    降级策略：
    1. 优先从 Apollo SDK 获取（内存缓存，毫秒级）
    2. 如果 SDK 不可用或报错，使用上一次成功获取的 Apollo 配置
    3. 如果都没有，降级到本地默认值

    这样确保 Apollo 临时故障时，Agent 行为保持稳定，不会突然变化。

    Returns:
        系统提示词字符串
    """
    global _last_apollo_prompt

    # 1. 优先从 Apollo SDK 获取
    if _apollo_client:
        try:
            value = _apollo_client.get_value("system_prompt")
            if value:
                # 成功获取，更新本地缓存
                _last_apollo_prompt = value
                return value
            else:
                print("[Apollo] ⚠️ Apollo 返回的 system_prompt 为空")
        except Exception as e:
            print(f"[Apollo] ⚠️ 获取 system_prompt 失败: {e}，使用上一次的配置")

    # 2. 降级到上一次成功获取的 Apollo 配置
    if _last_apollo_prompt:
        print("[Apollo] 🔄 使用上一次成功的 Apollo 配置")
        return _last_apollo_prompt

    # 3. 最终降级到本地默认值
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
        "hot_reload": True,
        "cycle_time": 30,
    }