# itwwy/test/sqlalchemy/models.py
from typing import Optional

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String


class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "user_account"
    # Mapped：编译器自动提示
    # mapped_column:字段绑定（将类属性映射到数据库）
    id: Mapped[int] = mapped_column(primary_key=True)
    # String(30)：name字段在数据库表的列中类型是varchar 长度是30
    name: Mapped[str] = mapped_column(String(30))

    # Optional：该字段在数据库表中的值是可以允许为null
    fullname: Mapped[Optional[str]]

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, name={self.name!r}, fullname={self.fullname!r})"

class Address(Base):
    __tablename__ = "address"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_address: Mapped[str]

    def __repr__(self) -> str:
        return f"Address(id={self.id!r}, email_address={self.email_address!r})"
