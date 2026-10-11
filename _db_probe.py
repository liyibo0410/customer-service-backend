# -*- coding: utf-8 -*-
"""临时诊断：直连 MySQL，拿到 /api/chat 500 的真实原因。"""
import asyncio
import io
import traceback

OUT = r"D:\software\PycharmProjects\customer-service-backend\_db_probe.txt"
lines = []


def log(m):
    lines.append(str(m))


async def main():
    from conf.config import settings
    log(f"DATABASE_URL = {settings.database_url}")
    log("")

    from sqlalchemy import text
    from infrastructure import database

    log("--- 1) 初始化引擎 ---")
    try:
        database.init_db_engine()
        log("引擎创建成功（注意：此时还没真正连接）")
    except Exception:
        log("引擎创建失败：")
        log(traceback.format_exc())
        return

    log("")
    log("--- 2) 真正执行一次查询 ---")
    try:
        async with database.async_session() as session:
            r = await session.execute(text("SELECT VERSION()"))
            log(f"连接成功，MySQL 版本 = {r.fetchone()}")
    except Exception as exc:
        log(f"连接失败：{type(exc).__name__}")
        log(f"  {str(exc)[:400]}")

    log("")
    log("--- 3) dialogue_states 表是否存在 ---")
    try:
        async with database.async_session() as session:
            r = await session.execute(text("SHOW TABLES LIKE 'dialogue_states'"))
            rows = r.fetchall()
            log(f"表存在: {bool(rows)}  {rows}")
    except Exception as exc:
        log(f"查询失败：{type(exc).__name__}: {str(exc)[:200]}")


try:
    asyncio.run(main())
except Exception:
    log(traceback.format_exc())

with io.open(OUT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))
