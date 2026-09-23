import asyncio
import random
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.digital_twin import (
    Contract,
    ContractPrice,
    Customer,
    CustomerExternalRef,
    HistoricalOrder,
    HistoricalOrderLine,
    Inventory,
    Product,
    ProductAlias,
    Warehouse,
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


def normalize_text(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_company(value: str) -> str:
    tokens = normalize_text(value).split()

    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()

    return " ".join(tokens)


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        existing = await session.scalar(
            select(Customer)
            .where(
                Customer.code == "CUST-1001"
            )
        )

        if existing:
            print(
                "Atlas seed already exists. "
                "No changes made."
            )
            return

        customer_specs = [
            (
                "CUST-1001",
                "Northstar Engineering Ltd",
                "northstar-engineering.com",
                "100000.00",
                "88000.00",
                "STRATEGIC",
            ),
            (
                "CUST-1002",
                "Northstar Engineering Services Ltd",
                "northstar-services.com",
                "45000.00",
                "18000.00",
                "STANDARD",
            ),
            (
                "CUST-1003",
                "Northstar Industrial Holdings",
                "northstar-industrial.com",
                "80000.00",
                "42000.00",
                "KEY",
            ),
            (
                "CUST-1004",
                "Westbridge Manufacturing Ltd",
                "westbridge-mfg.com",
                "60000.00",
                "25000.00",
                "STANDARD",
            ),
            (
                "CUST-1005",
                "Helix Mechanical Systems Ltd",
                "helix-mechanical.com",
                "75000.00",
                "31000.00",
                "KEY",
            ),
            (
                "CUST-1006",
                "Apex Industrial Group Ltd",
                "apex-industrial.com",
                "90000.00",
                "54000.00",
                "KEY",
            ),
            (
                "CUST-1007",
                "Novatek Components Ltd",
                "novatek-components.com",
                "35000.00",
                "12000.00",
                "STANDARD",
            ),
            (
                "CUST-1008",
                "Brighton Engineering Ltd",
                "brighton-engineering.com",
                "50000.00",
                "19000.00",
                "STANDARD",
            ),
            (
                "CUST-1009",
                "Rutherford Automation Ltd",
                "rutherford-auto.com",
                "85000.00",
                "33000.00",
                "KEY",
            ),
            (
                "CUST-1010",
                "Meridian Process Systems Ltd",
                "meridian-process.com",
                "70000.00",
                "27000.00",
                "STANDARD",
            ),
            (
                "CUST-1011",
                "Sterling Industrial Supplies Ltd",
                "sterling-industrial.com",
                "50000.00",
                "24000.00",
                "STANDARD",
            ),
            (
                "CUST-1012",
                "Cambridge Motion Controls Ltd",
                "cambridge-motion.com",
                "65000.00",
                "29000.00",
                "KEY",
            ),
            (
                "CUST-1013",
                "Vector Plant Engineering Ltd",
                "vector-plant.com",
                "55000.00",
                "16000.00",
                "STANDARD",
            ),
            (
                "CUST-1014",
                "Redbridge Technical Products Ltd",
                "redbridge-tech.com",
                "40000.00",
                "9000.00",
                "STANDARD",
            ),
            (
                "CUST-1015",
                "Falcon Process Equipment Ltd",
                "falcon-process.com",
                "95000.00",
                "44000.00",
                "KEY",
            ),
            (
                "CUST-1016",
                "Orion Mechanical Ltd",
                "orion-mechanical.com",
                "45000.00",
                "15000.00",
                "STANDARD",
            ),
            (
                "CUST-1017",
                "DeltaWorks Engineering Ltd",
                "deltaworks.co.uk",
                "60000.00",
                "21000.00",
                "STANDARD",
            ),
            (
                "CUST-1018",
                "Crown Industrial Solutions Ltd",
                "crown-industrial.com",
                "80000.00",
                "39000.00",
                "KEY",
            ),
            (
                "CUST-1019",
                "Hartwell Manufacturing Ltd",
                "hartwell-mfg.com",
                "55000.00",
                "17000.00",
                "STANDARD",
            ),
            (
                "CUST-1020",
                "EuroTech Assembly Systems Ltd",
                "eurotech-assembly.eu",
                "75000.00",
                "28000.00",
                "KEY",
            ),
        ]

        customers: list[Customer] = []

        for (
            code,
            name,
            domain,
            credit_limit,
            exposure,
            tier,
        ) in customer_specs:
            customer = Customer(
                code=code,
                name=name,
                normalized_name=(
                    normalize_company(name)
                ),
                primary_domain=domain,
                credit_limit=Decimal(
                    credit_limit
                ),
                current_exposure=Decimal(
                    exposure
                ),
                currency="GBP",
                tier=tier,
                status="ACTIVE",
            )

            session.add(customer)
            customers.append(customer)

        await session.flush()

        customer_by_code = {
            customer.code: customer
            for customer in customers
        }

        northstar = customer_by_code[
            "CUST-1001"
        ]

        for customer in customers:
            session.add(
                CustomerExternalRef(
                    customer_id=customer.id,
                    system="DEMO_CRM",
                    external_id=(
                        f"CRM-{customer.code}"
                    ),
                    extra_data={},
                )
            )

            session.add(
                CustomerExternalRef(
                    customer_id=customer.id,
                    system="DEMO_ERP",
                    external_id=(
                        f"ERP-{customer.code}"
                    ),
                    extra_data={},
                )
            )

        product_specs = [
            (
                "XTR-420",
                "XTR Industrial Pump",
                "340.00",
            ),
            (
                "XTR-410",
                "XTR Compact Industrial Pump",
                "315.00",
            ),
            (
                "XTR-430",
                "XTR High Capacity Pump",
                "365.00",
            ),
            (
                "XTR-420R",
                "XTR Industrial Pump Reinforced",
                "385.00",
            ),
            (
                "BRK-090",
                "Heavy Duty Brake Assembly",
                "180.00",
            ),
            (
                "BRK-080",
                "Standard Brake Assembly",
                "155.00",
            ),
            (
                "BRK-100",
                "Extra Heavy Brake Assembly",
                "205.00",
            ),
            (
                "PMP-220",
                "Process Transfer Pump",
                "260.00",
            ),
            (
                "VLV-310",
                "Industrial Control Valve",
                "120.00",
            ),
            (
                "HSE-500",
                "Reinforced Hydraulic Hose",
                "95.00",
            ),
        ]

        products: list[Product] = []

        for sku, name, price in product_specs:
            product = Product(
                sku=sku,
                name=name,
                normalized_name=(
                    normalize_text(name)
                ),
                catalog_price=Decimal(price),
                currency="GBP",
                uom="EA",
                active=True,
            )

            session.add(product)
            products.append(product)

        await session.flush()

        product_by_sku = {
            product.sku: product
            for product in products
        }

        alias_specs = [
            (
                "XTR-420",
                "XTR Pump",
                None,
            ),
            (
                "XTR-420",
                "XTR series",
                None,
            ),
            (
                "XTR-420",
                "420 Pump",
                None,
            ),
            (
                "XTR-420",
                "Industrial XTR",
                None,
            ),
            (
                "XTR-420",
                "Same pump as last month",
                "CUST-1001",
            ),
            (
                "XTR-420",
                "XTR-42",
                "CUST-1001",
            ),
            (
                "BRK-090",
                "BRK-90",
                None,
            ),
            (
                "BRK-090",
                "Brake Kit 90",
                None,
            ),
            (
                "BRK-090",
                "Heavy Brake",
                None,
            ),
            (
                "BRK-090",
                "90 Brake Assembly",
                None,
            ),
        ]

        for (
            sku,
            alias,
            customer_code,
        ) in alias_specs:
            session.add(
                ProductAlias(
                    product_id=(
                        product_by_sku[sku].id
                    ),
                    customer_id=(
                        customer_by_code[
                            customer_code
                        ].id
                        if customer_code
                        else None
                    ),
                    alias=alias,
                    normalized_alias=(
                        normalize_text(alias)
                    ),
                    source=(
                        "CUSTOMER_HISTORY"
                        if customer_code
                        else "CATALOG"
                    ),
                )
            )

        warehouses = [
            Warehouse(
                code="MAN",
                name="Manchester Warehouse",
                city="Manchester",
                country="GB",
                priority=10,
            ),
            Warehouse(
                code="LON",
                name="London Warehouse",
                city="London",
                country="GB",
                priority=20,
            ),
            Warehouse(
                code="RTM",
                name="Rotterdam Warehouse",
                city="Rotterdam",
                country="NL",
                priority=30,
            ),
        ]

        session.add_all(warehouses)
        await session.flush()

        warehouse_by_code = {
            warehouse.code: warehouse
            for warehouse in warehouses
        }

        inventory_specs = [
            (
                "XTR-420",
                "MAN",
                "20",
            ),
            (
                "XTR-420",
                "LON",
                "11",
            ),
            (
                "XTR-420",
                "RTM",
                "120",
            ),
            (
                "BRK-090",
                "MAN",
                "10",
            ),
            (
                "BRK-090",
                "LON",
                "5",
            ),
            (
                "BRK-090",
                "RTM",
                "50",
            ),
        ]

        for sku, warehouse_code, qty in (
            inventory_specs
        ):
            session.add(
                Inventory(
                    product_id=(
                        product_by_sku[sku].id
                    ),
                    warehouse_id=(
                        warehouse_by_code[
                            warehouse_code
                        ].id
                    ),
                    on_hand=Decimal(qty),
                    reserved=Decimal("0"),
                )
            )

        current_contract = Contract(
            code="FA-2026-119",
            customer_id=northstar.id,
            title=(
                "Northstar Engineering "
                "Framework Agreement 2026"
            ),
            status="ACTIVE",
            currency="GBP",
            valid_from=date(2026, 1, 1),
            valid_to=date(2026, 12, 31),
            payment_terms="NET_30",
        )

        old_contract = Contract(
            code="FA-2025-044",
            customer_id=northstar.id,
            title=(
                "Northstar Engineering "
                "Framework Agreement 2025"
            ),
            status="EXPIRED",
            currency="GBP",
            valid_from=date(2025, 1, 1),
            valid_to=date(2025, 12, 31),
            payment_terms="NET_30",
        )

        session.add_all(
            [
                current_contract,
                old_contract,
            ]
        )

        await session.flush()

        session.add_all(
            [
                ContractPrice(
                    contract_id=current_contract.id,
                    product_id=(
                        product_by_sku[
                            "XTR-420"
                        ].id
                    ),
                    unit_price=Decimal(
                        "288.00"
                    ),
                    min_quantity=Decimal("1"),
                ),
                ContractPrice(
                    contract_id=current_contract.id,
                    product_id=(
                        product_by_sku[
                            "BRK-090"
                        ].id
                    ),
                    unit_price=Decimal(
                        "165.00"
                    ),
                    min_quantity=Decimal("1"),
                ),
                ContractPrice(
                    contract_id=old_contract.id,
                    product_id=(
                        product_by_sku[
                            "XTR-420"
                        ].id
                    ),
                    unit_price=Decimal(
                        "300.00"
                    ),
                    min_quantity=Decimal("1"),
                ),
                ContractPrice(
                    contract_id=old_contract.id,
                    product_id=(
                        product_by_sku[
                            "BRK-090"
                        ].id
                    ),
                    unit_price=Decimal(
                        "170.00"
                    ),
                    min_quantity=Decimal("1"),
                ),
            ]
        )

        rng = random.Random(20260923)

        history_start = datetime(
            2025,
            1,
            1,
            tzinfo=UTC,
        )

        fixed_orders = [
            (
                northstar,
                [
                    (
                        product_by_sku[
                            "XTR-420"
                        ],
                        Decimal("20"),
                        Decimal("288.00"),
                        "XTR Pump",
                    ),
                    (
                        product_by_sku[
                            "BRK-090"
                        ],
                        Decimal("10"),
                        Decimal("165.00"),
                        "BRK-90",
                    ),
                ],
            ),
            (
                northstar,
                [
                    (
                        product_by_sku[
                            "XTR-420"
                        ],
                        Decimal("12"),
                        Decimal("288.00"),
                        "Same pump as last month",
                    ),
                ],
            ),
            (
                northstar,
                [
                    (
                        product_by_sku[
                            "BRK-090"
                        ],
                        Decimal("25"),
                        Decimal("165.00"),
                        "Heavy Brake",
                    ),
                ],
            ),
            (
                northstar,
                [
                    (
                        product_by_sku[
                            "XTR-420"
                        ],
                        Decimal("18"),
                        Decimal("288.00"),
                        "XTR-42",
                    ),
                ],
            ),
            (
                northstar,
                [
                    (
                        product_by_sku[
                            "XTR-420"
                        ],
                        Decimal("10"),
                        Decimal("288.00"),
                        "Industrial XTR",
                    ),
                    (
                        product_by_sku[
                            "BRK-090"
                        ],
                        Decimal("6"),
                        Decimal("165.00"),
                        "Brake Kit 90",
                    ),
                ],
            ),
        ]

        async def add_history_order(
            order_index: int,
            customer: Customer,
            items: list,
            ordered_at: datetime,
        ):
            order = HistoricalOrder(
                order_number=(
                    f"HIST-{order_index:05d}"
                ),
                customer_id=customer.id,
                ordered_at=ordered_at,
                currency="GBP",
                total=Decimal("0.00"),
                external_system="DEMO_ERP",
                external_id=(
                    f"LEGACY-{order_index:05d}"
                ),
            )

            session.add(order)
            await session.flush()

            total = Decimal("0.00")

            for line_number, item in enumerate(
                items,
                start=1,
            ):
                (
                    product,
                    quantity,
                    unit_price,
                    description,
                ) = item

                total += (
                    quantity * unit_price
                ).quantize(
                    Decimal("0.01")
                )

                session.add(
                    HistoricalOrderLine(
                        historical_order_id=(
                            order.id
                        ),
                        product_id=product.id,
                        line_number=line_number,
                        description=description,
                        quantity=quantity,
                        unit_price=unit_price,
                    )
                )

            order.total = total

        history_index = 1

        for customer, items in fixed_orders:
            await add_history_order(
                history_index,
                customer,
                items,
                history_start
                + timedelta(
                    days=300 + history_index
                ),
            )

            history_index += 1

        while history_index <= 150:
            customer = rng.choice(customers)

            selected_products = rng.sample(
                products,
                k=rng.randint(1, 3),
            )

            items = []

            for product in selected_products:
                quantity = Decimal(
                    str(
                        rng.randint(
                            1,
                            40,
                        )
                    )
                )

                multiplier = Decimal(
                    str(
                        rng.choice(
                            [
                                "0.90",
                                "0.95",
                                "1.00",
                            ]
                        )
                    )
                )

                unit_price = (
                    product.catalog_price
                    * multiplier
                ).quantize(
                    Decimal("0.01")
                )

                items.append(
                    (
                        product,
                        quantity,
                        unit_price,
                        product.name,
                    )
                )

            await add_history_order(
                history_index,
                customer,
                items,
                history_start
                + timedelta(
                    days=rng.randint(
                        1,
                        600,
                    )
                ),
            )

            history_index += 1

        await session.commit()

        print(
            "Atlas Industrial Systems "
            "seed completed successfully."
        )

        print(
            "Customers: 20"
        )

        print(
            "Products: 10"
        )

        print(
            "Warehouses: 3"
        )

        print(
            "Historical orders: 150"
        )

        print(
            "Northstar current contract: "
            "FA-2026-119"
        )


if __name__ == "__main__":
    asyncio.run(seed())