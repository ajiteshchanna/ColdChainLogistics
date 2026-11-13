"""Open-Meteo adapter with typed snapshots and explicit stale/error states."""

from dataclasses import dataclass
from datetime import datetime, timezone

import requests


@dataclass(frozen=True)
class WeatherSnapshot:
    latitude: float
    longitude: float
    temperature_c: float | None
    wind_speed_kph: float | None
    observed_at: datetime | None
    retrieved_at: datetime
    source: str
    status: str
    message: str | None = None


class WeatherClient:
    """Fetch current weather without converting failures into normal data."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 6.0,
        session: requests.Session | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def current(self, latitude: float, longitude: float) -> WeatherSnapshot:
        retrieved_at = datetime.now(timezone.utc)
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            return self._failure(
                latitude, longitude, retrieved_at, "Invalid latitude or longitude."
            )
        try:
            response = self.session.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current_weather": "true",
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            current = response.json().get("current_weather")
            if not isinstance(current, dict):
                return self._failure(
                    latitude, longitude, retrieved_at,
                    "Weather response omitted current_weather.",
                )
            temperature = current.get("temperature")
            wind_speed = current.get("windspeed")
            if temperature is None or wind_speed is None:
                return self._failure(
                    latitude, longitude, retrieved_at,
                    "Weather response omitted temperature or windspeed.",
                )
            observed_at = _parse_timestamp(current.get("time"))
            return WeatherSnapshot(
                latitude=latitude,
                longitude=longitude,
                temperature_c=float(temperature),
                wind_speed_kph=float(wind_speed),
                observed_at=observed_at,
                retrieved_at=retrieved_at,
                source="open-meteo",
                status="ok",
            )
        except (requests.RequestException, TimeoutError) as exc:
            return self._failure(
                latitude, longitude, retrieved_at, f"Weather request failed: {exc}"
            )
        except (TypeError, ValueError) as exc:
            return self._failure(
                latitude, longitude, retrieved_at, f"Invalid weather payload: {exc}"
            )

    @staticmethod
    def _failure(
        latitude: float,
        longitude: float,
        retrieved_at: datetime,
        message: str,
    ) -> WeatherSnapshot:
        return WeatherSnapshot(
            latitude=latitude,
            longitude=longitude,
            temperature_c=None,
            wind_speed_kph=None,
            observed_at=None,
            retrieved_at=retrieved_at,
            source="open-meteo",
            status="degraded",
            message=message,
        )


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
