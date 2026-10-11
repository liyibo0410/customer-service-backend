# 导读·职责：把消息对象渲染成 LLM 读的文本
# 导读·层位：prompts 层,被 TurnPlanner 调用
# 导读·产出示例：USER:我查物流 / BOT:给订单号,一问一答
# prompts/history_builder.py

# 类型注解:List/Dict 提示元素类型
from typing import List, Dict, Any
# Turn:一轮对话的数据结构(用户那句 + 机器人回复们),渲染历史要遍历它
from domain.state import Turn
# 消息模型:收发消息与点击卡片对象均在此
from domain.messages import UserMessage, BotMessage, FocusedObject, MessageType


# HistoryBuilder:纯函数式工具类,全是静态方法,不持有状态
class HistoryBuilder:
    """

    1. 将用户消息的UserMessage对象序列化为字符串---->"USER: 我准备查询订单信息"
    2. 将历史对话的Q(UserMessage)A(BotMessage)对象序列化为字符串："USER: 我想查询物流信息\n BOT: 好的，先提供订单编号"

    """

    # 静态方法:类名直调,不用 new 实例
    @staticmethod
    def build(turns: List[Turn]) -> str:
        """
        构建历史对话
        :param turns:
        :return:
        """

        # 每行文本先攒进列表,最后一次性 join,比字符串 += 高效
        msgs: List[str] = []
        # 遍历传入的每一轮(调用方通常传最近10轮)
        for turn in turns:
            # 先处理本轮的"用户提问"部分
            # 1. 用户消息
            user_message = turn.user_message
            # 把用户消息对象渲染成纯文本(文本或卡片两种形态)
            user_message_str = HistoryBuilder._render_user_message(user_message)
            # 拼上"USER:"前缀,LLM 靠它分清哪句是用户说的
            msgs.append(f"USER: {user_message_str}")
            # 再处理本轮的"机器人回复"部分(一轮可能回多条)
            # 2. 机器人回复消息
            for bot_msg in turn.bot_messages:
                # 逐条把机器人消息渲染成纯文本
                bot_msg_str = HistoryBuilder._render_bot_message(bot_msg)
                # 加"BOT:"前缀,LLM 借此知道哪句是助手的话
                msgs.append(f"BOT: {bot_msg_str}")
        # 换行拼成整段,喂 current_conversation
        return "\n".join(msgs)

    # 用户消息路由:按消息类型选"纯文本渲染"还是"对象渲染"
    @staticmethod
    def _render_user_message(user_message: UserMessage) -> str:
        """
        渲染用户消息
        :param user_message:
        :return:
        """
        # 是文本消息→直接渲染 text 字段
        if user_message.type is MessageType.TEXT:
            return HistoryBuilder._render_text_msg(user_message.text)
        # 否则是对象消息(点了卡片)→把对象渲染成结构化描述
        else:
            return HistoryBuilder._render_obj_msg(user_message.object)

    # 类方法:和静态方法类似,只是第一参约定叫 cls(这里并没用到)
    @classmethod
    def _render_bot_message(cls, bot_msg: BotMessage) -> str:
        # 机器人消息通常带 text,直接走文本渲染
        if bot_msg.text:
            return HistoryBuilder._render_text_msg(bot_msg.text)
        # 极少数情况:机器人也可能返回对象卡片,同样要能渲染
        else:
            return HistoryBuilder._render_obj_msg(bot_msg.object)  # 基本走不到


    # 文本渲染:唯一动作是去掉首尾空白,防多余空格/换行混进提示词
    @staticmethod
    def _render_text_msg(text: str) -> str:
        # strip() 顺手清理首尾空白,保证喂给 LLM 的文本干净
        return text.strip()

    # 对象渲染:拼成 label/id 等紧凑文本
    @classmethod
    def _render_obj_msg(cls, object_msg: FocusedObject) -> str:
        """
        id
        type
        title
        attributes
        :param object_msg:
        :return:
        "[id="对应的编号", type="订单对象 or 商品对象", title="对应的描述",attributes="price=1000 url="www.pic.com" ]"
        """
        # 先给对象类型起中文名:order→"订单对象",其余按商品算
        label = "订单对象" if object_msg.type == "order" else "商品对象"
        # 取对象唯一标识(订单号/商品 id)
        id = object_msg.id
        # 取对象标题,如 "iPhone 15 Pro Max"
        title = object_msg.title
        # attributes 是附加属性字典(价格/状态等)
        attributes: Dict[str, Any] = object_msg.attributes
        # 把 key:value 展平成 key=value 一行
        attributes_str = " ".join([f"{key}={value}" for key, value in attributes.items()])

        # 整体包进方括号,LLM 一眼就能读懂这是一张卡片对象
        return f"[label={label}, id={id}, title={title}, attributes={attributes_str}]"


# 自测入口:直接跑本文件时执行下面手测,被 import 时跳过
if __name__ == '__main__':

    # 这是模块级字符串,只当说明文字,实际不会执行任何逻辑
    """
    测试 HistoryBuilder 的 build 方法
    """
    # 自测脚本里重新 import,保证单独复制也能跑通
    from prompts.history_builder import HistoryBuilder
    # 造 Turn 需要 Turn 类
    from domain.state import Turn
    # 这些类型用于拼消息与卡片
    from domain.messages import UserMessage, BotMessage, FocusedObject, MessageType

    # 用例1:单轮纯文本对话,验证最基本的渲染
    def test_build_single_text_turn():
        """测试单轮纯文本对话"""
        # 先拼一个文本型用户消息:三个必填字段 + text
        # 创建用户消息
        user_msg = UserMessage(
            sender_id="user_001",
            message_id="msg_001",
            type=MessageType.TEXT,
            text="我想查询订单信息"
        )

        # 机器人可以回复多条,这里给两条
        # 创建机器人回复
        bot_msg1 = BotMessage(text="你好")
        bot_msg2 = BotMessage(text="请提供订单编号")

        # 把用户消息+回复列表包成一轮 Turn
        # 创建轮次
        turn = Turn(
            turn_id="turn_001",
            user_message=user_msg,
            bot_messages=[bot_msg1, bot_msg2]
        )

        # 调用被测方法:把这一轮渲染成"USER:/BOT:"文本
        # 构建历史对话
        result = HistoryBuilder.build([turn])
        # 打印看看渲染出来的历史长什么样
        print(f"结果:\n{result}")


    # 用例2:对象消息,验证点卡片场景的渲染
    def test_build_with_object_message():
        """测试包含对象类型的消息"""
        # 造一个"订单卡片"对象:带 id/type/title/attributes
        # 用户点击了一个订单对象
        focused_obj = FocusedObject(
            id="order_12345",
            type="order",
            title="iPhone 15 Pro Max",
            attributes={"price": "9999", "status": "已发货"}
        )

        # 对象消息:type 必须是 OBJECT,text 不填,object 指向卡片
        user_msg = UserMessage(
            sender_id="user_001",
            message_id="msg_001",
            type=MessageType.OBJECT,
            object=focused_obj
        )

        # 机器人回应仍是普通文本
        bot_msg = BotMessage(text="我看到您点击了这个订单，请问需要什么帮助？")

        # 组装成一轮"用户点卡片→机器人回应"
        turn = Turn(
            turn_id="turn_001",
            user_message=user_msg,
            bot_messages=[bot_msg]
        )

        # 再跑一次渲染,验证卡片也能转成文本
        result = HistoryBuilder.build([turn])
        # 输出里会出现 [label=订单对象, ...] 的卡片描述
        print(f"结果:\n{result}")

    # 依次执行两个手测用例
    # 运行所有测试
    test_build_single_text_turn()
    test_build_with_object_message()
