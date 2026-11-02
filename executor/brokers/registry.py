"""券商注册表：新增一家券商时，只需在这里登记它的适配器。"""
from __future__ import annotations

from ..adb import Adb
from .base import BrokerAdapter, BrokerSpec
from .ths import SPEC as THS_SPEC, ThsAdapter
from .zhangle import SPEC as ZHANGLE_SPEC, ZhangleAdapter

_SPECS: dict[str, BrokerSpec] = {
    ZHANGLE_SPEC.id: ZHANGLE_SPEC,
    THS_SPEC.id: THS_SPEC,
}
_ADAPTERS: dict[str, type[BrokerAdapter]] = {
    ZHANGLE_SPEC.id: ZhangleAdapter,
    THS_SPEC.id: ThsAdapter,
}


def specs() -> list[BrokerSpec]:
    return list(_SPECS.values())


def spec(broker: str) -> BrokerSpec:
    try:
        return _SPECS[broker]
    except KeyError as exc:
        raise ValueError(f"暂不支持该券商: {broker}") from exc


def adapter(broker: str, adb: Adb | None = None) -> BrokerAdapter:
    return _ADAPTERS[spec(broker).id](adb)
