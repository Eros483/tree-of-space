import sys
import threading
from collections import deque

_UPGRADE_RETRIES = 100


class TreeOfSpace:
    """M-ary tree with per-node locks and linearizable lock/unlock/upgrade.

    Concurrency protocol: each op announces an intent on every ancestor
    (root->leaf), commits on the target under the target's mutex, then
    credits the ancestor bookkeeping. An intent stays visible for the whole
    op, so intents[x] == 0 guarantees no in-flight op touches x's subtree.
    Every multi-lock acquisition is root->leaf, so lock ordering is acyclic.
    """

    def __init__(self, node_names, m):
        """Builds a balanced m-ary tree from level-ordered names.

        Args:
            node_names: Node names in level order; index doubles as node id.
            m: Maximum children per node.
        """
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
        # Per-node count of locked nodes below it; lets lock/unlock skip
        # subtree scans and lets upgrade prune its BFS.
        self.locked_descendants = [0] * self.n
        # Per-node count of in-flight ops announced on it.
        self.intents = [0] * self.n
        self.locks = [threading.Lock() for _ in range(self.n)]

    def _path(self, node_id):
        """Returns ids from root to node_id, inclusive."""
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

    def _release_intents(self, path):
        """Clears one intent per node; caller must hold no locks."""
        for i in path:
            lock = self.locks[i]
            lock.acquire()
            try:
                self.intents[i] -= 1
            finally:
                lock.release()

    def _announce(self, path):
        """Adds an intent to each ancestor, stopping at any locked ancestor.

        On failure the rollback runs with no locks held: acquiring ancestors
        while still holding this node's mutex would invert lock order against
        upgrade's root->leaf path acquisition and can deadlock.
        """
        done = []
        for i in path:
            lock = self.locks[i]
            lock.acquire()
            try:
                if self.is_locked[i]:
                    break
                self.intents[i] += 1
                done.append(i)
            finally:
                lock.release()
        else:
            return True
        self._release_intents(done)
        return False

    def _credit(self, path, delta):
        """Applies delta to ancestors' locked_descendants, then clears intents.

        Two phases so an intent stays set until all of the op's bookkeeping is
        visible. upgrade_lock reads intents[target] == 0 as "subtree is
        quiescent"; clearing intents alongside each per-ancestor update would
        let upgrade observe a half-committed credit and sweep a stale subtree.
        """
        for i in path:
            lock = self.locks[i]
            lock.acquire()
            try:
                self.locked_descendants[i] += delta
            finally:
                lock.release()
        for i in path:
            lock = self.locks[i]
            lock.acquire()
            try:
                self.intents[i] -= 1
            finally:
                lock.release()

    def _commit_lock(self, node_id, uid):
        """Marks node locked if it and its subtree are free.

        The intents check fails this lock while a descendant op is in flight
        (announced but not yet credited), which locked_descendants alone
        cannot see yet.
        """
        lock = self.locks[node_id]
        lock.acquire()
        try:
            if self.is_locked[node_id] or self.locked_descendants[node_id] > 0 or self.intents[node_id] > 0:
                return False
            self.is_locked[node_id] = True
            self.locked_by[node_id] = uid
            return True
        finally:
            lock.release()

    def _commit_unlock(self, node_id, uid):
        """Clears the node's lock if it is held by uid."""
        lock = self.locks[node_id]
        lock.acquire()
        try:
            if not self.is_locked[node_id] or self.locked_by[node_id] != uid:
                return False
            self.is_locked[node_id] = False
            self.locked_by[node_id] = -1
            return True
        finally:
            lock.release()

    def _collect_locked_descendants(self, node_id):
        """BFS over the subtree, pruned by locked_descendants counts.

        Returns:
            (locked descendant ids, visited ids). Every visited node's mutex
            is still held on return so the caller can mutate swept nodes
            against a stable view; the caller must release them.
        """
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
        """Locks node x for uid, excluding all ancestors and descendants."""
        node_id = self.node_to_id[x]
        ancestors = self._path(node_id)[:-1]
        if not self._announce(ancestors):
            return False
        if not self._commit_lock(node_id, uid):
            self._release_intents(ancestors)
            return False
        self._credit(ancestors, +1)
        return True

    def unlock(self, x, uid):
        """Reverts a prior lock(x, uid); fails if uid does not hold x."""
        node_id = self.node_to_id[x]
        ancestors = self._path(node_id)[:-1]
        if not self._announce(ancestors):
            return False
        if not self._commit_unlock(node_id, uid):
            self._release_intents(ancestors)
            return False
        self._credit(ancestors, -1)
        return True

    def upgrade_lock(self, x, uid):
        """Locks x by sweeping its locked descendants, which must all be uid's.

        A live intent on x means a descendant op is mid-commit, so retry
        rather than sweep a subtree whose bookkeeping is still settling.
        Returns False if the retries are exhausted under contention.
        """
        node_id = self.node_to_id[x]
        path = self._path(node_id)
        for _ in range(_UPGRADE_RETRIES):
            visited = []
            self._acquire(path)
            try:
                for i in path:
                    if self.is_locked[i]:
                        return False
                if self.intents[node_id] > 0:
                    continue
                if self.locked_descendants[node_id] == 0:
                    return False

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
        return False


def run(raw):
    """Parses the problem's input format and returns one true/false line per query."""
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
    """stdin -> stdout entry point."""
    sys.stdout.write(run(sys.stdin.buffer.read()))


def _assert_consistent(tree):
    """Brute-force check of every invariant: counts match reality, ownership
    is set iff locked, no locked node sits under another locked node, and no
    intent leaked."""
    for i in range(tree.n):
        expect = sum(
            1
            for j in range(tree.n)
            if j != i and tree.is_locked[j] and i in tree._path(j)[:-1]
        )
        assert tree.locked_descendants[i] == expect, (i, tree.locked_descendants[i], expect)
        if tree.is_locked[i]:
            assert tree.locked_by[i] != -1, i
            assert tree.locked_descendants[i] == 0, (i, "locked node with locked descendant")
        else:
            assert tree.locked_by[i] == -1, i
        assert tree.intents[i] == 0, (i, "leaked intent")


def _run_pair(tree, f1, f2, timeout=None):
    """Runs two ops from a barrier, asserts neither deadlocks and the tree
    stays consistent; returns results sorted for order-free comparison."""
    barrier = threading.Barrier(2)
    out = []

    def run(f):
        barrier.wait()
        out.append(f())

    threads = [threading.Thread(target=run, args=(f,)) for f in (f1, f2)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=timeout)
    for th in threads:
        assert not th.is_alive(), "thread deadlocked"
    _assert_consistent(tree)
    return sorted(out)


def _run_many(tree, fs, timeout=None):
    """Barrier-synced version of _run_pair for N ops; preserves input order."""
    barrier = threading.Barrier(len(fs))
    out = [None] * len(fs)

    def run(i, f):
        barrier.wait()
        out[i] = f()

    threads = [threading.Thread(target=run, args=(i, f)) for i, f in enumerate(fs)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=timeout)
    for th in threads:
        assert not th.is_alive(), "thread deadlocked"
    _assert_consistent(tree)
    return out


def _smoke_test():
    """Basic concurrent lock/unlock/upgrade pairs."""
    names = ["Root", "A", "B", "C", "D", "E", "F"]

    t = TreeOfSpace(names, 2)
    assert _run_pair(t, lambda: t.lock("C", 1), lambda: t.lock("D", 1)) == [True, True]

    t = TreeOfSpace(names, 2)
    assert _run_pair(t, lambda: t.lock("A", 2), lambda: t.lock("C", 3)) == [False, True]

    t = TreeOfSpace(names, 2)
    assert t.lock("C", 1)
    assert _run_pair(t, lambda: t.unlock("C", 1), lambda: t.unlock("C", 2)) == [False, True]

    t = TreeOfSpace(names, 2)
    assert t.lock("C", 1) and t.lock("D", 1)
    assert _run_pair(t, lambda: t.upgrade_lock("A", 1), lambda: t.lock("C", 2)) == [False, True]
    print("threaded smoke test passed")


def _stress_test():
    """Disjoint subtrees lock in parallel; an ancestor/descendant race has exactly one winner."""
    names = [f"n{i}" for i in range(31)]
    t = TreeOfSpace(names, 2)
    leaves = [15, 16, 23, 30]
    out = _run_many(t, [lambda i=i: t.lock(names[leaves[i]], i) for i in range(4)])
    assert all(out), out
    for i in range(4):
        assert t.unlock(names[leaves[i]], i)
    _assert_consistent(t)

    t2 = TreeOfSpace(names, 2)
    assert _run_pair(t2, lambda: t2.lock("n7", 1), lambda: t2.lock("n15", 2)) == [False, True]
    print("stress test passed")


def _edge_test():
    """Sequential rule checks, then concurrent races with either linearization allowed."""
    names = ["Root", "A", "B", "C", "D", "E", "F"]

    # sequential: descendant locked blocks parent lock
    t = TreeOfSpace(names, 2)
    assert t.lock("C", 1)
    assert not t.lock("A", 2)

    # sequential: parent locked blocks child lock (exercises announce rollback)
    t = TreeOfSpace(names, 2)
    assert t.lock("A", 1)
    assert not t.lock("C", 2)
    assert not t.lock("C", 1)

    # every failed-upgrade path returns False without crashing
    t = TreeOfSpace(names, 2)
    assert not t.upgrade_lock("C", 1)

    t = TreeOfSpace(names, 2)
    assert t.lock("A", 1)
    assert not t.upgrade_lock("A", 2)

    t = TreeOfSpace(names, 2)
    assert t.lock("A", 1)
    assert not t.upgrade_lock("B", 1)

    t = TreeOfSpace(names, 2)
    assert t.lock("C", 1) and t.lock("D", 2)
    assert not t.upgrade_lock("A", 1)

    # upgrade sweeps every branch: descendants unlocked, target locked
    t = TreeOfSpace(names, 2)
    assert t.lock("C", 1) and t.lock("D", 1) and t.lock("E", 1) and t.lock("F", 1)
    assert t.upgrade_lock("Root", 1)
    assert not t.unlock("C", 1) and not t.unlock("D", 1) and not t.unlock("E", 1) and not t.unlock("F", 1)
    assert t.unlock("Root", 1)
    _assert_consistent(t)

    # concurrent: N threads racing on the same leaf -> exactly one wins
    t = TreeOfSpace(names, 2)
    out = _run_many(t, [lambda i=i: t.lock("C", i) for i in range(8)])
    assert sum(out) == 1, out

    # concurrent: lock root vs lock descendant -> exactly one wins
    t = TreeOfSpace(names, 2)
    assert _run_pair(t, lambda: t.lock("Root", 1), lambda: t.lock("C", 2)) == [False, True]

    # concurrent: upgrade vs lock in a sibling subtree -> both succeed
    t = TreeOfSpace(names, 2)
    assert t.lock("C", 1) and t.lock("D", 1)
    assert _run_pair(t, lambda: t.upgrade_lock("A", 1), lambda: t.lock("E", 2)) == [True, True]

    # concurrent: upgrade vs unlock of a swept descendant -> both orders are valid
    t = TreeOfSpace(names, 2)
    assert t.lock("C", 1) and t.lock("D", 1)
    assert _run_pair(t, lambda: t.upgrade_lock("A", 1), lambda: t.unlock("C", 1)) in (
        [False, True],
        [True, True],
    )

    # concurrent: two upgrades of the same node -> exactly one wins
    t = TreeOfSpace(names, 2)
    assert t.lock("C", 1) and t.lock("D", 1)
    assert _run_pair(t, lambda: t.upgrade_lock("A", 1), lambda: t.upgrade_lock("A", 1)) == [False, True]

    # intents stay balanced after a batch of failures and successes
    t = TreeOfSpace(names, 2)
    assert not t.upgrade_lock("C", 1)
    assert t.lock("C", 1)
    assert not t.lock("C", 2)
    assert not t.unlock("C", 2)
    assert t.unlock("C", 1)
    assert not t.unlock("C", 1)
    _assert_consistent(t)
    print("edge test passed")


def _announce_rollback_deadlock_test():
    """Regression: _announce's failure path used to roll back intents while
    still holding the failing node's mutex (acquiring an ancestor mutex in
    reverse order), deadlocking against a concurrent upgrade's root->leaf
    path acquisition. A small switch interval widens the race window;
    _run_pair(timeout) catches a hang."""
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-5)
    try:
        names = ["Root", "A", "B", "C", "D", "E", "F"]
        for _ in range(200):
            t = TreeOfSpace(names, 2)
            assert t.lock("A", 1)
            _run_pair(t, lambda: t.lock("C", 2), lambda: t.upgrade_lock("A", 3), timeout=5)
    finally:
        sys.setswitchinterval(old)
    print("announce-rollback deadlock regression passed")


def _credit_upgrade_race_test():
    """Regression: _credit used to clear each ancestor's intent in the same
    critical section as its locked_descendants update. A lock on C paused
    between updating Root and A then showed intents[Root] == 0 while the op
    was still in flight, and upgrade_lock(Root) swept a half-committed state
    (Root locked, stale locked_descendants, C still locked).

    A gate on A's mutex parks T1 at exactly that point; upgrade must observe
    the still-active intent on Root and back off instead of proceeding.
    """
    names = ["Root", "A", "B", "C", "D", "E", "F"]
    t = TreeOfSpace(names, 2)
    root, a, c = 0, 1, t.node_to_id["C"]
    parked = threading.Event()
    resume = threading.Event()
    real_lock = t.locks[a]

    class Gate:
        """Lock proxy that parks T1 on its first acquire, mid-_credit."""

        armed = True

        def acquire(self):
            if self.armed:
                self.armed = False
                parked.set()
                assert resume.wait(5), "test orchestration broken"
            return real_lock.acquire()

        def release(self):
            real_lock.release()

    def t1():
        assert t._announce([root, a])
        assert t._commit_lock(c, 1)
        t.locks[a] = Gate()  # gate only _credit's acquire, not _announce's
        t._credit([root, a], +1)

    th = threading.Thread(target=t1)
    th.start()
    assert parked.wait(5)  # T1 mid-credit: Root's bump visible, A's pending
    assert not t.upgrade_lock("Root", 1)  # must back off on the live intent
    resume.set()
    th.join(5)
    assert not th.is_alive()
    _assert_consistent(t)
    assert t.is_locked[c] and not t.is_locked[root]
    print("credit/upgrade race regression passed")


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
        _stress_test()
        _edge_test()
        _announce_rollback_deadlock_test()
        _credit_upgrade_race_test()
        print("all tests passed")
    else:
        solve()
