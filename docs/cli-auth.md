# CLI 登录与长期会话

状态：Identity-only 认证已配对发布；剩余生产验收见 [roadmap](roadmap.md)

2026-10-09 范围澄清：本文描述远程 API 凭据。本地 Slurm/Linux/Lustre 查询使用
当前 Unix 用户的原生权限，不因整合进 CLI 就需要浏览器登录。用户设备或专有隔离
VM 上的 Agent 使用本人/委托 OAuth 授权调用 Portal，不依赖 Pilot 会话。
默认计算账户管理 API 与独立写 scope 已配套发布。2026-10-11 已在独立 Linux
容器中完成普通用户实际切换、恢复、新站点回执和原生 Slurm 核对，以及重放、
旧值冲突和独立授权撤销；日常会话重新刷新后仍可读取、不能写入。其他
业务管理继续按领域配对。现有 compute/billing/storage
只读 scope 不能据此增权，当前 CLI shell-enabled 规则也不是所有业务操作的通用前提。

## 用户体验

登录节点不要求用户在每次 SSH 会话中输入密码、复制 Bearer 或设置环境
变量。首次使用时，在登录节点执行：

```bash
sai auth login
```

命令显示 SAI Identity 的浏览器地址和一次性设备码。用户在已有浏览器
登录态中完成登录/MFA 并批准设备，命令自动完成登录。之后普通命令直接
使用本机的设备会话：

```bash
sai jobs list --scope self --limit 1
sai auth status
sai auth logout
```

`sai auth status --format table` 简洁显示控制台确认的本人认证状态、
首次补认证截止时间和认证入口，设备会话详情保留在默认 JSON 输出中。
它不显示令牌，也不在本地推算权限；受限账号
仍可查询自己的恢复状态，但不能借此查询作业。没有设备授权时仍需先运行
`sai auth login`。

如果 SSH 窗口需要先退出，可用 `sai auth login --no-wait` 发起授权，回来
后执行 `sai auth login --resume`。待确认的 device code 只写入权限为
`0700/0600` 的用户凭据缓存，过期后失效；它不会写入 shell history、TOML
或日志。

## 按操作申请权限

候选功能：`sai auth login --for account set-default` 为指定操作及其结果查询
申请权限；`--for invitations` 覆盖该命令组。权限取自现有命令声明，不增加另一份
权限目录。可加 `--no-wait`，本人在浏览器确认后只需 `sai auth login --resume`。
登录不会执行业务操作，也不修改连接配置或共享 profile。

现有会话在新授权等待、拒绝或权限不足时继续可用；成功后同一连接下的普通命令
使用更新后的登录。已有明确记录的授权范围会保留，新增权限仍由 Identity 确认。
权限不足返回 `identity_scope_not_granted`，不会拿不足的授权覆盖旧凭据。
`auth status` JSON 的 `scopes` 表示当前设备凭据记录的 OAuth 范围，未知为 null；
它不代表站点、项目或业务角色已获准。显式 `SAI_TOKEN` 不属于设备会话，应先取消
该环境输入，再为设备登录申请权限。

凭据继续绑定 Portal、issuer、client、resource 和配置中的 scope 基线。新增授权的
请求范围和实际返回范围分别保存在原受保护的待确认/凭据记录中。旧记录无需迁移；
它们缺失的范围保持未知。续期省略 scope 时保留原授权，明确缩小时采用新范围。
这些客户端验证不证明生产注册、本人同意或真实业务操作已完成。

## 协议归属

Device Authorization Grant 是 OAuth 2.0 的授权方式，不是 OAuth 的替代
品。SAI 的唯一身份入口是 `sai-identity` 及其维护的 OIDC/OAuth 协议引擎：

1. CLI 通过 `GET /.well-known/openid-configuration` 发现 Identity 的
   `device_authorization_endpoint`、`token_endpoint`、可选的
   `revocation_endpoint` 和 `userinfo_endpoint`。
2. CLI 按 RFC 8628 发起设备授权；用户在 Identity 浏览器页完成密码、OTP、
   MFA、consent 和风控确认。
3. CLI 轮询 Identity 的 token endpoint。批准后得到短期 OAuth access token
   和 rotating refresh token。CLI 不解析或伪造 Identity token。
4. access token 以 Portal resource audience 使用：当前 Portal 离线校验 Identity
   issuer/signature/audience/scope 和有效期，再执行
   workspace、membership、site、account、policy 判定。
5. Portal 通过 `POST /v1/authz/site-read` 签发独立的 `sai-authz` capability，
   远程命令访问授权的中心 CLI 路由，或配置好的站点读取网关。本地原生命令
   独立使用当前 Unix 权限直接查询，不通过这条认证链，也不作为远程失败的兜底。

Identity 侧必须先注册一个 public CLI client（不保存 client secret），允许
`urn:ietf:params:oauth:grant-type:device_code` 和 `refresh_token`，并明确
Portal resource/audience、最小 scope、access/refresh/session lifetime、
rotation/reuse detection、revocation、logout 和 key rotation。CLI 只接受
discovery 提供的端点和这些已审查的响应字段；不会猜测 issuer、scope 或
refresh 有效期。

Portal 不能新增一套平行的 `/v1/auth/cli/*` 身份 issuer。CLI 已删除旧
`POST /v1/token` HMAC 消费路径及旧 Bearer 缓存选择；所有安装都使用
Identity device/access/refresh 协议，或本进程显式提供的 Identity
`SAI_TOKEN`。CLI 不解析令牌，Portal 负责验证 issuer、audience 和 scope。
历史 `SAI_API_USERNAME`、`SAI_API_KEY_ID`、`SAI_API_SHARED_SECRET` 以及
TOML `username`/`key_id` 输入会在发起请求前被拒绝；对应命令参数已移除。
先取消设置提示中列出的旧环境变量、删除所选 TOML profile 中的旧字段，
再运行 `sai auth login`；将旧环境变量设为空字符串仍会被拒绝。
旧认证路径已经随 Portal/CLI 配对发布退役；这不等于撤权、日志交付等全部验收完成。

## 生命周期与存储

- 首次完整只读流程请求 `openid offline_access sai.compute.read sai.billing.read sai.storage.read`。
  `sai.storage.read` 是独立可选范围；先由 Identity 注册，再更新受管配置并显式
  执行设备登录取得用户同意。旧 refresh 会话不增权，软件更新不会覆盖现有受管配置。
  作业和费用是独立 scope，Portal 继续逐次校验业务权限及精确 operation。
  旧的作业专用会话不会自动获得费用权限；扩展授权范围需一次显式确认，之后
  沿用自动续期，不要求每次 SSH 登录重新授权。
- access token 默认由 Identity policy 控制为短期（客户端接受不超过 1 小时）。
- refresh token 由 Identity 轮换、可撤销并受绝对/闲置生命周期限制；客户端不
  提供不可撤销的“永久 Bearer”。在 SSH 可信的前提下，用户可以数月乃至更久
  不重新交互。refresh 会话失效后不能继续续期；已签出的 access token
  和站点 capability 仍分别受自己的有效期及验证规则约束。
- 撤销 refresh 不等于所有读取立即失效。当前 Portal 不逐请求查询 Identity
  会话；尚有效的 access token 可能继续申请 capability，最后签出的 capability
  又可能使用至到期。成员、站点和 shell 权限在新的能力签发时重新校验，
  已有能力则按到期、受控 JTI 撤销或策略 epoch 校验。完整停止窗口必须结合
  实际配置和实测确定，不能只报 capability 的两分钟寿命。
- 2026-10-06 已用普通用户独立设备会话完成生产撤销验收：最新成功轮换的
  refresh 在撤销后被原生端点拒绝；原 access 到期后不能再签发 capability，
  最后一份 capability 到期后也被拒绝。该样本的最后读取授权在撤销约399秒后
  到期，比 access 晚100秒；这是本次实测，不是所有凭据的统一失效承诺。
  日常独立会话随后正常刷新并读取，临时凭据与缓存已清理。
- OAuth token 响应不要求提供 refresh 到期字段。字段缺失，或 provider 用
  `refresh_expires_in=0` 表示服务端管理的 offline session 时，CLI 保存未知
  到期时间，状态输出 `refresh_expires_at=null`，不编造期限或宣称永久有效。
  已提供的正数到期时间仍严格校验；access token 和待确认设备码必须有期限。
  服务端返回 `invalid_grant` 后清除设备凭据并要求重新授权。
- refresh token 的默认路径是
  `${XDG_DATA_HOME}/sai/credentials.json`（未设置时
  `~/.local/share/sai/credentials.json`），目录 `0700`、文件 `0600`，原子
  替换并拒绝符号链接。access token 仍使用现有短期 cache。
- 多个 CLI 进程通过用户凭据锁串行化 refresh，避免 rotating token 的竞态。
- 独立 profile 和凭据文件不保证独立原生会话。同一浏览器 SSO 可以使两次授权
  复用同一 `sid`；独立撤销验收使用独立浏览器会话，不能为清理临时凭据而误撤销
  用户日常会话。早期同值验收只清理了本地凭据；2026-10-11 的独立客户端验收
  确认同一主体、不同原生会话后，实际撤销测试 grant，并验证最新 refresh 被拒绝，
  日常会话重新刷新仍成功。已签发 access token 的原有到期边界不因此改变。
- managed login-node 的 `/opt/sai/cli/config.toml` 只提供非敏感 Portal/
  Identity origin、client ID、scope 和 resource；refresh token 始终由当前
  Unix 用户持有，不能由 root 配置文件共享，也不能放入 package 或 wrapper。

## 失败与恢复

`sai` 不会猜测身份、回退到原始 Slurm、静默换用 `portal_read`，或把空列表
当作成功。续期收到 Identity 的 `invalid_grant` 后，命令返回
`credentials_unavailable`，并提示重新执行 `sai auth login`。网络暂时失败
不会删除仍然有效的本地 refresh token。

设备登录完成不等于生产闭环完成：还必须验证 Identity discovery/keys/rotation、
Portal resource-token consuming layer、issuer key/epoch、login-node package、
真实用户 GET-only canary 和回滚证据。已经完成和仍未完成的门槛分别记录在
[roadmap](roadmap.md)；缓存能力的真实401后自动续签与独立设备撤销已验，
成员和 shell 权限变更仍有各自的生产验收门槛。
