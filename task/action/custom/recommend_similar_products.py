# ═══════════════════════════════════════════════════════════════════════════
# 文件职责：RecommendSimilarProductsAction——推荐相似商品（占位动作）
# 所在层：task.action.custom（自定义动作，被 builder 自动扫描注册）
# 被谁调用：YAML 流程里 action: action_recommend_similar_products 的步骤
# ═══════════════════════════════════════════════════════════════════════════
# task/action/custom/recommend_similar_products.py

# 模块文档串：与两个 Lookup 动作相反，它直接产出 messages——因为它"自己就会说话"
"""
RecommendSimilarProductsAction：推荐相似商品（占位 action）
直接返回一句"已收到需求，功能待接入"的回复（产出 messages，不是 slot_updates）。
会先查一下商品名让回复更具体，查不到就用"这件商品"兜底。
"""

# Any：action_kwargs 的类型标注，与基类签名保持一致
from typing import Any

# BotMessage：本动作直接回复用户，产物要装 messages
from domain.messages import BotMessage
# DialogueState：从槽位表里取用户点选的商品
from domain.state import DialogueState
# 动作基类 + 产物类型
from task.action.base import Action, ActionResult
# 复用 shared 里的商品查询工具：只为了拿到商品标题
from task.action.custom.shared import fetch_product


# 推荐相似商品动作（占位版）：先说明"功能还没接"，不真的做推荐
class RecommendSimilarProductsAction(Action):
    name = "action_recommend_similar_products"
    # 名字是注册表的 key，builder 扫描到本类会自动注册

    # run：拼一句占位回复直接发给用户——这是一个"生成回复类"而非"查询写槽类"动作
    async def run(self, state: DialogueState, action_kwargs: dict[str, Any]) -> ActionResult:
        # 先读用户点选/说出的商品 id（可能是 None）
        product_id = state.active_task.slots.get("product_id")
        # label：回复里用来指代该商品的名字；没有 id 就用通用词"这件商品"兜底
        label = product_id or "这件商品"

        # 尝试调商品接口拿正式标题（查不到也不强求，接口层已返回 None）
        payload = await fetch_product(product_id)
        # 有数据且标题非空才替换 label，让回复更具体；否则沿用兜底说法
        if payload:
            label = str(payload.get("title") or "").strip() or label

        # 多行字符串拼接：组装一段占位文案（f-string 把 label 嵌进句子里）
        text = (
            f"我已经收到你对\"{label}\"的相似商品推荐需求。"
            "不过当前版本还没有接入正式的推荐系统，稍后可以继续补上这部分能力。"
        )
        # 产物走 messages 通道：占位动作直接开口回复，不需要再派 action_response
        return ActionResult(messages=[BotMessage(text=text)])
