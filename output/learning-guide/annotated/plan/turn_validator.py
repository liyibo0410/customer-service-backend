# 文件导读：防幻觉校验器——只判 TurnPlan 能否执行，不出话术
# 所在层：plan 规划层，位于计划产出与执行之间的一道安检
# 被谁调用：DialogueEngine 每轮执行前调用，不过则转交 ClarifyResponder
# plan/turn_validator.py

# 只 import Dict 作类型标注：intents 是“意图id→元数据”字典
from typing import Dict

# 对话状态：knowledge 轨校验时要用聚焦对象
from domain.state import DialogueState
# 知识意图元数据：含 requires_object 字段
from knowledge.intents import KnowledgeIntent
# 原因码枚举/计划/校验结果模型都在本层 models
from plan.models import ClarifyReason, TurnPlan, TurnPlanValidationResult
# 四种命令子类：task 轨第二重用 isinstance 白名单
from task.command.models import (
    CancelFlowCommand,
    ResumeFlowCommand,
    SetSlotsCommand,
    StartFlowCommand,
)
# 真实流程表：查 start_flow 要开的流程是否真的存在
from task.flow.flows import FlowsList


# 校验器无内部状态，进程内可复用同一个实例
class TurnPlanValidator:
    """
    防幻觉校验器
    职责：检查 TurnPlan 能不能执行，不能执行就给出原因码。
    只判断、不回复——话术交给 ClarifyResponder。
    """

    # 唯一入口：给 TurnPlan 做体检，返回能不能执行
    def validate(
            self,
            state: DialogueState,
            turn_plan: TurnPlan,
            flow_list: FlowsList,
            intents: Dict[str, KnowledgeIntent],
    ) -> TurnPlanValidationResult:
        """
        校验 turn_plan
        层层收窄：先看轨道数量，再钻进具体轨道细查。
        :param state: 当前对话状态（knowledge 校验要看聚焦对象）
        :param turn_plan: LLM 产出的本轮计划
        :param flow_list: 真实流程列表（查 flow 是否存在）
        :param intents: 知识意图注册表
        :return:
        """

        # 先收集命中的轨道，再逐层收窄判定
        active_tracks = self._active_tracks(turn_plan)

        # 1. 是否没有命中轨道
        # 三轨全空=白纸计划，先拒绝
        if not active_tracks:
            # 拒绝=只回原因码，话术不归这里管
            return self._reject(ClarifyReason.MISSING_TRACK)

        # 2. 是否命中多条轨道（引擎一次只执行一个轨道）
        # 引擎一次只执行一条轨道，多轨必须让用户选
        if len(active_tracks) > 1:
            # 打回并提示二选一
            return self._reject(ClarifyReason.MULTIPLE_TRACKS)

        # 3. 获取唯一的轨道
        # 轨道名已唯一，接下来按它分流
        active_track = active_tracks[0]

        # 4. 判断轨道到底是哪一个
        # 命中业务任务轨道
        if active_track == "task":
            # 4.1 业务任务轨道
            # 钻进 task 轨做四重校验
            return self._validate_task(turn_plan, flow_list)

        # 命中信息咨询轨道
        if active_track == "knowledge":
            # 4.2 信息咨询任务轨道
            # 钻进 knowledge 轨校验
            return self._validate_knowledge(state, turn_plan, intents)

        # chitchat 不需要任何校验，命中即合法
        # chitchat 轨免检，命中即放行
        return TurnPlanValidationResult(valid=True)

    @staticmethod
    # 收集三个轨道字段里非空的轨道名
    def _active_tracks(turn_plan: TurnPlan) -> list[str]:
        """把三个字段里非 null 的轨道名收集成列表。"""
        # 结果列表
        active_tracks: list[str] = []
        # task 字段非空即登记
        if turn_plan.task is not None:
            # 追加轨道名
            active_tracks.append("task")

        # knowledge 同理登记
        if turn_plan.knowledge is not None:
            # 追加轨道名
            active_tracks.append("knowledge")

        # chitchat 同理登记
        if turn_plan.chitchat is not None:
            # 追加轨道名
            active_tracks.append("chitchat")

        # 返回活跃轨道列表
        return active_tracks

    # 统一的打回出口：只带原因码返回
    def _reject(self, reason: ClarifyReason) -> TurnPlanValidationResult:
        """返回校验失败结果，只给原因码，不生成话术。"""
        # 构造失败结果：valid=False + reason
        return TurnPlanValidationResult(
            valid=False,
            reason=reason
        )

    # task 轨四重校验，任一不过即整体拒绝
    def _validate_task(
            self,
            turn_plan: TurnPlan,
            flows: FlowsList,
    ) -> TurnPlanValidationResult:
        """
        task 轨道的四重校验：任何一重不过就拒绝。
        """

        # 取出 task 轨的计划本体
        task_plan = turn_plan.task

        # 第一重:commands 不能为空
        # 第一重：命令为空说明 LLM 空转
        if task_plan is None or not task_plan.commands:
            # 以缺命令的原因码打回
            return self._reject(ClarifyReason.MISSING_TASK_COMMANDS)

        # 第二重:每个 command 都得是认识的类型
        # 第二重白名单：只认这四种真实命令
        allowed = (StartFlowCommand, ResumeFlowCommand, CancelFlowCommand, SetSlotsCommand)
        # 出现白名单外类型=编造命令，整单拒绝
        if not all(isinstance(cmd, allowed) for cmd in task_plan.commands):
            # 以非法命令原因码打回
            return self._reject(ClarifyReason.INVALID_TASK_COMMANDS)

        # 第三重:不能一次开多个流程
        # 只筛出开流程命令来数
        start_commands = [cmd for cmd in task_plan.commands if isinstance(cmd, StartFlowCommand)]
        # 第三重：一次开多个流程，状态机顶不住
        if len(start_commands) > 1:
            # 以多流程原因码打回
            return self._reject(ClarifyReason.MULTIPLE_TASK_FLOWS)

        # 第四重:内部系统流程不允许 LLM 直接开（即便它真实存在于合并后的流程表里，
        # 直接放行会让 CommandProcessor 抛 ValueError；这里按"不存在"处理走澄清）
        # 第四重：system_ 开头是内部过场，LLM 禁开
        if start_commands and start_commands[0].flow.startswith("system_"):
            # 按“流程不存在”处理并打回
            return self._reject(ClarifyReason.UNKNOWN_TASK_FLOW)

        # 第五重:要开的流程必须真实存在（最典型的防幻觉检查）
        # 第五重：开流程前必须确认真实存在（防幻觉）
        if start_commands:
            # 按 id 查真实流程定义
            flow = flows.get_flow_by_id(start_commands[0].flow)
            # 查不到=LLM 幻觉出的流程名
            if flow is None:
                # 以“流程不存在”打回
                return self._reject(ClarifyReason.UNKNOWN_TASK_FLOW)

        # 校验成功
        # 五重全过，放行
        return TurnPlanValidationResult(valid=True)

    # knowledge 轨校验入口
    def _validate_knowledge(
            self,
            state: DialogueState,
            turn_plan: TurnPlan,
            intents: Dict[str, KnowledgeIntent],
    ) -> TurnPlanValidationResult:
        """
        knowledge 轨道校验：intents 不能为空；需要对象的意图必须有对应聚焦对象。
        """

        # 第一重校验：意图不能缺
        # 取出 knowledge 轨计划做逐项检查
        knowledge_plan = turn_plan.knowledge
        # 意图不能缺，空列表直接打回
        if knowledge_plan is None or not knowledge_plan.intents:
            # 以缺意图原因码打回
            return self._reject(ClarifyReason.MISSING_KNOWLEDGE_INTENT)

        # 取出当前聚焦对象备用
        focused_object = state.focused_object  # 取出聚焦对象
        # 逐个意图核对，防 LLM 编造
        for intent in knowledge_plan.intents:
            # 用 get 取值：LLM 可能编出注册表里没有的意图 id，直接下标会 KeyError
            # 用 get 不抛 KeyError，注册表没有=幻觉意图
            intent_meta = intents.get(intent)
            # 不在注册表等同于没给意图
            if intent_meta is None:
                # 以缺意图原因码打回
                return self._reject(ClarifyReason.MISSING_KNOWLEDGE_INTENT)

            # 读取该意图是否要求聚焦对象
            required_object = intent_meta.requires_object
            # requires_object 非空才检查对象
            if required_object is not None:  # 该意图需要某个对象才能回答
                # 没对象或对象类型对不上就打回
                if focused_object is None or focused_object.type != required_object:
                    # 以缺聚焦对象原因码打回
                    return self._reject(ClarifyReason.MISSING_FOCUSED_OBJECT)

        # 全部意图校验通过 → 放行
        return TurnPlanValidationResult(valid=True)


# 手动自测：13 个用例覆盖全部拒绝路径
if __name__ == '__main__':
    # ---- 仅测试用导入，不参与生产逻辑 ----
    from task.command.models import Command
    from task.flow.flows import Flow
    from domain.messages import FocusedObject
    from knowledge.intents import KNOWLEDGE_INTENTS
    from plan.models import TaskTurnPlan

    # 复用一个无状态实例
    validator = TurnPlanValidator()

    # 状态1：无聚焦对象
    # 默认状态：无任何聚焦对象
    state = DialogueState(sender_id="user_001")
    # 状态2：已聚焦订单对象（用于 order_info 的正向用例）
    # 正向用例状态：先聚焦一个订单对象
    state_with_order = DialogueState(
        sender_id="user_001",
        focused_object=FocusedObject(id="ORDER_10001", type="order", title="订单10001"),
    )

    # 流程列表：必须包含 refund_request，否则合法的 start_flow 会被误判为 UNKNOWN_TASK_FLOW
    # 测试流程表须含 refund_request，否则会误拒
    flow_list = FlowsList(flows=[
        Flow(id="refund_request", name="退款申请", description="处理用户退款申请"),
        Flow(id="onboarding", name="欢迎引导", description="开场欢迎"),
    ])
    # 直接用项目里的意图注册表
    intents = KNOWLEDGE_INTENTS

    # 测试小工具：打印每种情况的判定
    def run_case(name: str, turn_plan: TurnPlan, st: DialogueState = state):
        # 调用真入口 validate
        result = validator.validate(st, turn_plan, flow_list, intents)
        # valid/reason 一目了然，便于核对
        print(f"[{name}] valid={result.valid}  reason={result.reason}")

    # 1. 三轨道全空 → MISSING_TRACK
    # 空 dict：三轨键全缺 → 轨道列表为空
    run_case(" 1.无轨道          ", TurnPlan.from_dict({}))

    # 2. 同时命中 task + knowledge 两条轨道 → MULTIPLE_TRACKS
    # 两个轨道同时亮 → 数到 2 直接拦下
    run_case(" 2.多轨道          ", TurnPlan.from_dict({
        "task": {"commands": [{"command": "start_flow", "flow": "refund_request"}]},
        "knowledge": {"intents": ["refund_policy"]},
    }))

    # 3. 仅 chitchat 轨道 → 直接放行
    # 仅 chitchat 非空 → 直接放行
    run_case(" 3.仅闲聊          ", TurnPlan.from_dict({"chitchat": {}}))

    # 4. task 轨道但 commands 为空 → MISSING_TASK_COMMANDS
    # commands 空列表是假值 → 第一重不过
    run_case(" 4.commands为空     ", TurnPlan.from_dict({"task": {"commands": []}}))

    # 5. task 里出现不认识的 command 类型 → INVALID_TASK_COMMANDS
    # 绕过注册表直接造基类命令 → 第二重拦下
    run_case(" 5.未知命令类型     ",
             TurnPlan(task=TaskTurnPlan(commands=[Command(command="weird_cmd")])))

    # 6. 一次开了两个流程 → MULTIPLE_TASK_FLOWS
    # 两条 start_flow 并存 → 第三重拦下
    run_case(" 6.同时开多个流程   ", TurnPlan(task=TaskTurnPlan(commands=[
        StartFlowCommand(command="start_flow", flow="refund_request"),
        StartFlowCommand(command="start_flow", flow="onboarding"),
    ])))

    # 7. start_flow 指向不存在的流程 → UNKNOWN_TASK_FLOW
    # not_exist_flow 不在流程表 → 第五重打回
    run_case(" 7.流程不存在       ", TurnPlan.from_dict({
        "task": {"commands": [{"command": "start_flow", "flow": "not_exist_flow"}]},
    }))

    # 8. start_flow 指向真实存在的流程 → 校验通过
    # refund_request 在表里 → 五重全过
    run_case(" 8.合法开流程       ", TurnPlan.from_dict({
        "task": {"commands": [{"command": "start_flow", "flow": "refund_request"}]},
    }))

    # 9. task 只有 set_slots → 校验通过
    # 只有 set_slots 无 start_flow → 三四五重跳过
    run_case(" 9.仅设置槽位       ", TurnPlan.from_dict({
        "task": {"commands": [{"command": "set_slots", "slots": {"order_number": "ORDER_10001"}}]},
    }))

    # 10. knowledge 轨道但 intents 为空 → MISSING_KNOWLEDGE_INTENT
    # 空 intents → 知识轨第一重拦下
    run_case("10.intents为空      ", TurnPlan.from_dict({"knowledge": {"intents": []}}))

    # 11. order_info 要求聚焦订单，但 state 没有聚焦对象 → MISSING_FOCUSED_OBJECT
    # order_info 要 order 对象但默认 state 没有
    run_case("11.缺聚焦对象       ", TurnPlan.from_dict({
        "knowledge": {"intents": ["order_info"]},
    }))

    # 12a. order_info + 已聚焦订单对象 → 校验通过
    # 注入聚焦了 order 的状态 → 校验通过
    run_case("12a.有聚焦对象      ", TurnPlan.from_dict({
        "knowledge": {"intents": ["order_info"]},
    }), st=state_with_order)

    # 12b. refund_policy 本身不要求聚焦对象 → 校验通过
    # refund_policy 不要求对象 → 免检通过
    run_case("12b.无需聚焦对象    ", TurnPlan.from_dict({
        "knowledge": {"intents": ["refund_policy"]},
    }))

    # 13. start_flow 指向 system_ 开头的内部流程 → UNKNOWN_TASK_FLOW（防 LLM 选中内部过场）
    # system_ 前缀触发第四重 → 视为不存在
    run_case("13.系统流程不可开    ", TurnPlan.from_dict({
        "task": {"commands": [{"command": "start_flow", "flow": "system_task_started"}]},
    }))
