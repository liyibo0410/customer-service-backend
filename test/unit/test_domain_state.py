"""
domain/state.py 单元测试
覆盖：DialogueState 的任务生命周期、会话管理、轮次管理、槽位操作
"""
import pytest

from domain.contexts import (
    CanceledSystemContext,
    StartedSystemContext,
    TaskContext,
)
from domain.messages import (
    FocusedObject,
    MessageType,
    UserMessage,
)
from domain.state import DialogueState, Session, Turn


def _make_state(sender_id: str = "user_1") -> DialogueState:
    return DialogueState(sender_id=sender_id)


def _make_user_message(text: str = "你好") -> UserMessage:
    return UserMessage(
        sender_id="user_1",
        message_id="msg_1",
        type=MessageType.TEXT,
        text=text,
    )


def _make_task(flow_id: str = "refund_request") -> TaskContext:
    return TaskContext(flow_id=flow_id)


class TestDialogueStateTaskLifecycle:
    def test_start_active_task(self):
        state = _make_state()
        task = _make_task()
        state.start_active_task(task)
        assert state.active_task is task
        assert state.active_task.flow_id == "refund_request"

    def test_end_active_task(self):
        state = _make_state()
        state.start_active_task(_make_task())
        state.end_active_task()
        assert state.active_task is None

    def test_cancel_active_task_clears_both(self):
        state = _make_state()
        state.start_active_task(_make_task())
        state.start_active_system_task(StartedSystemContext())
        state.cancel_active_task()
        assert state.active_task is None
        assert state.active_system_task is None

    def test_interrupted_pushes_to_paused_stack(self):
        state = _make_state()
        task = _make_task("task_a")
        state.start_active_task(task)
        state.interrupted_active_task()
        assert state.active_task is None
        assert len(state.paused_tasks) == 1
        assert state.paused_tasks[0].flow_id == "task_a"

    def test_multiple_interrupts_preserve_order(self):
        state = _make_state()
        state.start_active_task(_make_task("task_a"))
        state.interrupted_active_task()
        state.start_active_task(_make_task("task_b"))
        state.interrupted_active_task()
        assert len(state.paused_tasks) == 2
        assert state.paused_tasks[0].flow_id == "task_a"
        assert state.paused_tasks[1].flow_id == "task_b"

    def test_resume_mostRecent_by_default(self):
        state = _make_state()
        state.start_active_task(_make_task("task_a"))
        state.interrupted_active_task()
        state.start_active_task(_make_task("task_b"))
        state.interrupted_active_task()
        result = state.resumed_active_task()
        assert result is True
        assert state.active_task.flow_id == "task_b"
        assert len(state.paused_tasks) == 1

    def test_resume_by_flow_id(self):
        state = _make_state()
        state.start_active_task(_make_task("task_a"))
        state.interrupted_active_task()
        state.start_active_task(_make_task("task_b"))
        state.interrupted_active_task()
        result = state.resumed_active_task(flow_id="task_a")
        assert result is True
        assert state.active_task.flow_id == "task_a"
        assert len(state.paused_tasks) == 1
        assert state.paused_tasks[0].flow_id == "task_b"

    def test_resume_empty_stack_returns_false(self):
        state = _make_state()
        result = state.resumed_active_task()
        assert result is False

    def test_resume_unknown_flow_id_returns_false(self):
        state = _make_state()
        state.start_active_task(_make_task("task_a"))
        state.interrupted_active_task()
        result = state.resumed_active_task(flow_id="nonexistent")
        assert result is False

    def test_current_active_task_system_priority(self):
        state = _make_state()
        task = _make_task()
        sys_ctx = StartedSystemContext()
        state.start_active_task(task)
        assert state.current_active_task() is task
        state.start_active_system_task(sys_ctx)
        assert state.current_active_task() is sys_ctx

    def test_current_active_task_none_when_empty(self):
        state = _make_state()
        assert state.current_active_task() is None


class TestDialogueStateSlots:
    def test_set_slots(self):
        state = _make_state()
        state.start_active_task(_make_task())
        state.set_slots({"order_id": "A001", "reason": "质量问题"})
        assert state.active_task.slots == {"order_id": "A001", "reason": "质量问题"}

    def test_set_slots_incremental_update(self):
        state = _make_state()
        state.start_active_task(_make_task())
        state.set_slots({"order_id": "A001"})
        state.set_slots({"reason": "质量问题"})
        assert state.active_task.slots == {"order_id": "A001", "reason": "质量问题"}

    def test_set_slots_overwrites_existing(self):
        state = _make_state()
        state.start_active_task(_make_task())
        state.set_slots({"order_id": "A001"})
        state.set_slots({"order_id": "B002"})
        assert state.active_task.slots["order_id"] == "B002"

    def test_remove_slot(self):
        state = _make_state()
        state.start_active_task(_make_task())
        state.set_slots({"order_id": "A001", "reason": "质量问题"})
        state.remove_slot("reason")
        assert state.active_task.slots == {"order_id": "A001"}

    def test_remove_nonexistent_slot_raises(self):
        state = _make_state()
        state.start_active_task(_make_task())
        with pytest.raises(KeyError):
            state.remove_slot("nonexistent")


class TestDialogueStateSession:
    def test_start_session(self):
        state = _make_state()
        state.start_session()
        assert state.current_session_id is not None
        session = state.current_session()
        assert session is not None
        assert session.session_id == state.current_session_id
        assert session.started_at > 0
        assert session.closed_at is None

    def test_start_session_idempotent(self):
        state = _make_state()
        state.start_session()
        first_id = state.current_session_id
        state.start_session()
        assert state.current_session_id == first_id
        assert len(state.sessions) == 1

    def test_close_current_session(self):
        state = _make_state()
        state.start_session()
        state.close_current_session()
        assert state.current_session_id is None
        assert state.sessions[0].closed_at is not None

    def test_close_when_no_session_is_noop(self):
        state = _make_state()
        state.close_current_session()
        assert state.current_session_id is None

    def test_reset_runtime_state_preserves_sessions(self):
        state = _make_state()
        state.start_session()
        state.start_active_task(_make_task())
        state.reset_runtime_state_for_new_session()
        assert state.active_task is None
        assert state.active_system_task is None
        assert state.paused_tasks == []
        assert state.focused_object is None
        assert state.pending_turn is None
        assert state.current_session_id is None
        assert len(state.sessions) == 1

    def test_current_session_returns_none_when_no_id(self):
        state = _make_state()
        assert state.current_session() is None


class TestDialogueStateTurn:
    def test_begin_and_commit_turn(self):
        state = _make_state()
        state.start_session()
        msg = _make_user_message("退款")
        state.begin_turn(msg)
        assert state.pending_turn is not None
        assert state.pending_turn.user_message == msg
        state.commit_turn()
        assert state.pending_turn is None
        assert len(state.current_session().turns) == 1
        assert state.current_session().turns[0].user_message == msg

    def test_begin_turn_without_session_is_noop(self):
        state = _make_state()
        state.begin_turn(_make_user_message())
        assert state.pending_turn is None

    def test_commit_turn_without_session_is_noop(self):
        state = _make_state()
        state.pending_turn = Turn(
            turn_id="t1",
            user_message=_make_user_message(),
            bot_messages=[],
        )
        state.commit_turn()
        assert state.pending_turn is not None

    def test_multiple_turns_order_preserved(self):
        state = _make_state()
        state.start_session()
        for i in range(3):
            msg = _make_user_message(f"消息{i}")
            state.begin_turn(msg)
            state.commit_turn()
        turns = state.current_session().turns
        assert len(turns) == 3
        assert turns[0].user_message.text == "消息0"
        assert turns[2].user_message.text == "消息2"


class TestDialogueStateFocusedObject:
    def test_set_focused_object(self):
        state = _make_state()
        fo = FocusedObject(id="order_001", type="order", title="测试订单")
        state.set_focused_object(fo)
        assert state.focused_object == fo
        assert state.focused_object.id == "order_001"

    def test_overwrite_focused_object(self):
        state = _make_state()
        fo1 = FocusedObject(id="1", type="order")
        fo2 = FocusedObject(id="2", type="product")
        state.set_focused_object(fo1)
        state.set_focused_object(fo2)
        assert state.focused_object.id == "2"
