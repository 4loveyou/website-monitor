# Alpha123 今日空投监控

每小时自动检查 Alpha123「今日空投」，新增/修改通过 Server酱 推送微信；
删除仅记录不通知；无变化不通知。运行于 GitHub Actions（公开仓库免费 schedule），
零运行成本，不依赖用户电脑常开、不依赖 VPN。

本仓库不含任何 Secret；SendKey 通过 Actions Secret `SC_SENDKEY` 注入。

## 文件

- `website_monitor/`：监控核心（Python 标准库，零第三方依赖）
- `.github/workflows/monitor-hourly.yml`：每小时工作流
- `cloud-state/`：运行状态（基线/变化/通知记录，仅在变化时提交）

## 维护

代码权威来源在 AIOS 项目，不要直接在本仓库改业务代码；更新后重新同步并提交。
