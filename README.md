# Art-Net Repeater

A lightweight Art-Net DMX repeater and merger. Receives Art-Net packets, remaps selected channel ranges to other universes or address offsets, and re-broadcasts — without disturbing any channels not covered by a rule.

Supports **LTP** (Latest Takes Precedence) and **HTP** (Highest Takes Precedence) merge modes per rule, a configurable output framerate limit, and an optional browser-based dashboard for live monitoring and configuration.

---

## Features

- Remap any channel range on any universe to any other universe/offset
- LTP / HTP merge mode per rule — behaves like a professional DMX merger
- Passthrough architecture — untouched channels are re-broadcast as received, no zero-injection
- Physical-byte loopback guard — the repeater ignores its own outgoing packets
- Output framerate cap (`max_hz`) — useful when receivers can't handle fast Art-Net rates
- Optional web dashboard: live Hz meters, editable rules, DMX level viewer (toggle on demand)
- Zero dependencies beyond the Python standard library

---

## Requirements

| | Minimum |
|---|---|
| Python | **3.11** or newer |
| OS | Linux, macOS, or Windows |
| Network | UDP port 6454 reachable |

> **Python 3.11 is required** because the project uses the built-in `tomllib` module (added in 3.11) to parse the TOML config file.

---

## Installation

### Linux / macOS

```bash
# 1. Clone the repository
git clone https://github.com/isidorjokull/Art-Net-Repeater.git
cd Art-Net-Repeater

# 2. Verify Python version (must be 3.11+)
python3 --version

# 3. Copy the example config and edit it
cp config.example.toml config.toml
nano config.toml   # or your editor of choice

# 4. Run
python3 repeater.py config.toml
```

### Windows

Python on Windows does not always install as `python3`. Use the command that works for your installation:

```powershell
# Check Python version — must be 3.11 or newer
python --version
# or
py --version

# Clone
git clone https://github.com/isidorjokull/Art-Net-Repeater.git
cd Art-Net-Repeater

# Copy and edit config
copy config.example.toml config.toml
notepad config.toml

# Run (use whichever python command works)
python repeater.py config.toml
# or
py repeater.py config.toml
```

> **Windows firewall:** On first run, Windows may prompt to allow Python through the firewall. Click **Allow access** — the repeater needs UDP port 6454 for Art-Net traffic.

> **Python version on Windows:** Download Python 3.11+ from [python.org](https://www.python.org/downloads/). During installation, check **"Add Python to PATH"**. The Microsoft Store version of Python works too.

> **No `python3` command:** On Windows, the command is usually `python` or `py`, not `python3`. If you see `'python3' is not recognized`, use `python` instead.

---

## Configuration

The config file is TOML format. Start from `config.example.toml`:

```toml
[network]
listen_ip   = "0.0.0.0"        # interface to listen on (0.0.0.0 = all)
target_ip   = "192.168.0.255"  # destination IP or "broadcast"
artnet_port = 6454              # Art-Net standard port
max_hz      = 44               # optional: max output framerate per universe

[[rules]]
name         = "My first rule"
src_universe = 0
src_channels = [1, 107]        # channel range to read (1-indexed, inclusive)
dst_universe = 1
dst_channels = [1, 107]        # must be same length as src_channels
merge        = "ltp"           # "ltp" or "htp"

[[rules]]
name         = "Mirror to high addresses"
src_universe = 0
src_channels = [1, 107]
dst_universe = 0
dst_channels = [300, 406]
merge        = "htp"
```

### Key settings

**`listen_ip`** — Which network interface to receive Art-Net on. Use `"0.0.0.0"` to listen on all interfaces. Use a specific IP (e.g. `"192.168.0.21"`) to restrict to one interface.

**`target_ip`** — Where to send output packets. Use a subnet broadcast like `"192.168.0.255"` to reach all devices on the network, or a specific device IP for unicast. The string `"broadcast"` sends to `255.255.255.255`.

**`max_hz`** — Optional output framerate cap (frames per second per destination universe). Useful if a downstream DMX device can't handle the full incoming rate. The merger still processes every incoming frame internally — only the transmit rate is capped.

**`merge`** — Per-rule merge mode:
- `"ltp"` — Latest Takes Precedence. Destination channels are overwritten with the latest source values.
- `"htp"` — Highest Takes Precedence. Each channel outputs `max(passthrough_value, rule_value)`, recalculated every frame. Values decrease correctly when the source decreases.

### Channel numbering

All channel numbers in the config are **1-indexed** (channel 1 = DMX address 1). Ranges are inclusive. Source and destination ranges must be the same length — the repeater validates this on startup and on every config save.

---

## CLI Usage

```bash
python3 repeater.py [CONFIG] [OPTIONS]
```

| Argument | Default | Description |
|---|---|---|
| `CONFIG` | `config.toml` | Path to config file |
| `--listen-ip IP` | from config | Override `network.listen_ip` |
| `--target-ip IP` | from config | Override `network.target_ip` |
| `--port PORT` | from config | Override `network.artnet_port` |
| `--web [PORT]` | disabled | Enable web dashboard (default port 8080) |

```bash
# Headless — just forward, no UI
python3 repeater.py config.toml

# With web dashboard on default port 8080
python3 repeater.py config.toml --web

# Web dashboard on custom port
python3 repeater.py config.toml --web 9000

# Override network settings on the fly
python3 repeater.py config.toml --target-ip 192.168.1.255 --web
```

Stop with **Ctrl+C**.

---

## Web Dashboard

Start with `--web` and open `http://<host-ip>:8080` in a browser.

### Rules panel
- Edit rule names, universes, channel ranges, and merge mode inline
- Destination end channel auto-calculates from source range length — you only set start/end on the source side and the start on the destination
- **+** adds a new empty rule, **×** removes one
- **Save Rules** writes a new `config.toml` and hot-reloads the engine without restart

### Framerate limit
- The **Limit** field in the header sets `max_hz`
- Type a value and press Enter or click **Set** to apply immediately
- Clear the field and click **Set** to remove the limit (unlimited)

### DMX Viewer
- Off by default (saves resources — no level data is sent over SSE when hidden)
- Click **Show** to enable live channel bar graphs for universes touched by any rule
- Click **Hide** to stop the level stream

### Running the dashboard on a server
Use `tmux` or `screen` to keep the process alive after SSH disconnect:

```bash
tmux new-session -d -s artnet 'python3 repeater.py config.toml --web 8080'

# Attach later to see output
tmux attach -t artnet
```

### Updating from GitHub

```bash
# On the server
cd ~/Art-Net-Repeater
git pull

# Restart (kills old process in tmux and starts fresh)
tmux send-keys -t artnet C-c Enter
tmux send-keys -t artnet 'python3 repeater.py config.toml --web 8080' Enter
```

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'tomllib'`**
Your Python version is older than 3.11. Upgrade Python, or install the backport:
```bash
pip install tomli
```
Then edit the top of `config.py` — `tomli` is already listed as a fallback import.

**Port 6454 already in use**
Another Art-Net application is running on the same machine. Stop it, or use `--port` to pick a different port (note: non-standard ports won't communicate with standard Art-Net devices).

**No DMX output / repeater doesn't forward**
1. Check that the source is broadcasting to an address the repeater can receive (correct subnet, no firewall blocking UDP 6454)
2. Check the web dashboard — the `rx` counter in the header should be climbing if packets are arriving
3. Verify `target_ip` is a broadcast address reachable on the network (not a loopback like `127.x.x.x`)

**Source DMX glitching after adding the repeater**
The repeater re-broadcasts the full universe, which merges back with the source in DMX software that sums inputs. This is expected Art-Net behaviour. Solutions:
- Route the repeater output to a separate universe or subnet
- Use HTP merge mode — at equal values the output won't glitch
- The passthrough architecture ensures untouched channels are not zeroed by the repeater

**Web UI not accessible from another machine**
Ensure `listen_ip = "0.0.0.0"` (not `127.0.0.1`) and that the host firewall allows TCP on port 8080.
