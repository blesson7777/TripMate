from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from diesel.site_utils import haversine_distance_meters


@dataclass(frozen=True)
class OptimizedRoute:
    order: list[int]
    total_km: float


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return haversine_distance_meters(lat1, lon1, lat2, lon2) / 1000.0


def build_distance_matrix_km(coords: Sequence[tuple[float, float]]) -> list[list[float]]:
    count = len(coords)
    matrix = [[0.0] * count for _ in range(count)]
    for i in range(count):
        lat1, lon1 = coords[i]
        for j in range(i + 1, count):
            lat2, lon2 = coords[j]
            distance_km = haversine_km(lat1, lon1, lat2, lon2)
            matrix[i][j] = distance_km
            matrix[j][i] = distance_km
    return matrix


def route_length_km(
    order: Sequence[int],
    distance_matrix_km: Sequence[Sequence[float]],
    *,
    start_dist_km: Sequence[float] | None = None,
    return_to_start: bool = False,
) -> float:
    if not order:
        return 0.0

    total_km = 0.0
    if start_dist_km is not None:
        total_km += float(start_dist_km[order[0]])

    for a, b in zip(order, order[1:]):
        total_km += float(distance_matrix_km[a][b])

    if return_to_start:
        if start_dist_km is not None:
            total_km += float(start_dist_km[order[-1]])
        else:
            total_km += float(distance_matrix_km[order[-1]][order[0]])

    return float(total_km)


def nearest_neighbor_order(
    distance_matrix_km: Sequence[Sequence[float]],
    *,
    start_idx: int,
) -> list[int]:
    count = len(distance_matrix_km)
    if count == 0:
        return []
    if count == 1:
        return [0]

    if start_idx < 0 or start_idx >= count:
        raise ValueError("start_idx must be within coords range.")

    unvisited = set(range(count))
    unvisited.remove(start_idx)
    order: list[int] = [start_idx]
    current = start_idx

    while unvisited:
        next_idx = min(unvisited, key=lambda idx: float(distance_matrix_km[current][idx]))
        order.append(next_idx)
        unvisited.remove(next_idx)
        current = next_idx

    return order


def two_opt_improve(
    order: Sequence[int],
    distance_matrix_km: Sequence[Sequence[float]],
    *,
    start_dist_km: Sequence[float] | None = None,
    return_to_start: bool = False,
    max_swaps: int = 4000,
) -> OptimizedRoute:
    best_order = list(order)
    best_total = route_length_km(
        best_order,
        distance_matrix_km,
        start_dist_km=start_dist_km,
        return_to_start=return_to_start,
    )

    if len(best_order) < 4 or max_swaps <= 0:
        return OptimizedRoute(order=best_order, total_km=float(best_total))

    swaps = 0
    improved = True
    count = len(best_order)

    while improved and swaps < max_swaps:
        improved = False
        for i in range(1, count - 2):
            for k in range(i + 1, count - 1):
                swaps += 1
                if swaps > max_swaps:
                    break

                candidate = best_order[:i] + list(reversed(best_order[i : k + 1])) + best_order[k + 1 :]
                candidate_total = route_length_km(
                    candidate,
                    distance_matrix_km,
                    start_dist_km=start_dist_km,
                    return_to_start=return_to_start,
                )
                if candidate_total + 1e-6 < best_total:
                    best_order = candidate
                    best_total = candidate_total
                    improved = True
                    break

            if swaps > max_swaps or improved:
                break

    return OptimizedRoute(order=best_order, total_km=float(best_total))


def optimize_route_order(
    coords: Sequence[tuple[float, float]],
    *,
    start: tuple[float, float] | None = None,
    return_to_start: bool = False,
    max_swaps: int = 4000,
) -> OptimizedRoute:
    count = len(coords)
    if count == 0:
        return OptimizedRoute(order=[], total_km=0.0)
    if count == 1:
        return OptimizedRoute(order=[0], total_km=0.0)

    distance_matrix_km = build_distance_matrix_km(coords)
    start_dist_km: list[float] | None = None

    if start is not None:
        start_lat, start_lon = start
        start_dist_km = [
            haversine_km(start_lat, start_lon, lat, lon) for lat, lon in coords
        ]
        start_idx = min(range(count), key=lambda idx: float(start_dist_km[idx]))
        greedy = nearest_neighbor_order(distance_matrix_km, start_idx=start_idx)
        return two_opt_improve(
            greedy,
            distance_matrix_km,
            start_dist_km=start_dist_km,
            return_to_start=return_to_start,
            max_swaps=max_swaps,
        )

    if count <= 60:
        candidates = list(range(count))
    else:
        centroid_lat = sum(lat for lat, _ in coords) / count
        centroid_lon = sum(lon for _, lon in coords) / count
        farthest = sorted(
            range(count),
            key=lambda idx: (coords[idx][0] - centroid_lat) ** 2 + (coords[idx][1] - centroid_lon) ** 2,
            reverse=True,
        )[:40]
        candidates = sorted(set(farthest + [0]))

    greedy_ranked: list[tuple[float, int, list[int]]] = []
    for start_idx in candidates:
        greedy = nearest_neighbor_order(distance_matrix_km, start_idx=start_idx)
        greedy_total = route_length_km(
            greedy,
            distance_matrix_km,
            return_to_start=return_to_start,
        )
        greedy_ranked.append((float(greedy_total), start_idx, greedy))

    greedy_ranked.sort(key=lambda item: item[0])
    top = greedy_ranked[: min(len(greedy_ranked), 6)]

    best: OptimizedRoute | None = None
    for _total, _start_idx, greedy in top:
        candidate = two_opt_improve(
            greedy,
            distance_matrix_km,
            return_to_start=return_to_start,
            max_swaps=max_swaps,
        )
        if best is None or candidate.total_km < best.total_km:
            best = candidate

    if best is not None:
        return best

    fallback = greedy_ranked[0][2] if greedy_ranked else list(range(count))
    fallback_total = route_length_km(
        fallback,
        distance_matrix_km,
        return_to_start=return_to_start,
    )
    return OptimizedRoute(order=fallback, total_km=float(fallback_total))


def format_route_legs(
    coords: Sequence[tuple[float, float]],
    order: Sequence[int],
    *,
    start: tuple[float, float] | None = None,
    return_to_start: bool = False,
) -> list[dict]:
    legs: list[dict] = []
    if not order:
        return legs

    prev = start
    cumulative_km = 0.0
    for seq, idx in enumerate(order, start=1):
        lat, lon = coords[idx]
        leg_km = 0.0
        if prev is not None:
            leg_km = haversine_km(prev[0], prev[1], lat, lon)
        cumulative_km += float(leg_km)
        legs.append(
            {
                "seq": seq,
                "idx": idx,
                "latitude": lat,
                "longitude": lon,
                "leg_km": float(leg_km),
                "cumulative_km": float(cumulative_km),
            }
        )
        prev = (lat, lon)

    if return_to_start:
        if prev is not None:
            return_lat, return_lon = start if start is not None else coords[order[0]]
            back_km = haversine_km(prev[0], prev[1], return_lat, return_lon)
            cumulative_km += float(back_km)
            legs.append(
                {
                    "seq": len(order) + 1,
                    "idx": None,
                    "latitude": return_lat,
                    "longitude": return_lon,
                    "leg_km": float(back_km),
                    "cumulative_km": float(cumulative_km),
                    "is_return_leg": True,
                }
            )

    return legs


def normalize_coordinate_input(value) -> float:
    if isinstance(value, bool):
        raise ValueError("Coordinate must be a number.")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value.strip())
    raise ValueError("Coordinate must be a number.")


def validate_lat_lon(latitude: float, longitude: float) -> None:
    if latitude < -90 or latitude > 90:
        raise ValueError("Latitude must be between -90 and 90.")
    if longitude < -180 or longitude > 180:
        raise ValueError("Longitude must be between -180 and 180.")


def normalize_coords(
    items: Iterable[dict],
    *,
    lat_key: str = "latitude",
    lon_key: str = "longitude",
) -> list[tuple[float, float]]:
    coords: list[tuple[float, float]] = []
    for item in items:
        lat = normalize_coordinate_input(item.get(lat_key))
        lon = normalize_coordinate_input(item.get(lon_key))
        validate_lat_lon(lat, lon)
        coords.append((lat, lon))
    return coords
