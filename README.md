# AI 电商客服系统

> 智能电商客服平台 —— 数字人 TTS × 领域知识问答 × 订单查询 × 闲聊分流

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.136+-009688?logo=fastapi&logoColor=white)
![LangChain](https://img.shields.io/badge/LangChain-1.2+-FF4B4B?logo=chainlink&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

## 目录

- [项目简介](#项目简介)
- [系统架构](#系统架构)
- [核心功能](#核心功能)
- [技术栈](#技术栈)
- [快速启动](#快速启动)
- [API 接口文档](#api-接口文档)
- [项目结构](#项目结构)
- [功能扩展建议](#功能扩展建议)

## 项目简介

面向电商场景的智能客服后端系统，集成大模型对话、数字人语音合成、领域知识检索、订单商品查询等能力，支持智能分流（客服/闲聊/澄清）与流式响应。

## 系统架构

```
┌─────────────────────────────────────────────────────┐
│                   Vue 3 前端 (5173)                  │
│              商务风格 UI · 数字人形象                  │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP / SSE
┌──────────────────────▼──────────────────────────────┐
│              FastAPI 应用 (18082)                     │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │ 聊天路由  │  │ 数字人路由│  │ /health 存活探针   │  │
│  └────┬─────┘  └────┬─────┘  └───────────────────┘  │
│       │              │                               │
│  ┌────▼──────────────▼──────────────────────────┐   │
│  │            DialogueService 业务层              │   │
│  │   TurnPlanner → 意图分流 → Action 执行         │   │
│  └──┬──────────┬──────────┬──────────┬──────────┘   │
│     │          │          │          │               │
│  ┌──▼───┐  ┌──▼────┐  ┌──▼───┐  ┌──▼────────┐     │
│  │知识问答│  │订单查询│  │闲聊  │  │澄清/数字人 │     │
│  └──┬───┘  └──┬────┘  └──┬───┘  └──┬────────┘     │
│     │         │          │         │                │
│  ┌──▼─────────▼──────────▼─────────▼──────────┐    │
│  │     Infrastructure（LLM / DB / HTTP Client） │    │
│  └─────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
        │                    │                │
   ┌────▼────┐        ┌─────▼─────┐   ┌─────▼─────┐
   │  MySQL  │        │ 大模型 API │   │ 电商中台   │
   │ (会话态) │        │(OpenAI协议)│   │ (订单/商品)│
   └─────────┘        └───────────┘   └───────────┘
```

## 核心功能

| 模块 | 能力 |
|------|------|
| **智能对话** | 多轮对话、上下文记忆、流式输出 |
| **数字人 TTS** | Edge-TTS 语音合成，客服角色定制音色 |
| **知识问答** | 领域知识库检索，精准回答商品/售后问题 |
| **订单查询** | 对接业务系统，查询订单状态、物流信息 |
| **智能分流** | 客服/闲聊/澄清意图识别，精准路由 |

## 技术栈

| 层级 | 技术选型 |
|------|---------|
| **Web 框架** | FastAPI + Uvicorn (ASGI) |
| **AI 引擎** | LangChain + OpenAI 兼容协议 |
| **语音合成** | Edge-TTS（晓晓/云希等中文音色） |
| **数字人** | 魔珐星云 SDK（可选，需单独申请凭证） |
| **数据库** | MySQL（SQLAlchemy 2.x 异步 ORM） |
| **HTTP 客户端** | httpx（异步连接池，调电商中台） |
| **前端** | Vue 3 + Vite，商务风格 UI |

## 快速启动

### 1. 环境要求

- Python 3.12+
- MySQL 数据库
- [uv](https://github.com/astral-sh/uv) 包管理器（推荐）

### 2. 安装依赖

```bash
uv sync
```

### 3. 配置环境变量

在项目根目录创建 `.env` 文件：

```env
# ── 大模型（兼容 OpenAI 协议的任意服务） ──
LLM_API_KEY=your-api-key
LLM_MODEL=gpt-4o-mini
LLM_BASE_URL=https://api.openai.com/v1

# ── 数据库 ──
DATABASE_URL=mysql+aiomysql://user:password@localhost:3306/customer_service

# ── 电商中台 ──
COMMERCE_API_BASE_URL=https://your-commerce-api.com

# ── 服务端口 ──
APP_HOST=0.0.0.0
APP_PORT=18082

# ── 数字人（可选，不配置则数字人功能不可用） ──
DIGITAL_HUMAN_APP_ID=
DIGITAL_HUMAN_APP_SECRET=

# ── TTS 音色（可选，默认晓晓） ──
TTS_VOICE=zh-CN-XiaoxiaoNeural
```

### 4. 启动服务

```bash
# 启动后端
python main.py

# 启动前端（另开终端）
cd external/customer-service-frontend
npm install && npm run dev
```

- 后端 API：http://localhost:18082
- 前端页面：http://localhost:5173
- 接口文档：http://localhost:18082/docs（Swagger UI）

## API 接口文档

### `POST /api/chat` — 发送消息

用户发送文本或点击订单/商品卡片时调用。

**请求体：**

```json
{
  "sender_id": "user_001",
  "message_id": "可选，不传则服务端生成",
  "text": "我的订单发货了吗？",
  "object": null
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `sender_id` | string | 是 | 用户唯一标识 |
| `message_id` | string | 否 | 客户端消息 ID，不传自动生成 |
| `text` | string | 否 | 文本消息内容 |
| `object` | ChatObject | 否 | 对象消息（点击订单/商品卡片） |

**`ChatObject` 结构：**

```json
{
  "type": "order",
  "id": "ORD-20261012-001",
  "title": "iPhone 16 Pro",
  "attributes": { "amount": 7999, "status": "shipped" }
}
```

**响应体：**

```json
{
  "sender_id": "user_001",
  "message_id": "uuid",
  "messages": [
    { "text": "您的订单已发货，预计明天到达。", "object": null }
  ]
}
```

### `GET /api/chat/history` — 查询历史消息

**参数：** `sender_id`（query string）

**响应体：**

```json
{
  "sender_id": "user_001",
  "messages": [
    {
      "session_id": "sess_xxx",
      "role": "user",
      "text": "查一下我的订单",
      "object": null
    }
  ]
}
```

### `GET /api/digital-human/credentials` — 获取数字人凭证

返回魔珐星云 SDK 初始化所需的凭证，前端每次初始化数字人时调用。

> 未配置 `DIGITAL_HUMAN_APP_ID` / `DIGITAL_HUMAN_APP_SECRET` 时返回 503。

### `POST /api/chat/tts` — 语音合成

将文本合成为 MP3 音频流返回。

**请求体：**

```json
{ "text": "您好，很高兴为您服务", "voice": null }
```

**响应：** `audio/mpeg` 二进制流

### `GET /health` — 存活探针

返回 `{"status": "ok"}`，用于部署平台健康检查。

## 项目结构

```
customer-service-backend/
├── main.py                 # 服务启动入口
├── api/                    # API 路由层
│   ├── app.py              #   FastAPI 实例 & 生命周期管理
│   ├── schemas.py          #   请求/响应 Pydantic 模型
│   └── routers/            #   路由定义
│       ├── chat_router.py  #     聊天 & 历史接口
│       └── digital_human_router.py  # 数字人凭证 & TTS
├── service/                # 业务服务层（对话编排）
├── engine/                 # 对话引擎（LangChain 图构建）
├── plan/                   # 意图规划 & 轮次校验
├── domain/                 # 领域模型（消息/状态/上下文）
├── models/                 # ORM 数据模型
├── repository/             # 数据仓库（会话持久化）
├── knowledge/              # 知识库检索 & 意图匹配
├── task/                   # Action 执行（订单查询等）
├── digital_human/          # 数字人 TTS 封装
├── chitchat/               # 闲聊分流
├── clarify/                # 澄清追问
├── prompts/                # Prompt 模板（Jinja2）
├── flow_config/            # 对话流程配置（YAML）
├── infrastructure/         # 基础设施（DB/LLM/HTTP）
├── conf/                   # 配置层（pydantic-settings）
├── external/
│   └── customer-service-frontend/  # Vue 3 前端项目
└── test/                   # 测试用例
```

## 功能扩展建议

1. **多渠道接入** — 支持网页、微信、APP 等多端接入
2. **人工坐席协作** — 复杂问题转人工，人机协同服务
3. **数据分析看板** — 对话质量分析、热点问题统计

## License

MIT
