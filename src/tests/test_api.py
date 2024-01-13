import pytest

from provider.bot import get_restaurant_list_url, get_random_restaurants


@pytest.mark.asyncio
async def test_restaurant_retrieval_is_working_without_filter():
    url = get_restaurant_list_url(postal_code=64293)
    restaurants = await get_random_restaurants(url, count=1)
    assert len(restaurants) > 0


@pytest.mark.asyncio
async def test_restaurant_retrieval_is_working_with_filter():
    url = get_restaurant_list_url(postal_code=64293)
    restaurants = await get_random_restaurants(url, count=1, filter_fn=lambda _: True)
    assert len(restaurants) > 0
