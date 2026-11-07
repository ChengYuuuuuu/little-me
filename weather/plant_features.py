"""Artistic 0..1 mappings from documented weather measurements.

The inputs remain physical measurements. The output bounds are artistic choices:
temperature maps -5..30 °C to cool..warm; rain saturates at 5 mm/hour;
sunlight uses sunshine seconds within an hour; brightness combines sunlight,
cloud attenuation and day/night state. These are not meteorological indices.
"""
from __future__ import annotations

def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))

def normalized_features(*, sunshine_duration: float | None, cloud_cover: float | None,
                        precipitation: float | None, temperature_2m: float | None,
                        is_day: int | None = None) -> dict[str, float | None]:
    sunlight = None if sunshine_duration is None else _clamp(sunshine_duration / 3600.0)
    cloudiness = None if cloud_cover is None else _clamp(cloud_cover / 100.0)
    rain = None if precipitation is None else _clamp(precipitation / 5.0)
    warmth = None if temperature_2m is None else _clamp((temperature_2m + 5.0) / 35.0)
    if sunlight is None or cloudiness is None:
        brightness = None
    else:
        daylight = 1.0 if is_day is None else _clamp(float(is_day))
        brightness = _clamp(daylight * (0.7 * sunlight + 0.3 * (1.0 - cloudiness)))
    return {"sunlight_level": sunlight, "cloudiness": cloudiness, "rain_intensity": rain,
            "temperature_warmth": warmth, "environmental_brightness": brightness}
