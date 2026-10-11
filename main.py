# ══════════════════════════════════════════════════════════════════════════
# 文件职责：服务启动入口，用 uvicorn 拉起 FastAPI 应用并监听端口
# 所在层：应用入口（项目最顶层，不属于 api/domain/service 任一包）
# 被谁调用：命令行执行 python main.py 启动服务
# ══════════════════════════════════════════════════════════════════════════
# itwwy/main.py

# 模块文档字符串：说明本文件的作用是"启动 uvicorn"
"""
启动uvicorn
"""
# uvicorn：Python 的 ASGI 服务器，负责把 FastAPI 应用跑成真实 HTTP 服务
import uvicorn

# settings：全局唯一配置对象，host/port 都从 .env 解析而来
from conf.config import settings

# __name__=='__main__'：只有直接运行本文件才为真，被 import 时跳过
if __name__ == '__main__':
    # uvicorn.run：按"模块:应用对象名"定位并启动 FastAPI 应用
    uvicorn.run(
        app="api.app:app",
        host=settings.app_host,
        port=settings.app_port
    )