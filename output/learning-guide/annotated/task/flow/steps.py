# 【导读】本文件定义流程的"步骤(节点)"模型：FlowStep 为基类，持有公共字段 id/type/next/description；
# 四个具体子类 StartFlowStep/EndFlowStep/ActionFlowStep/CollectFlowStep 各自把 type 重写为固定的默认枚举值，
# 相当于给模型打"类型标签"(discriminated union 可辨识联合思路)；STEP_TYPE_TO_CLASS 表 + 各子类 from_dict 实现"按 type 反序列化为对应子类"的多态工厂。
"""
步骤（节点）设计
"""
# Enum 枚举：把"步骤类型"收敛为固定常量集合，避免代码/配置里到处散落魔法字符串
from enum import Enum
# typing 泛型标注工具：List/Dict/Any 用于类型提示；Literal/Annotated 本文件备用（类型即文档）
from typing import List, Dict, Any, Literal, Annotated
# pydantic：BaseModel 提供字段声明+运行时校验+序列化；Field/TypeAdapter/field_validator 此处导入备用
from pydantic import BaseModel, Field, TypeAdapter, field_validator
# 引入 links.py 的"边"类型：步骤的 next 字段类型就用它们，让 steps 与 links 两个模块形成闭环
from task.flow.links import FlowStepLink, StaticLink, ConditionalLink, FallbackLink


# —— 回复话术定义（专门服务于 collect 步骤）——
# mode 决定回复生成方式：static = 把 text 原样发给用户；rephrase = 用 prompt 让 LLM 把 text 改写得自然些。
class ResponseDefinition(BaseModel):
    """
    响应的模式:静态模式(static) 改写模式(rephrase)
    """
    mode: str = "static"  # 响应模式
    text: str  # 必填字段
    # prompt 为可选的改写提示词：仅 mode=rephrase 时生效，交给 LLM 把 text 改写成更自然的回复
    prompt: str | None = None


# —— 步骤类型枚举 ——
# 枚举值字符串必须与 YAML 中 type 的取值一一对应，它是整条反序列化链的"键"。
class FlowStepType(Enum):
    """
    流程的步骤类型
    """
    START = "start"
    END = "end"
    ACTION = "action"
    COLLECT = "collect"


# —— 步骤基类 ——
# 汇总所有步骤公共字段：id 唯一标识；type 区分种类；next 为出边列表；description 给人/LLM 看的说明。
class FlowStep(BaseModel):
    """
    流程模版
    """
    id: str  # 步骤ID
    type: FlowStepType  # 步骤类型
    next: List[FlowStepLink] = []  # 下一步
    description: str = ""  # 步骤描述

    # —— 反序列化入口（多态工厂）——
    # from_dict 先读 raw dict 里的 type 字符串，到 STEP_TYPE_TO_CLASS 查表拿到具体子类，
    # 再把解析工作委托给"该子类的 from_dict"——典型的分发(dispatch)模式：基类只知道怎么分发。
    @classmethod
    def from_dict(cls, step_data: dict[str, Any]) -> "FlowStep":
        step_type = step_data['type']
        clz = STEP_TYPE_TO_CLASS[step_type]
        return clz.from_dict(step_data)

    # —— 公共字段解析 ——
    # 四个子类的 from_dict 都会先调它，把 dict 里的公共部分抽成可直接 ** 展开的 kwargs。
    @staticmethod
    def base_fields(base_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        加载各个步骤的基础字段
        :param base_data: 各个步骤的字典数据
        :return:
        """
        return {
            # YAML 中的 type 是字符串，此处显式转成 FlowStepType 枚举，让类型系统收口
            "id": base_data['id'],
            "type": FlowStepType(base_data['type']),
            # description 允许缺省，缺省给空字符串
            "description": base_data.get('description', ''),
            # next 一栏格式多样（字符串或列表），统一交给 build_links 解析成边对象列表
            "next": FlowStep.build_links(base_data['next'])
        }

    # —— 出边解析：把 YAML 里 next 的两种形态翻译成边对象 ——
    @staticmethod
    def build_links(link_data: str | list[Dict[str, Any]]) -> List[FlowStepLink]:
        # 1. next是字符串
        # 形态一：next: 某step_id（字符串直连）→ 包装成一条"无条件静态边"
        if isinstance(link_data, str):
            return [StaticLink(target=link_data)]

        # 2. next是列表
        # 形态二：next 是列表，列表可能混合两种元素：{if:..., then:...} 条件分支 与 {else:...} 兜底分支。
        # loader/steps 会按列表顺序依次转成边对象，引擎运行时也按该顺序逐条求值。
        else:
            links = []
            for link_dict in link_data:
                # 字典里含 if 键 → 是一条条件边：if 表达式放 condition，then 的值放 target
                if "if" in link_dict:
                    links.append(ConditionalLink(condition=link_dict['if'], target=link_dict['then']))
                # 不含 if 键（必然含 else）→ 是一条兜底边：else 的值放 target
                else:
                    links.append(FallbackLink(target=link_dict['else']))
            return links


# —— 具体步骤一：开始步骤 ——
# 流程的入口哨兵。只复用基类字段，把 type 固定为 START 即可，故 from_dict 只需要解析公共字段。
class StartFlowStep(FlowStep):
    """
    流程步骤：开始
    """
    type: FlowStepType = FlowStepType.START

    @classmethod
    def from_dict(cls, step_data: dict[str, Any]) -> "StartFlowStep":
        return cls(**FlowStep.base_fields(step_data))


# —— 具体步骤二：结束步骤 ——
# 流程的出口哨兵：走到这里流程自然结束（没有出边 / 出边为空列表）。
# 字段与 from_dict 同上，仅 type 默认值不同——继承体系用"默认值区分类型"。
class EndFlowStep(FlowStep):
    """
    流程步骤：结束
    """
    type: FlowStepType = FlowStepType.END

    @classmethod
    def from_dict(cls, step_data: dict[str, Any]) -> "EndFlowStep":
        return cls(**FlowStep.base_fields(step_data))


# —— 具体步骤三：动作步骤 ——
# 执行某个"动作"：action 是动作名，args 是动作入参（dict 模板 或 指向运行时上下文的字符串引用）。
class ActionFlowStep(FlowStep):
    """
    流程步骤：执行某一个动作
    """
    type: FlowStepType = FlowStepType.ACTION

    action: str = ""  # 行动的名字（action_listen:哨兵-等你/action_response:告诉你/action_xxxx:找东西 ）
    args: dict | str = {}  # 动作参数，选填

    @classmethod
    def from_dict(cls, step_data: dict[str, Any]) -> "ActionFlowStep":
        return cls(
            **FlowStep.base_fields(step_data),
            action=step_data['action'],
            # args 允许缺省，缺省给空 dict（注意：缺省写法让 dict 与 str 两种形态都可容纳）
            args=step_data.get('args', {})
        )


# —— 具体步骤四：收集步骤 ——
# 向用户"要一个槽位值"：slot_name 指定要填哪个槽位；response 是询问时的回复话术。
class CollectFlowStep(FlowStep):
    """
    流程步骤：收集某个槽位信息
    """
    type: FlowStepType = FlowStepType.COLLECT

    slot_name: str  # 必填字段
    response: ResponseDefinition  # 必填字段（填写的槽位）

    @classmethod
    def from_dict(cls, step_data: dict[str, Any]) -> "CollectFlowStep":
        return cls(
            **FlowStep.base_fields(step_data),
            slot_name=step_data['slot_name'],
            # response 在 YAML 里是嵌套 dict，这里递归地交给 ResponseDefinition 再做一次 pydantic 反序列化
            response=ResponseDefinition(**step_data['response'])
        )


# —— 类型注册表：字符串 → 步骤子类 ——
# FlowStep.from_dict 依赖此表把 YAML 的 type 字符串路由到正确的子类。
# 注意：表的 key 是"字符串"而非枚举值，因此与 YAML 原文直接对齐，属于配置层约定。
STEP_TYPE_TO_CLASS = {
    "start": StartFlowStep,
    "action": ActionFlowStep,
    "collect": CollectFlowStep,
    "end": EndFlowStep
}
