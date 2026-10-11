# ═══════════════════════════════════════════════════════════════════════════
# 文件职责：定义 ActionCall（一次动作调用请求）与 ActionRunner（动作执行器）
# 所在层：task.action 动作框架，位于 registry 之上、flow 之下
# 被谁调用：task/flow/executor.py —— 每遇到 action 步就调 runner.run 去执行
# ═══════════════════════════════════════════════════════════════════════════
# task/action/runner.py

# 模块文档串：一个是"请求单"，一个是"调度器"，把动作的"声明"与"执行"解耦
"""
ActionRunner 与 ActionCall：
- ActionCall：一次动作调用请求（调哪个 action + 传什么参数），由 FlowExecutor 构造
- ActionRunner：查表 -> 调用 -> 返回，自己不关心 action 内部逻辑
"""

# Any：action_kwargs 的内容随 YAML 变化，类型不固定
from typing import Any

# pydantic：让 ActionCall 成为可校验的请求结构，构造错误能尽早暴露
from pydantic import BaseModel

# 产物类型：runner 跑完动作后，要把结果原样交还给上层
from task.action.base import ActionResult
# 注册表：runner 查"名字→实例"的唯一数据来源（执行器的"字典"）
from task.action.registry import ActionRegistry
# 对话状态：调动作时原样传进去，动作靠它读写槽位
from domain.state import DialogueState


# ActionCall：一次动作调用的"请求单"，executor 负责填好再交给 runner
class ActionCall(BaseModel):
    """一次动作调用请求：装着 action 名字和参数字典"""
    # 要调哪个动作：就是注册表里那张表的 key
    action_name: str
    # 传给动作 run() 的参数：通常直接取自 YAML 步骤里的 args
    action_kwargs: dict[str, Any] = {}


# 开闭原则：加新动作只需新增子类+注册，runner 与 registry 一行都不改
# 面向修改关闭，面向扩展开放
class ActionRunner:
    """
    通过给定的 action_call，执行 action
    """
    # 构造：注册表用"注入"的方式传进来，runner 自己不 new 任何动作
    def __init__(self, registry: ActionRegistry) -> None:
        # 存下注册表引用：查表与执行都靠它，runner 保持轻量
        self.registry = registry

    # run：一次动作调用的统一执行入口，三步走通"名字→代码"的翻译
    async def run(self, action_call: ActionCall, state: DialogueState) -> ActionResult:
        # 1. 获取 action 的名字
        # 第一步：从请求单上取出动作名（此刻还只是一个字符串）
        action_name = action_call.action_name

        # 2. 从 Action 注册中心获取名字对应的 Action 实例
        # 第二步：名字翻译成实例——查不到时 registry.get 会抛 KeyError 提前暴露
        action = self.registry.get(action_name)

        # 3. 调用具体 Action 的逻辑
        # 第三步：把 state 与参数交给实例，await 等它干完活（可能要调外部接口）
        return await action.run(state, action_call.action_kwargs)
