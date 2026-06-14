# Every Agent

基于 [LangGraph](https://langchain-ai.github.io/langgraph/) 构建的智能 Agent 框架，集成 OpenSandbox 沙箱环境，支持代码执行、网页搜索、文件上传等能力。

## 项目结构

```
every_agent/
├── src/
│   ├── agent/               # Agent 核心
│   │   └── main_agent.py    # 主 Agent 入口
│   ├── common/              # 公共模块
│   │   ├── config.py        # 全局配置
│   │   ├── env_utils.py     # 环境变量工具
│   │   └── log_utils.py     # 日志工具
│   ├── sandbox/             # 沙箱管理
│   │   ├── sandbox_manager.py    # 沙箱管理器（持久化 + 心跳保活）
│   │   ├── opensandbox_opt.py    # 沙箱底层工具（创建、连接、验证）
│   │   └── custom_opensandbox.py # OpenSandbox 后端封装
│   ├── skills/              # 技能定义
│   │   └── main/SKILL.md
│   └── tools/               # 工具定义
│       └── my_tools.py      # 搜索、上传等工具
├── .env.example             # 环境变量示例
├── langgraph.json           # LangGraph 配置
├── pyproject.toml           # 项目配置
└── requirements.txt         # 依赖列表
```

## 快速开始

### 1. 环境要求

- Python >= 3.10

### 2. 安装依赖

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入实际的 API Key
```

### 4. 启动 Agent

```bash
# 使用 LangGraph CLI 启动
langgraph dev
```

## 核心特性

### 沙箱管理

采用 **JSON 文件持久化 + 心跳保活** 方案：

- **自动复用**：启动时自动复用之前的沙箱，避免重复创建
- **状态持久化**：沙箱 ID 保存在 `.sandbox_state.json`
- **心跳保活**：每 4 分钟发送心跳，防止沙箱因空闲被销毁
- **自动降级**：复用失败时自动创建新沙箱

```
启动 → 读取状态 → 复用沙箱 → 心跳保活
                → 复用失败 → 创建新沙箱 → 保存状态 → 心跳保活
```

### 工具

| 工具 | 说明 |
|------|------|
| `web_search` | 基于智谱 AI 的网页搜索 |
| `upload_to_qiniu` | 上传文件到七牛云 OSS |

### 职责分离架构

```
main_agent.py          → 应用层（调用管理器）
sandbox_manager.py     → 高层管理（复用、持久化、心跳）
opensandbox_opt.py     → 底层工具（创建、连接、验证）
custom_opensandbox.py  → 协议适配（ExecuteResponse 等）
```

## 配置说明

| 环境变量 | 说明 |
|----------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key |
| `XIAOMI_API_KEY` | 小米 API Key |
| `ARK_API_KEY` | 字节 Ark API Key |
| `ZHIPU_API_KEY` | 智谱 AI API Key |
| `QINIU_ACCESS_KEY` | 七牛云 Access Key |
| `QINIU_SECRET_KEY` | 七牛云 Secret Key |
| `QINIU_BUCKET_NAME` | 七牛云存储空间名 |
| `QINIU_BUCKET_DOMAIN` | 七牛云域名 |

## 测试沙箱管理器

```bash
python test_sandbox_manager.py
```

## 常见问题

### 沙箱被销毁了怎么办？
代码会自动检测并创建新沙箱，无需手动干预。

### 如何清除沙箱状态？
```bash
rm .sandbox_state.json
# 或在代码中调用
manager.clear_state()
```

### 如何调整沙箱空闲超时？
修改 `src/sandbox/opensandbox_opt.py` 中 `create_sandbox` 的 `timeout` 参数。

## License

MIT
