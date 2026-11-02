"""SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Requisicao(Base):
    __tablename__ = "requisicoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pedido_original: Mapped[str] = mapped_column(Text, nullable=False)
    resposta_agente: Mapped[str] = mapped_column(Text, nullable=False)
    valor_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    itens: Mapped[list[RequisicaoItem]] = relationship(
        back_populates="requisicao",
        cascade="all, delete-orphan",
    )


class RequisicaoItem(Base):
    __tablename__ = "requisicao_itens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    requisicao_id: Mapped[int] = mapped_column(
        ForeignKey("requisicoes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    produto_id: Mapped[int] = mapped_column(Integer, nullable=False)
    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False)
    preco_unitario: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    requisicao: Mapped[Requisicao] = relationship(back_populates="itens")
