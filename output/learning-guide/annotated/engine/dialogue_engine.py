# 导读·职责：调度中枢,自己不干活,把活分给各专员
# 导读·层位：engine 调度层,service 之下执行模块之上
# 导读·调用链：dialogue_service 收到消息即调本类
# engine/dialogue_engine.py

# 会话超时要用系统时钟,time.time() 返回当前秒级时间戳
import time
# 类型注解:声明 OBJECT_TYPE_TO_SLOT 字典
from typing import Dict

# 澄清专员:拿着"原因码"去生成一句自然追问(保底话术/调LLM润色)
from clarify.responder import ClarifyResponder
# 消息层:UserMessage/BotMessage/FocusedObject
from domain.messages import BotMessage, FocusedObject, MessageType, ProcessResult, UserMessage
# DialogueState:会话/任务/待提交轮次都在此
from domain.state import DialogueState
# 闲聊轨道专员:把用户的话+历史交给 LLM 自然回一句
from chitchat.handler import ChitChatHandler
# 知识轨道专员:按意图找知识源,检索后拼接生成回复
from knowledge.handler import KnowledgeHandler
# ClarifyReason 枚举:9 种"为什么没听懂/没执行"的原因码
from plan.models import ClarifyReason
# TurnPlanner:调 LLM 把用户话解析成 TurnPlan
from plan.turn_planner import TurnPlanner
# TurnPlanValidator:防幻觉校验,拦下编造输出
from plan.turn_validator import TurnPlanValidator
# 命令模型:Command 基类,SetSlotsCommand 填槽用
from task.command.models import Command, SetSlotsCommand
# FlowsList:装载全部流程定义的对象,按 id 查流程/步骤用
from task.flow.flows import FlowsList
# CollectFlowStep:流程里"收集某个槽"的步骤
from task.flow.steps import CollectFlowStep
# TaskHandler:task 轨道执行专员——跑命令、推流程、攒机器人回复
from task.handler import TaskHandler

# 会话最长空闲 1 小时(秒),超时就视为"凉了",关旧会话开新会话
# 会话超时时间：超过这个时长没有活动就关闭旧会话、开新会话
SESSION_TIMEOUT_SECONDS = 60 * 60

# 对象类型->槽位名 的查表:前端点"订单卡片"就翻译成给订单号槽填值
# 对象类型 -> 该类型能填的槽位名（点击卡片时按此映射转成 SetSlotsCommand）
OBJECT_TYPE_TO_SLOT: Dict[str, str] = {
    # 点击订单卡片 → 转成填订单号槽
    "order": "order_number",
    # 点击商品卡片 → 转成填商品 id 槽
    "product": "product_id",
}


# DialogueEngine:把理解/执行/澄清全外包
class DialogueEngine:
    """
    对话引擎：只负责调度，不干活。

    引擎自己不做具体处理，它持有一堆"专员"：
    - turn_planner        : 调 LLM，把用户意图变成 TurnPlan
    - turn_plan_validator : 防幻觉校验，判断 TurnPlan 能不能执行
    - task_handler        : 执行 task 轨道（命令处理 + 流程推进）
    - clarify_responder   : 把原因码变成一句自然追问
    - knowledge / chitchat : 后续章节接入
    """

    # 构造函数:依赖注入——引擎不 new 专员,由外部组装好后传进来(方便测试替换)
    def __init__(
            self,
            turn_planner: TurnPlanner,
            task_handler: TaskHandler,
            knowledge_handler: KnowledgeHandler,
            chitchat_handler: ChitChatHandler,
            clarify_responder: ClarifyResponder,
            turn_plan_validator: TurnPlanValidator,
    ) -> None:
        # 记住规划专员引用:意图识别全交给它
        self.turn_planner = turn_planner
        # 记住任务执行专员引用:task 轨道的命令都交给它
        self.task_handler = task_handler
        # 记住知识专员引用:knowledge 轨道按意图检索知识并作答
        self.knowledge_handler = knowledge_handler
        # 记住闲聊专员引用:chitchat 轨道自然回一句
        self.chitchat_handler = chitchat_handler
        # 记住澄清专员引用:听不懂时由它生成追问话术
        self.clarify_responder = clarify_responder
        # 记住校验专员引用:执行前先过它的防幻觉检查
        self.turn_plan_validator = turn_plan_validator

    # 主入口:一条消息固定走"准备/开turn/分流/回填提交/组装返回"五步
    async def process_message(self, dialogue_state: DialogueState,
                              user_message: UserMessage) -> ProcessResult:
        """
        处理一条用户消息：准备会话 -> 开启 turn -> 分流处理 -> 收尾提交
        :param dialogue_state:
        :param user_message:
        :return:
        """

        # 第一步:先保证有个能用的当前会话(可能要新建/换新)
        # 1. 准备会话
        self._prepare_session(dialogue_state)

        # 第二步:把用户消息装进"待提交轮次"暂存区,此刻还没进历史
        # 2. 开启本轮 turn
        self._begin_turn(dialogue_state, user_message)

        # 第三步:按消息类型分流——文本走 LLM 规划,对象走点击卡片逻辑
        # 3. 按消息类型分流
        if user_message.type is MessageType.TEXT:
            # 文本消息走最复杂的"LLM 规划+执行"分支
            messages = await self._handle_text_message(state=dialogue_state)
        else:
            # 对象消息:先记住"用户正在看什么",后面回应要用这个上下文
            # 对象消息：先把点击的对象记成 focused_object，再决定怎么回应
            self._remember_focused_object(dialogue_state, user_message)
            # 再调对象消息处理器:能填槽就推进,否则澄清或让流程继续
            messages = await self._handle_object_message(
                message=user_message,
                state=dialogue_state,
            )

        # 第四步:把刚产出的机器人回复回填进本轮 turn
        # 4. 把本轮回复写入 turn
        if dialogue_state.pending_turn is not None:
            # 把引擎产出的回复列表追加到本轮暂存轮次的 bot_messages 上
            dialogue_state.pending_turn.bot_messages.extend(messages)
            # commit 时机:必须先让回复挂上 turn,再整体进 session 历史
            # 提交：turn 进入 session 历史
            dialogue_state.commit_turn()

        # 第五步:按路由层约定回传,只带收发标识与回复,不带内部状态
        # 5. 组装返回结果
        return ProcessResult(
            sender_id=user_message.sender_id,
            message_id=user_message.message_id,
            messages=messages,
        )

    # 会话准备:取会话/没会话就新建/超时就关旧开新并清理运行时残留
    def _prepare_session(self, dialogue_state: DialogueState) -> None:
        """
        准备会话
        :param dialogue_state:
        :return:
        """

        # 从 state 里取出当前会话(可能还没有)
        # 1. 获取当前会话
        session = dialogue_state.current_session()

        # 分支一:新用户首条消息,没有会话就新建一个
        # 2. 如果当前会话不存在，则创建一个会话
        if session is None:
            # start_session 内部会建 Session 并设为当前会话
            dialogue_state.start_session()
            # 新建完直接返回,不用再判断超时
            return

        # 分支二:已有会话,判断它是不是空闲超时了
        # 3. 判断会话是否超时
        now = time.time()
        # 距上次活跃超过阈值就判定超时,要换新会话
        if now - session.last_activity_at > SESSION_TIMEOUT_SECONDS:
            # 超时第一步:给旧会话盖上关闭时间戳,清空 current_session_id
            # 关闭会话
            dialogue_state.close_current_session()
            # 超时第二步:清掉任务/挂起/聚焦对象等运行时字段,防串台到新会话
            # 重置运行时状态
            dialogue_state.reset_runtime_state_for_new_session()
            # 超时第三步:旧会话归档完毕,开新会话承接本条消息
            # 创建会话
            dialogue_state.start_session()
        else:
            # 会话未超时:沿用当前会话,不进重建分支
            # 没超时:续期——把"最后活跃时刻"刷新成现在
            # 更新会话（会话续期）
            session.last_activity_at = now

    # 开 turn:用户消息包成 Turn 放待提交区
    def _begin_turn(self, dialogue_state: DialogueState, user_message: UserMessage) -> None:
        """
        开始一个 turn
        :param dialogue_state:
        :param user_message:
        :return:
        """
        # 内部:有当前会话才建 pending_turn,没会话则静默跳过
        dialogue_state.begin_turn(user_message)

    # 文本消息主分支:LLM 规划→防幻觉校验→按轨道分发(今天的学习主线)
    async def _handle_text_message(self, state: DialogueState) -> list[BotMessage]:
        """
        处理文本消息：调 LLM 规划 -> 防幻觉校验 -> 按轨道分发
        :param state:
        :return:
        """

        # 步骤一:TurnPlanner 结合上下文猜用户意图
        # 1. 调 LLM 生成本轮计划（确定任务轨道）
        turn_plan = await self.turn_planner.predict(state, self.task_handler.flows)
        # 兜底分支:返回空计划说明"三轨道全没命中",等价没听懂
        if turn_plan is None:
            # 直接走澄清:M   ISSING_TRACK 原因码交给话术专员生成追问
            return await self.clarify_responder.respond(
                state=state, reason=ClarifyReason.MISSING_TRACK,
            )

        # 步骤二:LLM 输出结构对但内容可能是编的,一律先过校验器
        # 2. 防幻觉校验：结构对但内容不合法的 LLM 输出，一律拦下走澄清
        validation = self.turn_plan_validator.validate(
            state=state,
            turn_plan=turn_plan,
            flow_list=self.task_handler.flows,
            # 校验白名单与知识轨道共用同一份意图注册表
            intents=self.knowledge_handler.knowledge_intents,
        )
        # 校验不过:本轮不执行,把具体原因码带去澄清(比笼统"没听懂"更准)
        if not validation.valid:
            # 回澄清话术:把 validation 给出的具体原因码带上
            return await self.clarify_responder.respond(
                state=state,
                reason=validation.reason or ClarifyReason.MISSING_TRACK,
            )

        # 步骤三:校验通过,按命中的轨道把执行权交出去
        # 3. 按轨道分发
        if turn_plan.task is not None:
            # task 轨道:把命令列表交给任务执行专员(今天真实执行的轨道)
            return await self.task_handler.handle(
                commands=turn_plan.task.commands,
                state=state,
            )
        # elif:task 为空但知识意图命中,转 knowledge 轨道
        elif turn_plan.knowledge is not None:
            # knowledge 轨道:把命中的知识意图交给知识专员,检索知识后作答
            return await self.knowledge_handler.handle(
                intents=turn_plan.knowledge.intents,
                state=state,
            )
        # 兜底:两轨道皆空,当闲聊处理
        else:
            # chitchat 闲聊轨道:把本轮消息+历史交给闲聊专员自然回一句
            return await self.chitchat_handler.handle(state=state)

    # 对象消息三分支:A能填槽推进 / C在流程不打断 / B没流程去澄清
    async def _handle_object_message(
            self,
            message: UserMessage,
            state: DialogueState,
    ) -> list[BotMessage]:
        """
        对象消息三分支：能填槽（推进）/ 在流程但不匹配（不打断）/ 没流程（澄清）
        """
        # 先问"点到的对象能不能补当前流程缺的槽",能就换成一个命令
        commands = self._resolve_object_commands(
            message=message,
            state=state,
            flows=self.task_handler.flows,
        )
        # 场景 A:对象正好补上流程缺的槽→带命令正常推进
        if commands:
            # 场景 A:对象能填当前槽 → 转成命令,推进流程
            return await self.task_handler.handle(commands=commands, state=state)

        # 命令是空的:分两种情形,取决于用户现在有没有在办业务
        # 没有匹配到 slot。如果用户正在一个流程中,不打断,让流程继续。
        if state.active_task is not None:
            # 场景 C:在办业务但对象无关→不打断,传空命令让流程自己续跑
            # 场景 C:在流程里但槽不匹配 → 不打断,空命令让流程继续
            return await self.task_handler.handle(commands=[], state=state)

        # 场景 B:压根没在办业务,只点对象没意图→追问用户想干嘛
        # 场景 B:没有流程 → 澄清
        return await self.clarify_responder.respond(
            state=state,
            reason=ClarifyReason.OBJECT_REQUIRES_INTENT,
        )

    # 小工具:点击对象存进 state.focused_object
    @staticmethod
    def _remember_focused_object(state: DialogueState, message: UserMessage) -> None:
        """
        把点击的对象记为聚焦对象。
        不管接下来怎么处理，"用户现在关注这个对象"这个事实先记下来。
        """
        # 消息里没带对象(理论上不会)就直接跳过
        if message.object is None:
            return
        # pydantic v2:model_dump 与 validate 往返即拷贝
        # pydantic v2 没有 from_dict/to_dict，用 model_validate + model_dump 拷一份
        state.set_focused_object(FocusedObject.model_validate(message.object.model_dump()))

    # 对象->命令转换器:查表找槽名,再看流程是不是正缺这个槽
    def _resolve_object_commands(
            self,
            message: UserMessage,
            state: DialogueState,
            flows: FlowsList,
    ) -> list[Command]:
        """
        对象转命令：当前点击的对象能不能填进当前流程正缺的槽位？
        能就生成一个 SetSlotsCommand，不能就返回空列表（交给调用方判断场景 B / C）。
        """
        # 取出对象引用,后面要判空、取 type/id
        message_object = message.object
        # 没带对象(防御),返回空列表
        if message_object is None:
            return []

        # 对象类型去掉首尾空白并转小写,防"Order"之类的大小写差异
        object_type = message_object.type.strip().lower()
        # 查表:order→order_number;查不到说明这不是可填槽的对象类型
        slot_name = OBJECT_TYPE_TO_SLOT.get(object_type)
        # 不认识的对象类型(比如点了文件),返回空
        if slot_name is None:
            return []

        # 关键判断:当前流程是不是正好缺这个槽?是才值得转命令
        if self._flow_has_unfilled_collect_slot(state, flows, slot_name):
            # 是→拼一条 set_slots 命令,把对象 id 填进缺的槽
            return [SetSlotsCommand(
                command="set_slots",
                slots={slot_name: message_object.id},
            )]
        # 否→返回空,交给调用方决定走场景 B 还是 C
        return []

    # 深查:当前活跃流程里,有没有"收集该槽"的步骤且槽还没填?
    @staticmethod
    def _flow_has_unfilled_collect_slot(
            state: DialogueState,
            flows: FlowsList,
            slot_name: str,
    ) -> bool:
        """检查当前流程是否定义了名为 slot_name 的收集槽且尚未填充。"""
        # 先拿当前活跃任务
        active_task = state.active_task
        if active_task is None:  # ① 没有活跃流程
            # 没在办业务→根本没有"待填的槽",返回 False
            return False
        # 按 flow_id 查流程定义,查不到说明流程清单没载入这份
        flow = flows.get_flow_by_id(active_task.flow_id)
        if flow is None:  # ② 流程 id 查不到(防御)
            # 防御性返回:流程定义不存在就当没这槽
            return False
        if active_task.slots.get(slot_name):  # ③ 这个槽已经填了
            # 槽已有值就不需要再收,返回 False
            return False
        for step in flow.steps:  # ④ 流程里有没有收集这个槽的步骤
            # 命中:是"收集槽位"步骤,且收的正是这个槽→说明需要用户提供
            if isinstance(step, CollectFlowStep) and step.slot_name == slot_name:
                # 结论:该槽待收集,点来的对象可以填进去
                return True
        # 遍历完都没有,说明当前流程不收集此槽
        return False
