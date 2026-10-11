# ═══════════════════════════════════════════════════════════════════════════
# 文件职责：LookupOrderStatusAction——查订单状态的自定义动作
# 所在层：task.action.custom（自定义动作，被 builder 自动扫描注册）
# 被谁调用：YAML 流程里 action: action_lookup_order_status 的步骤
# ═══════════════════════════════════════════════════════════════════════════
# task/action/custom/lookup_order_status.py

# 模块文档串：它只"查 + 写槽"，绝不亲自开口——回复话术留给 action_response
"""
LookupOrderStatusAction：查订单状态（自定义 action）
读槽位 order_number -> 调订单接口 -> 结果写回 order_status / order_summary 槽（失败写降级槽位）。
只负责"查并写槽"，不负责生成回复——回复由后面的 action_response 读槽生成。
"""

# Any：action_kwargs 的类型标注，和基类签名保持一致
from typing import Any

# DialogueState：从 state 的槽位表里取订单号
from domain.state import DialogueState
# 动作基类 + 产物类型：本动作产出的是 slot_updates
from task.action.base import Action, ActionResult
# 复用 shared 里的接口调用与摘要拼装工具
from task.action.custom.shared import _build_order_summary, fetch_order


# 查订单状态动作：名字即"注册表的 key"，builder 扫描到本类会自动注册
class LookupOrderStatusAction(Action):
    name = "action_lookup_order_status"
    # 名字与 YAML 步骤里的 action 字段一一对应，务必保持一致

    # run：读槽→查接口→写回槽位（整个过程不产生任何 messages）
    async def run(self, state: DialogueState, action_kwargs: dict[str, Any]) -> ActionResult:
        # 输入靠槽位：order_number 是前面 collect 步骤向用户问出来的
        order_number = state.active_task.slots.get("order_number")
        # 调中台接口；失败时 shared 会返回 None，不会抛异常
        payload = await fetch_order(order_number)

        # None = 接口查询失败：走"降级槽位"，把失败也写成一个可说的状态
        if payload is None:
            # 接口查询失败：写一组"查询失败"的降级槽位，保证流程能继续不崩
            # 降级文案照样进槽，后续 action_response 读槽照说，流程无缝衔接
            return ActionResult(slot_updates={
                "order_status": "查询失败",
                "order_summary": "暂时无法查到该订单信息，请稍后再试。",
            })

        # 成功：把查询结果写回槽位，回复交给下一个 action 去生成
        return ActionResult(slot_updates={
            # 优先取人性化的 status_desc；没有就退回 status；再没有写"未知"
            "order_status": payload.get("status_desc") or payload.get("status") or "未知",
            # 用 shared 里的工具把订单原始数据拼成一句可读摘要
            "order_summary": _build_order_summary(payload),
        })
