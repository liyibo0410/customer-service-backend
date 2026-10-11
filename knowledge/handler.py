# 【导读】职责：知识轨道入口，编排"意图->provider_ids->检索chunks->responder生成回复"三步流程
# 【导读】所在层：应用编排层（只调度不干活，业务细节全部下沉给 provider 与 responder）
# 【导读】被谁调用：上游路由判定需查业务/知识时，带上意图列表调 handle()
# knowledge/handler.py

"""
KnowledgeHandler：知识轨道入口，编排整个 knowledge 流程：
① 意图 -> 知识来源(provider_ids)
② 从每个 provider 检索知识片段(chunks)
③ 用知识 + 对话上下文生成回复
"""

# BotMessage：回复消息模型（输出类型）
from domain.messages import BotMessage
# DialogueState：对话状态，handle 的上下文入参
from domain.state import DialogueState
# 知识意图配置模型：映射"意图名 -> 该查哪些 provider"
from knowledge.intents import KnowledgeIntent
# chunk 模型：流程第②步的产物类型声明
from knowledge.providers import KnowledgeChunk
# 注册表：按 provider_id 取出对应知识提供者
from knowledge.registry import KnowledgeProviderRegistry
# 回复器：第③步真正调 LLM 生成回答的执行者
from knowledge.responder import KnowledgeResponder


class KnowledgeHandler:

    # 依赖注入：三样依赖全部在构造时传进来，Handler 自身不负责创建
    def __init__(
            self,
            # 意图表：{意图名: KnowledgeIntent}，含各意图对应的 provider_ids
            knowledge_intents: dict[str, KnowledgeIntent],
            # 提供者注册表：用 provider_id 换取检索实现
            provider_registry: KnowledgeProviderRegistry,
            # 知识回复器：负责把 chunks 拼进提示词并调 LLM
            knowledge_responder: KnowledgeResponder):

        # 保存意图表引用
        self.knowledge_intents = knowledge_intents
        # 保存注册表引用
        self.provider_registry = provider_registry
        # 保存回复器引用
        self.knowledge_responder = knowledge_responder

    # 知识轨道主入口：给定 LLM 判出的意图列表 + 对话状态，产出回复
    async def handle(self, intents: list[str], state: DialogueState) -> list[BotMessage]:
        # 1. 根据意图寻找知识来源（知识提供者 id 列表）
        # 意图可能多个且可能指向同一 provider，此函数负责映射并去重
        provider_ids: list[str] = self._get_provider_ids_by_intents(intents)

        # 2. 从每个 provider 检索知识片段
        # 收集桶：聚合各 provider 返回的 chunks
        chunks: list[KnowledgeChunk] = []
        # 逐个 provider 检索（provider 少且多为独立请求，顺序执行即可）
        for provider_id in provider_ids:
            # 经注册表拿到该 id 对应的知识提供者实例
            provider = self.provider_registry.get(provider_id)
            # 调用统一的 retrieve 接口，await 等网络/检索返回
            current_chunks = await provider.retrieve(state)
            # 把本次拿到的 chunks 追加进总列表
            chunks.extend(current_chunks)

        # 3. 用知识生成回复
        # 把用户话+历史+全部 chunks 交给 responder，await 等 LLM 回复
        return await self.knowledge_responder.respond(
            # 用户当前这句话从待处理回合取
            user_message=state.pending_turn.user_message,
            # 当前会话历史作为上下文
            recent_turns=state.current_session().turns,
            # 检索到的全部知识片段（合并后交给模板渲染）
            chunks=chunks,
        )

    # 私有辅助：把意图列表映射成 provider_ids 并去重（set 会打乱顺序，此处无顺序要求）
    def _get_provider_ids_by_intents(self, intents: list[str]) -> list[str]:
        """
        意图 -> provider_ids 并去重。
        LLM 可能一次给多个意图（如同时问退款+退货政策），它们可能指向同一个 provider。
        """
        # 结果列表：收集各意图声明的 provider_id
        provider_ids: list[str] = []
        # 遍历每个意图名
        for intent in intents:
            # 从意图表取出该意图配置，把它要求的 provider_ids 全部展开追加
            provider_ids.extend(self.knowledge_intents[intent].provider_ids)
        # 转 set 去重再转回 list，避免同一 provider 被重复检索
        return list(set(provider_ids))
