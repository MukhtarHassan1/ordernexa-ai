import hmac
import json
import os

from odoo import (
    Command,
    http,
)
from odoo.http import (
    Response,
    request,
)


def json_response(
    payload: dict,
    status: int = 200,
):
    return Response(
        json.dumps(
            payload,
            default=str,
        ),
        status=status,
        content_type="application/json",
    )


def authorized() -> bool:
    expected = os.getenv(
        "ORDERNEXA_ODOO_SHARED_SECRET",
        "",
    )

    provided = (
        request.httprequest.headers.get(
            "X-OrderNexa-Key",
            "",
        )
    )

    return bool(
        expected
        and provided
        and hmac.compare_digest(
            expected,
            provided,
        )
    )


def require_auth():
    if not authorized():
        return json_response(
            {
                "error": "unauthorized",
            },
            status=401,
        )

    return None


class OrderNexaController(
    http.Controller
):
    @http.route(
        "/ordernexa/api/health",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def health(self):
        auth_error = require_auth()

        if auth_error:
            return auth_error

        return json_response(
            {
                "status": "ok",
                "service": (
                    "ordernexa-odoo-connector"
                ),
                "database": (
                    request.env.cr.dbname
                ),
            }
        )

    @http.route(
        "/ordernexa/api/bootstrap",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def bootstrap(self):
        auth_error = require_auth()

        if auth_error:
            return auth_error

        Partner = (
            request.env["res.partner"]
            .sudo()
        )

        Product = (
            request.env["product.product"]
            .sudo()
        )

        partner = Partner.search(
            [
                (
                    "ref",
                    "=",
                    "CUST-1001",
                )
            ],
            limit=1,
        )

        if not partner:
            partner = Partner.create(
                {
                    "name": (
                        "Northstar "
                        "Engineering Ltd"
                    ),
                    "ref": "CUST-1001",
                    "is_company": True,
                    "email": (
                        "orders@"
                        "northstar-engineering.com"
                    ),
                }
            )

        product_specs = [
            {
                "default_code": "XTR-420",
                "name": (
                    "XTR Industrial Pump"
                ),
                "list_price": 340.00,
            },
            {
                "default_code": "BRK-090",
                "name": (
                    "Heavy Duty "
                    "Brake Assembly"
                ),
                "list_price": 180.00,
            },
        ]

        product_ids = []

        for spec in product_specs:
            product = Product.search(
                [
                    (
                        "default_code",
                        "=",
                        spec[
                            "default_code"
                        ],
                    )
                ],
                limit=1,
            )

            if not product:
                product = Product.create(
                    {
                        **spec,
                        "sale_ok": True,
                    }
                )

            product_ids.append(
                product.id
            )

        return json_response(
            {
                "status": "ready",
                "partner_id": partner.id,
                "product_ids": (
                    product_ids
                ),
            }
        )

    @http.route(
        "/ordernexa/api/sales-order",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def create_sales_order(self):
        auth_error = require_auth()

        if auth_error:
            return auth_error

        try:
            payload = json.loads(
                request
                .httprequest
                .get_data(
                    as_text=True
                )
                or "{}"
            )

            idempotency_key = payload.get(
                "idempotency_key"
            )

            transaction_id = payload.get(
                "transaction_id"
            )

            customer_code = payload.get(
                "customer_code"
            )

            po_number = payload.get(
                "po_number"
            )

            lines = payload.get(
                "lines",
                [],
            )

            if not idempotency_key:
                return json_response(
                    {
                        "error": (
                            "idempotency_key "
                            "is required"
                        )
                    },
                    status=422,
                )

            SaleOrder = (
                request.env["sale.order"]
                .sudo()
            )

            existing = SaleOrder.search(
                [
                    (
                        "ordernexa_idempotency_key",
                        "=",
                        idempotency_key,
                    )
                ],
                limit=1,
            )

            if existing:
                return json_response(
                    {
                        "id": existing.id,
                        "name": existing.name,
                        "state": (
                            existing.state
                        ),
                        "replayed": True,
                    }
                )

            partner = (
                request.env["res.partner"]
                .sudo()
                .search(
                    [
                        (
                            "ref",
                            "=",
                            customer_code,
                        )
                    ],
                    limit=1,
                )
            )

            if not partner:
                return json_response(
                    {
                        "error": (
                            "customer_not_found"
                        ),
                        "customer_code": (
                            customer_code
                        ),
                    },
                    status=422,
                )

            order_line_commands = []

            Product = (
                request.env[
                    "product.product"
                ]
                .sudo()
            )

            for line in lines:
                sku = line["sku"]

                product = Product.search(
                    [
                        (
                            "default_code",
                            "=",
                            sku,
                        )
                    ],
                    limit=1,
                )

                if not product:
                    return json_response(
                        {
                            "error": (
                                "product_not_found"
                            ),
                            "sku": sku,
                        },
                        status=422,
                    )

                order_line_commands.append(
                    Command.create(
                        {
                            "product_id": (
                                product.id
                            ),
                            "name": (
                                f"{sku} - "
                                f"{product.name}"
                            ),
                            "product_uom_qty": (
                                float(
                                    line[
                                        "quantity"
                                    ]
                                )
                            ),
                            "price_unit": (
                                float(
                                    line[
                                        "unit_price"
                                    ]
                                )
                            ),
                        }
                    )
                )

            order = SaleOrder.create(
                {
                    "partner_id": (
                        partner.id
                    ),
                    "client_order_ref": (
                        po_number
                    ),
                    "ordernexa_transaction_id": (
                        transaction_id
                    ),
                    "ordernexa_idempotency_key": (
                        idempotency_key
                    ),
                    "order_line": (
                        order_line_commands
                    ),
                }
            )

            order.action_confirm()

            return json_response(
                {
                    "id": order.id,
                    "name": order.name,
                    "state": order.state,
                    "replayed": False,
                },
                status=201,
            )

        except Exception as exc:
            request.env.cr.rollback()

            return json_response(
                {
                    "error": (
                        "odoo_execution_error"
                    ),
                    "message": str(exc),
                },
                status=500,
            )

    @http.route(
        (
            "/ordernexa/api/sales-order/"
            "<string:idempotency_key>"
        ),
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def verify_sales_order(
        self,
        idempotency_key,
    ):
        auth_error = require_auth()

        if auth_error:
            return auth_error

        order = (
            request.env["sale.order"]
            .sudo()
            .search(
                [
                    (
                        "ordernexa_idempotency_key",
                        "=",
                        idempotency_key,
                    )
                ],
                limit=1,
            )
        )

        if not order:
            return json_response(
                {
                    "error": "not_found",
                },
                status=404,
            )

        return json_response(
            {
                "id": order.id,
                "name": order.name,
                "state": order.state,
                "transaction_id": (
                    order
                    .ordernexa_transaction_id
                ),
                "idempotency_key": (
                    order
                    .ordernexa_idempotency_key
                ),
            }
        )