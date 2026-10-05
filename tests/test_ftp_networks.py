"""FTP Subworker 的控制连接和数据连接都从选中的 Network 出去；走 SOCKS 代理时不挑 Network。

Seam: FtpConnectionInfo.connect / FtpClient._open_connection，本地 aioftp 服务器
"""
from __future__ import annotations

import asyncio
import sys

import aioftp
import pytest

import features.ftp_pack.task as ftpTask
from app.config.cfg import cfg
from app.models.task import TaskError, TaskOptions
from app.network import Network
from features.ftp_pack.pack import FtpParser
from tests.helpers import buildFileContent, runStep

LOOPBACK = Network("lo", "lo", "127.0.0.2")


@pytest.fixture
def directProxy():
    saved = cfg.proxyServer.value
    cfg.proxyServer.value = "Off"
    yield
    cfg.proxyServer.value = saved


@pytest.fixture
async def ftpServer(tmp_path, directProxy):
    root = tmp_path / "root"
    root.mkdir()
    content = buildFileContent(300_000)
    (root / "file.bin").write_bytes(content)
    peers = []

    class Server(aioftp.Server):
        async def dispatcher(self, reader, writer):
            peers.append(writer.get_extra_info("peername")[0])
            return await super().dispatcher(reader, writer)

    server = Server([aioftp.User(base_path=root)])
    await server.start("127.0.0.1", 0)
    port = server.server.sockets[0].getsockname()[1]
    yield f"ftp://127.0.0.1:{port}/file.bin", content, peers
    await server.close()


@pytest.mark.skipif(sys.platform != "linux", reason="127.0.0.2 只在 Linux 的 lo 上默认可用")
async def test_subworkers_leave_from_selected_network(ftpServer, tmp_path, monkeypatch):
    url, content, peers = ftpServer
    task = await FtpParser().parse(TaskOptions(url=url, outputFolder=tmp_path / "out", subworkerCount=2))
    (tmp_path / "out").mkdir()
    peers.clear()

    opened = []
    realOpenConnection = ftpTask.openConnection

    async def openConnection(host, port, network, ssl=None):
        opened.append(network.name)
        return await realOpenConnection(host, port, network, ssl=ssl)

    monkeypatch.setattr("features.ftp_pack.task.selectedNetworks", lambda: [LOOPBACK])
    monkeypatch.setattr("features.ftp_pack.task.openConnection", openConnection)

    await asyncio.wait_for(runStep(task.steps[0]), timeout=10)

    assert (tmp_path / "out" / task.name).read_bytes() == content
    assert set(peers) == {"127.0.0.2"}
    assert len(opened) == 2 * len(peers)


async def test_socks_proxy_leaves_network_unused(monkeypatch):
    built = []

    class StubClient:
        def __init__(self, *, network=None, **kwargs):
            built.append(network)

        async def connect(self, host, port):
            raise ConnectionError("stub")

        def close(self):
            pass

    saved = cfg.proxyServer.value
    cfg.proxyServer.value = "socks5://127.0.0.1:1080"
    monkeypatch.setattr("features.ftp_pack.task.FtpClient", StubClient)
    info = ftpTask.FtpConnectionInfo(
        scheme="ftp", host="127.0.0.1", port=21, username="anonymous", password="", sourcePath="/",
    )
    try:
        with pytest.raises(TaskError):
            await info.connect(LOOPBACK)
    finally:
        cfg.proxyServer.value = saved

    assert built == [None]
