# 文件导读：依赖装配工厂，把六大组件按顺序拼成一台可用的 DialogueEngine
# 所在层：engine 引擎装配层，是 main 启动时的唯一入口
# 被谁调用：main.py / API 层调用 build_dialogue_engine() 拿单例
# engine/builder.py

"""
组件装配工厂：把 FlowLoader / TurnPlanner / TurnPlanValidator / ClarifyResponder
/ TaskHandler / DialogueEngine 组装起来。
"""
from pathlib import Path

# Path 用于定位工程根目录下的 flow 配置文件
from clarify.responder import ClarifyResponder
from engine.dialogue_engine import DialogueEngine
from plan.turn_planner import TurnPlanner
from plan.turn_validator import TurnPlanValidator
from task.action.builder import build_action_runner
from task.command.processor import CommandProcessor
from task.flow.executor import FlowExecutor
from task.flow.loader import FlowLoader
from task.handler import TaskHandler
# day10 新增组件
from chitchat.handler import ChitChatHandler
from chitchat.responder import ChitChatResponder
from knowledge.handler import KnowledgeHandler
from knowledge.intents import KNOWLEDGE_INTENTS
from knowledge.providers import FAQProvider, OrderAPIProvider, ProductAPIProvider, RAGProvider
from knowledge.registry import KnowledgeProviderRegistry
from knowledge.responder import KnowledgeResponder

# 澄清话术器 / 对话引擎 / 计划器 / 校验器 / 命令执行器 / 流程加载器 / 任务处理器
# 进程内复用的引擎单例（引擎本身无状态，flow 定义只需加载一次）
_engine: DialogueEngine | None = None
# 模块级全局缓存：第一次 build 后就不再重建，各请求共享
# 因为引擎与 flow 定义都是只读的，所以单例是安全的


# 装配主入口:首次按依赖顺序构建全部组件,之后直接返回缓存单例
def build_dialogue_engine() -> DialogueEngine:
    """
    组装 DialogueEngine：
    1. 加载 user_flows.yml / system_flows.yml -> FlowsList
    2. 用 FlowsList 构造 TaskHandler
    3. 构造 TurnPlanner / TurnPlanValidator / ClarifyResponder
    4. 组装 DialogueEngine
    :return:
    """
    # 声明要改写模块级缓存变量,而非新建局部变量
    global _engine
    # 声明要改写模块级变量
    if _engine is None:
        # 懒加载：只有首次调用才真装配
        base_path = Path(__file__).resolve().parents[1]
        # 当前文件在 engine/ 下，parents[1] 上跳两级到工程根目录
        flows = FlowLoader().load_many([
            base_path / "flow_config" / "user_flows.yml",
            base_path / "flow_config" / "system_flows.yml",
        ])
        # 一次加载用户流程 + 系统过场流程，合并成完整 FlowsList

        turn_planner = TurnPlanner()
        # 负责把用户消息规划成 TurnPlan
        command_processor = CommandProcessor()
        # 命令执行器：无状态，task 阶段一专门改 DialogueState
        action_runner = build_action_runner()
        # 动作执行器：内置 + 自定义自动发现的全部 Action 都在这里
        flow_executor = FlowExecutor()
        # 流程执行器：task 阶段二负责按 YAML 推进流程、执行 action
        task_handler = TaskHandler(
            flows=flows,
            command_processor=command_processor,
            action_runner=action_runner,
            flow_executor=flow_executor,
        )
        # 任务处理器：持有流程表 + 命令执行器 + 动作执行器 + 流程执行器（两阶段全链路）
        turn_plan_validator = TurnPlanValidator()
        # 防幻觉校验器：拦下不可执行的计划
        clarify_responder = ClarifyResponder()
        # 澄清器：校验不过时的"救场话术"
        knowledge_handler = KnowledgeHandler(
            knowledge_intents=KNOWLEDGE_INTENTS,
            provider_registry=KnowledgeProviderRegistry(
                [
                    ProductAPIProvider(),
                    OrderAPIProvider(),
                    FAQProvider(),
                    RAGProvider(),
                ]
            ),
            knowledge_responder=KnowledgeResponder(),
        )
        # 知识轨道：按意图检索知识（API/FAQ/RAG）并作答
        chitchat_handler = ChitChatHandler(ChitChatResponder())
        # 闲聊轨道：把消息+历史交给 LLM 自然回一句
        _engine = DialogueEngine(
            turn_planner=turn_planner,
            task_handler=task_handler,
            knowledge_handler=knowledge_handler,
            chitchat_handler=chitchat_handler,
            clarify_responder=clarify_responder,
            turn_plan_validator=turn_plan_validator,
        )
        # 四大依赖注入 DialogueEngine，构成每轮对话的主管线
    return _engine
    # 首次之后直接返回已缓存实例，避免重复加载 YAML
