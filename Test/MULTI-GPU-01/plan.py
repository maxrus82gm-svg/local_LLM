"""Source-only prototype: asymmetric GPU weight budgets in MiB.
Not connected to the live Manager or engine. Headroom is additional to user reserve.
Run: python plan.py
"""
import unittest


def allocate(devices, requested_mib=None, headroom_mib=2048):
    """Rows: (UUID, free MiB, user reserve MiB), in masked device order.
    Proportional to available capacities, integer largest remainder; no overbooking.
    """
    def nonneg(value):
        return type(value) is int and value >= 0
    if not devices or not nonneg(headroom_mib):
        raise ValueError('invalid_inventory')
    if requested_mib is not None and (not nonneg(requested_mib) or requested_mib == 0):
        raise ValueError('invalid_requested_budget')
    ids, capacity = [], []
    for uid, free, reserve in devices:
        if not isinstance(uid, str) or not uid or uid in ids or not nonneg(free) or not nonneg(reserve):
            raise ValueError('invalid_inventory')
        ids.append(uid)
        capacity.append(max(0, free-reserve-headroom_mib))
    total = sum(capacity)
    target = min(total, requested_mib if requested_mib is not None else total)
    if target < len(ids) or any(c == 0 for c in capacity):
        raise ValueError('gpu_reserve_insufficient')
    shares = [target*c//total for c in capacity]
    rem = target-sum(shares)
    order = sorted(range(len(ids)), key=lambda i: (-(target*capacity[i]%total), ids[i]))
    for i in order[:rem]:
        shares[i] += 1
    if any(s == 0 for s in shares):
        raise ValueError('gpu_reserve_insufficient')
    return dict(zip(ids, shares))


class Tests(unittest.TestCase):
    def test_work(self):
        self.assertEqual(allocate([('4070',16384,2048),('3060',8192,0)],21504), {'4070':12288,'3060':6144})
    def test_one_to_five(self):
        for n in range(1,6):
            rows = [(str(i),8192+1024*i,512) for i in range(n)]
            for request in (None,4096,100000):
                out = allocate(rows,request)
                self.assertEqual(sum(out.values()), min(sum(r[1]-r[2]-2048 for r in rows), request or 1000000))
                self.assertTrue(all(0 < out[u] <= f-r-2048 for u,f,r in rows))
                self.assertEqual(out,allocate(rows[::-1],request))
    def test_busy_and_invalid(self):
        for rows, request in (([('a',2048,0)],None),([('a',8192,0),('a',8192,0)],None),([('a',8192,0)],0),([('a',True,0)],None),([('a',8192,0),('b',8192,0)],1)):
            with self.assertRaises(ValueError):
                allocate(rows,request)
    def test_rounding(self):
        self.assertEqual(allocate([('a',100,0),('b',100,0),('c',100,0)],5,0),{'a':2,'b':2,'c':1})


if __name__ == '__main__':
    unittest.main()
