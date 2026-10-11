# task/handler.py

"""
TaskHandler：task 轨道的两阶段协调者。
阶段1 CommandProcessor：把命令应用到 state（建任务/填槽/取消/恢复/挂起）
阶段2 FlowExecutor：读改好的 state，按 YAML 推进流程、执行 action、生成回复
"""

from domain.messages import BotMessage
from domain.state import DialogueState
from task.action.runner import ActionRunner
from task.command.models import Command
from task.command.processor import CommandProcessor
from task.flow.executor import FlowExecutor
from task.flow.flows import FlowsList


# TaskHandler:task 轨道协调者,串联"命令应用+流程推进"两阶段
class TaskHandler:

    # 构造注入四依赖:流程表/命令处理器/动作执行器/流程执行器
    def __init__(
            self,
            flows: FlowsList,
            command_processor: CommandProcessor,
            action_runner: ActionRunner,
            flow_executor: FlowExecutor
    ):
        # 保存流程清单:查流程/步骤定义靠它
        self.flows = flows
        # 保存命令处理器:阶段1把命令应用到状态
        self.command_processor = command_processor
        # 保存动作执行器:阶段2执行具体动作靠它
        self.action_runner = action_runner
        # 保存流程执行器:阶段2推进流程的核心
        self.flow_executor = flow_executor

    # 两阶段总入口:先命令改状态,再推流程产回复
    async def handle(self, commands: list[Command], state: DialogueState) -> list[BotMessage]:
        # 阶段1：把命令应用到 state
        self.command_processor.run(commands, state, self.flows)

        # 阶段2：推进流程，执行 action，生成回复
        messages: list[BotMessage] = await self.flow_executor.run_task(state, self.flows, self.action_runner)

        # 返回阶段2生成的回复,供引擎回填本轮 turn
        return messages
