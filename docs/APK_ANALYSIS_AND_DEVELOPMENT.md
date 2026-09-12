# VOGE/无极 APK 分析与 Home Assistant 集成开发手册

> 文档用途：给后续开发者、审查者和 LLM 提供一份可以独立阅读的工程上下文。
>
> 当前目标：2026 款 VOGE/无极 CU250 二代 AMT 自动挡。
>
> 静态分析对象：`VOGE-release-product-arm64-V1.3.3-code-49.apk`。
>
> 文档状态：2026-09-12。账号密码登录流程已由用户实测通过；token-only 流程尚未实测，因此本文不会把 token-only 描述成已验证能力。

---

## 目录

1. [先读这一节：范围、结论和证据等级](#1-先读这一节范围结论和证据等级)
2. [项目目标与非目标](#2-项目目标与非目标)
3. [源材料、工具和复现边界](#3-源材料工具和复现边界)
4. [APK 元数据与静态分析方法](#4-apk-元数据与静态分析方法)
5. [APK 内部结构和网络链路](#5-apk-内部结构和网络链路)
6. [认证协议详解](#6-认证协议详解)
7. [现代、旧版和商城 API 的边界](#7-现代旧版和商城-api-的边界)
8. [当前只读 API 契约](#8-当前只读-api-契约)
9. [只读安全模型](#9-只读安全模型)
10. [数据模型、解析和身份校验](#10-数据模型解析和身份校验)
11. [坐标、时间和轨迹处理](#11-坐标时间和轨迹处理)
12. [Home Assistant 架构](#12-home-assistant-架构)
13. [配置流、ConfigEntry 和认证生命周期](#13-配置流configentry-和认证生命周期)
14. [实体、事件和 response-enabled actions](#14-实体事件和-response-enabled-actions)
15. [错误、限流、陈旧数据和可用性](#15-错误限流陈旧数据和可用性)
16. [隐私、日志和 diagnostics](#16-隐私日志和-diagnostics)
17. [测试体系与验证命令](#17-测试体系与验证命令)
18. [安装、运行和旧版告警 signer](#18-安装运行和旧版告警-signer)
19. [故障排查手册](#19-故障排查手册)
20. [后续研究和开发路线](#20-后续研究和开发路线)
21. [给后续 LLM 的工作规则](#21-给后续-llm-的工作规则)
22. [关键文件地图](#22-关键文件地图)
23. [术语表](#23-术语表)
24. [发布和提交前 checklist](#24-发布和提交前-checklist)

---

## 1. 先读这一节：范围、结论和证据等级

### 1.1 一句话结论

官方 APK 已经提供了足够的静态证据，支持为目标 CU250 构建一个**严格只读**的 Home Assistant 云端集成。现代燃油车 IoT API 可以使用 VOGE 手机号和密码登录，登录返回的主 token 通过 `Mansuoid` 访问车辆数据。当前代码已经实现账号密码登录、token 失效后的自动重新登录、车辆状态、历史行程、轨迹 response action，以及可选的旧版消息告警轮询。

但是，静态分析不能证明目标 CU250 的每个字段都在实车上启用。尤其不能仅因为 APK 中存在字段，就推断目标车一定支持 RPM、挡位、点火、在线/睡眠、胎压、胎温、冷却液温度或旧版实时数据。

### 1.2 当前真实验证状态

| 项目 | 当前状态 | 说明 |
|---|---|---|
| APK 静态分析 | 已完成 | 使用 JADX 反编译和 Android 工具核对调用链 |
| 账号密码登录 | **用户已实测通过** | 仅说明登录流程可用，不等于每个车辆字段均已验证 |
| token-only 登录/reauth | 未实测 | 代码保留兼容路径，暂不把它当作交付结论 |
| 目标 CU250 M1 车辆列表 | **授权测试账号已只读实测** | 已确认车型名来自 `deviceName`；其他能力仍由服务端数据下发 |
| M2 诊断字段 | 需要目标车脱敏响应 | 代码按身份严格匹配后才使用 |
| 轨迹数据 | 解析器和 actions 已有合成测试 | 仍需真实脱敏响应确认时间单位和字段实际值 |
| 车型业务目录 | **授权只读调查已完成** | 预约目录 18 个 `modelCode`；当前商城 16 个整车商品、15 个不同 `modelCode` |
| 旧版告警 | 代码支持，但依赖本地 signer | 没有 signer 时明确禁用，不影响现代状态功能 |
| 车辆控制 | 永不实现 | 不属于本项目范围 |
| APK 运行时动态抓包 | 未进行 | 不能把推断写成运行时事实 |
| 生产 API 动态调查 | 仅限用户明确授权的车型调查 | 只调用固定登录和静态确认的只读目录/详情接口，结果已脱敏 |

### 1.3 证据等级

后续修改必须给每个结论标记证据等级：

1. **静态已确认**：能在 APK 反编译产物、Manifest、Retrofit interface、调用者或常量中直接定位。
2. **代码已实现**：本仓库已有实现和合成测试，但不代表目标车辆真实返回该能力。
3. **用户实测**：用户实际使用目标账号/车辆验证过；需要记录测试范围，不夸大为全功能验证。
4. **静态推断**：从类名、UI、字段命名或调用关系合理推断，但尚未得到完整调用/响应证据。
5. **待脱敏实测**：需要真实响应才能确认，必须先删除秘密和精确位置。
6. **明确禁止推断**：没有足够证据，不能因为某个通用模型字段存在就开放实体或接口。

如果代码注释、README、旧契约和本文件不一致，优先遵循：

1. 当前安全实现和测试；
2. 本文件的“当前状态”；
3. `CU250_READ_ONLY_API_CONTRACT.md` 的底层 endpoint 契约；
4. APK 静态证据；
5. 最后才是名称猜测或其他车型经验。

---

## 2. 项目目标与非目标

### 2.1 目标车型

唯一目标是：

- 品牌：VOGE/无极；
- 年款：2026；
- 车型：CU250 二代；
- 变速形式：AMT 自动挡；
- 接入方式：官方 Android APK 所使用的云端 API；
- Home Assistant 侧：自定义集成、只读实体、只读 response actions。

其他 VOGE 车型、电动车、蓝牙仪表、投屏、数字钥匙或旧版车型代码只能用于理解共享基础设施，不能作为“CU250 已支持”的证据。

### 2.2 目标数据

当前设计希望在证据允许时读取：

- 当前/最近车辆位置；
- GPS 最近更新时间；
- 车辆/云端遥测更新时间；
- 当前月行程摘要；
- 每日和单次行程摘要；
- 单次和每日历史轨迹；
- 剩余油量百分比；
- 剩余油量升数；
- 百公里油耗；
- 预计剩余续航；
- 总里程和月里程；
- 设备/电瓶电压；
- 冷却液温度；
- 前后胎压和胎温（只有能力键和身份校验允许时）；
- 平均/最高速度及骑行行为统计；
- 震动、拖车/异常移动、防盗、碰撞、电子围栏、低电压、低油量、设备断开等账户消息事件。

动态 CAN 列表可能包含速度、RPM、挡位或点火等数据，但在真实 CU250 多次脱敏响应、稳定字段和单位确认前，不自动创建这些实体。

### 2.3 非目标和永远禁止的行为

本项目不实现：

- 解锁、上锁、设防、撤防；
- 唤醒设备；
- 断油、断电、远程熄火；
- 电子锁、数字钥匙、蓝牙钥匙；
- 阻尼设置；
- 车辆绑定、解绑或分享；
- 修改服务端默认车辆；
- 修改车辆名称、车牌、账号、密码、手机号、个人资料；
- 固件升级；
- 修改通知开关；
- 标记消息已读；
- 删除消息；
- 发送短信或语音验证码；
- 绑定或伪造 JPush registration ID；
- 商城登录、商城下单或商城写入；
- 把该集成变成任意 URL/HTTP method 的代理。

“只读”不仅意味着当前没有调用写接口，也意味着 transport 层要在发出请求前拒绝未声明的 endpoint。

---

## 3. 源材料、工具和复现边界

### 3.1 项目材料

主要材料如下：

```text
/Users/tink/Projects/voge/
├── VOGE-release-product-arm64-V1.3.3-code-49.apk
├── CU250_READ_ONLY_API_CONTRACT.md
├── README.md
├── custom_components/voge/
├── tests/
├── tools/
└── docs/APK_ANALYSIS_AND_DEVELOPMENT.md
```

APK 和反编译输出是研究输入，不是 Home Assistant 运行时依赖。JADX 临时输出曾位于：

```text
/Users/tink/.claude/jobs/df3001f3/tmp/voge-apk/src
```

临时路径不能作为未来构建的硬依赖；如果重新分析，应在本地临时目录生成，并且不把完整反编译输出提交到仓库。

### 3.2 使用过的工具和版本

- JADX 1.5.5；
- Android Studio 自带 JBR，用于 `keytool`、`apksigner` 等工具；
- Python 3.14.2；
- Home Assistant 2026.9.0；
- `pytest`；
- `pytest-homeassistant-custom-component`；
- Ruff；
- Pyright；
- `uv` 用于临时隔离依赖。

### 3.3 安全边界

分析阶段：

- 没有运行 APK；
- 常规 Home Assistant 使用不要求用户在聊天中提供密码；
- 车型调查阶段使用了用户主动提供并明确授权的测试账号，授权范围仅限固定登录和已静态确认的只读请求；
- 测试账号、密码、密码 MD5、token、手机号、VIN、完整设备 ID、SIM ID、坐标和地址均未写入本文或产品代码；
- 调查输出只保留车型、商品和目录等安全字段，临时脱敏文件权限设为 `0600`；
- 没有使用 APK 私有 signer 对外发布；
- 没有进行未经授权的生产 API 探测；
- 没有执行车辆控制、短信、JPush、账号修改、消息修改或商城写入。

用户实际在自己的 Home Assistant 中输入账号密码属于本地配置行为。密码只应通过 HA 的配置流/reauth 界面输入，不应复制到 issue、日志或测试 fixture。测试账号凭据即使曾在一次明确授权的研究上下文中提供，也不得在文档、摘要、命令输出、提交或后续报告中复述。

---

## 4. APK 元数据与静态分析方法

### 4.1 已确认元数据

| 字段 | 值 |
|---|---|
| 包名 | `com.jczy.voge` |
| 版本名 | `1.3.3` |
| versionCode | `49` |
| flavor | `productArm64` |
| 签名方案 | APK Signature Scheme v2 |
| 签名者数量 | 1 |
| 公钥算法 | RSA |
| 公钥长度 | 2048 bit |
| APK SHA-256 | `218242102ad27aeab1eb13c9e8bd1012bfcbf48ef1093092679ac720154a444e` |
| 证书 DN | `C=cn, ST=sd, L=cd, O=jczy, OU=jczy, CN=jczy` |
| 证书 SHA-256 | `130a712de3d1fafd27131d79a6c62d3d3108858324016156606435307eb09ce2` |
| 证书 SHA-1 | `8010a9ee5b831281cbc21ad3d369876aa377d0f1` |
| 公钥 SHA-256 | `1702cf4038952a33394719a94af8c45e381cb6834f65fda04dd4961a1528cba8` |

> 注意：上表只包含 APK 公共元数据和指纹。应用级 access key、signing secret、真实账户数据和 token 不在本文披露。

### 4.2 反编译时的检索策略

直接对整个 JADX 输出做宽泛 grep 会命中大量 SDK、Kotlin metadata、生成类和无关依赖，容易产生错误结论。推荐顺序：

1. 先读 Manifest，确认包名、组件和版本。
2. 找 `NetModule`、Retrofit service、base URL 和 interceptor。
3. 从 endpoint 常量反向找调用者。
4. 从 UI ViewModel/Repository 追到 service 方法。
5. 从响应 model 追字段，而不是根据字段名称猜 API。
6. 只对 first-party package 做精确搜索。
7. 记录“声明了但没有调用者”的接口，不能把声明当作实际行为。
8. 对登录、refresh、商城和 JPush 分开画调用链。

### 4.3 关键静态证据文件

JADX 输出中最重要的路径/职责：

| JADX 文件 | 证据 |
|---|---|
| `p372ui/login/LoginRepository.java` | `loginByPwd(String phone, String pwd)`，构造 mobile/password 请求 |
| `p372ui/login/LoginViewModel.java` | 登录前调用 `MD5.toMD5(pwd)` |
| `p372ui/login/LoginViewModel$loginInternal$1$action$1.java` | 密码登录与 SMS 登录是不同分支 |
| `utils/MD5.java` | Java MD5 小写 hex 规则 |
| `net/MotoApiService.java` | 现代车辆登录 Retrofit POST |
| `net/API_MOTO.java` | `ACCOUNT_LOGIN = api/login/loginByMobile` |
| `model/p371v2/LoginResponse.java` | 现代登录返回字段，含 token/bicoseToken |
| `net/BaseMotoModel.java` | 现代响应 envelope |
| `net/HttpHeaderInterceptor` 或同职责类 | 现代请求头 |
| `net/HttpHeaderCommonInterceptor` 或同职责类 | 旧版签名请求头 |
| `net/NetModule.java` | 现代、旧版和商城 base URL |
| `net/ApiService.java` | 通用 auth/login 与声明的 refresh endpoint |
| `net/MallApiService.java` | 商城 `gateway.do` 和 `sysLoginSmsAuto` |
| `model/SysLoginResponse.java` | 商城 refreshToken 字段，不能与车辆 token 混用 |
| `p372ui/main/MainViewModel.java` | 商城登录调用者 |

---

## 5. APK 内部结构和网络链路

### 5.1 三条必须隔离的网络链路

APK 中存在三类服务：

```text
现代燃油车辆 IoT API
  ├── host: iot-api.loncinindustries.com
  ├── 主 token: LoginResponse.token
  ├── 请求头: Mansuoid
  └── 车辆状态、诊断、统计、轨迹

旧版/通用 API
  ├── host: voge.loncinindustries.com/api
  ├── 用户 token + APK 应用级 SM3 签名
  └── 消息告警、旧版车辆/实验性数据

商城 OpenAPI
  ├── host: lxopenapi.loncinindustries.com
  ├── gateway.do / sysLoginSmsAuto
  ├── SysLoginResponse.refreshToken
  └── 商城业务，不是现代车辆 token refresh
```

不能因为三个服务在同一个 APK 中，就把 token、refreshToken、headers 或 endpoint 互相拼接。

### 5.2 现代 host 和请求头

现代 base URL：

```text
https://iot-api.loncinindustries.com/
```

当前集成生成的现代数据请求头：

```http
Content-Language: zh_CN
Platform: ANDROID
Mansuoid: <当前车辆访问 token>
Blade-Auth:
version: 1.3.3
PhoneModel: HomeAssistant/voge-0.1.0
Source: VOGE
```

登录请求也固定使用 HTTPS、JSON body、`allow_redirects=False`，但登录 client 与数据 client 分离。登录 POST 不会给 `_BaseReadOnlyClient` 增加任意 POST 能力。

### 5.3 现代响应 envelope

现代接口使用类似：

```json
{
  "code": 200,
  "message": "...",
  "message_sys": "...",
  "result": {},
  "success": true,
  "sysMsgEvent": null,
  "timestamp": 0
}
```

规则：

- `code == 200` 才是业务成功；
- HTTP 401 或 body `code == 401` 都是认证失效；
- `success` 只能辅助判断，不能替代 `code`；
- 非成功响应不得直接把服务端 message 原文塞进异常；
- `result` 的实际类型由 endpoint 决定，必须在各自 parser 中防御式处理。

### 5.4 旧版 envelope 和签名

旧版 base URL：

```text
https://voge.loncinindustries.com/api/
```

典型响应：

```json
{
  "code": 0,
  "msg": "...",
  "data": {},
  "errorCode": null
}
```

典型请求头：

```http
accessKey: <本地私密值>
timestamp: <Unix epoch milliseconds>
nonce: <UUID>
signature: <SM3 lowercase hex>
Authorization: <用户主 token>
```

签名算法的静态规则：

1. 构造 `accessKey`、`timestamp`、`nonce`。
2. 按 key 的字典序排序。
3. 对非空字段拼接 `key=value`。
4. 字段之间不加入 `&`、换行或其他分隔符。
5. 末尾追加 APK 内置 signing secret。
6. 对 UTF-8 字节执行 SM3。
7. 输出小写十六进制。

真实 access key 和 signing secret 只允许保存在本地被 `.gitignore` 排除的模块中；不能进入文档、日志、diagnostics、公开源码、压缩包或测试 fixture。

---

## 6. 认证协议详解

### 6.1 密码登录调用链

静态调用链：

```text
LoginViewModel.loginByPwd
  → MD5.toMD5(password)
  → LoginRepository.loginByPwd(phone, md5Password)
  → MotoApiService.loginByPwd
  → POST /api/login/loginByMobile
  → BaseMotoModel<LoginResponse>
  → LoginResponse.token
```

当前 Python 对应实现：

```text
config_flow._validate_credentials
  → VogeAuthClient.login(mobile, password)
  → POST https://iot-api.loncinindustries.com/api/login/loginByMobile
  → _validate_token(hass, token)
  → GET /api/app/favorite/device
  → 选择目标 vehicle
  → 创建 ConfigEntry
```

### 6.2 精确登录请求

请求：

```http
POST https://iot-api.loncinindustries.com/api/login/loginByMobile
Content-Type: application/json
Content-Language: zh_CN
Platform: ANDROID
Mansuoid:
Blade-Auth:
version: 1.3.3
PhoneModel: HomeAssistant/voge-0.1.0
Source: VOGE
```

JSON body 的字段集合必须恰好是：

```json
{
  "mobile": "<手机号>",
  "password": "<APK 兼容的 MD5 小写 hex>"
}
```

当前实现对手机号做外围空白清理，因为 API 字段是手机号；对密码**不 trim**，以保留 APK 的行为。

### 6.3 APK 兼容 MD5

APK 的 `MD5.toMD5` 行为：

- 使用字符串的字节表示；
- 当前 Python 使用 UTF-8，符合现代 Android/Java 常见运行时；
- 算法为 MD5；
- 输出小写十六进制；
- 无 salt；
- 无额外拼接；
- 无密码 trim；
- 无第二次 hash。

等价实现：

```python
hashlib.md5(password.encode("utf-8"), usedforsecurity=False).hexdigest()
```

MD5 输出虽然不是明文，但仍然是可重放的认证凭据，必须按秘密处理。不能把它写入日志、diagnostics、issue 或公开 fixture。

### 6.4 登录响应解析

只有以下响应才算成功：

1. HTTP 状态不是错误；
2. body 是 JSON object；
3. `code == 200`；
4. `success` 不是明确的 `False`；
5. `result` 是 object；
6. `result.token` 是非空字符串。

当前代码只提取 `result.token`。如果缺少 token、类型错误、JSON 畸形、HTTP 401、body code 401 或业务失败，转换成不含手机号/密码/token/message 原文的安全异常。

### 6.5 `token`、`bicoseToken` 和商城 `refreshToken`

现代 `LoginResponse` 中有：

- `token`：当前已确认用于现代车辆 API 的主访问 token；
- `bicoseToken`：APK 登录返回的另一个字段，但当前静态证据不足以证明它是目标 CU250 的现代 API 访问 token；当前不把它写入 `Mansuoid`；
- 没有 `refreshToken`；
- 没有 `expires`。

商城 `SysLoginResponse.refreshToken` 属于商城 OpenAPI 的登录链路，不能拿来刷新现代车辆 token。

`ApiService` 声明过 `AUTH_REFRESH = club-auth/refresh`，但静态输出中没有找到实际调用者，也没有证据证明它刷新 `Mansuoid`。在新的静态或脱敏运行证据出现前，不能调用它。

### 6.6 `VogeAuthManager` 状态机

`custom_components/voge/auth_manager.py` 的职责是：

- 持有当前内存 token；
- 持有认证模式；
- 在密码模式下持有本地 ConfigEntry 中的手机号/密码引用；
- 用一个 `asyncio.Lock` 串行化密码登录；
- 将新 token 推送给已注册的 modern/legacy data clients；
- 持久化新 token；
- unload 时清除密码引用和 client 列表。

401 恢复流程：

```text
GET 使用 old-token
  └─ HTTP 401 或 body code 401
      └─ auth_failure_handler(observed_token=old-token)
          └─ lock 内检查当前 token
              ├─ 当前 token 已不是 old-token：直接复用新 token
              └─ 仍是 old-token：执行一次固定密码登录
                  ├─ 登录失败：抛出认证错误
                  └─ 登录成功：更新 clients + ConfigEntry token
      └─ 原 GET 用新 token 最多重试一次
          ├─ 成功：返回数据
          └─ 再次 401：停止，不无限循环
```

并发情况下，多个请求观察到同一个旧 token：

- 第一个协程取得锁并登录；
- 其他协程等待锁；
- 后续协程发现 token 已经变化，复用该 token；
- 不产生多次并发登录。

### 6.7 token-only 当前定位

token-only 代码路径仍保留：

- 可在配置流中选择高级 token 模式；
- 旧 token entry 可迁移；
- 没有密码时不会调用短信、JPush、商城 refresh 或未知 refresh endpoint；
- token 失效后进入 reauth，要求用户输入新 token。

但是截至本文日期，token-only 尚未由用户实测。开发者不能在发布说明中写“token-only 已验证”。

---

## 7. 现代、旧版和商城 API 的边界

### 7.1 现代 API endpoint 表

所有现代 endpoint 都是 `GET`，主 host 为 `https://iot-api.loncinindustries.com`，业务成功 code 为 `200`。

| 名称 | Path | Query | 当前用途/状态 |
|---|---|---|---|
| `modern.devices` | `/api/app/favorite/device` | 无 | M1 车辆列表、车辆状态、位置、能力；配置验证和遥测主入口 |
| `modern.diagnosis` | `/api/app/favorite/synthesize-diagnosis` | 无 | M2 综合诊断；必须严格核对返回 `deviceId` |
| `modern.month_index` | `/api/app/favorite/index` | `deviceId` | M3 当前月摘要；统计 coordinator 按配置车辆调用 |
| `modern.month_tracks` | `/api/app/favorite/car-track-new` | `deviceId`, `month` | M4 月度每日/单次行程列表；按需并缓存 |
| `modern.route_detail` | `/api/app/favorite/locus` | `routeId` | M5 单条轨迹；routeId 必须先由 M4 验证 |
| `modern.behavior` | `/api/app/favorite/behavior` | `deviceId`, `month` | M6 月度驾驶行为；已 allowlist，格式/实际启用仍需确认 |
| `modern.riding` | `/api/app/favorite/riding` | `deviceId`, `month` | M7 月度骑行数据；已 allowlist，格式/实际启用仍需确认 |
| `modern.function_config` | `/api/app/operateConfig/getConfigCodes` | 无 | M8 功能代码发现；首版不依赖它决定车辆能力 |

当前 `_ALLOWED_ENDPOINTS` 只接受这些精确的 `Endpoint` 对象。新增 endpoint 必须同时更新代码、文档、安全测试和证据记录。

### 7.2 现代接口关键字段

#### M1 `/api/app/favorite/device`

响应通常是 `BaseMotoModel<ArrayList<MotoItem>>`。可得到或尝试解析：

- `deviceId`；
- `deviceIdIot`；
- `amapDeviceId`；
- `deviceName`；
- `productId`；
- `productName`；
- VIN；
- 用户身份字段；
- GCJ-02 位置候选；
- GPS 时间；
- 车辆/云端更新时间；
- 油耗、油量、续航、里程、月里程；
- 最高速度和行为计数；
- `menu` 能力键。

M1 同时用于：

- 验证 token；
- 列出账户绑定车辆；
- 在本地选择目标车辆；
- 作为 M2/M3 目标身份基准。

#### M2 `/api/app/favorite/synthesize-diagnosis`

响应没有 `deviceId` query，可能对应服务端默认车辆。因此当前代码只有在返回 `result.deviceId` 与已配置 `deviceId` 完全一致时，才把诊断合并到目标车。

候选字段：

- `fuelPercentage`；
- `restFuelLevel`；
- `sumDistance`；
- `voltage`；
- `coolingTpr`；
- `frontTireP`；
- `queenTireP`（后轮胎压）；
- `frontTireTpr`；
- `queenTireTpr`；
- `nextUpkeepMileage`；
- `timeGen`；
- `canList`；
- `menu`；
- `rafe`（含义未知，当前不创建实体）。

即使账户只有一辆车，也不能跳过 `deviceId` 严格匹配。

#### M3 `/api/app/favorite/index?deviceId=...`

当前月摘要候选字段：

- `deviceId`；
- `aveSpeed`；
- `distance`；
- `duration`；
- `geoLatitude`、`geoLongitude`；
- `gpsTime`。

`duration` 的单位尚未有目标车实测结论；代码保留原始值或不创建不确定单位的实体。

#### M4 `/api/app/favorite/car-track-new`

月份格式由 APK 调用习惯确认是 `yyyy-MM`。每日摘要和单次行程包含：

- 日：`day`、`distanceMo`、`durationMo`、`durationMoStr`、`driveTotalTimes`、速度和压弯统计；
- 行程：`routeId`、开始/结束日期、开始/结束地址、开始/结束坐标、距离、时长、平均/最高速度、行为统计。

`day` 的具体文字格式由服务器返回，不能在代码中臆造。

#### M5 `/api/app/favorite/locus?routeId=...`

`points` 是**包含 JSON 数组的字符串**，不是稳定的原生数组：

```json
{
  "points": "[{\"lat\":\"29.x\",\"lon\":\"106.x\",\"speed\":42.5,\"direction\":123.4,\"locatetime\":1234567890}]"
}
```

请求前必须验证 routeId 来自同一 ConfigEntry、同一月份的 M4 结果。响应若返回 routeId，也必须与请求值相等。

#### M6/M7/M8

M6 行为、M7 月度骑行和 M8 功能代码已从 APK endpoint/模型中识别，但当前不能用“接口存在”证明目标 CU250 返回有效值。未来接入时需要：

- 明确当前调用点；
- 真实脱敏响应；
- 目标 `deviceId` 归属；
- 防止排行榜泄露其他用户；
- 稳定的单位与时间语义；
- 专项 parser 和回归测试。

### 7.3 旧版 API endpoint 表

旧版 API 业务成功 code 为 `0`，请求需要本地私密应用级 SM3 signer。

| 名称 | Path | Query | 当前用途/状态 |
|---|---|---|---|
| `legacy.messages` | `/voge-system/app/message/page` | `module`, `pageSize`, `pageNum` | module=1 只读消息分页；告警 coordinator 使用 |
| `legacy.message_info` | `/voge-system/app/message/info` | `messageId` | 已 allowlist，默认不自动逐条调用 |
| `legacy.vehicles` | `/moto/app/vehicle/excludeShareVehicle` | 无 | 已 allowlist，实验性身份关联入口 |
| L4 legacy realtime | `/moto/app/vehicle/body/{vehicleId}` | 路径 ID | 契约中记录但当前默认禁用，不能仅靠字段存在启用 |

L1 分页参数规则：

- `module` 固定为 `1`；
- `pageNum` 从 `1` 开始；
- `pageSize` 当前限制为 `1..100`，默认使用 `50`；
- 省略未确认的 `clubType`；
- 最多扫描 `ALERT_MAX_PAGES=5` 页；
- 不调用 upReadStatus、delete 或 deleteAll。

### 7.4 商城 API：记录但不接入

商城 host：

```text
https://lxopenapi.loncinindustries.com/
```

APK 中的 `gateway.do`、`sysLoginSmsAuto` 和 `SysLoginResponse.refreshToken` 属于商城登录链路。它们不是现代车辆 `Mansuoid` token 的刷新机制，本集成不调用、不保存、不推断其可互换性。

### 7.5 车型目录只读调查：范围和最终计数

2026-09-12，使用用户明确授权的测试账号执行了一次独立的车型目录调查。调查只调用：

1. 固定的手机号密码登录；
2. 现代 M1 车辆列表；
3. APK 静态确认的商城目录、商品搜索、商品详情和预约车型属性查询；
4. APK 静态确认的旧版车型/推荐车型只读查询。

没有调用短信、JPush、车辆控制、账户修改、消息修改、绑定/解绑、服务端默认车辆修改、商城下单或其他写入接口。HTTP 客户端使用正常系统 CA 和 hostname 校验，并拒绝跨 host redirect。

脱敏结果的最终一致性检查如下：

| 检查项 | 结果 |
|---|---|
| 预约车型属性调用 | 8 次，全部 HTTP 和业务成功 |
| 预约目录品牌 | 1 个：`voge` / 无极 |
| 预约目录车系 | 6 个，其中 R、AC 当前车型列表为空 |
| 预约目录不同车型代码 | 18 个 |
| 商城无极品牌整车商品 | 16 个，1 页，无截断 |
| 商城商品详情 | 16/16 成功，16/16 名称匹配 |
| 商城不同 `modelCode` | 15 个 |
| 商城车型是否都在预约目录 | 是，15 个不同代码全部包含 |
| 商城首页“整车”商品 | 14 个 |
| 首页遗漏、但品牌搜索可见 | SR450X、RR660S |
| CU250 二代商品 | 2 个商品，共用 `modelCode=997` |

这里的“18 个车型”是**当前预约/商城业务域能够枚举出的车型代码目录**，不是现代 IoT 联网能力支持矩阵，也不能代表 App 历史上曾出现过的所有车型。

### 7.6 现代车辆车型名称：必须优先使用 `deviceName`

测试账号当前绑定车辆的安全命名字段为：

| 字段 | 观测值 | 含义 |
|---|---|---|
| `deviceName` | `CU250 II代自动挡` | 现代车辆明确的车型/型号显示名称 |
| `productId` | `2` | 现代 IoT 产品标识；全局语义尚未确认 |
| `productName` | `null` | 为空不妨碍车型识别 |
| `itemName` | `null` | 当前不能作为车型名称来源 |

APK UI 调用链也明确区分了这些字段：

- `MotoInfoActivity` 将 `MotoItem.getDeviceName()` 写入车型控件 `tvMotoModel`；
- 有颜色时显示 `deviceName(color)`；
- `MotoWarpItem.requireDeviceName()` 同样要求 `deviceName`；
- `CommonWebActivity` 的 `currentMotoInfo` Web 桥接执行：

```java
userDefaultCarBody.setVehicleName(
    motoWarpItem.getMoto().getProductName()
);
userDefaultCarBody.setModelName(
    motoWarpItem.getMoto().getDeviceName()
);
```

因此：

```text
productName → vehicleName
deviceName  → modelName
```

Home Assistant 显示已绑定车辆车型时，不需要调用商城反查，应直接使用：

```python
vehicle.device_name
```

对于测试车辆，这可以保留“自动挡”这一精确差异；商城 `modelName` 不能做到这一点。

`productId=2` 与 `deviceName=CU250 II代自动挡` 只能记录为该绑定车辆上的**观测关联**。APK 未内置 `productId → 车型` 静态表，当前也没有找到能够枚举全量现代 `productId` 的目录接口，因此不得写成：

```python
# 错误：当前证据不足以证明全局一对一关系
PRODUCT_NAMES = {
    "2": "CU250 II代自动挡",
}
```

### 7.7 当前预约车型业务目录：18 个 `modelCode`

当前可用的预约车型属性服务为：

```text
goodsAttributeSerApiService
```

响应模型是 `BookingDrivingAttrModel`，包含：

- `brand[]`；
- `tline[]`；
- `model[]`。

单项模型 `BookingDrivingAttrItem` 包含：

- `code`；
- `name`；
- `picUrl`；
- `checked`。

APK 的概念流程是：

```text
brand → tline → model
```

当前服务器在查询车型级目录时，需要同时提交已选择的 `brand` 和 `tline`。只提交 `tline` 虽然会返回 HTTP 200 和 `SUCCESS`，但 `model=[]`。这与当前 APK 反编译代码最后一级只显式携带 `tline` 的形态不完全一致，说明服务端契约可能在 APK 发布后发生了兼容性调整。

品牌：

| 品牌代码 | 品牌名称 | 商城品牌 ID |
|---|---|---:|
| `voge` | 无极 | `33` |

完整车型目录：

| 车系 | `tlineCode` | `modelName` | `modelCode` | 当前商城整车商品 |
|---|---:|---|---:|---|
| CU | `906` | CU625 | `907` | 有 |
| CU | `906` | CU250 | `916` | 无 |
| CU | `906` | CU525旅行版/2025款 | `919` | 有 |
| CU | `906` | CU525链条版 | `981` | 有 |
| CU | `906` | CU625自动挡 | `992` | 有 |
| CU | `906` | CU530 | `995` | 有 |
| CU | `906` | CU250Ⅱ代 | `997` | 有，2 个商品 |
| DS | `910` | DS900X 2025款 | `928` | 有 |
| DS | `910` | DS625X | `956` | 无 |
| DS | `910` | DS500X | `985` | 有 |
| SR | `931` | SR250GT | `932` | 无 |
| SR | `931` | SR4 Max | `958` | 有 |
| SR | `931` | SR150C-PRO版 | `973` | 有 |
| SR | `931` | SR150R | `988` | 有 |
| SR | `931` | SR250GT II代 | `999` | 有 |
| SR | `931` | SR450X | `1001` | 有 |
| RR | `934` | RR660S | `957` | 有 |
| RR | `934` | RR500S | `978` | 有 |

服务端还识别以下车系，但当前没有返回车型：

| 车系 | `tlineCode` | 当前车型数 |
|---|---:|---:|
| R | `952` | 0 |
| AC | `953` | 0 |

预约目录比当前商城商品目录多 3 款：

| `modelName` | `modelCode` |
|---|---:|
| CU250 | `916` |
| SR250GT | `932` |
| DS625X | `956` |

这 3 款仍存在于预约车型目录，但不能据此推断当前仍可下定、一定支持现代 IoT，或与旧版 `vehicleModelId` 存在相同编号。

### 7.8 当前商城完整整车商品：16 个商品、15 个车型代码

使用 `mallGoodsInfoPageList` 并限定商城无极品牌 `brandId=33`，当前返回 16 个 `productType=vehicle` 商品。随后使用只读 `mallGoodsInfoInfo` 对 16 个商品逐一查询详情，补齐全部 `modelCode`。

| 车系 | 商品标题 | `modelCode` | 商城商品 ID | 首页分组行 ID | 商品业务 `code` |
|---|---|---:|---:|---:|---|
| CU | CU625【定金】 | `907` | `400580` | `477` | `GID2025061215362502504037` |
| CU | CU525 旅行版【定金】 | `919` | `400598` | `475` | `GV2025062700003` |
| CU | CU525链条版【定金】 | `981` | `400605` | `474` | `GV2025102200008` |
| CU | CU625自动挡【定金】 | `992` | `400616` | `473` | `GV2026030300013` |
| CU | CU530【定金】 | `995` | `400625` | `472` | `GV2026042700014` |
| CU | CU250Ⅱ代【定金】 | `997` | `400639` | `537` | `GV2026052500015` |
| CU | CU250 Ⅱ代 自动挡【定金】 | `997` | `400640` | `536` | `GV2026052500016` |
| DS | DS900X【定金】 | `928` | `400600` | `485` | `GV2025062700005` |
| DS | DS500X【定金】 | `985` | `400607` | `484` | `GV2026012300010` |
| SR | SR4 MAX【定金】 | `958` | `400606` | `479` | `GV2025122300009` |
| SR | SR150C PRO【定金】 | `973` | `400599` | `481` | `GV2025062700004` |
| SR | SR150R【定金】 | `988` | `400608` | `478` | `GV2026013000011` |
| SR | SR250GT II代【定金】 | `999` | `400653` | `545` | `GV2026061200017` |
| SR | SR450X【定金】 | `1001` | `400693` | 无首页分组行 | `GV2026090200018` |
| RR | RR660S【定金】 | `957` | `400582` | 无首页分组行 | `GID2025061217285402504611` |
| RR | RR500S【定金】 | `978` | `400603` | `486` | `GV2025101600006` |

需要特别注意 `MallGoods.id` 的接口语义：

- 在全局搜索和详情接口中，`MallGoods.id` 是实际商品 ID；
- 在分组列表接口中，`MallGoods.id` 是分组行 ID；
- 在分组列表接口中，`MallGoods.goodsId` 才是实际商品 ID；
- 分组接口的 `goodsId` 与搜索/详情接口的 `id` 对应。

商品业务 `code`、商品 ID、分组行 ID 和 `modelCode` 是四套不同字段，不得互相替代。

#### CU250 二代手动/自动挡不能通过 `modelCode` 区分

两个独立商城商品分别是：

```text
普通版本：
  商品 ID   = 400639
  modelCode = 997
  modelName = CU250Ⅱ代

自动挡版本：
  商品 ID   = 400640
  modelCode = 997
  modelName = CU250Ⅱ代
```

两者只通过商品标题、商品 ID、分组行 ID 和商品业务 `code` 区分。它们共用：

```text
modelCode = 997
modelName = CU250Ⅱ代
```

所以 `modelCode=997` 表示 CU250 二代车型族，**不是 AMT 自动挡专属代码**。现代绑定车辆要显示精确版本，必须使用 `deviceName=CU250 II代自动挡`。

### 7.9 商城首页分类不是车型目录

`mallGroupIndexList` 当前返回的整车相关首页分类：

| 首页分类 | ID |
|---|---:|
| 整车 | `159` |
| CU 巡航系列 | `160` |
| SR 踏板系列 | `161` |
| DS 拉力系列 | `162` |
| RR 仿赛系列 | `163` |

这些 ID 只用于商城首页分类，不是 `tlineCode`、`modelCode` 或现代 `productId`。

`mallGroupGoodsList(mainId=159)` 的首页“整车”分类只有 14 个独立商品，而 `mallGoodsInfoPageList(brandId=33)` 返回 16 个。首页未展示但品牌搜索可见：

| 车型 | `modelCode` | 商品 ID |
|---|---:|---:|
| SR450X | `1001` | `400693` |
| RR660S | `957` | `400582` |

因此不得仅使用首页栏目声称获得了完整当前商品目录。

### 7.10 各套车型和商品 ID 必须严格隔离

| 字段 | 所属业务域 | 示例 | 正确含义 |
|---|---|---|---|
| `deviceName` | 现代 IoT 绑定车辆 | `CU250 II代自动挡` | 车型显示名称，不是 ID |
| `productId` | 现代 IoT | `2` | 不透明的 IoT 产品标识；全局映射未知 |
| `productName` | 现代 IoT | 当前测试车辆为 `null` | 被 APK 映射为 `vehicleName`，不能替代 `deviceName` |
| `modelCode` | 预约/商城车型 | `997` | 业务车型代码，不是现代 `productId` |
| `tlineCode` | 预约/商城车系 | CU=`906` | 车系代码，不是车型代码 |
| 商城品牌 ID | 商城 | `33` | 商城无极品牌筛选 ID |
| 商城首页分类 ID | 商城首页 | CU 分类=`160` | 首页 UI 分类 ID |
| 商品 ID | 商城商品 | `400640` | 标识一个具体商城商品 |
| 分组行 ID | 商城分组 | `536` | 标识商品在分组列表中的一行 |
| 商品业务 `code` | 商城商品 | `GV...` / `GID...` | 商城商品业务编码 |
| `vehicleModelId` | 旧版车辆 API | 当前未取得 | 旧版车型 ID，不能与以上字段混用 |
| `modelsId` | 旧版推荐车型 | 当前无数据 | 推荐车型模型 ID，不能与以上字段混用 |

明确禁止建立以下等式：

```text
现代 productId 2       ≠ 商城 modelCode 997
商城 modelCode 997     ≠ CU250 自动挡专属代码
商城商品 ID 400640      ≠ 现代 productId
商城 tlineCode 906     ≠ modelCode 997
商城首页分类 ID 160     ≠ tlineCode 906
```

即使未来通过更多账号观察到相同关联，也必须保留来源和证据等级，不能在缺少正式现代产品目录时将观测结果升级为全局协议事实。

### 7.11 旧版车型和推荐车型目录当前不可用

旧版只读请求的当前结果：

| 接口 | 当前结果 |
|---|---|
| `/api/moto/app/vehicle/excludeShareVehicle` | HTTP 200，但业务 `code=500` |
| `/voge-system/app/vehicle/model/all` | 返回 HTML/fallback 页面 |
| `/api/voge-system/app/vehicle/model/all` | HTTP 404 |
| `/api/voge-system/app/modelsRecommend/list` | 业务成功 `code=0`，但 `data=[]` |
| `/api/moto/app/vehicle/model` | HTTP 200，但业务 `code=500` |

因此当前没有获得有效的：

- `vehicleModelId → 车型名称`；
- `modelsId → 推荐车型名称`；
- 旧版车型 ID 与商城 `modelCode` 的映射；
- 旧版车型 ID 与现代 `productId` 的映射。

不得用商城代码填补这些空缺。

### 7.12 “App 支持所有车型”的准确边界

当前能够准确陈述：

> VOGE App 当前预约/商城业务接口能够枚举出 18 个车型代码；当前商城品牌目录有 16 个整车商品，对应 15 个不同 `modelCode`。

当前不能准确陈述：

> 这 18 个车型全部支持现代 IoT 定位、轨迹、油量、告警或其他联网能力。

原因：

1. `goodsAttributeSerApiService` 是预约车型目录；
2. `mallGoodsInfoPageList` 是商城商品目录；
3. 现代车辆 API 没有发现全局 `productId` 目录；
4. 测试账号只提供了一个现代绑定车辆样本；
5. 旧版车型目录当前没有返回可用数据；
6. App 可能识别不在当前预约/商城目录中的历史车辆；
7. 商城是否在售与车辆是否支持 IoT 没有必然关系。

当前证据等级应写成：

| 结论 | 证据等级 |
|---|---|
| `deviceName` 是现代车型显示名 | APK 静态已确认 + 授权只读实测 |
| 测试车辆 `deviceName=CU250 II代自动挡` | 授权只读实测 |
| 测试车辆 `productId=2` | 授权只读实测，仅限观测关联 |
| 预约目录有 18 个 `modelCode` | 授权只读实测 |
| 当前商城有 16 个整车商品 | 授权只读实测 |
| CU250 二代两个商品共用 `997` | 授权只读实测 |
| 18 个车型全部支持现代 IoT | 明确禁止推断 |
| `productId=2` 全局等于 CU250 二代自动挡 | 明确禁止推断 |

### 7.13 Home Assistant 全车型命名规则

已绑定现代车辆的显示名称优先级应统一为：

```text
deviceName
→ productName
→ ConfigEntry 已保存的显示名称
→ “VOGE product <productId>”
→ “VOGE Motorcycle”
```

推荐集中成一个辅助函数或一致的属性逻辑：

```python
def vehicle_display_name(
    vehicle: VehicleSnapshot,
    fallback: str | None = None,
) -> str:
    return (
        vehicle.device_name
        or vehicle.product_name
        or fallback
        or (
            f"VOGE product {vehicle.product_id}"
            if vehicle.product_id
            else None
        )
        or "VOGE Motorcycle"
    )
```

实现注意事项：

1. 车辆选择标签 `_vehicle_label` 应以 `deviceName` 开头，而不是先显示泛化 `productName` 或 `productId`；
2. ConfigEntry 标题应使用 `deviceName or productName`；
3. `DeviceInfo.model` 在 coordinator 已有数据时也必须检查 `deviceName`，不能只读取 `productName`；
4. `productId` 若保存到 `DeviceInfo.model_id` 或 diagnostics，必须标明它是现代 IoT 产品 ID；
5. 不要在 HA setup 或轮询过程中调用商城，只为显示名称维护商城会增加认证域、签名、限流和故障面；
6. 不要根据 `modelCode=997` 推断自动挡；精确“自动挡”来自现代绑定车辆的 `deviceName`；
7. 配置项唯一性仍使用设备/账户稳定 hash，不能因为多个车辆显示名相同而改变身份模型。

针对当前实现，以下两种写法都不够稳健：

```python
# 错误：现代测试车辆 productName 为 null
model = vehicle.product_name

# 错误：把不透明 IoT ID 当作车型显示名
model = f"VOGE product {vehicle.product_id}"
```

正确方向是：

```python
model = vehicle.device_name or vehicle.product_name or saved_display_name
```

商城车型表可以用于诊断、开发文档或用户主动查询，但不应成为现代车辆名称解析的运行时依赖。

---

## 8. 当前只读 API 契约

更完整的底层契约见 `CU250_READ_ONLY_API_CONTRACT.md`。本节给出开发时必须牢记的执行规则。

### 8.1 Endpoint 是代码声明，不是字符串拼接

`custom_components/voge/api.py` 用不可变 `Endpoint` 声明：

```python
Endpoint(
    name="modern.devices",
    base_url=MODERN_BASE_URL,
    path="/api/app/favorite/device",
    query_keys=frozenset(),
    modern=True,
    max_body_bytes=MODERN_MAX_BODY_BYTES,
)
```

`_validate_request` 在任何网络请求前检查：

- endpoint 对象是否属于 `_ALLOWED_ENDPOINTS`；
- query key 集合是否完全相等；
- base URL 是否 HTTPS；
- path 是否以 `/` 开始且没有 `..`。

不会提供：

- 任意 URL 参数；
- 任意 method 参数；
- 任意 path 参数；
- 任意 request body 参数；
- 任意 header 注入接口。

### 8.2 登录 POST 的隔离

账号密码登录确实是一个 POST，但它不应被误认为车辆读取白名单的一部分：

- `VogeAuthClient` 只暴露固定的 `login(mobile, password)`；
- host/path 在类内部固定；
- body 字段固定为 `mobile`、`password`；
- 不接受用户提供的 URL、method、headers 或额外 JSON；
- 数据 client 仍然只有各个固定 GET 方法；
- 禁止通过 public API 发送任意其他 POST/PUT/DELETE。

### 8.3 明确禁止 endpoint 类别

无论使用什么 HTTP method，都禁止：

- `/api/app/command/*`；
- `/api/app/favorite/up-default`；
- bind/del/bind-device；
- updateAppCarName、userDeviceCarNoUp、saveUserSettingStatus；
- digital key；
- device upgrade；
- account/profile/password/mobile mutation；
- 旧版 `contorl/*`、awaken、bind、update；
- JPush `bindRid`；
- message upReadStatus/delete/deleteAll；
- member notification/rule update；
- SMS/voice code；
- `gateway.do` 商城写入或未确认的商城认证调用。

### 8.4 TLS 和 redirect

使用 Home Assistant/aiohttp 标准 TLS：

- 系统 CA；
- hostname 校验；
- 不复制 APK 的 trust-all TLS；
- `allow_redirects=False`；
- 任何 3xx 都在本地拒绝；
- 不接受跨 host redirect。

日志中使用 endpoint 符号名，避免输出带完整 `deviceId`、`routeId` 或 token 的 URL。

---

## 9. 只读安全模型

### 9.1 威胁模型

需要防范：

1. 新开发者为了“兼容某个接口”加入任意 URL/HTTP method，绕过只读边界。
2. 默认车辆接口返回另一辆车的数据，却被错误合并到 CU250。
3. 401 触发无限登录/重试风暴。
4. 429 被立即重试，造成云端压力或账号临时封禁。
5. diagnostics、异常或日志泄露 token、MD5、手机号、VIN、坐标或消息正文。
6. 旧版 signer 被打进 tar.gz、APK 归档或 Git 历史。
7. 轨迹 routeId 被用户任意传入，变成跨车辆数据代理。
8. 账户级消息被错误归属到某一辆车。

### 9.2 防护分层

```text
固定 endpoint 声明
  ↓
query/path/host/TLS 本地校验
  ↓
HTTP 只读 client
  ↓
响应大小和 envelope 校验
  ↓
模型 parser 的类型/范围校验
  ↓
deviceId/routeId/VIN 身份校验
  ↓
coordinator 的独立刷新和错误隔离
  ↓
HA entity/action/event 的最小公开数据
  ↓
diagnostics/logging 递归脱敏
```

### 9.3 不能把“读取状态”与“修改状态”混淆

以下例子即使名字听起来像状态读取，也不应未经证据接入：

- `up-default`：会切换服务端默认车；
- `getDeviceSettingStatus`：配置状态且缺少显式车辆身份；
- `rule/{vehicleId}`：安全功能配置，不等于当前告警；
- message `ifRead`：只能读字段，不能因为它是未读就调用写接口。

---

## 10. 数据模型、解析和身份校验

### 10.1 `models.py` 的职责

`custom_components/voge/models.py` 将不稳定的服务端 JSON 转换成不可变 dataclass：

- `VehicleSnapshot`：M1 车辆快照；
- `DiagnosisSnapshot`：M2 综合诊断；
- `MonthSummary`：M3 月度摘要；
- `AlertMessage`：旧版消息；
- 辅助函数：`parse_vehicle`、`parse_vehicle_list`、`parse_diagnosis`、`parse_month_summary`、`parse_alert_message(s)`。

parser 的原则：

- 非 dict/list 输入返回空或 `None`，不崩溃；
- 必要身份字段缺失时丢弃记录；
- 数字字符串可解析；
- bool 不当作数字；
- `NaN`/无穷被拒绝；
- 空字符串、`null`、`none`、`-` 不被伪装成 0；
- 所有范围检查集中在 `util.py`，避免各 entity 自己猜范围。

### 10.2 `util.py` 的关键函数

- `stable_hash(value, length)`：生成稳定、不可逆的短标识，用于 HA identity；
- `redact_identifier(value)`：diagnostics 使用 `sha256:<prefix>…`；
- `parse_float`：有限浮点解析；
- `parse_int`：只有整数值才转为 int，不静默截断小数；
- `parse_percent`：支持数字和百分号字符串，限制 0–100；
- `parse_bounded_float`：范围校验；
- `parse_coordinate_pair`：纬度/经度范围和零坐标校验；
- `gcj02_to_wgs84`：中国境内 GCJ-02 逆变换；
- `parse_server_datetime`：按配置时区解析无 offset 的服务器时间。

### 10.3 `menu` 能力键

当前约定：

- `menu[key] == 1`：服务端宣称支持；
- `menu[key] == 0`：不启用新实体，已登记实体应保持 unavailable；
- 没有 key 但字段多次有效：可以保留为默认禁用候选，不能自动广泛暴露；
- 能力变化不自动删除 entity registry。

重要：`menu` 是服务端下发能力，不是车型名称的替代品。要把实体声明为 CU250 默认支持，至少需要目标车实测或稳定能力证据。

### 10.4 M1/M2 身份 join

M2 没有显式 `deviceId` query，因此：

```text
M1 vehicle.device_id
  == M2 diagnosis.device_id
  → 才能合并诊断
```

以下情况只保留 M1，丢弃 M2：

- M2 没有 deviceId；
- M2 deviceId 与配置目标不相等；
- M2 结构非法；
- M2 请求失败。

不能以“账户只有一辆车”“productName 一样”“当前位置相近”放宽严格匹配。

### 10.5 VIN 只用于实验性旧版关联

现代和旧版字段不能直接互换：

- `deviceId`；
- `deviceIdIot`；
- `amapDeviceId`；
- `deviceNum`；
- `vehicleId`。

只有现代 VIN 和旧版 VIN 都非空，trim + uppercase 后各侧恰好一个完全匹配，才允许实验性 L3/L4 关联。VIN 不进入日志、entity unique_id 或 diagnostics。

---

## 11. 坐标、时间和轨迹处理

### 11.1 当前坐标

静态证据表明现代坐标作为 GCJ-02 输入传给百度地图 SDK。处理顺序：

1. 优先 `geoLatitude`/`geoLongitude`；
2. 缺失时回退 `latitude`/`longitude`；
3. 验证纬度 `[-90,90]`、经度 `[-180,180]`；
4. 中国范围内执行 GCJ-02 → WGS84；
5. 中国范围外原样返回；
6. device tracker 输出 WGS84，除非用户关闭转换选项；
7. 不把现代坐标当 BD-09；
8. diagnostics 不输出精确坐标。

### 11.2 时间

服务器返回的时间通常没有时区后缀：

- `timeGen`：常见 `yyyy-MM-dd HH:mm:ss`；
- `createTime`：常见 `yyyy-MM-dd HH:mm:ss`；
- `gpsTime` 与 `gpsTimeStr` 必须分开保留；
- `locatetime` 的秒/毫秒单位尚未确认。

Home Assistant 选项 `server_timezone` 默认 `Asia/Shanghai`，这是当前临时假设，不是静态证明。解析为 timezone-aware datetime 后才交给 HA。

不同时间的含义：

| 时间 | 含义 |
|---|---|
| GPS update time | 车辆/设备上报 GPS 的时间 |
| Vehicle update time | 车辆诊断/云端工况时间 |
| Cloud fetch time | HA 成功拉取响应的 UTC 时间 |

不能用 HA fetch time 冒充车辆上报时间。

### 11.3 轨迹模型

`routes.py` 中的核心类型：

- `TrackPoint`：lat、lon、speed、direction、原始 locatetime；
- `TripSummary`：M4 单次行程摘要；
- `DayTripSummary`：M4 每日分组；
- `RouteDetail`：M5 已验证的单条轨迹。

`parse_route_detail` 要求：

- response 是 object；
- response routeId 若存在，必须等于 expected routeId；
- points 解析后至少有两个有效点；
- 损坏点可以丢弃，但不能把无效坐标变成 0；
- points 字符串非法 JSON 要返回安全的 `RouteParseError`，不打印原文。

### 11.4 GeoJSON

GeoJSON 坐标顺序必须是：

```text
[longitude, latitude]
```

单条 route 输出一个 `Feature` + `LineString`。按日输出 `FeatureCollection`，每个独立 route 作为一个独立 feature，不能跨停车/熄火间隙连接成一条虚假直线。

route 细节默认按需读取，不能塞入普通实体属性；actions 的 response 是合适的输出渠道。

---

## 12. Home Assistant 架构

### 12.1 总体调用图

```text
HA config flow / reauth
        │
        ▼
VogeAuthClient ──固定登录 POST──► modern login endpoint
        │
        ▼
VogeAuthManager
  ├── current token
  ├── password credentials (password mode only)
  ├── asyncio.Lock
  ├── update ConfigEntry token
  └── set_token(modern + legacy clients)
        │
        ├──────────────► VogeModernClient (GET-only)
        │                      │
        │                      ├── TelemetryCoordinator (M1+M2)
        │                      └── StatisticsCoordinator (M3)
        │
        └──────────────► VogeLegacyClient (GET-only, optional signer)
                               │
                               └── AlertCoordinator (L1)

TelemetryCoordinator ──► sensors + device_tracker
StatisticsCoordinator ─► monthly sensors
AlertCoordinator ──────► event entity + HA bus
Route services ────────► M4/M5, cache, GeoJSON response
Diagnostics ────────────► counts/flags only
```

### 12.2 模块职责

| 文件 | 职责 |
|---|---|
| `__init__.py` | HA setup、migration、client/coordinator 组装、unload |
| `const.py` | domain、认证键、endpoint 相关常量、轮询范围、事件类型 |
| `auth_manager.py` | 固定车辆密码登录、MD5、token single-flight、token 持久化 |
| `auth.py` | 旧版应用级 signer 数据类和 SM3 header 构造 |
| `api.py` | endpoint allowlist、modern/legacy GET transport、401/429/redirect/size guard |
| `config_flow.py` | 新建账号/密码或 token entry、车辆选择、reauth、options |
| `runtime.py` | 一条 ConfigEntry 的共享 clients/coordinators/cache |
| `coordinator.py` | telemetry/statistics/alerts 刷新和错误转换 |
| `models.py` | M1/M2/M3/消息解析与身份模型 |
| `routes.py` | M4/M5 行程、点、GeoJSON 解析 |
| `sensor.py` | 车辆和统计 sensor description/entity |
| `device_tracker.py` | 最后有效车辆位置 |
| `event.py` | 新告警 event entity 和 event bus |
| `services.py` | 三个 response-enabled 只读 action |
| `store.py` | 有限 message ID 去重持久化 |
| `diagnostics.py` | 不含秘密的诊断摘要 |
| `strings.json` + translations | HA UI 文案 |

### 12.3 RuntimeData

`VogeRuntimeData` 保存：

- `auth_manager`；
- `modern_client`；
- 可选 `legacy_client`；
- telemetry/statistics/alerts coordinators；
- 原始目标 `device_id`（仅运行时/ConfigEntry 内部使用）；
- hashed device/account key；
- product name；
- server timezone；
- coordinate conversion flag；
- route lock；
- month cache；
- route cache。

密码不能放进 coordinator data、entity attributes、event payload 或 route cache。

---

## 13. 配置流、ConfigEntry 和认证生命周期

### 13.1 新用户 flow

当前状态机：

```text
async_step_user
  ├── 默认显示 password mode
  ├── 用户选择 token mode → credentials(token)
  └── 用户选择 password mode → credentials(mobile, password)
          │
          ├── VogeAuthClient.login
          ├── GET M1 验证 token
          ├── 一个车辆：直接创建 entry
          └── 多个车辆：进入 vehicle 选择
```

车辆选择始终是 HA 本地选择：

- 不调用 `up-default`；
- 不修改服务端默认车辆；
- 将目标 `deviceId` 保存到 ConfigEntry；
- entity unique_id 使用 hash，不使用原始 ID。

### 13.2 ConfigEntry 数据

密码模式 entry 大致包含：

```python
{
    "auth_mode": "password",
    "token": "<current token>",
    "mobile": "<mobile stored locally>",
    "password": "<password stored locally>",
    "device_id": "<selected device id>",
    "product_name": "<saved display model name; prefer deviceName>",
    "product_id": "<optional opaque modern IoT product id>",
    "account_key": "<stable hash>",
}
```

token-only entry 不应包含手机号和密码：

```python
{
    "auth_mode": "token",
    "token": "<current token>",
    "device_id": "<selected device id>",
    "product_name": "<saved display model name; prefer deviceName>",
    "product_id": "<optional opaque modern IoT product id>",
    "account_key": "<stable hash>",
}
```

`product_name` 是为了兼容现有 ConfigEntry 键名而保留的本地显示名称槽位，不应被理解为必须原样保存服务端 `productName`。创建或迁移 entry 时应优先保存 `deviceName`，再回退到 `productName`。可选 `product_id` 只保存现代 IoT 返回的原始不透明 `productId`，不得写入商城 `modelCode`。

真实值只允许在 Home Assistant 本地 ConfigEntry 存储中存在。该集成没有额外声称提供密码加密仓库；保护 HA 主机、`.storage`、备份和文件权限是部署者责任。

### 13.3 Setup 顺序

`async_setup_entry`：

1. 从 entry 读取认证模式、token、手机号、密码和目标 deviceId；
2. 老 entry 没有 `auth_mode` 时按是否有手机号兼容判定；
3. 创建 `VogeAuthManager`；
4. 没有 token 时，密码模式调用固定登录，token-only 抛出认证失败；
5. 创建 modern client 并注册到 manager；
6. 根据本地 signer 是否存在决定是否创建 legacy client；
7. 创建 coordinators；
8. telemetry 首次刷新，严格寻找配置目标 deviceId；
9. statistics/alerts 按需刷新；
10. 转发 HA platforms；
11. unload 时关闭 manager、清理 route/month cache。

### 13.4 401 自动恢复

`_BaseReadOnlyClient._get`：

- 每次请求前读取当前 token；
- 收到 HTTP 401 或业务 code 401 时，调用受控 auth failure handler；
- handler 成功后重新生成 headers；
- 原请求只允许一次重试；
- 第二次认证失败直接抛出。

modern 和 legacy header 都是 callable，每次重试时读取当前 token，不能在 client 创建时永久冻结旧 token。

### 13.5 Reauth

密码 entry reauth：

- 再次输入手机号和密码；
- 固定车辆登录；
- 用只读 M1 验证；
- 必须仍然包含原目标 deviceId；
- 更新 token/mobile/password；
- 不改变目标 deviceId、entity unique_id 或服务端默认车辆。

token-only reauth：

- 输入 replacement token；
- 只读 M1 验证；
- 必须包含原目标 deviceId；
- 更新 token。

### 13.6 Migration

`ConfigFlow.VERSION` 当前为 `2`。旧的 token entry 如果没有 `auth_mode`，`async_migrate_entry` 会补为 token mode（如果没有手机号）。迁移不得把旧 token 当密码、不得自动调用未知 refresh endpoint。

### 13.7 Options flow

Options flow 当前只处理：

- telemetry interval：60–300 秒；
- statistics interval：900–3600 秒；
- alert interval：30–300 秒；
- server timezone；
- GCJ-02 转换开关；
- 是否启用旧版消息轮询。

认证凭据更新通过 reauth，而不是在用户没有重新提交密码时用空值覆盖 ConfigEntry。

---

## 14. 实体、事件和 response-enabled actions

### 14.1 Telemetry sensors

当前 `sensor.py` 定义的主要实体：

| entity key | API 来源 | 单位/类型 | 可用性规则 |
|---|---|---|---|
| `fuel_percentage` | M2 `fuelPercentage` | `%` | M2 身份匹配；已知占位 0% 可为 unknown |
| `remaining_fuel` | M2/M1 `restFuelLevel` | L | 优先 M2，回退 M1 |
| `fuel_consumption` | M1 `consumptionPerHundredKM` | L/100 km | 防御数值解析 |
| `remaining_range` | M1 `restTrip` | km | M1 能力/有效值 |
| `total_mileage` | M2/M1 `sumDistance` | km | 优先 M2，回退 M1 |
| `maximum_speed` | M1 `maxSpeed` | km/h | 有效值 |
| `monthly_duration` | M1 `durationMoStr` | 文本 | 原始文本 |
| `voltage` | M2 `voltage` | V | M2 能力和身份 |
| `coolant_temperature` | M2 `coolingTpr` | °C | 能力键缺失时默认禁用 |
| `front_tire_pressure` | M2 `frontTireP` | bar | 能力键缺失时默认禁用 |
| `rear_tire_pressure` | M2 `queenTireP` | bar | 能力键缺失时默认禁用 |
| `front_tire_temperature` | M2 `frontTireTpr` | °C | 能力键缺失时默认禁用 |
| `rear_tire_temperature` | M2 `queenTireTpr` | °C | 能力键缺失时默认禁用 |
| `next_maintenance_mileage` | M2 `nextUpkeepMileage` | km | 能力键缺失时默认禁用 |
| `harsh_acceleration_count` | M1 | 次 | diagnostic sensor |
| `harsh_deceleration_count` | M1 | 次 | diagnostic sensor |
| `harsh_steering_count` | M1 | 次 | diagnostic sensor |
| `bending_count` | M1 | 次 | diagnostic sensor |
| `bending_angle` | M1 | ° | diagnostic sensor |
| `gps_update_time` | M1 GPS fields | timestamp | 服务器时区解析 |
| `vehicle_update_time` | M2/M1 timeGen | timestamp | 服务器时区解析 |
| `cloud_fetch_time` | coordinator | UTC timestamp | HA 成功抓取时间 |

entity unique_id：

```text
<stable_device_hash>_<entity_key>
```

不要把 raw deviceId、VIN、token 或手机号放入 unique_id。

### 14.2 Monthly statistics sensors

`VogeStatisticsCoordinator` 使用显式 `deviceId` 的 M3：

- monthly mileage；
- average speed；
- 没有有效 M3 时安全回退到 M1 的对应字段（如果存在）。

M3 的 `duration` 单位未确认，因此不擅自建立带错误单位的 duration sensor。

### 14.3 Device tracker

`VogeDeviceTracker`：

- source type 为 GPS；
- latitude/longitude 使用内部转换后的 WGS84；
- 单次失败不将位置清零；
- extra attributes 只有坐标系和 diagnosis status；
- 不加入地址、deviceId、VIN、token 或原始响应。

### 14.4 告警 event entity

旧版 L1 是账户级消息接口，没有可靠的顶层车辆 ID。因此：

- event entity 归属于独立账户级设备 `VOGE Account Alerts`；
- 如果账户恰好一辆车，payload 可写 `single_vehicle_assumption`；
- 多车辆账户必须写 `account_level`；
- 不能根据标题、地址或自然语言猜车辆归属；
- 如果未来 `param` 出现明确 ID，需要重新设计验证和迁移。

已知 event type：

```text
fault_code
safe_riding
vibration
geofence
collision
low_voltage
low_data
anti_theft
device_disconnected
abnormal_movement
low_fuel
unknown
```

原始 type 映射：

| type | event type | 证据/备注 |
|---:|---|---|
| 1 | `fault_code` | 静态标签 |
| 2 | `safe_riding` | 静态标签 |
| 3 | `vibration` | 静态标签 |
| 4 | `geofence` | 静态标签 |
| 5 | `collision` | 静态标签 |
| 6 | `low_voltage` | 静态标签 |
| 7 | `low_data` | 静态标签 |
| 8 | `anti_theft` | 静态标签 |
| 9 | `device_disconnected` | 静态标签 |
| 10 | `abnormal_movement` | 拖车语义 |
| 13 | `low_fuel` | 静态标签 |
| 50 | `vibration` | 目前 `icon_only`，需真实消息确认 |
| 51–62 | `unknown` | 不猜语义 |

事件不是长期保持 on 的 binary sensor，因为消息没有可靠的恢复时间语义。

### 14.5 消息去重和首次基线

`AlertDedupStore`：

- 每个 ConfigEntry 最多保存最近 500 个稳定 message ID；
- messageId 缺失时根据稳定字段生成 SHA-256 synthetic ID；
- 不保存完整正文用于去重；
- 首次成功轮询只建立基线，不重放历史消息；
- 后续从第 1 页开始扫描；
- 遇到已知 ID、最后一页或安全页数上限就停止；
- 新消息按 createTime 从旧到新；
- event 成功发出后才 acknowledge；失败释放 inflight，允许重试。

### 14.6 Response-enabled actions

`services.py` 提供：

1. `voge.get_month_trips`
2. `voge.get_route_geojson`
3. `voge.get_day_geojson`

它们的共同规则：

- `config_entry_id` 必须是已加载的 VOGE entry；
- month 必须严格 `yyyy-MM`；
- routeId 必须来自同一 entry、同一月份的 M4；
- day 必须使用 M4 原样返回的 day 字符串；
- 使用 `route_lock` 避免缓存竞态；
- 使用 month cache TTL 5 分钟；
- 使用 route cache TTL 10 分钟；
- 不把完整轨迹写入实体属性；
- 不默认写入 `/config/www`。

`get_day_geojson` 对部分 route 失败时返回 `partial: true` 和错误数量，而不把不同 route 连接成虚假线段。

---

## 15. 错误、限流、陈旧数据和可用性

### 15.1 错误分类

| 异常 | 含义 | HA 行为 |
|---|---|---|
| `ReadOnlyViolation` | endpoint/query/path/安全边界违规 | 本地拒绝，不发请求 |
| `VogeAuthError` | HTTP/body 401、登录失败或 token 问题 | 一次恢复失败后进入 reauth |
| `VogeApiError` | 网络、HTTP、业务 code、JSON/大小问题 | coordinator 按普通更新失败处理 |
| `RouteParseError` | 轨迹结构/身份/点不足 | action 返回安全错误或 partial |
| `ConfigEntryAuthFailed` | HA 需要重新认证 | 触发标准 reauth |
| `UpdateFailed` | coordinator 一次读取失败 | 保留最后成功状态，等待下一次刷新 |

异常文本只应包含 endpoint 符号名、reason、HTTP status 或业务 code，不包含：

- token；
- 手机号；
- 密码或 MD5；
- 完整 URL query；
- 服务端 message 原文；
- 原始 response body。

### 15.2 401

HTTP 401 与 body `code == 401` 都必须处理。密码模式：

- lock 内重新登录一次；
- 更新所有 client 和 ConfigEntry token；
- 原始 GET 最多重试一次。

token-only：

- 没有密码，不能假装能 refresh；
- 进入 reauth；
- 不调用商城、club-auth、短信或 JPush。

### 15.3 429

当前策略：

- 读取 `Retry-After`；
- 数字或 HTTP date 都可尝试解析；
- clamp 到 1–3600 秒；
- 缺失/非法时使用从 30 秒开始的指数冷却，封顶 3600 秒；
- 请求内部不 sleep；
- 不立即重试；
- coordinator 下一次调度再尝试。

### 15.4 5xx、网络错误和超时

- 普通 API 总超时约 30 秒；
- route detail 可使用更长的 route timeout；
- 5xx/网络错误不在单次 request 内无限重试；
- 等待独立 coordinator 的下一次计划刷新；
- 不因车辆睡眠或数据时间戳老就提高频率；
- M1 失败时不继续请求 M2。

### 15.5 陈旧数据

数据刷新失败时应保留最后已知值，另外提供：

- GPS update time；
- vehicle update time；
- cloud fetch time；
- diagnosis status；
- coordinator last update success/exception type。

`device_tracker` 不因一次云端失败把位置变成空值或 0,0。

---

## 16. 隐私、日志和 diagnostics

### 16.1 不得公开的字段

以下字段都按秘密或个人数据处理：

- 主 token；
- `Mansuoid`；
- `Authorization`；
- refresh token；
- 明文密码；
- MD5 密码；
- 手机号/mobile/tel；
- VIN；
- `deviceId`、`deviceIdIot`、`amapDeviceId`、`deviceNum`、`vehicleId`；
- SIM ICCID/IMSI；
- 精确坐标；
- 精确地址；
- route points；
- 消息正文 content；
- 消息 param；
- 完整 message ID；
- APK access key 和 signing secret。

### 16.2 diagnostics 当前内容

`diagnostics.py` 可以输出：

- integration version；
- product name（注意不能由用户输入秘密生成）；
- hashed device/account key；
- timezone 和 coordinate conversion 开关；
- auth mode；
- token 是否 configured；
- mobile/password 是否 configured 的布尔值；
- coordinator success 和 exception type；
- vehicle count；
- 能力菜单（仅键和值；如果未来菜单来源不受控，要重新审查）；
- 数据是否有位置/诊断的布尔值；
- route/month cache 数量；
- alert 数量和 page scan 状态。

不得输出：

- token、手机号、密码、MD5、VIN、raw IDs；
- coordinates/address/route points；
- message body/param/IDs；
- private signer；
- 原始 API response。

### 16.3 测试方式

隐私测试应将真实敏感值替换为合成 needle，然后：

1. 构造包含 raw ID、坐标、VIN、token、消息正文的内部模型；
2. 调用 diagnostics；
3. 递归序列化输出；
4. 断言每个合成秘密均不出现；
5. 同时断言安全状态字段仍存在。

测试代码中的合成值也不能冒充真实用户数据。

---

## 17. 测试体系与验证命令

### 17.1 测试文件职责

| 文件 | 覆盖内容 |
|---|---|
| `test_auth.py` | MD5、固定登录 host/path/body、响应解析、401 重试、single-flight、token-only 不调用未知 refresh |
| `test_api_guard.py` | endpoint/query allowlist、禁止路径、非 TLS、控制/短信/JPush/商城路径拒绝 |
| `test_api_transport.py` | GET-only、redirect、401/429、Retry-After、cooldown、响应 envelope |
| `test_diagnostics.py` | diagnostics 递归敏感值排除 |
| `test_ha_setup.py` | HA 2026.9 setup、迁移、token compatibility、password flow、reauth、options |
| `test_ha_entities.py` | sensor/device tracker/entity 行为 |
| `test_models.py` | M1/M2/消息模型和防御数值解析 |
| `test_routes.py` | M4/M5、点、route identity、GeoJSON、partial |
| `test_sm3.py` | 旧版应用级签名算法（仅合成 credentials） |
| `test_util.py` | hash、数值、坐标、时间工具 |

所有网络测试都使用 fake session、mock response 或 `AsyncMock`，不联系生产服务。

### 17.2 当前基线

- Python：3.14.2；
- Home Assistant：2026.9.0；
- pytest：通过 uv 临时环境；
- 项目不是依赖 APK 运行时的 Python package。

### 17.3 推荐验证命令

从项目根目录执行：

```bash
PYTHONPATH="$PWD" uv run --python 3.14.2 \
  --with pytest --with aiohttp \
  pytest -q
```

HA 专项：

```bash
PYTHONPATH="$PWD" uv run --python 3.14.2 \
  --with pytest \
  --with pytest-homeassistant-custom-component \
  --with homeassistant==2026.9.0 \
  pytest -q --asyncio-mode=auto \
  tests/test_ha_entities.py \
  tests/test_ha_setup.py \
  tests/test_auth.py \
  tests/test_diagnostics.py
```

Ruff：

```bash
uv run --python 3.14.2 --with ruff \
  ruff check .
```

Pyright：

```bash
PYTHONPATH="$PWD" uv run --python 3.14.2 \
  --with pyright \
  --with homeassistant==2026.9.0 \
  --with pytest \
  pyright custom_components/voge tests
```

资源 JSON：

```bash
PYTHONPATH="$PWD" uv run --python 3.14.2 python -c '
import json
from pathlib import Path
for path in [
    Path("custom_components/voge/manifest.json"),
    Path("custom_components/voge/strings.json"),
    Path("custom_components/voge/translations/en.json"),
    Path("custom_components/voge/translations/zh-Hans.json"),
]:
    json.loads(path.read_text())
print("JSON resources valid")
'
```

编译检查：

```bash
PYTHONPATH="$PWD" uv run --python 3.14.2 python -c \
  'import compileall; raise SystemExit(0 if compileall.compile_dir("custom_components", quiet=1) else 1)'
```

编译后必须删除：

```text
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
```

### 17.4 不可接受的测试“通过”方式

- 不能为了通过测试放宽 endpoint allowlist；
- 不能用 `except Exception: pass` 吞掉身份错误；
- 不能把 token-only 失败改成调用未知 refresh；
- 不能把真实 token/密码写进 fixture；
- 不能用生产 API 作为普通单元测试依赖；
- 不能只测试 HTTP 200 而不测试业务 code 401/429；
- 不能把完整轨迹放进 entity attributes 来“方便断言”。

---

## 18. 安装、运行和旧版告警 signer

### 18.1 安装现代状态功能

将以下目录复制到 Home Assistant：

```text
/config/custom_components/voge
```

即复制：

```text
custom_components/voge/
```

然后重启 Home Assistant。

### 18.2 首次登录

1. 打开“设置 → 设备与服务”。
2. 添加 `VOGE Motorcycle`。
3. 默认选择 VOGE 账户密码模式。
4. 在 HA 本地表单输入手机号和密码。
5. 等待只读 M1 车辆列表验证。
6. 选择目标 CU250；多车辆时只在 HA 本地选择。
7. 完成配置后由集成自动保存当前 token，并在 token 失效时使用本地凭据重新登录。

密码不会通过聊天发送，也不应复制到日志或 issue。

### 18.3 token-only 高级模式

可以选择已有访问 token，但截至本文日期未实测。该模式不保存账号密码；token 失效后需要 HA reauth 输入 replacement token，不能期待自动恢复。

### 18.4 旧版告警 signer

现代车辆状态不依赖旧版 signer。若希望启用旧版消息告警，需要自己合法获得 APK/JADX 输出后，在本地运行：

```bash
python3 tools/extract_legacy_credentials.py \
  /path/to/HttpHeaderCommonInterceptor.java \
  custom_components/voge/_legacy_credentials.py
```

脚本不打印秘密，并设置文件权限为 `0600`。生成文件：

```text
custom_components/voge/_legacy_credentials.py
```

已经被 `.gitignore` 排除。不要：

- 提交该文件；
- 把它放进压缩包；
- 把它粘贴到 issue；
- 把它放进 diagnostics；
- 将真实值写进测试。

没有 signer 时：

- modern telemetry/statistics/route 仍可加载；
- legacy alert polling 明确禁用；
- 不应为了启用告警而放宽只读或隐私边界。

---

## 19. 故障排查手册

### 19.1 添加集成时登录失败

检查顺序：

1. 确认手机号/密码在官方 App 中可用；
2. 确认密码没有被聊天工具、shell 或 HA 前端额外改写；
3. 确认手机号外围空格不是账号的一部分；
4. 查看 HA 中的固定错误类型，不寻找或打印完整服务端 message；
5. 确认 HA 能解析 `iot-api.loncinindustries.com` 并完成正常 TLS；
6. 确认没有代理替换证书或跨 host redirect；
7. 重新认证时确认新账号仍绑定原目标 deviceId。

不要把密码、MD5 或 token 发给开发者排查。

### 19.2 token 过期后进入 reauth

密码模式正常行为是：

```text
旧 token 401 → 自动密码登录 → 新 token 持久化 → 原 GET 重试
```

如果最终仍进入 reauth：

- 账号密码可能已失效；
- 服务器拒绝登录；
- 新登录账号不再拥有原目标车辆；
- 第二次 GET 仍返回 401；
- 当前 entry 实际是 token-only mode；
- 发生了 API/网络故障而不是认证故障。

只需在 HA reauth 表单重新输入，不要手工编辑 ConfigEntry 中的 MD5。

### 19.3 车辆实体 unavailable

可能原因：

- M1 临时网络失败；
- M2 diagnosis identity 不匹配，被安全丢弃；
- 服务端 `menu` 明确表示不支持；
- 字段为空、越界、NaN 或占位符；
- coordinator 尚未成功初始化；
- target deviceId 不再被账号返回。

先查看 GPS/vehicle/cloud fetch timestamp 和 diagnostics 的布尔状态，不要立即增加轮询频率。

### 19.4 胎压/胎温/冷却液实体没有出现

这不一定是 bug。实体默认规则是：

- M2 返回身份必须匹配；
- 字段必须有效；
- 对明确需要能力支持的实体，`menu` 缺失时默认禁用；
- 不能因为通用 APK 模型有字段，就宣称 CU250 支持。

应收集脱敏 M1/M2 响应，保留字段名、productName/productId、menu key 和类型，删除秘密/ID/坐标/地址后再分析。

### 19.5 轨迹 action 失败

检查：

- month 是否为 `yyyy-MM`；
- day 是否原样来自 `get_month_trips`；
- route_id 是否来自同一 entry、同一月份；
- route response 是否含至少两个有效点；
- `points` 是否是有效 JSON 字符串；
- 是否因为部分 route 错误而返回 `partial: true`。

不要把用户手工猜的 routeId 直接作为 HTTP 参数代理出去。

### 19.6 没有告警 event entity

首先检查本地是否有 `_legacy_credentials.py`，但不要打印其内容。没有 signer 时集成会主动禁用旧版告警，这是预期行为，不影响 modern telemetry。

### 19.7 看到重复告警

检查：

- HA storage 是否被删除；
- ConfigEntry 是否被重新创建而不是迁移；
- `messageId` 是否为空导致 synthetic ID 输入变化；
- event entity 是否在 acknowledge 前发生异常；
- 是否刚完成首次基线（首次不应重放历史）。

不要通过调用消息已读接口“解决”重复问题。

---

## 20. 后续研究和开发路线

### 20.1 优先级 P0：维持当前可用性和安全性

- 继续保留账号密码自动恢复；
- 由用户实测 token-only 后，再更新其状态；
- 保持所有测试不访问生产；
- 不让新 endpoint 绕过 allowlist；
- 不让 diagnostics 泄露 ConfigEntry 密码/token。

### 20.2 优先级 P1：目标 CU250 脱敏响应

至少需要下列只读样本：

```http
GET https://iot-api.loncinindustries.com/api/app/favorite/device
```

建议脱敏保留：

- 字段名；
- `productName`、`productId`；
- 标识符种类但替换值；
- `menu` key 和 0/1；
- 返回车辆数量；
- 字段类型和是否为空。

必须删除或替换：

- token/Authorization/Mansuoid；
- 手机号；
- VIN；
- 完整 deviceId/deviceIdIot/amapDeviceId；
- SIM ID；
- 精确坐标和地址；
- 完整消息和 route points。

### 20.3 优先级 P1：M2 实测和字段启用矩阵

对目标 CU250 记录：

| 字段 | 是否出现 | 是否有效 | menu key | 身份是否匹配 | 是否建实体 |
|---|---|---|---|---|---|
| `fuelPercentage` | 待填 | 待填 | 待填 | 必须是 | 已有候选 |
| `restFuelLevel` | 待填 | 待填 | 待填 | 必须是 | 已有候选 |
| `voltage` | 待填 | 待填 | 待填 | 必须是 | 已有候选 |
| `coolingTpr` | 待填 | 待填 | 待填 | 必须是 | 条件启用 |
| `frontTireP` | 待填 | 待填 | 待填 | 必须是 | 条件启用 |
| `queenTireP` | 待填 | 待填 | 待填 | 必须是 | 条件启用 |
| `frontTireTpr` | 待填 | 待填 | 待填 | 必须是 | 条件启用 |
| `queenTireTpr` | 待填 | 待填 | 待填 | 必须是 | 条件启用 |
| `canList` | 待填 | 待填 | 待填 | 必须是 | 默认不动态建实体 |

### 20.4 优先级 P2：动态 CAN

只有同时满足以下条件，才建立固定 CAN 映射：

- 稳定 `id` 或 `codeValue`；
- 稳定 `desc`/`unit`；
- 多次目标 CU250 响应一致；
- `value` 的换算语义确认；
- 不会因服务端文案变化导致 unique_id 漂移；
- 默认禁用并可回滚。

候选但当前禁止直接开放：

- RPM；
- 当前速度；
- 挡位；
- 点火状态；
- 在线/睡眠状态。

不要盲目重复 `coefficient`/`offset`，除非确认服务端 value 尚未换算。

### 20.5 优先级 P2：旧版 L3/L4

L4 旧版实时数据候选包括：

- rpm；
- speed；
- gear；
- ign；
- online/sleep；
- front/rear pressure；
- mileage；
- updateTime。

启用前必须：

1. L3 通过唯一 VIN 关联；
2. 用户显式开启实验选项；
3. 多次响应证明不是固定零值/占位值；
4. 时间和身份与 modern 目标车一致；
5. 有专项测试和回滚路径。

### 20.6 优先级 P3：统计、告警语义和时间

待确认：

- M6/M7 实际调用和字段；
- `rafe` 语义/单位；
- M3 duration 单位；
- `locatetime` 秒还是毫秒；
- message `param` 是否含明确车辆身份；
- vibration 是 type 3、50 还是两者；
- type 51–62；
- server timezone；
- token 生命周期和限流策略。

每项都要增加证据记录和合成测试，不能只改一个字段映射就宣称完成。

---

## 21. 给后续 LLM 的工作规则

### 21.1 开始任务前

1. 先读本文件和 `CU250_READ_ONLY_API_CONTRACT.md`；
2. 再读目标代码和对应测试；
3. 明确需求是研究、文档、解析、实体还是 transport；
4. 检查当前证据等级；
5. 不把其它车型字段当作 CU250 证据；
6. 不要求用户在对话中发送密码/token/坐标。

### 21.2 修改认证时

- 只能使用固定 `/api/login/loginByMobile`；
- 保留密码不 trim 的 MD5 兼容行为；
- 不把 MD5 当非敏感数据；
- 不能把商城 refreshToken 或 `club-auth/refresh` 当作已确认 refresh；
- 不能加入 SMS/JPush；
- 401 必须有 retry guard；
- 并发登录必须 single-flight；
- token 更新必须同步所有 clients；
- entry token 要持久化，但不能记录到日志。

### 21.3 修改数据 API 时

- 先添加不可变 `Endpoint`；
- 显式声明 query keys；
- 保持 GET-only；
- 更新 `_ALLOWED_ENDPOINTS` 时同时更新 guard 测试；
- 新 path 不能接受用户任意拼接；
- 对默认车辆接口做身份核对；
- 对 routeId 做来源核对；
- 不增加控制/写入 API。

### 21.4 修改实体时

- 使用 coordinator data，不直接请求 API；
- 遵守 `menu` 和有效值规则；
- 不把完整 raw response 放 attributes；
- 不把坐标、地址、VIN、token 放 unique_id；
- 不因一次刷新失败清零最后有效值；
- 新字段先标为待实测，必要时默认禁用。

### 21.5 修改告警时

- L1 是账户级，不要假装它是车辆级；
- 未知 type 保留为 unknown；
- 不调用已读/删除；
- 首次轮询建立基线；
- 先发事件，成功后 acknowledge；
- message content/param 不能进入 diagnostics。

### 21.6 修改文档或提交时

- 文档中的“已验证”必须有实际证据；
- 当前应写“账号密码已实测、token-only 未实测”；
- 不提交 APK（除非另有明确安全策略）；
- 不提交 `_legacy_credentials.py`；
- 不提交包含该文件的 archive；
- 不提交 `.venv`、cache、raw JADX output 或响应 fixture；
- commit 前扫描 staged tree，而不是只扫描工作区。

---

## 22. 关键文件地图

### 22.1 根目录文档和配置

- `README.md`：用户安装、登录、功能和安全说明；
- `CU250_READ_ONLY_API_CONTRACT.md`：底层 endpoint/字段/只读契约；
- `docs/APK_ANALYSIS_AND_DEVELOPMENT.md`：本工程知识库；
- `pyproject.toml`：Python、pytest、Ruff、Pyright 基线；
- `.gitignore`：APK、私有 signer、缓存、HA 本地状态和生成 archive；
- `hacs.json`：HACS 元数据；
- `uv.lock`：开发依赖锁定信息。

### 22.2 集成源代码

- `custom_components/voge/__init__.py`：生命周期入口；
- `custom_components/voge/auth_manager.py`：现代车辆登录和 token 管理；
- `custom_components/voge/api.py`：transport 和 allowlist；
- `custom_components/voge/auth.py`：旧版 SM3 signer；
- `custom_components/voge/config_flow.py`：登录/车辆/reauth/options；
- `custom_components/voge/const.py`：常量；
- `custom_components/voge/runtime.py`：共享运行时；
- `custom_components/voge/coordinator.py`：刷新协调；
- `custom_components/voge/models.py`：车辆/诊断/消息 parser；
- `custom_components/voge/routes.py`：轨迹 parser/GeoJSON；
- `custom_components/voge/sensor.py`：sensor；
- `custom_components/voge/device_tracker.py`：位置；
- `custom_components/voge/event.py`：告警事件；
- `custom_components/voge/services.py`：response actions；
- `custom_components/voge/store.py`：message ID store；
- `custom_components/voge/diagnostics.py`：脱敏诊断；
- `custom_components/voge/strings.json`、`translations/`：UI 文案。

### 22.3 测试和工具

- `tests/test_auth.py`：认证；
- `tests/test_api_guard.py`：只读边界；
- `tests/test_api_transport.py`：transport；
- `tests/test_ha_setup.py`：HA flow/setup/reauth；
- `tests/test_diagnostics.py`：隐私；
- `tests/test_ha_entities.py`：实体；
- `tests/test_models.py`：模型；
- `tests/test_routes.py`：轨迹；
- `tests/test_sm3.py`：SM3；
- `tests/test_util.py`：工具；
- `tools/extract_legacy_credentials.py`：本地生成私密 signer，不打印值。

### 22.4 明确不提交的文件

- `VOGE-release-product-arm64-V1.3.3-code-49.apk`；
- `custom_components/voge/_legacy_credentials.py`；
- `custom_components/voge.tar.gz`；
- `.venv/`；
- `__pycache__/`、`*.pyc`；
- `.pytest_cache/`、`.ruff_cache/`；
- raw JADX output；
- 真实 API response；
- HA `.storage/`、数据库和 secrets 文件。

---

## 23. 术语表

| 术语 | 含义 |
|---|---|
| M1 | 现代 API 车辆列表/基础状态：`favorite/device` |
| M2 | 现代 API 综合诊断：`synthesize-diagnosis` |
| M3 | 当前月摘要：`favorite/index` |
| M4 | 月度行程列表：`car-track-new` |
| M5 | 单条轨迹：`locus` |
| M6 | 月度驾驶行为/雷达评分：`behavior` |
| M7 | 月度骑行数据：`riding` |
| M8 | 功能代码发现：`getConfigCodes` |
| L1 | 旧版账户消息分页 |
| L2 | 旧版单条消息详情 |
| L3 | 旧版绑定车辆列表 |
| L4 | 旧版实时车辆数据，实验性 |
| `Mansuoid` | 现代车辆 API 使用的主 token header |
| `bicoseToken` | 现代登录响应中的另一个 token 字段，当前用途未确认 |
| `refreshToken` | 当前只在商城响应模型中确认，不能与车辆 token 混用 |
| M1/M2 join | 用严格 deviceId 将车辆列表和诊断结果合并 |
| single-flight | 并发认证失败时只允许一个登录请求 |
| GCJ-02 | 中国地图坐标系，现代 API 坐标的静态推断来源 |
| WGS84 | Home Assistant device tracker 对外使用的坐标系 |
| `menu` | 服务端下发的能力键/开关 |
| `canList` | 动态 CAN 字段列表，不能直接全部变成实体 |
| reauth | Home Assistant 标准重新认证流程 |
| ConfigEntry | Home Assistant 本地集成配置项 |
| response-enabled action | 通过 HA service/action 返回 JSON/GeoJSON，而不是写入实体属性 |

---

## 24. 发布和提交前 checklist

### 24.1 代码正确性

- [ ] 账号密码登录仍只访问固定 modern login endpoint；
- [ ] password 不 trim，手机号只做合理外围清理；
- [ ] 只提取 `result.token`；
- [ ] modern/legacy data client 仍严格 GET-only；
- [ ] endpoint/query/host/TLS/redirect/size guard 测试通过；
- [ ] 401 最多恢复并重试一次；
- [ ] 并发 401 single-flight；
- [ ] 429 有 cooldown，不在 request 内 sleep；
- [ ] M2 严格 deviceId 匹配；
- [ ] routeId 来源验证；
- [ ] vehicle identity 不被默认车辆接口混淆；
- [ ] 车型显示优先使用 `deviceName`，`productName` 只作回退；
- [ ] modern `productId` 没有被商城 `modelCode` 覆盖或静态猜测；
- [ ] `modelCode=997` 没有被描述为 CU250 AMT 专属代码；
- [ ] token-only 仍标记为未实测，而不是伪造验证结果。

### 24.2 Home Assistant 行为

- [ ] 新 flow 默认账号密码；
- [ ] token-only 明确是高级模式；
- [ ] reauth 保持目标 deviceId；
- [ ] migration 不破坏旧 entry；
- [ ] options 不用空密码覆盖旧密码；
- [ ] entity unique_id 不含 raw ID；
- [ ] 车辆选择标签、ConfigEntry 标题和 `DeviceInfo.model` 使用一致的车型名称优先级；
- [ ] HA setup/轮询不依赖商城目录来解析现代车辆名称；
- [ ] event entity 账户级归属；
- [ ] route actions 是 response-enabled；
- [ ] 轨迹不进入普通 attributes；
- [ ] 卸载清除密码引用和 route cache。

### 24.3 隐私与安全

- [ ] 没有 token、手机号、明文密码、MD5、VIN、raw ID、SIM ID、坐标、地址、消息正文；
- [ ] 没有 APK access key/signing secret；
- [ ] 没有 `_legacy_credentials.py`；
- [ ] 没有包含私有 signer 的 tar/zip；
- [ ] 没有 APK 二进制（按当前仓库策略）；
- [ ] 没有 raw JADX output；
- [ ] diagnostics 递归扫描通过；
- [ ] 日志不会打印完整 URL/header/body；
- [ ] 没有新增 SMS/JPush/商城/控制调用；
- [ ] 使用正常 CA/hostname 校验。

### 24.4 工具和 Git

- [ ] pytest 全部通过，跳过项有解释；
- [ ] HA 2026.9.0 专项测试通过；
- [ ] Ruff 通过；
- [ ] Pyright 通过；
- [ ] JSON 资源通过解析；
- [ ] compileall 通过；
- [ ] 清理所有缓存；
- [ ] `git diff --cached --name-status` 只显示安全源代码/文档/测试；
- [ ] `git ls-files` 不包含 APK、私有 signer、archive、`.venv` 或 secrets；
- [ ] staged tree 再做一次敏感值扫描；
- [ ] 发布说明准确区分“账号密码已实测”和“token-only 未实测”。

---

## 当前结论

当前最可靠的交付结论是：

1. 官方 APK 静态证据支持现代车辆账号密码登录；
2. 用户已经实测账号密码登录通过；
3. 现代车辆访问主 token 是 `LoginResponse.token`，通过 `Mansuoid` 使用；
4. 代码具备密码模式自动 token 恢复，但 token-only 尚未实测；
5. 授权只读实测确认现代车辆车型名称应优先读取 `deviceName`；测试车辆返回 `CU250 II代自动挡`，而 `productName=null`；
6. 测试车辆的 `productId=2` 仅是单条绑定车辆上的观测关联，不能升级为全局 `productId → 车型` 映射；
7. 当前预约业务目录可枚举 18 个 `modelCode`，当前商城有 16 个整车商品和 15 个不同 `modelCode`；
8. CU250 二代普通/自动挡两个商城商品共用 `modelCode=997`，因此 `997` 不是 AMT 专属代码；
9. modern `productId`、预约/商城 `modelCode`、`tlineCode`、商城分类 ID、商品 ID、业务 `code`、旧版 `vehicleModelId` 和推荐 `modelsId` 必须严格隔离；
10. 当前没有获得全量 modern `productId` 目录，也没有获得有效旧版 `vehicleModelId` 或推荐 `modelsId` 映射；
11. modern data API 和 legacy message API 均受严格只读 allowlist 限制；车型目录调查使用独立的受控只读脚本，不应成为 HA 运行时依赖；
12. 商城 refresh、未知 refresh、短信、JPush 和控制接口均不属于当前实现；
13. 18 个业务车型不能被描述为 18 个已确认支持现代 IoT 的车型，目标 CU250 的具体遥测能力仍必须由脱敏真实响应确认；
14. 任何未来扩展都必须先满足证据、身份、隐私和只读安全要求。
