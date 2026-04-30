import pytest
from scrapers.daily_close import PriceProvider, ProviderUnavailable, SUCCESS_THRESHOLD


def test_provider_abstract_raises_on_fetch():
    """抽象類別 fetch() 沒實作時應 raise NotImplementedError。"""
    p = PriceProvider()
    with pytest.raises(NotImplementedError):
        p.fetch(["2330"], None)


def test_provider_unavailable_is_an_exception():
    """ProviderUnavailable 是 Exception 子類。"""
    assert issubclass(ProviderUnavailable, Exception)


def test_success_threshold_is_80_percent():
    """門檻常數固定 0.80。"""
    assert SUCCESS_THRESHOLD == 0.80
