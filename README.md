# VOGE / 无极 Home Assistant 集成

用于 Home Assistant 的 VOGE / 无极自定义集成。

## 安装

### 通过 HACS 安装

1. 在 HACS 中打开“集成”。
2. 打开右上角菜单，选择“自定义存储库”。
3. 添加以下仓库地址：

   ```text
   https://github.com/goxofy/Voge-Motorcycles-HomeAssistant
   ```

4. 类别选择“集成”。
5. 搜索并安装 `VOGE Motorcycle`。
6. 重启 Home Assistant。

当前要求 Home Assistant `2026.9.0` 或更高版本。

### 手动安装

将仓库中的 `custom_components/voge/` 完整复制到 Home Assistant 配置目录：

```text
/config/custom_components/voge
```

完成后重启 Home Assistant。

### 更新

- HACS 安装：在 HACS 中完成更新后重启 Home Assistant。
- 手动安装：使用新版 `custom_components/voge/` 完整覆盖旧目录，然后重启 Home Assistant。

## 配置

1. 打开 Home Assistant 的“设置 → 设备与服务”。
2. 选择“添加集成”。
3. 搜索并选择 `VOGE Motorcycle`。
4. 按配置表单提示完成登录。
5. 如果账号下有多辆车，选择该配置项需要使用的车辆。

当前每个配置项对应一辆车。如需添加多辆车，请分别创建配置项。

可以在集成选项中调整：

- 车辆数据轮询间隔；
- 统计数据轮询间隔；
- 告警轮询间隔；
- 服务器时区；
- 坐标转换；
- 告警轮询开关。

## 开发

开发和兼容性基线：

- Home Assistant `2026.9.0`；
- Python `3.14.2`；
- [`uv`](https://docs.astral.sh/uv/)。

运行完整测试：

```bash
uv run --python 3.14.2 \
  --with pytest \
  --with pytest-homeassistant-custom-component \
  --with homeassistant==2026.9.0 \
  --with aiohttp \
  pytest -q --asyncio-mode=auto
```

运行 Ruff：

```bash
uv run --python 3.14.2 --with ruff ruff check .
```

运行 Pyright：

```bash
uv run --python 3.14.2 \
  --with pyright \
  --with homeassistant==2026.9.0 \
  --with pytest \
  pyright custom_components/voge tests tools/inspect_vehicle_capabilities.py
```

提交改动前应确保测试、Ruff 和 Pyright 检查通过。
