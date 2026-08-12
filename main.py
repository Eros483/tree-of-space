import sys


class TreeOfSpace:
    """Implement lock/unlock/upgradeLock here"""

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

    def lock(self, x, uid):
        raise NotImplementedError("implement me")

    def unlock(self, x, uid):
        raise NotImplementedError("implement me")

    def upgrade_lock(self, x, uid):
        raise NotImplementedError("implement me")


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
                "false\ntrue\nfalse",
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
