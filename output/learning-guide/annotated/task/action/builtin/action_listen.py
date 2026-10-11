# ═══════════════════════════════════════════════════════════════════════════
# 文件职责：定义哨兵动作 ActionListen——只发"该等用户输入"的信号
# 所在层：task.action.builtin（内置动作，随框架一起打包，用户一般不新增这类）
# 被谁调用：builder 手动注册；FlowExecutor 外层循环识别名字后 break
# ═══════════════════════════════════════════════════════════════════════════
# task/action/builtin/action_listen.py

# 模块文档串：这个动作"什么都不做"，存在的意义就是被外层循环认出
"""
ActionListen：哨兵 action，不干任何活。
它只作为"该等用户输入了"的信号：FlowExecutor 的外层循环看到 action_name == "action_listen" 就 break，
把控制权交还用户。
"""

# Any：签名与基类保持一致（虽然一个参数都不会用到）
from typing import Any

# DialogueState：占位参数类型，保证 run 签名与基类抽象方法一致
from domain.state import DialogueState
# 继承 Action 基类、使用 ActionResult 产物类型
from task.action.base import Action, ActionResult


# 哨兵动作：不执行任何业务逻辑，唯一使命是"发停靠信号"
class ActionListen(Action):
    """
    什么都不做，返回空的 ActionResult
    """
    # 名字是硬契约：外层循环只认这串字符，别改名
    name = "action_listen"

    # run：参数一律不碰，直接交一份"空产物"（无消息、无槽位更新）
    async def run(self, state: DialogueState, action_kwargs: dict[str, Any]) -> ActionResult:
        # 空产物：信号全靠"名字"传递，外层循环看到 action_listen 就 break 收工
        return ActionResult()
