from dataclasses import dataclass
from enum import auto
from typing import Self

from provider.models.common import IdEnum


class HeroImageUrlType(IdEnum):
    STOCK = auto()
    CHAIN = auto()
    PROFESSIONAL = auto()
    UNKNOWN = auto()
    OWN = auto()
    RANDOM = auto()


@dataclass
class BrandItem:
    name: str
    logo_url: str
    hero_image_url: str
    hero_image_url_type: HeroImageUrlType
    branch_name: str

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        hero_image_url_type = HeroImageUrlType.from_key(d["heroImageUrlType"])

        return cls(
            d["name"],
            d["logoUrl"],
            d["heroImageUrl"],
            hero_image_url_type,
            d["branchName"],
        )

    def hero_image_url_with_parameter(self, parameter: str) -> str:
        """
        examples:
            c_thumb,h_136,w_288/f_auto/q_auto
            ar_50:9,c_thumb,w_940/f_auto/q_auto
            ar_50:9,w_940/f_auto/q_auto

        pass an empty string to get the unmodified version of the hero image

        the c_thumb seems to shift the aspect ratio a bit to a lower height/wider width

        :param parameter: part of url path  which contains the sizes/ratios for the image (see examples)
        :return: formatted hero image url with given parameter
        """
        return self.hero_image_url.format(parameters=parameter)


@dataclass
class Brand:
    chain_id: str
    description: list[str]
    slogan: str
    logo_url: str
    header_image_url: str
    _item: BrandItem

    def __getattr__(self, item):
        return getattr(self._item, item)

    @classmethod
    def from_dict_item(cls, item: BrandItem, d: dict) -> Self:
        return cls(
            d["chainId"],
            d["description"],
            d["slogan"],
            d["logoUrl"],
            d["headerImageUrl"],
            item,
        )
