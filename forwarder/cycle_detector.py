from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Set, Tuple


class RouteCycleDetector:

    @classmethod
    def would_create_cycle(
        cls,
        existing_pairs: List[Tuple[int, int]],
        new_source: int,
        new_dest: int,
    ) -> bool:
        if new_source == new_dest:
            return True

        graph: Dict[int, List[int]] = defaultdict(list)
        for src, dst in existing_pairs:
            graph[src].append(dst)
        graph[new_source].append(new_dest)

        visited: Set[int] = set()

        def dfs(current: int) -> bool:
            if current == new_source:
                return True
            visited.add(current)
            for neighbor in graph.get(current, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
            return False

        return dfs(new_dest)

    @classmethod
    def find_all_cycles(cls, pairs: List[Tuple[int, int]]) -> List[List[int]]:
        graph: Dict[int, List[int]] = defaultdict(list)
        nodes: Set[int] = set()
        for src, dst in pairs:
            graph[src].append(dst)
            nodes.add(src)
            nodes.add(dst)

        visited: Set[int] = set()
        rec_stack: Set[int] = set()
        cycles: List[List[int]] = []

        def dfs(node: int, path: List[int]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor, list(path))
                elif neighbor in rec_stack:
                    cycle_start = path.index(neighbor)
                    cycles.append(path[cycle_start:] + [neighbor])

            rec_stack.remove(node)

        for n in nodes:
            if n not in visited:
                dfs(n, [])

        return cycles
