# 沙箱持久化管理

## 问题背景

每次启动 Agent 都会创建新的沙箱，导致：
- ❌ 启动时间长
- ❌ 资源浪费
- ❌ 沙箱状态丢失

## 解决方案

采用 **JSON 文件持久化 + 心跳保活** 的组合方案：
- ✅ 自动复用之前的沙箱
- ✅ 沙箱 ID 持久化到本地文件
- ✅ 心跳保活防止自动销毁
- ✅ 复用失败时自动创建新沙箱

## 架构设计

### 职责分离（单一职责原则）

```
┌─────────────────────────────────────────────────────┐
│                 main_agent.py                       │
│           （应用层，调用管理器）                      │
└─────────────────────┬───────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────┐
│            sandbox_manager.py                       │
│     （高层管理：复用、持久化、心跳）                 │
│     - get_sandbox()                                 │
│     - 状态持久化                                     │
│     - 心跳保活                                       │
└─────────────────────┬───────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────┐
│           opensandbox_opt.py                        │
│     （底层工具：创建、连接、验证）                   │
│     - create_sandbox()                              │
│     - connect_sandbox()                             │
│     - verify_sandbox()                              │
│     - sync_skills_to_sandbox()                      │
└─────────────────────────────────────────────────────┘
```

### 设计原则

1. **opensandbox_opt.py** - 底层工具函数
   - 职责：沙箱的基本操作（创建、连接、验证、同步）
   - 特点：无状态，可复用，不涉及业务逻辑

2. **sandbox_manager.py** - 高层管理逻辑
   - 职责：智能获取、状态持久化、心跳保活
   - 特点：有状态，包含业务逻辑

3. **main_agent.py** - 应用层
   - 职责：调用管理器，集成到 Agent
   - 特点：简单调用，不涉及底层细节

## 工作流程

```
启动 Agent
    ↓
读取 .sandbox_state.json
    ↓
尝试连接旧沙箱
    ├── 成功 → 验证可用性 → 启动心跳保活 → 继续
    └── 失败 → 创建新沙箱 → 保存 ID → 启动心跳保活
```

## 文件说明

### 1. `src/sandbox/sandbox_manager.py`（高层管理）
沙箱管理器核心模块，提供以下功能：
- 沙箱智能获取（自动复用）
- 状态持久化（JSON 文件）
- 心跳保活
- 状态清理

### 2. `src/sandbox/opensandbox_opt.py`（底层工具）
底层工具函数：
- `create_sandbox()` - 创建新沙箱
- `connect_sandbox()` - 连接现有沙箱
- `verify_sandbox()` - 验证沙箱可用性
- `sync_skills_to_sandbox()` - 同步技能到沙箱

### 3. `.sandbox_state.json`（自动生成）
状态文件，存储：
```json
{
  "sandbox_id": "a284ce2d-a82d-4554-817c-5fbd40ee0cab",
  "created_at": "2024-01-15T10:30:00",
  "last_used": "2024-01-15T14:20:00"
}
```

## 使用方法

### 高层使用（推荐）

```python
from sandbox.sandbox_manager import SandboxManager
from sandbox.opensandbox_opt import config

# 创建管理器
manager = SandboxManager(
    config=config,
    state_file=".sandbox_state.json",
    heartbeat_interval=240,  # 4 分钟心跳间隔
)

# 获取沙箱（自动复用或创建）
sandbox = manager.get_sandbox()
```

### 底层使用（高级场景）

```python
from sandbox.opensandbox_opt import create_sandbox, connect_sandbox, verify_sandbox, config

# 直接创建
sandbox = create_sandbox(config)

# 或连接现有沙箱
sandbox = connect_sandbox("sandbox-id", config)

# 验证沙箱
is_valid = verify_sandbox(sandbox)
```

### 测试脚本

```bash
# 运行测试
python test_sandbox_manager.py
```

## 配置说明

### 心跳间隔

```python
heartbeat_interval=240  # 4 分钟（秒）
```

**为什么是 4 分钟？**
- 沙箱空闲超时是 30 分钟
- 心跳间隔应小于超时时间的一半
- 4 分钟既不会太频繁，又能有效保活

### 状态文件路径

```python
state_file=".sandbox_state.json"  # 项目根目录
```

## 手动管理沙箱

### 查看当前沙箱状态

```bash
cat .sandbox_state.json
```

### 清除沙箱状态

```python
manager = SandboxManager(config=config)
manager.clear_state()
```

或者直接删除文件：

```bash
rm .sandbox_state.json
```

## 常见问题

### Q1: 沙箱被销毁了怎么办？

A: 代码会自动检测并创建新沙箱，无需手动干预。

### Q2: 如何手动指定沙箱 ID？

A: 修改 `main_agent.py` 中的 `get_sandbox()` 调用：

```python
# 方式 1: 使用管理器（推荐）
sandbox = manager.get_sandbox()  # 自动从状态文件读取

# 方式 2: 使用底层函数（不推荐）
from sandbox.opensandbox_opt import connect_sandbox
sandbox = connect_sandbox("your-sandbox-id", config)
```

### Q3: 心跳保活会消耗资源吗？

A: 会消耗少量资源（每 4 分钟执行一次 `echo` 命令），但相比重新创建沙箱的开销，可以忽略不计。

### Q4: 如何调整空闲超时时间？

A: 修改 `opensandbox_opt.py` 中的 `timeout` 参数：

```python
sandbox = SandboxSync.create(
    image,
    timeout=timedelta(hours=2),  # 改为 2 小时
    ...
)
```

## 测试

### 测试 1: 状态文件读写

```bash
python test_sandbox_manager.py
```

### 测试 2: 验证沙箱复用

1. 首次运行：创建新沙箱，保存 ID
2. 再次运行：自动复用之前的沙箱
3. 查看日志确认复用成功

## 性能对比

| 操作 | 首次运行 | 后续运行 |
|------|----------|----------|
| 无持久化 | ~30 秒 | ~30 秒 |
| 有持久化 | ~30 秒 | ~2 秒 |

**结论：** 使用持久化后，后续运行速度提升约 15 倍！

## 注意事项

1. **不要将 `.sandbox_state.json` 提交到 Git**
   - 已添加到 `.gitignore`
   - 每个开发环境应该有自己的沙箱

2. **沙箱镜像版本更新**
   - 如果更新了镜像版本，建议清除状态文件
   - 这样会自动创建使用新镜像的沙箱

3. **网络环境变化**
   - 如果切换了网络环境，旧沙箱可能无法连接
   - 代码会自动创建新沙箱，无需手动处理

## 相关文件

- `src/sandbox/sandbox_manager.py` - 高层管理（复用、持久化、心跳）
- `src/sandbox/opensandbox_opt.py` - 底层工具（创建、连接、验证）
- `src/sandbox/custom_opensandbox.py` - OpenSandbox 后端封装
- `test_sandbox_manager.py` - 测试脚本
