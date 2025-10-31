# Catfish API - Gemini 网页应用逆向代理

这是一个功能强大的反向代理服务，它将 Google Gemini 网页应用封装成了一个与 OpenAI API 格式高度兼容的后端服务。你可以使用任何支持 OpenAI 格式的客户端或应用，通过修改 API 地址和密钥，直接无缝地使用由 Gemini 提供的强大功能。

本项目从一个简单的想法出发，逐步实现了认证、多轮对话、动态模型发现、API Key 保护、自动重试、伪流式响应，并最终集成了强大的多模态能力。

## 核心功能

*   **OpenAI 格式兼容**: 提供与 OpenAI `v1/chat/completions` 和 `v1/models` 高度一致的接口，方便现有应用直接迁移。
*   **多轮对话**: 通过自定义的 `session_id` 字段，实现稳定、有状态的连续对话。
*   **强大的 Gemini Web 能力**:
    *   **🌐 联网搜索**: 当提问需要实时信息时，模型会自动联网搜索，无需任何额外参数。
    *   **🖼️ 图像生成**: 通过自然的提示词（如“画一个...”、“生成图片...”）即可调用 Google 的图像生成模型。
    *   **🛠️ Google 扩展**: 支持通过 `@` 符号（如 `@Youtube`, `@Gmail`）调用你在 Gemini 网页上已授权的 Google 应用扩展。
*   **多模态视觉理解**: 支持符合 GPT-4 Vision API 格式的请求，可以识别并理解你提供的图片内容（通过 URL 或 Base64）。
*   **健壮性设计**:
    *   **API Key 认证**: 通过 `Bearer Token` 保护你的服务不被滥用。
    *   **动态模型发现**: 自动获取当前账号可用的所有 Gemini 模型列表。
    *   **自动重试**: 当遇到网络波动或API临时性错误时，会自动进行多次重试。
    *   **会话管理**: 智能管理会话生命周期，防止内存泄漏。
*   **高度可配置**: 所有核心参数（Cookie、API Key、代理、Gem 提示词等）均通过环境变量进行配置，轻松适应不同部署环境。
*   **部署友好**: 提供 `Dockerfile` 和 `docker-compose.yml`，可一键在本地或云端平台（如 Render）进行容器化部署。

## 快速开始

### 1. 环境准备

*   [Python](https://www.python.org/) (3.11+)
*   [Git](https://git-scm.com/)
*   [Docker](https://www.docker.com/) 和 Docker Compose (推荐，用于本地测试和部署)

### 2. 克隆与安装

```bash
git clone <你的项目仓库地址>
cd catfishAPI
pip install -r requirements.txt
```

### 3. 配置环境变量

这是最关键的一步。在项目根目录下，将 `.env.example` 文件复制一份并重命名为 `.env`，然后填入以下值：

**文件: `.env`**
```env
# Google 账户凭证 (必需)
# 从你的浏览器开发者工具中获取
SECURE_1PSID=g.a000...
SECURE_1PSIDTS=sidts-CjEB...

# 服务 API Key (必需)
# 用于保护你的 API 服务，请设置一个强随机字符串
API_KEY=your-secret-and-strong-api-key-here

# 自定义 Meta Gem 提示词 (可选)
# 这是给 AI 的核心指令，用于解释如何处理 <system_prompt> 标签。留空则使用默认值。
META_GEM_PROMPT="You are a helpful assistant. The user may provide a block enclosed in <system_prompt> and </system_prompt> tags in their first message. You must treat the content within these tags as the highest-priority system instructions for the entire conversation."

# HTTP 代理 (可选)
# 如果你的本地网络需要代理才能访问 Google，请设置它。在云端部署时通常留空。
# PROXY_URL="http://127.0.0.1:7890"

# 重试次数 (可选)
# 默认为 5 次。
RETRY_ATTEMPTS=5
```

#### 如何获取 Cookie (`SECURE_1PSID` 和 `SECURE_1PSIDTS`)

1.  在 Chrome 或 Firefox 浏览器中登录 [https://gemini.google.com](https://gemini.google.com)。
2.  按 `F12` 打开开发者工具，切换到 "网络 (Network)" 标签。
3.  刷新页面，在请求列表中随便点击一个请求。
4.  在右侧的 "标头 (Headers)" -> "请求标头 (Request Headers)" -> `cookie:` 字段中，找到并复制这两个字段的值。

### 4. 运行服务

你有两种方式可以启动服务：

**A. 直接运行 (本地开发)**

```bash
# 确保你的 .env 文件已配置好
python run.py 
# 或者
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

**B. 使用 Docker (推荐)**

```bash
# 这条命令会构建镜像并启动服务，同时自动加载 .env 文件
docker-compose up --build
```
服务将在 `http://localhost:8000` 上运行。

## API 使用指南

### 认证

所有对 `/v1/*` 路径的请求都需要在 HTTP 头部中包含 `Authorization` 字段。

```
Authorization: Bearer <你在.env文件中设置的API_KEY>
```

### 端点

#### `GET /v1/models`

获取当前账号所有可用的模型列表。

#### `POST /v1/chat/completions`

核心聊天接口，用于发送消息。

### 功能示例

以下示例使用 `curl` 命令进行演示，请将 `<YOUR_API_KEY>` 替换为你的真实密钥。

#### 基础文本对话

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_API_KEY>" \
  -d '{
    "model": "gemini-2.5-flash",
    "messages": [
      {
        "role": "system",
        "content": "你是一个只会说押韵句子的诗人。"
      },
      {
        "role": "user",
        "content": "你好，今天天气怎么样？"
      }
    ]
  }'
```

#### 多轮对话

在第一轮请求成功后，从响应中获取 `session_id`，并在后续请求中带上它。

```bash
# 第一轮 (同上) -> 获得 "session_id": "some-uuid-string"

# 第二轮
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_API_KEY>" \
  -d '{
    "model": "gemini-2.5-flash",
    "messages": [
      {
        "role": "user",
        "content": "那明天呢？"
      }
    ],
    "session_id": "some-uuid-string"
  }'
```

#### 联网搜索

这是一个自动功能，只需提出需要实时信息的问题即可。

```bash
# ...
"messages": [
  {
    "role": "user",
    "content": "总结一下最近关于苹果发布会的新闻。"
  }
]
# ...
```

#### 图像生成

使用明确的指令来生成图片。响应中的 `content` 字段将包含Markdown格式的图片。

```bash
# ...
"messages": [
  {
    "role": "user",
    "content": "帮我画一幅梵高风格的星空下的猫的油画。"
  }
]
# ...
```
**响应示例**: `"...这是为您生成的图片:\n\n**Generated Images:**\n![Generated Image](data:image/png;base64,...)"`

#### Google 扩展调用

使用 `@` 符号触发你在 Gemini 网页上开启的扩展。

```bash
# ...
"messages": [
  {
    "role": "user",
    "content": "@Youtube 帮我找一下关于 FastAPI 入门教程的视频"
  }
]
# ...
```

#### 图像理解 (Vision)

发送符合 GPT-4 Vision 格式的请求。支持 URL 和 Base64 两种方式。

**使用 URL:**
```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_API_KEY>" \
  -d '{
    "model": "gemini-1.5-pro",
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "text",
            "text": "这张图片里有什么？"
          },
          {
            "type": "image_url",
            "image_url": {
              "url": "https://upload.wikimedia.org/wikipedia/commons/a/a7/Camponotus_japonicus.jpg"
            }
          }
        ]
      }
    ]
  }'
```

**使用 Base64:**
```bash
# ...
"content": [
  { "type": "text", "text": "描述一下这张图。" },
  {
    "type": "image_url",
    "image_url": {
      "url": "data:image/jpeg;base64,iVBORw0KGgoAAAANSUhEUg..."
    }
  }
]
# ...
```

## 部署

本项目已为容器化部署做好准备。你可以直接将此项目仓库连接到支持 Docker 的云平台（如 Render, Heroku, Fly.io）。

**在部署时，请务必在平台的“环境变量”设置页面中配置好 `SECURE_1PSID`, `SECURE_1PSIDTS`, `API_KEY` 等变量。**

## 致谢

本项目的核心功能依赖于 [HanaokaYuzu/Gemini-API](https://github.com/HanaokaYuzu/Gemini-API) 这个优秀的逆向工程库，感谢其作者的辛勤工作。
