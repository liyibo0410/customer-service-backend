# ═══════════════════════════════════════════════════════════════════════════
# 文件职责：FlowExecutor 流程执行器——把 YAML 流程一步步推进到"执行动作"
# 所在层：task.flow（流程编排层），动作框架的调用方、流程与动作的"粘合层"
# 被谁调用：上层 service/engine 拿到一轮输入后调 run_task，产出本轮回复
# ═══════════════════════════════════════════════════════════════════════════
# task/flow/executor.py

# 模块文档串：全文主线——"两层循环"：外层跑动作、内层走流程步
"""
FlowExecutor：流程执行器。
把"零件"串起来跑：读 state -> 按 YAML 一步步推进 -> 遇到 action 交给 ActionRunner 执行
-> 该等用户时（action_listen 哨兵）退出。推进业务任务流程与系统任务流程。

两层循环：
- run_task（外层）：负责执行 action、收集消息，直到拿到 action_listen 哨兵
- advance_until_action（内层）：负责沿流程推进 step，跳过非 action 步，返回一个 ActionCall
"""

# CollectedSystemContext：系统"收集信息"过场上下文——collect 步靠它去向用户提问
from domain.contexts import CollectedSystemContext
# BotMessage：run_task 一路上把动作产出的消息攒进这个列表
from domain.messages import BotMessage
# DialogueState：整个流程推进都在读写这一个"聚合根"状态对象
from domain.state import DialogueState
# ActionResult：动作产物——只关心 slot_updates 与 messages 两个字段
from task.action.base import ActionResult
# ActionCall=动作请求单；ActionRunner=动作执行器（本文件是它的唯一调用方）
from task.action.runner import ActionCall, ActionRunner
# FlowsList：全部 YAML 流程的容器，按 flow_id 取流程对象
from task.flow.flows import FlowsList
# 三类"边"：无条件边/条件边/兜底边，_select_next_step 逐条判定走哪条
from task.flow.links import ConditionalLink, FallbackLink, StaticLink
# 四个流程步类型：start/end/action/collect，_run_step 靠 isinstance 分发
from task.flow.steps import (
    ActionFlowStep,
    CollectFlowStep,
    EndFlowStep,
    StartFlowStep,
)


# FlowExecutor：对外只暴露 run_task 一个"跑一轮"的入口
class FlowExecutor:
    """
    流程执行器：推进 yaml 中定义的业务任务流程以及系统任务流程
    """

    # run_task（外层循环）：反复"拿动作→执行动作"，直到哨兵才停
    async def run_task(self, state: DialogueState, flows: FlowsList, action_runner: ActionRunner) -> list[BotMessage]:
        """
        外层循环：找要执行的 action -> 判断要不要退场 -> 执行 action
        :return: 本轮要给用户的所有消息
        """
        # messages：本轮积累的所有回复，函数末尾一次性交还
        messages: list[BotMessage] = []
        # while True：出口只有一个——下面命中 action_listen 哨兵时 break
        while True:

            # 1. 推进流程，直到 step 类型是 action 才退出（拿到一个 ActionCall）
            # 内层循环返回一个"动作请求单"；可能一次推进了多个 step（start/collect/…）
            action_call: ActionCall = self.advance_until_action(state, flows)
            # 2. 哨兵：action_listen 表示"该等用户下一轮输入了"，结束本轮流程
            # 这一步是"交还控制权"的关键：消息已经攒够，等用户再开口
            if action_call.action_name == "action_listen":
                break

            # 3. 其他 action：交给 ActionRunner 执行；槽位更新写回 state、消息收进列表
            # 非哨兵动作才是真干活：交给 runner 后动作产物会告诉我们"说什么/写什么"
            action_result: ActionResult = await action_runner.run(action_call, state)
            # 注意：只有存在业务任务时才写回槽位（系统过场期间 active_task 可能已被清空，
            # 此时 slot_updates 一定为空，跳过即可避免对 None 操作）
            # 槽位只写回"业务任务"：set_slots 内部是 active_task.slots.update
            if action_result.slot_updates and state.active_task is not None:
                state.set_slots(action_result.slot_updates)
            # 动作产出的 messages 追加进本轮回复列表（可能一条，也可能空）
            messages.extend(action_result.messages)

        # 4. 返回本轮消息，等待用户下一轮输入
        return messages

    # advance_until_action（内层循环）：沿流程"走步"，走到要执行 action 的步才返回
    def advance_until_action(self, state: DialogueState, flows: FlowsList) -> ActionCall:
        """
        内层循环（FlowExecutor 的心脏）：沿 YAML 流程推进 step，
        跳过不需要执行 action 的步骤，遇到要执行 action 的步骤返回它的 ActionCall。
        """
        # while True：每轮必"前进一步"，走到该返回的地方自然 return
        while True:

            # 1. 获取当前任务上下文对象：系统任务优先
            # 每次迭代都重新取"当前主角"：上一步可能已让系统过场退场/切换了任务
            current_active_task = state.current_active_task()

            # 2. 没有当前任务：返回 action_listen 等用户输入。
            #    典型情况：业务流刚跑完 end（active_task 被清空）且无系统过场；或会话刚开始还没开任务
            # 没有任何任务在跑 = 无事可做，直接抛哨兵让外层结束本轮
            if current_active_task is None:
                return ActionCall(action_name="action_listen")

            # 3. 取流程对象（防御：配置错误时提前暴露，而不是一路崩下去）
            # 任务上下文只记 flow_id，流程定义要回 YAML 容器里查
            flow = flows.get_flow_by_id(current_active_task.flow_id)
            # flow_id 查不到 = YAML 里没定义这个流程，属于配置错误
            if flow is None:
                raise ValueError(f"流程不存在：'{current_active_task.flow_id}'")

            # 4. 取当前 step（防御：step_id 越界同样提前暴露）
            # 同样按 id 从流程里定位到"当前站在哪一步"
            step = flow.get_step_by_id(current_active_task.step_id)
            # step_id 对不上 = 流程文件有问题（比如把 step 删了），宁可当场报错
            if step is None:
                raise ValueError(
                    f"步骤不存在：flow='{flow.id}', step='{current_active_task.step_id}'"
                )

            # 5. 运行当前 step：返回 None 表示"这一步不产 action，继续推进"
            # 按 step 类型处理：start/end/collect 多半返回 None 继续转，action 步返回请求单
            action_call = self._run_step(state, step, flows)
            # 拿到非空请求单 = 该执行动作了，返回给外层循环
            if action_call is not None:
                return action_call

    # _run_step：四种 step 类型的"分发中枢"，用 isinstance 选对处理函数
    def _run_step(self, state: DialogueState, step, flows: FlowsList) -> ActionCall | None:
        """按 step 类型分发到四个 _run_*_step"""
        # start：流程入口哨兵，直接让位下一步
        if isinstance(step, StartFlowStep):
            return self._run_start_step(step, state)
        # end：流程出口哨兵，负责清任务上下文
        if isinstance(step, EndFlowStep):
            return self._run_end_step(state)
        # collect：收集槽位——要么已填往前走，要么派系统过场去问
        if isinstance(step, CollectFlowStep):
            return self._run_collect_step(step, state, flows)
        # action：真正的执行步，构造 ActionCall 交给外层
        if isinstance(step, ActionFlowStep):
            return self._run_action_step(step, state)
        # 未知 step 类型：不做任何推进，返回 None（保守处理）
        return None

    # _run_start_step：start 步没有可执行内容，把指针挪到 next 就算完成
    def _run_start_step(self, step: StartFlowStep, state: DialogueState) -> None:
        """start 步：推进到 next 步，返回 None 让内层循环继续"""
        self._advance_next_step(state, step)
        # 返回 None：内层 while 继续转，下一轮就会处理真正的第一个 step
        return None

    # _run_end_step：end 步——流程到头了，把"正在跑的流程"清掉
    def _run_end_step(self, state: DialogueState) -> None:
        """end 步：结束当前 flow。系统过场与业务流分别清对应上下文"""
        # 先看当前是不是"系统过场"在跑：两种流程的清理目标不同
        if state.active_system_task:
            # 系统流结束（如过场白说完）：只清系统任务，业务任务还在下面等着
            # 只清 active_system_task：业务任务原地待命，等系统让位后继续跑
            state.end_active_system_task()
        else:
            # 业务流结束：清空活跃任务
            # 没有系统任务在跑 = 是业务流走完了，直接把 active_task 置空
            state.end_active_task()
        # 返回 None：清场后让内层循环再转一圈，自然会撞上"无任务→哨兵"
        return None

    # _run_action_step：action 步——先推进指针，再回头构造这次调用的请求单
    def _run_action_step(self, step: ActionFlowStep, state: DialogueState) -> ActionCall:
        """
        action 步：先推进 next，再构造 ActionCall 返回。
        顺序不能反：如果不先推进，外层执行完 action 后内层会停在同一步，死循环反复执行同一个 action。
        """
        # ① 先把指针挪到 next（防死循环的关键：这次执行完下次就站在新一步）
        self._advance_next_step(state, step)
        # ② 再取当前步的 action 名/参数，包成请求单返回
        action_call = self._build_action_call(state, step)
        return action_call

    # _run_collect_step：collect 步——自动补槽，再判断槽位是否已填
    def _run_collect_step(self, step: CollectFlowStep, state: DialogueState, flows: FlowsList):
        """collect 步：自动补槽 + 判断槽位是否已填"""
        # 1. 尝试自动补槽（用户之前可能点过订单/商品卡片，focused_object 跨 turn 持久化）
        # 先试试"能不能不提问就填上"——用户点过卡片时能省掉一次反问
        self._try_to_fill_collect_slot_focused_object(state, step)

        # 2. 槽已填：直接走下一步
        # 槽位有值 = 信息够了，本轮不必再问，直接推进去执行后面的动作
        if state.active_task.slots.get(step.slot_name):
            self._advance_next_step(state, step)
            # 返回 None：内层继续推进，不在这里产生动作
            return None

        # 3. 槽没填：启动"收集信息"系统过场，让系统先问一句（问句来自 step.response）
        # 槽位空着 = 必须向用户要：去查"收集信息"这个系统流程的模板
        collect_flow = flows.get_flow_by_id("system_collect_information")
        # 开一个"收集信息"系统过场：记住要问哪个槽、用哪句问话，让系统流替业务流开口
        state.start_active_system_task(CollectedSystemContext(
            step_id=collect_flow.start_step().id,
            slot_name=step.slot_name,
            response=step.response.model_dump(mode="json"),
        ))
        # 过场一开，下一轮内层循环就会优先跑系统流，先执行"问话"动作
        return None

    # _try_to_fill_collect_slot_focused_object：用"聚焦对象"自动补槽
    def _try_to_fill_collect_slot_focused_object(self, state: DialogueState, step: CollectFlowStep):
        """
        用聚焦对象自动补槽：解决"用户先点卡片、后说意图"的跨 turn 场景。
        例如点过订单卡片后说"查物流"，进流程 collect order_number 时直接把卡片 id 填进去，不再多问一遍。
        """
        # 没有聚焦对象 = 用户没点过卡片，无从补起，直接放弃
        if state.focused_object is None:
            return None

        # 要收集的正是 order_number 且用户点过订单卡：把卡片 id 直接当订单号填上
        if step.slot_name == 'order_number' and state.focused_object.type == "order":
            state.set_slots({step.slot_name: state.focused_object.id})

        # 同理：收集 product_id 且点过商品卡：用商品 id 补槽
        if step.slot_name == "product_id" and state.focused_object.type == "product":
            state.set_slots({step.slot_name: state.focused_object.id})

    # _advance_next_step：所有"往前推一步"的公共方法，本质是改写 step_id
    def _advance_next_step(self, state: DialogueState, step):
        """
        所有 step 推进的公用方法：本质是改 step_id。
        把当前任务上下文记的 step_id 改成 next step 的 id。
        """
        # 先从出边里挑出目标步 id（static/条件/兜底三种链接在这里选）
        next_step_id = self._select_next_step(step, state)
        # 把任务上下文记的 step_id 覆写成新值——"推进"对状态来说就这么一行
        state.current_active_task().step_id = next_step_id

    # _select_next_step：从 step.next 出边列表里挑出要去的下一步
    def _select_next_step(self, step, state: DialogueState) -> str:
        """
        从 step.next 链接里挑出目标 step id。条件跳转的核心逻辑在这里。
        """
        # 按 YAML 里的顺序逐条试链接：先静态边、再条件边、最后兜底边
        for link in step.next:
            # 静态边：无条件跳转，第一个遇到就直接走
            if isinstance(link, StaticLink):
                return link.target          # 无条件：直接走
            # 条件边：先算条件表达式，为真才走 then 分支
            if isinstance(link, ConditionalLink):
                if self._eval_condition(state, link.condition):
                    return link.target      # 条件为真：走 then
            # 兜底边：前面的条件都没命中时走这里（相当于 else）
            if isinstance(link, FallbackLink):
                return link.target          # 兜底：前面的条件都没命中时走 else

        # 修正讲义：不再返回字面量"没有下一步"（会被写进 step_id 导致下游崩溃），而是抛出清晰错误
        raise ValueError(f"步骤 '{step.id}' 没有可匹配的下一步（next 链接未命中）")

    # _eval_condition：执行 YAML 条件表达式（如 "slots.get('product_id')"）
    def _eval_condition(self, state: DialogueState, condition: str) -> bool:
        """
        计算 YAML 条件表达式（如 "slots.get('product_id')"）。
        安全要点：eval 只给 data 里的 slots/context 两个变量，全局命名空间置空（禁 builtins），
        防止恶意字符串调用 __import__ 等做危险操作。
        """
        # 白名单思路：条件里能碰到的只有两个变量——槽位表 + 当前上下文
        data = {
            "slots": state.active_task.slots,
            # context: 当前任务上下文（系统任务优先），转成 dict 供条件里点字段
            "context": state.current_active_task().model_dump(mode="json")
        }
        # eval 受限沙箱：全局命名空间只剩空壳 {'__builtins__': None}，表达式动不了外部
        return bool(eval(condition, {'__builtins__': None}, data))

    # _build_action_call：把 action 步解析成"动作请求单"（含参数解引用）
    def _build_action_call(self, state: DialogueState, step) -> ActionCall:
        """
        构造 ActionCall：取 step 里的 action 名与参数。
        正常 args 是 dict，直接当 action_kwargs；特殊场景 args 是字符串引用（如 "context.response"），
        需要从当前系统上下文的对应字段取出真实值——一个系统流可服务不同业务场景的秘密。
        """
        # 动作名直接抄 step：这是 registry 查表用的 key
        action_name = step.action
        # 参数默认就是 dict：YAML 的 args 长啥样，原样当 action_kwargs
        action_kwargs = step.args

        # 参数是 str 而非 dict = 遇到了"字符串引用"这种特殊写法
        if isinstance(action_kwargs, str):
            # 形如 "context.response"：取 . 后面的字段名，从 active_system_task 取（如 CollectedSystemContext.response）
            # 解引用需要系统上下文在场；没有系统任务却这么写 = 配置可疑
            if state.active_system_task is None:
                # 防御：没有系统上下文却用了字符串引用，退回空参数
                action_kwargs = {}
            else:
                # "context.response" 拆成 ["context", "response"]，[1] 就是字段名
                key = action_kwargs.split(".")[1]
                # 从系统上下文的 dict 里取该字段真值——同一句问话就能服务不同业务场景
                action_kwargs = state.active_system_task.model_dump(mode="json")[key]

        # 把解析好的"动作名 + 参数"包成请求单，交还外层去执行
        return ActionCall(action_name=action_name, action_kwargs=action_kwargs)
