# ══════════════════════════════════════════════════════════════════════════
# 文件职责：定义聊天 HTTP 接口（POST /api/chat、GET /api/chat/history）
# 所在层：API 层路由（FastAPI 的 APIRouter）
# 被谁调用：api/app.py 通过 app.include_router(router) 挂载
# ══════════════════════════════════════════════════════════════════════════
# uuid：标准库，用于生成消息唯一 id
import uuid
# APIRouter 组织路由；Depends 声明"参数由依赖注入提供"
from fastapi import APIRouter, Depends

# 依赖函数：提供组装好的 DialogueService（仓库+引擎）
from api.routers.dependencies import get_dialogue_service
# API 层出入参模型：请求体/响应体/消息/对象/历史记录
from api.schemas import ChatRequest, ChatResponse, ChatBotMessage, ChatObject, HistoryResponse, HistoryMessage
# 领域模型：业务层只认这些类，与 API 模型互转
from domain.messages import ProcessResult, UserMessage, MessageType, FocusedObject
# DialogueService：对话业务的核心服务类
from service.dialogue_service import DialogueService

# 创建路由对象，后续用装饰器把各接口挂到 router 上
router = APIRouter()


# 定义路由接口

# 注册对话接口：处理 POST /api/chat（前端发消息的入口）
@router.post("/api/chat")
# chat_request 由 FastAPI 自动解析请求体；服务经 Depends 注入
async def chat_endpoint(
        chat_request: ChatRequest,
        dialogue_service: DialogueService = Depends(get_dialogue_service)
) -> ChatResponse:
    # 1. 处理输入接口模型
    # 第 1 步：接口请求模型 → 领域模型，供业务层使用
    user_message = _build_user_message(chat_request)
    # 2. 业务处理
    # 第 2 步：await 调业务服务，跑完整条对话流程
    process_result: ProcessResult = await dialogue_service.process_message(user_message)
    # 3. 处理输出接口模型
    # 第 3 步：业务结果 → API 响应模型，返回前端
    return _build_chat_response(process_result)


# 辅助函数：接口请求模型 → 领域消息模型
def _build_user_message(chat_request: ChatRequest) -> UserMessage:
    """
    将请求数据模型转换为领域数据模型

    :param chat_request: API 层的聊天请求模型
    :return: 领域层的用户消息模型
    """
    # 逐字段构造 UserMessage；message_id/type/object 三处是条件分支
    return UserMessage(
        sender_id=chat_request.sender_id,
        message_id=chat_request.message_id if chat_request.message_id else str(uuid.uuid4()),
        type=MessageType.TEXT if chat_request.text else MessageType.OBJECT,
        text=chat_request.text,
        object=FocusedObject(
            id=chat_request.object.id,
            type=chat_request.object.type,
            title=chat_request.object.title,
            attributes=chat_request.object.attributes,
        ) if chat_request.object else None
    )

# 辅助函数：领域处理结果 → API 响应模型
def _build_chat_response(process_result: ProcessResult) -> ChatResponse:
    """
    将领域处理结果转换为 API 响应模型

    :param process_result: 领域层的处理结果
    :return: API 层的聊天响应模型
    """
    # 逐条把领域消息转成 ChatBotMessage，对象同样递归转换
    return ChatResponse(
        sender_id=process_result.sender_id,
        message_id=process_result.message_id,
        messages=[
            ChatBotMessage(
                text=bot_msg.text,
                object=ChatObject(
                    type=bot_msg.object.type,
                    id=bot_msg.object.id,
                    title=bot_msg.object.title,
                    attributes=bot_msg.object.attributes
                ) if bot_msg.object else None
            )
            for bot_msg in process_result.messages
        ]
    )

# 注册历史接口：GET /api/chat/history?sender_id=xxx 拉取用户历史
@router.get('/api/chat/history')
# sender_id 来自 URL 查询参数；DialogueService 经依赖注入；返回 HistoryResponse 结构
async def history(
        sender_id: str,
        dialogue_service: DialogueService = Depends(get_dialogue_service),
) -> HistoryResponse:
    # 调 service 加载该用户的真实历史消息（按 session 展开，每条带 session_id）
    chat_message_response: list[HistoryMessage] = await dialogue_service.load_chat_history(sender_id)
    # 组装历史响应:回显 sender_id 并携带平铺后的消息列表
    return HistoryResponse(sender_id=sender_id, messages=chat_message_response)
