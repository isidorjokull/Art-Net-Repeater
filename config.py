"""Load and validate config from a TOML file, merged with CLI overrides."""
from dataclasses import dataclass, field

try:
    import tomllib  # stdlib Python >= 3.11
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # pip install tomli for 3.10
    except ModuleNotFoundError:
        sys.exit("Python 3.11+ required, or install 'tomli': pip install tomli")

from mapper import Rule

BROADCAST_SENTINEL = "broadcast"
DEFAULT_BROADCAST_IP = "255.255.255.255"


@dataclass
class Config:
    listen_ip: str
    target_ip: str          # resolved IP or DEFAULT_BROADCAST_IP
    is_broadcast: bool
    port: int
    max_hz: float | None    # output framerate cap per universe; None = unlimited
    rules: list[Rule] = field(default_factory=list)


def _parse_rule(raw: dict, index: int) -> Rule:
    name = raw.get("name", f"rule[{index}]")
    try:
        src_universe = int(raw["src_universe"])
        dst_universe = int(raw["dst_universe"])
        src_first_1, src_last_1 = raw["src_channels"]
        dst_first_1, dst_last_1 = raw["dst_channels"]
    except KeyError as e:
        raise ValueError(f"{name}: missing field {e}") from None
    except (TypeError, ValueError):
        raise ValueError(f"{name}: src_channels and dst_channels must be [first, last] pairs")

    src_len = src_last_1 - src_first_1 + 1
    dst_len = dst_last_1 - dst_first_1 + 1
    if src_len != dst_len:
        raise ValueError(
            f"{name}: src range ({src_first_1}–{src_last_1}, len={src_len}) "
            f"must match dst range ({dst_first_1}–{dst_last_1}, len={dst_len})"
        )
    if src_first_1 < 1 or src_last_1 > 512 or dst_first_1 < 1 or dst_last_1 > 512:
        raise ValueError(f"{name}: channel numbers must be between 1 and 512")

    merge = raw.get("merge", "ltp").lower()
    if merge not in ("ltp", "htp"):
        raise ValueError(f"{name}: merge must be 'ltp' or 'htp', got '{merge}'")

    target_ip = raw.get("target_ip", None)
    if target_ip is not None:
        target_ip = str(target_ip).strip()
        if not target_ip:
            target_ip = None

    return Rule(
        name=name,
        src_universe=src_universe,
        src_first=src_first_1 - 1,   # convert to 0-indexed
        src_last=src_last_1 - 1,
        dst_universe=dst_universe,
        dst_first=dst_first_1 - 1,
        dst_last=dst_last_1 - 1,
        merge=merge,
        target_ip=target_ip,
    )


def load(path: str, cli_overrides: dict) -> "Config":
    """
    Load config from a TOML file and apply CLI overrides.
    Raises ValueError on bad config so callers can decide how to handle it.
    """
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except FileNotFoundError:
        raise ValueError(f"Config file not found: {path}")
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"Config parse error in {path}: {e}")

    net = raw.get("network", {})
    listen_ip = cli_overrides.get("listen_ip") or net.get("listen_ip", "0.0.0.0")
    target_raw = cli_overrides.get("target_ip") or net.get("target_ip", BROADCAST_SENTINEL)
    port = int(cli_overrides.get("port") or net.get("artnet_port", 6454))

    is_broadcast = target_raw.lower() == BROADCAST_SENTINEL
    target_ip = DEFAULT_BROADCAST_IP if is_broadcast else target_raw

    max_hz_raw = net.get("max_hz", None)
    if max_hz_raw is not None:
        try:
            max_hz = float(max_hz_raw)
        except (TypeError, ValueError):
            raise ValueError("network.max_hz must be a number")
        if max_hz <= 0:
            raise ValueError("network.max_hz must be a positive number")
    else:
        max_hz = None

    raw_rules = raw.get("rules", [])
    if not raw_rules:
        raise ValueError("Config has no [[rules]] — nothing to do.")

    rules = []
    for i, r in enumerate(raw_rules):
        rules.append(_parse_rule(r, i))  # ValueError propagates to caller

    return Config(
        listen_ip=listen_ip,
        target_ip=target_ip,
        is_broadcast=is_broadcast,
        port=port,
        max_hz=max_hz,
        rules=rules,
    )
