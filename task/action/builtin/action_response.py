# ═══════════════════════════════════════════════════════════════════════════
# 文件职责：定义回复动作 ActionResponse——几乎所有"对用户说话"的出口
# 所在层：task.action.builtin（内置动作），按 mode 分三条说话路径
# 被谁调用：builder 手动注册；YAML 中 action: action_response 的步骤都会执行它
# ═══════════════════════════════════════════════════════════════════════════
# task/action/builtin/action_response.py

# 模块文档串：记住一个判断——"要不要花钱请 LLM 说话"，mode 是开关
"""
ActionResponse：几乎所有"对用户说话"都靠它。三种模式：
- static   : 文案写死在 YAML，渲染模板后直接用（最常用，不走 LLM）
- rephrase : 有模板底稿，让 LLM 润色得更自然（走 LLM）
- generate : 没有预设文案，让 LLM 从零生成（走 LLM）
"""

# Any：action_kwargs 随 YAML 变化，类型不固定
from typing import Any

# jinja2 模板：负责渲染 YAML 文案里的 {{ }} 占位符
from jinja2 import Template
# 输出解析器：把 LLM 返回对象转成纯字符串
from langchain_core.output_parsers import StrOutputParser
# 提示词模板：把 prompt 文案变成可填变量的 langchain 模板
from langchain_core.prompts import PromptTemplate

# BotMessage：产物 messages 的元素，机器人回复的载体
from domain.messages import BotMessage
# DialogueState：渲染模板时从 state 取槽位/上下文
from domain.state import DialogueState
# 全局 LLM 实例：rephrase/generate 两条路都用它生成文案
from infrastructure.llm import llm
# 历史构建器：把多轮 turns 拼成给 LLM 看的对话历史
from prompts.history_builder import HistoryBuilder
# 动作基类与产物类型
from task.action.base import Action, ActionResult


# 回复动作：一个动作三种说法，YAML 的 mode 决定走哪条路
class ActionResponse(Action):
    # 统一名字：几乎所有"要说话"的 action 步骤都指向它
    name = "action_response"

    # run：三种模式的"分发中心"——static/rephrase/generate 三选一
    async def run(self, state: DialogueState, action_kwargs: dict[str, Any]) -> ActionResult:
        """
        按 mode 分三种处理
        :param state:
        :param action_kwargs: 来自 YAML action 步骤的 args（mode/text/prompt 等）
        :return:
        """
        # 读出说话方式；YAML 没写 mode 就按最省事的 static 处理
        mode = action_kwargs.get("mode", "static")
        # static：文案写死在 YAML——渲染占位符后直接说，最快的路、不发 LLM
        if mode == "static":
            # 取出写死的原话（含 {{ }} 占位符，不是 LLM 编的）
            text = action_kwargs['text']
            # 先用当前槽位把 {{ }} 替换成真实值，得到最终台词
            rendered_text = self._render_text(text, state)
            # 产物走 messages 通道：包成一条 BotMessage，外层会原样发给用户
            return ActionResult(messages=[BotMessage(text=rendered_text)])

        # rephrase：有底稿但嫌生硬——让 LLM 照着底稿"润色"，保留要点改说法
        elif mode == "rephrase":
            text = action_kwargs['text']
            rendered_text = self._render_text(text, state)   # 先渲染出底稿
            prompt_text = action_kwargs['prompt']            # 再按润色指令交给 LLM
            # 底稿当"建议回复"喂给 LLM，语义不变但语气更自然
            message = await self._call_llm(prompt_text, state, rendered_text)
            # 润色结果同样包成 BotMessage 走 messages 通道
            return ActionResult(messages=[BotMessage(text=message)])

        # generate：无预设文案——只给 prompt 和上下文，让 LLM 从零写一句话
        else:  # generate
            # prompt：生成指令模板，只交代"该说什么"，不给底稿
            prompt_text = action_kwargs['prompt']
            # 注意：没传 rendered_text，方法内部会当空串处理（generate 无底稿）
            message = await self._call_llm(prompt_text, state)
            return ActionResult(messages=[BotMessage(text=message)])

    # _render_text：模板渲染——把 YAML 文案里的 {{ }} 替换成当前对话的真实数据
    def _render_text(self, text: str, state: DialogueState) -> str:
        """
        把模板里的 {{ }} 替换成真实值。
        模板能访问两个变量：
        - slots  : 当前业务任务收集/查到的槽位
        - context: 当前上下文（系统过场优先，否则业务任务）
        """
        # 把字符串当 jinja2 模板编译（语法是 {{ 变量 }}，与 LLM 的 {变量} 不同）
        template = Template(text)
        # render 时注入两个变量：slots=当前槽位表；context=系统过场优先取
        result = template.render(
            slots=state.active_task.slots if state.active_task else {},
            context=state.active_system_task or state.active_task,
        )
        # 渲染完的纯文本就是最终要出口的台词
        return result

    # _call_llm：统一走 LLM 的出口——rephrase 传底稿当参考；generate 不传用空串
    async def _call_llm(self, prompt_text: str, state: DialogueState, rendered_text: str = "") -> str:
        """
        rephrase 和 generate 都走这个方法，区别在传不传 rendered_text（建议回复底稿）
        :param prompt_text: 给 LLM 的指令模板
        :param state:
        :param rendered_text: rephrase 模式的底稿，generate 模式为空串
        :return:
        """
        # 把指令文案转成 langchain PromptTemplate（占位符写法是 {变量}）
        prompt = PromptTemplate.from_template(prompt_text)   # langchain 模板，变量用 {xxx}
        # LangChain 管道：模板→LLM→字符串解析器，"|" 像流水线把三个环节串起来
        chain = prompt | llm | StrOutputParser()

        # ainvoke 异步调整条链；喂三个变量：历史对话/本轮用户话/底稿（参考用）
        bot_message = await chain.ainvoke({
            "history": HistoryBuilder.build(state.current_session().turns),
            "user_message": HistoryBuilder._render_user_message(state.pending_turn.user_message),
            "current_response": rendered_text,
        })
        # 链的末端是 StrOutputParser，返回的就是可直接展示的字符串
        return bot_message
