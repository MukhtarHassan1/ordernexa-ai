import hashlib
import json
import re
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.digital_twin import (
    Approval,
    Checkpoint,
    Contract,
    ContractPrice,
    Customer,
    Evidence,
    Inventory,
    OrderLine,
    PolicyDecision,
    Product,
    ProductAlias,
    SourceArtifact,
    Warehouse,
)
from app.models.enums import TransactionStatus
from app.schemas.c2c import (
    CreditValidationResult,
    CustomerResolutionResult,
    FulfillmentAllocation,
    LineValidationResult,
    ManualOrderInput,
    ManualOrderValidationResponse,
    PolicyResult,
    TransactionDetailResponse,
)
from app.schemas.transaction import (
    TransactionAdvance,
    TransactionCreate,
)
from app.services.business_order_service import (
    BusinessOrderConflict,
    claim_business_order,
)
from app.services.transaction_service import (
    advance_transaction,
    create_transaction,
    get_transaction,
)


LEGAL_SUFFIXES = {
    "ltd",
    "limited",
    "inc",
    "llc",
    "plc",
    "corp",
    "corporation",
    "company",
    "co",
}


class ResolutionNeedsReview(Exception):
    def __init__(
        self,
        message: str,
        *,
        resolution_type: str,
        candidates: list[dict],
        public_id: str,
    ):
        super().__init__(message)

        self.message = message
        self.resolution_type = resolution_type
        self.candidates = candidates
        self.public_id = public_id


def normalize_text(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_company_name(value: str) -> str:
    tokens = normalize_text(value).split()

    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()

    return " ".join(tokens)


def canonical_hash(payload: dict) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")

    return hashlib.sha256(raw).hexdigest()


async def transition(
    session: AsyncSession,
    transaction,
    target: TransactionStatus,
    event_type: str,
    payload: dict | None = None,
):
    return await advance_transaction(
        session,
        transaction,
        TransactionAdvance(
            target_status=target.value,
            event_type=event_type,
            actor_type="SYSTEM",
            payload=payload or {},
        ),
    )


async def resolve_customer(
    session: AsyncSession,
    transaction,
    data: ManualOrderInput,
) -> tuple[Customer, Decimal, str]:
    if data.customer_code:
        customer = await session.scalar(
            select(Customer)
            .where(
                Customer.code == data.customer_code,
                Customer.status == "ACTIVE",
            )
        )

        if customer:
            return customer, Decimal("1.0000"), "EXACT_CUSTOMER_CODE"

    if data.customer_domain:
        customer = await session.scalar(
            select(Customer)
            .where(
                Customer.primary_domain
                == data.customer_domain.lower(),
                Customer.status == "ACTIVE",
            )
        )

        if customer:
            return customer, Decimal("1.0000"), "EXACT_DOMAIN"

    target = normalize_company_name(data.customer_hint)

    result = await session.execute(
        select(Customer)
        .where(Customer.status == "ACTIVE")
    )

    customers = list(result.scalars().all())

    exact = [
        customer
        for customer in customers
        if customer.normalized_name == target
    ]

    if len(exact) == 1:
        return (
            exact[0],
            Decimal("1.0000"),
            "NORMALIZED_NAME_EXACT",
        )

    scored = []

    for customer in customers:
        score = SequenceMatcher(
            None,
            target,
            customer.normalized_name,
        ).ratio()

        scored.append(
            (
                score,
                customer,
            )
        )

    scored.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    best_score, best_customer = scored[0]

    second_score = (
        scored[1][0]
        if len(scored) > 1
        else 0
    )

    if (
        best_score >= 0.88
        and best_score - second_score >= 0.08
    ):
        return (
            best_customer,
            Decimal(f"{best_score:.4f}"),
            "FUZZY_NAME",
        )

    candidates = [
        {
            "code": customer.code,
            "name": customer.name,
            "score": round(score, 4),
        }
        for score, customer in scored[:3]
    ]

    raise ResolutionNeedsReview(
        "Customer identity is ambiguous and requires review.",
        resolution_type="CUSTOMER",
        candidates=candidates,
        public_id=transaction.public_id,
    )


async def resolve_product(
    session: AsyncSession,
    transaction,
    customer: Customer,
    product_term: str,
) -> tuple[Product, Decimal, str]:
    normalized_term = normalize_text(product_term)

    direct_product = await session.scalar(
        select(Product)
        .where(
            Product.sku == product_term.upper(),
            Product.active.is_(True),
        )
    )

    if direct_product:
        return (
            direct_product,
            Decimal("1.0000"),
            "EXACT_SKU",
        )

    alias_rows = await session.execute(
        select(ProductAlias, Product)
        .join(
            Product,
            Product.id == ProductAlias.product_id,
        )
        .where(
            ProductAlias.normalized_alias
            == normalized_term,
            Product.active.is_(True),
            or_(
                ProductAlias.customer_id
                == customer.id,
                ProductAlias.customer_id.is_(None),
            ),
        )
    )

    aliases = alias_rows.all()

    if aliases:
        aliases.sort(
            key=lambda row: (
                row[0].customer_id != customer.id,
            )
        )

        alias, product = aliases[0]

        method = (
            "CUSTOMER_ALIAS_EXACT"
            if alias.customer_id == customer.id
            else "GLOBAL_ALIAS_EXACT"
        )

        return (
            product,
            Decimal("1.0000"),
            method,
        )

    product_result = await session.execute(
        select(Product)
        .where(Product.active.is_(True))
    )

    products = list(product_result.scalars().all())

    all_aliases_result = await session.execute(
        select(ProductAlias)
    )

    all_aliases = list(
        all_aliases_result.scalars().all()
    )

    aliases_by_product: dict = {}

    for alias in all_aliases:
        aliases_by_product.setdefault(
            alias.product_id,
            [],
        ).append(alias)

    scored: list[tuple[float, Product]] = []

    for product in products:
        candidate_strings = [
            normalize_text(product.sku),
            normalize_text(product.name),
        ]

        for alias in aliases_by_product.get(
            product.id,
            [],
        ):
            if (
                alias.customer_id is None
                or alias.customer_id == customer.id
            ):
                candidate_strings.append(
                    alias.normalized_alias
                )

        score = max(
            SequenceMatcher(
                None,
                normalized_term,
                candidate,
            ).ratio()
            for candidate in candidate_strings
        )

        scored.append(
            (
                score,
                product,
            )
        )

    scored.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    best_score, best_product = scored[0]

    second_score = (
        scored[1][0]
        if len(scored) > 1
        else 0
    )

    if (
        best_score >= 0.84
        and best_score - second_score >= 0.08
    ):
        return (
            best_product,
            Decimal(f"{best_score:.4f}"),
            "FUZZY_CATALOG",
        )

    candidates = [
        {
            "sku": product.sku,
            "name": product.name,
            "score": round(score, 4),
        }
        for score, product in scored[:3]
    ]

    raise ResolutionNeedsReview(
        f"Product '{product_term}' is ambiguous.",
        resolution_type="PRODUCT",
        candidates=candidates,
        public_id=transaction.public_id,
    )


async def determine_price(
    session: AsyncSession,
    *,
    customer: Customer,
    product: Product,
    quantity: Decimal,
) -> tuple[
    Decimal,
    Contract | None,
    ContractPrice | None,
]:
    today = date.today()

    result = await session.execute(
        select(
            Contract,
            ContractPrice,
        )
        .join(
            ContractPrice,
            ContractPrice.contract_id == Contract.id,
        )
        .where(
            Contract.customer_id == customer.id,
            Contract.status == "ACTIVE",
            Contract.valid_from <= today,
            Contract.valid_to >= today,
            ContractPrice.product_id == product.id,
            ContractPrice.min_quantity <= quantity,
        )
        .order_by(
            Contract.valid_from.desc(),
            ContractPrice.min_quantity.desc(),
        )
        .limit(1)
    )

    row = result.first()

    if row:
        contract, price = row

        return (
            price.unit_price,
            contract,
            price,
        )

    return (
        product.catalog_price,
        None,
        None,
    )


async def build_fulfillment_plan(
    session: AsyncSession,
    *,
    product: Product,
    quantity: Decimal,
    preferred_warehouse_code: str,
) -> tuple[list[dict], str]:
    result = await session.execute(
        select(
            Inventory,
            Warehouse,
        )
        .join(
            Warehouse,
            Warehouse.id == Inventory.warehouse_id,
        )
        .where(
            Inventory.product_id == product.id,
            Warehouse.active.is_(True),
        )
    )

    inventory_rows = list(result.all())

    inventory_rows.sort(
        key=lambda item: (
            item[1].code != preferred_warehouse_code,
            item[1].priority,
            item[1].code,
        )
    )

    remaining = quantity

    plan: list[dict] = []

    for inventory, warehouse in inventory_rows:
        available = (
            inventory.on_hand
            - inventory.reserved
        )

        if available <= 0:
            continue

        take = min(
            remaining,
            available,
        )

        if take > 0:
            plan.append(
                {
                    "warehouse_code": warehouse.code,
                    "warehouse_name": warehouse.name,
                    "quantity": str(take),
                }
            )

            remaining -= take

        if remaining <= 0:
            break

    if remaining > 0:
        return plan, "INSUFFICIENT"

    if len(plan) > 1:
        return plan, "SPLIT"

    return plan, "SINGLE_WAREHOUSE"


async def create_manual_order(
    session: AsyncSession,
    data: ManualOrderInput,
    *,
    source: str = "MANUAL",
) -> ManualOrderValidationResponse:
    transaction = await create_transaction(
        session,
        TransactionCreate(
            source=source,
            intent="PURCHASE_ORDER",
            customer_reference=data.po_number,
            currency=data.currency.upper(),
        ),
    )

    raw_payload = data.model_dump(
        mode="json"
    )

    source_artifact = SourceArtifact(
        transaction_id=transaction.id,
        artifact_type="NORMALIZED_ORDER_JSON",
        original_name=f"{data.po_number}.json",
        mime_type="application/json",
        storage_provider="INLINE",
        sha256=canonical_hash(raw_payload),
        source_ref=data.po_number,
        extra_data={
            "ingestion_adapter": source,
        },
    )

    session.add(source_artifact)

    order_lines: dict[int, OrderLine] = {}

    for input_line in data.lines:
        line = OrderLine(
            transaction_id=transaction.id,
            line_number=input_line.line_number,
            requested_product_term=(
                input_line.product_term
            ),
            quantity=input_line.quantity,
            uom=input_line.uom.upper(),
            requested_unit_price=(
                input_line.requested_unit_price
            ),
            status="EXTRACTED",
        )

        session.add(line)

        order_lines[
            input_line.line_number
        ] = line

    await session.flush()

    transaction = await transition(
        session,
        transaction,
        TransactionStatus.TRIAGED,
        "INTENT_CLASSIFIED",
        {
            "intent": "PURCHASE_ORDER",
            "confidence": "1.0000",
            "mode": "DETERMINISTIC_MANUAL_INPUT",
        },
    )

    transaction = await transition(
        session,
        transaction,
        TransactionStatus.EXTRACTED,
        "ORDER_SCHEMA_VALIDATED",
        {
            "po_number": data.po_number,
            "line_count": len(data.lines),
            "source_artifact_id": str(
                source_artifact.id
            ),
        },
    )

    transaction = await transition(
        session,
        transaction,
        TransactionStatus.CUSTOMER_RESOLUTION,
        "CUSTOMER_RESOLUTION_STARTED",
        {
            "customer_hint": data.customer_hint,
        },
    )

    customer, customer_confidence, customer_method = (
        await resolve_customer(
            session,
            transaction,
            data,
        )
    )

    transaction.customer_id = customer.id

    session.add(
        Evidence(
            transaction_id=transaction.id,
            evidence_type="CUSTOMER_RESOLUTION",
            source_type="CUSTOMER_MASTER",
            source_ref=f"customer:{customer.code}",
            label=customer.name,
            excerpt=(
                f"Resolved '{data.customer_hint}' "
                f"to {customer.code}."
            ),
            confidence=customer_confidence,
            details={
                "method": customer_method,
                "domain": customer.primary_domain,
            },
        )
    )

    await session.flush()

    # Claim the *business order*, not merely this technical transaction.
    # This closes the cross-transaction duplicate gap while preserving an
    # explicit amendment/revision path.
    try:
        business_identity = await claim_business_order(
            session, transaction=transaction, customer=customer, data=data
        )
    except BusinessOrderConflict as exc:
        transaction = await transition(
            session,
            transaction,
            TransactionStatus.DUPLICATE_REVIEW,
            "BUSINESS_ORDER_DUPLICATE_BLOCKED",
            {
                "normalized_po": exc.normalized_po,
                "candidates": [item.as_dict() for item in exc.candidates],
                "erp_write_allowed": False,
            },
        )
        raise ResolutionNeedsReview(
            "This customer PO revision already exists. Review/link the existing order or submit an explicit amendment.",
            resolution_type="DUPLICATE_ORDER",
            candidates=[item.as_dict() for item in exc.candidates],
            public_id=transaction.public_id,
        ) from exc
    except ValueError as exc:
        transaction = await transition(
            session,
            transaction,
            TransactionStatus.WAITING_CUSTOMER,
            "AMENDMENT_VALIDATION_REQUIRED",
            {"message": str(exc), "erp_write_allowed": False},
        )
        raise ResolutionNeedsReview(
            str(exc),
            resolution_type="AMENDMENT_VALIDATION",
            candidates=[],
            public_id=transaction.public_id,
        ) from exc

    transaction = await transition(
        session,
        transaction,
        TransactionStatus.PRODUCT_RESOLUTION,
        "CUSTOMER_RESOLVED",
        {
            "customer_code": customer.code,
            "customer_name": customer.name,
            "confidence": str(customer_confidence),
            "method": customer_method,
            "business_order": {
                "normalized_po": business_identity.normalized_po,
                "revision": business_identity.revision,
                "content_fingerprint": business_identity.content_fingerprint,
                "amendment": business_identity.revision > 1,
            },
        },
    )

    product_by_line: dict[int, Product] = {}
    resolution_by_line: dict[int, tuple] = {}

    for input_line in data.lines:
        line = order_lines[
            input_line.line_number
        ]

        product, confidence, method = (
            await resolve_product(
                session,
                transaction,
                customer,
                input_line.product_term,
            )
        )

        line.resolved_product_id = product.id
        line.resolution_confidence = confidence
        line.resolution_method = method
        line.status = "PRODUCT_RESOLVED"

        product_by_line[
            input_line.line_number
        ] = product

        resolution_by_line[
            input_line.line_number
        ] = (
            confidence,
            method,
        )

        session.add(
            Evidence(
                transaction_id=transaction.id,
                order_line_id=line.id,
                evidence_type="PRODUCT_RESOLUTION",
                source_type="PRODUCT_MASTER",
                source_ref=f"sku:{product.sku}",
                label=product.name,
                excerpt=(
                    f"Resolved "
                    f"'{input_line.product_term}' "
                    f"to {product.sku}."
                ),
                confidence=confidence,
                details={
                    "method": method,
                },
            )
        )

    await session.flush()

    transaction = await transition(
        session,
        transaction,
        TransactionStatus.PRICING_CHECK,
        "PRODUCTS_RESOLVED",
        {
            "resolved_line_count": len(
                product_by_line
            ),
        },
    )

    pricing_exception_reasons: list[str] = []

    line_results_temp: dict[int, dict] = {}

    order_value = Decimal("0.00")

    for input_line in data.lines:
        line = order_lines[
            input_line.line_number
        ]

        product = product_by_line[
            input_line.line_number
        ]

        executable_price, contract, contract_price = (
            await determine_price(
                session,
                customer=customer,
                product=product,
                quantity=input_line.quantity,
            )
        )

        line.executable_unit_price = (
            executable_price
        )

        line.line_total = (
            executable_price
            * input_line.quantity
        ).quantize(
            Decimal("0.01")
        )

        order_value += line.line_total

        pricing_exception = (
            input_line.requested_unit_price
            is not None
            and abs(
                input_line.requested_unit_price
                - executable_price
            )
            > Decimal("0.01")
        )

        if pricing_exception:
            pricing_exception_reasons.append(
                (
                    f"LINE_{input_line.line_number}_"
                    f"REQUESTED_PRICE_DIFFERS_FROM_"
                    f"EXECUTABLE_PRICE"
                )
            )

        if contract:
            evidence_source = (
                f"contract:{contract.code}"
            )

            evidence_label = (
                f"{contract.code} contract price"
            )

            excerpt = (
                f"{product.sku} executable price "
                f"{executable_price} "
                f"{contract.currency} from "
                f"{contract.code}."
            )

            effective_from = contract.valid_from
            effective_to = contract.valid_to
        else:
            evidence_source = (
                f"product:{product.sku}"
            )

            evidence_label = (
                f"{product.sku} catalog price"
            )

            excerpt = (
                f"{product.sku} executable price "
                f"{executable_price} "
                f"{product.currency} from catalog."
            )

            effective_from = None
            effective_to = None

        session.add(
            Evidence(
                transaction_id=transaction.id,
                order_line_id=line.id,
                evidence_type="PRICING_AUTHORITY",
                source_type=(
                    "CONTRACT"
                    if contract
                    else "CATALOG"
                ),
                source_ref=evidence_source,
                label=evidence_label,
                excerpt=excerpt,
                confidence=Decimal("1.0000"),
                effective_from=effective_from,
                effective_to=effective_to,
                details={
                    "requested_unit_price": (
                        str(
                            input_line
                            .requested_unit_price
                        )
                        if input_line
                        .requested_unit_price
                        is not None
                        else None
                    ),
                    "executable_unit_price": str(
                        executable_price
                    ),
                    "pricing_exception": (
                        pricing_exception
                    ),
                },
            )
        )

        line_results_temp[
            input_line.line_number
        ] = {
            "product": product,
            "pricing_exception": (
                pricing_exception
            ),
            "executable_price": (
                executable_price
            ),
        }

    transaction.value = order_value

    await session.flush()

    transaction = await transition(
        session,
        transaction,
        TransactionStatus.INVENTORY_CHECK,
        "PRICING_VALIDATED",
        {
            "order_value": str(
                order_value
            ),
            "pricing_exception_count": len(
                pricing_exception_reasons
            ),
        },
    )

    fulfillment_reasons: list[str] = []

    for input_line in data.lines:
        line = order_lines[
            input_line.line_number
        ]

        product = product_by_line[
            input_line.line_number
        ]

        plan, fulfillment_status = (
            await build_fulfillment_plan(
                session,
                product=product,
                quantity=input_line.quantity,
                preferred_warehouse_code=(
                    data.delivery_warehouse_code
                ),
            )
        )

        line.fulfillment_plan = plan
        line.fulfillment_status = (
            fulfillment_status
        )

        if fulfillment_status == "SPLIT":
            fulfillment_reasons.append(
                (
                    f"LINE_{input_line.line_number}_"
                    f"MULTI_WAREHOUSE_FULFILLMENT"
                )
            )

        elif fulfillment_status == "INSUFFICIENT":
            fulfillment_reasons.append(
                (
                    f"LINE_{input_line.line_number}_"
                    f"INSUFFICIENT_INVENTORY"
                )
            )

        session.add(
            Evidence(
                transaction_id=transaction.id,
                order_line_id=line.id,
                evidence_type="INVENTORY_VALIDATION",
                source_type="INVENTORY_MASTER",
                source_ref=f"sku:{product.sku}",
                label=(
                    f"{product.sku} fulfillment plan"
                ),
                excerpt=(
                    f"Fulfillment status: "
                    f"{fulfillment_status}."
                ),
                confidence=Decimal("1.0000"),
                details={
                    "preferred_warehouse": (
                        data.delivery_warehouse_code
                    ),
                    "plan": plan,
                    "status": fulfillment_status,
                },
            )
        )

    await session.flush()

    transaction = await transition(
        session,
        transaction,
        TransactionStatus.CREDIT_CHECK,
        "INVENTORY_VALIDATED",
        {
            "fulfillment_exceptions": (
                fulfillment_reasons
            ),
        },
    )

    projected_exposure = (
        customer.current_exposure
        + order_value
    )

    over_limit_by = max(
        Decimal("0.00"),
        projected_exposure
        - customer.credit_limit,
    )

    credit_requires_approval = (
        over_limit_by > 0
    )

    session.add(
        Evidence(
            transaction_id=transaction.id,
            evidence_type="CREDIT_VALIDATION",
            source_type="CUSTOMER_MASTER",
            source_ref=f"customer:{customer.code}",
            label=(
                f"{customer.code} credit position"
            ),
            excerpt=(
                f"Current exposure "
                f"{customer.current_exposure}; "
                f"projected exposure "
                f"{projected_exposure}; "
                f"credit limit "
                f"{customer.credit_limit}."
            ),
            confidence=Decimal("1.0000"),
            details={
                "credit_limit": str(
                    customer.credit_limit
                ),
                "current_exposure": str(
                    customer.current_exposure
                ),
                "order_value": str(order_value),
                "projected_exposure": str(
                    projected_exposure
                ),
                "over_limit_by": str(
                    over_limit_by
                ),
            },
        )
    )

    policy_reasons: list[str] = []
    approval_requirements: list[
        tuple[str, str]
    ] = []

    if pricing_exception_reasons:
        policy_reasons.extend(
            pricing_exception_reasons
        )

        approval_requirements.append(
            (
                "Requested price differs "
                "from authoritative price.",
                "SALES_MANAGER",
            )
        )

    if credit_requires_approval:
        policy_reasons.append(
            "CREDIT_LIMIT_EXCEEDED"
        )

        approval_requirements.append(
            (
                "Projected customer exposure "
                "exceeds credit limit.",
                "FINANCE_MANAGER",
            )
        )

    policy_reasons.extend(
        fulfillment_reasons
    )

    if any(
        "INSUFFICIENT_INVENTORY"
        in reason
        for reason in fulfillment_reasons
    ):
        approval_requirements.append(
            (
                "Inventory cannot fully satisfy "
                "the requested quantity.",
                "OPERATIONS_MANAGER",
            )
        )

    required_roles = sorted(
        {
            role
            for _, role
            in approval_requirements
        }
    )

    if approval_requirements:
        outcome = "APPROVAL_REQUIRED"
    else:
        outcome = "AUTO_APPROVED"

    if credit_requires_approval:
        transaction.risk = "HIGH"
    elif (
        pricing_exception_reasons
        or fulfillment_reasons
    ):
        transaction.risk = "MEDIUM"
    else:
        transaction.risk = "LOW"

    policy_decision = PolicyDecision(
        transaction_id=transaction.id,
        policy_name="C2C_ORDER_POLICY",
        policy_version="1.0.0",
        outcome=outcome,
        reasons=policy_reasons,
        required_approvers=required_roles,
        inputs={
            "order_value": str(order_value),
            "credit_limit": str(
                customer.credit_limit
            ),
            "current_exposure": str(
                customer.current_exposure
            ),
            "projected_exposure": str(
                projected_exposure
            ),
            "pricing_exception_count": len(
                pricing_exception_reasons
            ),
            "fulfillment_exceptions": (
                fulfillment_reasons
            ),
        },
    )

    session.add(policy_decision)
    await session.flush()

    for reason, role in approval_requirements:
        session.add(
            Approval(
                transaction_id=transaction.id,
                policy_decision_id=(
                    policy_decision.id
                ),
                reason=reason,
                approver_role=role,
                status="PENDING",
            )
        )

    await session.flush()

    if outcome == "APPROVAL_REQUIRED":
        transaction = await transition(
            session,
            transaction,
            TransactionStatus.APPROVAL_REQUIRED,
            "POLICY_APPROVAL_REQUIRED",
            {
                "reasons": policy_reasons,
                "required_approvers": (
                    required_roles
                ),
            },
        )
    else:
        transaction = await transition(
            session,
            transaction,
            TransactionStatus.READY,
            "POLICY_AUTO_APPROVED",
            {
                "reasons": [],
            },
        )

    checkpoint = Checkpoint(
        transaction_id=transaction.id,
        step="DRAFT_VALIDATED",
        status="VERIFIED",
        data={
            "transaction_status": (
                transaction.status
            ),
            "customer_code": customer.code,
            "order_value": str(order_value),
            "policy_outcome": outcome,
        },
        side_effects=[],
        verified=True,
    )

    session.add(checkpoint)

    await session.commit()

    customer_result = CustomerResolutionResult(
        customer_id=customer.id,
        code=customer.code,
        name=customer.name,
        confidence=customer_confidence,
        method=customer_method,
    )

    line_results: list[
        LineValidationResult
    ] = []

    for input_line in data.lines:
        line = order_lines[
            input_line.line_number
        ]

        product = product_by_line[
            input_line.line_number
        ]

        confidence, method = (
            resolution_by_line[
                input_line.line_number
            ]
        )

        temp = line_results_temp[
            input_line.line_number
        ]

        allocations = [
            FulfillmentAllocation(
                warehouse_code=item[
                    "warehouse_code"
                ],
                warehouse_name=item[
                    "warehouse_name"
                ],
                quantity=Decimal(
                    item["quantity"]
                ),
            )
            for item in line.fulfillment_plan
        ]

        line_results.append(
            LineValidationResult(
                line_number=line.line_number,
                requested_product_term=(
                    line.requested_product_term
                ),
                resolved_product_id=product.id,
                resolved_sku=product.sku,
                resolved_name=product.name,
                resolution_confidence=confidence,
                resolution_method=method,
                quantity=line.quantity,
                requested_unit_price=(
                    line.requested_unit_price
                ),
                executable_unit_price=(
                    temp["executable_price"]
                ),
                line_total=line.line_total,
                pricing_exception=temp[
                    "pricing_exception"
                ],
                fulfillment_status=(
                    line.fulfillment_status
                ),
                fulfillment_exception=(
                    line.fulfillment_status
                    != "SINGLE_WAREHOUSE"
                ),
                allocations=allocations,
            )
        )

    credit_result = CreditValidationResult(
        credit_limit=customer.credit_limit,
        current_exposure=(
            customer.current_exposure
        ),
        order_value=order_value,
        projected_exposure=(
            projected_exposure
        ),
        over_limit_by=over_limit_by,
        requires_approval=(
            credit_requires_approval
        ),
    )

    policy_result = PolicyResult(
        outcome=outcome,
        reasons=policy_reasons,
        required_approvers=required_roles,
    )

    return ManualOrderValidationResponse(
        transaction_id=transaction.id,
        public_id=transaction.public_id,
        correlation_id=(
            transaction.correlation_id
        ),
        po_number=data.po_number,
        status=transaction.status,
        risk=transaction.risk,
        value=order_value,
        currency=transaction.currency,
        customer=customer_result,
        lines=line_results,
        credit=credit_result,
        policy=policy_result,
    )


async def get_transaction_detail(
    session: AsyncSession,
    public_id: str,
) -> TransactionDetailResponse | None:
    transaction = await get_transaction(
        session,
        public_id,
    )

    if transaction is None:
        return None

    line_result = await session.execute(
        select(OrderLine)
        .where(
            OrderLine.transaction_id
            == transaction.id
        )
        .order_by(OrderLine.line_number)
    )

    evidence_result = await session.execute(
        select(Evidence)
        .where(
            Evidence.transaction_id
            == transaction.id
        )
        .order_by(Evidence.created_at)
    )

    policy_result = await session.execute(
        select(PolicyDecision)
        .where(
            PolicyDecision.transaction_id
            == transaction.id
        )
        .order_by(PolicyDecision.created_at)
    )

    approval_result = await session.execute(
        select(Approval)
        .where(
            Approval.transaction_id
            == transaction.id
        )
        .order_by(Approval.created_at)
    )

    checkpoint_result = await session.execute(
        select(Checkpoint)
        .where(
            Checkpoint.transaction_id
            == transaction.id
        )
        .order_by(Checkpoint.created_at)
    )

    return TransactionDetailResponse(
        transaction=transaction,
        lines=list(
            line_result.scalars().all()
        ),
        evidence=list(
            evidence_result.scalars().all()
        ),
        policy_decisions=list(
            policy_result.scalars().all()
        ),
        approvals=list(
            approval_result.scalars().all()
        ),
        checkpoints=list(
            checkpoint_result.scalars().all()
        ),
    )