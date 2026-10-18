# 来源、许可与复用边界

| 来源 | 固定版本 / 许可 | 复用内容 | 本项目新增 |
| --- | --- | --- | --- |
| [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent/tree/ccc695635094d7615373db267b77f894d978b1a0) | `ccc695635094d7615373db267b77f894d978b1a0` / MIT | 完整模型运行时、Desktop/Gateway、原生子任务、插件接口、PM | `travel_extensions` 内的业务适配与配置；核心源码未修改 |
| [官方 Langfuse 插件](https://github.com/NousResearch/hermes-official-plugins/tree/c2a95963c442f3f23e4bc6fe0da898e1dd1fb63d/langfuse) | `c2a95963c442f3f23e4bc6fe0da898e1dd1fb63d`、2.0.0 / MIT | 官方 SDK 4.15.2、客户端、脱敏、生命周期观测 | 独立版本锁定补丁补旅行审查事件；原文件和版权保留在安装目录，非未经修改的官方插件 |
| [nashsu/llm_wiki](https://github.com/nashsu/llm_wiki/tree/48fd970e206a02a6d2028d1dbfc41b7a0345bf0b) | `48fd970e206a02a6d2028d1dbfc41b7a0345bf0b` / GPLv3 | 参考 Raw / Wiki / Schema / purpose 文件组织规范 | 独立 Python 实现 SQLite 原话、事实、冲突与规则，不复制其 GPL 实现，不运行其应用 |
| ReportLab | 4.5.1 / BSD | PDF 排版与字体嵌入 | 由已审查方案直接生成中文 PDF |
| 豆包搜索接口 | 远程第三方服务，非本仓库授权内容 | `open.feedcoopapi.com/search_api/web_search` | 原生 WebSearchProvider 的 HTTP 适配；不分发 API 凭据或额度 |
| Sol 中转接口 | 远程第三方服务，非本仓库授权内容 | `ccgoai.club/v1` | 默认配置，不背书其计费或底层模型身份 |

完整上游保留各自 LICENSE / NOTICE。本项目 MIT 许可不改变第三方服务条款、网页内容许可或系统字体许可。微软雅黑来自使用者 Windows，仓库不打包字体。图片由本项目排版，产品界面为实际验收截图；合成数据和真实输出均有明确标注。

LLM Wiki 在 2026-10-18 核查为 20,732 Star、v0.6.12；这仅是当时来源记录，不当作实时维护状态。[详细复用依据](05-Wiki偏好.md)。
