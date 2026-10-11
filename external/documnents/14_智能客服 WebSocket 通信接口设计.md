# 智能客服 WebSocket 通信接口设计指南 

> 本文档基于现有 `POST /api/chat` 接口（`routers.py`），讲解如何使用 WebSocket 改造为**实时双向通信**方式，包含后端接口定义、依赖安装、前端调用示例。

---

## 1. 为什么选择 WebSocket

现有接口 `POST /api/chat` 的工作方式：

```
客户端  →  [发送请求]  →  服务端处理  →  [返回完整响应]  →  客户端
         ═══════════════ 单向请求-响应 ═══════════════
```

WebSocket 改造后的工作方式：

```
客户端  ←────────── 持久连接 ──────────→  服务端
         →  发送消息（JSON）
         ←  流式回复（逐 token 返回）
         ←  主动推送（如"正在输入..."）
         →  取消生成
         ←  连接状态通知
```

**主要优势：**

| 特性 | HTTP POST | WebSocket |
|------|-----------|-----------|
| 连接方式 | 短连接 | 长连接（持久化） |
| 响应方式 | 一次性返回 | 流式逐条推送 |
| 服务端主动推送 | ❌ 不支持 | ✅ 支持 |
| 实时性 | 较低 | 高 |
| 适用场景 | 简单问答 | 流式对话、打字机效果、状态通知 |

---

## 2. 环境依赖安装（uv 方式）

### 2.1 安装 websockets 库

FastAPI 原生支持 WebSocket，但建议同时安装 `websockets` 库以获得更好的性能：

```bash
# 进入项目目录
cd customer-service-backend

# 使用 uv 添加 websockets 依赖
uv add websockets

# 安装完成后，pyproject.toml 中会自动新增：
# "websockets>=15.0.1"
```

### 2.2 同步安装所有依赖

```bash
# 确保所有依赖已安装
uv sync
```

### 2.3 验证安装

```bash
# 验证 websockets 是否安装成功
uv run python -c "import websockets; print('websockets 版本:', websockets.__version__)"
```

### 2.4 完整的依赖清单（pyproject.toml）

安装后 `pyproject.toml` 中的依赖项如下：

```toml
[project]
name = "customer-service-backend"
version = "0.1.0"
description = "智能客服后端服务"
requires-python = ">=3.12"
dependencies = [
    "aiomysql>=0.3.2",
    "fastapi[all]>=0.139.0",    # fastapi[all] 已包含 uvicorn、websockets 等
    "httpx>=0.28.1",
    "jinja2>=3.1.6",
    "langchain>=1.3.13",
    "langchain-openai>=1.3.5",
    "pydantic-settings>=2.14.2",
    "sqlalchemy>=2.0.51",
    "websockets>=15.0.1",       # 新增：WebSocket 协议支持
]
```

> **说明**：`fastapi[all]` 已包含 `uvicorn` 和基础的 WebSocket 支持，额外安装 `websockets` 是为了获得更完善的协议实现和更好的性能。如果仅需基本功能，也可以不额外安装。

---

## 3. 后端 WebSocket 接口定义

### 3.1 在 `routers.py` 中新增 WebSocket 端点

在现有 `router.py` 基础上，新增以下代码（**仅作参考，不修改现有工程**）：

```python
# routers.py — 在现有代码基础上新增以下内容

import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from atguigu.api.deps import get_dialogue_service
from atguigu.service.dialogue_service import DialogueService

router = APIRouter()

# ==================== 现有 HTTP 接口（保持不变） ====================

@router.post("/api/chat", response_model=ChatResponse)
async def chat(
    chat_request: ChatRequest,
    dialogue_service: DialogueService = Depends(get_dialogue_service)
):
    # ... 现有代码保持不变 ...


# ==================== 新增：WebSocket 接口 ====================

@router.websocket("/ws/chat")
async def websocket_chat(
    websocket: WebSocket,
    dialogue_service: DialogueService = Depends(get_dialogue_service),
):
    """
    WebSocket 聊天接口

    与 POST /api/chat 功能等价，但支持：
    1. 流式逐条返回 Bot 消息
    2. 服务端主动推送状态（如"正在输入..."）
    3. 客户端可中途取消生成

    消息协议（JSON）：

    客户端 → 服务端:
    {
        "type": "message",              // 消息类型
        "sender_id": "user_001",         // 用户ID
        "message_id": "msg_abc123",      // 消息ID（可选，不传则自动生成）
        "text": "你好，我想咨询...",      // 用户输入文本
        "object": {                      // 可选：附加对象
            "type": "product",
            "id": "p001",
            "title": "商品名称",
            "attributes": {...}
        }
    }

    客户端 → 服务端（取消生成）:
    {
        "type": "cancel",
        "sender_id": "user_001"
    }

    服务端 → 客户端（Bot 消息，逐条）:
    {
        "type": "bot_message",
        "sender_id": "user_001",
        "message_id": "msg_abc123",
        "data": {
            "text": "您好，想了解什么商品呢？",
            "object": { ... }           // 可选
        }
    }

    服务端 → 客户端（状态通知）:
    {
        "type": "status",
        "sender_id": "user_001",
        "data": {
            "status": "thinking"        // thinking | typing | done | error
        }
    }

    服务端 → 客户端（错误）:
    {
        "type": "error",
        "sender_id": "user_001",
        "data": {
            "code": "PROCESS_ERROR",
            "message": "处理消息时出错"
        }
    }
    """

    # 1. 接受 WebSocket 连接
    await websocket.accept()
    print(f"[WebSocket] 新客户端已连接")

    try:
        # 2. 持续接收客户端消息
        while True:
            # 接收原始文本
            raw_data = await websocket.receive_text()

            try:
                payload = json.loads(raw_data)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "data": {"code": "INVALID_JSON", "message": "消息格式错误，需要 JSON"}
                })
                continue

            msg_type = payload.get("type")

            # --------------------------------------------------
            # 处理 "cancel" 类型：取消当前生成
            # --------------------------------------------------
            if msg_type == "cancel":
                sender_id = payload.get("sender_id")
                # TODO: 通知 dialogue_service 取消该用户的正在生成任务
                await websocket.send_json({
                    "type": "status",
                    "sender_id": sender_id,
                    "data": {"status": "cancelled"}
                })
                continue

            # --------------------------------------------------
            # 处理 "message" 类型：正常聊天消息
            # --------------------------------------------------
            if msg_type == "message":
                sender_id = payload.get("sender_id")
                text = payload.get("text")
                message_id = payload.get("message_id") or uuid.uuid4().hex
                obj_payload = payload.get("object")

                # ① 构建 UserMessage（与 HTTP 接口逻辑一致）
                user_message = UserMessage.from_dict({
                    "sender_id": sender_id,
                    "message_id": message_id,
                    "text": text if text else None,
                    "object": {
                        "type": obj_payload["type"],
                        "id": obj_payload["id"],
                        "title": obj_payload["title"],
                        "attributes": obj_payload.get("attributes")
                    } if obj_payload else None
                })

                # ② 发送"正在思考"状态
                await websocket.send_json({
                    "type": "status",
                    "sender_id": sender_id,
                    "data": {"status": "thinking"}
                })

                try:
                    # ③ 调用对话服务（与 POST /api/chat 一致）
                    process_result: ProcessResult = await dialogue_service.process_message(user_message)

                    # ④ 流式逐条返回 Bot 消息
                    for bot_msg in process_result.messages:
                        await websocket.send_json({
                            "type": "bot_message",
                            "sender_id": process_result.sender_id,
                            "message_id": process_result.message_id,
                            "data": {
                                "text": bot_msg.text,
                                "object": {
                                    "type": bot_msg.object.type,
                                    "id": bot_msg.object.id,
                                    "title": bot_msg.object.title,
                                    "attributes": bot_msg.object.attributes
                                } if bot_msg.object else None
                            }
                        })

                    # ⑤ 发送"完成"状态
                    await websocket.send_json({
                        "type": "status",
                        "sender_id": sender_id,
                        "data": {"status": "done"}
                    })

                except Exception as e:
                    # ⑥ 处理异常
                    await websocket.send_json({
                        "type": "error",
                        "sender_id": sender_id,
                        "data": {
                            "code": "PROCESS_ERROR",
                            "message": str(e)
                        }
                    })

    except WebSocketDisconnect:
        # 客户端主动断开连接
        print(f"[WebSocket] 客户端已断开连接")
    except Exception as e:
        # 其他异常，尝试发送错误信息后关闭
        print(f"[WebSocket] 发生异常: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "data": {"code": "INTERNAL_ERROR", "message": "服务器内部错误"}
            })
        except:
            pass
        await websocket.close()
```

### 3.2 注册 WebSocket 路由到主应用

在 `main.py` 中引入上述 router 即可（如果你的项目已经有 `router` 的注册逻辑则无需修改）：

```python
# main.py
from fastapi import FastAPI
from atguigu.api.routers import router

app = FastAPI(title="智能客服")

# 注册路由（包含 HTTP 和 WebSocket）
app.include_router(router)
```

### 3.3 关键设计说明

| 关注点 | 说明 |
|--------|------|
| **消息协议** | 统一使用 JSON 格式，通过 `type` 字段区分消息类型 |
| **复用逻辑** | `UserMessage.from_dict()` 和 `dialogue_service.process_message()` 与 HTTP 接口完全一致 |
| **流式推送** | 遍历 `process_result.messages`，逐条通过 `websocket.send_json()` 发送 |
| **状态通知** | 在开始处理时发送 `thinking`，完成后发送 `done` |
| **取消机制** | 客户端可发送 `type: "cancel"` 来中断服务端生成（需在 service 层实现取消逻辑） |
| **连接管理** | 每个 WebSocket 连接对应一个用户会话，断开即释放资源 |

---

## 4. 前端 WebSocket 请求示例

### 4.1 基础 HTML + JavaScript 示例（单文件）

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>智能客服 - WebSocket 聊天</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/font-awesome@4.7.0/css/font-awesome.min.css">
</head>
<body class="bg-gray-100 min-h-screen flex items-center justify-center p-4">

    <div class="w-full max-w-lg bg-white rounded-2xl shadow-lg flex flex-col h-[600px]">
        <!-- 头部 -->
        <div class="px-5 py-4 border-b flex items-center gap-3">
            <div class="w-10 h-10 bg-blue-500 rounded-full flex items-center justify-center">
                <i class="fa fa-headphones text-white text-lg"></i>
            </div>
            <div>
                <h2 class="font-semibold text-gray-800">智能客服</h2>
                <p id="statusBadge" class="text-xs text-green-500">
                    <i class="fa fa-circle"></i> 已连接
                </p>
            </div>
        </div>

        <!-- 消息区域 -->
        <div id="chatBox" class="flex-1 overflow-y-auto p-4 space-y-3 bg-gray-50">
            <!-- 消息会动态插入到这里 -->
        </div>

        <!-- 输入区域 -->
        <div class="p-4 border-t flex gap-2">
            <input
                id="messageInput"
                type="text"
                placeholder="输入消息..."
                class="flex-1 border rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400"
                onkeydown="if(event.key==='Enter') sendMessage()"
            />
            <button
                id="sendBtn"
                onclick="sendMessage()"
                class="bg-blue-500 text-white px-5 py-2 rounded-lg hover:bg-blue-600 transition font-medium"
            >
                <i class="fa fa-send"></i>
            </button>
        </div>
    </div>

    <script>
        // =============================================
        // WebSocket 聊天客户端
        // =============================================

        const WS_URL = 'ws://localhost:8000/ws/chat';
        const USER_ID = 'user_' + Math.random().toString(36).slice(2, 10);

        let ws = null;
        let currentStatus = null;  // 当前状态：thinking / typing / done

        // ---------- 连接管理 ----------

        function connect() {
            ws = new WebSocket(WS_URL);

            ws.onopen = () => {
                console.log('[WS] 已连接到服务器');
                updateStatus('connected', '已连接');
            };

            ws.onmessage = (event) => {
                const msg = JSON.parse(event.data);
                handleMessage(msg);
            };

            ws.onclose = (event) => {
                console.log('[WS] 连接已关闭', event.code, event.reason);
                updateStatus('disconnected', '已断开');
                // 可选：自动重连
                // setTimeout(connect, 3000);
            };

            ws.onerror = (error) => {
                console.error('[WS] 连接错误', error);
                updateStatus('error', '连接异常');
            };
        }

        // ---------- 发送消息 ----------

        function sendMessage() {
            const input = document.getElementById('messageInput');
            const text = input.value.trim();
            if (!text) return;

            // 检查连接状态
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                alert('未连接到服务器，请刷新页面重试');
                return;
            }

            // 构建消息体（与后端 ChatRequest Schema 对应）
            const payload = {
                type: 'message',
                sender_id: USER_ID,
                text: text,
                message_id: null,       // null 表示由服务端生成
                object: null            // 可选的附加对象
            };

            // 发送
            ws.send(JSON.stringify(payload));

            // 在聊天框中显示用户消息
            appendMessage('user', text);

            // 清空输入框
            input.value = '';
        }

        // ---------- 接收消息处理 ----------

        function handleMessage(msg) {
            switch (msg.type) {

                case 'status':
                    // 状态通知
                    const status = msg.data.status;
                    currentStatus = status;

                    if (status === 'thinking') {
                        showTypingIndicator();
                    } else if (status === 'done') {
                        hideTypingIndicator();
                    }
                    console.log('[WS] 状态:', status);
                    break;

                case 'bot_message':
                    // Bot 回复消息
                    hideTypingIndicator();
                    appendMessage('bot', msg.data.text, msg.data.object);
                    break;

                case 'error':
                    // 错误处理
                    hideTypingIndicator();
                    console.error('[WS] 服务器错误:', msg.data);
                    appendMessage('system', `错误: ${msg.data.message}`);
                    break;

                default:
                    console.warn('[WS] 未知消息类型:', msg.type);
            }
        }

        // ---------- UI 辅助函数 ----------

        function appendMessage(role, text, objectPayload) {
            const chatBox = document.getElementById('chatBox');

            const bubble = document.createElement('div');
            bubble.className = role === 'user'
                ? 'flex justify-end'
                : 'flex justify-start';

            const isUser = role === 'user';
            bubble.innerHTML = `
                <div class="max-w-[75%] px-4 py-2 rounded-2xl text-sm ${
                    isUser
                        ? 'bg-blue-500 text-white rounded-br-md'
                        : role === 'system'
                            ? 'bg-red-100 text-red-700 rounded-bl-md'
                            : 'bg-white border text-gray-700 shadow-sm rounded-bl-md'
                }">
                    ${text || ''}
                    ${objectPayload ? `
                        <div class="mt-2 p-2 bg-white/20 rounded text-xs">
                            📦 [${objectPayload.type}] ${objectPayload.title}
                        </div>
                    ` : ''}
                </div>
            `;
            chatBox.appendChild(bubble);
            chatBox.scrollTop = chatBox.scrollHeight;
        }

        function showTypingIndicator() {
            // 移除旧的 typing 指示器
            hideTypingIndicator();

            const chatBox = document.getElementById('chatBox');
            const indicator = document.createElement('div');
            indicator.id = 'typingIndicator';
            indicator.className = 'flex justify-start';
            indicator.innerHTML = `
                <div class="bg-white border px-4 py-2 rounded-2xl rounded-bl-md shadow-sm">
                    <span class="text-gray-400 text-sm">
                        <i class="fa fa-spinner fa-pulse"></i> 正在思考...
                    </span>
                </div>
            `;
            chatBox.appendChild(indicator);
            chatBox.scrollTop = chatBox.scrollHeight;
        }

        function hideTypingIndicator() {
            const indicator = document.getElementById('typingIndicator');
            if (indicator) indicator.remove();
        }

        function updateStatus(status, text) {
            const badge = document.getElementById('statusBadge');
            badge.className = 'text-xs';
            badge.innerHTML = `<i class="fa fa-circle"></i> ${text}`;

            if (status === 'connected') {
                badge.classList.add('text-green-500');
            } else if (status === 'disconnected') {
                badge.classList.add('text-red-500');
            } else if (status === 'error') {
                badge.classList.add('text-yellow-500');
            }
        }

        // ---------- 启动连接 ----------
        connect();
    </script>
</body>
</html>
```

### 4.2 前端消息协议对照表

| 方向 | type 字段 | 说明 |
|------|-----------|------|
| 客户端 → 服务端 | `message` | 发送聊天消息 |
| 客户端 → 服务端 | `cancel` | 取消当前生成 |
| 服务端 → 客户端 | `bot_message` | 逐条 Bot 回复 |
| 服务端 → 客户端 | `status` | 状态通知（thinking / done） |
| 服务端 → 客户端 | `error` | 错误信息 |

### 4.3 Vue 3 组件示例（Composition API）

```vue
<template>
  <div class="chat-container">
    <div class="messages">
      <div
        v-for="(msg, idx) in messages"
        :key="idx"
        :class="['message', msg.role === 'user' ? 'user' : 'bot']"
      >
        {{ msg.text }}
      </div>
      <div v-if="isThinking" class="typing-indicator">
        <i class="fa fa-spinner fa-pulse"></i> 正在思考...
      </div>
    </div>
    <div class="input-area">
      <input v-model="inputText" @keydown.enter="send" placeholder="输入消息..." />
      <button @click="send">发送</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue';

const WS_URL = 'ws://localhost:8000/ws/chat';
const USER_ID = 'user_' + Math.random().toString(36).slice(2, 10);

const messages = ref([]);
const inputText = ref('');
const isThinking = ref(false);
let ws = null;

function connect() {
  ws = new WebSocket(WS_URL);

  ws.onopen = () => console.log('[WS] 已连接');
  ws.onclose = () => console.log('[WS] 已断开');

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);

    switch (msg.type) {
      case 'bot_message':
        isThinking.value = false;
        messages.value.push({ role: 'bot', text: msg.data.text });
        break;
      case 'status':
        if (msg.data.status === 'thinking') isThinking.value = true;
        if (msg.data.status === 'done') isThinking.value = false;
        break;
      case 'error':
        isThinking.value = false;
        console.error(msg.data.message);
        break;
    }
  };
}

function send() {
  const text = inputText.value.trim();
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;

  messages.value.push({ role: 'user', text });
  ws.send(JSON.stringify({
    type: 'message',
    sender_id: USER_ID,
    text: text,
    message_id: null,
    object: null
  }));
  inputText.value = '';
}

onMounted(() => connect());
onUnmounted(() => ws?.close());
</script>
```

### 4.4 React 示例（Hooks）

```tsx
import { useState, useEffect, useRef, useCallback } from 'react';

const WS_URL = 'ws://localhost:8000/ws/chat';
const USER_ID = 'user_' + Math.random().toString(36).slice(2, 10);

interface ChatMessage {
  role: 'user' | 'bot' | 'system';
  text: string;
}

export default function ChatWidget() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => console.log('[WS] 已连接');
    ws.onclose = () => console.log('[WS] 已断开');

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      switch (msg.type) {
        case 'bot_message':
          setIsThinking(false);
          setMessages(prev => [...prev, { role: 'bot', text: msg.data.text }]);
          break;
        case 'status':
          setIsThinking(msg.data.status === 'thinking');
          break;
        case 'error':
          setIsThinking(false);
          setMessages(prev => [...prev, { role: 'system', text: `错误: ${msg.data.message}` }]);
          break;
      }
    };

    return () => ws.close();
  }, []);

  const send = useCallback(() => {
    const text = inputText.trim();
    if (!text || wsRef.current?.readyState !== WebSocket.OPEN) return;

    setMessages(prev => [...prev, { role: 'user', text }]);
    wsRef.current.send(JSON.stringify({
      type: 'message',
      sender_id: USER_ID,
      text,
      message_id: null,
      object: null,
    }));
    setInputText('');
  }, [inputText]);

  return (
    <div>
      <div className="messages">
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>{msg.text}</div>
        ))}
        {isThinking && <div className="typing">正在思考...</div>}
      </div>
      <div className="input-area">
        <input value={inputText} onChange={e => setInputText(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()} />
        <button onClick={send}>发送</button>
      </div>
    </div>
  );
}
```

---

## 5. 完整对比：HTTP vs WebSocket

以一个完整对话轮次为例：

### 5.1 HTTP 方式（现有）

```
客户端                                    服务端
  │                                         │
  │  POST /api/chat { text: "你好" }        │
  │ ──────────────────────────────────────→ │
  │                                         │ 处理中...
  │                                         │
  │  { sender_id, messages: [{...}, ...]}   │
  │ ←────────────────────────────────────── │
  │                                         │
  │  [连接关闭，下次请求需新建连接]            │
```

### 5.2 WebSocket 方式

```
客户端                                    服务端
  │                                         │
  │  ws://localhost:8000/ws/chat            │
  │ ═══════════════ 建立连接 ═══════════════ │
  │                                         │
  │  { type: "message", text: "你好" }      │
  │ ──────────────────────────────────────→ │
  │                                         │ 处理中...
  │  { type: "status", status: "thinking" } │
  │ ←────────────────────────────────────── │
  │                                         │
  │  { type: "bot_message", text: "您好！"} │
  │ ←────────────────────────────────────── │
  │                                         │
  │  { type: "bot_message", text: "请问..."}│
  │ ←────────────────────────────────────── │
  │                                         │
  │  { type: "status", status: "done" }     │
  │ ←────────────────────────────────────── │
  │                                         │
  │  [连接保持，可继续发送下一条消息]          │
```

---

## 6. 进阶：带身份认证的 WebSocket

### 6.1 通过 URL 参数传递 Token

```python
# 后端
@router.websocket("/ws/chat")
async def websocket_chat(
    websocket: WebSocket,
    token: str = Query(...),  # 从 URL 参数获取 token
):
    # 验证 token
    user_info = verify_token(token)
    if not user_info:
        await websocket.close(code=4001, reason="认证失败")
        return

    await websocket.accept()
    # ...
```

```javascript
// 前端
const token = 'your_jwt_token_here';
const ws = new WebSocket(`ws://localhost:8000/ws/chat?token=${token}`);
```

### 6.2 通过首条消息传递 Token

```python
# 后端：在 accept 后等待首条认证消息
await websocket.accept()
auth_msg = await websocket.receive_json()
if auth_msg.get("type") != "auth" or not verify_token(auth_msg.get("token")):
    await websocket.close(code=4001)
    return
```

```javascript
// 前端
ws.onopen = () => {
    ws.send(JSON.stringify({
        type: 'auth',
        token: 'your_jwt_token_here'
    }));
};
```

---

## 总结

| 步骤 | 做什么 |
|------|--------|
| 1 | `uv add websockets` 安装依赖 |
| 2 | 在 `routers.py` 中新增 `@router.websocket("/ws/chat")` 端点 |
| 3 | 定义 JSON 消息协议（type: message / bot_message / status / error） |
| 4 | 复用现有 `dialogue_service.process_message()` 业务逻辑 |
| 5 | 前端用 `new WebSocket(url)` 建立连接，`send()` 发送，`onmessage` 接收 |
| 6 | （可选）添加 token 认证、心跳保活、自动重连等机制 |

WebSocket 最核心的价值在于**长连接 + 服务端主动推送**，非常适合智能客服这种需要流式输出、实时互动的场景。以上所有代码均基于现有 `POST /api/chat` 的数据模型设计，无需修改现有业务逻辑即可平滑迁移。
