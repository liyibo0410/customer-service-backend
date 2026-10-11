# -*- coding: utf-8 -*-
"""端到端验证：真实构造 DialogueState，调用 _build_prompt_inputs，确认意图清单已注入。"""
import io, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
rep = []
try:
    from domain.state import DialogueState, Turn, Session
    from domain.messages import UserMessage, MessageType
    from task.flow.flows import FlowsList
    from task.flow.loader import FlowLoader
    from plan.turn_planner import TurnPlanner

    um = UserMessage(sender_id="u1", message_id="m1", type=MessageType.TEXT, text="我想问一下退款政策")
    turn = Turn(turn_id="t1", user_message=um, bot_messages=[])
    sess = Session(session_id="s1", started_at=0.0, last_activity_at=0.0, turns=[turn])
    state = DialogueState(sender_id="u1")
    state.sessions = [sess]
    state.current_session_id = "s1"
    state.pending_turn = turn

    # 空流程清单即可（本测试只关心知识意图字段）
    planner = TurnPlanner()
    inputs = planner._build_prompt_inputs(state, FlowsList(flows=[]))

    kj = inputs.get("knowledge_intents_json", "")
    rep.append("A) _build_prompt_inputs 调用成功")
    rep.append("B) knowledge_intents_json 长度 = %d（旧版为 0）" % len(kj))
    obj = json.loads(kj)
    rep.append("C) 解析出的意图数 = %d" % len(obj["intents"]))
    rep.append("D) 首个意图 = %s" % json.dumps(obj["intents"][0], ensure_ascii=False))
    rep.append("E) 含 requires_object 的意图 = %s" % ", ".join(i["id"] for i in obj["intents"] if i["requires_object"]))
    rep.append("F) 不泄露 provider_ids: %s" % ("是" if all("provider_ids" not in i for i in obj["intents"]) else "否"))
    rep.append("G) 关键字段齐全: %s" % ("是" if all(k in inputs for k in ["user_message","current_conversation","available_flows_json","knowledge_intents_json"]) else "否"))
except Exception as e:
    import traceback
    rep.append("异常: %r" % e)
    rep.append(traceback.format_exc())

with io.open("_fix_verify2.txt","w",encoding="utf-8") as f:
    f.write("\n".join(rep))
print("done")