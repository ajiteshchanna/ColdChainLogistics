"""Bounded route adapter with a deterministic offline fixture."""

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from typing import Any


@dataclass(frozen=True)
class RouteEstimate:
    origin: tuple[float, float]
    destination: tuple[float, float]
    distance_km: float
    duration_minutes: float
    geometry: tuple[tuple[float, float], ...]
    status: str
    source: str
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "origin": self.origin,
            "destination": self.destination,
            "distance_km": self.distance_km,
            "duration_minutes": self.duration_minutes,
            "geometry": self.geometry,
            "status": self.status,
            "source": self.source,
            "warnings": self.warnings,
        }


class OsrmClient:
    """Provide route estimates without making the demo depend on the network."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float = 3.0,
        route_fixtures: dict[str, RouteEstimate] | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.route_fixtures = route_fixtures or {}

    def route(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        *,
        route_key: str | None = None,
        blocked: bool = False,
        delay_minutes: float = 0.0,
    ) -> RouteEstimate:
        if not _valid_coordinate(origin) or not _valid_coordinate(destination):
            raise ValueError("Origin and destination coordinates must be valid.")
        if delay_minutes < 0:
            raise ValueError("delay_minutes must not be negative.")
        if blocked:
            return RouteEstimate(
                origin, destination, 0.0, 0.0, (), "unavailable", "fixture",
                ("Route is blocked by the active scenario.",),
            )
        if route_key and route_key in self.route_fixtures:
            fixture = self.route_fixtures[route_key]
            return RouteEstimate(
                fixture.origin,
                fixture.destination,
                fixture.distance_km,
                fixture.duration_minutes + delay_minutes,
                fixture.geometry,
                fixture.status,
                fixture.source,
                fixture.warnings,
            )
        distance = _haversine_km(origin, destination) * 1.18
        return RouteEstimate(
            origin,
            destination,
            distance,
            distance / 45.0 * 60.0 + delay_minutes,
            (origin, destination),
            "ok",
            "deterministic_fixture",
            ("Road geometry is an offline deterministic fixture.",),
        )


def _valid_coordinate(point: tuple[float, float]) -> bool:
    return (
        len(point) == 2
        and -90 <= point[0] <= 90
        and -180 <= point[1] <= 180
    )


def _haversine_km(origin: tuple[float, float], destination: tuple[float, float]) -> float:
    latitude_one, longitude_one = map(radians, origin)
    latitude_two, longitude_two = map(radians, destination)
    delta_latitude = latitude_two - latitude_one
    delta_longitude = longitude_two - longitude_one
    value = (
        sin(delta_latitude / 2) ** 2
        + cos(latitude_one) * cos(latitude_two) * sin(delta_longitude / 2) ** 2
    )
    return 6371.0 * 2 * asin(sqrt(value))
