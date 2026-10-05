# Subworker 和 BT 对等连接绑定到选中的 Network

用户在设置里选中若干 Network 后，每个 HTTP、FTP Subworker 的连接和每个 BT 对等连接都从其中一个 Network 出去，
一个文件同时用上 Wi-Fi 和 USB 共享的手机等多条线路。做法参考 [Plexo](https://github.com/anmolkapil/plexo)（MIT）：
不装虚拟网卡、不改路由、不要管理员权限，只把 socket 绑到 Network 上。

选择是全局的 Settings，不是 Task Options：libtorrent 的出口设置按会话生效，一个开关也更好解释。一个都不选时行为和以前一样。

## 绑定方式

| 系统 | HTTP（wreq） | FTP（自建 socket） | BT（libtorrent `outgoing_interfaces`） |
|---|---|---|---|
| Linux | `interface`（SO_BINDTODEVICE）+ 源地址 | SO_BINDTODEVICE + 源地址 | 设备名 |
| macOS | `interface`（IP_BOUND_IF）+ 源地址 | 源地址 | IPv4 地址 |
| Windows | 源地址（wreq 在 Windows 上不支持 `interface`） | 源地址 | IPv4 地址 |

Linux 只按目标地址选出口，只绑源地址时包仍从默认路由出去，必须把 socket 钉在设备上。非特权 SO_BINDTODEVICE 需要
内核 5.7+，应用要求的 glibc 2.35+ 发行版都满足。macOS、Windows 按源地址就能选出口。Windows 上 libtorrent 认的设备名
和 Qt 的接口名对不上，所以 BT 在 macOS、Windows 都用 IPv4 地址。

## Subworker 怎么分到 Network

1. 没有 Network 的 Subworker（新建、恢复、原 Network 断开或被取消选择）取未完成 Subworker 最少的 Network。
2. 从跑完的 Subworker 分裂出来的 Subworker 接手它的 Network：快的 Network 跑完得早，就能分到文件的更多部分。
3. 一次尝试失败的 Subworker 换到下一个选中的 Network，坏掉的 Network 不会拖住下载的尾巴。

Subworker 用哪个 Network 不写进 `.ghd`，每次 Task Run 重新分配。每次尝试都重新探测 Network，所以地址变化、插拔网线
会在下一次重试时生效。

## Considered Options

- **按 Task 选 Network**：要给 Task Options、编辑卡片、Android 字段和浏览器扩展都加字段，BT 又没法按 Task 区分出口。
- **像 Plexo 那样拆成固定大小的块，空闲连接领下一块**：要换掉现有的分裂式调度和 `.ghd` 格式；分裂时接手 Network 已经能让快的
  Network 多干活。
- **只绑源地址**：Linux 上不起作用。

## Consequences

- DNS、新建 Task 时的解析、BT 的 Tracker 和 DHT 仍走默认路由；HTTP 每次 Task Run 开头的重定向探测走第一个选中的 Network。
- 两个 Network 接在同一个路由器后面（比如同一台路由器的 Wi-Fi 和网线）不会更快，总带宽还是那一条宽带。
- Windows 插网线时会关掉 Wi-Fi，要在组策略 Windows Connection Manager 下把 “Minimize the number of simultaneous
  connections to the Internet or a Windows Domain” 设为已禁用。
- Windows 上只有 IPv4 的 Network 连优先 IPv6 的服务器时，wreq 不给 IPv6 连接绑源地址，这个 Subworker 实际走默认路由。
- FTP 走 SOCKS 代理时连接都去代理，不挑 Network。
- M3U8、MPEG-DASH 由 N_m3u8DL-RE 下载，eD2k 由 Kelpie 下载，都不经过 Network。
- macOS、Windows 上 BT 只能经选中的 Network 连 IPv4 对等方。
- Android 不提供这项设置。
