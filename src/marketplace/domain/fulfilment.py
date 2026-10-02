"""Fulfilment types from J40. Provision types install via J32; the rest are orders (J48)."""

FULFILMENT_TYPES: frozenset[str] = frozenset(
    {
        "SHIP_PHYSICAL",
        "DELIVER_DIGITAL",
        "LICENSE_SOFTWARE",
        "PROVISION_SOFTWARE",
        "PROVISION_CLOUD",
        "STREAM_LMS_COURSE",
        "DELIVER_MULTIMEDIA",
        "DISPATCH_SERVICE",
        "BOOK_APPOINTMENT",
    }
)

PROVISION_TYPES: frozenset[str] = frozenset({"PROVISION_SOFTWARE", "PROVISION_CLOUD"})

ADDRESS_REQUIRED: frozenset[str] = frozenset(
    {"SHIP_PHYSICAL", "DISPATCH_SERVICE", "BOOK_APPOINTMENT"}
)
