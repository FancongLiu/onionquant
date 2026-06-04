# Token 优化研究报告

> 研究人：Token 优化研究员
> 日期：2026-05-17
> 状态：初版完成

---

## 一、CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC 调研

### 1.1 作用

设置 `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` 后，Claude Code 会禁用所有非必要的对外网络请求，包括：

| 禁用项 | 说明 |
|--------|------|
| **Statsig 指标采集** | 操作延迟、可靠性、使用模式等遥测（不含代码/路径） |
| **Sentry 错误报告** | Claude Code 本身的运行时错误日志上报 |
| **Bug 报告 (`/bug` 命令)** | 禁止向 Anthropic 发送对话历史 |
| **Grove 配置拉取** | 禁用启动时获取远程配置（可节省 10-12 秒启动延迟） |

### 1.2 对 Token 消耗的影响：双刃剑

| 维度 | 影响 | 方向 |
|------|------|------|
| **启动速度** | 跳过 Grove 远程配置拉取，启动快 10-12 秒 | 正面 |
| **隐私合规** | 无遥测数据离开本地 | 正面 |
| **Prompt Cache TTL** | 关键副作用！对于订阅用户，Statsig 控制 1 小时缓存 TTL 的特性开关；禁用 Statsig 后回退到 5 分钟 TTL | **负面** |
| **缓存命中率** | 5 分钟 vs 1 小时 → 缓存更容易过期 → 更多缓存写入 → **Token 增加** | **负面** |

### 1.3 结论与建议

| 用户类型 | 建议 | 理由 |
|----------|------|------|
| **Anthropic 订阅用户** | **不启用** | 损失 1 小时缓存 TTL → 缓存命中率下降 → Token 消耗反而增加 |
| **第三方 API 用户** | **启用** | 无缓存 TTL 损失，且能避免启动延迟和上报错误 |
| **隐私要求极高** | **启用** | 牺牲一点缓存效率换取完全无数据外泄 |

**本项目判断：** 如果是 Anthropic 直连订阅用户，**不建议启用**。Token 优化的首要目标是减少消耗，而启用此变量可能因缓存失效导致更多消耗。

---

## 二、当前配置审计

### 2.1 `.claudeignore` 现状

```gitignore
# 防止 Claude Code 读取 Copilot 的工作区内容（避免作弊）
benchmark_copilot/
benchmark2_copilot/
benchmark3_copilot/
```

**问题：**
- 仅排除了 benchmark 目录
- 没有排除 `.venv/`、`__pycache__/`、`.git/` 等大量无关文件
- 没有排除 `*.pyc`、`*.log` 等模式
- 缺少本地 `.claudeignore` 钩子支持（当前 `.claude/settings.json` 未配置 PreToolUse hook）

### 2.2 `.gitignore` 现状

```gitignore
__pycache__/
*.py[cod]
.venv/
venv/
env/
.claude/
```

**评价：** 基础文件已覆盖，但缺少 `node_modules/`、`build/`、`dist/` 等常见模式。不过本项目无 node_modules，暂可接受。

### 2.3 `.claude/settings.json` 现状

```json
{
  "permissions": {
    "allow": ["Read", "Glob", "Grep", ...]
  }
}
```

**问题：** 完全没有任何 token 优化相关的 env 配置。上下文窗口使用默认的 100 万 token，思考预算无限制。

### 2.4 CLAUDE.md 现状

**不存在。** 目前本项目没有 CLAUDE.md 文件。这既好又坏：
- 好：不消耗任何固定的每轮 token（CLAUDE.md 每轮加载）
- 坏：Claude 没有项目上下文，可能导致探索性消耗更多 token

---

## 三、Token 优化策略详解

### 3.1 上下文窗口控制（效果最大）

| 配置 | 默认值 | 推荐值 | 节省幅度 |
|------|--------|--------|----------|
| 上下文窗口 | 1,000,000 tokens | 200,000 tokens | ~5x 每轮减少 |
| 自动压缩阈值 | ~83% (830K) | 80% (160K) | 更早触发压缩 |
| 思考预算 | 31,999 tokens | 10,000 tokens | ~70% |

**原理：** Input tokens 占总消耗的 70-90%。限制上下文窗口是单点改动中效果最大的。每次交换时模型只需处理 20 万 token 而非 100 万。

### 3.2 模型分层策略

| 模型 | 适用场景 | 成本对比 |
|------|----------|----------|
| **Haiku** | 子代理探索、文件搜索、简单查询 | 最低 |
| **Sonnet** | 日常编码、代码审查、测试编写 | 中等（默认推荐） |
| **Opus** | 复杂架构设计、多步推理 | 最高 |

**策略：**
- 子代理使用 Haiku：`CLAUDE_CODE_SUBAGENT_MODEL=haiku`
- 日常使用 Sonnet，复杂场景手动切换到 Opus：`/model opus`

### 3.3 手动压缩与清理

| 命令 | 作用 | Token 节省 |
|------|------|------------|
| `/compact` | 不带参数触发免费本地压缩 | 30-50%（长会话） |
| `/compact keep [指令]` | 带提示词的有损压缩（付费但效果更好） | 50-70% |
| `/clear` | 完全清空上下文，重新开始 | 单次 100% |

**最佳实践：** 在每次里程碑完成后手动运行 `/compact`，在切换任务时使用 `/clear`。

### 3.4 子代理隔离

子代理通过 Task 工具运行在**独立上下文窗口**中：
- 文件搜索、日志转储、多步推理在隔离窗口中完成
- 只有摘要返回主会话
- 主会话上下文不会被无关输出污染

### 3.5 `.claudeignore` 最佳实践

应排除的高 Token 消耗目录：

| 目录/模式 | 建议原因 | 预计节省 |
|-----------|----------|----------|
| `.venv/` | 虚拟环境包含大量无关 Python 文件 | 节省扫描和误读 |
| `__pycache__/` | Python 字节码缓存 | 减少文件数量 |
| `.git/` | Git 内部对象 | 避免 Claude 分析 .git 目录 |
| `*.pyc` | 编译文件 | 减少误匹配 |
| `*.log` | 日志文件 | 避免加载大日志 |
| `*_copilot/` | 已包含 benchmark 目录 | 已配置 |

### 3.6 精准提示

模糊的提示会触发昂贵的探索性操作：

| 不推荐的写法 | 推荐的写法 |
|-------------|-----------|
| "看看 auth 代码有什么问题" | "对比 `src/auth.py:30-90` 和 `api/login.py:10-60` 找出不匹配" |

### 3.7 第三方文件索引工具

| 工具 | 技术栈 | Token 节省 | 特点 |
|------|--------|-----------|------|
| **Code Context Engine** | sqlite-vec + tree-sitter | 94% | AST 索引 + 混合检索 |
| **CCTO** | ONNX + SQLite | 60-80% | 配置最简单 |
| **Lucid** | TF-IDF/Qdrant | 30-70% | 代码骨架剪枝 |
| **Claude Context (Zilliz)** | Milvus | 39-63% | Merkle 树变化检测 |

这些工具将"读取全部文件"改为"索引 → 语义搜索 → 按需读取"模式，大幅减少每轮加载到上下文的 token。

---

## 四、Claude Code 缓存机制调研

### 4.1 Prompt Caching 工作原理

Anthropic 的 prompt caching 基于**逐字节前缀匹配**：
- API 从请求开头缓存在每个 `cache_control` 断点之前
- 前缀中任何位置的更改都会使之后的所有缓存失效
- 命中缓存后，输入 token 仅按 10% 计费

### 4.2 缓存层级布局

| 层级 | 缓存范围 | 内容 |
|------|----------|------|
| **系统提示 + 工具定义** | 全局（所有用户共享） | 身份、系统规则、24+ 工具定义 |
| **CLAUDE.md** | 项目内共享 | 项目规则（注入为 `<system-reminder>`） |
| **会话上下文** | 会话内共享 | 记忆规则、环境信息 |
| **对话消息** | 每轮独立 | 动态用户/助手消息 |

### 4.3 缓存的五大失效陷阱

| 陷阱 | 后果 | 解决方案 |
|------|------|----------|
| **1. 中途编辑 CLAUDE.md** | 从此位置起全部缓存失效，历史消息重新计价 | 规划好再写入；如需修改使用 `/new` 新会话 |
| **2. 前缀中包含动态内容** | 每个请求有不同前缀，零缓存命中 | 时间戳、随机 ID 放在最后一条用户消息中 |
| **3. 中途切换模型** | 模型切换会重建整个缓存（模型专有） | 使用子代理分工而非切换主模型 |
| **4. 不当的 `/compact`** | 使用不同的 system prompt 导致前缀分叉 | 确保 compaction 共享与父进程相同的前缀 |
| **5. 中途增减工具** | 工具集合变化导致前缀不一致 | 保持工具集合不变 |

### 4.4 缓存 TTL 配置

| 变量 | 作用 |
|------|------|
| `ENABLE_PROMPT_CACHING_1H=1` | 启用 1 小时缓存 TTL（默认） |
| `FORCE_PROMPT_CACHING_5M=1` | 强制使用 5 分钟 TTL |

1 小时缓存的收费模式：
- 写入：基础价格的 2.0x
- 读取：基础价格的 0.1x
- **盈亏平衡点：约 1.12 次命中**

### 4.5 `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` 的缓存副作用

根据社区分析，此变量会**禁用 Statsig 特性开关**，而 Statsig 控制 1 小时缓存 TTL 的启用。禁用后回退到 5 分钟 TTL，对于订阅制用户会导致：
- 缓存更频繁过期
- 更多缓存写入（2.0x 单价）
- 更少缓存读取
- **总体 token 成本上升**

---

## 五、立即执行：配置优化

### 5.1 `.claude/settings.json` 优化

```json
{
  "permissions": {
    "allow": [
      "Read",
      "Glob",
      "Grep",
      "WebSearch",
      "WebFetch",
      "Agent",
      "Skill",
      "TodoWrite",
      "AskUserQuestion",
      "EnterPlanMode",
      "ExitPlanMode",
      "NotebookEdit",
      "Bash(*)",
      "Edit(*)",
      "Write(*)"
    ]
  },
  "env": {
    "CLAUDE_CODE_DISABLE_1M_CONTEXT": "1",
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "200000",
    "MAX_THINKING_TOKENS": "10000",
    "CLAUDE_CODE_SUBAGENT_MODEL": "haiku"
  }
}
```

| 变量 | 值 | 说明 | 预估节省 |
|------|-----|------|---------|
| `CLAUDE_CODE_DISABLE_1M_CONTEXT` | `1` | 禁用 100 万上下文，启用 20 万 | **~5x 每轮减少** |
| `CLAUDE_CODE_AUTO_COMPACT_WINDOW` | `200000` | 达到 20 万时自动压缩 | **~50% 长会话** |
| `MAX_THINKING_TOKENS` | `10000` | 限制思考预算（默认 31999） | **~70% 思考消耗** |
| `CLAUDE_CODE_SUBAGENT_MODEL` | `haiku` | 子代理使用最便宜的模型 | **~80% 子代理成本** |

**不添加 `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` 的理由：** 对于直连 Anthropic 的订阅用户，此变量会禁用 Statsig 特性开关 → 丢失 1 小时缓存 TTL → 缓存命中率下降 → 实际 token 消耗上升。

### 5.2 `.claudeignore` 优化

```gitignore
# 防止 Claude Code 读取 Copilot 的工作区内容（避免作弊）
benchmark_copilot/
benchmark2_copilot/
benchmark3_copilot/

# Python 缓存和虚拟环境
__pycache__/
*.pyc
.venv/
venv/
env/

# Git 内部文件
.git/

# 日志文件
*.log

# 操作系统文件
.DS_Store
Thumbs.db
```

### 5.3 CLAUDE.md 创建建议

当前项目没有 CLAUDE.md。虽然这省去了固定加载消耗，但会导致：
- Claude 每次需要探索来理解项目结构
- 无法通过项目规则指导 Claude 的行为

**建议：** 创建一个 2K tokens 以内的精简版 CLAUDE.md，包含：
- 项目目录结构（一句话说明）
- 关键文件路径
- 常用命令
- 编码规范（一句话）

预计净节省：探索性 token 减少 30-50%。

---

## 六、效果预估

| 优化项 | 单项节省 | 叠加大致范围 |
|--------|---------|-------------|
| 上下文窗口 100 万 → 20 万 | ~5x 每轮 | 基础 |
| 自动压缩提前触发 | ~50% 长会话 | 叠加 |
| 思考预算 31999 → 10000 | ~70% 思考 token | 叠加 |
| 子代理使用 Haiku | ~80% 子代理 | 条件触发 |
| 精准提示 | 30-60% 探索性消耗 | 行为依赖 |
| 手动 `/compact` | 30-50% 每轮 | 行为依赖 |
| 文件索引工具 | 60-94% | 第三方工具 |
| **综合预估** | **70-90%** | **取决于使用模式** |

---

## 七、持续优化建议

1. **每周检查** `/cost` 了解 token 消耗趋势
2. **关注** Anthropic 官方博客和 GitHub Issues 了解最新优化技术
3. **评估** 第三方文件索引工具（Code Context Engine 等）在项目中的实际效果
4. **监控缓存命中率** — 官方称应像监控系统 uptime 一样对待
5. **当 CLAUDE.md 内容增长时** 定期审查并精简

---

## 八、参考资料

- [Anthropic 官方博客：Lessons from building Claude Code - Prompt caching is everything](https://claude.com/blog/lessons-from-building-claude-code-prompt-caching-is-everything)
- [KDnuggets: 7 Practical Ways to Reduce Claude Code Token Usage](https://www.kdnuggets.com/7-practical-ways-to-reduce-claude-code-token-usage)
- [everything-claude-code Token Optimization Guide](https://github.com/affaan-m/everything-claude-code/blob/main/docs/token-optimization.md)
- [GitHub Issue #19105: Lazy-Loading Architecture for Token Optimization](https://github.com/anthropics/claude-code/issues/19105)
- [GitHub Issue #1304: Need for dedicated .claudeignore file](https://github.com/anthropics/claude-code/issues/1304)
- [Claude Code settings.json 最佳实践](https://github.com/shanraisshan/claude-code-best-practice/blob/main/best-practice/claude-settings.md)
- [Code Context Engine: AST indexing + hybrid search](https://github.com/elara-labs/code-context-engine)
