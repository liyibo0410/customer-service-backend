# 【导读】repository/dialogue_state_repository.py ｜ Repository 层：对话状态表的读写封装
# 【导读】被谁调用：Service 层的 DialogueService；它依赖 SQLAlchemy 异步会话执行 SQL
# 【导读】依赖方向：上层只认 load_state/save_state 两个接口，看不到任何 SQL 实现细节

# itwwy/repository/dialogue_state_repository.py

# 教:json 负责把状态对象在"字典"与"JSON 字符串"之间互转
import json
# 教:AsyncSession 仅作类型标注，提醒调用方传入的是异步会话
from sqlalchemy.ext.asyncio import AsyncSession
# 教:select 是 SQLAlchemy 2.0 的查询构造器（ORM 风格写 SQL）
from sqlalchemy import select
# 教:导入 MySQL 方言的 insert，它才带 on_duplicate_key_update 能力
from sqlalchemy.dialects.mysql import insert
# 教:domain 层领域对象：JSON 反序列化后还原成它再交给上层
from domain.state import DialogueState
# 教:本文件的 ORM 模型，代表 dialogue_states 表中的一行
from models.dialogue_state import DialogueStateRecord


# 教:仓储类：向上层只暴露 load_state / save_state 两个方法
class DialogueStateRepository:

    # 教:构造时接收一个 AsyncSession（会话由上层依赖注入处提供）
    def __init__(self, session: AsyncSession):
        # 教:把会话存为实例属性，查询、执行、提交都复用它
        self.session = session

    # 教:读操作：async 异步方法，注解标明入参和返回值类型
    async def load_state(self, sender_id: str) -> DialogueState:
        """
        读操作
        :return:
        """

        # 1. 定义sql
        # 教:构造 SELECT 语句：筛出 sender_id 等于入参的那一行
        sql = select(DialogueStateRecord).where(DialogueStateRecord.sender_id == sender_id)

        # 2. 执行sql
        # 教:await 真正执行查询；数据库 IO 期间让出 CPU 给其他请求
        result = await self.session.execute(sql)

        # 3. 获取结果
        # 教:取"零或一条"：有记录返回 Row 对象，没有则返回 None
        sate = result.scalar_one_or_none()

        # 教:查到记录才需要反序列化，否则走下方"新用户"兜底分支
        if sate:
            # 将 state.state_json 反序列化成一个 DialogueState 对象
            # 教:把库里存的 JSON 字符串解析成 Python 字典
            state_dict = json.loads(sate.state_json)
            # 教:pydantic 校验字典字段并构造出 DialogueState 领域对象
            return DialogueState.model_validate(state_dict)

        # 教:库里还没有该用户：返回只含 sender_id 的空状态兜底
        return DialogueState(sender_id=sender_id)

    # 教:写操作：利用"主键冲突即更新"实现有则更新、无则插入（upsert）
    async def save_state(self, dialogue_state: DialogueState):
        """
        写操作(插入、修改)
        传统：插入之前先查询该条件（sender_id）对应的记录是否存在，如果不存在 则插入，反之修改
        进阶：负责将插入sql直接升级为修改sql(主键重复机制判断)
        :return:
        """

        # 1. 得到DialogueState的json字符串
        # 教:pydantic 先导出 JSON 兼容字典(mode="json")，再序列化成字符串存库
        state_json: str = json.dumps(dialogue_state.model_dump(mode="json"))

        # 2. 定义插入的sql语句
        # 注意这里的依赖是：sqlalchemy.dialects.mysql.insert  而不是  sqlalchemy.insert
        # 教:构造 INSERT 语句，values 指定要写入的两列值
        insert_stmt = insert(DialogueStateRecord).values(
            sender_id=dialogue_state.sender_id, state_json=state_json
        )

        # 3. 升级update语句的sql
        # 教:若主键 sender_id 已存在则转成更新，把 state_json 换成新值
        update_stmt = insert_stmt.on_duplicate_key_update(
            state_json=insert_stmt.inserted.state_json
        )

        # 4. 执行sql
        # 教:await 执行这条 upsert；未 commit 前改动只在当前事务内
        await  self.session.execute(update_stmt)

        # 5. 提交
        # 教:commit 提交事务才真正落库，持久化在这里完成
        await self.session.commit()
