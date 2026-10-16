"""Effective-dated authoritative contract evidence lookup.

This service retrieves structured contract evidence. It deliberately does NOT
set the executable sale price; the pricing authority service remains the only
source of executable pricing.
"""
from datetime import date

from sqlalchemy import or_, select
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
        return {
            "customer_code": customer_code,
            "sku": sku,
            "effective_on": effective.isoformat(),
            "evidence": [],
            "conflict": False,
            "stale_evidence": [],
            "warning": "No active customer was resolved.",
            "authority_notice": "No executable price is produced by knowledge retrieval.",
        }

    active_rows = (await session.execute(
        select(Contract, ContractPrice, Product)
        .join(ContractPrice, ContractPrice.contract_id == Contract.id)
        .join(Product, Product.id == ContractPrice.product_id)
        .where(
            Contract.customer_id == customer.id,
            Contract.status == "ACTIVE",
            Contract.valid_from <= effective,
            Contract.valid_to >= effective,
            Product.sku == sku,
            Product.active.is_(True),
        )
        .order_by(Contract.valid_from.desc(), ContractPrice.min_quantity.desc())
    )).all()

    evidence = [{
        "source_type": "ACTIVE_CONTRACT",
        "source_ref": contract.code,
        "source_artifact_id": str(contract.source_artifact_id) if contract.source_artifact_id else None,
        "title": contract.title,
        "sku": product.sku,
        "effective_from": contract.valid_from.isoformat(),
        "effective_to": contract.valid_to.isoformat(),
        "currency": contract.currency,
        "quoted_contract_unit_price": str(price.unit_price),
        "minimum_quantity": str(price.min_quantity),
        "note": "Contract evidence only; pricing authority must validate executable pricing.",
    } for contract, price, product in active_rows]

    # When no currently effective contract is found, surface nearby historical/
    # future evidence explicitly as STALE/FUTURE instead of silently using it.
    stale_rows = []
    if not evidence:
        stale_rows = (await session.execute(
            select(Contract, ContractPrice, Product)
            .join(ContractPrice, ContractPrice.contract_id == Contract.id)
            .join(Product, Product.id == ContractPrice.product_id)
            .where(
                Contract.customer_id == customer.id,
                Product.sku == sku,
                Product.active.is_(True),
                or_(Contract.valid_to < effective, Contract.valid_from > effective),
            )
            .order_by(Contract.valid_to.desc())
            .limit(5)
        )).all()
    stale_evidence = [{
        "source_ref": contract.code,
        "status": "EXPIRED" if contract.valid_to < effective else "FUTURE",
        "effective_from": contract.valid_from.isoformat(),
        "effective_to": contract.valid_to.isoformat(),
        "currency": contract.currency,
        "quoted_contract_unit_price": str(price.unit_price),
        "minimum_quantity": str(price.min_quantity),
    } for contract, price, _ in stale_rows]

    # More than one simultaneously effective contract is not automatically a
    # conflict: quantity tiers may be expected. A conflict exists when multiple
    # contracts advertise different prices for the same minimum-quantity tier.
    by_tier: dict[str, set[tuple[str, str]]] = {}
    for contract, price, _ in active_rows:
        by_tier.setdefault(str(price.min_quantity), set()).add((contract.currency, str(price.unit_price)))
    conflict = any(len(values) > 1 for values in by_tier.values())

    if conflict:
        warning = "Conflicting simultaneously-effective contract evidence exists; deterministic pricing must stop for review."
    elif not evidence and stale_evidence:
        warning = "No effective contract price; only expired/future evidence exists and must not be executed."
    elif not evidence:
        warning = "No effective contract price; review current agreements."
    else:
        warning = None

    return {
        "customer_code": customer_code,
        "sku": sku,
        "effective_on": effective.isoformat(),
        "evidence": evidence,
        "conflict": conflict,
        "stale_evidence": stale_evidence,
        "warning": warning,
        "authority_notice": "Retrieved contract evidence cannot directly set executable price.",
    }
