import asyncio

from deepagents import create_deep_agent

from common.config import llm_xiaomi, AGENTS_MD_FILENAME, SANDBOX_CONFIG, LOCAL_SKILLS_DIR, SANDBOX_SKILLS_ROOT, \
    LOCAL_AGENTS_MD
from sandbox.custom_opensandbox import OpenSandboxBackend
from sandbox.opensandbox_opt import get_or_create_sandbox, sync_skills_to_sandbox
from tools.my_tools import web_search, upload_to_qiniu

sandbox_backend = None


async def crete():
    # 获取或创建OpenSandbox沙箱（优先连接已有沙箱，失败则新建）
    # 可通过 sandbox_id 参数指定已运行的沙箱，避免重复创建
    sandbox = get_or_create_sandbox(SANDBOX_CONFIG, sandbox_id="a284ce2d-a82d-4554-817c-5fbd40ee0cab")

    # 创建OpenSandbox后端，用于文件上传、命令执行等操作
    sandbox_backend = OpenSandboxBackend(sandbox=sandbox)
    # 本地技能目录
    local_skills_path = str(LOCAL_SKILLS_DIR)

    # 沙箱中的技能目录
    sandbox_skills_path = SANDBOX_SKILLS_ROOT

    # 智能同步技能到沙箱
    uploaded_count = sync_skills_to_sandbox(sandbox_backend, local_skills_path, sandbox_skills_path)

    # with open(str(LOCAL_AGENTS_MD), 'r', encoding='utf-8') as f:
    #     content = f.read()
    #
    # # 上传到沙箱
    # result = sandbox_backend.upload_files([(AGENTS_MD_FILENAME, content.encode("utf-8"))])

    if uploaded_count > 0:
        print(f"✅ 成功上传了 {uploaded_count} 个新技能到沙箱")
    else:
        print("✅ 所有技能已存在于沙箱中，无需上传")

    return create_deep_agent(  # create_agent
        model=llm_xiaomi,
        memory=[AGENTS_MD_FILENAME],  # 由MemoryMiddleware加载, 主Agent的系统提示词
        tools=[web_search, upload_to_qiniu],
        skills=["/skills/main/"],
        backend=sandbox_backend,
    )


main_agent = asyncio.run(crete())
