# 【导读】domain/messages.py —— 领域层：对话消息的数据模型
# 职责：定义 UserMessage/BotMessage/ProcessResult 与 MessageType 枚举，不含业务逻辑
# 被 state.py 及各编排层 import，作为用户输入与机器人回复进出的统一“信封”
# itwwy/domain/messages.py

# 模块文档字符串：先说明本文件定义了用户/机器人两种消息类型
"""
消息类型：两种
UserMessage(用户)
BotMessage(机器人)
"""
# 导入枚举工具：用来声明取值固定、可读性好的常量集合
from enum import Enum
# 导入 pydantic 模型基类：声明字段即可自动校验与序列化
from pydantic import BaseModel, Field
from typing import Optional

# FocusedObject：夹带在消息里的“业务对象”（如订单卡片、商品卡片）
class FocusedObject(BaseModel):
    """
    聚焦对象
    """
    # 必填：业务对象唯一标识（如 order_id、product_id）
    id: str                              # 对象的唯一标识（如order_id、product_id）
    # 必填：对象种类标签（如 “order”、”product”），配合 id 锁定具体数据
    type: str                            # 对象类型（如 “order”, “product”）
    # 展示标题（如”纯棉T恤”）；可空，省略时前端自行兜底
    title: Optional[str] = None             # 对象的标题（如 “纯棉T恤”）
    # 预留扩展信息；使用 Field(default_factory=dict) 避免可变默认值陷阱
    attributes: dict = Field(default_factory=dict)                # 其他额外信息

# MessageType：消息“载体”枚举——内容装的是纯文本还是业务对象
class MessageType(Enum):
    # 文本类型；枚举值用字符串，方便入库与接口传输
    TEXT = "text"  # 文本类型
    # 对象类型；表示消息携带一个 FocusedObject
    OBJECT = "object"  # 对象类型

# 用户消息模型
# UserMessage：用户发来的消息；text 与 object 按 type 二选一
class UserMessage(BaseModel):
    # 必填：消息发送者（用户）标识
    sender_id: str                       # 用户ID(必填字段)
    # 必填：消息唯一编号，用于日志追踪与幂等去重
    message_id: str                      # 消息ID(必填字段)
    # 必填：消息类型，决定后续走“文本”还是“对象”处理分支
    type: MessageType                    # 消息类型（text or object）必填字段
    # 文本正文；仅 type=TEXT 时有效，否则为 None
    text: str | None = None              # 文本消息
    # 业务对象；仅 type=OBJECT 时有效，与 text 互斥
    object: FocusedObject | None = None  # 对象类型的消息

# 机器人消息模型
# BotMessage：机器人的一条回复，字段与 UserMessage 基本对称
class BotMessage(BaseModel):
    # 回复文本（可空）
    text: str | None = None
    # 可附带返回一个业务对象卡片（可空）
    object: FocusedObject | None = None

# ProcessResult：整轮处理完的“结果包”，统一交还给上层/前端
class ProcessResult(BaseModel):
    # 这批回复要回给哪个用户
    sender_id: str  # 用户ID
    # 本次处理结果内部生成的消息号
    message_id: str  # 消息ID(内部生成)
    # 机器人全部回复的列表，前端按顺序逐条渲染
    messages: list[BotMessage]  # 回复消息（机器人回复的所有消息都给前端）

# __main__ 测试块：直接运行本文件时自测，被 import 时不会执行
if __name__ == '__main__':
    # 最简构造：只传必填参数 id、type，其余字段取默认值
    fo = FocusedObject(id="1", type="2")   # 聚焦对象

    # 把 Python 对象变成字典
    data = fo.model_dump(mode='json')
    # 把字典还原成 Python 对象
    obj = FocusedObject.model_validate(data)

    # fo 是一个 FocusedObject 实例
    print(type(fo))                       #FocusedObject对象
    # data 是 dict（model_dump 序列化后的普通字典）
    print(type(data))                     #dict字典
    # obj 被 model_validate 还原成 FocusedObject 实例
    print(type(obj))                      #FocusedObject对象
