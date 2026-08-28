"""L0 — catalog access. A database query, never a web search.

Runtime web research for parts is prohibited (docs/architecture.md, CLAUDE.md):
it yields dead links, out-of-stock parts, wrong specs and invented part numbers,
and returns a different BOM on every run — fatal for a quoting tool.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .schema import (ActuatorRole, ActuatorSpec, Dimensions, Geometry, Part,
                     PartKind)

DATA_DIR = Path(__file__).parent / "data"


class UnverifiedPartError(RuntimeError):
    """Raised when an unverified part would reach a customer-facing artifact."""


def _actuator_from_dict(d: dict | None) -> ActuatorSpec | None:
    if not d:
        return None
    spec = dict(d)
    spec["role"] = ActuatorRole(spec.get("role", ActuatorRole.JOINT.value))
    return ActuatorSpec(**spec)


def _part_from_dict(d: dict) -> Part:
    return Part(
        id=d["id"],
        kind=PartKind(d["kind"]),
        manufacturer=d["manufacturer"],
        part_number=d["part_number"],
        description=d.get("description", ""),
        price_usd=float(d["price_usd"]),
        dimensions=Dimensions(**d["dimensions"]),
        mass_kg=float(d["mass_kg"]),
        actuator=_actuator_from_dict(d.get("actuator")),
        geometry=Geometry(**d.get("geometry", {})),
        lead_time_days=d.get("lead_time_days"),
        source_url=d.get("source_url"),
        verified=bool(d.get("verified", False)),
        notes=d.get("notes", ""),
    )


class Catalog:
    def __init__(self, parts: list[Part]) -> None:
        self._parts = {p.id: p for p in parts}
        if len(self._parts) != len(parts):
            raise ValueError("duplicate part ids in catalog")

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Catalog":
        path = Path(path) if path else DATA_DIR / "parts.json"
        raw = json.loads(Path(path).read_text())
        return cls([_part_from_dict(d) for d in raw["parts"]])

    def __len__(self) -> int:
        return len(self._parts)

    def get(self, part_id: str) -> Part:
        try:
            return self._parts[part_id]
        except KeyError:
            raise KeyError(
                f"part {part_id!r} is not in the catalog. It does not exist. "
                "Parts are added by a human, offline — never invented at runtime."
            ) from None

    def query(
        self,
        kind: PartKind | None = None,
        max_price_usd: float | None = None,
        min_torque_nm: float | None = None,
        min_speed_rad_s: float | None = None,
        actuator_role: ActuatorRole | None = None,
        max_envelope_volume_m3: float | None = None,
        allow_unverified: bool = False,
    ) -> list[Part]:
        """Constrained selection over the catalog. Deterministic and total.

        ``allow_unverified`` defaults to False: a part no human has confirmed
        cannot be quoted from.
        """
        out = []
        for p in self._parts.values():
            if not p.verified and not allow_unverified:
                continue
            if kind is not None and p.kind is not kind:
                continue
            if max_price_usd is not None and p.price_usd > max_price_usd:
                continue
            if min_torque_nm is not None:
                if p.actuator is None or p.actuator.rated_torque_nm < min_torque_nm:
                    continue
            # Speed is a selection constraint, not an afterthought. A drive axis
            # sized on torque alone gets a high-ratio joint servo that is strong
            # and far too slow, and the machine crawls.
            if min_speed_rad_s is not None:
                if p.actuator is None or p.actuator.max_speed_rad_s < min_speed_rad_s:
                    continue
            # Role is a hard filter, not a preference. Torque and speed describe
            # what a motor can produce; role describes whether it can be used
            # where the design puts it.
            if actuator_role is not None:
                if p.actuator is None or p.actuator.role is not actuator_role:
                    continue
            if max_envelope_volume_m3 is not None:
                if p.dimensions.envelope_volume_m3 > max_envelope_volume_m3:
                    continue
            out.append(p)
        return sorted(out, key=lambda p: p.price_usd)

    def assert_quotable(self, parts: list[Part]) -> None:
        """Gate before anything customer-facing. Fails loudly, never silently."""
        bad = [p.id for p in parts if not p.verified]
        if bad:
            raise UnverifiedPartError(
                "these parts are not human-verified and cannot be quoted: "
                + ", ".join(sorted(bad))
                + ". Verify price, part number and specs against the vendor, then "
                "set verified=true in the catalog."
            )

    def stats(self) -> dict:
        verified = sum(1 for p in self._parts.values() if p.verified)
        by_kind: dict[str, int] = {}
        for p in self._parts.values():
            by_kind[p.kind.value] = by_kind.get(p.kind.value, 0) + 1
        return {
            "total": len(self._parts),
            "verified": verified,
            "unverified": len(self._parts) - verified,
            "with_geometry": sum(1 for p in self._parts.values() if p.geometry.step_path),
            "by_kind": by_kind,
        }
