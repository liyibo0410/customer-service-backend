# ══════════════════════════════════════════════════════════════════════════
# 文件职责：提供 FastAPI 依赖注入函数（session/repository/engine/service）
# 所在层：API 层（只管装配对象，不写业务逻辑）
# 被谁调用：chat_router 中 Depends(get_dialogue_service) 逐级触发
# ══════════════════════════════════════════════════════════════════════════
# api/routers/dependencies.py

# Depends：依赖注入标记，参数用它声明"这个值由 FastAPI 提供"
from fastapi import Depends
# AsyncSession：SQLAlchemy 异步会话类型，用作类型标注
from sqlalchemy.ext.asyncio import AsyncSession
# DialogueService：对话业务服务，组装后交给路由函数使用
from service.dialogue_service import DialogueService
# DialogueStateRepository：对话状态仓库，负责持久化状态读写
from repository.dialogue_state_repository import DialogueStateRepository
# build_dialogue_engine：构建/复用对话引擎的工厂函数
from engine.builder import build_dialogue_engine
# DialogueEngine：对话引擎类型，用于返回值标注
from engine.dialogue_engine import DialogueEngine
# database 模块：内含 async_session（异步会话工厂）
from infrastructure import database


# 依赖一：数据库会话。生成器 + async with 保证用完自动关闭
async def get_session():
    """
    实际流程：
        进入 async with → 打开 session
        yield session → 把 session 交给repository函数使用
        路由函数执行完毕 → 回到 yield 之后
        退出 async with → 自动关闭 session ✅
    :return:
    """
    # 从连接池取会话；会话获取涉及网络 IO，需异步等待
    async with database.async_session() as session:  # 异步方式获取session  获取session要网络传输（耗时的）
        # yield 把会话"交出去"给下游使用，请求结束再回来自动关闭
        yield session


# 依赖二：仓库。先注入会话，再包一层仓库给业务层用
async def get_dialogue_state_repository(session: AsyncSession = Depends(get_session)):
    """
    创建 DialogueStateRepository 实例

    依赖链执行顺序：
        1. get_session() 打开 session 并 yield
        2. 这里拿到 session，创建 Repository
        3. Repository 被Service使用，Service被路由函数使用
        4. 路由函数返回后，get_session() 继续执行，自动关闭 session
    :param session:
    :return:
    """
    # 用注入的会话创建仓库实例并返回给上层使用
    return DialogueStateRepository(session=session)
    # 3. 函数返回后，FastAPI 继续执行 get_session() y


# 依赖三：对话引擎。引擎无状态，直接复用进程内单例
async def get_dialogue_engine() -> DialogueEngine:
    """
    获取对话引擎（各专员：turn_planner / task_handler / validator / clarify_responder）

    复用 engine/builder.py 里的进程内单例：引擎本身无状态，而 flow 定义只需从 YAML
    解析一次、LLM 客户端也只需建一次，没必要每个请求都重新装配。
    :return:
    """
    # builder 内部做了单例缓存，每次返回同一个引擎实例
    return build_dialogue_engine()


# 依赖四：业务服务。按依赖树把仓库与引擎组装成服务
async def get_dialogue_service(
        dialogue_state_repository: DialogueStateRepository = Depends(get_dialogue_state_repository),
        dialogue_engine: DialogueEngine = Depends(get_dialogue_engine)
) -> DialogueService:
    # 实例化服务：仓库负责状态持久化，引擎负责对话推理
    return DialogueService(dialogue_state_repository=dialogue_state_repository, dialogue_engine=dialogue_engine)
