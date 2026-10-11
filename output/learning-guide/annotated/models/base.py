# 【导读】models/base.py ｜ 模型层基石：定义 SQLAlchemy 的"声明式基类" Base
# 【导读】被谁调用：所有 ORM 表模型（如 DialogueStateRecord）都继承 Base；建表依赖它的元数据
# 【导读】原理：声明式映射让"Python 类 ↔ 数据库表"一一对应，业务代码基本不用手写建表 SQL

# itwwy/model/base.py

# 教:DeclarativeBase 是 SQLAlchemy 2.0 声明式体系的根基类
from sqlalchemy.orm import DeclarativeBase

# 教:Base 本身可留空；子类继承后会自动收集表结构元数据
class Base(DeclarativeBase):
    # 教:pass 只作占位，真正的列定义在各表模型的子类里
    pass
