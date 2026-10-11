# ══════════════════════════════════════════════════════════════════════════
# 文件职责：定义 API 层出入参 pydantic 模型（请求/响应/消息/对象）
# 所在层：API 层（schemas 只描述接口数据结构，不含业务逻辑）
# 被谁调用：chat_router 等引入做类型标注，FastAPI 自动校验
# ══════════════════════════════════════════════════════════════════════════
# itwwy/api/schemas.py

# pydantic 模型基类：声明式定义结构，自动校验与序列化
from pydantic import BaseModel


# 聚焦对象模型：对应前端点击订单/商品卡片时携带的数据
class ChatObject(BaseModel):
    """
    聚焦对象：
    对应前端点击订单/商品卡片时带的数据
    """
    # type：必填字符串，业务上区分 order / product
    type: str # 聚焦对象的类型 order、product
    # id：对象唯一标识，必填字符串
    id: str # 对象 id
    # str | None = None：可选字段，标题不传时默认 None
    title: str | None = None # 对象标题
    # attributes：扩展属性字典，默认空字典存金额/状态等杂项
    attributes: dict = {} # 扩展属性，默认空字典


# 对话请求体模型：POST /api/chat 的请求结构
class ChatRequest(BaseModel):
    """
    请求对象（用户问题）
    `POST /api/chat` 的请求体
    注意：
    text 和 object 都是可选的，但实际使用中至少要传一个
    文本消息传 text，对象消息传 object
    """
    # sender_id：用户唯一标识，必填字段
    sender_id: str # 用户唯一标识
    # message_id：客户端消息 id，可选；不传则服务端生成
    message_id: str | None = None # 客户端消息 id，不传则服务端生成
    # text：文本消息内容，发文字提问时填充
    text: str | None = None # 文本消息内容
    # object：对象消息内容，点订单/商品卡片时填充
    object: ChatObject | None = None # 对象消息内容


# 单条机器人回复模型：回复可以是文本或对象卡片
class ChatBotMessage(BaseModel):
    """
    机器人消息
    """
    # 回复文本，可为空（纯对象卡片回复时无文本）
    text: str | None = None
    # 回复携带的对象卡片，可为空
    object: ChatObject | None = None


# 对话响应体模型：POST /api/chat 的返回结构
class ChatResponse(BaseModel):
    """
    响应对象（机器人回复）
    """
    # sender_id：回显当前会话用户 id
    sender_id: str
    # message_id：本次处理的消息 id
    message_id: str
    # messages：机器人回复列表，一次可返回多条
    messages: list[ChatBotMessage]


# 单条历史消息模型：只区分 user / bot 两个角色
class HistoryMessage(BaseModel):
    """
    历史消息
    """
    # session_id：消息所属的后端会话 id（保留归属，供前端分组/折叠展示，day11）
    session_id: str
    # role:消息角色,固定取 user / bot 两值
    role: str  # user or bot
    # text：历史文本内容，可为空
    text: str | None = None
    # object：历史对象卡片，可为空
    object: ChatObject | None = None

# 历史记录响应体模型：GET /api/chat/history 的返回结构
class HistoryResponse(BaseModel):
    """
    历史消息列表
    `GET /api/chat/history` 的返回体。
    """
    # sender_id：回显请求方用户 id
    sender_id: str
    # messages：该用户的历史消息列表
    messages: list[HistoryMessage]
