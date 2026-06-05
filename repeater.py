#!/usr/bin/env python3
"""Art-Net DMX channel repeater — entry point."""
import argparse
import sys

from engine import Engine
import web


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Receive Art-Net DMX, remap channels, re-send to another universe."
    )
    parser.add_argument(
        "config",
        nargs="?",
        default="config.toml",
        metavar="CONFIG",
        help="Path to config file (default: config.toml)",
    )
    parser.add_argument("--listen-ip", metavar="IP", help="Override network.listen_ip")
    parser.add_argument("--target-ip", metavar="IP", help="Override network.target_ip")
    parser.add_argument("--port", type=int, metavar="PORT", help="Override network.artnet_port")
    parser.add_argument(
        "--web",
        nargs="?",
        const=8080,
        type=int,
        metavar="PORT",
        help="Enable web UI (default port 8080)",
    )
    args = parser.parse_args()

    overrides = {
        "listen_ip": args.listen_ip,
        "target_ip": args.target_ip,
        "port": args.port,
    }

    try:
        engine = Engine(args.config, overrides)
    except ValueError as e:
        sys.exit(f"Config error: {e}")

    cfg = engine.status  # just for the startup banner
    print(f"Listening on {engine._cfg.listen_ip}:{engine._cfg.port}")
    print(f"Forwarding to {engine._cfg.target_ip}")
    print(f"Active rules ({len(engine._cfg.rules)}):")
    for r in engine._cfg.rules:
        print(
            f"  [{r.merge.upper()}] {r.name}  "
            f"U{r.src_universe} ch{r.src_first+1}–{r.src_last+1}"
            f" → U{r.dst_universe} ch{r.dst_first+1}–{r.dst_last+1}"
        )

    if args.web is not None:
        print(f"\nWeb UI → http://localhost:{args.web}")
        web.start(engine, args.web)

    print("\nRunning — Ctrl+C to stop.\n")
    engine.run_forever()


if __name__ == "__main__":
    main()
