# 【导读】职责：知识提供者注册表，构造时收编所有 provider，运行时按 provider_id 查出实例
# 【导读】所在层：基础设施/组装层（常与 DI 容器配合，Handler 只持有本注册表不直接依赖具体类）
# 【导读】被谁调用：KnowledgeHandler.handle() 在遍历 provider_ids 时经 get() 取提供者
# knowledge/registry.py

"""
KnowledgeProviderRegistry：知识提供者注册表。
构造时传入所有 provider 实例，运行时按 provider_id 快速查找。
get 找不到时直接抛 KeyError——provider_id 是代码写死的常量，不该出现找不到。
"""

# 仅导入抽象基类用于类型标注（字典值类型声明为 KnowledgeProvider）
from knowledge.providers import KnowledgeProvider


class KnowledgeProviderRegistry:
    """
    知识提供者注册表
    """

    # 构造时把 provider 列表转成 {provider_id: 实例} 字典——查表 O(1)
    def __init__(self, providers: list[KnowledgeProvider]) -> None:
        # 字典推导：以各 provider 的 provider_id 为键建立索引
        self._providers_by_id = {p.provider_id: p for p in providers}

    # 按 id 取提供者；键不存在时 dict 原生抛 KeyError（有意为之，见模块 docstring）
    def get(self, provider_id: str) -> KnowledgeProvider:
        # 直接查字典返回对应实例，没有就用不到此处的多余分支
        return self._providers_by_id[provider_id]
