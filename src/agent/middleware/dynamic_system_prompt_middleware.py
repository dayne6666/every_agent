"""
系统提示词动态 Middleware

功能：
- 每次对话时从缓存获取 system_prompt（毫秒级响应）
- 替换（而非追加）system message，确保身份清晰
- 实现系统提示词的热更新，无需重启服务
- 支持降级到本地默认配置

缓存机制：
1. 首次调用时从 Apollo 获取配置并缓存
2. 后续调用直接返回缓存值（无网络开销）
3. Apollo SDK 每 30 秒自动轮询，检测到变更时更新缓存
"""

import logging
from typing import Any, Callable, Awaitable, Optional

from langchain_core.messages import SystemMessage, ContentBlock
from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ContextT,
    ModelRequest,
    ModelResponse,
    ResponseT,
)

from common.apollo_config import get_system_prompt

logger = logging.getLogger(__name__)


def replace_system_message(
    system_message: SystemMessage | None,
    new_content: str,
) -> SystemMessage:
    """
    替换 system message 的内容（而非追加）

    Args:
        system_message: 原有的 system message
        new_content: 新的 system prompt 内容

    Returns:
        替换后的 SystemMessage
    """
    # 直接用新内容创建新的 SystemMessage
    new_content_blocks: list[ContentBlock] = [{"type": "text", "text": new_content}]
    return SystemMessage(content_blocks=new_content_blocks)


class DynamicSystemPromptMiddleware(AgentMiddleware[AgentState, ContextT, ResponseT]):
    """
    系统提示词动态 Middleware

    每次调用 model 前，从缓存获取 system_prompt 并**替换**到 system message 中。
    实现系统提示词的热更新，无需重启服务。

    ⚠️ 重要：这是**替换**操作，不是追加！
    - Apollo 的提示词会完全替换原有的 system prompt
    - 确保身份切换时不会出现矛盾的指令
    - 例如：从"客服助手"切换到"写作助手"时，旧的身份会被完全替换

    缓存策略：
    - 首次调用：从 Apollo 获取配置并缓存
    - 后续调用：直接返回缓存值（毫秒级响应）
    - 配置变更：Apollo SDK 轮询检测到变更后自动更新缓存

    使用场景：
    - 需要动态调整 Agent 行为时，无需重启服务
    - A/B 测试不同的系统提示词
    - 运维人员可以通过 Apollo Portal 实时优化 Agent 表现

    工作流程：
    1. 用户发送消息
    2. Middleware 被调用
    3. 从缓存获取 system_prompt（毫秒级）
    4. **替换** system message（不是追加）
    5. 调用 LLM 生成回复
    """

    def __init__(self, enabled: bool = True):
        """
        初始化系统提示词动态 Middleware

        Args:
            enabled: 是否启用，默认为 True
        """
        self._enabled = enabled
        self._last_prompt: Optional[str] = None

    def modify_request(self, request: ModelRequest[ContextT]) -> ModelRequest[ContextT]:
        """
        修改 model request，**替换**最新的 system_prompt

        Args:
            request: 原始的 model request

        Returns:
            修改后的 model request
        """
        if not self._enabled:
            return request

        try:
            # 从缓存获取 system_prompt（毫秒级响应）
            apollo_prompt = get_system_prompt()

            # 如果获取到了 Apollo 配置，**替换**到 system message
            if apollo_prompt:
                # 记录日志（仅当配置变更时）
                if apollo_prompt != self._last_prompt:
                    logger.info("[DynamicSystemPrompt] 检测到 system_prompt 变更，已替换")
                    self._last_prompt = apollo_prompt

                # ⚠️ **替换** system message（不是追加）
                new_system_message = replace_system_message(
                    request.system_message,
                    apollo_prompt
                )
                return request.override(system_message=new_system_message)

        except Exception as e:
            logger.error(f"[DynamicSystemPrompt] 获取配置失败: {e}")

        return request

    def wrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], ModelResponse[ResponseT]],
    ) -> ModelResponse[ResponseT]:
        """
        包装 model call，在调用前注入配置

        Args:
            request: model request
            handler: 处理函数

        Returns:
            model response
        """
        modified_request = self.modify_request(request)
        return handler(modified_request)

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        """
        异步包装 model call，在调用前注入配置

        Args:
            request: model request
            handler: 异步处理函数

        Returns:
            model response
        """
        modified_request = self.modify_request(request)
        return await handler(modified_request)