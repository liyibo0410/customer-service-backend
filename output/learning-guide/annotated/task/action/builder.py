# ═══════════════════════════════════════════════════════════════════════════
# 文件职责：Action 装配工厂——内置手动注册、自定义包自动扫描注册
# 所在层：task.action 动作框架，负责把分散的 Action 类组装成完整 runner
# 被谁调用：上层（service/engine）启动时调 build_action_runner() 一次性初始化
# ═══════════════════════════════════════════════════════════════════════════
# task/action/builder.py

# 模块文档串：两种注册策略对比——内置手动、自定义自动（开闭原则的落点）
"""
Action 装配工厂：
- 内置 action：手动注册（少而稳定）
- 自定义 action：扫描 custom 包，自动发现并注册 Action 子类（开闭原则：新增 action 不用改注册代码）
"""

# importlib：按"模块名字符串"动态导入模块（custom 下各文件是运行时发现的）
import importlib
# inspect：反射遍历模块的成员，用来筛出其中的 Action 子类
import inspect
# pkgutil：遍历一个包路径，枚举出包里的所有子模块（自动发现的入口）
import pkgutil

# Action 基类：判定一个类是否"值得注册"的判据
from task.action.base import Action
# 内置哨兵动作：等用户输入
from task.action.builtin.action_listen import ActionListen
# 内置回复动作：几乎所有的"对用户说话"
from task.action.builtin.action_response import ActionResponse
# 注册表：所有动作实例最后都登记到这里
from task.action.registry import ActionRegistry
# 执行器：注册表装配完成后，由它对外提供"按名执行"能力
from task.action.runner import ActionRunner


# register_builtin_actions：内置动作数量少且稳定，手动点名注册即可
def register_builtin_actions(action_runner: ActionRunner):
    """
    注册内置的 action：手动 register
    :param action_runner:
    :return:
    """
    # 两个内置动作各实例化一次（无状态单例，可放心复用）
    action_listen = ActionListen()
    action_response = ActionResponse()
    # 依次登记进注册表：注册发生在"建 runner"阶段，一次完成、永久生效
    action_runner.registry.register(action_listen)
    action_runner.registry.register(action_response)


# register_custom_actions：扫描 custom 包自动发现——新动作只需在包里加文件
def register_custom_actions(action_runner: ActionRunner):
    """
    扫描 custom 包，完成 Action 子类的自动注册
    :param action_runner:
    :return:
    """
    # 先把 custom 包本身导入成对象，拿到它的 __path__ 才能枚举里面的模块
    package = importlib.import_module("task.action.custom")

    # iter_modules 枚举包内全部模块：(_, 模块名, 是否子包)；prefix 拼出模块全名
    for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__, prefix=f"{package.__name__}."):
        # 只处理模块文件，不处理子包
        # 跳过子包：扫描目标是"扁平放着的 action 文件"，递归进子包会扫歪
        if is_pkg:
            continue
        # 逐个真正导入子模块，模块顶层的 Action 子类定义才会被执行
        module = importlib.import_module(module_name)
        # 反射遍历模块里所有"类"，逐个过筛
        for _, obj in inspect.getmembers(module, inspect.isclass):
            # 只要 Action 的子类，排除基类本身
            # 反射筛类：issubclass 保证是动作家族；"obj is Action"排除抽象基类自身
            if not issubclass(obj, Action) or obj is Action:
                continue
            # 只注册"在这个模块里定义的"类，排除被 import 进来的
            # 防重：文件头 import 进来的他人 Action 不该被重复注册
            if obj.__module__ != module.__name__:
                continue
            # 实例化并注册：新增一个 Action 子类文件即自动生效，注册代码零改动（开闭原则）
            action_runner.registry.register(obj())


# build_action_runner：装配入口——造注册表、包 runner、先后注册两类动作
def build_action_runner() -> ActionRunner:
    """组装并返回一个已注册所有 action 的 ActionRunner"""
    # 新建空注册表并包一层 runner，后面所有注册都挂在它身上
    action_runner = ActionRunner(ActionRegistry())
    register_builtin_actions(action_runner)
    register_custom_actions(action_runner)
    # 返回一个"满配"执行器：之后 executor 直接拿它跑动作
    return action_runner


# 直接运行本文件即自测：打印已注册的全部动作名，肉眼验收注册结果
if __name__ == '__main__':
    # 自测时调用一次完整装配流程
    runner = build_action_runner()
    # sorted 排序后打印，方便核对；这里读私有 _actions 仅限演示
    print("已注册 action：", sorted(runner.registry._actions.keys()))
