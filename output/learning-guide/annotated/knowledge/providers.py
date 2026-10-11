# 【导读】职责：定义"知识提供者"抽象接口 retrieve(state)->chunks，及商品/订单/FAQ/RAG 四类实现
# 【导读】所在层：领域/数据适配层（API 类调电商中台 HTTP 实时数据；FAQ/RAG 为可替换占位）
# 【导读】被谁调用：KnowledgeProviderRegistry 注册管理，KnowledgeHandler 经注册表取到后逐个 retrieve()
# knowledge/providers.py

"""
知识提供者：把"某一类知识来源"抽象成同一个接口 retrieve(state) -> list[KnowledgeChunk]。
- API 类：查实时业务数据（商品/订单+物流），走电商中台 HTTP 接口
- FAQ / RAG 类：占位实现，将来接入真实 FAQ 库 / 向量库时只需替换 retrieve 实现
"""

# 标准库 asyncio：用于 OrderAPIProvider 里并发发起多个 HTTP 请求
import asyncio
# 标准库 json：把接口返回的数据序列化成字符串，便于塞进给 LLM 的文本
import json
# abc 提供抽象基类机制：@abstractmethod 强制子类实现 retrieve
from abc import ABC, abstractmethod
# typing.Any：宽松标注动态类型的接口返回（dict[str, Any]）
from typing import Any

# pydantic 模型基类：KnowledgeChunk 用声明式字段 + 自动校验
from pydantic import BaseModel

# 全局配置对象：读 commerce_api_base_url（电商中台地址）
from conf.config import settings
# 对话状态：retrieve 靠它拿到 focused_object（当前聚焦的商品/订单）
from domain.state import DialogueState
# 注意：import 包再取属性（见下）
from infrastructure import http_client  # 注意：import 包再取属性（见下）


class KnowledgeChunk(BaseModel):
    """一段检索到的知识片段，最终会拼进给 LLM 的上下文"""
    content: str


class KnowledgeProvider(ABC):
    """知识提供者的抽象基类"""

    # 知识提供者的 ID（knowledge/intents.py 里意图的 provider_ids 与它对上）
    provider_id = ""

    # 声明抽象方法：所有子类必须实现它，规则即"喂 state，吐 chunks"
    @abstractmethod
    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        """
        提供检索方法
        :param state:
        :return:
        """
        # 抽象方法体不干活，仅占位（子类各自实现真实检索）
        pass


class ProductAPIProvider(KnowledgeProvider):
    """商品信息提供者：GET /products/{id}"""

    # 注册 ID：与 KnowledgeIntent.provider_ids 里的 'api.product' 一一对应
    provider_id = 'api.product'

    # 商品检索实现：从 state 取商品 id，调接口拿详情转文本，包成一个 chunk
    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        # focused_object：意图识别阶段落定的"用户正在问的商品/订单对象"
        product_id = state.focused_object.id
        # 调电商中台接口拿商品原始数据（await 等待网络返回）
        data: dict[str, Any] = await self._get_product_info_by_id(product_id)
        # 把 dict 转成带缩进的 JSON 字符串，LLM 才"读得懂"结构化数据
        text = json.dumps(data, ensure_ascii=False, indent=2)
        # 统一返回 chunk 列表：内容前加"商品信息:"提示 LLM 这是什么
        return [KnowledgeChunk(content=f"商品信息:\n{text}")]

    # 内部辅助：按 id 拼 URL 并 GET，返回其中的 data 字段
    async def _get_product_info_by_id(self, product_id: str) -> dict[str, Any]:
        # f-string 拼出商品详情接口地址（地址基座来自配置）
        url = f"{settings.commerce_api_base_url}/products/{product_id}"
        # 注意此处：
        # 文件头部 from infrastructure import http_client
        # 此处使用 http_client.http_client.get(url) 调用
        # 不要这样：
        # 文件头部 from infrastructure.http_client import http_client
        # 会使拿到的 http_client 是 None（模块初始化时序问题）
        response = await http_client.http_client.get(url)
        # 电商中台通用返回结构 {code, msg, data}，业务数据装在 data 里
        return response.json()["data"]


class OrderAPIProvider(KnowledgeProvider):
    """订单信息提供者：并发查订单 + 物流"""

    # 注册 ID：意图的 provider_ids 写 'api.order' 即可路由到本类
    provider_id = 'api.order'

    # 订单检索实现：一次要拿"订单+物流"两类数据，合并成一个 chunk
    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        # focused_object 在订单场景装的就是订单号
        order_number = state.focused_object.id

        # 用 asyncio.gather 并发查订单和物流，省一半等待时间
        # gather 同时跑两个协程，总耗时≈最慢那个而非两者之和
        order_payload, logistics_payload = await asyncio.gather(
            # 任务一：查订单基础信息
            self._fetch_order(order_number),
            # 任务二：查该订单物流轨迹（与任务一并行发出）
            self._fetch_logistics(order_number),
        )

        # 把订单号+两段数据合并成结构化 JSON，整体作为一个 chunk 返回
        return [
            KnowledgeChunk(
                # 描述头 + json 序列化结果拼接成最终知识文本
                content="订单与物流信息：\n"
                        # json.dumps 把三个字段整理成缩进 JSON
                        + json.dumps(
                    {
                        # 订单号便于 LLM 核对
                        "order_number": order_number,
                        # 订单主数据（金额/状态/商品明细…）
                        "order": order_payload,
                        # 物流数据（轨迹/承运商…）
                        "logistics": logistics_payload,
                    },
                    # 保留中文不转义，便于阅读
                    ensure_ascii=False,
                    # 两层缩进让结构清晰
                    indent=2,
                )
            )
        ]

    # 内部辅助：查订单主数据（对应中台 /orders/{order_number}）
    async def _fetch_order(self, order_number) -> dict[str, Any]:
        # 拼订单详情接口地址
        url = f"{settings.commerce_api_base_url}/orders/{order_number}"
        # GET 请求中台，await 等网络返回
        response = await http_client.http_client.get(url)
        # 取统一响应里的 data 段
        return response.json()["data"]

    # 内部辅助：查物流信息（对应中台 /orders/{order_number}/logistics）
    async def _fetch_logistics(self, order_number) -> dict[str, Any]:
        # 拼物流接口地址
        url = f"{settings.commerce_api_base_url}/orders/{order_number}/logistics"
        # GET 请求物流接口
        response = await http_client.http_client.get(url)
        # 物流接口可能无 data，用 .get 兜底成空 dict（更健壮）
        return response.json().get("data", {})


class FAQProvider(KnowledgeProvider):
    """FAQ 知识库提供者（占位）"""

    # 注册 ID：意图可声明要查 FAQ 默认库
    provider_id = 'faq.default'

    # 占位检索：先返回"没查到"，保证管线能跑通、接口形状一致
    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        # TODO 接入真实 FAQ 库
        return [KnowledgeChunk(content="FAQ：未检索到相关问题")]


class RAGProvider(KnowledgeProvider):
    """RAG 向量库提供者（占位）"""

    # 注册 ID：意图可声明要走 RAG 向量检索
    provider_id = 'rag.default'

    # 占位检索：同上，未来换成真实向量库召回即可
    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        # TODO 接入向量数据库
        return [KnowledgeChunk(content="RAG：未检索到相关信息")]
