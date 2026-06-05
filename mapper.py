"""Channel remapping: stateful LTP/HTP merger over persistent passthrough buffers."""
from dataclasses import dataclass


@dataclass
class Rule:
    name: str
    src_universe: int
    src_first: int   # 0-indexed internally (converted from 1-indexed at load time)
    src_last: int    # inclusive, 0-indexed
    dst_universe: int
    dst_first: int   # 0-indexed
    dst_last: int    # inclusive, 0-indexed
    merge: str       # "ltp" or "htp"

    @property
    def length(self) -> int:
        return self.src_last - self.src_first + 1


def update_and_merge(
    rules: list[Rule],
    rule_states: dict[int, bytearray],
    passthrough: dict[int, bytearray],
    src_universe: int,
    src_dmx: bytes,
) -> dict[int, bytearray]:
    """
    Update rule states from a new source packet, then compute the merged output
    for every affected destination universe.

    rule_states:  {rule_index: bytearray(512)} — last values each rule contributed
                  at the destination channel positions. Mutated in-place.
    passthrough:  {universe: bytearray(512)} — latest full received frame per universe.
                  Must be updated by the caller BEFORE this call.

    Returns {dst_universe: merged_bytearray(512)} for universes that need re-sending.

    Merge logic per rule:
      LTP — overwrite dst channels with latest source values (last-packet wins).
      HTP — per-channel max(passthrough_base, rule_value); recomputed from fresh
            passthrough each call so values correctly decrease when source falls.
    """
    dst_universes_of_rules = {r.dst_universe for r in rules}
    affected: set[int] = set()

    # Step 1 — update rule states for rules whose source just arrived
    for i, rule in enumerate(rules):
        if rule.src_universe != src_universe:
            continue
        if i not in rule_states:
            rule_states[i] = bytearray(512)
        src_slice = src_dmx[rule.src_first : rule.src_last + 1]
        if len(src_slice) < rule.length:
            src_slice = src_slice + bytes(rule.length - len(src_slice))
        rule_states[i][rule.dst_first : rule.dst_last + 1] = src_slice
        affected.add(rule.dst_universe)

    # Step 2 — if the incoming universe is also a destination, the passthrough
    # base changed, so all rules writing to it must be recomputed too
    if src_universe in dst_universes_of_rules:
        affected.add(src_universe)

    # Step 3 — compute merged output for each affected destination universe
    outputs: dict[int, bytearray] = {}
    for dst_uni in affected:
        # Start from a copy of the passthrough base (all 512 channels from last
        # received packet on that universe, or zeros if never received)
        base = bytearray(passthrough.get(dst_uni, bytes(512)))

        for i, rule in enumerate(rules):
            if rule.dst_universe != dst_uni or i not in rule_states:
                continue
            state = rule_states[i]
            if rule.merge == "ltp":
                base[rule.dst_first : rule.dst_last + 1] = (
                    state[rule.dst_first : rule.dst_last + 1]
                )
            else:  # htp
                for j in range(rule.dst_first, rule.dst_last + 1):
                    if state[j] > base[j]:
                        base[j] = state[j]

        outputs[dst_uni] = base

    return outputs
