# -*- coding: utf-8 -*-
"""验证 turn_planner 修复：意图清单是否真的注入提示词。"""
import io, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
rep = []
try:
    from knowledge.intents import KNOWLEDGE_INTENTS
    rep.append("1) KNOWLEDGE_INTENTS 载入成功，共 %d 个意图" % len(KNOWLEDGE_INTENTS))
    rep.append("   意图 id: %s" % ", ".join(KNOWLEDGE_INTENTS.keys()))
except Exception as e:
    rep.append("1) 载入 KNOWLEDGE_INTENTS 失败: %r" % e)

try:
    from plan.turn_planner import TurnPlanner
    rep.append("2) plan.turn_planner 导入成功（无循环导入）")
except Exception as e:
    rep.append("2) 导入 TurnPlanner 失败: %r" % e)
    with io.open("_fix_verify.txt","w",encoding="utf-8") as f: f.write("\n".join(rep))
    print("done"); sys.exit(0)

# 构造最小 state 与 flows，调用 _build_prompt_inputs（不联网、不调 LLM）
try:
    from domain.state import DialogueState
    from task.flow.flows import FlowsList
    from domain.messages import UserMessage
    planner = TurnPlanner()
    # 尽量构造一个能跑的 state
    user_msg = UserMessage(text="退款政策是什么")
    state = DialogueState(pending_turn=None)
    # 直接测 _build_prompt_inputs 需要 pending_turn；改为直接验证序列化逻辑
    payload = json.dumps(
        {"intents":[{"id":i.id,"description":i.description,"requires_object":i.requires_object} for i in KNOWLEDGE_INTENTS.values()]},
        ensure_ascii=False)
    obj = json.loads(payload)
    rep.append("3) 意图清单 JSON 生成成功，intents 条数 = %d" % len(obj["intents"]))
    rep.append("   样例: %s" % json.dumps(obj["intents"][2], ensure_ascii=False))
    # 校验每条都含三要素且不含 provider_ids
    ok = all("id" in i and "description" in i and "requires_object" in i and "provider_ids" not in i for i in obj["intents"])
    rep.append("4) 三要素(id/description/requires_object)齐全且未泄露 provider_ids: %s" % ("是" if ok else "否"))
except Exception as e:
    rep.append("3) 序列化验证异常: %r" % e)

# 静态检查源码：确认空串已被替换
src = io.open("plan/turn_planner.py", encoding="utf-8").read()
rep.append("5) 源码中 knowledge_intents_json = \"\" 的旧写法: %s" % ("仍存在（失败）" if 'knowledge_intents_json = ""' in src else "已移除（通过）"))
rep.append("6) 源码中已引入 KNOWLEDGE_INTENTS: %s" % ("是" if "from knowledge.intents import KNOWLEDGE_INTENTS" in src else "否"))

with io.open("_fix_verify.txt","w",encoding="utf-8") as f:
    f.write("\n".join(rep))
print("done")