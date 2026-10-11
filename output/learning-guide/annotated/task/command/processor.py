# 文件导读：命令处理器——把 start/set/cancel/resume 四种命令写到对话状态
# 所在层：task 命令层，被 TaskHandler 阶段1调用（纯同步、不碰 LLM）
# 被谁调用：TaskHandler.handle → run()；turn_validator 也引用命令类型
# itwwy/task/command/processor.py
from domain.contexts import (
    CanceledSystemContext,
    InterruptedSystemContext,
    ResumedSystemContext,
    StartedSystemContext,
    TaskContext,
)
from domain.state import DialogueState
from task.command.models import Command, StartFlowCommand, SetSlotsCommand, CancelFlowCommand, ResumeFlowCommand
from task.flow.flows import FlowsList


# 命令执行器无内部状态，可全局共享一个实例
class CommandProcessor:

    # 公共入口：把一队命令按顺序应用到 state
    def run(
            self,
            commands: list[Command],
            state: DialogueState,
            flows: FlowsList,
    ) -> None:
        """
        把命令应用到 state
        :param commands:
        :param state:
        :param flows:
        :return:
        """
        # 命令有先后顺序，逐个应用不跳步
        for command in commands:
            # 转交单条命令处理函数
            self._apply(command, state, flows)


    # _apply 用 isinstance 认出命令子类型再分流
    def _apply(
            self,
            command: Command,
            state: DialogueState,
            flows: FlowsList,
    ) -> None:
        """
        处理命令
        :param command:
        :param state:
        :param flows:
        :return:
        """
        # start_flow：开新流程
        if isinstance(command, StartFlowCommand):
            self._handle_start_flow(command, state, flows)
        # set_slots：往活跃任务塞槽位
        elif isinstance(command, SetSlotsCommand):
            self._handle_set_slots(command, state)
        # cancel_flow：取消当前业务任务
        elif isinstance(command, CancelFlowCommand):
            self._handle_cancel_flow(state, flows)
        # resume_flow：恢复挂起的任务
        elif isinstance(command, ResumeFlowCommand):
            self._handle_resume_flow(command, state, flows)

    # start_flow 处理器：改任务位并挂系统过场
    def _handle_start_flow(self, command: StartFlowCommand, state: DialogueState, flows: FlowsList) -> None:
        """
        开启业务任务
        :param command:
        :param state:
        :param flows:
        :return:
        """

        # 清除当前系统流程
        # 先清掉残留系统过场，避免上一句白抢戏
        state.end_active_system_task()

        # 防御:不允许直接启动 system_ 开头的内部流程
        # 内部过场只许代码激活，LLM 越权直接抛错
        if command.flow.startswith("system_"):
            # 错误信息带上流程名，方便排查
            raise ValueError(f"不能直接启动系统流程：'{command.flow}'")

        # 校验:流程必须存在
        # 查真实流程定义，双保险防幻觉
        target_flow = flows.get_flow_by_id(command.flow)
        # 查不到=流程不存在，直接抛错
        if target_flow is None:
            # 抛“未知流程”异常
            raise ValueError(f"未知流程：'{command.flow}'.")

        # 校验:流程必须有起点
        # 取流程起点步
        start_step = target_flow.start_step()
        # 没有起点步说明流程配置坏了
        if start_step is None:
            # 抛错暴露坏流程
            raise ValueError(f"流程 '{command.flow}' 没有开始步骤")

        # 看手头有没有活跃任务，决定走哪个分支
        active_task = state.active_task

        # ===== 情况一:当前有活跃任务 =====
        # 情况一：正办着业务又要求开新流程
        if active_task is not None:

            # 同一个流程：不重复启动
            # 要开的就是当前流程 → 幂等
            if active_task.flow_id == command.flow:
                # 不重复启动，静默退出
                return

            # 不是同一个流程：把当前任务放进暂停栈
            # 记下被切换走流程的 id
            interrupted_flow_id = active_task.flow_id
            # id 转中文名，过场台词要用
            interrupted_flow_name = self._readable_flow_name(active_task.flow_id, flows)
            # 旧任务压入暂停栈、清空活跃位
            state.interrupted_active_task()

            # 试着从暂停栈恢复要开的流程
            # 试着把目标流程从暂停栈捞回来（返回布尔）
            resumed = state.resumed_active_task(command.flow)
            # 捞不到 → 目标从没做过，走新建
            if not resumed:
                # 要开的流程不在暂停栈 → 新建
                # 新建活跃任务并从起点步起跑
                state.start_active_task(TaskContext(flow_id=command.flow, step_id=start_step.id))
                # 记新流程 id 给过场用
                started_flow_id = command.flow
                # 记新流程中文名给过场用
                started_flow_name = self._readable_flow_name(command.flow, flows)
            # 捞到了 → resumed_active_task 已把它激活
            else:
                # 要开的流程在暂停栈 → 已被 resumed_active_task 恢复
                # 已恢复则 id 就是目标流程
                started_flow_id = command.flow
                # 名称同理再取一遍
                started_flow_name = self._readable_flow_name(command.flow, flows)

            # 激活"打断"过场
            # 无论新建还是恢复，都挂“任务被打断”过场
            self._activate_interrupted_system_flow(
                state, flows, interrupted_flow_id, interrupted_flow_name,
                started_flow_id, started_flow_name)

            # 情况一处理完返回
            return

        # ===== 情况二:当前没有活跃任务 =====
        # 试着恢复同名任务
        # 情况二：手头空闲，先试恢复暂停栈里的
        resumed = state.resumed_active_task(command.flow)
        # 恢复成功 → 目标从暂停栈回来了
        if resumed:
            # 要开的流程在暂停栈 → 恢复
            # 挂“任务恢复”过场并返回
            self._activate_resumed_system_flow(state, flows, command.flow,
                                               self._readable_flow_name(command.flow, flows))
            # 恢复成功就结束
            return

        # 要开的流程从没做过 → 新建
        # 栈里也没有 → 才真正从零新建
        state.start_active_task(TaskContext(flow_id=command.flow, step_id=start_step.id))
        # 挂“新任务开始”过场
        self._activate_started_system_flow(
            state, flows, command.flow, self._readable_flow_name(command.flow, flows),
        )

    @staticmethod
    # 内部 id 转成给用户看的中文名
    def _readable_flow_name(flow_id: str, flows: FlowsList) -> str:
        # 查流程定义
        flow = flows.get_flow_by_id(flow_id)
        # 有 name 用 name，查不到用 id 兜底
        return flow.name if flow else flow_id

    @staticmethod
    # 过场A：对应 system_task_started（告知开始办理）
    def _activate_started_system_flow(
            state: DialogueState, flows: FlowsList, started_flow_id: str, started_flow_name: str):

        # 取过场流程本体（YAML 里配置的步骤）
        flow = flows.get_flow_by_id("system_task_started")
        # 用 StartedSystemContext 挂上系统过场
        state.start_active_system_task(StartedSystemContext(
            flow_id="system_task_started",
            step_id=flow.start_step().id,
            started_flow_id=started_flow_id,
            started_flow_name=started_flow_name,
        ))

    @staticmethod
    # 过场B：对应 system_task_interrupted（告知被打断）
    def _activate_interrupted_system_flow(
            state: DialogueState, flows: FlowsList, interrupted_flow_id: str, interrupted_flow_name: str,
            started_flow_id: str, started_flow_name: str):

        # 取打断过场流程
        flow = flows.get_flow_by_id("system_task_interrupted")
        # 打断上下文同时带新旧两个流程信息
        state.start_active_system_task(InterruptedSystemContext(
            flow_id=flow.id,
            step_id=flow.start_step().id,
            interrupted_flow_id=interrupted_flow_id,
            interrupted_flow_name=interrupted_flow_name,
            started_flow_id=started_flow_id,
            started_flow_name=started_flow_name
        ))

    @staticmethod
    # 过场C：对应 system_task_resumed（告知已继续）
    def _activate_resumed_system_flow(
            state: DialogueState, flows: FlowsList,
            resumed_flow_id: str, resumed_flow_name: str):

        # 取恢复过场流程
        flow = flows.get_flow_by_id("system_task_resumed")
        # 恢复上下文只需目标流程信息
        state.start_active_system_task(ResumedSystemContext(
            flow_id=flow.id,
            step_id=flow.start_step().id,
            resumed_flow_id=resumed_flow_id,
            resumed_flow_name=resumed_flow_name
        ))

    # set_slots：给当前任务补槽位
    def _handle_set_slots(self, command: SetSlotsCommand, state: DialogueState):
        # 没有活跃任务则忽略，槽位无处安放
        if state.active_task:
            # 有任务才合并写入槽位
            state.set_slots(command.slots)

    # cancel_flow：取消当前业务任务
    def _handle_cancel_flow(self, state: DialogueState, flows: FlowsList):
        # 获取当前正在执行的 flow
        # 拿当前活跃任务
        active_task = state.active_task
        # 没任务可取消（可能 LLM 误判）
        if active_task is None:
            # 没有正在办的任务，取消无从谈起（LLM 可能误判出取消意图）
            return
        # 先取定义，取消台词要报流程名
        target_flow = flows.get_flow_by_id(active_task.flow_id)
        # 取消当前 task
        # 清掉活跃任务和残留系统过场
        state.cancel_active_task()
        # 启动 system_task_canceled 过场
        # 挂“任务已取消”过场（system_task_canceled）
        state.start_active_system_task(
            CanceledSystemContext(
                flow_id="system_task_canceled",
                step_id=flows.get_flow_by_id("system_task_canceled").start_step().id,
                canceled_flow_id=target_flow.id,
                canceled_flow_name=target_flow.name,
            )
        )

    # resume_flow：恢复暂停栈里的任务
    def _handle_resume_flow(self, command: ResumeFlowCommand, state: DialogueState, flows: FlowsList):
        # ===== 第一步:确定要恢复哪个流程 =====
        # 指名恢复：用户点明要续哪个流程
        if command.flow is not None:
            # 指名恢复:用户明确说了恢复哪个
            # 指名就再验一遍流程真实性
            target_flow = flows.get_flow_by_id(command.flow)
            # 查无此流程直接抛错
            if target_flow is None:
                # 抛“未知流程”异常
                raise ValueError(f"未知流程 '{command.flow}'.")
            # 锁定目标 id
            target_flow_id = target_flow.id
            # 锁定目标名称
            target_flow_name = target_flow.name
        # 不指名恢复：只剩“继续刚才的”
        else:
            # 不指名恢复:用户只说"继续刚才的" → 取暂停栈栈顶(最近挂起的)
            # 暂停栈空则无任务可续，直接忽略
            if not state.paused_tasks:
                return
            # 栈尾=最近挂起的任务
            top_paused = state.paused_tasks[-1]
            # 取栈顶任务 id
            target_flow_id = top_paused.flow_id
            # 名称转可读
            target_flow_name = self._readable_flow_name(target_flow_id, flows)

        # ===== 第二步:按"当前有没有活跃任务"恢复 =====
        # 第二步：看当前活跃状态
        active_task = state.active_task
        # 当前有任务 → 恢复要走“打断”逻辑
        if active_task is not None:
            # 目标就是当前任务 → 重复，忽略
            if active_task.flow_id == target_flow_id:
                return  # 已经在办它,不重复
            # 记将被打断任务的 id
            interrupted_flow_id = active_task.flow_id
            # 名称转可读
            interrupted_flow_name = self._readable_flow_name(active_task.flow_id, flows)
            # 当前任务先挂起腾位
            state.interrupted_active_task()
            # 目标不在栈里=恢复失败
            if not state.resumed_active_task(target_flow_id):
                # 失败回退：无参调用恢复栈顶＝把刚挂起的捞回
                state.resumed_active_task()  # 恢复失败,回退
                # 回滚后放弃本条命令
                return
            # 挂“打断当前+恢复目标”组合过场
            self._activate_interrupted_system_flow(  # ③打断当前+恢复目标
                state, flows, interrupted_flow_id, interrupted_flow_name,
                target_flow_id, target_flow_name)
        else:
            # command.flow 为 None 时 resumed_active_task 恢复栈顶，正好对应"继续刚才的"
            # 没活跃任务：直接恢复（None 时正好取栈顶）
            if not state.resumed_active_task(command.flow):  # ④没任务,直接恢复
                # 恢复失败(空栈/找不到)就静默退出
                return
            # 恢复成功则取出活跃任务
            resumed = state.active_task
            # 挂“任务恢复”过场并带上名字
            self._activate_resumed_system_flow(
                state, flows, resumed.flow_id, self._readable_flow_name(resumed.flow_id, flows))
