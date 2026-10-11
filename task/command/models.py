# 【导读】本文件定义"LLM 产出的结构化指令"模型：LLM 在对话中不是直接输出话术，而是输出一条 Command 指令；
# 基类 Command 只含公共字段 command(指令名)，四个子类承载各自的专属参数：
#   StartFlowCommand 启动某条流程 / SetSlotsCommand 直接写入槽位 / CancelFlowCommand 取消当前流程 /
#   ResumeFlowCommand 恢复被中断的流程；COMMAND_NAME_TO_CLASS 映射表 + 基类 from_dict 工厂，
# 与 steps.py 的 STEP_TYPE_TO_CLASS 是同一套"按字符串路由到子类"的反序列化设计(手写版 discriminated union)。
# itwwy/task/command/models.py

from typing import Any

from pydantic import BaseModel


# —— 命令基类 ——
class Command(BaseModel):
    # command 是指令类型名（如 "start_flow"），是反序列化分发的判别字段(discriminator)
    command: str

    # —— 反序列化工厂 ——
    # 拿 data 里的 command 字符串查表得到具体子类，再以整个 dict(含子类字段)构造该子类
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Command":
        clz = COMMAND_NAME_TO_CLASS[data["command"]]
        return clz(**data)

# —— 子类：启动流程 ——
# 参数 flow 指定要启动的流程 id（对应 user_flows/system_flows 中的流程 key）
class StartFlowCommand(Command):
    flow: str

# —— 子类：设置槽位 ——
# LLM 已从用户话里抽出槽位值时，直接以 dict 写入，不必再走 collect 步骤向用户提问
class SetSlotsCommand(Command):
    slots: dict[str, Any]

# —— 子类：取消流程 ——
# 无额外参数(pass)，取消当前正在进行的流程
class CancelFlowCommand(Command):
    pass


# —— 子类：恢复流程 ——
# flow 可空：不指定则恢复最近被中断的流程，指定则恢复对应流程
class ResumeFlowCommand(Command):
    flow: str | None = None


# —— 指令类型注册表：字符串 → 命令子类 ——
# 新增一种 LLM 指令时，在这里登记即可被 Command.from_dict 自动识别
COMMAND_NAME_TO_CLASS = {
    "start_flow": StartFlowCommand,
    "set_slots": SetSlotsCommand,
    "cancel_flow": CancelFlowCommand,
    "resume_flow": ResumeFlowCommand,
}


if __name__ == '__main__':
    # 自测示例：把 dict 形式的指令反序列化成 Command 子类对象
    command = {"command": "set_slots", "slots": {"order_number": "10001"}}
    print(Command.from_dict(command))
