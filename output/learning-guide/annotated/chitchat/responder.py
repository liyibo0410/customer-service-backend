# 【导读】职责：闲聊轨道的"执行者"，真正调 LLM 自然回一句（Handler 只递原料给它）
# 【导读】所在层：应用层（Responder 组合提示词/LLM/输出解析器，是知识轨道的 LLM 边界）
# 【导读】被谁调用：ChitChatHandler.handle()，以及将来其他需要闲聊回复的地方
# chitchat/responder.py

"""
ChitchatResponder：闲聊的真正干活的——调 LLM 自然回一句。
只拿两样原料：用户这句话 + 最近的对话历史。
"""

# LangChain 输出解析器：把 LLM 返回的字符串直接透传成 str
from langchain_core.output_parsers import StrOutputParser
# LangChain 提示词模板：把外部 jinja2 文本包成可渲染的 PromptTemplate
from langchain_core.prompts import PromptTemplate

# 消息模型：BotMessage 出、UserMessage 入（都是领域对象而非裸字符串）
from domain.messages import BotMessage, UserMessage
# Turn：一回合对话（用户消息+机器人回复）的模型，历史即 Turn 列表
from domain.state import Turn
# 项目统一配置好的 LLM 实例（链的最后一段，负责真实生成）
from infrastructure.llm import llm
# 历史构造器：把多轮 Turn 渲染成给 LLM 看的"对话记录"文本
from prompts.history_builder import HistoryBuilder
# 提示词加载器：按名字（如 chitchat_respond）读 prompts/jinja2 下的模板文本
from prompts.loader import load_prompt


# 闲聊响应器：无需实例化字段，方法即服务（stateless 设计）
class ChitChatResponder:

    # 对外唯一入口：吃进用户消息+历史，吐出 BotMessage 列表
    async def respond(
            self,
            # 用户当前这句话（领域对象，可能携带商品/订单对象）
            user_message: UserMessage,
            # 最近若干轮对话（充当闲聊的上下文记忆）
            recent_turns: list[Turn],
    ) -> list[BotMessage]:
        # 把用户消息渲染成文本（对象消息也能转成 [订单对象 ...] 描述）
        user_message = HistoryBuilder._render_user_message(user_message)
        # 会话历史拼成对话记录
        history = HistoryBuilder.build(recent_turns)

        # 加载闲聊提示词 -> 组链 -> 调 LLM
        prompt_text = load_prompt("chitchat_respond")
        # 以 jinja2 格式把模板文本包装成 PromptTemplate（变量名对齐模板）
        prompt = PromptTemplate.from_template(prompt_text, template_format="jinja2")
        # LCEL 链式语法：模板 -> LLM -> 字符串解析器，| 即数据依次流过
        chain = prompt | llm | StrOutputParser()
        # 把变量喂进模板，await 触发一次 LLM 调用
        response = await chain.ainvoke({
            # 模板里的 {{ user_message }}
            "user_message": user_message,
            # 模板里的 {{ history }}
            "history": history,
        })
        # 统一用 BotMessage 包装回复，外层只认这个消息模型
        return [BotMessage(text=response)]
