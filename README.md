# 9.网站信息监控

长期运行的网站信息监控系统（PRD v1.1 + 2026-09-06 用户扩展）：每小时自动检查 Alpha123「今日空投」与「空投预告」两个板块，识别新增与修改并通过微信通知用户；删除只记录不通知。正式运行于免费云端，不依赖用户电脑常开、不依赖用户 VPN、不产生额外费用。

## 状态

- 版本：v0.4.0（今日空投 + 空投预告双板块；云端已上线）
- Project ID：`website-monitor`
- 2026-09-06：PRD v1.1 确认；V1 开发（34 测试）；云端上线成功；
  用户扩展「空投预告」（38 测试通过）

## 功能（V1，按 PRD v1.1）

- 每小时自动检查 https://alpha123.uk/zh/index.html 的「今日空投」+「空投预告」
- 两板块独立基线；预告项进入当日 = 今日新增通知（每日提醒）
- 从旧版升级：首次发送「Alpha123监控扩展｜空投预告 N 项」完整数据，不误报新增
- 首次运行：建立基线并微信发送当前完整数据（标注「Alpha123监控初始化」）
- 变化检测：新增/修改 → 微信通知（尽量展示前后值）；删除 → 记录不通知；无变化 → 不通知
- 多变化合并为一条微信；连续 3 次获取失败微信提醒；恢复后发送恢复通知
- 微信通知：V1 Server酱（Turbo / SC3 自动适配）；通知接口可替换，不写死
- 数据保存：当前/历史快照、变化记录、运行/错误日志、通知记录

## 快速开始（本地开发/验证）

环境：Python 3.9+（本项目用 Codex 内置 Python 3.12 开发），无需安装任何第三方包。

```powershell
# 运行测试（34 项）
$env:PYTHONPATH = "D:\AIOS\03-PROJECTS\9.网站信息监控\03-src"
python -m unittest discover -s 04-tests -p "test_*.py"

# 抓取一次真实数据（排查用）
python -m website_monitor fetch-sample

# 本地 dry-run 一轮（不真实推送微信；状态写到 05-data/state）
python -m website_monitor run --data-dir 05-data/state --dry-notify

# 真实通知一轮：需先配置 SendKey（见下方 Secret 说明）
python -m website_monitor run --data-dir 05-data/state
```

说明：`run` 即“一轮检查”；每小时调度由云端（GitHub Actions）负责，没有长期常驻进程。

## 免费云端（正式运行）

采用 GitHub Actions（公开仓库免费 schedule），详见
[deploy/README.md](deploy/README.md)：

1. 新建公开仓库并克隆
2. 执行 `07-scripts/sync-to-github.ps1 -Target <仓库路径>` 同步代码
3. 在仓库 Settings 配置 Actions Secret：`SC_SENDKEY`
4. 手动触发一次工作流验证初始化消息，之后每小时自动运行

> 私有免费仓库不会触发 schedule（GitHub 免费个人账户限制），因此 V1 使用公开仓库；
> 仓库内不含任何 Secret 或私人数据。

## Secret 安全（SendKey）

- SendKey 属 Secret，禁止写入代码 / README / Git / 日志；
- 本地运行：用 AIOS Security Manager 登记并注入，例如：

  ```powershell
  sm secret add sc-serverchan-sendkey --name "Server酱 SendKey" --owner website-monitor --permission READ_ONLY
  sm grant add website-monitor sc-serverchan-sendkey --permission READ_ONLY
  sm run --project website-monitor --secret sc-serverchan-sendkey --var SC_SENDKEY -- python -m website_monitor run --data-dir 05-data/state
  ```

- 云端运行：SendKey 存于 GitHub Actions 加密 Secret（`SC_SENDKEY`），由工作流注入
  环境变量；GitHub Secrets 与 sm 均为受控 Secret Store，
  `07-SECURITY/REGISTRY/SECRETS-REGISTRY.md` 只登记元数据。

## 文档

- [PRD](01-PRD/PRD.md)（v1.1，已确认）
- [云端部署](deploy/README.md)（GitHub Actions）
- [项目身份证](00-meta/PROJECT.md)
- [项目特殊规则](00-meta/AGENTS.md)
- [交接记录](00-meta/HANDOFF.md)
- [更新记录](00-meta/CHANGELOG.md)
- [决策记录](11-knowledge/decisions/)

## 目录

```text
00-meta/  项目身份证 / 交接 / 变更记录
01-PRD/   需求与方案（PRD v1.1，已确认）
02-research/  调研记录（含 Alpha123 API 实测）
03-src/   website_monitor 核心包（纯标准库）
04-tests/ 单元/场景测试（34 项）
05-data/  运行数据（状态/历史/记录，不入 Git）
06-config/ 配置（config.yaml 不入 Git；example 为脱敏模板）
07-scripts/ 运行/同步脚本
08-launcher/ 启动器（待开发）
09-output/  产物（预留）
10-logs/   运行日志（不入 Git）
11-knowledge/ 决策 / 经验沉淀
12-vendor/ 第三方代码登记（只读）
99-archive/ 归档
deploy/    免费云端物料（workflow / cloud-state / 部署说明）
```

## 技术栈

- Python 3 纯标准库（urllib / json / 文件存储），零第三方依赖
- 云端：GitHub Actions（schedule + 公开仓库免费额度）+ 仓库内 cloud-state 状态
- 通知：可替换 Notifier 接口；V1 = Server酱（Turbo / SC3 自动适配）

## 环境重建

- 无第三方依赖（requirements.txt 保持空占位）
