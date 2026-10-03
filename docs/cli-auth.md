# CLI 登录与长期会话

状态：Identity-only 认证退役候选，待 Portal/CLI 配对发布

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
4. access token 以 Portal resource audience 使用：Portal 校验 Identity
   issuer/signature/audience/scope（或受保护的 introspection），再执行
   workspace、membership、site、account、policy 判定。
5. Portal 通过 `POST /v1/authz/site-read` 签发独立的 `sai-authz` capability，
   CLI 最终只访问 `/v1/slurm/cli/*` 或 `/v1/billing/cli/*`。

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
本片需与 Portal 旧 issuer 退役配对发布，当前不宣称已完成该生产发布。

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
  不重新交互，但账号禁用、全局 logout、token-family reuse 或策略过期会立即
  收敛权限。
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
- managed login-node 的 `/opt/sai/cli/config.toml` 只提供非敏感 Portal/
  Identity origin、client ID、scope 和 resource；refresh token 始终由当前
  Unix 用户持有，不能由 root 配置文件共享，也不能放入 package 或 wrapper。

## 失败与恢复

`sai` 不会猜测身份、回退到原始 Slurm、静默换用 `portal_read`，或把空列表
当作成功。Identity device/session 无效、过期或被撤销时，命令返回
`credentials_unavailable`，并提示重新执行 `sai auth login`。网络暂时失败
不会删除仍然有效的本地 refresh token。

设备登录完成不等于生产闭环完成：还必须验证 Identity discovery/keys/rotation、
Portal resource-token consuming layer、issuer key/epoch、login-node package、
真实用户 GET-only canary 和回滚证据。本文件不宣称这些部署门禁已经通过。
