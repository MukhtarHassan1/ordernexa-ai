from app.models.enums import TransactionStatus


ALLOWED_TRANSITIONS: dict[
    TransactionStatus,
    set[TransactionStatus],
] = {
    TransactionStatus.RECEIVED: {
        TransactionStatus.TRIAGED,
        TransactionStatus.DUPLICATE_REVIEW,
        TransactionStatus.FAILED_MANUAL,
        TransactionStatus.CANCELLED,
    },

    TransactionStatus.TRIAGED: {
        TransactionStatus.EXTRACTED,
        TransactionStatus.DUPLICATE_REVIEW,
        TransactionStatus.FAILED_RETRYABLE,
        TransactionStatus.FAILED_MANUAL,
    },

    TransactionStatus.DUPLICATE_REVIEW: {
        TransactionStatus.TRIAGED,
        TransactionStatus.CANCELLED,
        TransactionStatus.FAILED_MANUAL,
    },

    TransactionStatus.EXTRACTED: {
        TransactionStatus.CUSTOMER_RESOLUTION,
        TransactionStatus.FAILED_RETRYABLE,
        TransactionStatus.FAILED_MANUAL,
    },

    TransactionStatus.CUSTOMER_RESOLUTION: {
        TransactionStatus.PRODUCT_RESOLUTION,
        TransactionStatus.DUPLICATE_REVIEW,
        TransactionStatus.WAITING_CUSTOMER,
        TransactionStatus.FAILED_MANUAL,
    },

    TransactionStatus.PRODUCT_RESOLUTION: {
        TransactionStatus.PRICING_CHECK,
        TransactionStatus.WAITING_CUSTOMER,
        TransactionStatus.FAILED_MANUAL,
    },

    TransactionStatus.PRICING_CHECK: {
        TransactionStatus.INVENTORY_CHECK,
        TransactionStatus.APPROVAL_REQUIRED,
        TransactionStatus.FAILED_MANUAL,
    },

    TransactionStatus.INVENTORY_CHECK: {
        TransactionStatus.CREDIT_CHECK,
        TransactionStatus.APPROVAL_REQUIRED,
        TransactionStatus.WAITING_CUSTOMER,
    },

    TransactionStatus.CREDIT_CHECK: {
        TransactionStatus.READY,
        TransactionStatus.APPROVAL_REQUIRED,
        TransactionStatus.FAILED_MANUAL,
    },

    TransactionStatus.READY: {
        TransactionStatus.APPROVAL_REQUIRED,
        TransactionStatus.ERP_PENDING,
    },

    TransactionStatus.APPROVAL_REQUIRED: {
        TransactionStatus.READY,
        TransactionStatus.ERP_PENDING,
        TransactionStatus.WAITING_CUSTOMER,
        TransactionStatus.CANCELLED,
    },

    TransactionStatus.WAITING_CUSTOMER: {
        TransactionStatus.TRIAGED,
        TransactionStatus.CUSTOMER_RESOLUTION,
        TransactionStatus.PRODUCT_RESOLUTION,
        TransactionStatus.READY,
        TransactionStatus.CANCELLED,
    },

    TransactionStatus.ERP_PENDING: {
        TransactionStatus.ERP_CREATED,
        TransactionStatus.BLOCKED_UNCERTAIN,
        TransactionStatus.FAILED_RETRYABLE,
        TransactionStatus.FAILED_MANUAL,
    },

    TransactionStatus.ERP_CREATED: {
        TransactionStatus.DOWNSTREAM_SYNC,
        TransactionStatus.DEGRADED,
    },

    TransactionStatus.DOWNSTREAM_SYNC: {
        TransactionStatus.VERIFIED,
        TransactionStatus.DEGRADED,
        TransactionStatus.FAILED_RETRYABLE,
    },

    TransactionStatus.VERIFIED: {
        TransactionStatus.COMPLETED,
        TransactionStatus.DEGRADED,
    },

    TransactionStatus.DEGRADED: {
        TransactionStatus.RECOVERY_PENDING,
        TransactionStatus.FAILED_MANUAL,
    },

    TransactionStatus.BLOCKED_UNCERTAIN: {
        TransactionStatus.RECOVERY_PENDING,
        TransactionStatus.FAILED_MANUAL,
    },

    TransactionStatus.FAILED_RETRYABLE: {
        TransactionStatus.RECOVERY_PENDING,
        TransactionStatus.FAILED_MANUAL,
    },

    TransactionStatus.RECOVERY_PENDING: {
        TransactionStatus.TRIAGED,
        TransactionStatus.EXTRACTED,
        TransactionStatus.CUSTOMER_RESOLUTION,
        TransactionStatus.PRODUCT_RESOLUTION,
        TransactionStatus.PRICING_CHECK,
        TransactionStatus.INVENTORY_CHECK,
        TransactionStatus.CREDIT_CHECK,
        TransactionStatus.ERP_PENDING,
        TransactionStatus.DOWNSTREAM_SYNC,
        TransactionStatus.VERIFIED,
        TransactionStatus.FAILED_MANUAL,
    },

    TransactionStatus.FAILED_MANUAL: {
        TransactionStatus.RECOVERY_PENDING,
        TransactionStatus.CANCELLED,
    },

    TransactionStatus.COMPLETED: set(),
    TransactionStatus.CANCELLED: set(),
}


class InvalidStateTransition(ValueError):
    pass


def validate_transition(
    current: TransactionStatus,
    target: TransactionStatus,
) -> None:
    allowed = ALLOWED_TRANSITIONS.get(current, set())

    if target not in allowed:
        raise InvalidStateTransition(
            f"Invalid transition: {current.value} -> {target.value}"
        )