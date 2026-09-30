from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    ordernexa_transaction_id = fields.Char(
        string="OrderNexa Transaction",
        index=True,
        copy=False,
    )

    ordernexa_idempotency_key = fields.Char(
        string="OrderNexa Idempotency Key",
        index=True,
        copy=False,
    )

    _ordernexa_idempotency_unique = models.Constraint(
        "UNIQUE(ordernexa_idempotency_key)",
        "OrderNexa idempotency key must be unique.",
    )