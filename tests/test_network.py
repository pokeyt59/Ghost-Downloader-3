"""Network：Subworker 挑 Network 的规则、探测结果、wreq 客户端的绑定参数、自建连接、设置卡片。

Seam: app.network（nextNetwork、probeNetworks、openConnection）、app.client.buildClient、NetworkSettingCard
"""
from __future__ import annotations

import asyncio
import sys
from collections import Counter
from ipaddress import IPv4Address, IPv6Address

import pytest

from app.client import buildClient
from app.config.cfg import cfg
from app.network import Network, nextNetwork, openConnection, probeNetworks

WIFI = Network("wlan0", "Wi-Fi", "192.168.1.5")
PHONE = Network("usb0", "iPhone USB", "172.20.10.2", "2001:db8::2")


class TestNextNetwork:

    def test_no_selection_means_default_route(self):
        assert nextNetwork([], "wlan0", Counter(), hasFailed=False) is None

    def test_new_subworker_takes_least_used(self):
        assert nextNetwork([WIFI, PHONE], "", Counter({"wlan0": 2, "usb0": 1}), hasFailed=False) == PHONE

    def test_keeps_its_network(self):
        assert nextNetwork([WIFI, PHONE], "wlan0", Counter({"wlan0": 5}), hasFailed=False) == WIFI

    def test_failure_moves_to_next(self):
        assert nextNetwork([WIFI, PHONE], "wlan0", Counter(), hasFailed=True) == PHONE
        assert nextNetwork([WIFI, PHONE], "usb0", Counter(), hasFailed=True) == WIFI

    def test_vanished_network_is_replaced(self):
        assert nextNetwork([PHONE], "wlan0", Counter({"usb0": 3}), hasFailed=False) == PHONE


def test_probe_skips_loopback_and_networks_without_address():
    networks = probeNetworks()

    assert all(network.name != "lo" for network in networks)
    assert all(network.ipv4 or network.ipv6 for network in networks)


class TestBuildClient:

    @pytest.fixture
    def configFor(self, monkeypatch):
        captured = {}
        monkeypatch.setattr("app.client.Client", lambda **config: captured.update(config))

        def build(platform, network):
            captured.clear()
            monkeypatch.setattr("app.client.sys.platform", platform)
            buildClient(emulation=None, network=network)
            return dict(captured)
        return build

    def test_linux_pins_device_and_source(self, configFor):
        config = configFor("linux", PHONE)

        assert config["interface"] == "usb0"
        assert config["local_addresses"] == (IPv4Address("172.20.10.2"), IPv6Address("2001:db8::2"))

    def test_windows_binds_source_only(self, configFor):
        config = configFor("win32", WIFI)

        assert "interface" not in config
        assert config["local_addresses"] == (IPv4Address("192.168.1.5"), None)

    def test_no_network_binds_nothing(self, configFor):
        config = configFor("linux", None)

        assert "interface" not in config and "local_addresses" not in config


class TestOpenConnection:

    @pytest.mark.skipif(sys.platform != "linux", reason="127.0.0.2 只在 Linux 的 lo 上默认可用")
    async def test_binds_device_and_source(self):
        peers = []

        async def onClient(reader, writer):
            peers.append(writer.get_extra_info("peername")[0])
            writer.close()

        server = await asyncio.start_server(onClient, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        reader, writer = await openConnection("127.0.0.1", port, Network("lo", "lo", "127.0.0.2"))
        await reader.read()
        writer.close()
        server.close()
        await server.wait_closed()

        assert peers == ["127.0.0.2"]

    async def test_network_without_matching_family_fails(self):
        with pytest.raises(OSError):
            await openConnection("127.0.0.1", 9, Network("lo", "lo", ipv6="::1"))


class TestNetworkSettingCard:

    @pytest.fixture
    def card(self, qtbot, monkeypatch):
        from app.view.components.setting_cards import NetworkSettingCard

        monkeypatch.setattr("app.view.components.setting_cards.probeNetworks", lambda: [WIFI, PHONE])
        monkeypatch.setattr(cfg, "save", lambda: None)
        saved = cfg.networks.value
        cfg.networks.value = ["eth9"]
        card = NetworkSettingCard()
        qtbot.addWidget(card)
        yield card
        cfg.networks.value = saved

    def test_lists_probed_and_disconnected_selected_networks(self, card):
        assert [row.nameLabel.text() for row in card._rows] == ["Wi-Fi", "iPhone USB", "eth9"]
        assert card._rows[2].addressLabel.text() == "未连接"
        assert card._rows[2].switchButton.isChecked()

    def test_toggling_rows_updates_setting_and_choice(self, card):
        card._rows[2].switchButton.setChecked(False)
        card._rows[0].switchButton.setChecked(True)
        card._rows[1].switchButton.setChecked(True)

        assert cfg.networks.value == ["wlan0", "usb0"]
        assert card.choiceLabel.text() == "Wi-Fi + iPhone USB"

    def test_empty_choice_reads_system_default(self, card):
        card._rows[2].switchButton.setChecked(False)

        assert cfg.networks.value == []
        assert card.choiceLabel.text() == "系统默认"
