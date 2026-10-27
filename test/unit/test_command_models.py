"""
task/command/models.py 单元测试
覆盖：Command.from_dict 反序列化分发、各子类字段校验、注册表完整性
"""
import pytest
from pydantic import ValidationError

from task.command.models import (
    CancelFlowCommand,
    Command,
    ResumeFlowCommand,
    SetSlotsCommand,
    StartFlowCommand,
    COMMAND_NAME_TO_CLASS,
)


class TestCommandFromDict:
    def test_start_flow(self):
        data = {"command": "start_flow", "flow": "refund_request"}
        cmd = Command.from_dict(data)
        assert isinstance(cmd, StartFlowCommand)
        assert cmd.flow == "refund_request"
        assert cmd.command == "start_flow"

    def test_set_slots(self):
        data = {"command": "set_slots", "slots": {"order_id": "A001"}}
        cmd = Command.from_dict(data)
        assert isinstance(cmd, SetSlotsCommand)
        assert cmd.slots == {"order_id": "A001"}

    def test_cancel_flow(self):
        data = {"command": "cancel_flow"}
        cmd = Command.from_dict(data)
        assert isinstance(cmd, CancelFlowCommand)

    def test_resume_flow_without_flow_id(self):
        data = {"command": "resume_flow"}
        cmd = Command.from_dict(data)
        assert isinstance(cmd, ResumeFlowCommand)
        assert cmd.flow is None

    def test_resume_flow_with_flow_id(self):
        data = {"command": "resume_flow", "flow": "refund_request"}
        cmd = Command.from_dict(data)
        assert isinstance(cmd, ResumeFlowCommand)
        assert cmd.flow == "refund_request"


class TestCommandRegistry:
    def test_all_four_commands_registered(self):
        assert len(COMMAND_NAME_TO_CLASS) == 4
        assert "start_flow" in COMMAND_NAME_TO_CLASS
        assert "set_slots" in COMMAND_NAME_TO_CLASS
        assert "cancel_flow" in COMMAND_NAME_TO_CLASS
        assert "resume_flow" in COMMAND_NAME_TO_CLASS

    def test_unknown_command_raises(self):
        with pytest.raises(KeyError):
            Command.from_dict({"command": "unknown_command"})

    def test_missing_command_field_raises(self):
        with pytest.raises(KeyError):
            Command.from_dict({})


class TestCommandSubclassValidation:
    def test_start_flow_missing_flow_raises(self):
        with pytest.raises(ValidationError):
            StartFlowCommand(command="start_flow")

    def test_set_slots_missing_slots_raises(self):
        with pytest.raises(ValidationError):
            SetSlotsCommand(command="set_slots")

    def test_set_slots_empty_dict_ok(self):
        cmd = SetSlotsCommand(command="set_slots", slots={})
        assert cmd.slots == {}
