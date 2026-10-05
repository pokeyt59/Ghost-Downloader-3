"""BT 的对等连接从选中的 Network 出去：Linux 用设备名，macOS、Windows 用 IPv4 地址。

Seam: BTSession._networkSettings（libtorrent outgoing_interfaces）
"""
from __future__ import annotations

import pytest

from app.network import Network
from features.bittorrent_pack.session import BTSession

NETWORKS = [
    Network("wlan0", "Wi-Fi", "192.168.1.5", "2001:db8::5"),
    Network("usb0", "iPhone USB", ipv6="2001:db8::2"),
]


@pytest.fixture
def settingsOn(monkeypatch):
    monkeypatch.setattr("features.bittorrent_pack.session.selectedNetworks", lambda: NETWORKS)

    def build(platform):
        monkeypatch.setattr("features.bittorrent_pack.session.sys.platform", platform)
        return BTSession()._networkSettings()
    return build


def test_linux_binds_peers_to_devices(settingsOn):
    assert settingsOn("linux") == {"outgoing_interfaces": "wlan0,usb0"}


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_others_bind_peers_to_ipv4_addresses(settingsOn, platform):
    assert settingsOn(platform) == {"outgoing_interfaces": "192.168.1.5"}


def test_no_selection_leaves_peers_on_default_route(monkeypatch):
    monkeypatch.setattr("features.bittorrent_pack.session.selectedNetworks", lambda: [])

    assert BTSession()._networkSettings() == {"outgoing_interfaces": ""}
