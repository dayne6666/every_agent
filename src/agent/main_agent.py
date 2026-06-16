import asyncio

from deepagents import create_deep_agent

from agent.memory.prompts import get_default_system_prompt
from common.apollo_config import init_apollo, get_system_prompt
from common.config import llm_xiaomi, AGENTS_MD_FILENAME, SANDBOX_CONFIG, LOCAL_SKILLS_DIR, SANDBOX_SKILLS_ROOT, \
    LOCAL_AGENTS_MD
from sandbox.custom_opensandbox import OpenSandboxBackend
from sandbox.sandbox_manager import SandboxManager
from sandbox.opensandbox_opt import sync_skills_to_sandbox
from tools.my_tools import web_search, upload_to_qiniu
from agent.agent_state import sandbox_backend as _sb, sandbox_manager as _sm

sandbox_backend = _sb
sandbox_manager = _sm


async def crete():
    from agent import agent_state

    # 使用沙箱管理器获取沙箱（自动复用旧沙箱，失败则创建新的）
    agent_state.sandbox_manager = SandboxManager(
        config=SANDBOX_CONFIG,
        state_file=".sandbox_state.json",
        heartbeat_interval=240,
    )
    sandbox = agent_state.sandbox_manager.get_sandbox()

    # 创建OpenSandbox后端，用于文件上传、命令执行等操作
    agent_state.sandbox_backend = OpenSandboxBackend(sandbox=sandbox)
    # 本地技能目录
    local_skills_path = str(LOCAL_SKILLS_DIR)

    # 沙箱中的技能目录
    sandbox_skills_path = SANDBOX_SKILLS_ROOT

    # 智能同步技能到沙箱
    uploaded_count = sync_skills_to_sandbox(agent_state.sandbox_backend, local_skills_path, sandbox_skills_path)

    with open(str(LOCAL_AGENTS_MD), 'r', encoding='utf-8') as f:
        content = f.read()

    # 上传到沙箱
    result = agent_state.sandbox_backend.upload_files([(AGENTS_MD_FILENAME, content.encode("utf-8"))])

    if uploaded_count > 0:
        print(f"✅ 成功上传了 {uploaded_count} 个新技能到沙箱")
    else:
        print("✅ 所有技能已存在于沙箱中，无需上传")

    # 初始化 Apollo 配置中心
    init_apollo(agent_state.sandbox_backend)

    # 从 Apollo 获取系统提示词（降级到本地默认值）
    system_prompt = get_system_prompt()

    return create_deep_agent(  # create_agent
        model=llm_xiaomi,
        # memory=[AGENTS_MD_FILENAME],  # 由MemoryMiddleware加载, 主Agent的系统提示词
        tools=[web_search, upload_to_qiniu],
        skills=["/skills/main/"],
        backend=agent_state.sandbox_backend,
        system_prompt=system_prompt,
    )


main_agent = asyncio.run(crete())
