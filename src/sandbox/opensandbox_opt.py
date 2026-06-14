import hashlib
import os
from datetime import timedelta
from typing import Optional

import httpx
from opensandbox import SandboxSync
from opensandbox.config import ConnectionConfigSync


# 默认沙箱镜像
DEFAULT_SANDBOX_IMAGE = "sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/code-interpreter:v1.0.2"


def create_sandbox(config: ConnectionConfigSync, image: Optional[str] = None) -> SandboxSync:
    """
    创建新沙箱

    Args:
        config: ConnectionConfigSync 配置
        image: 沙箱镜像（可选，默认使用 DEFAULT_SANDBOX_IMAGE）

    Returns:
        SandboxSync 实例
    """
    if not image:
        image = DEFAULT_SANDBOX_IMAGE

    print(f"[INFO] 正在创建新沙箱，使用镜像: {image}")
    sandbox = SandboxSync.create(
        image,
        entrypoint=["/opt/opensandbox/code-interpreter.sh"],
        env={"PYTHON_VERSION": "3.11"},
        resource={"memory": "4Gi"},
        timeout=timedelta(minutes=30),
        connection_config=config,
    )
    print(f"[INFO] 成功创建新沙箱，ID: {sandbox.id}")
    return sandbox


def connect_sandbox(sandbox_id: str, config: ConnectionConfigSync) -> Optional[SandboxSync]:
    """
    连接到现有沙箱

    Args:
        sandbox_id: 沙箱 ID
        config: ConnectionConfigSync 配置

    Returns:
        SandboxSync 实例，连接失败返回 None
    """
    try:
        print(f"[INFO] 正在连接到沙箱: {sandbox_id}")
        sandbox = SandboxSync.connect(sandbox_id, connection_config=config)
        print(f"[INFO] 成功连接到沙箱: {sandbox_id}")
        return sandbox
    except Exception as e:
        print(f"[WARNING] 连接沙箱 {sandbox_id} 失败: {e}")
        return None


def verify_sandbox(sandbox: SandboxSync) -> bool:
    """
    验证沙箱是否可用

    Args:
        sandbox: SandboxSync 实例

    Returns:
        bool: 沙箱是否可用
    """
    try:
        result = sandbox.commands.run("echo test")
        return result.exit_code == 0
    except Exception:
        return False


def _file_md5(filepath: str) -> str:
    """计算文件的 MD5 哈希值"""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _calc_local_skill_hash(local_skills_path: str, skill_name: str) -> str:
    """
    计算本地技能目录的综合哈希值（所有文件内容 MD5 + 相对路径拼接）。
    任何文件内容或数量变化都会导致哈希值不同。
    """
    skill_dir = os.path.join(local_skills_path, skill_name)
    file_hashes = []
    for root, dirs, files in os.walk(skill_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]  # 跳过隐藏目录
        for fname in sorted(files):
            if fname.startswith('.'):
                continue
            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, skill_dir).replace(os.sep, '/')
            file_hashes.append(f"{rel_path}:{_file_md5(full_path)}")
    combined = "|".join(file_hashes)
    return hashlib.md5(combined.encode()).hexdigest() if combined else ""


def _calc_sandbox_skill_hash(backend, sandbox_skills_path: str, skill_name: str) -> str:
    """
    计算沙箱中技能目录的综合哈希值。
    在沙箱中执行脚本，对每个文件计算 MD5 后汇总。
    """
    skill_dir = f"{sandbox_skills_path}/{skill_name}"
    script = (
        f"find {skill_dir} -type f ! -name '.*' | sort | "
        f"xargs -I{{}} sh -c 'echo $(basename {{}}):$(md5sum {{}} | cut -d\" \" -f1)'"
    )
    result = backend.execute(script)
    output = _extract_output(result)
    if not output:
        return ""
    return hashlib.md5(output.strip().encode()).hexdigest()


def _extract_output(result) -> str:
    """从执行结果中提取输出文本"""
    if hasattr(result, 'stdout') and result.stdout:
        return result.stdout
    if hasattr(result, 'output') and result.output:
        return result.output
    if hasattr(result, 'result') and result.result:
        return result.result
    if isinstance(result, str):
        return result
    return str(result) if result else ""


def _upload_skill(backend, local_skills_path: str, sandbox_skills_path: str, skill_name: str):
    """上传单个技能目录到沙箱"""
    skill_local_path = os.path.join(local_skills_path, skill_name)
    skill_sandbox_path = f"{sandbox_skills_path}/{skill_name}"

    # 先删除沙箱中旧版本
    backend.execute(f"rm -rf {skill_sandbox_path}")

    for root, dirs, files in os.walk(skill_local_path):
        rel_path = os.path.relpath(root, skill_local_path)
        if rel_path == ".":
            sandbox_dir = skill_sandbox_path
        else:
            sandbox_dir = f"{skill_sandbox_path}/{rel_path.replace(os.sep, '/')}"

        if rel_path != ".":
            backend.execute(f"mkdir -p {sandbox_dir}")

        for file in files:
            local_file = os.path.join(root, file)
            if rel_path == ".":
                sandbox_file = f"{skill_sandbox_path}/{file}"
            else:
                sandbox_file = f"{skill_sandbox_path}/{rel_path.replace(os.sep, '/')}/{file}"

            try:
                with open(local_file, 'rb') as f:
                    content = f.read()
                backend.upload_files([(sandbox_file, content)])
                print(f"  ✓ {file}")
            except Exception as e:
                print(f"  ✗ {file}: {e}")


def sync_skills_to_sandbox(backend, local_skills_path, sandbox_skills_path):
    """
    基于内容哈希的智能同步：比较本地和沙箱的文件内容，只更新有变化的技能。

    对比逻辑：
    1. 计算本地每个技能的文件内容哈希
    2. 计算沙箱中每个技能的文件内容哈希
    3. 哈希不同 → 重新上传
    4. 本地有沙箱没有 → 上传
    5. 沙箱有本地没有 → 删除

    Args:
        backend: OpenSandbox 后端实例
        local_skills_path: 本地技能目录路径
        sandbox_skills_path: 沙箱中技能目录路径

    Returns:
        int: 上传（更新）的技能数量
    """
    print(f"[SYNC] 开始同步技能...")
    print(f"  本地: {local_skills_path}")
    print(f"  沙箱: {sandbox_skills_path}")

    # 1. 确保沙箱技能目录存在
    backend.execute(f"mkdir -p {sandbox_skills_path}")

    # 2. 获取本地技能列表及哈希
    local_skills = {}
    if os.path.exists(local_skills_path):
        for item in os.listdir(local_skills_path):
            item_path = os.path.join(local_skills_path, item)
            if os.path.isdir(item_path) and not item.startswith('.'):
                local_skills[item] = _calc_local_skill_hash(local_skills_path, item)

    # 3. 获取沙箱技能列表及哈希
    result = backend.execute(f"ls -1 {sandbox_skills_path}/ 2>/dev/null || true")
    output = _extract_output(result)
    sandbox_skill_names = set()
    if output:
        for line in output.strip().split('\n'):
            name = line.strip().rstrip('/')
            if name and not name.startswith('.'):
                sandbox_skill_names.add(name)

    sandbox_hashes = {}
    for name in sandbox_skill_names:
        sandbox_hashes[name] = _calc_sandbox_skill_hash(backend, sandbox_skills_path, name)

    # 4. 对比并同步
    uploaded = 0
    skipped = 0
    deleted = 0

    all_skills = set(local_skills.keys()) | sandbox_skill_names

    for skill_name in all_skills:
        local_hash = local_skills.get(skill_name)
        sandbox_hash = sandbox_hashes.get(skill_name)

        if local_hash is None:
            # 本地已删除，沙箱中保留 → 删除沙箱中的
            print(f"[SYNC] 🗑️  删除（本地已移除）: {skill_name}")
            backend.execute(f"rm -rf {sandbox_skills_path}/{skill_name}")
            deleted += 1

        elif sandbox_hash is None:
            # 沙箱中不存在 → 新增上传
            print(f"[SYNC] ➕ 新增: {skill_name}")
            _upload_skill(backend, local_skills_path, sandbox_skills_path, skill_name)
            uploaded += 1

        elif local_hash != sandbox_hash:
            # 内容有变化 → 更新
            print(f"[SYNC] 🔄 更新: {skill_name}")
            _upload_skill(backend, local_skills_path, sandbox_skills_path, skill_name)
            uploaded += 1

        else:
            # 内容相同 → 跳过
            skipped += 1

    # 5. 汇总
    total = uploaded + skipped + deleted
    if total == 0:
        print(f"[SYNC] 没有发现任何技能")
    else:
        print(f"[SYNC] 同步完成: 上传/更新 {uploaded} / 跳过 {skipped} / 删除 {deleted}")

    return uploaded


# 配置连接
config = ConnectionConfigSync(
    domain="http://192.168.10.251:9090",
    use_server_proxy=True,
    request_timeout=timedelta(seconds=60),
    transport=httpx.HTTPTransport(limits=httpx.Limits(max_connections=20)),
)