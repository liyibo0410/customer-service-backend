# 【导读】本文件实现 FlowLoader：负责把两个 YAML 配置文件(user_flows.yml 业务流 / system_flows.yml 系统流)
# 按"yaml -> dict -> pydantic 数据模型"的路径加载为 FlowsList；load_many 合并多文件并做全局槽位去重检查，
# load 单文件分三步(读文件/slots 槽位/各流程及其 collect 步骤用到的槽位)；
# 注意 slots 有两层语义：顶层全局槽位定义 与 每个流程内"实际要收集"的槽位子集(去重后)。
# itwwy/task/flow/loader.py

from pathlib import Path
from typing import List, Dict, Any

# PyYAML：把 YAML 文本解析为 Python 的 dict/list 原生结构
import yaml

# 引入容器类型(FlowsList/Flow/FlowSlot)与步骤类型(基类 + CollectFlowStep 判型用)
from task.flow.flows import FlowsList, Flow, FlowSlot
from task.flow.steps import FlowStep, CollectFlowStep

"""
yaml --->dict---->数据模型
"""


class FlowLoader:
    """
    流程加载器（加载两个yaml文件）
    """

    # —— 多文件批量加载入口 ——
    # 一次性喂入多个 YAML 路径(如 [user_flows.yml, system_flows.yml])，汇总成唯一的 FlowsList。
    def load_many(self, paths: List[Path]) -> FlowsList:
        flows: List[Flow] = []
        slots: Dict[str, FlowSlot] = {}
        for path in paths:
            # 1. 加载单个yaml文件的flow_list
            # 逐个加载单文件，得到"只含该文件流程"的 FlowsList
            single_flows_list = self.load(path)
            # 2. 获取单个yaml的flows
            # extend 把该文件的流程并入总列表（跨文件流程 id 理论上不重复，重复则引擎层才会暴露问题）
            flows.extend(single_flows_list.flows)
            # 3. 检测重复槽位
            # 全局槽位字典在所有文件间共享，若不同文件定义了同名槽位会互相覆盖，先求交集做防御性检查
            duplicate_slot_name = set(slots).intersection(single_flows_list.slots)
            if duplicate_slot_name:  # 去重可选(建议做去重)
                duplicates = ", ".join(sorted(duplicate_slot_name))
                raise ValueError(
                    f"flow定义中存在重复的槽位名称: {duplicates}."
                )
            # 4. 更新
            # 无冲突才把本文件的槽位并入全局字典（同名时后加载者覆盖前加载者）
            slots.update(single_flows_list.slots)
        return FlowsList(flows=flows, slots=slots)

    # —— 单文件加载入口 ——
    def load(self, path: Path) -> FlowsList:
        """
        加载单个yaml文件
        :param path:
        :return:
        """
        # 1. 读 YAML → dict
        # safe_load(而非 load)只解析纯数据结构，杜绝 YAML 标签导致的任意对象执行风险
        with  open(path, 'r', encoding="utf-8") as f:
            data: Dict[str, Any] = yaml.safe_load(f)

        # 2. 加载slots部分
        # 顶层 slots(可能为空 {})→ 槽位名 -> FlowSlot 的字典
        slots: Dict[str, FlowSlot] = self._load_slots(data.get('slots', {}))

        # 3. 加载flows部分
        # 把每个流程的 dict 转成 Flow 对象，并把全局槽位定义传进去用于收集"本流程用到的槽位"
        flows = self._load_flows(data.get('flows', {}), slots)

        return FlowsList(slots=slots, flows=flows)

    # —— 槽位加载 ——
    # 遍历 YAML 的 slots 字典，每个条目变成一个 FlowSlot(name 用字典 key，其余字段解包传入)
    def _load_slots(self, yaml_slots_data: Dict[str, Any]) -> Dict[str, FlowSlot]:
        """
        加载槽位
        :param yaml_slots_data:
        :return:
        """
        slots = {}
        for slot_name, slot_dict in yaml_slots_data.items():
            # FlowSlot(name=..., **slot_dict)：name 由外层 key 决定，type/label/description 由内层 dict 提供
            slots[slot_name] = FlowSlot(
                name=slot_name,
                **slot_dict
            )

        return slots

    # —— 流程加载 ——
    def _load_flows(self, yaml_flows_data: Dict[str, Any], slots_definition: Dict[str, FlowSlot]) -> List[Flow]:
        """
        加载流程
        :param yaml_flows_data:
        :param slots_definition:
        :return:
        """
        flows: List[Flow] = []
        for flow_id, flow_dict in yaml_flows_data.items():
            # 关键一步：把每个步骤 dict 交给 FlowStep.from_dict 多态工厂，自动变成对应子类对象(如 CollectFlowStep)
            steps = [FlowStep.from_dict(step) for step in flow_dict.get('steps', [])]
            flows.append(
                Flow(
                    # flow_id 直接使用 YAML flows 字典的 key，保持与配置文件完全一致
                    id=flow_id,
                    description=flow_dict.get('description', ''),
                    name=flow_dict.get('name'),
                    steps=steps,
                    # 槽位不再整表搬进来，只收集该流程步骤"真正用到"的那些(见 _collect_flow_slots)
                    slots=self._collect_flow_slots(slots_definition, steps)
                )
            )

        return flows

    # —— 收集某流程实际需要的槽位 ——
    # 目的是精简：LLM 读流程时只看到本流程用到的槽位，而不是几百个无关槽位。
    def _collect_flow_slots(self, slots_definition: Dict[str, FlowSlot],
                            steps: List[FlowStep]) -> List[FlowSlot]:
        """
        收集流程中的槽位
        :param slots_definition:  业务的所有流程用到的所有槽位定义
        :param steps: 当前流程的所有步骤
        :return: 当前流程要用到的槽位定义
        """
        seen = set()
        flow_slots = []
        for step in steps:

            # 只看收集步骤
            # 只有 collect 步骤才会向用户索要槽位，action 步骤不产生新槽位，直接跳过
            if not isinstance(step, CollectFlowStep):
                continue

            # 去重
            # 流程中可能会在不同的step中有重复的槽位名字
            # (LLM看流程使用的槽位：在同一个流程下 没有必要给LLM两份一样的槽位名字)
            step_slot_name = step.slot_name
            if step_slot_name in seen:
                # 流程中有重复的槽位名字不添加
                continue
            seen.add(step_slot_name)

            # 用 get,查不到不报错
            # 槽位名字可能在顶层 slots 里找不到定义，此时跳过；用 get 而不是 [] 避免 KeyError 中断整个加载
            slot_definition = slots_definition.get(step_slot_name)
            if slot_definition is not None:  # 流程中有的槽位名字对应的槽位定义有
                flow_slots.append(slot_definition)

        return flow_slots


if __name__ == '__main__':
    # 直接运行本文件可自测：加载两个 YAML 并打印结果（路径基于本文件向上两级到项目根目录）
    base_path = Path(__file__).parents[2]
    user_flow_path = base_path / 'flow_config' / 'user_flows.yml'
    system_flow_path = base_path / 'flow_config' / 'system_flows.yml'
    loader = FlowLoader()
    flows_list = loader.load_many([user_flow_path, system_flow_path])
    print(flows_list)
