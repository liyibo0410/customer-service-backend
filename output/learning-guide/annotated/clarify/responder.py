# 文件导读：澄清回复器——把校验原因码变成一句自然的追问话术
# 所在层：clarify 澄清层，接在 turn_validator 拒绝结果之后
# 被谁调用：DialogueEngine 校验失败时调 respond()，产出 BotMessage
# clarify/responder.py
"""
澄清回复器：把一个冷冰冰的原因码，变成一句自然的用户追问。

两段式设计：
  ① 基础话术：按 reason 用 if-else 写死一句兜底话术，保证永远有一句能用的话
  ② LLM 润色：把基础话术 + 上下文喂给 LLM，改写得更自然
"""
# 把聚焦对象 JSON 化后喂给 LLM 润色
import json

# 输出解析器：把 LLM 返回物剥成字符串
from langchain_core.output_parsers import StrOutputParser
# 提示词模板：用 jinja2 渲染模板文件
from langchain_core.prompts import PromptTemplate

# 机器人消息：最终以 BotMessage 列表返回
from domain.messages import BotMessage
# 状态：提供历史/聚焦对象/当前用户句
from domain.state import DialogueState
# 基础设施里共享的 LLM 实例
from infrastructure.llm import llm
# 原因码枚举：基础话术按它分支
from plan.models import ClarifyReason
# 历史与当前用户句的渲染器
from prompts.history_builder import HistoryBuilder
# 按名字读取 prompts/jinja2 下的模板
from prompts.loader import load_prompt


# 澄清话术器：reason + state → 一句追问
class ClarifyResponder:

    # 对外入口：返回润色后的一句话
    async def respond(
            self,
            state: DialogueState,
            reason: ClarifyReason,
    ) -> list[BotMessage]:
        # ① 基础话术
        # ① 先拿规则写死的兜底话术
        clarify_message = self.build_clarify_message(reason=reason, state=state)

        # ② 润色需要的上下文
        # pending_turn 可能为空（本轮还没开启，或已提交），做防御
        # ② 备润色上下文：先取本轮暂存区
        pending_turn = state.pending_turn
        # 防御性取值：没有本轮则给空串
        user_message = (
            HistoryBuilder._render_user_message(pending_turn.user_message)
            if pending_turn is not None else ""
        )
        # 取当前会话（可能还没有）
        session = state.current_session()
        # 只喂最近 10 轮历史，避免稀释重点
        history = HistoryBuilder.build(session.turns[-10:]) if session is not None else ""
        # pydantic v2 没有 to_dict()，用 model_dump；无聚焦对象时传空串让模板跳过
        # 聚焦对象 JSON 化，无对象给空串让模板跳过
        focused_object = (
            json.dumps(state.focused_object.model_dump(mode="json"), ensure_ascii=False)
            if state.focused_object is not None else ""
        )

        # 加载提示词
        # 加载澄清模板文本
        prompt_text = load_prompt("clarify_respond")
        # 声明用 jinja2 语法渲染
        prompt = PromptTemplate.from_template(prompt_text, template_format="jinja2")
        # LCEL 管道：模板 → LLM → 剥字符串
        chain = prompt | llm | StrOutputParser()
        # 异步调用并把五类变量注入模板
        rewritten = await chain.ainvoke(
            {
                "reason": reason.value,
                "clarify_message": clarify_message,
                "focused_object": focused_object,
                "history": history,
                "user_message": user_message,
            }
        )
        # 去首尾空白后包成 BotMessage 返回
        return [BotMessage(text=str(rewritten).strip())]

    # 规则话术器：按原因码给兜底句
    def build_clarify_message(
            self,
            reason: ClarifyReason,
            state: DialogueState,
    ) -> str:
        # 多轨歧义：请用户先选方向
        if reason is ClarifyReason.MULTIPLE_TRACKS:
            return "你这次同时提到了多个方向。我们先处理一个，你想先办业务还是先咨询信息呢？"

        # 缺聚焦对象：先发对象再服务
        if reason is ClarifyReason.MISSING_FOCUSED_OBJECT:
            return "请先发送你想咨询的对象，我再继续帮你看。"

        # 咨询意图缺失：列出可问类别
        if reason is ClarifyReason.MISSING_KNOWLEDGE_INTENT:
            return "你是想了解商品信息、订单信息，还是售后配送规则呢？"

        # 整轮无方向：业务/咨询二选一
        if reason is ClarifyReason.MISSING_TRACK:
            return "你是想先处理业务问题，还是先咨询信息呢？"

        # 任务轨空转：举业务例子引导
        if reason is ClarifyReason.MISSING_TASK_COMMANDS:
            return "你这次是想办理什么业务呢？比如查订单、查物流，或者申请退款。"

        # 有对象缺意图：按对象类型追问
        if reason is ClarifyReason.OBJECT_REQUIRES_INTENT:
            # 读当前聚焦对象来定话术
            focused_object = state.focused_object
            # 订单语境下给订单选项
            if focused_object is not None and focused_object.type == "order":
                return "我已经收到这个订单了。你想查订单状态、查物流，还是申请退款呢？"
            # 商品语境下给商品选项
            if focused_object is not None and focused_object.type == "product":
                return "我已经收到这个商品了。你想了解它的商品信息、发货情况，还是售后相关问题呢？"

        # 兜底：其余原因码统一含糊重问
        return "我还需要再确认一下你的意思，你可以换个更具体的说法告诉我。"


# 手动自测：只跑规则话术，不碰 LLM
if __name__ == '__main__':
    from domain.messages import FocusedObject
    import asyncio

    # 无状态实例
    responder = ClarifyResponder()

    # 状态1：空状态（无聚焦对象）
    # 空状态：无聚焦对象
    state = DialogueState(sender_id="user_001")
    # 状态2：已聚焦订单对象
    # 聚焦订单对象的状态
    state_with_order = DialogueState(
        sender_id="user_001",
        focused_object=FocusedObject(id="ORDER_10001", type="order", title="订单10001"),
    )
    # 状态3：已聚焦商品对象
    # 聚焦商品对象的状态
    state_with_product = DialogueState(
        sender_id="user_001",
        focused_object=FocusedObject(id="SKU_20001", type="product", title="纯棉T恤"),
    )

    # 测试器：直接调用规则话术分支
    def run_case(name: str, reason: ClarifyReason, st: DialogueState = state):
        # 离线可用，不经过 LLM
        msg = responder.build_clarify_message(reason, st)
        # 打印话术对照预期
        print(f"[{name}] {msg}")

    # 1. 多轨道 → 让用户选办业务还是咨询
    run_case(" 1.多轨道        ", ClarifyReason.MULTIPLE_TRACKS)
    # 2. 缺聚焦对象 → 让用户先发对象
    run_case(" 2.缺聚焦对象     ", ClarifyReason.MISSING_FOCUSED_OBJECT)
    # 3. 知识轨道缺意图 → 问咨询哪类信息
    run_case(" 3.缺知识意图     ", ClarifyReason.MISSING_KNOWLEDGE_INTENT)
    # 4. 缺轨道 → 问办业务还是咨询
    run_case(" 4.缺轨道        ", ClarifyReason.MISSING_TRACK)
    # 5. task 轨道缺 commands → 问办什么业务
    run_case(" 5.缺任务指令     ", ClarifyReason.MISSING_TASK_COMMANDS)
    # 6. 有订单对象缺意图 → 订单话术
    run_case(" 6.订单缺意图     ", ClarifyReason.OBJECT_REQUIRES_INTENT, st=state_with_order)
    # 7. 有商品对象缺意图 → 商品话术
    run_case(" 7.商品缺意图     ", ClarifyReason.OBJECT_REQUIRES_INTENT, st=state_with_product)
    # 8. 对象缺意图但没有聚焦对象 → 兜底话术
    run_case(" 8.无对象兜底     ", ClarifyReason.OBJECT_REQUIRES_INTENT)
    # 9. 未单独处理的 reason（如流程不存在）→ 兜底话术
    run_case(" 9.未知流程兜底   ", ClarifyReason.UNKNOWN_TASK_FLOW)

    # 10.（可选）端到端验证 respond，会真实调用 LLM，需要 .env 配置
    # from domain.messages import UserMessage, MessageType
    # from domain.state import Turn
    # state.pending_turn = Turn(
    #     turn_id="t1",
    #     user_message=UserMessage(sender_id="user_001", message_id="m1",
    #                              type=MessageType.TEXT, text="我想问点事"),
    #     bot_messages=[],
    # )
    # state.start_session()
    # result = asyncio.run(responder.respond(state, ClarifyReason.MULTIPLE_TRACKS))
    # print(f"[10.LLM润色     ] {result[0].text}")
