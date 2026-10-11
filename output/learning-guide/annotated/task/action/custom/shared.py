# ═══════════════════════════════════════════════════════════════════════════
# 文件职责：自定义 action 共用的工具函数——调中台接口 + 拼订单摘要
# 所在层：task.action.custom（自定义动作的工具层，供各 Lookup action 复用）
# 被谁调用：lookup_order_status / lookup_logistics / recommend_similar_products
# ═══════════════════════════════════════════════════════════════════════════
# task/action/custom/shared.py

# 模块文档串：接口调用都"静默降级"——失败返回 None，把决策权留给调用方
"""
自定义 action 共用的工具函数：
- fetch_order / fetch_logistics / fetch_product：调电商中台接口（带优雅降级，失败返回 None）
- _build_order_summary：把订单数据拼成一句摘要
"""

# Any：订单接口字段五花八门，字典值统一用 Any 标注
from typing import Any
# quote：URL 编码工具，订单号/商品号里若有特殊字符也能安全拼进路径
from urllib.parse import quote

# settings：应用配置（含中台接口的基础地址）
from conf.config import settings
# 注意：必须 import 包再取属性，见 fetch_order 内注释
# 关键写法：import 的是"子模块"而非模块内的变量——这是避开初始化时序坑的前提
from infrastructure import http_client  # 注意：必须 import 包再取属性，见 fetch_order 内注释


# _base_url：取配置里中台基础地址并去掉末尾斜杠，方便安全拼接 URL
def _base_url() -> str:
    # rstrip("/")：防止配置里多写斜杠，导致拼出 "//orders" 之类的脏路径
    return settings.commerce_api_base_url.rstrip("/")


# _extract_data：剥壳——电商接口统一包一层 {"data": {...}}，这里只把 data 取出来
def _extract_data(result: dict | None) -> dict | None:
    """电商接口返回 {"data": {...}} 包了一层，统一剥出里面的 data；非 dict 返回 None"""
    # 只有 dict 才尝试取 data；传 None 或非 dict 都安全地落空
    data = result.get("data") if isinstance(result, dict) else None
    # data 自身若不是 dict 也返回 None，防止把"脏结构"交给下游
    return data if isinstance(data, dict) else None


# fetch_order：按订单号查订单详情；失败一律降级返回 None，绝不让流程崩
async def fetch_order(order_id: str) -> dict | None:
    # try 包住整段网络调用：超时/断连/解析错都被吞掉（优雅降级）
    try:
        # 这一大段是前人踩坑记录：为何要 import"包"而不是"模块里的变量"
        # 注意此处：
        # 文件头部 from infrastructure import http_client
        # 此处使用 http_client.http_client.get(url) 调用
        # 不要这样做：
        # 文件头部 from infrastructure.http_client import http_client
        # 会使拿到的 http_client 是 None（模块初始化时序问题）
        # 真正发 GET 请求：两级取值先取"子模块"再取客户端实例；订单号做 URL 编码
        r = await http_client.http_client.get(f"{_base_url()}/orders/{quote(order_id)}")
        # 成功：把响应 json 剥成 data 返回（data 仍可能是 None，调用方再兜底）
        return _extract_data(r.json())
    except Exception:
        # 兜底：任何异常都静默返回 None，调用方据此走"降级槽位"分支
        return None


# fetch_logistics：查物流信息，结构与 fetch_order 完全同构，失败同样降级 None
async def fetch_logistics(order_id: str) -> dict | None:
    try:
        # 只在 URL 上多拼一段 /logistics，其余处理逻辑与查订单一致
        r = await http_client.http_client.get(f"{_base_url()}/orders/{quote(order_id)}/logistics")
        return _extract_data(r.json())
    except Exception:
        return None


# fetch_product：按商品号查商品详情，供推荐类 action 补充商品标题
async def fetch_product(product_id: str) -> dict | None:
    try:
        r = await http_client.http_client.get(f"{_base_url()}/products/{quote(product_id)}")
        return _extract_data(r.json())
    except Exception:
        return None


# _build_order_summary：把订单数据拼成一句给人看的中文摘要
def _build_order_summary(payload: dict[str, Any]) -> str:
    """
    把订单数据拼成一句给人看的摘要，例如"订单金额 ¥99。商品：纯棉T恤、帆布鞋。"
    :param payload: 订单接口返回的 data 字典
    :return:
    """
    # parts：逐段收集"金额句/商品句"，最后用句号拼接成一段话
    parts = []
    # 有金额字段才拼金额句；字段缺失/为 0 就跳过（防御性取数）
    if payload.get("amount"):
        parts.append(f"订单金额 ¥{payload['amount']}")
    # items 缺省用空表兜底：接口没给商品明细时不至于 TypeError
    items = payload.get("items") or []
    if items:
        # 列表推导取"前两个商品"的标题做预览；空标题的条目被过滤掉
        titles = [str(item.get("title_snapshot") or "").strip()
                  for item in items[:2] if item.get("title_snapshot")]
        # 有拿得到的标题才拼"商品："这一句
        if titles:
            parts.append("商品：" + "、".join(titles))
    # 用中文句号把各句拼成一段；一个片段都没有就返回空串（由调用方决定怎么说）
    return "。".join(parts) + "。" if parts else ""
