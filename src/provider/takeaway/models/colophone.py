from dataclasses import dataclass
from typing import Self


@dataclass
class ChamberOfCommerce:
    issuer: str
    number: str

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(
            d["issuer"],
            d["number"],
        )


@dataclass
class ColophonData:
    branch_name: str
    restaurant_name: str
    street_name: str
    street_number: str
    postal_code: str
    city: str
    legal_entity: str
    legal_representative_name: str
    legal_name: str
    legal_entity_class: str | None
    email: str
    fax: str
    chamber_of_commerce: list[ChamberOfCommerce]
    vat_number: str | None
    dispute_resolution_link: str | None

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(
            d["branchName"],
            d["restaurantName"],
            d["streetName"],
            d["streetNumber"],
            d["postalCode"],
            d["city"],
            d.get("legalEntity"),
            d.get("legalRepresentativeName"),
            d.get("legalName"),
            d.get("legalEntityClass"),
            d.get("email"),
            d.get("fax"),
            [ChamberOfCommerce.from_dict(coc) for coc in d.get("chamberOfCommerce", [])],
            d.get("vatNumber"),
            d.get("disputeResolutionLink"),
        )


@dataclass
class Colophon:
    status: str
    data: ColophonData

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(
            d["status"],
            ColophonData.from_dict(d["data"]),
        )
