# 【导读】职责：把检索到的知识 chunks 拼进提示词，调 LLM 生成知识类回复（真正的执行者）
# 【导读】所在层：应用层（Responder 持有 LLM 边界；与 ChitchatResponder 同构，仅多一段知识上下文）
# 【导读】被谁调用：KnowledgeHandler.handle() 在拿到全部 chunks 后调 respond() 收尾
# knowledge/responder.py

"""
KnowledgeResponder：用检索到的知识 + LLM 生成最终回复。
与 ChitchatResponder 结构相似，多的只是 knowledge_content（把多个 chunk 拼成一段上下文）。
"""

# LangChain 字符串输出解析器：直接把 LLM 输出转 str，省去结构化解析
from langchain_core.output_parsers import StrOutputParser
# LangChain 模板类：把 jinja2 提示词文本变成可渲染模板
from langchain_core.prompts import PromptTemplate

# 消息模型：本层出入皆领域对象，与消息总线解耦
from domain.messages import BotMessage, UserMessage
# Turn 历史回合类型（拼 history 变量用）
from domain.state import Turn
# 项目统一 LLM 实例：知识问答的生成后端
from infrastructure.llm import llm
# 导入 chunk 模型：respond 入参声明 chunks 的类型（来自 providers.py）
from knowledge.providers import KnowledgeChunk
# 历史构造器：复用同一套"回合->文本历史"渲染逻辑
from prompts.history_builder import HistoryBuilder
# 模板加载器：按名读取 prompts/jinja2/knowledge_respond.jinja2
from prompts.loader import load_prompt


class KnowledgeResponder:

    # 核心方法：入参 = 用户话 + 历史 + 知识片段，出参 = 机器人回复列表
    async def respond(
            self,
            # 用户当前这句话（可能已携带商品/订单对象）
            user_message: UserMessage,
            # 最近若干轮对话历史，作为上下文
            recent_turns: list[Turn],
            # 检索到的知识片段（可能来自多个 provider 的合并结果）
            chunks: list[KnowledgeChunk],
    ) -> list[BotMessage]:
        # 准备提示词上下文
        user_message = HistoryBuilder._render_user_message(user_message)
        history = HistoryBuilder.build(recent_turns)
        # 多个 chunk（如 FAQ + RAG 双路检索）的内容用空行拼成一段完整上下文
        knowledge_content = "\n\n".join([chunk.content for chunk in chunks])

        # 构造 chain
        prompt_text = load_prompt("knowledge_respond")
        # 模板以 jinja2 格式实例化，变量名须与模板里的 {{ }} 对齐
        prompt = PromptTemplate.from_template(
            # 模板原始文本
            prompt_text,
            # 声明 jinja2 模板语法（支持 {% if %} 分支）
            template_format="jinja2",
        )
        # LCEL：模板 -> LLM -> 字符串解析，数据从左向右流过
        chain = prompt | llm | StrOutputParser()

        # 运行 chain
        response = await chain.ainvoke({
            # 模板变量：用户问题原文
            "user_message": user_message,
            # 模板变量：多轮历史文本
            "history": history,
            # 模板变量：拼好的知识上下文，LLM 据此作答
            "knowledge_content": knowledge_content,
        })

        # 包装成 BotMessage 返回，与闲聊轨道输出格式保持一致
        return [BotMessage(text=response)]
