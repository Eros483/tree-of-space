import sys
import threading
from collections import deque


class TreeOfSpace:
    def __init__(self, node_names, m):
        self.m = m
        self.n = len(node_names)
        self.node_to_id = {name: i for i, name in enumerate(node_names)}
        self.id_to_node = node_names
        self.parent = [None] * self.n
        for i in range(self.n):
            if i > 0:
                self.parent[i] = (i - 1) // m
        self.is_locked = [False] * self.n
        self.locked_by = [-1] * self.n
        self.locked_descendants = [0] * self.n
        self.locks = [threading.Lock() for _ in range(self.n)]

    def _path(self, node_id):
        path = []
        curr = node_id
        while curr is not None:
            path.append(curr)
            curr = self.parent[curr]
        return path[::-1]

    def _acquire(self, node_ids):
        for i in node_ids:
            self.locks[i].acquire()

    def _release(self, node_ids):
        for i in reversed(node_ids):
            self.locks[i].release()

    def _collect_locked_descendants(self, node_id):
        locked = []
        visited = []
        queue = deque(range(self.m * node_id + 1, min(self.n, self.m * node_id + self.m + 1)))
        while queue:
            curr = queue.popleft()
            self.locks[curr].acquire()
            visited.append(curr)
            if self.is_locked[curr]:
                locked.append(curr)
            elif self.locked_descendants[curr] > 0:
                child_start = self.m * curr + 1
                child_end = min(self.n, self.m * curr + self.m + 1)
                for child in range(child_start, child_end):
                    queue.append(child)
        return locked, visited

    def lock(self, x, uid):
        node_id = self.node_to_id[x]
        path = self._path(node_id)
        self._acquire(path)
        try:
            if self.is_locked[node_id] or self.locked_descendants[node_id] > 0:
                return False

            curr = self.parent[node_id]
            while curr is not None:
                if self.is_locked[curr]:
                    return False
                curr = self.parent[curr]

            self.is_locked[node_id] = True
            self.locked_by[node_id] = uid

            curr = self.parent[node_id]
            while curr is not None:
                self.locked_descendants[curr] += 1
                curr = self.parent[curr]

            return True
        finally:
            self._release(path)

    def unlock(self, x, uid):
        node_id = self.node_to_id[x]
        path = self._path(node_id)
        self._acquire(path)
        try:
            if not self.is_locked[node_id] or self.locked_by[node_id] != uid:
                return False

            self.is_locked[node_id] = False
            self.locked_by[node_id] = -1

            curr = self.parent[node_id]
            while curr is not None:
                self.locked_descendants[curr] -= 1
                curr = self.parent[curr]

            return True
        finally:
            self._release(path)

    def upgrade_lock(self, x, uid):
        node_id = self.node_to_id[x]
        path = self._path(node_id)
        self._acquire(path)
        try:
            if self.is_locked[node_id] or self.locked_descendants[node_id] == 0:
                return False

            curr = self.parent[node_id]
            while curr is not None:
                if self.is_locked[curr]:
                    return False
                curr = self.parent[curr]

            locked_desc, visited = self._collect_locked_descendants(node_id)
            for desc_id in locked_desc:
                if self.locked_by[desc_id] != uid:
                    return False

            for desc_id in locked_desc:
                self.is_locked[desc_id] = False
                self.locked_by[desc_id] = -1
                p = self.parent[desc_id]
                while p is not None:
                    self.locked_descendants[p] -= 1
                    p = self.parent[p]

            self.is_locked[node_id] = True
            self.locked_by[node_id] = uid

            p = self.parent[node_id]
            while p is not None:
                self.locked_descendants[p] += 1
                p = self.parent[p]

            return True
        finally:
            self._release(visited)
            self._release(path)


def run(raw):
    data = raw.split()
    it = iter(data)
    n = int(next(it))
    m = int(next(it))
    q = int(next(it))
    node_names = [next(it).decode() for _ in range(n)]

    tree = TreeOfSpace(node_names, m)

    ops = {
        b"1": tree.lock,
        b"2": tree.unlock,
        b"3": tree.upgrade_lock,
    }
    out = []
    for _ in range(q):
        op, node, uid = next(it), next(it).decode(), int(next(it))
        out.append("true" if ops[op](node, uid) else "false")
    return "\n".join(out)


def solve():
    sys.stdout.write(run(sys.stdin.buffer.read()))


def _assert_consistent(tree):
    for i in range(tree.n):
        expect = sum(
            1
            for j in range(tree.n)
            if j != i and tree.is_locked[j] and i in tree._path(j)[:-1]
        )
        assert tree.locked_descendants[i] == expect, (i, tree.locked_descendants[i], expect)


def _smoke_test():
    names = ["Root", "A", "B", "C", "D", "E", "F"]

    def concurrent(tree, f1, f2):
        barrier = threading.Barrier(2)
        out = []

        def run(f):
            barrier.wait()
            out.append(f())

        threads = [threading.Thread(target=run, args=(f1,)), threading.Thread(target=run, args=(f2,))]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        _assert_consistent(tree)
        return sorted(out)

    t = TreeOfSpace(names, 2)
    assert concurrent(t, lambda: t.lock("C", 1), lambda: t.lock("D", 1)) == [True, True]

    t = TreeOfSpace(names, 2)
    assert concurrent(t, lambda: t.lock("A", 2), lambda: t.lock("C", 3)) == [False, True]

    t = TreeOfSpace(names, 2)
    assert t.lock("C", 1)
    assert concurrent(t, lambda: t.unlock("C", 1), lambda: t.unlock("C", 2)) == [False, True]

    t = TreeOfSpace(names, 2)
    assert t.lock("C", 1) and t.lock("D", 1)
    assert concurrent(t, lambda: t.upgrade_lock("A", 1), lambda: t.lock("C", 2)) == [False, True]
    print("threaded smoke test passed")


if __name__ == "__main__":
    if "--test" in sys.argv:
        cases = [
            (
                b"""7
2
3
World
Asia
Africa
China
India
SouthAfrica
Egypt
1 China 9
2 India 9
3 Asia 9""",
                "true\nfalse\ntrue",
            ),
            (
                b"""7
2
5
World
Asia
Africa
China
India
SouthAfrica
Egypt
1 China 9
1 India 9
3 Asia 9
2 India 9
2 Asia 9""",
                "true\ntrue\ntrue\nfalse\ntrue",
            ),
            (
                b"""3
2
4
Root
A
B
1 A 1
1 A 2
2 A 2
2 A 1""",
                "true\nfalse\nfalse\ntrue",
            ),
        ]
        for raw, expected in cases:
            assert run(raw) == expected, f"FAILED:\n{raw!r}\nexpected {expected!r}\ngot {run(raw)!r}"
        _smoke_test()
        print("all tests passed")
    else:
        solve()
