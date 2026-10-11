# ═══════════════════════════════════════════════════════════════════════════
# 文件职责：动作框架的基石——产物模型 ActionResult + 抽象基类 Action
# 所在层：task.action 动作框架（编排层的一部分），其余 action 文件都依赖它
# 被谁调用：registry/runner/builder，以及 builtin/custom 下所有 Action 子类
# ═══════════════════════════════════════════════════════════════════════════
# task/action/base.py

# 模块文档串：本文件先定义两个核心名词，全框架都围绕它们转
"""
Action 框架的基石：
- ActionResult：一个 action 干完活的产物（回复消息 / 要写回 state 的槽位）
- Action：所有动作的抽象基类，自定义 action 继承它并实现 run
"""

# ABC=抽象基类；abstractmethod=装饰器，用来声明"子类必须实现"的方法
from abc import ABC, abstractmethod
# Any：槽位值的类型不可预知，用 Any 表示"放行任意类型"
from typing import Any

# pydantic 模型基类：声明字段即可拿到校验与序列化能力
from pydantic import BaseModel

# BotMessage=机器人回复模型，ActionResult.messages 列表里的元素类型
from domain.messages import BotMessage
# DialogueState=对话状态"聚合根"：action 干活时读写槽位全靠它
from domain.state import DialogueState


# 产物模型：action 干完活后交回给框架的"结果信封"
class ActionResult(BaseModel):
    """
    动作的产物。
    一个 action 干完活，产出两类东西之一（或都不产出）：
    - messages     : 要发给用户的回复（生成回复类 action 用）
    - slot_updates : 要写回 state 的槽位（查询类 action 用，留给 action_response 去"说"）
    """
    # 产物通道一：直接对用户说话（action_response 等"回复类动作"填这里）
    messages: list[BotMessage] = []       # 要发给用户的回复
    # 产物通道二：只写槽位、不开口（查单/查物流等"查询动作"走这里，话术留给后面说）
    slot_updates: dict[str, Any] = {}     # 要写回 state 的槽位


# 动作基类：一个 Action 子类 = 对话流程里一个可执行的最小动作单元
class Action(ABC):
    """
    所有动作的抽象基类。
    每个 action 要做两件事：
. 定一个唯一的 name（和 YAML 里 action: xxx 对上）
. 实现 async run：拿 state 和参数干活，返回 ActionResult
    run 必须是 async 的——很多 action 要调外部接口（查订单/物流），是慢 I/O。
    """
    # 类属性而非实例属性：唯一名字，注册表拿它当 key，必须与 YAML 的 action 名一致
    name: str  # Action 的名字，注册表用它做 name -> 实例 的索引

    # 抽象方法装饰器：子类不实现 run 就无法实例化，防止"空壳动作"混上线
    @abstractmethod
    # run：动作的"干活入口"。入参=state 与 action_kwargs，返回 ActionResult
    async def run(
            self,
            state: DialogueState,
            action_kwargs: dict[str, Any],
    ) -> ActionResult:
        """子类必须实现：执行这个动作并返回产物"""
        # pass 占位：抽象方法体留空，具体逻辑全部由子类重写
        pass
