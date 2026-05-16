量化公司（实验性）目录

结构说明：
- org.json: 公司元数据与部门列表
- agents/: 各类 agent 的实现骨架
- scripts/: 研究与爬取脚本

目标：搭建一个可扩展的“量化公司”框架，支持多个部门、子Agent和自动化研究流程。

自动审批 agent 提交
--------------------

本仓库包含一个示例 GitHub Actions 工作流，用于自动审批由可信 agent 创建的 PR：

- 工作流路径：`.github/workflows/auto_approve_agents.yml`
- 判定规则：默认通过 PR 的作者（由 `ALLOWED_AGENT_AUTHORS` secret 指定，逗号分隔）或 PR 是否带有 `agent` 标签来决定是否自动审批。
- 必需的仓库 Secrets（在 GitHub 仓库 Settings -> Secrets 中添加）：
	- `AGENT_BOT_PAT`：用于在工作流中执行审批操作的机器用户 PAT（需要 `repo` 权限）。
	- `ALLOWED_AGENT_AUTHORS`（可选）：允许自动审批的 agent 用户列表，例如 `agent-bot,glm-agent`。
	- `AGENT_AUTO_MERGE`（可选）：设置为 `true` 可在审批后自动合并（谨慎启用）。
	- `AGENT_MERGE_METHOD`（可选）：合并方式，`merge`、`squash` 或 `rebase`，默认 `merge`。

注意事项：
- 若仓库启用了严格的分支保护（require review 等），请确保机器用户有权提交审批或仓库管理员在保护规则中允许工作流合并（通常需要仓库管理员配合）。
- 出于安全考虑，建议仅对带特定标签或来自白名单作者的 PR 进行自动审批。

使用示例：
1. 在 GitHub 仓库中添加上面列出的 Secrets。
2. 确保 agent 在创建 PR 时使用受信任的作者或添加 `agent` 标签。
3. 当 PR 被创建或更新时，工作流会检测并（如果符合条件）自动提交一次 Approve Review；如果开启 `AGENT_AUTO_MERGE`，会随后合并 PR。

如果你希望我把审查规则调整为只按作者或只按标签，请告诉我具体偏好，我会修改工作流文件。

本地自动保留（自动提交）
------------------------

如果你的需求是在本地编辑时自动“保留”修改而不想每次手动确认，可以使用仓库自带的简单脚本来实现自动提交：

- 脚本路径：`scripts/auto_commit_agent.py`。
- 功能：轮询检测仓库变动，自动执行 `git add -A` + `git commit`（可选 `git push`）。
- 快速使用：在项目根目录运行（建议在独立终端长期运行）：

```powershell
python scripts/auto_commit_agent.py --interval 5 --message "Auto-commit by agent" --push
```

- 可通过环境变量配置：
	- `AGENT_AUTO_COMMIT_AUTHOR`：提交作者（例如 "Agent Bot <bot@example.com>"）。
	- `AGENT_AUTO_COMMIT_MESSAGE`：提交信息。
	- `AGENT_AUTO_COMMIT_INTERVAL`：轮询间隔（秒）。

安全与使用建议：
- 该脚本会立即提交所有未暂存的更改，慎用在大型/不稳定修改上；建议只在你信任的工作流或临时保存场景下开启。
- 若你仅需要自动保存编辑到磁盘，请在 VS Code 中启用 `Files: Auto Save` 设置，而非自动提交到版本库。
- 我可以调整脚本以只提交特定路径、只在满足某些条件时提交（例如特定作者或文件扩展名），如果需要告诉我你的规则。
