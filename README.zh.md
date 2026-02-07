# iphoneclaw

[English](README.md) | [中文](README.zh.md)

![demo](assets/demo.gif)

![iphoneclaw mascot](assets/iphoneclaw-brand-mascot.png)

完整演示视频: [assets/iphoneclaw.mp4](assets/iphoneclaw.mp4)

官网: https://iphoneclaw.com

`iphoneclaw` 是一个 **macOS-only** 的 Python CLI Worker：通过 **iPhone 镜像 / iPhone Mirroring** 窗口，让 VLM（Vision Language Model）以 UI-TARS 风格的 `Thought:` / `Action:` 循环来操控你的 iPhone。

核心流程:

1. 截取 iPhone 镜像窗口截图（Quartz CGWindowList）
2. 调用 OpenAI-compatible 的多模态接口
3. 解析 `Thought:` / `Action:`
4. 用 Quartz CGEvent 执行鼠标/键盘操作
5. 记录每一步到 `runs/`

同时提供 **本地 Supervisor API**（仅文本 + SSE），便于外部 Agent 框架监督运行：拉取最近 N 轮对话、订阅实时事件，并通过 `pause/resume/stop/inject` 进行干预。设计目标是可以接入 **Claude Code / Codex** 等编排框架，让“老板 Agent”监管这个 UI Worker。

## 设备与系统要求

- 一台 Mac（Mac mini / MacBook）+ 一台 iPhone
- 支持 iPhone 镜像:
  - Mac 升级到 **macOS Sequoia（macOS 15）** 或更高
  - iPhone 升级到 **iOS 18** 或更高
  - Mac 和 iPhone 使用 **同一 Apple ID** 登录
- Python >= 3.9
- 终端需要授予 Screen Recording（屏幕录制）与 Accessibility（辅助功能）权限

## 安装

```bash
git clone https://github.com/NoEdgeAI/iphoneclaw.git
cd iphoneclaw

# pip
pip install -e .

# 或 uv
uv pip install -e .
```

包含开发依赖（可选）:

```bash
pip install -e ".[dev]"
# 或
uv pip install -e ".[dev]"
```

检查权限:

```bash
iphoneclaw doctor
```

如果 Screen Recording 或 Accessibility 显示 **MISSING**，到 **System Settings > Privacy & Security** 给你的终端程序授权。

## 推荐模型

iphoneclaw 支持任意 OpenAI-compatible 的视觉模型接口。以下是常见选项:

### 选项 A: UI-TARS + vLLM（自建）

UI-TARS 是字节系 GUI agent 模型，天然输出 iphoneclaw 需要的 Action 格式。

```bash
python -m vllm.entrypoints.openai.api_server \
  --served-model-name ui-tars \
  --model ByteDance-Seed/UI-TARS-1.5-7B \
  --limit-mm-per-prompt image=5 \
  -tp 1
```

运行:

```bash
python -m iphoneclaw run \
  --instruction "打开设置并开启 Wi-Fi" \
  --base-url http://127.0.0.1:8000/v1 \
  --model ui-tars
```

### 选项 B: 火山 Ark（Doubao）

```bash
export IPHONECLAW_MODEL_BASE_URL="https://ark.cn-beijing.volces.com/api/v3"
export IPHONECLAW_MODEL_API_KEY="your-ark-api-key"
export IPHONECLAW_MODEL_NAME="doubao-seed-1-6-vision-250815"

python -m iphoneclaw run \
  --instruction "打开设置并开启 Wi-Fi"
```

## 快速开始

```bash
# 1) 权限检查
python -m iphoneclaw doctor

# 2) 启动并验证窗口识别
python -m iphoneclaw launch --app 'iPhone镜像'

# 3) 测试截图（包含自动裁剪白边校准）
python -m iphoneclaw screenshot --out /tmp/shot.jpg

# 4) 运行 worker
python -m iphoneclaw run \
  --instruction "打开设置并开启 Wi-Fi"
```

## 致谢

- [UI-TARS](https://github.com/bytedance/UI-TARS)

