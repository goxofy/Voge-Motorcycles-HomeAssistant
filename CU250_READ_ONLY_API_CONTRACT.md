# VOGE CU250 二代 AMT：只读 API 与 Home Assistant 接入契约

> 目标车辆：2026 款 VOGE/无极 CU250 二代 AMT 自动挡。
>
> 静态分析对象：`VOGE-release-product-arm64-V1.3.3-code-49.apk`。
>
> 本文只定义读取、解析和 Home Assistant 映射。禁止车辆控制、账户修改、设备绑定、默认车辆切换、消息已读/删除、通知设置修改以及 JPush 注册绑定。

## 1. 当前证据边界

### 1.1 已由 APK 静态分析确认

- Android 包名：`com.jczy.voge`
- 版本：`1.3.3`，versionCode `49`
- Flavor：`productArm64`
- APK SHA-256：`218242102ad27aeab1eb13c9e8bd1012bfcbf48ef1093092679ac720154a444e`
- APK 使用单一 RSA-2048 签名者，APK Signature Scheme v2。
- 现代燃油摩托车 API、旧版/通用 API 的 host、Retrofit 路径、请求头、响应包装模型和认证失效逻辑。
- 现代车辆列表、综合诊断、月度统计、轨迹列表、单条轨迹、骑行数据、驾驶行为模型。
- 旧版车辆消息分页接口及已知消息类型。
- 现代地图坐标按 GCJ-02 传给百度地图 SDK。

### 1.2 尚未进行

- 未运行 APK。
- 未登录用户账户。
- 未请求、接收或使用用户密码。
- 未调用厂商线上生产 API。
- 未发送任何车辆控制命令。
- 未获得 CU250 的真实、脱敏接口响应。

因此，本文是“可实施的静态契约”，不是对目标 CU250 实车能力的最终确认。

### 1.3 仍需真实脱敏响应确认

至少需要一次只读响应：

```http
GET https://iot-api.loncinindustries.com/api/app/favorite/device
```

响应应保留：

- 字段名
- `productName`
- `productId`
- 标识符种类
- `menu` 能力键
- 匹配车辆数量

必须替换或删除：

- token
- 手机号
- VIN
- 完整 `deviceId`、`deviceIdIot`、`amapDeviceId`
- SIM ICCID/IMSI
- 精确经纬度
- 精确地址

## 2. 后端与认证协议

## 2.1 现代燃油摩托车 IoT API

Base URL：

```text
https://iot-api.loncinindustries.com/
```

目标 CU250 的主要认证头：

```http
Content-Language: zh_CN
Platform: ANDROID
Mansuoid: <用户访问令牌>
Blade-Auth:
version: 1.3.3
PhoneModel: HomeAssistant/<集成版本>
Source: VOGE
```

规则：

- `Mansuoid` 直接使用登录后返回的主 token。
- CU250 是燃油摩托车路径，不使用电摩/Bicose token。
- `Blade-Auth` 在原 App 中会被加入；燃油车场景值为空。集成可以发送空值，也可以在实测确认无需该头后省略。
- 现代 IoT 请求没有每次请求签名。
- 集成必须使用正常系统 CA 和 hostname 校验；不得复制 APK 的 trust-all TLS 行为。
- 禁止跟随到其他 host 的重定向。

现代响应包装：

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

判定：

- 业务成功：`code == 200`
- 认证失效：HTTP `401` 或响应体 `code == 401`
- 对认证失效不得无限重试；Home Assistant 中转换为 `ConfigEntryAuthFailed` 并启动 reauth。
- `success` 可以作为辅助信息，但不得替代 `code == 200`。
- 其他业务 code 抛出已脱敏的 API 异常，不记录完整响应体。

## 2.2 旧版/通用 API

Base URL：

```text
https://voge.loncinindustries.com/api/
```

请求头：

```http
accessKey: <APK 内置应用访问键，本文不披露>
timestamp: <Unix epoch 毫秒>
nonce: <带连字符 UUID>
signature: <SM3 小写十六进制>
Authorization: <同一个用户主 token>
```

签名输入：

1. 构造 `accessKey`、`timestamp`、`nonce`。
2. 按字段名 Unicode/字典序升序排序。
3. 对每个非空值拼接 `key=value`。
4. 字段之间不添加 `&`、换行或其他分隔符。
5. 末尾追加 APK 内置应用 secret。
6. 对 UTF-8 字节执行 SM3。
7. 输出小写十六进制。

等价伪代码：

```python
signing_text = "".join(
    f"{key}={value}"
    for key, value in sorted(fields.items())
    if value not in (None, "")
) + app_secret
signature = sm3(signing_text.encode("utf-8")).hex()
```

旧版响应包装：

```json
{
  "code": 0,
  "msg": "...",
  "data": {},
  "errorCode": null
}
```

判定：

- 业务成功：`code == 0`
- 认证失效：HTTP `401` 或响应体 `code == 401`
- 认证失效同样转换为 `ConfigEntryAuthFailed`。
- APK 内置应用访问键、签名 secret 不进入日志、诊断或用户界面。

## 3. 强制只读网络守卫

HTTP 客户端必须在发出网络请求前检查三元组：

```text
(method, exact_host, normalized_path)
```

同时检查允许的 query 参数集合。

要求：

- 默认客户端仅实现 `GET`。
- 不提供接受任意 URL 或任意路径的公共方法。
- 不允许 path traversal、双重编码或跨 host 重定向。
- URL 日志只记录符号化 endpoint 名称，不记录含 `deviceId`、`routeId` 的完整 URL。
- 即使某个写操作错误地使用 `GET`，只要路径不在白名单中也必须在本地拒绝。
- 登录接口与车辆数据客户端分离；首版采用 token-only，不把任何登录 POST 放入车辆读取白名单。

建议代码结构：

```python
ALLOWED_REQUESTS = {
    ("GET", MODERN_HOST, "/api/app/favorite/device"): frozenset(),
    # 其余路径逐项声明
}
```

任何未精确匹配的请求应抛出 `ReadOnlyViolation`，不得尝试发送。

## 4. 首版现代 API 白名单

## 4.1 M1：绑定车辆与基础状态

```http
GET /api/app/favorite/device
```

Query：无。

响应：

```text
BaseMotoModel<ArrayList<MotoItem>>
```

用途：

- 验证 token。
- 列出账户绑定车辆。
- 找到目标 CU250。
- 获取当前/最近位置、GPS 时间、里程、月里程、油耗、剩余油量、续航和骑行行为计数等。
- 读取服务端下发的 `menu` 能力表。

建议轮询：90 秒，允许配置为 60–300 秒。

不得因数据陈旧而提高频率，也不得调用唤醒命令。

## 4.2 M2：综合诊断/车辆工况

```http
GET /api/app/favorite/synthesize-diagnosis
```

Query：无。

响应可以按兼容联合模型解析，已发现的模型包括：

- `MotoMainPage`
- `MotoInfoDetailBean`
- `CompositeReportResponseData`

可用字段候选：

- `deviceId`
- `fuelPercentage`
- `restFuelLevel`
- `sumDistance`
- `voltage`
- `coolingTpr`
- `frontTireP`
- `frontTireTpr`
- `queenTireP`（后轮胎压）
- `queenTireTpr`（后轮胎温度）
- `nextUpkeepMileage`
- `timeGen`
- `canList`
- `menu`
- `rafe`（语义未知，首版不建实体）

关键身份规则：

- 该接口没有 `deviceId` query，极可能返回服务端默认车辆。
- 只有当响应 `result.deviceId` 非空且严格等于已选择的 `MotoItem.deviceId` 时，才可把数据合并到 CU250。
- 如果 `deviceId` 缺失或不匹配，丢弃本次综合诊断数据并记录不含实际 ID 的警告。
- 即使账户目前只有一辆车，也不放宽上述校验。
- 绝不调用 `PUT /api/app/favorite/up-default` 切换默认车辆。

建议轮询：与 M1 同一个 coordinator，90 秒。

## 4.3 M3：当前月摘要

```http
GET /api/app/favorite/index?deviceId=<modern_device_id>
```

允许 query：仅 `deviceId`。

响应：

```text
BaseMotoModel<CurrentMotoMonthDataBean>
```

字段：

- `aveSpeed`
- `deviceId`
- `distance`
- `duration`
- `geoLatitude`
- `geoLongitude`
- `gpsTime`

规则：

- 请求必须使用从 M1 选中的 `MotoItem.deviceId`。
- 如果响应包含 `deviceId`，必须再次核对。
- `duration` 单位尚需真实响应确认；首版保留原始值，不擅自生成带单位传感器。

建议轮询：15–30 分钟。

## 4.4 M4：按月获取轨迹和行程列表

```http
GET /api/app/favorite/car-track-new?deviceId=<modern_device_id>&month=<yyyy-MM>
```

允许 query：`deviceId`、`month`。

`month` 格式由 APK 确认为：

```text
yyyy-MM
```

响应：

```text
BaseMotoModel<ArrayList<MotoTrackSumItem>>
```

每日摘要字段：

- `day`
- `distanceMo`
- `durationMo`
- `durationMoStr`
- `driveTotalTimes`
- `aveSpeed`
- `maxSpeed`
- `bendingAngle`
- `bendingCount`
- `list`

单次行程字段：

- `routeId`
- `beginDate`
- `endDate`
- `beginAddr`
- `endAddr`
- `beginLatitude`
- `beginLongitude`
- `endLatitude`
- `endLongitude`
- `distanceMo`
- `durationMo`
- `durationMoStr`
- `aveSpeed`
- `maxSpeed`
- `accumulation`
- `bendingAngle`
- `bendingCount`

规则：

- `day` 的实际文本格式由服务器提供，静态分析未能确定；不得自行硬编码。
- `routeId` 只能作为 M5 的来源，不接受用户任意拼接后直接请求。
- 轨迹列表按月按需获取；当前月最多每 15–30 分钟刷新一次，历史月份优先缓存或按需请求。

## 4.5 M5：按已验证 routeId 获取单条轨迹

```http
GET /api/app/favorite/locus?routeId=<verified_route_id>
```

允许 query：仅 `routeId`。

响应：

```text
BaseMotoModel<MotoTrackByIdItem>
```

重要字段：

- `routeId`
- `beginAddr`
- `endAddr`
- `crtDate`
- `distanceMo`
- `durationMo`
- `durationMoStr`
- `maxSpeed`
- `sumDistance`
- `points`
- 急加速、急减速、急转弯、压弯和超速相关摘要

`points` 不是数组本身，而是“包含 JSON 数组的字符串”：

```json
{
  "points": "[{\"lat\":\"29.x\",\"lon\":\"106.x\",\"speed\":42.5,\"direction\":123.4,\"locatetime\":1234567890}]"
}
```

安全规则：

- `routeId` 必须来自同一目标 `deviceId` 的 M4 返回结果。
- 如果响应包含 `routeId`，应与请求值核对。
- 不允许直接提供任意 routeId 的通用 HTTP 代理服务。
- 默认按需调用，不参与周期轮询。

## 4.6 M6：月度驾驶行为/雷达评分

```http
GET /api/app/favorite/behavior?deviceId=<modern_device_id>&month=<server_month>
```

允许 query：`deviceId`、`month`。

响应：

```text
BaseMotoModel<RadarRating>
```

字段包括：

- `analyse`
- `synthesize`
- `fahrverhaltenRanking`

隐私规则：

- 只保留目标 CU250 自身的评分和行为摘要。
- 不持久化排行榜中其他用户的手机号、头像、VIN、设备 ID 或昵称。
- 如果无法明确识别自身记录，则不导入排行榜记录。

`month` 参数名在 Java/Kotlin 方法签名中也出现为 `yearMonth`；实际格式需真实响应或调用点进一步确认。首版可以仅在已确认当前调用格式后启用。

建议轮询：30–60 分钟。

## 4.7 M7：月度骑行数据

```http
GET /api/app/favorite/riding?deviceId=<modern_device_id>&month=<server_month>
```

允许 query：`deviceId`、`month`。

响应：

```text
BaseMotoModel<MotoMonthRideData>
```

字段：

- `sumDistance`
- `day[]`
  - `day`
  - `distance`
  - `today`
    - `distanceMo`
    - `durationMo`
    - `durationMoStr`
    - `maxSpeed`
    - 急加速、急减速、急转弯、压弯次数和最大角度

建议轮询：30–60 分钟。

## 4.8 M8：功能代码发现（可选）

```http
GET /api/app/operateConfig/getConfigCodes
```

响应：

```text
BaseMotoModel<List<String>>
```

只用于功能发现，不应覆盖 M1/M2 的车辆级 `menu` 能力判断。首版可以不调用。

## 5. 首版旧版 API 白名单

旧版 API 仅用于消息告警，以及在严格身份匹配后进行实验性数据补充。

## 5.1 L1：车辆告警消息分页

```http
GET /voge-system/app/message/page?module=1&pageSize=<n>&pageNum=<n>
```

允许 query：

- `module`，必须固定为 `1`
- `pageSize`
- `pageNum`
- `clubType` 必须省略

响应：

```text
BaseModel<BasePageModel<MessageModel>>
```

分页结构：

```json
{
  "current": 1,
  "pages": 1,
  "records": [],
  "size": 50,
  "total": 0
}
```

`MessageModel` 字段：

- `messageId`
- `module`
- `type`
- `title`
- `content`
- `createTime`
- `ifRead`
- `memberId`
- `param`

规则：

- `pageNum` 从 `1` 开始。
- 建议 `pageSize=50`。
- `param` 可能是对象、数组、字符串化 JSON 或未知标量，必须按 JSON-compatible 原值保留并防御式解析。
- 不因 `param` 未知而丢弃消息。
- `content` 优先保留原文；如果它是文本/颜色片段数组，可另生成纯文本版本。
- `ifRead` 只作为只读元数据，不得用于触发写操作。

建议轮询：45 秒，允许配置为 30–300 秒。

## 5.2 L2：单条消息详情（默认不自动调用）

```http
GET /voge-system/app/message/info?messageId=<message_id>
```

响应：

```text
BaseModel<MessageModel>
```

页面列表已经包含标题、内容和时间，因此首版周期轮询不需要逐条调用详情。只在未来明确发现详情含必要字段时启用。

## 5.3 L3：旧版绑定车辆列表（实验性身份关联）

```http
GET /moto/app/vehicle/excludeShareVehicle
```

响应：

```text
BaseModel<List<VehicleModel>>
```

相关字段：

- `vehicleId`
- `deviceNum`
- `deviceType`
- `vin`
- `modelName`
- `modelNickname`
- `locationLat`
- `locationLon`
- `positionTime`
- `updateTime`
- `mileage`
- `carOnline`
- `energySaving`

身份关联只能使用：

1. 现代 M1 中目标车辆 VIN 非空。
2. 旧版列表中 VIN 非空。
3. 对 VIN 执行 `trim + uppercase` 后完全相等。
4. 现代侧恰好一个匹配项。
5. 旧版侧恰好一个匹配项。

如果任一条件不满足，禁止启用旧版车辆级补充。

不得假设以下字段可互换：

- `deviceId`
- `deviceIdIot`
- `amapDeviceId`
- `deviceNum`
- `vehicleId`

## 5.4 L4：旧版实时数据（默认禁用、实验性）

```http
GET /moto/app/vehicle/body/{legacy_vehicle_id}
```

响应：

```text
BaseModel<RTModel>
```

候选字段：

- `antiTheftStatus`
- `frontPressure`
- `rearPressure`
- `gearPostion`
- `ign`
- `mileage`
- `oilMeter`
- `onlineStatus`
- `sleepStatus`
- `powerSaving`
- `powerStatus`
- `rpm`
- `speed`
- `rssi`
- `sate`
- `updateTime`

启用条件：

- L3 已通过唯一 VIN 关联得到唯一 `vehicleId`。
- 用户显式打开“实验性旧版实时数据”。
- 连续多个只读响应证明字段不是固定零值、占位值或其他车型数据。
- 响应身份和时间与现代目标车辆能够合理对应。

静态分析发现当前 V2 仪表盘没有调用该接口，因此其存在不代表 CU250 支持。

建议轮询：

- 活跃且持续更新时：60 秒。
- 睡眠或时间戳陈旧时：5–15 分钟。
- 不得调用唤醒接口强制更新。

## 6. 明确排除的读取接口

以下接口虽然可能是 GET，但不进入首版白名单：

- `/api/app/favorite/carDaySumLocus?date=...`
  - 没有 `deviceId`，存在服务端默认车辆混淆风险。
  - 使用 M4 获取目标车辆的 routeId，再逐条调用 M5 构造日轨迹。
- `/api/app/favorite/getDeviceSettingStatus`
  - 是配置状态，不是实时告警；且没有显式车辆 ID。
- `/voge-system/app/rule/{vehicleId}`
  - 返回安全功能配置开关，不代表当前告警状态。
- `/moto/app/vehicle/odoHistory`
- `/moto/app/vehicle/trail`
- `/moto/app/vehicle/{vehicleId}/detail/{date}`
  - 首版已有更安全的现代显式 `deviceId`/已验证 `routeId` 路径。
- 排行榜、社区、商城、账号资料、数字钥匙、固件、SIM 充值等非必要读取接口。

## 7. 绝对禁止的接口和行为

下列路径无论 HTTP 方法如何，都不得由该集成调用。

### 7.1 现代 API 禁止项

- `/api/app/command/*`
- `/api/app/command/createCommand`
- `/api/app/command/createCommandAndWaitingCan`
- `/api/app/favorite/up-default`
- `/api/iot/app/iot-user-device/bind-device`
- `/api/iot/app/iot-user-device/del`
- `/api/app/favorite/updateAppCarName`
- `/api/app/favorite/userDeviceCarNoUp`
- `/api/app/favorite/saveUserSettingStatus`
- `/api/app/digitalKey/*`
- `/api/app/my/device/upgrade`
- 账户注销、密码修改、手机号修改、个人资料修改、文件上传、注册、登出和智能投屏确认接口

禁止动作包括但不限于：

- 解锁、上锁
- 设防/撤防
- 唤醒
- 断油/断电
- 电子锁或蓝牙钥匙操作
- 阻尼设置
- 默认车辆切换
- 车辆绑定/解绑
- 固件升级

### 7.2 旧版 API 禁止项

- `/moto/app/vehicle/contorl/*`（服务端路径原样拼写）
- `/moto/app/vehicle/contorl/command`
- `/moto/app/vehicle/contorl/awakenDevice`
- `/moto/app/vehicle/bind`
- `/moto/app/vehicle/update`
- 车辆分享新增、删除和设置接口
- `/voge-system/app/jPushReg/bindRid`
- `/voge-system/app/message/upReadStatus`
- `/voge-system/app/message/delete`
- `/voge-system/app/message/deleteAll`
- `/voge-system/app/memberNotify/set`
- `/voge-system/app/rule/update`
- `/voge-system/app/rule/updateDefault`

### 7.3 JPush 禁止项

- 不生成、伪造或绑定 JPush registration ID。
- 不覆盖手机 App 已绑定的 registration ID。
- 不修改 alias、tag、mobile number 或厂商推送配置。
- 首版告警仅轮询消息历史。

## 8. 车辆身份契约

## 8.1 配置入口

首版 config flow 只接受 token，不接受明文密码。

验证步骤：

1. 调用 M1。
2. 处理现代 `code == 200`。
3. 从车辆列表读取 `productName`、`productId`、`deviceId`、VIN 和 `menu`。
4. 如果只有一个明确的 CU250 候选，可以预选。
5. 如果有多个候选，由 Home Assistant config flow 展示脱敏标签供用户选择。
6. 绝不通过修改服务端默认车辆来完成选择。

“CU250 二代 AMT”不能只由 APK 本地常量判断，因为 APK 中没有找到 CU250/AMT 固定字符串；车型和能力由服务端下发。

## 8.2 Home Assistant 唯一标识

建议：

- Config entry 唯一 ID：优先使用稳定 `userId` 的 SHA-256 派生值，不显示原始 `userId`。
- HA device identifier：目标现代 `deviceId` 的 SHA-256 派生值。
- Entity unique_id：`<device_hash>_<entity_key>`。
- 原始 token、VIN、deviceId 不放进 entity unique_id、日志或诊断。

原始 `deviceId` 可以作为调用 API 所需的私密 config-entry 数据保存。

## 8.3 消息归属

L1 是账户级接口，没有车辆 query，`MessageModel` 顶层也没有确认的车辆 ID 字段。

因此：

- 告警 event entity 始终归属到单独的“VOGE account alerts”账户级设备；这样即使以后新增绑定车辆，也不会让既有 entity registry 关系错误指向某辆车。
- 账户恰好只有一辆绑定车辆时，事件载荷可以标注 `single_vehicle_assumption`，但这只是账户状态推断，不是服务端消息提供的车辆身份。
- 多车辆账户必须标注 `account_level`，不能猜测消息属于 CU250。
- 不得通过标题、地址或自然语言内容做不可靠的车辆匹配。
- 如果未来 `param` 提供明确 ID，只能使用经过验证的 ID 映射，并重新设计稳定的实体迁移策略。

## 9. 能力和实体创建规则

## 9.1 通用规则

- `menu[key] == 1`：已声明支持；字段值有效时创建/启用实体。
- `menu[key] == 0`：不创建新实体；已存在实体保持 registry 记录但状态 unavailable。
- `menu` 没有该键但实际字段持续返回有效值：可创建默认禁用实体，并在真实 CU250 样本确认后升级为默认启用。
- 空字符串、`null`、`-`、无法解析数字不得转换成 `0`。
- 业务上的真实 `0` 必须保留，但已知 App 用作占位符的字段需额外谨慎。
- capability 变化时不自动删除 HA entity registry 项。

## 9.2 M1 基础实体候选

| HA 实体 | API 字段 | 单位/类型 | 规则 |
|---|---|---|---|
| 位置 | `geoLatitude`,`geoLongitude`，回退 `latitude`,`longitude` | `device_tracker` | 验证范围；GCJ-02 转 WGS84 |
| GPS 更新时间 | `gpsTimeStr`，保留 `gpsTime` | timestamp sensor | 两字段分开解析，不能假定相同语义 |
| 车辆/云端更新时间 | `timeGen` | timestamp sensor | 格式 `yyyy-MM-dd HH:mm:ss`；时区可配置 |
| 剩余油量 | `restFuelLevel` | L | `menu.restFuelLevel == 1` 或实测有效 |
| 预计续航 | `restTrip` | km | 已由 UI 文案确认 |
| 百公里油耗 | `consumptionPerHundredKM` | `L/100 km` | 不使用 APK UI 的简化 `L` 作为 HA 单位 |
| 总里程 | `sumDistance` | km | `menu.sumDistance == 1` |
| 本月里程 | `distanceMo` | km | UI 标注“骑行里程(KM)” |
| 本月骑行时长 | `durationMoStr` | 文本/后续 duration | 初始可做文本 sensor |
| 平均速度 | `aveSpeed` 或经实测确认的 `avgTime` | km/h | `avgTime` 命名异常，未实测前不混用 |
| 最大速度 | `maxSpeed` | km/h | 防御式数值解析 |
| 急加速次数 | `harshAccelerationCount` | 次 | 数值 sensor |
| 急减速次数 | `harshDecelerationCount` | 次 | 数值 sensor |
| 急转弯次数 | `harshSteeringCount` | 次 | 数值 sensor |
| 压弯次数 | `bendingCount` | 次 | 数值 sensor |
| 最大压弯角 | `bendingAngle` | ° | 数值 sensor |

以下状态暂不做实体，只保留在内部原始模型用于后续实测：

- `deviceStatus`
- `lockStatus`
- `buzzerStatus`
- `isCan`
- `rafe`
- `deviceIdIot`

## 9.3 M2 综合诊断实体候选

只有身份校验通过时使用：

| HA 实体 | 字段 | 单位 |
|---|---|---|
| 油量百分比 | `fuelPercentage` | `%` |
| 剩余油量 | `restFuelLevel` | L |
| 设备/电瓶电压 | `voltage` | V |
| 冷却液/水温 | `coolingTpr` | °C |
| 前轮胎压 | `frontTireP` | bar |
| 后轮胎压 | `queenTireP` | bar |
| 前轮胎温度 | `frontTireTpr` | °C |
| 后轮胎温度 | `queenTireTpr` | °C |
| 下次保养剩余里程 | `nextUpkeepMileage` | km |
| 综合诊断更新时间 | `timeGen` | timestamp |

字段优先级：

- M2 身份匹配且值有效时，电压、温度、胎压和 `fuelPercentage` 使用 M2。
- `restFuelLevel`、`sumDistance` 若 M2 有有效值可使用 M2，否则回退 M1。
- `fuelPercentage == "0%"` 在 APK 中会回退显示升数。首版应保留原值，但在没有真实样本证明它表示真实空油箱前，将百分比状态标记为未知，而不是贸然报告 0%。

## 9.4 `canList` 动态数据

综合诊断响应存在动态 CAN 列表模型：

```text
canList[].name
canList[].value[].id
canList[].value[].idDesc
canList[].value[].desc
canList[].value[].value
canList[].value[].valueName
canList[].value[].unit
canList[].value[].type
canList[].value[].canValue
canList[].value[].codeValue
canList[].value[].coefficient
canList[].value[].offset
canList[].value[].dictionaries
```

这可能包含速度、RPM、挡位或其他 CU250 专有数据，但静态 APK 没有提供目标车型样本。

首版规则：

- 原样防御式解析。
- 不自动将任意服务端文本变成默认启用实体。
- 只有当 `id`/`codeValue` 稳定、`desc` 和 `unit` 明确、真实 CU250 多次响应一致时，才建立固定实体映射。
- 动态实体默认禁用，避免服务端文案变化造成 unique_id 漂移。
- 不自行重复应用 `coefficient`/`offset`，除非真实响应证明 `value` 尚未换算。
- 不把完整 `canList` 放进普通 entity attributes。

## 9.5 实验性旧版实体

只有 L3 唯一 VIN 匹配及 L4 实测通过后才启用：

- RPM sensor
- 实时速度 sensor
- 挡位 sensor
- RSSI sensor
- 点火 binary sensor
- 在线 binary sensor
- 睡眠 binary sensor
- 防盗状态 binary sensor
- 旧版前/后胎压 sensor

这些实体首版默认禁用，不以模型字段存在作为 CU250 支持证据。

## 10. 告警事件契约

## 10.1 已知旧版类型

| 原始 type | 归一化 event type | APK 标签 |
|---:|---|---|
| 1 | `fault_code` | 故障码提醒 |
| 2 | `safe_riding` | 安全骑行提醒 |
| 3 | `vibration` | 震动告警 |
| 4 | `geofence` | 电子围栏告警 |
| 5 | `collision` | 碰撞告警 |
| 6 | `low_voltage` | 低电压告警 |
| 7 | `low_data` | 流量告警 |
| 8 | `anti_theft` | 防盗告警 |
| 9 | `device_disconnected` | 设备异常提醒 |
| 10 | `abnormal_movement` | 拖车告警 |
| 13 | `low_fuel` | 油量告警提醒 |
| 50 | `vibration` | 仅由震动图标强关联，标题仍为权威 |
| 51–62 | `unknown` | 静态 APK 未给出明确语义 |

规则：

- 未知 numeric type 不丢弃。
- 事件属性始终带 `raw_type`。
- 对 type 50 增加 `mapping_confidence: icon_only`，直到真实 CU250 消息确认。
- `title` 和 `content` 使用服务端原文，不用本地类型表覆盖。

## 10.2 Home Assistant event entity

建议 event types：

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

每次新消息触发：

```text
事件实体状态更新
+ Home Assistant event bus: voge_vehicle_alert
```

事件属性：

```json
{
  "message_id": "<内部值；诊断中哈希>",
  "module": 1,
  "raw_type": 3,
  "event_type": "vibration",
  "mapping_confidence": "confirmed_static|icon_only|unknown",
  "title": "震动告警",
  "content": "...",
  "content_plain": "...",
  "create_time": "...",
  "param": {},
  "if_read": 0,
  "vehicle_attribution": "single_vehicle_assumption|account_level"
}
```

不建议把每种告警做成长期保持 `on` 的 binary sensor，因为消息记录没有可靠的“告警恢复/结束”语义。

## 10.3 去重和首次基线

持久化 Store 仅保存有限的消息标识，不保存完整消息内容：

- 每个 config entry 最多保存最近 500 个 `messageId`。
- `messageId` 为空时，用消息稳定字段生成 SHA-256 合成标识；不保存原始内容。
- 首次成功轮询只建立基线，不向 HA 重放全部历史告警。
- 后续从第 1 页开始抓取，直到遇到已知 ID、到达服务器最后一页或到达安全页数上限。
- 建议安全上限 5 页；达到上限时明确记录“可能仍有未处理页面”，不得静默宣称完整。
- 新消息按 `createTime` 从旧到新触发。
- 一次处理成功后再更新持久化 ID 集，避免网络异常导致消息丢失。

绝不调用：

```text
/voge-system/app/message/upReadStatus
/voge-system/app/message/delete
/voge-system/app/message/deleteAll
```

## 11. 坐标和轨迹解析契约

## 11.1 当前坐标

静态证据表明现代 API 坐标直接作为 GCJ-02 输入传给百度地图 SDK。

规则：

1. 优先读取数值 `geoLatitude`、`geoLongitude`。
2. 如果缺失，回退字符串 `latitude`、`longitude`。
3. 验证纬度 `[-90, 90]`、经度 `[-180, 180]`。
4. 中国大陆范围内执行 GCJ-02 → WGS84 转换。
5. 范围外原样返回。
6. Home Assistant `device_tracker` 只输出 WGS84。
7. 内部可保留原始 GCJ-02 用于排查，但诊断中完全删除或降低精度。
8. 提供高级选项“禁用坐标转换”，用于未来后端坐标系变化后的兼容排查。

不得把现代坐标当成 BD-09。

## 11.2 GeoJSON

GeoJSON 坐标顺序必须是：

```text
[longitude, latitude]
```

单条 M5 轨迹：

- 一个有效点数组 → `LineString`

按日聚合：

- 从 M4 获取目标车辆当天所有已验证 `routeId`。
- 分别调用 M5。
- 每个 route 保持独立 segment。
- 多 segment 输出 `MultiLineString` 或多个 `LineString Feature`。
- 不跨停车/熄火间隔画直线。

明确不复现 APK 在单 segment 时重复同一数组的可疑逻辑。

## 11.3 TrackPoint

字段：

- `lat`
- `lon`
- `speed`
- `direction`
- `locatetime`

`locatetime` 单位尚未确认：

- 原始 Long 必须保留为 `locatetime_raw`。
- 在真实响应确认数量级前，不对外宣称它是秒或毫秒。
- 首版 GeoJSON 可以省略转换后的点时间，只返回原始值或完全省略逐点元数据。

## 11.4 错误和大小限制

- 每个字符串化 points segment 单独解析。
- 某个 segment 损坏时保留其他有效 segment，并返回 `partial: true` 和错误数量。
- 日志不打印损坏 segment 原文。
- 不静默截断轨迹点。
- 如设置资源上限，超限时返回明确 `route_too_large` 错误及点数/字节数，不假装完整。
- 普通 entity attributes 中不存完整轨迹数组。

## 12. 时间处理

已确认格式：

```text
MotoMainPage.timeGen = yyyy-MM-dd HH:mm:ss
MessageModel.createTime = yyyy-MM-dd HH:mm:ss
```

规则：

- 这些字符串没有时区后缀。
- 不得按 UTC 静默解释。
- Home Assistant 选项提供 `server_timezone`，建议初始默认 `Asia/Shanghai`，并明确标记为待实测假设。
- 内部转换为 timezone-aware datetime 后再交给 HA。
- `gpsTime` 和 `gpsTimeStr` 分开保存和解析，不假设二者相同。
- 解析失败时保留 raw 字符串，不返回错误时间。
- coordinator 自己的抓取时间使用 UTC，仅表示“HA 何时成功拉取”，不冒充车辆上报时间。

## 13. Home Assistant 结构

建议目录：

```text
custom_components/voge/
├── __init__.py
├── manifest.json
├── const.py
├── config_flow.py
├── api.py
├── auth.py
├── models.py
├── coordinator.py
├── sensor.py
├── binary_sensor.py
├── device_tracker.py
├── event.py
├── services.py
├── diagnostics.py
├── store.py
├── strings.json
└── translations/
    ├── en.json
    └── zh-Hans.json
```

## 13.1 Config entry

- 一账户一 config entry。
- 首版只要求主 token。
- 允许在 config entry 内选择一个或多个已确认 CU250，但本项目默认只启用目标 CU250。
- token 使用 HA 标准 config-entry 私密数据保存。
- 永不写日志或 diagnostics。
- reauth 只替换 token，不改变车辆选择和 entity unique_id。

## 13.2 Coordinator 划分

### Telemetry coordinator

- M1 + 条件安全的 M2
- 默认 90 秒
- 单次 M1 失败时不调用 M2
- M2 身份不匹配时只丢弃 M2，不污染 M1 状态

### Alert coordinator

- L1
- 默认 45 秒
- 与 telemetry 独立退避，避免旧版消息 API 故障导致车辆状态 unavailable
- 首次基线不重放历史

### Statistics coordinator

- M3、M6、M7
- 默认 30 分钟
- M6/M7 可在格式或能力未确认时关闭

### Route client/service

- M4、M5
- 按需调用
- 不纳入普通 coordinator 周期轮询

### Experimental legacy coordinator

- L3/L4
- 默认关闭
- 唯一 VIN 匹配后才可启动

## 13.3 历史轨迹 Home Assistant actions

建议提供支持 response data 的 actions：

```text
voge.get_month_trips
voge.get_route_geojson
voge.get_day_geojson
```

参数必须引用已配置车辆和经过验证的年月/routeId，不接受任意 host/path。

默认行为：

- 返回结构化 JSON/GeoJSON。
- 不把精确轨迹永久写入 entity attributes。
- 不默认把精确轨迹写入 `/config/www`。
- 如以后增加持久缓存，应明确让用户选择保留周期，并在 diagnostics 中完全排除轨迹点。

## 14. 可用性、陈旧数据和重试

- 正常 GET 超时建议：connect 10 秒，总计 30 秒；大轨迹单独提高总超时。
- HTTP/业务 429：客户端进入本地冷却；`Retry-After` 被限制在 1–3600 秒，缺失或非法时从 30 秒开始指数增长并封顶 3600 秒；请求内部不 sleep，也不立即重试。
- HTTP 5xx/网络错误：当前不在单次请求内自动重试，由独立 coordinator 等待下一次调度，避免云端故障时放大请求量。
- HTTP/业务 401：立即进入 reauth，不继续重试。
- 其他 4xx：不自动重试。
- 不因车辆睡眠或时间戳旧而频繁请求。
- 数据陈旧时保留最后已知值，并提供：
  - GPS 更新时间
  - 车辆工况更新时间
  - HA 最后成功抓取时间
  - 可选“数据陈旧”诊断 binary sensor
- `device_tracker` 不因一次请求失败而把车辆位置清零。

## 15. 日志和 diagnostics 脱敏

必须递归删除或替换：

- `Mansuoid`
- `Authorization`
- access token
- refresh token
- APK 应用 access key 和签名 secret
- 手机号、`mobile`、`tel`
- VIN
- 完整 `deviceId`、`deviceIdIot`、`amapDeviceId`、`vehicleId`、`deviceNum`
- `simIccid`、`simImsi`
- 精确经纬度
- 精确地址
- 完整 route points
- 可能含地址/身份信息的消息 `content` 和 `param`

建议：

- ID 用稳定 SHA-256 前缀表示，例如 `sha256:12ab34cd…`。
- diagnostics 中坐标默认完全删除；如果确需检查，只保留非常粗略区域且必须显式说明。
- 消息 diagnostics 只保留计数、已知/未知 type、最近抓取时间，不保留正文。
- 异常日志记录 endpoint 符号名、HTTP 状态、业务 code，不记录请求头、完整 URL、原始 body。

## 16. APK 签名元数据

用 Android SDK `apksigner` 和 Android Studio 自带 JBR 验证：

- `Verifies`: 是
- v1：否
- v2：是
- v3/v3.1/v3.2/v4：否
- SourceStamp：否
- Signers：1
- 证书 DN：`C=cn, ST=sd, L=cd, O=jczy, OU=jczy, CN=jczy`
- 证书 SHA-256：`130a712de3d1fafd27131d79a6c62d3d3108858324016156606435307eb09ce2`
- 证书 SHA-1：`8010a9ee5b831281cbc21ad3d369876aa377d0f1`
- 公钥算法：RSA
- 公钥长度：2048 bit
- 公钥 SHA-256：`1702cf4038952a33394719a94af8c45e381cb6834f65fda04dd4961a1528cba8`

## 17. 实施顺序

1. 实现不含网络调用的现代/旧版响应模型与解析单元测试。
2. 实现严格 `(method, host, path, query keys)` 只读守卫。
3. 实现现代 token-only client 和 M1 token 校验。
4. 实现 config flow、reauth 和 diagnostics 脱敏。
5. 实现 M1/M2 telemetry coordinator 与基础实体。
6. 实现 GCJ-02 → WGS84、device tracker 和坐标测试向量。
7. 实现 M4/M5 轨迹解析、segment 保留和 GeoJSON actions。
8. 通过私密方式提供旧版签名材料后，实现 L1 告警轮询、去重 Store 和 event entity。
9. 获取真实脱敏 CU250 响应，确认 `menu`、车型 ID、消息 `param`、type 50/51–62、`locatetime`、时区和 `rafe`。
10. 只有唯一 VIN 关联与有效实时响应都成立时，才开放实验性 L4 实体。

## 18. 当前结论

现代 API 已足以支持首版的大部分目标：

- 当前车辆位置
- GPS 更新时间
- 车辆工况更新时间
- 总里程和月里程
- 剩余油量、续航和百公里油耗
- 电压、冷却液温度和胎压/胎温（以 M2 身份和能力确认结果为准）
- 月度摘要、行程列表和轨迹 GeoJSON
- 驾驶行为摘要

旧版消息 API 可用于只读告警轮询：

- 震动
- 拖车/异常移动
- 防盗
- 碰撞
- 电子围栏
- 低电压
- 低油量
- 设备异常/断开
- 故障码和安全骑行提醒

但必须继续保留以下限制：

- 不能仅凭静态模型声称 CU250 支持 RPM、挡位、点火、在线、睡眠或旧版防盗实时状态。
- 不能把安全设置开关当成正在发生的告警。
- 不能在多车辆账户中猜测账户级消息属于哪辆车。
- 不能为读取数据而切换服务端默认车辆。
- 不能复制 App 的信任所有 TLS 证书行为。
- 不能调用任何控制、绑定、已读、删除或设置修改接口。
