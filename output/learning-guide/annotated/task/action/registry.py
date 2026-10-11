# ═══════════════════════════════════════════════════════════════════════════
# 文件职责：ActionRegistry 注册表——维护"动作名 -> Action 实例"的映射
# 所在层：task.action 动作框架，位于 base 之上、runner 之下
# 被谁调用：builder 写入注册、runner 按名查询（把 YAML 的名字"翻译"成实例）
# ═══════════════════════════════════════════════════════════════════════════
# task/action/registry.py

# 模块文档串：本质是一张"名字→实例"的查表，连接 YAML 字符串与真实 Python 对象
"""
ActionRegistry：Action 注册表。
维护一张 name -> Action 实例 的表，把 YAML 里的"动作名字字符串"翻译成真正可执行的 Python 实例。
"""

# 只依赖 Action 类型做类型标注，不关心具体某个动作长什么样
from task.action.base import Action


# 注册表：内部就一张 dict，名字为键、动作实例为值
class ActionRegistry:
    # 构造：建一张空表，等 builder 逐个把动作登记进来
    def __init__(self) -> None:
        # 下划线开头是"私有"约定：外部不要直接读写这张表，统一走 register / get
        self._actions: dict[str, Action] = {}

    # register：登记动作实例——builder 扫描到 Action 子类后调用它
    def register(self, action: Action) -> None:
        """注册一个 action 实例，以它的 name 为键"""
        # 以 name 属性做 key 存入；同名后注册会覆盖先注册的，配置上要避免重名
        self._actions[action.name] = action

    # get：按名取实例——runner 每执行一步都从这里查一次表
    def get(self, name: str) -> Action:
        """按名字取出 action 实例；查不到就抛 KeyError（属于配置错误，应该早暴露）"""
        # 查不到=YAML 写了不存在/拼错的 action 名，属于配置 bug
        if name not in self._actions:
            # 故意抛异常让它崩溃在明处，好过静默返回 None 带病运行
            raise KeyError(f"Unknown action '{name}'.")
        # 命中：把对应实例交出去，具体怎么执行由 runner 负责
        return self._actions[name]
