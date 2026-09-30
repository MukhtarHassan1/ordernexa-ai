"""Metadata-scoped, effective-dated authoritative evidence lookup.

This is deterministic retrieval over existing Atlas contract/catalog tables,
NOT vector/embedding RAG, and never itself sets an executable sale price.
"""
from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.digital_twin import Contract, ContractPrice, Customer, Product


async def contract_evidence(
    session: AsyncSession, *, customer_code: str, sku: str,
    effective_on: date | None = None,
) -> dict:
    effective = effective_on or date.today()
    customer = await session.scalar(select(Customer).where(
        Customer.code == customer_code, Customer.status == "ACTIVE",
    ))
    if customer is None:
        return {"customer_code": customer_code, "sku": sku, "effective_on": effective.isoformat(),
                "evidence": [], "warning": "No active customer was resolved."}
    result = await session.execute(
        select(Contract, ContractPrice, Product)
        .join(ContractPrice, ContractPrice.contract_id == Contract.id)
        .join(Product, Product.id == ContractPrice.product_id)
        .where(Contract.customer_id == customer.id, Contract.status == "ACTIVE",
               Contract.valid_from <= effective, Contract.valid_to >= effective,
               Product.sku == sku, Product.active.is_(True))
        .order_by(Contract.valid_from.desc(), ContractPrice.min_quantity.desc())
    )
    evidence = [{
        "source_type": "ACTIVE_CONTRACT", "source_ref": contract.code,
        "source_artifact_id": str(contract.source_artifact_id) if contract.source_artifact_id else None,
        "title": contract.title, "sku": product.sku,
        "effective_from": contract.valid_from.isoformat(),
        "effective_to": contract.valid_to.isoformat(),
        "currency": contract.currency,
        "quoted_contract_unit_price": str(price.unit_price),
        "minimum_quantity": str(price.min_quantity),
        "note": "Contract evidence only; pricing service must validate executable pricing.",
    } for contract, price, product in result.all()]
    return {"customer_code": customer_code, "sku": sku,
            "effective_on": effective.isoformat(), "evidence": evidence,
            "warning": None if evidence else "No effective contract price; review current agreements."}
