"""
task/action/registry.py 单元测试
覆盖：ActionRegistry 的 register / get 行为
"""
import pytest

from task.action.base import Action, ActionResult
from task.action.registry import ActionRegistry


class _StubAction(Action):
    """测试用 Action 桩件"""
    name: str = "stub"

    async def run(self, state, action_kwargs) -> ActionResult:
        return ActionResult()


class _AnotherAction(Action):
    name: str = "another"

    async def run(self, state, action_kwargs) -> ActionResult:
        return ActionResult()


class TestActionRegistry:
    def test_register_and_get(self):
        registry = ActionRegistry()
        action = _StubAction()
        registry.register(action)
        assert registry.get("stub") is action

    def test_get_unknown_raises_key_error(self):
        registry = ActionRegistry()
        with pytest.raises(KeyError, match="Unknown action"):
            registry.get("nonexistent")

    def test_register_multiple_actions(self):
        registry = ActionRegistry()
        a1 = _StubAction()
        a2 = _AnotherAction()
        registry.register(a1)
        registry.register(a2)
        assert registry.get("stub") is a1
        assert registry.get("another") is a2

    def test_register_same_name_overwrites(self):
        registry = ActionRegistry()
        a1 = _StubAction()
        a2 = _StubAction()
        registry.register(a1)
        registry.register(a2)
        assert registry.get("stub") is a2

    def test_empty_registry_raises_on_get(self):
        registry = ActionRegistry()
        with pytest.raises(KeyError):
            registry.get("anything")
