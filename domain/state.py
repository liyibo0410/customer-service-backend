# 【导读】domain/state.py —— 领域层：对话状态的“聚合根”容器
# 职责：管理单个用户的任务生命周期/会话/回合；DialogueState 是状态机核心
# 被上层 StateStore 持久化存取，被 turn_planner 等编排逻辑调用以推进对话
# itwwy/domain/state.py

# time：取当前时间戳，给会话打开始/活动/关闭标记
import time
# uuid：生成全局唯一的会话ID与轮次ID
import uuid
# 类型标注：Dict=字典类型；Any=槽位值可以是任意类型
from typing import Dict, Any

# pydantic 模型基类：状态对象可整体校验、序列化后落库
from pydantic import BaseModel

# 引入任务/系统上下文模型：本文件负责调度这些状态对象
from domain.contexts import SystemContext, SystemContextUnion, TaskContext
# 引入消息模型：Turn 里要装用户消息与机器人回复
from domain.messages import FocusedObject, UserMessage, BotMessage

# Turn：一“轮”对话的最小记录 = 用户1句 + 机器人若干回复
class Turn(BaseModel):
    """
    本轮对话的对象
    """
    # 轮次ID：全局唯一，便于定位与追溯单轮对话
    turn_id: str                                         # 轮次唯一标识，使用 UUID
    # 该轮用户的输入（先暂存，待回复凑齐后一起归档）
    user_message: UserMessage                            # 这一轮用户说的那一句话
    # 机器人回复列表：一轮可回多条
    bot_messages: list[BotMessage]                       # 这一轮系统给出的所有回复

# Session：一次“会话”的容器，按时间顺序装多轮 Turn
class Session(BaseModel):
    """
    会话信息
    """
    # 会话唯一标识
    session_id: str                                      # 会话唯一标识，使用 UUID
    # 会话创建时刻（Unix 时间戳）
    started_at: float                                    # 会话开始的时间戳
    # 最近一次活动时刻：判断会话超时就看它与当前时间差
    last_activity_at: float                              # 最后一次活动的时间戳，用来判断超时
    # 会话关闭时刻；None=会话仍在进行中
    closed_at: float | None = None                       # 会话关闭时间，未关闭时为 `None`
    # 已提交轮次列表，元素顺序即对话先后
    turns: list[Turn] = []                               # 这个会话里的所有轮次

# DialogueState：聚合根——把某个用户的全部对话状态收在一棵对象树里
class DialogueState(BaseModel):
    # 归属用户：按 sender_id 找到属于“这个人”的状态副本
    sender_id: str                                       # 用户id
    # 正在执行的业务任务（同一时刻至多一个）
    active_task: TaskContext | None = None               # 当前执行的业务任务
    # ★挂起任务栈：被打断的任务压栈保存现场，可后续恢复
    paused_tasks: list[TaskContext] = []                 # 当期暂停的业务任务（多个）
    # 正在插播的“系统过场”上下文（判别器联合类型，见 contexts.py）
    active_system_task: SystemContextUnion | None = None      # 当前执行的系统流程（带判别器：持久化往返不丢子类字段）
    # 当前聚焦对象：用户最近点选的那张业务卡片
    focused_object: FocusedObject | None = None
    # 全部历史会话都留存（换新会话只关当前，不删历史）
    sessions: list[Session] = []                         # 当前用户的所有都存储起来
    # 指针：指向 sessions 中“正在对话”的那个；None=当前无会话
    current_session_id: str | None = None                # 当前用户的session的sessionID
    # ★回合暂存区：消息先落在内存里，commit 时才真正写进会话
    pending_turn: Turn | None = None                     # turn会话的暂存区（变量：内存中缓冲区）

    # --------------任务相关--------------------------
    # 【开始业务任务】让新任务上位；调用前旧任务应已结束或中断
    def start_active_task(self, active_task: TaskContext):
        """
        把传进来的 TaskContext 设为活跃任务。
        调用时机：当 TurnPlanner 判断用户发起了一个新业务任务时。
        :param active_task:
        :return:
        """
        # 直接替换“活跃任务”引用
        self.active_task = active_task

    # 【结束任务】流程自然跑到 end 步骤时调用
    def end_active_task(self):
        """
        结束业务任务
        调用时机：当业务任务流程跑到 end 步骤时。
        :return:
        """
        # 置空即可，不影响挂起列表与历史会话
        self.active_task = None

    # 【取消任务】用户明确放弃（如“算了不退了”）→ 作废不再恢复
    def cancel_active_task(self):
        """
        取消业务任务
        把活跃任务和当前系统过场都清空
        调用时机：用户主动说"算了不退了"这类取消意图时。
        :return:
        """
        # 清空业务任务
        self.active_task = None
        # 同时清掉系统过场，避免残留的引导话术继续生效
        self.active_system_task = None

    # 【中断任务】用户中途切到别处 → 旧任务挂起（与“取消”本质不同）
    def interrupted_active_task(self):
        """
        中断活跃任务
        把当前活跃任务 移到挂起列表，再清空活跃任务。
        调用时机：用户在任务 A 中途切到任务 B 时。
        :return:
        """
        # 压栈保存现场；step_id/slots 都在任务对象里，无需额外拷贝
        self.paused_tasks.append(self.active_task)
        # 清空活跃位，给新任务腾位置
        self.active_task = None


    # 【恢复任务】从挂起栈取回任务；flow_id=None 恢复最近挂起的，否则按ID找
    def resumed_active_task(self, flow_id: str | None = None) -> bool:
        """
        恢复业务任务:流程ID

        如果用户没有明确指定需要恢复的具体任务，那么 flow_id = None，恢复最近的任务
        如果用户明确指定需要恢复的具体任务：
          则按 flow_id 在挂起列表里找到这个任务，恢复为活跃任务，并从挂起列表里移除。

        调用时机：用户说"继续刚才的退款"这类意图时。

        注意：任务被恢复时，step_id 和 slots 都还在，所以可以从挂起前的位置接着跑，不用从头来。

        :return: 恢复成功或失败
        """

        # 1. 判断栈中是否存在中断的业务任务
        if not self.paused_tasks:
            return False

        # 2. 如果业务流程ID不存在
        if flow_id is None:
            # pop() 弹栈：后挂起的先恢复（LIFO），符合“最近中断最先想起”
            self.active_task = self.paused_tasks.pop()
            return True

        # 2. 如果业务流程ID存在
        for i, paused_task in enumerate(self.paused_tasks):
            if paused_task.flow_id == flow_id:
                # 激活
                self.active_task = paused_task
                # 删除
                del self.paused_tasks[i]
                return True

        # 栈里没有匹配该 flow_id 的任务 → 恢复失败
        return False

    # 【开系统过场】要插播一句话/一段流程时先设一个系统上下文
    def start_active_system_task(self, active_system_task: SystemContext):
        """
        开启系统流程
        调用时机：每当系统要插播过场白（任务开始、打断、取消、恢复、收集槽位）时。
        :param active_system_task:
        :return:
        """
        # 直接覆盖引用：同一时刻只跑一个系统过场
        self.active_system_task = active_system_task

    # 【结束系统过场】过场话说完就清空，把话语权还给业务任务
    def end_active_system_task(self):
        """
        结束系统流程
        :return:
        """
        # 置空即可
        self.active_system_task = None

    # 【取本轮主角】上层流程根据它决定“这轮让谁响应”
    def current_active_task(self):
        """
        返回当前正在执行的任务（系统流程、业务任务）
        先获取系统流程 如果获取不到 获取业务任务
        - 如果有系统流程，先返回系统流程
        - 否则返回业务任务

        为什么系统流程优先？
        因为系统流程往往是要插播一句过场白，必须先说完，然后才能让位给业务任务继续。
        :return:
        """
        # 系统过场优先：话没插播完，业务任务不能抢答
        return self.active_system_task or self.active_task

    # --------------槽位相关--------------------------
    # 【写槽位】把新收集到的信息合并进当前任务的槽位表
    def set_slots(self, slots: Dict[str, Any]):
        """
        设置槽位
        :param slots:
        :return:
        """
        # update 增量覆盖：只动传入的键，旧槽位原样保留
        self.active_task.slots.update(slots)

    # 【删槽位】用户改口/反悔时移除某项已收集信息
    def remove_slot(self, slot_name: str):
        """
        移除槽位
        :param slot_name: 移除的槽位名
        :return:
        """
        # pop 直接删除；槽位不存在会抛 KeyError，调用方需保证存在
        self.active_task.slots.pop(slot_name)

    # -------------- session相关 --------------------------
    # 【取当前会话】按 current_session_id 反查出 Session 对象
    def current_session(self) -> Session | None:
        """
        获取当前会话对象
        根据 current_session_id 在 sessions 里找出当前会话。
        :return:
        """
        # 线性扫描历史会话；会话量小所以够用，量大可改索引
        for session in self.sessions:
            if session.session_id == self.current_session_id:
                return session

        return None

    # 【开新会话】生成新 Session 并设为当前（只在无当前会话时）
    def start_session(self):
        """
        开启新会话
        创建一个新的 Session，加进 sessions 列表，并把它设为当前会话。
        :return:
        """
        # 幂等保护：已有当前会话就不重复创建
        if self.current_session() is None:
            # 只取一次“现在”，让开始时间与活动时间保持一致
            now = time.time()
            session_id = str(uuid.uuid4())
            # 构造 Session；turns 用默认空列表，轮次稍后逐个追加
            session = Session(
                session_id=session_id,
                started_at=now,
                last_activity_at=now
            )
            # 挂进历史会话列表，之后可按序回溯
            self.sessions.append(session)
            # 把新会话设为当前，后续轮次都写进它
            self.current_session_id = session_id

    # 【关会话】打上关闭时间戳并断开当前会话指针
    def close_current_session(self):
        """
        关闭当前会话
        给当前会话打上关闭时间戳，再把 current_session_id 置空。
        :return:
        """
        # 确实有当前会话才执行关闭，避免误操作
        if self.current_session() is not None:
            # 1. 修改session的时间closed_at
            self.current_session().closed_at = time.time()
            # 2. 清空当前的session_id
            self.current_session_id = None

    # 【开新会话前的清场】只清“运行时字段”，历史 sessions 必须保留
    def reset_runtime_state_for_new_session(self):
        """
        重置会话状态
        session会话超时新会话开始前的"清理工作"。
        注意：
        - 它只清运行时字段：当前任务、挂起任务、系统过场、聚焦对象
        - 它不清 sessions：历史会话需要保留
        :return:
        """
        # 下面6行依次复位：活跃任务、系统过场、挂起栈、聚焦对象、暂存区、当前会话指针
        self.active_task = None
        self.active_system_task = None
        self.paused_tasks = []
        self.focused_object = None
        self.pending_turn = None
        self.current_session_id = None

    # --------------turn相关--------------------------
    # 【开始一轮】把收到的用户消息包装成 Turn，先放入暂存区
    def begin_turn(self, message: UserMessage):
        """
        开始一个turn
        收到用户消息后，把它装进一个新的 turn 对象
        先放到 pending_turn，而不是直接进 session。
        :param message:
        :return:
        """
        # 只在有当前会话时才暂存，避免产生游离脏数据
        if self.current_session():
            # Turn 先在 pending_turn 里“发育”，机器人回复稍后补进 bot_messages
            self.pending_turn = Turn(
                turn_id=str(uuid.uuid4()),
                user_message=message,
                bot_messages=[]
            )

    # 【提交本轮】整轮处理完（回复就绪）才把暂存内容落库
    def commit_turn(self):
        """
        提交一个turn
        本轮处理完成（机器人回复也填好了）后
        把 pending_turn 追加到当前会话的 turns 里，再把 pending_turn 清空。
        :return:
        """
        # 与 begin_turn 的守卫保持一致，成对出现
        if self.current_session():
            # 从暂存区正式写入会话 turns，顺序即对话顺序
            self.current_session().turns.append(self.pending_turn)
            # 清空暂存区，为下一轮腾位子
            self.pending_turn = None

    # --------------FocusedObject相关--------------------------
    # 【设置聚焦对象】用户点的是对象卡片（而非文本）时调用
    def set_focused_object(self, focused_object: FocusedObject):
        """
        设置聚焦对象
        调用时机：
        用户发的不是文本而是一条对象消息时,例如前端点了订单卡片
        需要把这个对象设为当前关注的对象。
        :param focused_object:
        """
        # 直接覆盖引用：最新点的卡片成为当前聚焦对象
        self.focused_object = focused_object