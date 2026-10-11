# -*- coding: utf-8 -*-
"""
把 day01-day06 六篇讲义 + 项目源码打包成一个可离线浏览的学习 HTML。

原则：
- 讲义正文逐字保留，只做排版、代码高亮、图片本地化
- 源码按天归类，带行号高亮，便于逐行对照阅读

运行：
  <工具venv>/python.exe output/build_guide.py
"""
import html
import re
import shutil
from pathlib import Path

import markdown
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name

DOC_BASE = Path(r"D:\个人文件\AI大模型学习资料\16-智能客服")
PROJ = Path(r"D:\software\PycharmProjects\customer-service-backend")
OUT = PROJ / "output" / "learning-guide"
IMG_OUT = OUT / "images"

# ============ 六篇讲义 ============
DOCS = [
    ("day01", "Day 1 · 项目概述与整体架构",
     r"day01\01【电商小二】项目概述与整体架构.md"),
    ("day02", "Day 2 · 领域模型 domain",
     r"day03\02【电商小二】领域模型domain.md"),
    ("day03", "Day 3 · 流程数据模型与加载",
     r"day03\03【电商小二】流程数据模型与加载.md"),
    ("day04", "Day 4 · 三层架构",
     r"day04\04【电商小二】三层架构.md"),
    ("day05", "Day 5 · DialogueEngine 与 TurnPlanner",
     r"day05\05【电商小二】DialogueEngine 与 TurnPlanner的LLM调用.md"),
    ("day06", "Day 6 · 防幻觉校验与对象消息处理",
     r"day06\06【电商小二】防幻觉校验与对象消息处理.md"),
    ("day07", "Day 7 · TaskHandler 与 CommandProcessor",
     r"day07\07【电商小二】TaskHandler与CommandProcessor.md"),
    ("day08", "Day 8 · Action 实现",
     r"day01\课堂笔记\08【电商小二】Action实现.md"),
    ("day09", "Day 9 · FlowExecutor 执行器",
     r"day01\课堂笔记\09【电商小二】FlowExecutor执行器.md"),
    ("day10", "Day 10 · 信息检索与闲聊",
     r"day01\课堂笔记\10【电商小二】信息检索与闲聊.md"),
    ("day11", "Day 11 · 历史对话实现",
     r"day01\课堂笔记\11【电商小二】历史对话实现.md"),
]

# ============ 源码按天归类 ============
CODE_GROUPS = {
    "day01": [
        ("main.py", "应用入口：装配并启动 uvicorn 服务"),
        ("api/app.py", "创建 FastAPI 应用实例、挂载路由、注册生命周期事件（初始化/关闭数据库引擎）"),
        ("api/routers/chat_router.py", "对话路由：POST /api/chat 接收消息，GET /api/chat/history 查历史；负责 API 模型与领域模型互转"),
        ("api/routers/dependencies.py", "依赖注入：对外提供 engine 与 service 实例"),
        ("api/schemas.py", "API 层出入参模型（ChatRequest / ChatResponse 等）"),
        ("conf/config.py", "全局配置：从 .env 读取数据库、LLM、服务地址等配置"),
    ],
    "day02": [
        ("domain/messages.py", "消息模型：UserMessage / BotMessage / FocusedObject / ProcessResult"),
        ("domain/state.py", "对话状态聚合根 DialogueState，内含 Session 与 Turn 两层结构"),
        ("domain/contexts.py", "任务上下文：TaskContext 与 5 种 SystemContext 子类（带 discriminator 联合类型）"),
    ],
    "day03": [
        ("task/flow/links.py", "步骤跳转关系：StaticLink / ConditionalLink / FallbackLink"),
        ("task/flow/steps.py", "流程步骤类型：start / action / collect / end，及各自的 from_dict 解析"),
        ("task/flow/flows.py", "Flow 与 FlowsList 容器，提供 start_step / get_step_by_id / get_flow_by_id"),
        ("task/flow/loader.py", "流程加载器：从 YAML 读取并组装成 FlowsList"),
        ("task/command/models.py", "命令模型：start_flow / set_slots / cancel_flow / resume_flow 及多态解析"),
        ("flow_config/user_flows.yml", "业务流程定义：查订单、查物流、退款申请、相似商品推荐、转人工"),
        ("flow_config/system_flows.yml", "系统流程定义：开场、打断、取消、恢复、收集槽位等过场白"),
    ],
    "day04": [
        ("service/dialogue_service.py", "Service 层：编排 load → engine 处理 → save 三步"),
        ("repository/dialogue_state_repository.py", "Repository 层：读写 dialogue_states 表，用 upsert 保存状态"),
        ("infrastructure/database.py", "异步数据库引擎与 session 工厂"),
        ("infrastructure/llm.py", "LLM 客户端：统一成 BaseChatModel 接口"),
        ("infrastructure/http_client.py", "调用电商中台 API 的 HTTP 客户端"),
        ("models/base.py", "SQLAlchemy 声明式基类"),
        ("models/dialogue_state.py", "dialogue_states 表的 ORM 映射"),
    ],
    "day05": [
        ("engine/dialogue_engine.py", "对话引擎：只调度不干活，串联会话准备、turn 开启、轨道分发、turn 提交"),
        ("plan/turn_planner.py", "TurnPlanner：调 LLM 把用户消息解析成 TurnPlan（意图规划）"),
        ("plan/models.py", "TurnPlan 数据模型：task / knowledge / chitchat 三条轨道 + 澄清原因码"),
        ("prompts/history_builder.py", "HistoryBuilder：把对话历史与消息对象渲染成提示词文本"),
        ("prompts/loader.py", "load_prompt：按名字加载 jinja2 提示词模板"),
        ("prompts/jinja2/turn_plan.jinja2", "意图规划提示词模板"),
    ],
    "day06": [
        ("plan/turn_validator.py", "TurnPlanValidator：防幻觉校验，只判断不回复，输出原因码"),
        ("clarify/responder.py", "ClarifyResponder：规则基础话术保底 + LLM 润色，把原因码变成自然追问"),
        ("engine/builder.py", "组件装配工厂：把各专员组装成引擎单例"),
        ("knowledge/intents.py", "知识意图注册表 KnowledgeIntent / KNOWLEDGE_INTENTS"),
        ("prompts/jinja2/clarify_respond.jinja2", "澄清润色提示词模板"),
    ],
    "day07": [
        ("task/command/processor.py", "CommandProcessor：把四种命令真正应用到 DialogueState（start / set_slots / cancel / resume）"),
    ],
    "day08": [
        ("task/action/base.py", "Action 基类 + ActionResult（动作产物：messages 回复 / slot_updates 写槽）"),
        ("task/action/registry.py", "ActionRegistry：name -> Action 实例 的注册表（字符串翻译成对象）"),
        ("task/action/runner.py", "ActionRunner + ActionCall：一次动作调用（查表→调用→返回）"),
        ("task/action/builder.py", "action 装配：内置手动注册 + custom 包自动发现（开闭原则）"),
        ("task/action/builtin/action_listen.py", "ActionListen：哨兵，表示'该等用户输入了'"),
        ("task/action/builtin/action_response.py", "ActionResponse：static / rephrase / generate 三模式回复"),
        ("task/action/custom/shared.py", "调电商接口工具：fetch_order / fetch_logistics / fetch_product / 摘要"),
        ("task/action/custom/lookup_order_status.py", "查订单状态 action：调接口写 order_status/order_summary 槽"),
        ("task/action/custom/lookup_logistics.py", "查物流 action：写 logistics_* 槽"),
        ("task/action/custom/recommend_similar_products.py", "推荐相似商品 action（占位，直接产出回复）"),
    ],
    "day09": [
        ("task/flow/executor.py", "FlowExecutor：两层循环推进流程、执行 action、action_listen 哨兵退出"),
        ("task/handler.py", "TaskHandler：两阶段协调（CommandProcessor 改状态 + FlowExecutor 推进产出回复）"),
    ],
    "day10": [
        ("chitchat/handler.py", "闲聊轨道入口：把消息+历史交给 responder（只调度）"),
        ("chitchat/responder.py", "闲聊 responder：调 LLM 自然回一句"),
        ("knowledge/providers.py", "知识提供者：Product/Order API×2 + FAQ/RAG 占位（统一 retrieve 接口）"),
        ("knowledge/registry.py", "KnowledgeProviderRegistry：provider_id -> 实例"),
        ("knowledge/responder.py", "知识回复生成器：chunks 拼上下文 + LLM 作答"),
        ("knowledge/handler.py", "KnowledgeHandler：意图→provider_ids→检索→作答"),
        ("prompts/jinja2/chitchat_respond.jinja2", "闲聊提示词模板"),
        ("prompts/jinja2/knowledge_respond.jinja2", "知识作答提示词模板"),
    ],
    "day11": [
        ("api/routers/chat_router.py", "历史接口 GET /api/chat/history 改为真实数据（改动点见 Day1/4/5 同文件）"),
        ("service/dialogue_service.py", "新增 load_chat_history：把 sessions.turns 展开成带 session_id 的平铺消息"),
        ("prompts/history_builder.py", "新增 render_user_message / render_bot_message：领域消息→接口历史消息"),
        ("api/schemas.py", "HistoryMessage 增加 session_id 字段"),
    ],
}

LEXER_MAP = {
    "python": "python", "py": "python",
    "yaml": "yaml", "yml": "yaml",
    "jinja2": "jinja", "jinja": "jinja",
    "json": "json",
    "bash": "bash", "shell": "bash", "sh": "bash",
    "sql": "sql", "http": "http",
    "markdown": "markdown", "md": "markdown",
    "text": "text", "plaintext": "text", "": "text",
}

# ---------------- 图片本地化 ----------------
img_map: dict = {}
img_counter = 0


def copy_image(src: Path):
    """把讲义引用的图片复制到输出目录，重命名为安全文件名，返回相对引用路径。"""
    global img_counter
    try:
        src = src.resolve()
    except Exception:
        return None
    if not src.exists():
        return None
    key = str(src).lower()
    if key in img_map:
        return img_map[key]
    img_counter += 1
    ext = src.suffix.lower() or ".png"
    new_name = f"img_{img_counter:04d}{ext}"
    IMG_OUT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, IMG_OUT / new_name)
    img_map[key] = f"images/{new_name}"
    return img_map[key]


def localize_images(md_text: str, doc_dir: Path) -> str:
    def repl_md(m):
        alt, path = m.group(1), m.group(2).strip()
        new = copy_image(doc_dir / path)
        return f"![{alt}]({new})" if new else f"`[图片缺失: {path}]`"
    def repl_html(m):
        path = m.group(1).strip()
        new = copy_image(doc_dir / path)
        return f'<img src="{new}" alt="">' if new else f"<em>[图片缺失: {path}]</em>"

    md_text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", repl_md, md_text)
    md_text = re.sub(r'<img\s+src="([^"]+)"[^>]*>', repl_html, md_text)
    return md_text


# ---------------- 代码高亮 ----------------
def render_code(code_text: str, lang: str) -> str:
    lexer_name = LEXER_MAP.get((lang or "").strip().lower())
    try:
        if lexer_name:
            lexer = get_lexer_by_name(lexer_name, stripall=False)
        else:
            from pygments.lexers import guess_lexer
            lexer = guess_lexer(code_text)
    except Exception:
        lexer = get_lexer_by_name("text", stripall=False)
    code_html = highlight(
        code_text, lexer,
        HtmlFormatter(linenos="table", cssclass="codehilite", style="monokai"),
    )
    # 每个代码块（讲义代码 + 源码）都包一层相对定位容器，右上角挂"复制"按钮
    return (
        f'<div class="code-wrap">{code_html}'
        f'<button class="copy" type="button">复制</button></div>'
    )


CODE_RE = re.compile(
    r'<pre><code(?:\s+class="language-([^"]*)")?>(.*?)</code></pre>', re.DOTALL
)


def postprocess_code(html_text: str) -> str:
    def repl(m):
        lang = m.group(1) or ""
        raw = html.unescape(m.group(2))
        return render_code(raw, lang)
    return CODE_RE.sub(repl, html_text)


# ---------------- 讲义渲染 ----------------
def make_slug(title: str, idx: int) -> str:
    t = re.sub(r"[`*\[\]()#{}|\\/\"'<>:：，。、？?！!·\s]+", "-", title)
    t = re.sub(r"-+", "-", t).strip("-")
    return f"{t}-{idx}" if t else f"sec-{idx}"


def inject_anchors(md_text: str):
    """给标题行注入 anchor id，同时返回目录结构。"""
    lines = md_text.split("\n")
    out, toc, in_code, idx = [], [], False, 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            out.append(line)
            continue
        if in_code:
            out.append(line)
            continue
        m = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if m:
            level, title = len(m.group(1)), m.group(2).strip()
            if level >= 2:  # h1 是讲义大标题，不进目录
                idx += 1
                slug = make_slug(title, idx)
                toc.append((level, title, slug))
                out.append(f"{stripped} {{: #{slug} }}")
                continue
        out.append(line)
    return "\n".join(out), toc


def render_doc(md_text: str, doc_dir: Path):
    md_text = localize_images(md_text, doc_dir)
    md_text, toc = inject_anchors(md_text)
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "attr_list", "sane_lists", "md_in_html"]
    )
    body = md.convert(md_text)
    return postprocess_code(body), toc


# ---------------- 源码 ----------------
def safe_id(path: str) -> str:
    return "code-" + re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", path).strip("-")


# 记录已渲染过的源码 section（同路径只渲染一次，其余 day 分组做导航跳转）
_rendered_source_ids: dict = {}


def render_source(rel_path: str, desc: str):
    full = PROJ / rel_path
    if not full.exists():
        return None
    # 若存在逐行教学注释版（annotated/<同路径>），优先展示它
    annotated = OUT / "annotated" / rel_path
    if annotated.exists():
        text = annotated.read_text(encoding="utf-8", errors="replace")
        note = "（含逐行教学注释）"
    else:
        text = full.read_text(encoding="utf-8", errors="replace")
        note = ""
    ext = full.suffix.lower().lstrip(".")
    sid = safe_id(rel_path)
    if sid in _rendered_source_ids:
        # 已在别的 day 分组渲染过：返回仅导航引用，不再重复生成 section
        return {
            "id": sid,
            "dup": True,
            "path": rel_path,
            "desc": desc + note,
            "lines": _rendered_source_ids[sid],
            "body": "",
        }
    lines = len(text.splitlines())
    _rendered_source_ids[sid] = lines
    return {
        "id": sid,
        "path": rel_path,
        "desc": desc + note,
        "lines": lines,
        "body": render_code(text, ext),
    }


# ---------------- 组装 ----------------
CSS = """*{box-sizing:border-box}
html,body{margin:0;padding:0;height:100%}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;color:#e6edf3;background:#0b0f14;line-height:1.75;font-size:15px}
code,pre,.mono{font-family:"JetBrains Mono",Consolas,"Courier New",monospace}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:#2d333b;border-radius:6px;border:2px solid #0b0f14}
::-webkit-scrollbar-thumb:hover{background:#3d444d}
.app{display:flex;height:100vh}
.sidebar{width:300px;flex:0 0 300px;border-right:1px solid #21262d;background:linear-gradient(180deg,#11161d 0%,#0d1117 100%);display:flex;flex-direction:column;overflow:hidden}
.brand{padding:18px 20px 14px;border-bottom:1px solid #21262d;background:radial-gradient(120% 140% at 0% 0%,rgba(56,139,253,.16),transparent 60%)}
.brand h1{margin:0;font-size:17px;font-weight:700;letter-spacing:.02em;background:linear-gradient(90deg,#58a6ff,#bc8cff);-webkit-background-clip:text;background-clip:text;color:transparent}
.brand p{margin:5px 0 0;font-size:12px;color:#8b949e}
.search{padding:12px 14px;border-bottom:1px solid #21262d}
.search input{width:100%;padding:8px 12px;border:1px solid #30363d;border-radius:8px;font-size:13px;outline:none;background:#0d1117;color:#e6edf3;transition:border-color .15s,box-shadow .15s}
.search input::placeholder{color:#6e7681}
.search input:focus{border-color:#58a6ff;box-shadow:0 0 0 3px rgba(88,166,255,.15)}
nav{flex:1;overflow-y:auto;padding:6px 0 40px}
.day{margin-bottom:1px}
.day-head{display:flex;align-items:center;gap:9px;padding:9px 18px;cursor:pointer;font-size:13.5px;font-weight:600;color:#e6edf3;user-select:none;border-radius:6px;margin:0 6px}
.day-head:hover{background:#1c2128}
.day-head .caret{font-size:10px;color:#8b949e;transition:transform .15s;width:10px}
.day.collapsed .caret{transform:rotate(-90deg)}
.day.collapsed .day-body{display:none}
.day-body{padding-bottom:6px}
.sub-head{padding:6px 20px 3px 34px;font-size:10.5px;font-weight:700;color:#57606a;letter-spacing:.14em;text-transform:uppercase}
.nav-item{display:block;padding:5px 16px 5px 34px;font-size:13px;color:#8b949e;text-decoration:none;border-left:2px solid transparent;cursor:pointer;line-height:1.5;border-radius:0 6px 6px 0}
.nav-item:hover{background:#1c2128;color:#e6edf3}
.nav-item.lv3{padding-left:50px;font-size:12.5px;color:#7d8590}
.nav-item.active{background:linear-gradient(90deg,rgba(88,166,255,.16),transparent);border-left-color:#58a6ff;color:#58a6ff;font-weight:600}
.nav-item.file{display:flex;justify-content:space-between;gap:6px}
.nav-item.file .ln{font-size:10.5px;color:#57606a;font-family:monospace;margin-top:1px}
main{flex:1;overflow-y:auto;scroll-behavior:smooth;background:radial-gradient(1200px 500px at 85% -10%,rgba(88,166,255,.07),transparent 60%)}
.section{display:none;padding:36px 52px 140px;max-width:1100px}
.section.active{display:block}
.doc-title{font-size:26px;font-weight:700;margin:0 0 6px;padding-bottom:14px;border-bottom:1px solid #21262d;background:linear-gradient(90deg,#f0f6fc,#79c0ff);-webkit-background-clip:text;background-clip:text;color:transparent}
.doc-meta{font-size:12.5px;color:#6e7681;margin:10px 0 28px}
.src-head{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;padding-bottom:12px;border-bottom:1px solid #21262d;margin-bottom:6px}
.src-head h2{margin:0;font-size:20px;font-weight:600;font-family:monospace;color:#79c0ff;word-break:break-all}
.src-head .lines{font-size:12px;color:#6e7681}
.src-desc{margin:14px 0 18px;padding:11px 16px;background:linear-gradient(90deg,rgba(56,139,253,.10),transparent);border-left:3px solid #388bfd;border-radius:0 8px 8px 0;font-size:13.5px;color:#c9d1d9}
h1{font-size:24px;margin:36px 0 14px;font-weight:700;color:#f0f6fc}
h2{font-size:20px;margin:32px 0 12px;font-weight:700;color:#e6edf3;padding-bottom:8px;border-bottom:1px solid #21262d}
h3{font-size:16.5px;margin:26px 0 10px;font-weight:600;color:#e6edf3}
h4{font-size:15px;margin:20px 0 8px;font-weight:600;color:#d2d8df}
p{margin:11px 0}
ul,ol{padding-left:24px;margin:11px 0}
li{margin:5px 0}
a{color:#58a6ff;text-decoration:none}
a:hover{text-decoration:underline}
blockquote{margin:14px 0;padding:3px 16px;border-left:4px solid #30363d;color:#8b949e;background:#0d1117;border-radius:0 8px 8px 0}
table{border-collapse:collapse;margin:16px 0;font-size:13.5px;display:block;overflow-x:auto;max-width:100%}
th,td{border:1px solid #30363d;padding:7px 12px;text-align:left}
th{background:#161b22;font-weight:600;color:#c9d1d9}
tr:nth-child(even) td{background:#0d1117}
img{max-width:100%;border-radius:8px;border:1px solid #30363d;margin:12px 0;display:block}
hr{border:0;border-top:1px solid #21262d;margin:28px 0}
:not(pre)>code{background:#1c2128;padding:.18em .45em;border-radius:5px;font-size:.88em;color:#79c0ff}
strong{color:#f0f6fc}
.code-wrap{position:relative;margin:14px 0;border-radius:10px;box-shadow:0 2px 12px rgba(0,0,0,.35)}
.codehilite{background:#11151c;border-radius:10px;overflow:hidden;border:1px solid #21262d}
.codehilite pre{margin:0;padding:13px 0;font-size:13px;line-height:1.66;overflow-x:auto;background:transparent!important}
.codehilite table{border:0;margin:0;display:table;width:100%;border-collapse:collapse}
.codehilite td{border:0;padding:0}
.codehilite .linenos{width:1%;min-width:46px;text-align:right;color:#484f58;user-select:none;padding:13px 10px 13px 13px!important;background:#0c1016!important;border-right:1px solid #1f242c!important;font-size:12.5px;vertical-align:top}
.codehilite .code{padding:13px 15px!important}
.codehilite .lineno{display:block}
.code-wrap .copy{position:absolute;top:9px;right:11px;opacity:0;transition:opacity .15s,background .15s;background:#1c2128;color:#8b949e;border:1px solid #30363d;border-radius:6px;padding:4px 11px;font-size:11.5px;cursor:pointer;z-index:2}
.code-wrap:hover .copy{opacity:1}
.copy:hover{background:#272c35;color:#e6edf3;border-color:#484f58}
.arch-title{font-size:13px;font-weight:700;color:#58a6ff;margin:20px 0 9px;letter-spacing:.06em}
.arch-row{display:flex;flex-wrap:wrap;gap:8px;align-items:stretch}
.arch-col{flex-direction:column;align-items:flex-start;margin:4px 0 2px 22px;border-left:1px dashed #30363d;padding-left:12px}
.arch-down{text-align:center;color:#484f58;font-size:11px;line-height:13px;padding-left:60px;align-self:center}
.node{background:#11161d;border:1px solid #30363d;border-left:4px solid #388bfd;border-radius:8px;padding:6px 11px;min-width:118px;max-width:240px;box-shadow:0 1px 4px rgba(0,0,0,.25)}
.node .fn{font-family:Consolas,monospace;font-size:12px;font-weight:600;color:#79c0ff;word-break:break-all}
.node .cm{font-size:11px;color:#8b949e;margin-top:2px;line-height:1.5}
.node .sub{font-family:Consolas,monospace;font-size:10px;color:#57606a;margin-top:1px}
.node.teal{border-left-color:#3fb950}.node.green{border-left-color:#3fb950}
.node.pur{border-left-color:#bc8cff}.node.orange{border-left-color:#d29922}
.node.gray{border-left-color:#57606a}
.node:hover{transform:translateY(-1px);box-shadow:0 4px 14px rgba(88,166,255,.12);transition:.15s}
.arch-arrow{text-align:center;font-size:12px;color:#484f58;padding-left:64px}
.empty{padding:40px;color:#57606a;text-align:center}
@media(max-width:900px){.sidebar{width:230px;flex-basis:230px}.section{padding:24px 20px 100px}}
"""

JS = """
(function(){
  var sections=document.querySelectorAll('.section');
  var items=document.querySelectorAll('.nav-item');
  function show(id){
    sections.forEach(function(s){s.classList.toggle('active',s.id===id)});
    document.querySelector('main').scrollTop=0;
    items.forEach(function(i){i.classList.toggle('active',i.dataset.target===id)});
    try{location.hash=id}catch(e){}
  }
  function go(id,anchor){
    show(id);
    if(anchor){
      var el=document.getElementById(anchor);
      if(el) setTimeout(function(){el.scrollIntoView({behavior:'smooth',block:'start'})},30);
    }
  }
  items.forEach(function(it){
    it.addEventListener('click',function(){
      go(it.dataset.target,it.dataset.anchor||'');
    });
  });
  document.querySelectorAll('.day-head').forEach(function(h){
    h.addEventListener('click',function(){h.parentElement.classList.toggle('collapsed')});
  });
  var search=document.getElementById('search');
  search.addEventListener('input',function(){
    var q=search.value.trim().toLowerCase();
    document.querySelectorAll('.day').forEach(function(day){
      var hit=0;
      day.querySelectorAll('.nav-item').forEach(function(it){
        var ok=!q||it.textContent.toLowerCase().indexOf(q)>=0;
        it.style.display=ok?'':'none';
        if(ok)hit++;
      });
      day.style.display=hit?'':'none';
      if(q&&hit)day.classList.remove('collapsed');
    });
  });
  document.querySelectorAll('.copy').forEach(function(b){
    b.addEventListener('click',function(){
      var wrap=b.closest('.code-wrap');
      // 注意：linenos=table 结构里行号与代码是两个 <td>，行号列也在 <pre> 里，
      // 必须取代码列 td.code 内的 pre，否则复制到的是行号
      var pre=wrap?wrap.querySelector('.codehilite td.code pre'):null;
      var txt=pre?pre.innerText.replace(/^\\s*\\d+\\s*/gm,''):'';
      function ok(){b.textContent='已复制';setTimeout(function(){b.textContent='复制'},1200);}
      function fallback(){
        // clipboard API 在 file:// 或非 https 下不可用，退回 execCommand 复制
        var ta=document.createElement('textarea');
        ta.value=txt;ta.setAttribute('readonly','');
        ta.style.position='fixed';ta.style.top='0';ta.style.opacity='0';
        document.body.appendChild(ta);ta.select();
        try{document.execCommand('copy');ok();}catch(e){b.textContent='复制失败';}
        document.body.removeChild(ta);
      }
      if(navigator.clipboard&&window.isSecureContext){
        navigator.clipboard.writeText(txt).then(ok).catch(fallback);
      }else{fallback();}
    });
  });
  var first=document.querySelector('.nav-item');
  if(first)go(first.dataset.target,'');
})();
"""


ARCH_HTML = r'''<section class="section" id="arch">
<h1 class="doc-title">流程架构总览 · 从请求进入到回复离开</h1>
<p class="doc-meta">节点 = 项目文件名，旁注为该文件职责；▼ 表示数据/调用流向。建议先看 ④ 引擎调度，再对照各 day 源码。</p>

<div class="arch-title">① 入口层</div>
<div class="arch-row">
  <div class="node orange"><div class="fn">main.py</div><div class="cm">启动入口：python main.py 拉起 uvicorn</div></div>
  <div class="arch-down">▼ 按 "api.app:app" 定位</div>
  <div class="node"><div class="fn">api/app.py</div><div class="cm">FastAPI 实例 + lifespan：启动时 init DB 连接池与 HTTP 客户端，关闭时释放</div></div>
</div>

<div class="arch-title">② API / DI 层</div>
<div class="arch-row">
  <div class="node"><div class="fn">api/routers/chat_router.py</div><div class="cm">HTTP 入口：POST /api/chat 对话 · GET /api/chat/history 历史（API模型↔领域模型互转）</div></div>
  <div class="arch-down">▼</div>
  <div class="node teal"><div class="fn">api/routers/dependencies.py</div><div class="cm">FastAPI 依赖注入：session → repository → service</div></div>
</div>

<div class="arch-title">③ Service 层</div>
<div class="arch-row">
  <div class="node teal"><div class="fn">service/dialogue_service.py</div><div class="cm">编排：load_state → engine.process_message → save_state；另提供 load_chat_history</div></div>
</div>
<div class="arch-arrow">▼ load/save 状态　　　▼ 推理</div>
<div class="arch-row">
  <div class="node green"><div class="fn">repository/dialogue_state_repository.py</div><div class="cm">按 sender_id 读库 / 整棵 DialogueState 写库（upsert）</div></div>
  <div class="node gray"><div class="fn">engine/dialogue_engine.py</div><div class="cm">调度中枢（见 ④）</div></div>
</div>

<div class="arch-title">④ 引擎调度层（核心）</div>
<div class="arch-row"><div class="node gray"><div class="fn">engine/dialogue_engine.py</div><div class="cm">文本消息 → LLM 规划；对象消息(点卡片) → 记聚焦对象 + 尝试填槽</div></div></div>
<div class="arch-col">
  <div class="arch-row">
    <div class="node"><div class="fn">plan/turn_planner.py</div><div class="cm">调 LLM 把用户话解析成 TurnPlan（task/knowledge/chitchat 三轨道）</div></div>
    <div class="arch-down">▼ 计划先过安检</div>
    <div class="node"><div class="fn">plan/turn_validator.py</div><div class="cm">防幻觉校验：轨道数 / task 四重 / knowledge 意图+聚焦对象</div></div>
    <div class="arch-down">✗ 不过 →</div>
    <div class="node pur"><div class="fn">clarify/responder.py</div><div class="cm">澄清：原因码 → 基础话术 → LLM 润色成追问</div></div>
  </div>

  <div class="arch-row"><div class="node gray"><div class="fn">task/handler.py</div><div class="cm">task 轨道两阶段协调者（改状态 → 推进流程）</div></div></div>
  <div class="arch-col">
    <div class="arch-row">
      <div class="node"><div class="fn">task/command/processor.py</div><div class="cm">阶段① 命令应用到 state：start_flow/set_slots/cancel/resume（挂起栈+系统过场）</div></div>
      <div class="arch-down">▼</div>
      <div class="node"><div class="fn">task/flow/executor.py</div><div class="cm">阶段② 按 YAML 推进 step；遇 action 交 Runner，遇 action_listen 哨兵退出等输入</div></div>
      <div class="arch-down">▼</div>
      <div class="node"><div class="fn">task/action/runner.py</div><div class="cm">ActionCall → 注册表查实例 → 执行 → ActionResult(messages/slot_updates)</div></div>
      <div class="arch-down">▼ 名字→实例</div>
      <div class="node teal"><div class="fn">task/action/builder.py · registry.py</div><div class="cm">内置手动注册 + custom 包自动发现；name→Action 实例</div></div>
    </div>
    <div class="arch-row">
      <div class="node green"><div class="fn">builtin/action_response.py · action_listen.py</div><div class="cm">回复（static/rephrase/generate 三模式）· 哨兵（该等用户输入了）</div></div>
      <div class="node green"><div class="fn">custom/lookup_order_status.py · lookup_logistics.py · recommend_similar_products.py</div><div class="cm">查订单/查物流/推荐：读槽→调接口→写槽或直接回复</div></div>
      <div class="arch-down">▼</div>
      <div class="node"><div class="fn">custom/shared.py</div><div class="cm">fetch_order/logistics/product → infrastructure/http_client.py → 电商中台 API</div></div>
    </div>
  </div>

  <div class="arch-row">
    <div class="node gray"><div class="fn">knowledge/handler.py</div><div class="cm">knowledge 轨道：意图 → provider_ids → 检索 chunks → 作答</div></div>
    <div class="arch-down">▼</div>
    <div class="node"><div class="fn">knowledge/providers.py</div><div class="cm">Product/Order（asyncio.gather 并发查订单+物流）/FAQ/RAG；统一 retrieve(state)→chunks</div></div>
    <div class="arch-down">▼</div>
    <div class="node"><div class="fn">knowledge/responder.py</div><div class="cm">chunks 拼上下文 + LLM 按 knowledge_respond 模板作答</div></div>
  </div>

  <div class="arch-row">
    <div class="node gray"><div class="fn">chitchat/handler.py → responder.py</div><div class="cm">闲聊轨道：用户话+历史 → LLM 自然回一句（chitchat_respond 模板）</div></div>
  </div>
</div>

<div class="arch-title">⑤ 领域层（贯穿全程的数据模型）</div>
<div class="arch-row">
  <div class="node"><div class="fn">domain/state.py</div><div class="cm">DialogueState 聚合根：Session/Turn/active_task/paused_tasks/系统过场/聚焦对象</div></div>
  <div class="node"><div class="fn">domain/messages.py</div><div class="cm">UserMessage / BotMessage / FocusedObject / ProcessResult</div></div>
  <div class="node"><div class="fn">domain/contexts.py</div><div class="cm">TaskContext + 5 种 SystemContext（判别联合，持久化往返不丢子类字段）</div></div>
</div>

<div class="arch-title">⑥ 基础设施层</div>
<div class="arch-row">
  <div class="node"><div class="fn">models/dialogue_state.py</div><div class="cm">dialogue_states 表 ORM 映射（JSON 列存整棵状态）</div></div>
  <div class="arch-down">▼</div>
  <div class="node"><div class="fn">infrastructure/database.py</div><div class="cm">异步引擎 + session 工厂（连接池，lifespan 启停）</div></div>
  <div class="node orange"><div class="fn">infrastructure/llm.py</div><div class="cm">LLM 统一客户端（init_chat_model→BaseChatModel），planner 与各 responder 复用</div></div>
  <div class="node orange"><div class="fn">infrastructure/http_client.py</div><div class="cm">电商中台 HTTP 客户端（连接池），custom action 与 API provider 复用</div></div>
</div>

<div class="arch-title">⑦ 配置与提示词</div>
<div class="arch-row">
  <div class="node"><div class="fn">flow_config/user_flows.yml · system_flows.yml</div><div class="cm">业务流程 + 系统过场定义，由 task/flow/loader.py 载成 FlowsList</div></div>
  <div class="node"><div class="fn">prompts/jinja2/*.jinja2</div><div class="cm">turn_plan 意图规划 · clarify_respond 澄清润色 · chitchat_respond 闲聊 · knowledge_respond 知识作答</div></div>
  <div class="node"><div class="fn">conf/config.py</div><div class="cm">.env 全局配置：LLM / 数据库 / 电商中台地址 / 服务端口</div></div>
</div>
</section>
'''


def build():
    OUT.mkdir(parents=True, exist_ok=True)

    doc_sections, nav_days, src_sections = [], [], []

    for key, title, rel in DOCS:
        doc_path = DOC_BASE / rel
        text = doc_path.read_text(encoding="utf-8", errors="replace")
        body, toc = render_doc(text, doc_path.parent)
        sid = f"doc-{key}"
        doc_sections.append(
            f'<section class="section" id="{sid}">'
            f'<h1 class="doc-title">{html.escape(title)}</h1>'
            f'<p class="doc-meta">来源：{html.escape(rel)}</p>{body}</section>'
        )

        # 源码
        files = []
        for rel_path, desc in CODE_GROUPS.get(key, []):
            src = render_source(rel_path, desc)
            if not src:
                continue
            # 同一文件在多个 day 被引用时只渲染一次（dup），其余仅作导航跳转
            if not src.get("dup"):
                src_sections.append(
                    f'<section class="section" id="{src["id"]}">'
                    f'<div class="src-head"><h2>{html.escape(src["path"])}</h2>'
                    f'<span class="lines">{src["lines"]} 行</span></div>'
                    f'<p class="src-desc">{html.escape(src["desc"])}</p>'
                    f'{src["body"]}</section>'
                )
            files.append(
                f'<a class="nav-item file" data-target="{src["id"]}">'
                f'<span>{html.escape(Path(rel_path).name)}</span>'
                f'<span class="ln">{src["lines"]}</span></a>'
            )

        doc_nav = f'<a class="nav-item" data-target="{sid}">讲义全文</a>'
        toc_nav = "".join(
            f'<a class="nav-item {"lv3" if lv == 3 else ""}" data-target="{sid}" '
            f'data-anchor="{slug}">{html.escape(t)}</a>'
            for lv, t, slug in toc
        )
        file_nav = "".join(files)
        nav_days.append(
            f'<div class="day"><div class="day-head"><span class="caret">▼</span>'
            f'<span>{html.escape(title)}</span></div><div class="day-body">'
            f'<div class="sub-head">讲义章节</div>{doc_nav}{toc_nav}'
            f'<div class="sub-head">对应源码</div>{file_nav}</div></div>'
        )

    pyg_css = HtmlFormatter(style="monokai").get_style_defs(".codehilite")

    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>电商小二 · Day1-Day11 学习指南</title>
<style>{CSS}</style>
<style>{pyg_css}</style>
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="brand">
      <h1>电商小二 · 学习指南</h1>
      <p>Day 1 - Day 11 讲义 + 项目源码逐行对照</p>
    </div>
    <div class="search"><input id="search" placeholder="搜索章节或文件名..."></div>
    <nav id="nav"><a class="nav-item active" data-target="arch">🏛 流程架构总览</a><div class="sub-head" style="padding-top:6px">按天学习</div>{''.join(nav_days)}</nav>
  </aside>
  <main>
    {ARCH_HTML}
    {''.join(doc_sections)}
    {''.join(src_sections)}
  </main>
</div>
<script>{JS}</script>
</body>
</html>"""

    out_file = OUT / "index.html"
    out_file.write_text(page, encoding="utf-8")

    # 清理不再被引用的旧图片（避免上次生成的孤儿文件残留）
    used_names = {Path(v).name for v in img_map.values()}
    for old in IMG_OUT.glob("*"):
        if old.is_file() and old.name not in used_names:
            try:
                old.unlink()
            except OSError:
                pass

    print(f"生成完成: {out_file}")
    print(f"  讲义  : {len(doc_sections)} 篇")
    print(f"  源码  : {len(src_sections)} 个文件")
    print(f"  图片  : {len(img_map)} 张 -> {IMG_OUT}")
    print(f"  体积  : {out_file.stat().st_size / 1024 / 1024:.2f} MB (HTML)")


if __name__ == "__main__":
    build()
