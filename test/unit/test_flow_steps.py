"""
task/flow/steps.py & links.py 单元测试
覆盖：FlowStep.from_dict 多态反序列化、build_links 两种形态、各子类字段
"""
import pytest

from task.flow.links import ConditionalLink, FallbackLink, StaticLink
from task.flow.steps import (
    ActionFlowStep,
    CollectFlowStep,
    EndFlowStep,
    FlowStep,
    FlowStepType,
    ResponseDefinition,
    StartFlowStep,
    STEP_TYPE_TO_CLASS,
)


class TestFlowStepLink:
    def test_static_link(self):
        link = StaticLink(target="step_2")
        assert link.target == "step_2"

    def test_conditional_link(self):
        link = ConditionalLink(condition="slots.get('ok')", target="step_yes")
        assert link.condition == "slots.get('ok')"
        assert link.target == "step_yes"

    def test_fallback_link(self):
        link = FallbackLink(target="step_else")
        assert link.target == "step_else"


class TestBuildLinks:
    def test_string_next_becomes_static_link(self):
        links = FlowStep.build_links("step_2")
        assert len(links) == 1
        assert isinstance(links[0], StaticLink)
        assert links[0].target == "step_2"

    def test_list_with_conditional(self):
        data = [{"if": "slots.get('x')", "then": "step_a"}]
        links = FlowStep.build_links(data)
        assert len(links) == 1
        assert isinstance(links[0], ConditionalLink)
        assert links[0].condition == "slots.get('x')"
        assert links[0].target == "step_a"

    def test_list_with_fallback(self):
        data = [{"else": "step_fallback"}]
        links = FlowStep.build_links(data)
        assert len(links) == 1
        assert isinstance(links[0], FallbackLink)
        assert links[0].target == "step_fallback"

    def test_mixed_conditional_and_fallback(self):
        data = [
            {"if": "slots.get('a')", "then": "step_a"},
            {"if": "slots.get('b')", "then": "step_b"},
            {"else": "step_default"},
        ]
        links = FlowStep.build_links(data)
        assert len(links) == 3
        assert isinstance(links[0], ConditionalLink)
        assert isinstance(links[1], ConditionalLink)
        assert isinstance(links[2], FallbackLink)


class TestFlowStepFromDict:
    def test_start_step(self):
        data = {
            "id": "start",
            "type": "start",
            "next": "collect_order",
            "description": "流程入口",
        }
        step = FlowStep.from_dict(data)
        assert isinstance(step, StartFlowStep)
        assert step.id == "start"
        assert step.type == FlowStepType.START
        assert step.description == "流程入口"
        assert len(step.next) == 1
        assert isinstance(step.next[0], StaticLink)

    def test_end_step(self):
        data = {"id": "end", "type": "end", "next": []}
        step = FlowStep.from_dict(data)
        assert isinstance(step, EndFlowStep)
        assert step.type == FlowStepType.END
        assert step.next == []

    def test_action_step(self):
        data = {
            "id": "do_something",
            "type": "action",
            "next": "end",
            "action": "action_response",
            "args": {"text": "好的"},
        }
        step = FlowStep.from_dict(data)
        assert isinstance(step, ActionFlowStep)
        assert step.action == "action_response"
        assert step.args == {"text": "好的"}

    def test_action_step_default_args(self):
        data = {
            "id": "act",
            "type": "action",
            "next": "end",
            "action": "action_listen",
        }
        step = FlowStep.from_dict(data)
        assert step.args == {}

    def test_collect_step(self):
        data = {
            "id": "ask_order",
            "type": "collect",
            "next": "check_order",
            "slot_name": "order_id",
            "response": {"mode": "static", "text": "请提供订单号"},
        }
        step = FlowStep.from_dict(data)
        assert isinstance(step, CollectFlowStep)
        assert step.slot_name == "order_id"
        assert isinstance(step.response, ResponseDefinition)
        assert step.response.mode == "static"
        assert step.response.text == "请提供订单号"

    def test_collect_step_rephrase_mode(self):
        data = {
            "id": "ask",
            "type": "collect",
            "next": "end",
            "slot_name": "reason",
            "response": {
                "mode": "rephrase",
                "text": "请问退款原因",
                "prompt": "用温和语气改写",
            },
        }
        step = FlowStep.from_dict(data)
        assert step.response.mode == "rephrase"
        assert step.response.prompt == "用温和语气改写"

    def test_description_defaults_to_empty(self):
        data = {"id": "s", "type": "start", "next": "end"}
        step = FlowStep.from_dict(data)
        assert step.description == ""

    def test_unknown_type_raises(self):
        data = {"id": "x", "type": "unknown_type", "next": "end"}
        with pytest.raises(KeyError):
            FlowStep.from_dict(data)


class TestStepTypeRegistry:
    def test_all_four_types_registered(self):
        assert set(STEP_TYPE_TO_CLASS.keys()) == {"start", "end", "action", "collect"}
