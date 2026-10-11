# itwwy/test/sqlalchemy/test_sync_usage.py

from models import Base, User
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


def main():
    # 1. 创建引擎
    # sqlite: 轻量级数据库,数据直接存储到文件中
    # ///mydb: 在当前目录下创建数据库文件mydb
    # ////mydb: 在磁盘根目录下创建数据库文件mydb
    # echo=True: 执行的各种DDL...语句都可以在控制台
    engine = create_engine("sqlite:///mydb", echo=True)

    # 2. 创建表
    Base.metadata.create_all(engine)

    # with：获取session，并自动关闭资源
    with Session(engine) as session:
        # 3. 插入记录
        spongebob = User(
            name="Mr 张",
            fullname="张三"
        )

        sandy = User(
            name="sandy",
            fullname="Sandy Cheeks"
        )

        patrick = User(
            name="patrick",
            fullname="Patrick Star"
        )

        # 向数据库中添加三条记录
        session.add_all([spongebob, sandy, patrick])

        # 手动提交：将数据刷到磁盘
        session.commit()

        # 4. 查询
        stmt = select(User).where(User.name.in_(["Mr 张", "sandy"]))
        for user in session.scalars(stmt):
            print(user)

        stmt = select(User).where(User.name == 'Mr 张')
        print(session.scalars(stmt).one())

if __name__ == '__main__':
    main()
