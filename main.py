import sys

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

    def _get_locked_descendants(self, node_id):
        locked = []
        stack = list(range(self.m * node_id + 1, min(self.n, self.m * node_id + self.m + 1)))

        while stack:
            curr = stack.pop()
            if self.is_locked[curr]:
                locked.append(curr)
            elif self.locked_descendants[curr] > 0:
                child_start = self.m * curr + 1
                child_end = min(self.n, self.m * curr + self.m + 1)
                for child in range(child_start, child_end):
                    stack.append(child)

        return locked

    def lock(self, x, uid):
        node_id = self.node_to_id[x]
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

    def unlock(self, x, uid):
        node_id = self.node_to_id[x]
        if not self.is_locked[node_id] or self.locked_by[node_id] != uid:
            return False

        self.is_locked[node_id] = False
        self.locked_by[node_id] = -1

        curr = self.parent[node_id]
        while curr is not None:
            self.locked_descendants[curr] -= 1
            curr = self.parent[curr]

        return True

    def upgrade_lock(self, x, uid):
        node_id = self.node_to_id[x]
        if self.is_locked[node_id] or self.locked_descendants[node_id] == 0:
            return False

        curr = self.parent[node_id]
        while curr is not None:
            if self.is_locked[curr]:
                return False
            curr = self.parent[curr]

        locked_desc = self._get_locked_descendants(node_id)
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
        print("all tests passed")
    else:
        solve()
import sys

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

    def _get_locked_descendants(self, node_id):
        locked = []
        stack = list(range(self.m * node_id + 1, min(self.n, self.m * node_id + self.m + 1)))

        while stack:
            curr = stack.pop()
            if self.is_locked[curr]:
                locked.append(curr)
            elif self.locked_descendants[curr] > 0:
                child_start = self.m * curr + 1
                child_end = min(self.n, self.m * curr + self.m + 1)
                for child in range(child_start, child_end):
                    stack.append(child)
                    
        return locked

    def lock(self, x, uid):
        node_id = self.node_to_id[x]
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

    def unlock(self, x, uid):
        node_id = self.node_to_id[x]
        if not self.is_locked[node_id] or self.locked_by[node_id] != uid:
            return False

        self.is_locked[node_id] = False
        self.locked_by[node_id] = -1

        curr = self.parent[node_id]
        while curr is not None:
            self.locked_descendants[curr] -= 1
            curr = self.parent[curr]

        return True

    def upgrade_lock(self, x, uid):
        node_id = self.node_to_id[x]
        if self.is_locked[node_id] or self.locked_descendants[node_id] == 0:
            return False

        curr = self.parent[node_id]
        while curr is not None:
            if self.is_locked[curr]:
                return False
            curr = self.parent[curr]

        locked_desc = self._get_locked_descendants(node_id)
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
        print("all tests passed")
    else:
        solve()
