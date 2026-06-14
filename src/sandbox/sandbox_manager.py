"""
沙箱管理器 - 基于 JSON 文件的持久化方案
避免重复创建沙箱，支持沙箱状态恢复和心跳保活
"""

import json
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from opensandbox import SandboxSync
from opensandbox.config import ConnectionConfigSync

from sandbox.opensandbox_opt import create_sandbox, connect_sandbox, verify_sandbox


class SandboxManager:
    """沙箱管理器 - 使用 JSON 文件持久化沙箱状态"""

    def __init__(
        self,
        config: ConnectionConfigSync,
        state_file: str = ".sandbox_state.json",
        heartbeat_interval: int = 240,  # 4分钟发一次心跳
    ):
        """
        初始化沙箱管理器

        Args:
            config: OpenSandbox 连接配置
            state_file: 状态文件路径
            heartbeat_interval: 心跳间隔（秒），默认 4 分钟
        """
        self.config = config
        self.state_file = Path(state_file)
        self.heartbeat_interval = heartbeat_interval
        self.state = self._load_state()
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_running = False
        self._sandbox: Optional[SandboxSync] = None

    def get_sandbox(self, image: Optional[str] = None) -> SandboxSync:
        """
        获取沙箱：优先复用旧沙箱，失败则创建新的

        Args:
            image: 创建新沙箱时使用的镜像（可选）

        Returns:
            SandboxSync 实例
        """
        # 1. 尝试恢复之前的沙箱
        saved_sandbox_id = self.state.get("sandbox_id")
        if saved_sandbox_id:
            print(f"[INFO] 尝试恢复沙箱: {saved_sandbox_id}")
            sandbox = connect_sandbox(saved_sandbox_id, self.config)
            if sandbox and verify_sandbox(sandbox):
                print(f"[INFO] ✅ 成功恢复沙箱: {saved_sandbox_id}")
                self._sandbox = sandbox
                self._update_last_used()
                self._start_heartbeat()
                return sandbox
            print(f"[WARNING] 沙箱不可用，将创建新的沙箱")

        # 2. 创建新沙箱
        print(f"[INFO] 创建新沙箱...")
        sandbox = create_sandbox(self.config, image)
        self._sandbox = sandbox

        # 3. 保存沙箱状态
        self._save_state(sandbox.id)

        # 4. 启动心跳保活
        self._start_heartbeat()

        return sandbox

    def get_sandbox_id(self) -> Optional[str]:
        """
        获取保存的沙箱 ID

        Returns:
            沙箱 ID，如果没有保存则返回 None
        """
        return self.state.get("sandbox_id")

    def _start_heartbeat(self):
        """启动心跳保活线程"""
        if self._heartbeat_running:
            return

        self._heartbeat_running = True
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="SandboxKeepAlive"
        )
        self._heartbeat_thread.start()
        print(f"[INFO] 💓 心跳保活已启动，间隔: {self.heartbeat_interval}秒")

    def _heartbeat_loop(self):
        """心跳循环"""
        while self._heartbeat_running and self._sandbox:
            try:
                # 发送心跳命令
                result = self._sandbox.commands.run("echo heartbeat")
                if result.exit_code == 0:
                    print(f"[KeepAlive] 💓 心跳成功 @ {time.strftime('%H:%M:%S')}")
                    # 更新最后使用时间
                    self._update_last_used()
                else:
                    print(f"[KeepAlive] ⚠️ 心跳失败，退出码: {result.exit_code}")
            except Exception as e:
                print(f"[KeepAlive] ❌ 心跳异常: {e}")

            # 等待下次心跳
            time.sleep(self.heartbeat_interval)

    def stop_heartbeat(self):
        """停止心跳保活"""
        self._heartbeat_running = False
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5)
        print("[INFO] 💓 心跳保活已停止")

    def cleanup(self):
        """清理资源"""
        self.stop_heartbeat()
        print("[INFO] 沙箱管理器已清理")

    def _save_state(self, sandbox_id: str):
        """保存沙箱状态到 JSON 文件"""
        self.state = {
            "sandbox_id": sandbox_id,
            "created_at": datetime.now().isoformat(),
            "last_used": datetime.now().isoformat(),
        }
        self._write_state()

    def _update_last_used(self):
        """更新最后使用时间"""
        if "sandbox_id" in self.state:
            self.state["last_used"] = datetime.now().isoformat()
            self._write_state()

    def _write_state(self):
        """写入状态文件"""
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ERROR] 保存沙箱状态失败: {e}")

    def _load_state(self) -> dict:
        """从 JSON 文件加载沙箱状态"""
        try:
            if self.state_file.exists():
                with open(self.state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                    print(f"[INFO] 📄 已加载沙箱状态: {state.get('sandbox_id', '无')}")
                    return state
        except Exception as e:
            print(f"[WARNING] 加载沙箱状态失败: {e}")
        return {}

    def clear_state(self):
        """清除保存的沙箱状态"""
        self.state = {}
        self._write_state()
        print("[INFO] 🗑️ 沙箱状态已清除")