# 导读·职责：意图规划器——调 LLM 解析出 TurnPlan
# 导读·层位：plan 规划层,被 DialogueEngine 调用
# 导读·核心链：| 管道串联模板→LLM→解析器
# plan/turn_planner.py

# 序列化用:把 state 里的任务/对象转成 JSON 字符串喂给 LLM 看
import json
# 打"降级警告"日志用,方便排查 LLM 调用失败
import logging
# 类型注解:给"提示词输入字典"标类型,写起来更清晰
from typing import Any, Dict

# 输出解析器:把 LLM 返回文本剥成 dict
from langchain_core.output_parsers import JsonOutputParser
# LangChain 提示词模板:把 jinja2 文本包成可调用的模板对象
from langchain_core.prompts import PromptTemplate

# DialogueState:本轮上下文(当前任务、历史、聚焦对象)都从它身上取
from domain.state import DialogueState
# 全局唯一 llm 实例:统一走 conf/config 配置的模型/地址/密钥
from infrastructure.llm import llm
# TurnPlan:LLM 返回 dict 后要还原成的类型化数据模型
from plan.models import TurnPlan
# HistoryBuilder:渲染历史为 USER/BOT 文本
from prompts.history_builder import HistoryBuilder
# 按名字读 prompts/jinja2/*.jinja2 模板文件
from prompts.loader import load_prompt
# FlowsList:当前可用的全部流程清单,给 LLM 当"业务菜单"参考
from task.flow.flows import FlowsList

# 拿本模块的日志器:警告统一走它,能带出模块名方便定位
logger = logging.getLogger(__name__)


# TurnPlanner:用 LLM 分析意图,输出 TurnPlan
class TurnPlanner:
    """
    意图分析器
    作用：根据任务自然语言 调用LLM 分析轨道类型
    """

    # 对外唯一入口:两步——拼提示词入参,再走 LLM 链;引擎 await 调用
    async def predict(self, state: DialogueState, flows: FlowsList) -> TurnPlan:
        """
        :param state:
        :param flows:
        :return: 返回值是什么?(分析:定义数据模型)
        """

        # 第一步:把 state 里的上下文渲染成模板要的字段(纯本地拼装,不联网)
        # 1. 构建提示词
        inputs_prompt = self._build_prompt_inputs(state, flows)

        # 第二步:拿着拼好的入参真正调 LLM,await 等它出结果
        # 2. 调用LLM模型
        turn_plan = await self._predict_from_prompt_inputs(inputs_prompt)

        # 返回 TurnPlan;注意内部异常会被兜底成"空计划",不会抛给上层
        return turn_plan

    # 拼提示词入参:把各种 Python 对象"翻译"成 LLM 能读的字符串/字典
    def _build_prompt_inputs(self, state: DialogueState, flows_list: FlowsList) -> Dict[str, Any]:
        """
        构建提示词输入参数
        :param state:
        :param flows_list:
        :return:
        """
        # 用户最新一句话:从本轮刚开的 pending_turn 取(还没进历史)
        # 1. 用户消息
        user_msg = HistoryBuilder._render_user_message(state.pending_turn.user_message)

        # 历史取最近10轮:太多费 token,太久远还容易带偏 LLM(可调策略)
        # 2. 历史对话(当前session的turns:后10轮：最近的10轮) 。历史对话取多少 取哪些：动态策略
        current_conversation = HistoryBuilder.build(state.current_session().turns[-10:])

        # 正在办的任务序列化成 JSON,LLM 才知道该续办还是补槽
        # 3. 当前激活任务(业务任务)
        active_task_json = json.dumps(
            # mode=json:pydantic 序列化成可传的 dict
            state.active_task.model_dump(mode="json"), ensure_ascii=False
        # 没活跃任务就置 None,模板里原样显示 null
        ) if state.active_task is not None else None

        # 挂起的任务也全给:用户可能想"继续之前那个退款"
        # 4. 中断任务
        interrupted_tasks_json = json.dumps(
            # 列表推导:把每个暂停任务都序列化成 dict 再整体转 JSON
            [paused_task.model_dump(mode="json") for paused_task in state.paused_tasks],
            ensure_ascii=False
        )

        # 前端点过的卡片信息:聊订单/商品时这是关键上下文线索
        # 5. 页面点击卡片获取的信息
        focused_object_json = json.dumps(
            state.focused_object.model_dump(mode="json"), ensure_ascii=False
        # 用户没点过卡片就是 None
        ) if state.focused_object is not None else None

        # 流程清单=给 LLM 挑 flow id 的菜单,省 token
        # 6. 流程清单（LLM只需"业务说明书"，不需要流程内部步骤，省token又防干扰）
        # system_ 开头是引擎内部过场,绝不能暴露——LLM 选中了执行端会拒绝
        # 注意只给业务流程：system_* 是引擎内部过场，绝不能暴露给 LLM 选中（processor 会拒绝启动）
        business_flows = [flow for flow in flows_list.flows if not flow.id.startswith("system_")]
        # exclude steps:流程只发骨架,细节全剥掉
        available_flows_json = json.dumps(
            {"flows": [flow.model_dump(mode="json", exclude={"steps"}) for flow in business_flows]},
            ensure_ascii=False,
        )

        # 知识意图清单:后续章节接入 knowledge 轨道时再来填充
        # 7. 知识意图清单（后续章节接入知识轨道时填充）
        knowledge_intents_json = ""

        # 返回字段名与 jinja2 模板里的 {{ }} 变量一一对应,不能对不上
        return {
            "user_message": user_msg,
            "current_conversation": current_conversation,
            "active_task_json": active_task_json,
            "interrupted_tasks_json": interrupted_tasks_json,
            "focused_object_json": focused_object_json,
            "available_flows_json": available_flows_json,
            "knowledge_intents_json": knowledge_intents_json,
        }

    # 真正调 LLM:模板→链→ainvoke 一次跑完
    async def _predict_from_prompt_inputs(self, inputs_prompt: Dict[str, Any]) -> TurnPlan:
        """
        1. 加载提示词模板
        2. 格式化模版
        3. 调用模型
        :param inputs_prompt:
        :return:
        """

        # 读 jinja2/turn_plan.jinja2 模板原文
        prompt_template_text = load_prompt("turn_plan")

        # 包成 PromptTemplate,按 jinja2 渲染 {{ }}
        prompt_template = PromptTemplate.from_template(template=prompt_template_text, template_format="jinja2")

        # 管道:模板输出→LLM→JsonOutputParser 剥成 dict
        # prompt | llm 会自动把前者的输出当后者的输入,不用手写胶水代码
        # JsonOutputParser:LLM 答非 JSON 就抛异常
        chain = prompt_template | llm | JsonOutputParser()

        # 不 try 的话,LLM 一抽风整个请求就 500,所以异常统一降级
        # 兜底：网络异常 / LLM 输出非法 JSON 都算"没听懂"，
        # 降级为空计划(三轨道全 None)，由引擎的防幻觉校验转 MISSING_TRACK 澄清，避免直接 500。
        try:
            # ainvoke 异步跑完整条链;返回的已是解析好的 dict
            llm_response_dict: Dict[str, Any] = await chain.ainvoke(inputs_prompt)
            # dict 按三轨道结构还原成 TurnPlan
            return TurnPlan.from_dict(llm_response_dict)
        # 捕获一切异常:网络超时/JSON 解析失败/字段缺失都算"这次没听懂"
        except Exception as exc:  # noqa: BLE001
            # 记警告日志:谁挂了、原因是什么,方便排障
            logger.warning("TurnPlanner 调用失败，降级为空计划: %s", exc)
            # 空计划=三轨道全 None,引擎校验后自然转成 MISSING_TRACK 澄清
            return TurnPlan()
