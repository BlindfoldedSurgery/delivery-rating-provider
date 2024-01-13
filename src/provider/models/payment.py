from dataclasses import dataclass
from typing import Self, Tuple

from provider.models.common import ShippingType, PaymentMethod


@dataclass
class PaymentFee:
    name: str
    type: str
    value: int
    min_value: int
    max_value: int
    shipping_type: ShippingType

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(
            d["name"],
            d["type"],
            d["value"],
            d["minValue"],
            d["maxValue"],
            ShippingType.from_key(d["shippingType"]),
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
            [PaymentFee.from_dict(p) for p in d["paymentMethodFees"]],
            [Message.from_item(m) for m in d["messages"].items()],
            [Issuer.from_dict(i) for i in d["issuers"]],
        )
