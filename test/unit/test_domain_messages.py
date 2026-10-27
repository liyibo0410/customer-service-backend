"""
domain/messages.py 单元测试
覆盖：FocusedObject、UserMessage、BotMessage、MessageType、ProcessResult
"""
import pytest
from pydantic import ValidationError

from domain.messages import (
    BotMessage,
    FocusedObject,
    MessageType,
    ProcessResult,
    UserMessage,
)


class TestFocusedObject:
    def test_minimal_construction(self):
        fo = FocusedObject(id="order_001", type="order")
        assert fo.id == "order_001"
        assert fo.type == "order"
        assert fo.title is None
        assert fo.attributes == {}

    def test_full_construction(self):
        fo = FocusedObject(
            id="order_001",
            type="order",
            title="纯棉T恤",
            attributes={"amount": 99.0},
        )
        assert fo.title == "纯棉T恤"
        assert fo.attributes["amount"] == 99.0

    def test_serialization_roundtrip(self):
        fo = FocusedObject(id="p1", type="product", title="测试商品")
        data = fo.model_dump(mode="json")
        restored = FocusedObject.model_validate(data)
        assert restored == fo

    def test_attributes_default_factory_isolation(self):
        fo1 = FocusedObject(id="1", type="t")
        fo2 = FocusedObject(id="2", type="t")
        fo1.attributes["key"] = "value"
        assert "key" not in fo2.attributes


class TestMessageType:
    def test_enum_values(self):
        assert MessageType.TEXT.value == "text"
        assert MessageType.OBJECT.value == "object"

    def test_enum_from_value(self):
        assert MessageType("text") is MessageType.TEXT
        assert MessageType("object") is MessageType.OBJECT


class TestUserMessage:
    def test_text_message(self):
        msg = UserMessage(
            sender_id="user_1",
            message_id="msg_1",
            type=MessageType.TEXT,
            text="你好",
        )
        assert msg.sender_id == "user_1"
        assert msg.type == MessageType.TEXT
        assert msg.text == "你好"
        assert msg.object is None

    def test_object_message(self):
        obj = FocusedObject(id="order_001", type="order")
        msg = UserMessage(
            sender_id="user_1",
            message_id="msg_2",
            type=MessageType.OBJECT,
            object=obj,
        )
        assert msg.type == MessageType.OBJECT
        assert msg.text is None
        assert msg.object == obj

    def test_missing_required_fields_raises(self):
        with pytest.raises(ValidationError):
            UserMessage(sender_id="u1")

    def test_serialization_roundtrip(self):
        msg = UserMessage(
            sender_id="user_1",
            message_id="msg_3",
            type=MessageType.TEXT,
            text="测试",
        )
        data = msg.model_dump(mode="json")
        restored = UserMessage.model_validate(data)
        assert restored == msg


class TestBotMessage:
    def test_text_only(self):
        bm = BotMessage(text="好的")
        assert bm.text == "好的"
        assert bm.object is None

    def test_with_object(self):
        obj = FocusedObject(id="p1", type="product")
        bm = BotMessage(text="这是您的商品", object=obj)
        assert bm.object == obj

    def test_empty_message(self):
        bm = BotMessage()
        assert bm.text is None
        assert bm.object is None


class TestProcessResult:
    def test_construction(self):
        result = ProcessResult(
            sender_id="user_1",
            message_id="resp_1",
            messages=[BotMessage(text="回复1"), BotMessage(text="回复2")],
        )
        assert result.sender_id == "user_1"
        assert len(result.messages) == 2
        assert result.messages[0].text == "回复1"

    def test_empty_messages_list(self):
        result = ProcessResult(
            sender_id="user_1",
            message_id="resp_2",
            messages=[],
        )
        assert result.messages == []
