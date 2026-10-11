# -*- coding: utf-8 -*-
"""
开发环境一键启动器
=====================================================================
按正确顺序拉起整套服务：
    MySQL(3307) → 商城中台(18081) → AI 客服后端(18082) → 前端 dev(5173)
最后打一张状态表告诉你缺什么。

用法：
    uv run python tools/dev_up.py              # 启动（已在跑的会自动跳过）
    uv run python tools/dev_up.py --init-db    # 先建库建表，再启动
    uv run python tools/dev_up.py --status     # 只看状态，不动任何进程
    uv run python tools/dev_up.py --stop       # 停掉后端与前端

为什么要有这个脚本：
    本机历史上最常见的故障是「前端报请求失败」= 18082 后端没起来。
    但现在 MySQL 与商城中台也都是可缺项：**三缺一就会在页面上看到红条**
    （加载历史消息失败 / 加载订单列表失败 / 请求失败），所以四件事统一收口。

端口约定：
    3307 MySQL（3306 被本机另一个项目的 Docker MySQL 占着，见 MYSQL_PORT 注释）
    18081 商城中台 · 18082 AI 客服后端 · 5173 前端 dev
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

# 仓库根目录（本文件在 tools/ 下，往上一层就是根）
ROOT = Path(__file__).resolve().parents[1]
# `uv run python tools/dev_up.py` 时，Python 只把 tools/ 放进 sys.path，
# 仓库根的顶层包（models / conf / infrastructure）会 import 不到 —— 手动补上。
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# 前端工程目录
FE_DIR = ROOT / "external" / "customer-service-frontend"
# 临时日志（仅非 Windows 用；Windows 走独立控制台窗口，日志直接看窗口）
LOG_DIR = ROOT / ".dev-logs"

IS_WIN = os.name == "nt"

# 本机环境里 npm / uv 都在 PATH 上；这两个端口不要改，前端 vite 代理写死了 18082
BACKEND_PORT = 18082
FRONTEND_PORT = 5173
# 中台（商城 API）端口：前端 vite 把 /commerce 转发到这里，写死在 vite.config.js
COMMERCE_PORT = 18081
# MySQL 宿主端口：本机 3306 被另一个项目的 Docker MySQL 占着，课程的
# customer-service-mysql 容器改发布到 3307（容器内依然是 3306）。
# 改这里的同时记得同步 .env 的 DATABASE_URL 与中台工程的 .env。
MYSQL_PORT = 3307
# MySQL 容器名（定义在 COMPOSE_FILE 里，脚本只在提示信息里用到）
MYSQL_CONTAINER = "customer-service-mysql"
# 中台工程目录：本仓库 external/ 下就自带一份（含 .venv），不必去课程资料目录里找。
# 换机器 / 换路径时可用环境变量 COMMERCE_DIR 覆盖。
COMMERCE_DIR = Path(os.environ.get(
    "COMMERCE_DIR", str(ROOT / "external" / "ecommerce-service-backend"),
))
# MySQL 的唯一定义处：容器名、卷、口令、宿主端口都写在这份 compose 里，
# 本脚本只负责把它 up 起来，不另抄一份参数（避免两处定义漂移）。
COMPOSE_FILE = ROOT / "external" / "docker" / "docker-compose.yml"


# ---------------------------------------------------------------- 基础工具
def say(msg: str = "") -> None:
    """安全打印：极少数控制台编码不支持中文时降级，不让脚本崩在 print 上。"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", "replace").decode("ascii", "replace"))


def rule(char: str = "=") -> None:
    say(char * 68)


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    """能不能连上该端口 —— 判断服务是否在跑的最可靠办法。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def _run_bytes(args: list[str]) -> str:
    """执行命令并按字节取回输出，再自己挑编码解码。

    注意：不要用 subprocess 的 text=True —— `uv run` 会给子进程设 PYTHONUTF8=1，
    于是 Python 用 utf-8 去解 netstat / taskkill 在中文 Windows 上的 GBK 输出，
    直接抛 UnicodeDecodeError（异常还发生在读取线程里，非常难查）。
    """
    raw = subprocess.run(args, capture_output=True).stdout or b""
    for enc in ("utf-8", "gbk", "cp936"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def pids_on_port(port: int) -> list[int]:
    """取出正在监听该端口的进程号，用于 --stop。"""
    pids: set[int] = set()
    try:
        if IS_WIN:
            out = _run_bytes(["netstat", "-ano"])
            for line in out.splitlines():
                parts = line.split()
                # 形如： TCP    127.0.0.1:5173    0.0.0.0:0    LISTENING    4300
                if len(parts) >= 5 and parts[0].upper() == "TCP" and parts[3].upper() == "LISTENING":
                    if parts[1].endswith(f":{port}") and parts[4].isdigit():
                        pids.add(int(parts[4]))
        else:
            out = _run_bytes(["lsof", "-ti", f":{port}"])
            pids.update(int(x) for x in out.split() if x.strip().isdigit())
    except Exception:
        pass
    return sorted(pids)


def kill_pid(pid: int) -> bool:
    try:
        if IS_WIN:
            # 不需要看输出，按字节收走即可（同样避开中文输出的编码坑）
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        else:
            os.kill(pid, 9)
        return True
    except Exception:
        return False


def spawn(title: str, command: str, cwd: Path) -> subprocess.Popen:
    """把服务丢进独立控制台窗口 —— 出问题能直接看得到日志，Ctrl+C 也能关。"""
    if IS_WIN:
        # /k 让窗口执行完不关闭；title 设置窗口标题便于区分
        #
        # 坑：这里必须把「整条命令行」当字符串传给 Popen（而不是 list）。
        # 传 list 时 Python 会走 list2cmdline 转义，把命令里的 " 变成 \"，
        # 而 cmd.exe 不认 \" 这种转义 —— 结果是带引号的 exe 路径（如中台工程里
        # 那个含中文的 .venv python）被当成非法程序名，窗口一闪就没了。
        # shell=False + 字符串 在 Windows 上会把命令行原样交给 CreateProcess。
        cmdline = f"cmd /k title {title} && {command}"
        return subprocess.Popen(
            cmdline,
            cwd=str(cwd),
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
    LOG_DIR.mkdir(exist_ok=True)
    log_file = open(LOG_DIR / f"{title}.log", "ab")
    return subprocess.Popen(
        command, cwd=str(cwd), shell=True,
        stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True,
    )


def wait_until_open(port: int, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_open(port):
            return True
        time.sleep(0.5)
    return False


# ------------------------------------------------------ 依赖服务：MySQL / 中台
def _run_text(args: list[str], timeout: float = 60.0) -> tuple[bool, str]:
    """跑一条命令，返回 (是否成功, 输出文本)。

    和 _run_bytes 一样按字节收结果再挑编码 —— docker 在中文 Windows 上的输出是 GBK。
    """
    try:
        proc = subprocess.run(args, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        return False, f"命令不存在：{args[0]}（Docker Desktop 没装/没在 PATH？）"
    except subprocess.TimeoutExpired:
        return False, f"命令超时：{' '.join(args)}"
    raw = (proc.stdout or b"") + (proc.stderr or b"")
    for enc in ("utf-8", "gbk", "cp936"):
        try:
            return proc.returncode == 0, raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return proc.returncode == 0, raw.decode("utf-8", "replace")


def ensure_mysql() -> bool:
    """确保 MYSQL_PORT 上有课程的 MySQL；没有就用仓库内的 compose 把它拉起来。

    容器名 / 卷 / 口令全部来自 external/docker/docker-compose.yml（就是课程 day01 那份），
    宿主端口在那份 compose 里改成了 3307 —— 本机 3306 被另一个项目的 Docker MySQL
    长期占用且其 root 口令已丢失，撞端口会让两边都连不上。

    卷 `docker_mysql_data` 里存着 customer_service（对话状态）与 commerce（订单/商品）
    两个库：只要卷在，历史数据就不会丢。**容器删了可以重建，卷千万别删。**
    """
    if port_open(MYSQL_PORT):
        return True

    say(f"  [启动] MySQL {MYSQL_PORT}（容器 {MYSQL_CONTAINER}）...")

    # 首选 compose：容器不存在就新建、存在就启动，本身幂等
    ok, out = _run_text(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d", "mysql"],
        timeout=240,
    )
    if not ok:
        # 常见情形：机器上已有一个「不是 compose 建的」同名容器 —— compose 会报名字冲突。
        # 这时直接 start 它就行（数据在卷里，不受影响）。
        started, out2 = _run_text(["docker", "start", MYSQL_CONTAINER], timeout=120)
        if not started:
            say(f"  [!]    MySQL 起不来：{(out2 or out).strip()[:200]}")
            say(f"         Docker Desktop 没启动？或手动执行： docker start {MYSQL_CONTAINER}")
            return False

    if wait_until_open(MYSQL_PORT, 120):
        say(f"  [完成] MySQL {MYSQL_PORT} 就绪")
        return True
    say(f"  [!]    MySQL {MYSQL_PORT} 120 秒内没起来 —— docker logs {MYSQL_CONTAINER}")
    return False


def ensure_commerce() -> bool:
    """确保中台（COMMERCE_PORT）在跑。

    前端右侧的订单/商品列表，以及查订单、查物流这些 action，全都经它取数；
    它不起就会看到「加载订单列表失败。」
    """
    if port_open(COMMERCE_PORT):
        return True

    if not COMMERCE_DIR.is_dir():
        say(f"  [!]    中台工程目录不存在：{COMMERCE_DIR}")
        say("         用环境变量 COMMERCE_DIR 指向 ecommerce-service-backend 再试。")
        return False

    say(f"  [启动] 中台（商城 API）{COMMERCE_PORT} ...")
    # 课程工程自带 .venv（依赖齐全），优先直接用；没有才退回 uv
    py = COMMERCE_DIR / ".venv" / "Scripts" / "python.exe"
    command = f'"{py}" main.py' if py.exists() else "uv run python main.py"
    spawn("csb-commerce-18081", command, COMMERCE_DIR)
    if wait_until_open(COMMERCE_PORT, 90):
        say(f"  [完成] 中台 {COMMERCE_PORT} 就绪")
        return True
    say(f"  [!]    中台 {COMMERCE_PORT} 90 秒内没起来 —— 看那个新开的窗口")
    return False


# ---------------------------------------------------------------- 建库建表
def init_db() -> bool:
    """连 MySQL 建库 + 建表。

    仓库里没有任何 .sql 脚本，代码里也没有 create_all，所以表必须有人来建。
    这里直接复用 ORM 的 Base.metadata，保证表结构与模型定义永远一致。
    """
    say("[init-db] 开始建库建表 ...")
    try:
        from sqlalchemy import text
        from sqlalchemy.engine import make_url
        from sqlalchemy.ext.asyncio import create_async_engine
        from models.base import Base
        # 必须 import 到具体模型类，表才会注册进 Base.metadata
        import models.dialogue_state  # noqa: F401
        from conf.config import settings
    except ImportError as exc:
        say(f"[init-db] 缺少依赖：{exc}")
        say("[init-db] 请改用 uv 运行： uv run python tools/dev_up.py --init-db")
        return False

    import asyncio

    url = make_url(settings.database_url)
    db_name = url.database

    async def _run() -> None:
        # 第一步：不指定库连上去，把库建出来（create_all 不会建库）
        server_engine = create_async_engine(url.set(database=None), echo=False)
        try:
            async with server_engine.begin() as conn:
                await conn.execute(text(
                    f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                    "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                ))
        finally:
            await server_engine.dispose()

        # 第二步：连到目标库，按 ORM 元数据建表
        db_engine = create_async_engine(settings.database_url, echo=False)
        try:
            async with db_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        finally:
            await db_engine.dispose()

    try:
        asyncio.run(_run())
    except Exception as exc:
        say(f"[init-db] 失败：{type(exc).__name__}: {str(exc)[:200]}")
        say("[init-db] MySQL 没起？先启动 3306 再重试。")
        return False

    tables = ", ".join(sorted(Base.metadata.tables.keys()))
    say(f"[init-db] 完成：库 `{db_name}`，表 {tables}")
    return True


# ---------------------------------------------------------------- 各动作
def do_status(verbose: bool = True) -> dict[str, bool]:
    state = {
        "backend": port_open(BACKEND_PORT),
        "frontend": port_open(FRONTEND_PORT),
        "commerce": port_open(COMMERCE_PORT),
        "mysql": port_open(MYSQL_PORT),
    }
    if verbose:
        say()
        rule()
        say("  当前状态")
        rule()
        _line("AI 客服后端", BACKEND_PORT, state["backend"], "对话接口 / 数字人凭证 / TTS")
        _line("前端 dev", FRONTEND_PORT, state["frontend"], "浏览器打开这个端口")
        _line("商城中台", COMMERCE_PORT, state["commerce"], "订单/商品取数；没起则右侧列表报错")
        _line("MySQL", MYSQL_PORT, state["mysql"], "对话状态持久化；没起则历史消息会报错")
        rule()
    return state


def _line(name: str, port: int, up: bool, note: str) -> None:
    flag = "运行中" if up else "未启动"
    say(f"  {pad(name, 16)}:{pad(str(port), 7)}[{pad(flag, 6)}] {note}")


def pad(text: str, width: int) -> str:
    """按终端显示宽度补空格 —— 中文占两格，直接 str.ljust 会歪。"""
    shown = sum(2 if ord(ch) > 0x2E80 else 1 for ch in text)
    return text + " " * max(0, width - shown)


def do_start() -> int:
    say()
    rule()
    say("  电商客服系统 - 开发环境启动")
    rule()

    # 前端依赖没装就直接说清楚，别等到 5173 起不来才猜
    if not (FE_DIR / "node_modules").is_dir():
        say("[!] 前端依赖未安装，请先执行：")
        say(f'    cd "{FE_DIR}" && npm install')
        return 1

    # ---- 依赖服务：先 MySQL，再中台（顺序不能反，中台起来就要连库）----
    ensure_mysql()
    ensure_commerce()

    state = do_status(verbose=False)

    # ---- 后端 ----
    if state["backend"]:
        say(f"  [跳过] AI 客服后端 {BACKEND_PORT} 已在运行")
    else:
        say(f"  [启动] AI 客服后端 {BACKEND_PORT} ...")
        spawn("csb-backend-18082", "uv run python main.py", ROOT)
        if wait_until_open(BACKEND_PORT, 60):
            say(f"  [完成] AI 客服后端 {BACKEND_PORT} 就绪")
        else:
            say(f"  [!]    AI 客服后端 {BACKEND_PORT} 60 秒内没起来 —— 看那个新开的窗口")

    # ---- 前端 ----
    if state["frontend"]:
        say(f"  [跳过] 前端 dev {FRONTEND_PORT} 已在运行")
    else:
        say(f"  [启动] 前端 dev {FRONTEND_PORT} ...")
        spawn("csb-frontend-5173", "npm run dev", FE_DIR)
        if wait_until_open(FRONTEND_PORT, 90):
            say(f"  [完成] 前端 dev {FRONTEND_PORT} 就绪")
        else:
            say(f"  [!]    前端 dev {FRONTEND_PORT} 90 秒内没起来 —— 看那个新开的窗口")

    say()
    do_status(verbose=True)

    say()
    say("  打开： http://localhost:5173")
    say("  注意： 必须用 localhost，不要写 127.0.0.1 或 IP —— 魔珐数字人 SDK 只认 localhost/HTTPS")
    if not port_open(MYSQL_PORT):
        say("  MySQL 没起：历史消息与右侧业务对象列表会报错，但数字人和语音不受影响")
    say()
    say("  停止： uv run python tools/dev_up.py --stop")
    say()
    return 0


def do_stop() -> int:
    say()
    rule()
    say("  停止开发环境")
    rule()
    stopped_any = False
    for name, port in (("AI 客服后端", BACKEND_PORT), ("前端 dev", FRONTEND_PORT)):
        pids = pids_on_port(port)
        if not pids:
            say(f"  [跳过] {name} {port} 本来就没在跑")
            continue
        for pid in pids:
            ok = kill_pid(pid)
            say(f"  [{'停止' if ok else '失败'}] {name} {port} (pid={pid})")
            stopped_any = stopped_any or ok
    time.sleep(1)
    do_status(verbose=True)
    if not stopped_any and not port_open(BACKEND_PORT) and not port_open(FRONTEND_PORT):
        say("  两个端口都已释放")
    return 0


# ---------------------------------------------------------------- 入口
def main() -> int:
    parser = argparse.ArgumentParser(
        description="电商客服系统开发环境一键启动器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  uv run python tools/dev_up.py             # 启动\n"
            "  uv run python tools/dev_up.py --init-db   # 建库建表后启动\n"
            "  uv run python tools/dev_up.py --stop      # 停止\n"
        ),
    )
    parser.add_argument("--init-db", action="store_true", help="启动前先建库建表（需要 MySQL 已运行）")
    parser.add_argument("--status", action="store_true", help="只查看端口状态，不启动任何服务")
    parser.add_argument("--stop", action="store_true", help="停止后端与前端")
    args = parser.parse_args()

    if args.status:
        do_status(verbose=True)
        return 0
    if args.stop:
        return do_stop()

    if args.init_db:
        # 建库建表前必须有 MySQL —— 这里顺手把容器拉起来，不用再让人先手动起库
        if not port_open(MYSQL_PORT) and not ensure_mysql():
            say(f"[!] MySQL {MYSQL_PORT} 起不来，无法建库建表。")
            return 1
        if not init_db():
            return 1

    return do_start()


if __name__ == "__main__":
    sys.exit(main())
