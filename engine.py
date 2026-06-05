"""Engine: runs the Art-Net repeater loop in a background thread."""
import socket
import threading
import time

from artnet import parse_artdmx, build_artdmx
from config import load
from mapper import update_and_merge


class Engine:
    def __init__(self, config_path: str, cli_overrides: dict):
        self._config_path = config_path
        self._cli_overrides = cli_overrides
        self._lock = threading.Lock()

        self._cfg = load(config_path, cli_overrides)
        self._paused = False
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        # Shared state (read by web layer, written by UDP thread)
        self._passthrough: dict[int, bytearray] = {}
        self._rule_states: dict[int, bytearray] = {}
        self._rx = 0
        self._tx = 0

        # Per-rule Hz tracking
        self._rule_counts: list[int] = [0] * len(self._cfg.rules)
        self._rule_hz: list[float] = [0.0] * len(self._cfg.rules)
        self._hz_last_time = time.monotonic()
        self._hz_thread: threading.Thread | None = None

        self._sock_rx: socket.socket | None = None
        self._sock_tx: socket.socket | None = None

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        self._open_sockets()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._hz_thread = threading.Thread(target=self._hz_ticker, daemon=True)
        self._hz_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._sock_rx:
            try:
                self._sock_rx.close()
            except OSError:
                pass

    def pause(self) -> None:
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        with self._lock:
            self._paused = False

    def reload(self) -> None:
        new_cfg = load(self._config_path, self._cli_overrides)
        with self._lock:
            self._cfg = new_cfg
            self._rule_states.clear()
            self._rule_counts = [0] * len(new_cfg.rules)
            self._rule_hz = [0.0] * len(new_cfg.rules)

    def run_forever(self) -> None:
        """Blocking version for headless mode — runs until KeyboardInterrupt."""
        self.start()
        try:
            while not self._stop_event.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    # ------------------------------------------------------------------ #
    # State properties (thread-safe reads for the web layer)              #
    # ------------------------------------------------------------------ #

    @property
    def status(self) -> dict:
        with self._lock:
            cfg = self._cfg
            rules_info = []
            for i, r in enumerate(cfg.rules):
                rules_info.append({
                    "name": r.name,
                    "src_u": r.src_universe,
                    "src_ch": [r.src_first + 1, r.src_last + 1],
                    "dst_u": r.dst_universe,
                    "dst_ch": [r.dst_first + 1, r.dst_last + 1],
                    "merge": r.merge,
                    "hz": round(self._rule_hz[i] if i < len(self._rule_hz) else 0, 1),
                })
            return {
                "running": self._thread is not None and self._thread.is_alive(),
                "paused": self._paused,
                "rx": self._rx,
                "tx": self._tx,
                "listen": f"{cfg.listen_ip}:{cfg.port}",
                "target": cfg.target_ip,
                "rules": rules_info,
            }

    @property
    def levels(self) -> dict:
        with self._lock:
            return {
                str(uni): list(buf)
                for uni, buf in self._passthrough.items()
            }

    @property
    def config_text(self) -> str:
        try:
            with open(self._config_path) as f:
                return f.read()
        except OSError:
            return ""

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _open_sockets(self) -> None:
        cfg = self._cfg
        rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass
        rx.bind((cfg.listen_ip, cfg.port))
        rx.settimeout(1.0)  # allows the stop_event to be checked

        tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        tx.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        self._sock_rx = rx
        self._sock_tx = tx

    def _loop(self) -> None:
        rx, tx = self._sock_rx, self._sock_tx
        while not self._stop_event.is_set():
            try:
                data, _ = rx.recvfrom(540)
            except socket.timeout:
                continue
            except OSError:
                break

            pkt = parse_artdmx(data)
            if pkt is None:
                continue

            with self._lock:
                cfg = self._cfg
                paused = self._paused

                base = bytearray(512)
                base[: len(pkt["dmx"])] = pkt["dmx"]
                self._passthrough[pkt["universe"]] = base
                self._rx += 1

                outputs = update_and_merge(
                    cfg.rules, self._rule_states,
                    self._passthrough, pkt["universe"], pkt["dmx"],
                )

                # Update per-rule hit counters
                for i, rule in enumerate(cfg.rules):
                    if rule.src_universe == pkt["universe"] and i < len(self._rule_counts):
                        self._rule_counts[i] += 1

            if paused:
                continue

            dest = (cfg.target_ip, cfg.port)
            for dst_universe, dmx_buf in outputs.items():
                try:
                    tx.sendto(build_artdmx(dst_universe, bytes(dmx_buf)), dest)
                except OSError:
                    pass
                with self._lock:
                    self._tx += 1

    def _hz_ticker(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(1.0)
            now = time.monotonic()
            with self._lock:
                elapsed = now - self._hz_last_time
                if elapsed > 0:
                    self._rule_hz = [
                        c / elapsed for c in self._rule_counts
                    ]
                    self._rule_counts = [0] * len(self._rule_counts)
                self._hz_last_time = now
