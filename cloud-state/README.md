# cloud-state

云端持久化目录（GitHub Actions 每轮运行后仅在内容变化时提交）：

- `state.json`：基线状态（init_done / 连续失败次数 / today+upcoming 双板块成功快照）
- `changes.jsonl`：变化记录（add / modify / delete）
- `notifications.jsonl`：微信通知记录
- `history/`：基线变化时的历史快照
- `runs.jsonl`：逐轮运行日志（gitignore，不提交）

该目录不包含任何 Secret。
