# 文件导读：定义"知识意图"的数据模型，并内置 7 类意图的注册表
# 所在层：knowledge 知识层，是全项目的静态"意图词典"
# 被谁调用：TurnPlanValidator 查真伪；TurnPlanner / 执行侧 provider 也要引用
# itwwy/knowledge/intents.py

from pydantic import BaseModel

# 用 pydantic 声明强类型意图结构，字段缺失会直接报错
class KnowledgeIntent(BaseModel):
    id: str
    # 意图唯一标识：LLM 在 TurnPlan 里填的就是这个 id
    description: str
    # 给人看的说明，也常被塞进提示词教 LLM 认识意图
    provider_ids: list[str] = []
    # 处理该意图的应答器列表：api.* 走接口查询，faq/rag 走知识库
    requires_object: str | None = None
    # 非空表示必须先把对应类型的对象聚焦上，才能回答这类问题

KNOWLEDGE_INTENTS: dict[str, KnowledgeIntent] = {
    # 注册表：id → 元数据，供 O(1) 下标/查询使用
    "product_info": KnowledgeIntent(
        id="product_info",
        description="商品信息咨询",
        provider_ids=["api.product"],
        # 商品信息需要实时查商品接口，而不是翻 FAQ
        requires_object="product",
        # 用户得先发商品对象，意图才成立
    ),
    "order_info": KnowledgeIntent(
        id="order_info",
        description="订单信息咨询",
        provider_ids=["api.order"],
        # 查订单状态/物流走订单接口
        requires_object="order",
        # 必须先聚焦订单，order_info 才能答
    ),
    "refund_policy": KnowledgeIntent(
        id="refund_policy",
        description="退款政策咨询",
        provider_ids=["faq.default", "rag.default"],
        # 政策类知识从 FAQ/知识库检索即可，无需实时接口
    ),
    "return_policy": KnowledgeIntent(
        id="return_policy",
        description="退货政策咨询",
        provider_ids=["faq.default", "rag.default"],
    ),
    "shipping_policy": KnowledgeIntent(
        id="shipping_policy",
        description="配送政策咨询",
        provider_ids=["faq.default", "rag.default"],
    ),
    "platform_rule": KnowledgeIntent(
        id="platform_rule",
        description="平台规则咨询",
        provider_ids=["rag.default"],
        # 平台规则覆盖面广，只交给更全量的 RAG 检索
    ),
    "general_ecommerce_info": KnowledgeIntent(
        id="general_ecommerce_info",
        description="电商通用信息咨询",
        provider_ids=["faq.default", "rag.default"],
    ),
}
# 注意区分：product_info / order_info 要求聚焦对象；
# 其余五个政策类意图 requires_object=None，随时可答
