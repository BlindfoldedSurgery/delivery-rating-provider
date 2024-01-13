from dataclasses import dataclass
from typing import Self, Tuple

from provider.takeaway.models.common import ShippingType, PaymentMethod


@dataclass
class PaymentFee:
    name: PaymentMethod
    type: str
    value: int
    min_value: int | None
    max_value: int | None
    shipping_type: ShippingType | None

    @classmethod
    def from_item(cls, item: Tuple[str, dict]) -> Self:
        name, d = item
        return cls(
            PaymentMethod.from_key(name),
            d["type"],
            d["value"],
            d.get("minValue"),
            d.get("maxValue"),
            ShippingType.from_key(d["shippingType"]) if d.get("shippingType") else None,
        )


@dataclass
class Message:
    name: str
    messages: list[str]

    @classmethod
    def from_item(cls, item: Tuple[str, list[str]]) -> Self:
        return cls(*item)


@dataclass
class Issuer:
    pass

    @classmethod
    def from_dict(cls, _: dict) -> Self:
        return cls()


@dataclass
class Payment:
    methods: list[PaymentMethod]
    payment_method_fees: dict  # TODO
    fees: list[PaymentFee]
    messages: list[Message]
    issuers: list[Issuer]

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(
            [PaymentMethod.from_key(p) for p in d["methods"]],
            d["paymentMethodFees"],
            [PaymentFee.from_item(p) for p in d["paymentMethodFees"].items()],
            [Message.from_item(m) for m in d["messages"].items()],
            [Issuer.from_dict(i) for i in d["issuers"]],
        )
