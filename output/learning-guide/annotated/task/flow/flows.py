# 【导读】本文件定义流程的"容器"模型：FlowSlot 描述单个槽位；Flow 描述一条完整流程(id+步骤+槽位+起止查询方法)；
# FlowsList 是多个流程的汇总容器(由 loader 把 YAML 全量装入)，并集中维护跨流程共享的全局槽位字典 slots；
# 三个"查找方法" start_step/get_step_by_id/get_flow_by_id 都是用线性遍历实现的简单查询，供运行时引擎定位节点。
# itwwy/task/flow/flows.py

from typing import List, Dict
from pydantic import BaseModel
# 复用 steps.py 的步骤基类与 StartFlowStep(判型时用)，实现"流程包含步骤"的聚合关系
from task.flow.steps import FlowStep, StartFlowStep


# —— 槽位模型 ——
# 槽位(slot) = 一段对话中需要被填充的变量（如 order_number）。name 即 YAML 字典的 key。
class FlowSlot(BaseModel):
    """
    槽位
    """
    name: str  # 槽位的名字
    type: str = "any"  # 槽位的类型
    label: str = ""  # 槽位的标签
    description: str = ""  # 槽位的描述


# —— 流程模型 ——
# 一个 Flow 对应 YAML 中 flows 字典里的一项（如 order_status_query）：由若干步骤按 next 串联成图。
class Flow(BaseModel):
    """
    流程
    """
    id: str  # 流程的ID
    description: str = ""
    steps: List[FlowStep] = []  # 步骤
    slots: List[FlowSlot] = []  # 槽位
    name: str | None = None  # 流程名字

    # 返回本流程的"开始步骤"：运行时从哪一步进入，就靠它定位（按类型过滤 StartFlowStep）
    def start_step(self) -> StartFlowStep | None:
        """
        返回流程的开始步骤
        :return:
        """
        # 线性扫描 steps，isinstance 判断是否为 StartFlowStep（也可用 step.type == FlowStepType.START）
        for step in self.steps:
            if isinstance(step, StartFlowStep):
                return step
        # 若配置里没有 start 步骤则返回 None，调用方需要自行处理这种"坏配置"
        return None

    # 按步骤 id 查步骤：引擎执行"跳边"时，用边的 target(id) 在这里找到真正的步骤对象
    def get_step_by_id(self, step_id: str) -> FlowStep | None:
        """
        根据步骤ID获取步骤
        :param step_id:
        :return:
        """
        for step in self.steps:
            if step.id == step_id:
                return step
        return None


# —— 流程列表容器 ——
# FlowsList 同时容纳"多条流程"与"全局槽位字典"，是 FlowLoader 加载 YAML 后的最终产物。
class FlowsList(BaseModel):
    """
    流程列表
    """
    flows: List[Flow] = []
    slots: Dict[str, FlowSlot] = {}

    # 按流程 id 取流程：通常用于用户/LLM 发起某流程(如 start_flow 命令带 flow id)时的入口查询
    def get_flow_by_id(self, flow_id: str) -> Flow | None:
        """
        根据流程ID获取流程
        :param flow_id:
        :return:
        """
        for flow in self.flows:
            if flow.id == flow_id:
                return flow
        return None
