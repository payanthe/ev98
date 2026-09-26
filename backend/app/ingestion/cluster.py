from collections import defaultdict

from app.domain.text import haversine_m, normalize_fa
from app.ingestion.records import NormalizedRecord


def cluster_charge_points(
    records: list[NormalizedRecord], max_distance_m: float = 250
) -> list[list[NormalizedRecord]]:
    """Group same-name charge points that sit on one physical site.

    Name alone never merges two sites. Distance alone never merges two names.
    """
    parent = list(range(len(records)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    buckets: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        buckets[normalize_fa(record.name, cluster_key=True)].append(index)

    for indexes in buckets.values():
        for left in range(len(indexes)):
            for right in range(left + 1, len(indexes)):
                a, b = records[indexes[left]], records[indexes[right]]
                if haversine_m(a.lat, a.lng, b.lat, b.lng) <= max_distance_m:
                    union(indexes[left], indexes[right])

    groups: dict[int, list[NormalizedRecord]] = defaultdict(list)
    for index, record in enumerate(records):
        groups[find(index)].append(record)
    return list(groups.values())
