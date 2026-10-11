# ═══════════════════════════════════════════════════════════════════════════
# 文件职责：LookupLogisticsAction——查物流状态的自定义动作
# 所在层：task.action.custom（自定义动作，被 builder 自动扫描注册）
# 被谁调用：YAML 流程里 action: action_lookup_logistics 的步骤
# ═══════════════════════════════════════════════════════════════════════════
# task/action/custom/lookup_logistics.py

# 模块文档串：与查订单几乎同构——读槽→调物流接口→写 logistics_* 槽位
"""
LookupLogisticsAction：查物流（自定义 action）
和查订单几乎一样的结构：读 order_number -> 调物流接口 -> 写 logistics_* 槽 / 失败降级。
"""
# 本文件可对照 lookup_order_status.py 一起读，体会"动作模板"的套路

# Any：action_kwargs 的类型标注，与基类签名保持一致
from typing import Any

# DialogueState：从 state 的槽位表里取订单号
from domain.state import DialogueState
# 动作基类 + 产物类型：查询动作统一走 slot_updates 通道
from task.action.base import Action, ActionResult
# 复用 shared 里的物流接口调用工具
from task.action.custom.shared import fetch_logistics


# 查物流动作：名字与 YAML 的 action: action_lookup_logistics 对应
class LookupLogisticsAction(Action):
    name = "action_lookup_logistics"
    # 名字是注册表的 key，builder 扫描到本类会自动注册

    # run：读槽→查物流接口→把结果写回槽位（同样不直接说话）
    async def run(self, state: DialogueState, action_kwargs: dict[str, Any]) -> ActionResult:
        # 输入靠槽位：与查订单共用同一个 order_number（复用 collect 的提问成果）
        order_number = state.active_task.slots.get("order_number")
        # 调物流接口；失败时返回 None（shared 里已做优雅降级）
        payload = await fetch_logistics(order_number)

        # None = 查询失败：三个物流槽位全部写入"未知/提示"降级值
        if payload is None:
            # 降级槽位照样能让流程继续：action_response 读了也说得通
            return ActionResult(slot_updates={
                "tracking_number": "未知",
                "logistics_company": "未知",
                "logistics_status": "暂时无法查到物流信息，请稍后再试。",
            })

        # 成功：把物流三件套（单号/公司/状态）写回槽位，供后续 action_response 念出来
        return ActionResult(slot_updates={
            "tracking_number": payload.get("tracking_number") or "未知",
            # 字段缺失时用"未知"兜底，保证回复模板里不会出现 None
            "logistics_company": payload.get("logistics_company") or "未知",
            # 状态优先取可读的 status_desc，退而求其次用 status，再没有写"未知"
            "logistics_status": payload.get("status_desc") or payload.get("status") or "未知",
        })
