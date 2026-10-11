# 【导读】本文件定义"步骤之间的跳转边(Link)"模型：流程被建模成一张有向图，节点是步骤、边决定下一步去哪。
# 三种边：StaticLink 无条件直连(对应 next 直接写字符串)、ConditionalLink 条件分支(对应 {if,then})、
# FallbackLink 兜底分支(对应 {else})；三者继承自基类 FlowStepLink(公共字段仅 target=目标步骤id)，可统一按 List[FlowStepLink] 多态使用。
# itwwy/task/flow/links.py

from pydantic import BaseModel


# —— 基类 FlowStepLink ——
# 声明所有"边"共有的结构：只须知道要跳去哪个步骤的 id(stepID)。
# 基类同样继承 pydantic.BaseModel，确保子类能被 pydantic 统一校验/序列化/反序列化。
class FlowStepLink(BaseModel):
    """
    模版边（基类）
    """
    target: str  # 下一步的stepID


# —— StaticLink 静态边 ——
# 对应 YAML 写法 "next: 某step_id"（next 的值直接是一个字符串）：
# 无任何条件，当前步骤走完必然跳转到 target。
# 除基类字段外没有新增字段，因此用 pass 占位，仅"类型名"有区分意义。
class StaticLink(FlowStepLink):
    """
    静态边
    对应 next 的值是字符串
    """
    pass


# —— ConditionalLink 条件边 ——
# 对应 YAML 中 next 为列表且其中一项形如 {if: "判断表达式", then: step_id}。
# condition 字段承载 if 后的表达式字符串（例如 "slots.get('product_id')"），
# 运行期由引擎执行该表达式：为真则跳 target；为假则跳过本边、继续检查下一条边。
class ConditionalLink(FlowStepLink):
    """
    对应的是 next:[{if:"xxxxxx",then:step_id}]
    """
    condition: str  # 接收if 中的 xxxxx


# —— FallbackLink 兜底边 ——
# 对应 YAML 中 next 列表里的 {else: step_id}，充当一串 if-then 判断之后的 else 分支：
# 当所有 ConditionalLink 都不满足时，流程沿这条兜底边走，避免"无路可走"而卡死。
# 语义是"最后才走的无条件下一条"，不需要额外字段，故同样用 pass 占位。
class FallbackLink(FlowStepLink):
    """"
    对应的是 next:[{else:step_id}]
    """
    pass
