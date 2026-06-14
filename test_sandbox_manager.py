"""
沙箱管理器测试脚本
用于验证 JSON 文件持久化功能
"""

import sys
import os
import json
from pathlib import Path

# 添加 src 到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from sandbox.sandbox_manager import SandboxManager
from sandbox.opensandbox_opt import config


def test_state_file():
    """测试状态文件的读写"""
    state_file = ".sandbox_state.json"

    # 清理旧的状态文件
    if Path(state_file).exists():
        Path(state_file).unlink()
        print("✅ 已清理旧的状态文件")

    # 创建管理器
    manager = SandboxManager(
        config=config,
        state_file=state_file,
    )

    # 测试保存状态
    print("\n📝 测试保存沙箱 ID...")
    manager._save_state("test-sandbox-id-12345")
    print(f"   保存的沙箱 ID: {manager.state.get('sandbox_id')}")

    # 验证文件是否创建
    if Path(state_file).exists():
        print("✅ 状态文件已创建")
        with open(state_file, "r") as f:
            content = json.load(f)
            print(f"   文件内容: {json.dumps(content, indent=2)}")
    else:
        print("❌ 状态文件未创建")
        return False

    # 测试读取状态
    print("\n📖 测试读取沙箱状态...")
    manager2 = SandboxManager(
        config=config,
        state_file=state_file,
    )
    saved_id = manager2.get_sandbox_id()
    print(f"   读取到的沙箱 ID: {saved_id}")

    if saved_id == "test-sandbox-id-12345":
        print("✅ 状态读写测试通过")
    else:
        print("❌ 状态读写测试失败")
        return False

    # 测试清除状态
    print("\n🗑️ 测试清除沙箱状态...")
    manager2.clear_state()
    saved_id = manager2.get_sandbox_id()
    print(f"   清除后的沙箱 ID: {saved_id}")

    if saved_id is None:
        print("✅ 状态清除测试通过")
    else:
        print("❌ 状态清除测试失败")
        return False

    return True


def test_get_sandbox():
    """测试获取沙箱（需要网络连接）"""
    print("\n🔧 测试获取沙箱...")
    print("   (这将尝试连接或创建沙箱，需要网络)")

    manager = SandboxManager(
        config=config,
        state_file=".sandbox_state.json",
        heartbeat_interval=10,  # 测试时使用较短的间隔
    )

    try:
        sandbox = manager.get_sandbox()
        print(f"✅ 成功获取沙箱，ID: {sandbox.id}")

        # 停止心跳
        manager.stop_heartbeat()
        print("✅ 心跳已停止")

        return True
    except Exception as e:
        print(f"❌ 获取沙箱失败: {e}")
        return False


def test_low_level_functions():
    """测试底层工具函数"""
    print("\n🔧 测试底层工具函数...")

    from sandbox.opensandbox_opt import create_sandbox, connect_sandbox, verify_sandbox

    # 测试创建沙箱
    print("\n📝 测试创建沙箱...")
    try:
        sandbox = create_sandbox(config)
        print(f"✅ 成功创建沙箱: {sandbox.id}")

        # 测试验证沙箱
        print("\n📝 测试验证沙箱...")
        is_valid = verify_sandbox(sandbox)
        if is_valid:
            print("✅ 沙箱验证通过")
        else:
            print("❌ 沙箱验证失败")
            return False

        # 测试连接沙箱
        print("\n📝 测试连接沙箱...")
        connected_sandbox = connect_sandbox(sandbox.id, config)
        if connected_sandbox:
            print(f"✅ 成功连接沙箱: {connected_sandbox.id}")
        else:
            print("❌ 连接沙箱失败")
            return False

        return True
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def main():
    print("=" * 60)
    print("🧪 沙箱管理器测试")
    print("=" * 60)

    # 运行状态文件测试
    print("\n" + "=" * 60)
    print("📋 测试 1: 状态文件读写")
    print("=" * 60)
    if not test_state_file():
        print("\n❌ 状态文件测试失败，跳过后续测试")
        return

    # 询问是否运行网络测试
    print("\n" + "=" * 60)
    print("📋 测试 2: 获取沙箱（需要网络）")
    print("=" * 60)
    response = input("是否运行网络测试？(y/n): ").strip().lower()

    if response == "y":
        if test_get_sandbox():
            print("\n" + "=" * 60)
            print("🎉 所有测试通过！")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("❌ 网络测试失败")
            print("=" * 60)
    else:
        print("\n⏭️ 跳过网络测试")
        print("\n" + "=" * 60)
        print("🎉 状态文件测试通过！")
        print("=" * 60)


if __name__ == "__main__":
    main()
