# 导读·职责：三轨道计划模型+澄清枚举+校验结果
# 导读·层位：plan 数据层;TurnPlanner 还原落这
# 导读·pydantic:字段自动校验;走 from_dict 还原
# plan/models.py
# json 库:__main__ 自测里把 JSON 字符串转成 dict 用
import json
# Enum:ClarifyReason 继承 str,可当串比较
from enum import Enum
# Command:所有命令的基类/判别器,子类用 command 字段区分类型
from task.command.models import Command
# pydantic 基类:声明式定义字段,自动校验类型/序列化
from pydantic import BaseModel

# 子计划一:task 轨道——一组要执行的动作命令(开流程/填槽/取消/恢复)
class TaskTurnPlan(BaseModel):
    # 命令列表:每个 dict 经 Command.from_dict 还原
    commands: list[Command] = [] # 命令

    # 类方法:dict→TaskTurnPlan 统一还原入口
    @classmethod
    def from_dict(cls, data: dict) -> "TaskTurnPlan":
        # 列表推导逐个还原命令;LLM 漏字段/给错类型这里会抛异常(设计如此)
        return cls(commands=[Command.from_dict(command) for command in data["commands"]])

# 子计划二:knowledge 轨道——用户想咨询哪类信息(意图 id 列表)
class KnowledgeTurnPlan(BaseModel):
    # LLM 从"知识意图清单"里挑命中的意图,如 ["refund_policy"]
    intents: list[str] = [] # 意图

    # 类方法:dict → KnowledgeTurnPlan 的还原入口
    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeTurnPlan":
        # 字符串列表直接透传,不需要逐元素加工
        return cls(intents=data["intents"])

# 子计划三:chitchat 轨道——闲聊不携带数据,空类占位即可
class ChitchatTurnPlan(BaseModel):
    # 空类也得有方法体,pass 就是"什么都不做"的占位
    pass

# 顶层计划:三轨道同时只有命中的非 None,可多轨道并存(但互斥时校验器把关)
class TurnPlan(BaseModel):
    """
    本轮对话的规划结果
    """
    # 命中业务:非 None 才带 commands 去执行
    task: TaskTurnPlan | None = None # 业务任务的轨道
    # 命中知识咨询:非 None 时承载命中的意图 id,后续章节接知识处理器
    knowledge: KnowledgeTurnPlan | None = None  # 信息咨询业务轨道
    # 命中闲聊:非 None 即纯闲聊,空对象即可
    chitchat: ChitchatTurnPlan | None = None  # 闲聊业务轨道

    # 顶层还原入口:TurnPlanner 拿到 LLM dict 后第一个调的就是它
    @classmethod
    def from_dict(cls, data: dict) -> "TurnPlan":
        # data.get 判命中:命中才建子计划,否则 None
        return cls(
            # task 轨道:先判断非 None 再还原,避免把 null 误建成空对象
            task=TaskTurnPlan.from_dict(data["task"]) if data.get("task") is not None else None,
            # knowledge 同理:null 表示用户没咨询知识
            knowledge=KnowledgeTurnPlan.from_dict(data["knowledge"]) if data.get("knowledge") is not None else None,
            # chitchat 无数据可还原:只要字段存在就算命中,给个空对象
            chitchat=ChitchatTurnPlan() if data.get("chitchat") is not None else None,
        )

# 澄清原因码:说明为何不执行,str 可当串
class ClarifyReason(str, Enum):
    # LLM 一条轨道都没命中,三轨道全 null
    MISSING_TRACK = "missing_track"
    # 同时命中多条轨道产生歧义,让用户选一个
    MULTIPLE_TRACKS = "multiple_tracks"
    # 说在办业务但 commands 是空的,没给出任何命令
    MISSING_TASK_COMMANDS = "missing_task_commands"
    # 走知识咨询轨道却没给任何意图 id
    MISSING_KNOWLEDGE_INTENT = "missing_knowledge_intent"
    # 需要"点击对象"当上下文(如帮我退这个)却没点过卡片
    MISSING_FOCUSED_OBJECT = "missing_focused_object"
    # 只点了对象没说诉求,得追问用户要干嘛
    OBJECT_REQUIRES_INTENT = "object_requires_intent"
    # 命令命令类型不认识或字段非法,LLM 没按协议写
    INVALID_TASK_COMMANDS = "invalid_task_commands"
    # 一条回复里出现多个流程命令,不知道该跑哪个
    MULTIPLE_TASK_FLOWS = "multiple_task_flows"
    # 引用可用清单外的 flow id=幻觉典型
    UNKNOWN_TASK_FLOW = "unknown_task_flow"

# 校验结果:validator 的返回类型,只判断不回复
class TurnPlanValidationResult(BaseModel):
    # 是否放行执行:False 时引擎改走澄清流程
    valid: bool # 是否有效
    # 不放行的具体原因码;valid=True 时通常为 None
    reason: ClarifyReason | None = None #无效时的原因

# 自测:直接运行本文件才执行,import 不跑
if __name__ == '__main__':


    # 样本1:用户要退款→task 轨 start_flow
    json_str1 = """
    {
      "task": {
        "commands": [
          {"command": "start_flow", "flow": "refund_request"}
        ]
      },
      "knowledge": null,
      "chitchat": null
    }
    """

    # json.loads:字符串→dict→from_dict→TurnPlan
    # 转成dict
    turn_plan1 = TurnPlan.from_dict(json.loads(json_str1))
    # 打印对象:task 被填命令,另两轨道 None
    print(turn_plan1)

    # 场景2样本:用户补了个订单号→task 轨道 set_slots 填槽
    json_str2 = """
    {
      "task": {
        "commands": [
          {"command": "set_slots", "slots": {"order_number": "A001"}}
        ]
      },
      "knowledge": null,
      "chitchat": null
    }
    """
    # 同样的 TurnPlan 还原逻辑,这次演示的是第二种命令
    # 转成dict
    turn_plan2 = TurnPlan.from_dict(json.loads(json_str2))
    print(turn_plan2)
