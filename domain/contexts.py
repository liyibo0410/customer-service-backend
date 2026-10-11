# 【导读】domain/contexts.py —— 领域层：任务/系统流程的上下文模型
# 职责：TaskContext 承载业务任务；SystemContext 五子类描述系统过场事件（靠 flow_id 判别）
# 被 state.py 引用；SystemContextUnion 用于把持久化字典反序列化成具体子类
# domain/contexts.py

# 导入类型注解工具
# Literal：用来固定字段只能取某几个特定字符串值，做类型区分
# Annotated：给类型附加额外元数据（这里用来放鉴别器discriminator）
from typing import Literal, Annotated

# 从pydantic导入模型基类、字段工具、类型适配器
# BaseModel：pydantic数据模型基类，用来定义结构化数据
# Field：给模型字段附加配置参数
# TypeAdapter：pydantic v2新增工具，专门用来解析【联合类型(Union)】
from pydantic import BaseModel, Field, TypeAdapter


# TaskContext：普通业务任务（如订单查询）的运行时上下文
class TaskContext(BaseModel):
    """
    业务任务上下文
    保存一个普通业务对话任务运行时的数据
    """
    # 流程标识（如 order_query）：决定走哪套流程，也是“恢复任务”时的匹配键
    flow_id: str                    # 业务任务的流程ID，每个对话流程唯一标识，例如"order_query"
    # 进度指针：标记当前走到流程哪一步；None=还没进入具体步骤
    step_id: str | None = None      # 业务任务下的步骤ID，标记当前走到流程哪一步；None=还没进入具体步骤
    # 槽位表：存放用户逐步提供的信息（订单号、手机号等）
    slots: dict = {}                # 业务任务执行过程中收集到的槽位数据。槽位=用户填的信息，例如订单号、手机号


# SystemContext：系统流程上下文【父类】——5 种子类共有的骨架
class SystemContext(BaseModel):
    """
    系统流程上下文【父类】
    所有系统事件上下文都要继承这个父类
    定义具体流程的通用属性：所有系统事件都会带 flow_id、step_id
    """
    # 双重身份：标记事件类型；同时充当“判别器”用于反序列化分流
    flow_id: str                    # 系统流程的流程ID，非常关键！用来区分是什么系统事件
    # 系统事件自身的步骤；多数事件用不到，默认 None
    step_id: str | None = None      # 系统流程当前执行的步骤ID


# 事件1/5：流程开始——机器人开场启动一个全新的业务任务
class StartedSystemContext(SystemContext):
    """
    流程开始事件（子类，继承SystemContext父类）
    代表：机器人开启了一个全新的业务任务
    """
    # 被启动的业务任务ID，例如 "order_status_query"
    started_flow_id: str = ""            # 新开始的业务任务ID，例如"order_status_query"
    # 任务名（如“订单状态查询”），供开场白文案使用
    started_flow_name: str = ""          # 新开始的业务任务名字，例如"订单状态查询"

    # 使用 Literal 类型固定 flow_id 值！！
    # Literal["system_task_started"]：强制这个子类实例 flow_id 只能等于 "system_task_started"
    # 这个字段就是「鉴别器(discriminator)」，pydantic靠它自动判断当前字典对应哪一个子类
    # 覆盖父类字段：本类 flow_id 恒等于固定字符串（这就是鉴别器）
    flow_id: Literal["system_task_started"] = "system_task_started"


# 事件2/5：流程中断——被别的任务抢走，旧任务挂起但可恢复
class InterruptedSystemContext(SystemContext):
    """
    流程中断事件（子类）
    场景：用户中途跳转到另一个任务，旧任务被打断挂起
    例：查订单中途，用户说"帮我查话费" → 订单任务中断，开启话费任务
    """
    # 被打断的旧任务ID（稍后会压入 DialogueState 的挂起栈）
    interrupted_flow_id: str = ""               # 被中断的旧业务任务ID
    # 旧任务名字，用于“稍后可以继续…”这类引导语
    interrupted_flow_name: str = ""             # 被中断的旧业务任务名字
    # 用户新切入的业务任务ID
    started_flow_id: str = ""                   # 新开始的业务任务ID
    # 新任务名字，用于过场文案
    started_flow_name: str = ""                 # 新开始的业务任务名字
    # 鉴别器固定值：system_task_interrupted
    flow_id: Literal["system_task_interrupted"] = "system_task_interrupted"


# 事件3/5：流程取消——任务直接作废、不会再恢复（与中断本质不同）
class CanceledSystemContext(SystemContext):
    """
    流程取消事件（子类）
    代表旧任务直接作废，不是暂停，不会再恢复
    """
    # 被取消的业务任务ID
    canceled_flow_id: str = ""          # 被取消的业务任务ID
    # 被取消任务的名字
    canceled_flow_name: str = ""        # 被取消的业务任务名字
    # 鉴别器固定值：system_task_canceled
    flow_id: Literal["system_task_canceled"] = "system_task_canceled"


# 事件4/5：流程恢复——从挂起栈把旧任务捡回来继续跑
class ResumedSystemContext(SystemContext):
    """
    流程恢复事件（子类）
    把之前中断挂起的任务重新捡回来继续执行
    """
    # 要恢复的任务ID：用来在挂起栈里精确匹配 flow_id
    resumed_flow_id: str = ""           # 被恢复的业务任务ID
    # 被恢复任务的名字，用于“好的，我们继续…”文案
    resumed_flow_name: str = ""         # 被恢复的业务任务名字
    # 鉴别器固定值：system_task_resumed
    flow_id: Literal["system_task_resumed"] = "system_task_resumed"


# 事件5/5：收集槽位——机器人反问用户，索要某项信息
class CollectedSystemContext(SystemContext):
    """
    系统流程收集槽位信息事件（子类）
    机器人向用户提问，索要某个信息（收集槽位）
    """
    # 这次想收集哪个槽位，例如 order_id
    slot_name: str = ""     # 收集的槽位名，例如"order_id"订单号
    # 提问动作：机器人发给用户的话术，如 {"text": "请提供订单号"}
    response: dict = {}     # {"text":"请告诉我你的订单号"} 机器人发给用户的提示话术
    # 鉴别器固定值：system_collect_information
    flow_id: Literal["system_collect_information"] = "system_collect_information"


# --------------------------核心难点：带鉴别器的联合类型---------------------------
# 定义系统流程的联合类型：SystemContextUnion 可以是上面5种子类的其中任意一种
# Annotated：给这个Union类型附加额外配置
# Field(discriminator="flow_id")：【鉴别器】
# 告诉pydantic：解析字典的时候，去读取字典里 flow_id 字段的值，自动匹配对应的子类！
# 例如 flow_id="system_task_started" → 自动识别成 StartedSystemContext 对象
# ★核心难点：5 个子类的“联合类型”，表示这几种事件中的任意一种
# Annotated 让联合类型挂上判别器配置：解析字典时自动按 flow_id 选子类
SystemContextUnion = Annotated[
    StartedSystemContext |
    InterruptedSystemContext |
    CanceledSystemContext |
    ResumedSystemContext |
    CollectedSystemContext,
    Field(discriminator="flow_id")
]

# 创建联合类型适配器实例！！
# TypeAdapter是pydantic v2专门用来解析Union联合类型的工具
# 你不能直接 SystemContextUnion.model_validate()，联合类型没有model_validate方法
# 必须创建适配器对象，用适配器去解析字典
# Union 没有 .model_validate，须包一层 TypeAdapter 才能解析
# 全局实例化一次复用；validate_python 即自动落成对应子类
system_context_adapter = TypeAdapter(SystemContextUnion)


# 下面这段是测试代码，只有你直接运行这个py文件才会执行
if __name__ == '__main__':

    # 模拟后端收到的原始字典数据（接口传过来的json解析后的字典）
    data = {
        "flow_id": "system_task_started",
        "step_id": "start",
        "started_flow_id": "order_status_query",
        "started_flow_name": "订单状态查询"
    }

    # 坑1：用【父类SystemContext】的model_validate解析字典
    # 父类只会读取父类自己定义的字段 flow_id、step_id
    # 子类独有的字段 started_flow_id、started_flow_name 直接被丢弃！！！
    # 这就是注释写的：父类序列化拿不到子类字段的问题
    obj1 = SystemContext.model_validate(data)
    print(type(obj1))
    print(obj1)

    # 坑2：用【具体子类】model_validate解析字典
    # 可以完整拿到所有字段，但是缺点：你代码里必须提前知道现在是哪一个子类！
    # 实际开发JSON来的时候你不知道flow_id是什么，没法手动选StartedSystemContext还是别的类
    obj2 = StartedSystemContext.model_validate(data)
    print(type(obj2))
    print(obj2)

    # ✅正确方案：使用适配器 validate_python() 解析字典
    # 适配器自动读取 flow_id鉴别器字段，自动匹配对应子类！
    # 不需要你手动判断类型，自动生成对应的子类对象，所有字段完整保留
    obj = system_context_adapter.validate_python(data)

    print(type(obj))
    print(obj) # domain/contexts.py
