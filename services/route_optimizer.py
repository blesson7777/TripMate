from __future__ import annotations

from functools import lru_cache
import logging
import math
from typing import Sequence
from urllib.parse import quote

import requests
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

logger = logging.getLogger(__name__)

OSRM_TABLE_URL = "https://router.project-osrm.org/table/v1/driving/"
OSRM_TIMEOUT_SECONDS = 8
MAX_TOWERS_PER_REQUEST = 25
SUPPORTED_OPTIMIZE_FOR = {"distance", "duration"}


class RouteOptimizerError(RuntimeError):
    """Raised when route optimization cannot be completed."""


def _validate_coordinate_pair(value: Sequence[float] | tuple[float, float], label: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{label} must contain exactly [latitude, longitude].")
    latitude = _validate_latitude(value[0], f"{label} latitude")
    longitude = _validate_longitude(value[1], f"{label} longitude")
    return latitude, longitude


def _validate_latitude(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a valid number.")
    try:
        latitude = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a valid number.") from exc
    if latitude < -90 or latitude > 90:
        raise ValueError(f"{label} must be between -90 and 90.")
    return latitude


def _validate_longitude(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a valid number.")
    try:
        longitude = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a valid number.") from exc
    if longitude < -180 or longitude > 180:
        raise ValueError(f"{label} must be between -180 and 180.")
    return longitude


def _validate_optimize_for(value: str) -> str:
    normalized = (value or "distance").strip().lower()
    if normalized not in SUPPORTED_OPTIMIZE_FOR:
        raise ValueError("optimize_for must be either 'distance' or 'duration'.")
    return normalized


def _haversine_meters(origin: tuple[float, float], destination: tuple[float, float]) -> float:
    lat1, lon1 = origin
    lat2, lon2 = destination
    radius_m = 6_371_000.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_m * c


def _build_haversine_matrix(coords: Sequence[tuple[float, float]]) -> tuple[list[list[float]], list[list[float]]]:
    size = len(coords)
    distances = [[0.0] * size for _ in range(size)]
    durations = [[0.0] * size for _ in range(size)]
    average_speed_mps = 35_000 / 3600

    for row_index in range(size):
        for col_index in range(row_index + 1, size):
            distance_m = _haversine_meters(coords[row_index], coords[col_index])
            duration_s = distance_m / average_speed_mps
            distances[row_index][col_index] = distance_m
            distances[col_index][row_index] = distance_m
            durations[row_index][col_index] = duration_s
            durations[col_index][row_index] = duration_s

    return distances, durations


def _coordinates_signature(coords: Sequence[tuple[float, float]]) -> str:
    return ";".join(f"{longitude:.6f},{latitude:.6f}" for latitude, longitude in coords)


@lru_cache(maxsize=128)
def _fetch_osrm_table_cached(signature: str) -> tuple[tuple[tuple[float, ...], ...], tuple[tuple[float, ...], ...]]:
    url = (
        f"{OSRM_TABLE_URL}{quote(signature, safe=';,.')}"
        "?annotations=distance,duration"
    )
    response = requests.get(url, timeout=OSRM_TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json()

    if payload.get("code") != "Ok":
        raise RouteOptimizerError("OSRM returned a non-success response.")

    distances = payload.get("distances")
    durations = payload.get("durations")
    if not isinstance(distances, list) or not isinstance(durations, list):
        raise RouteOptimizerError("OSRM response did not contain matrices.")

    normalized_distances: list[tuple[float, ...]] = []
    normalized_durations: list[tuple[float, ...]] = []
    expected_size = len(distances)

    for distance_row, duration_row in zip(distances, durations):
        if not isinstance(distance_row, list) or not isinstance(duration_row, list):
            raise RouteOptimizerError("OSRM matrix rows are invalid.")
        if len(distance_row) != expected_size or len(duration_row) != expected_size:
            raise RouteOptimizerError("OSRM matrix dimensions are invalid.")

        cleaned_distance_row: list[float] = []
        cleaned_duration_row: list[float] = []
        for distance_value, duration_value in zip(distance_row, duration_row):
            if distance_value is None or duration_value is None:
                raise RouteOptimizerError("OSRM matrix contains unreachable points.")
            cleaned_distance_row.append(float(distance_value))
            cleaned_duration_row.append(float(duration_value))

        normalized_distances.append(tuple(cleaned_distance_row))
        normalized_durations.append(tuple(cleaned_duration_row))

    return tuple(normalized_distances), tuple(normalized_durations)


def _build_distance_duration_matrices(
    coords: Sequence[tuple[float, float]],
) -> tuple[list[list[float]], list[list[float]], bool]:
    signature = _coordinates_signature(coords)
    try:
        distances, durations = _fetch_osrm_table_cached(signature)
        return [list(row) for row in distances], [list(row) for row in durations], False
    except (requests.RequestException, RouteOptimizerError, ValueError) as exc:
        logger.warning("OSRM matrix unavailable, using haversine fallback: %s", exc)
        distances, durations = _build_haversine_matrix(coords)
        return distances, durations, True


def _solve_route(
    cost_matrix: Sequence[Sequence[int]],
    *,
    start_node: int = 0,
    end_node: int | None = None,
) -> list[int]:
    node_count = len(cost_matrix)
    if node_count < 2:
        return [start_node, start_node]

    if end_node is None:
        manager = pywrapcp.RoutingIndexManager(node_count, 1, start_node)
    else:
        manager = pywrapcp.RoutingIndexManager(node_count, 1, [start_node], [end_node])
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return int(cost_matrix[from_node][to_node])

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.seconds = 5

    solution = routing.SolveWithParameters(search_parameters)
    if solution is None:
        raise RouteOptimizerError("OR-Tools could not find an optimized route.")

    route: list[int] = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        route.append(manager.IndexToNode(index))
        index = solution.Value(routing.NextVar(index))
    route.append(manager.IndexToNode(index))
    return route


def _build_open_route_cost_matrix(cost_matrix: Sequence[Sequence[int]]) -> tuple[list[list[int]], int]:
    size = len(cost_matrix)
    dummy_end = size
    max_cost = max((max(row) for row in cost_matrix), default=0)
    huge_cost = max(1_000_000, max_cost * 1000 + 1)

    open_matrix = [[huge_cost] * (size + 1) for _ in range(size + 1)]
    for row_index in range(size):
        for col_index in range(size):
            open_matrix[row_index][col_index] = int(cost_matrix[row_index][col_index])

    for row_index in range(1, size):
        open_matrix[row_index][dummy_end] = 0
    open_matrix[dummy_end][dummy_end] = 0

    return open_matrix, dummy_end


def _total_metric(
    route: Sequence[int],
    matrix: Sequence[Sequence[float]],
) -> float:
    total_value = 0.0
    for from_node, to_node in zip(route, route[1:]):
        total_value += float(matrix[from_node][to_node])
    return total_value


def _total_distance_km(route: Sequence[int], distance_matrix: Sequence[Sequence[float]]) -> float:
    return round(_total_metric(route, distance_matrix) / 1000.0, 2)


def _total_duration_minutes(route: Sequence[int], duration_matrix: Sequence[Sequence[float]]) -> float:
    return round(_total_metric(route, duration_matrix) / 60.0, 1)


def optimize_route_path(
    start: tuple[float, float],
    towers: list[tuple[float, float]],
    *,
    return_to_start: bool = False,
    optimize_for: str = "distance",
) -> dict:
    optimize_metric = _validate_optimize_for(optimize_for)
    validated_start = _validate_coordinate_pair(start, "start")
    if not towers:
        raise ValueError("towers must contain at least one coordinate pair.")
    if len(towers) > MAX_TOWERS_PER_REQUEST:
        raise ValueError(f"towers cannot contain more than {MAX_TOWERS_PER_REQUEST} items.")

    validated_towers = [
        _validate_coordinate_pair(tower, f"tower #{index}")
        for index, tower in enumerate(towers, start=1)
    ]

    coords = [validated_start, *validated_towers]
    distance_matrix, duration_matrix, used_fallback = _build_distance_duration_matrices(coords)
    optimize_matrix = distance_matrix if optimize_metric == "distance" else duration_matrix
    integer_cost_matrix = [
        [int(round(cell)) for cell in row]
        for row in optimize_matrix
    ]

    if return_to_start:
        raw_route = _solve_route(integer_cost_matrix)
        route = raw_route
    else:
        open_cost_matrix, dummy_end = _build_open_route_cost_matrix(integer_cost_matrix)
        raw_route = _solve_route(open_cost_matrix, end_node=dummy_end)
        route = [node for node in raw_route if node != dummy_end]

    ordered_coordinates = [coords[index] for index in route]

    return {
        "route": route,
        "distance": _total_distance_km(route, distance_matrix),
        "duration_minutes": _total_duration_minutes(route, duration_matrix),
        "ordered_coordinates": ordered_coordinates,
        "mode": "local" if used_fallback else "road",
        "used_fallback": used_fallback,
        "return_to_start": bool(return_to_start),
        "optimize_for": optimize_metric,
    }


def optimize_route(depot: tuple[float, float], towers: list[tuple[float, float]]) -> dict:
    """
    Args:
        depot: (lat, lon)
        towers: [(lat, lon), ...]

    Returns:
        {
            "route": [0, 2, 1, 3, 0],
            "distance": total_distance_in_km,
            "ordered_coordinates": [(lat, lon), ...]
        }
    """
    result = optimize_route_path(
        start=depot,
        towers=towers,
        return_to_start=True,
        optimize_for="distance",
    )
    return {
        "route": result["route"],
        "distance": result["distance"],
        "ordered_coordinates": result["ordered_coordinates"],
    }
