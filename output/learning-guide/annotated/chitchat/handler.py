# 【导读】职责：闲聊轨道入口，只做"调度不干活"，从 state 取消息+历史后委托给 ChitchatResponder
# 【导读】所在层：应用编排层（Handler 层只管取数与转发，不含任何 LLM/提示词逻辑）
# 【导读】被谁调用：上游对话路由按意图分发，闲聊类话题走本类的 handle()
# chitchat/handler.py

"""
ChitChatHandler：闲聊轨道入口。
自己不干活，把 state 里的"当前用户消息 + 最近历史"拿出来交给 ChitchatResponder。
"""

# 导入领域层消息模型：BotMessage 即机器人回复，handle 的返回值类型
from domain.messages import BotMessage
# 导入对话状态：承载用户消息/会话历史等所有上下文，贯穿全程的数据信封
from domain.state import DialogueState
# 导入真正干活的响应器（仅作类型标注，方便依赖注入）
from chitchat.responder import ChitChatResponder


# 闲聊处理器：构造时把执行者注入进来，Handler 只依赖"接口"而非具体实现
class ChitChatHandler:
    # 依赖注入：外部组装好 ChitChatResponder 传入，Handler 内部不 new
    def __init__(self, responder: ChitChatResponder):
        # 保存响应器引用，供后续 handle() 调用
        self.responder = responder

    # 闲聊入口：async 因底层要调 LLM（IO），入参是整包状态，返回回复列表
    async def handle(self, state: DialogueState) -> list[BotMessage]:
        # 本轮"待处理"的那一回合就挂在 state.pending_turn 上
        pending_turn = state.pending_turn
        # 取出用户这次说的原话（可能是文本，也可能是带对象的消息）
        user_message = pending_turn.user_message
        # 取当前会话的历史回合，作为闲聊的上下文记忆
        recent_turns = state.current_session().turns

        # 把"当前话 + 历史"两样原料交给 responder，await 等它调完 LLM
        return await self.responder.respond(
            # 关键字传参：用户这句话
            user_message=user_message,
            # 关键字传参：最近的历史回合列表
            recent_turns=recent_turns,
        )
