"""Persistence access for requisitions."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database.models import Requisicao, RequisicaoItem
from app.schemas.requisicao import ValidatedLineItem


class RequisicaoRepository:
    """CRUD operations for requisitions."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        *,
        pedido_original: str,
        resposta_agente: str,
        itens: list[ValidatedLineItem],
        valor_total: Decimal,
    ) -> Requisicao:
        requisicao = Requisicao(
            pedido_original=pedido_original,
            resposta_agente=resposta_agente,
            valor_total=valor_total,
        )
        for item in itens:
            requisicao.itens.append(
                RequisicaoItem(
                    produto_id=item.produto_id,
                    titulo=item.titulo,
                    quantidade=item.quantidade,
                    preco_unitario=item.preco_unitario,
                    subtotal=item.subtotal,
                )
            )
        self._db.add(requisicao)
        self._db.commit()
        self._db.refresh(requisicao)
        return requisicao

    def list_requisicoes(self, *, limit: int, offset: int) -> tuple[list[Requisicao], int]:
        total = self._db.scalar(select(func.count()).select_from(Requisicao)) or 0
        stmt = (
            select(Requisicao)
            .options(selectinload(Requisicao.itens))
            .order_by(Requisicao.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list(self._db.scalars(stmt).all())
        return rows, int(total)

    def get_by_id(self, requisicao_id: int) -> Requisicao | None:
        stmt = (
            select(Requisicao)
            .options(selectinload(Requisicao.itens))
            .where(Requisicao.id == requisicao_id)
        )
        return self._db.scalar(stmt)
