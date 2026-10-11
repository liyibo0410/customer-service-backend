# 【导读】models/dialogue_state.py ｜ 模型层：把 dialogue_states 表映射成 ORM 类
# 【导读】被谁调用：Repository 层用它做查询与插入；注册进 Base 元数据后可自动建表
# 【导读】分工：ORM 管"持久化表结构"，pydantic(domain.state)管"接口校验与传输"，两者各司其职

# itwwy/models/dialogue_state.py

# 教:从基类 Base 继承，本表定义会注册进全局元数据
from models.base import Base
# 教:Mapped[str] 标注列类型；mapped_column 携带建表参数
from sqlalchemy.orm import Mapped, mapped_column
# 教:TEXT 是数据库长文本类型，适合存大段 JSON 状态串
from sqlalchemy import TEXT


# 教:一个表模型类对应一张表，类属性即映射成表的列
class DialogueStateRecord(Base):
    # 教:__tablename__ 显式指定物理表名为 dialogue_states
    __tablename__ = "dialogue_states"
    # 教:把 sender_id 设为主键：每个用户只存一行，天然适配 upsert
    sender_id: Mapped[str] = mapped_column(primary_key=True)
    # 教:state_json 列存放序列化后的整包状态；default 必须是空串这类不可变值
    state_json: Mapped[str] = mapped_column(TEXT, nullable=False, default="")  # 数据库长文本类型（default 兜底空串，不能是可变的 dict）
