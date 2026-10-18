# 官方 Langfuse：两个缺口的修复与真实复验

最新补充：[杭州两日复杂任务](09-复杂任务展示.md)已完成真实 Desktop、模型、搜索和本地观测验收：18 次模型请求、10 次搜索、4 条 trace、46 条观测，全部闭合且无 ERROR；提供同次运行截图、两页 PDF 和原网页核对。下文早期小案例及合成测试保留各自测量边界。

当前采用官方 `langfuse` 2.0.0，固定 [c2a95963…](https://github.com/NousResearch/hermes-official-plugins/tree/c2a95963c442f3f23e4bc6fe0da898e1dd1fb63d/langfuse)，SDK 4.15.2。客户端、脱敏、队列和导出仍由官方实现承担；本项目新增版本锁定的兼容补丁，不维护第二套观测系统。

## 从问题到修复

| 问题 | 根因证据 | 最小修复 |
| --- | --- | --- |
| 子搜索成功却显示 ERROR | `agent/tool_executor.py` 抑制父工具内层的 `post_tool_call`，原生子任务继承此上下文，成功结果未闭合工具 span | 在 [research.py](../../travel_extensions/travel/research.py) 的子任务 `launch` 外用现成 `suppress_post_tool_call_hook(False)`，离开上下文恢复父工具原状态 |
| 9 次模型调用只记录 8 次 | 旅行审查走 `pre/post_auxiliary_call`，固定版官方插件没有订阅 | [patch_langfuse.py](../../travel_extensions/observability/patch_langfuse.py) 只补 `travel_review` 事件，复用官方 generation、usage、脱敏与错误处理 |
| 补记审查可能误关主 trace | 官方普通模型结束处理会在无工具回答后结束回合 | 新增 `finish_turn` 开关，审查结束只闭合自己的 generation，不结束父回合 |

辅助请求以 `aux:travel_review:<api_request_id>` 区分普通模型调用和每次重试。审查异常仅记录错误类型，不记录可能携带凭据的原始异常；错误不提前关闭主任务。子搜索恢复正常的原生回调，避免通过额外回调重复补发。

`model_tools.suppress_post_tool_call_hook` 是已存在的上游接口，但不是长期稳定的插件 API；因此与 Hermes 固定基线绑定。升级必须重新验证，不能只更新版本号。

## 真实入库对照

同一条合成旅行需求、官方隐藏 Desktop/Gateway、真实父子 Agent 和本地 Langfuse 4.38.0。模型/搜索响应固定，观测服务真实；不是付费模型质量对比。

| 指标 | 修复前 | 修复后 |
| --- | ---: | ---: |
| 实际模型请求 | 9 | 9 |
| 入库 generation | 8 | **9** |
| 观测记录总数 | 17 | **18** |
| 子搜索工具状态 | ERROR：没有收到结果 | **DEFAULT：正常结束，输出保留** |
| 错误观测 | 1 | **0** |
| 合成输入 / 输出 token 总和 | 160 / 160 | **180 / 180** |
| Markdown / PDF | 各 1 份 | **各 1 份** |

[修复前回执](data/langfuse-live-20261018.json) · [修复后回执](data/langfuse-fixed-20261018.json) · [修复后桌面](images/desktop-travel-v4.png)。回执只导出类型、名称、状态、关联、时间与用量，不包含原始对话、公私钥或全量 metadata。

补丁后官方 142 项相关测试通过；原来仅断言旧 hook 集合的 1 项不再适用，由本项目新增 hook 注册与行为测试覆盖。另测审查成功/失败、请求 ID 隔离、不提前关闭父 trace、补丁幂等/回滚/拒绝覆盖本地修改；父子真实集成断言成功搜索只产生一次结束事件。默认测试不调用真实模型或搜索。

## 安装与回滚

先准备自己的本地 Langfuse 服务。旅行功能不依赖此服务。仓库根目录：

```powershell
pwsh.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ./travel_extensions/setup.ps1 -WithLangfuse
```

只在当前旅行 profile `.env` 配置 `HERMES_LANGFUSE_BASE_URL`（默认 `http://localhost:15501`）、`HERMES_LANGFUSE_PUBLIC_KEY`、`HERMES_LANGFUSE_SECRET_KEY`；保持 `HERMES_LANGFUSE_CAPTURE=sanitized`。无凭据时插件不启用发送；不要填写无权发送数据的远程地址。服务自身的部署参考 [Langfuse 官方自托管说明](https://langfuse.com/self-hosting)。

安装脚本通过官方 CLI 的 `--ref` 固定提交，沿用官方 PM 安装 SDK。已有插件则不重新下载。兼容补丁校验原 `__init__.py` 与 manifest 的 SHA-256，原文件分别保存为 `__init__.py.travel-original`、`plugin.yaml.travel-original`。重复执行不会重复添加 hook，版本或本地内容不匹配会拒绝覆盖。**安装目录是官方插件加本项目补丁，不应称为未经修改的官方插件。**

升级前关闭使用这个 profile 的进程。在已激活应用环境中回滚：

```powershell
python -m travel_extensions.observability.patch_langfuse --plugin .hermes-runtime/profile/plugins/langfuse --restore
```

回滚会恢复原版及其已知观测缺口。再次运行 setup 会重新应用补丁。不要删除原文件备份后强行绕过 hash 校验。

## 复现真实入库检查

设置 `TRAVEL_LANGFUSE_PROFILE` 为已配置本地凭据并安装补丁的 profile，`TRAVEL_TEST_PYTHON` 为 PM 应用解释器，`TRAVEL_SCREENSHOT_VERSION` 为未使用的新数字：

```powershell
node --experimental-strip-types travel_extensions/verification/desktop-travel.ts
python -m travel_extensions.verification.langfuse_receipt --env-file .hermes-runtime/profile/.env --trace-id <主trace> --trace-id <子trace> --output .hermes-runtime/新回执.json
```

未设置 profile 时桌面验收不发送观测。回执脚本只允许 loopback 服务并拒绝覆盖旧文件。Langfuse v4 的 `events_only` 模式使用 `/api/public/v2/observations`，旧 traces API 返回不支持，不代表上报失败。

## 仍需理解的边界

- 主子 Agent 沿用官方两条 trace，通过 `Subagent: leaf` 的子 session 关联；未把官方实现改造成统一执行树。
- 只补当前旅行审查；标题、视觉、其他辅助服务不在此次完整性声明中。
- 所有 token 都是该次 fixture 提供的合成 usage，用于核对“不丢调用”，不是模型性能或费用评测。中转真实单价未知，不能把估算费用当实扣。
- 官方插件无持久化离线发送队列。服务不可用时不阻塞回答，但可能丢失记录；当前测试不证明生产高可用。
- 2026-10-18 本机 Docker 通过同时备份重建 `Docker/run` 与 `docker-secrets-engine` 恢复，Engine 29.6.1 和 Langfuse 健康接口验证通过；不是针对所有 Docker 故障的永久修复。
