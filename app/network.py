from __future__ import annotations

import asyncio
import socket
import sys
from collections import Counter
from dataclasses import dataclass
from ssl import SSLContext

from app.config.cfg import cfg


@dataclass(frozen=True)
class Network:
    name: str
    label: str
    ipv4: str = ""
    ipv6: str = ""


def probeNetworks() -> list[Network]:
    # Android 从不选 Network，不必为它加载 QtNetwork
    from PySide6.QtNetwork import QAbstractSocket, QNetworkInterface

    Flag = QNetworkInterface.InterfaceFlag
    Protocol = QAbstractSocket.NetworkLayerProtocol
    networks = []
    for interface in QNetworkInterface.allInterfaces():
        flags = interface.flags()
        if not (flags & Flag.IsUp and flags & Flag.IsRunning) or flags & Flag.IsLoopBack:
            continue
        # 唯一本地地址（fd00::/8）出不了内网
        addresses = [
            entry.ip() for entry in interface.addressEntries()
            if entry.ip().isGlobal() and not entry.ip().isUniqueLocalUnicast()
        ]
        ipv4 = next((a.toString() for a in addresses if a.protocol() == Protocol.IPv4Protocol), "")
        ipv6 = next((a.toString() for a in addresses if a.protocol() == Protocol.IPv6Protocol), "")
        if ipv4 or ipv6:
            networks.append(Network(interface.name(), interface.humanReadableName(), ipv4, ipv6))
    return networks


def selectedNetworks() -> list[Network]:
    names = cfg.networks.value
    if not names:
        return []
    return [network for network in probeNetworks() if network.name in names]


def nextNetwork(networks: list[Network], current: str, counts: Counter[str], hasFailed: bool) -> Network | None:
    if not networks:
        return None
    names = [network.name for network in networks]
    if current in names:
        index = names.index(current)
        return networks[(index + 1) % len(networks)] if hasFailed else networks[index]
    return min(networks, key=lambda network: counts[network.name])


async def openConnection(
    host: str, port: int, network: Network, ssl: SSLContext | None = None,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    loop = asyncio.get_running_loop()
    lastError: OSError | None = None
    for family, kind, proto, _, address in await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM):
        localIp = {socket.AF_INET: network.ipv4, socket.AF_INET6: network.ipv6}.get(family)
        if not localIp:
            continue
        sock = socket.socket(family, kind, proto)
        try:
            sock.setblocking(False)
            # Linux 只按目标地址选出口，绑源地址不够，要把 socket 钉在设备上
            if sys.platform == "linux":
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, network.name.encode())
            sock.bind((localIp, 0))
            await loop.sock_connect(sock, address)
        except OSError as e:
            sock.close()
            lastError = e
        except BaseException:
            sock.close()
            raise
        else:
            return await asyncio.open_connection(sock=sock, ssl=ssl, server_hostname=host if ssl else None)
    raise lastError or OSError(f"{network.label} 没有能连到 {host} 的地址")
