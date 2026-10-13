import os
import random
import sys
import unittest
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nosqlbench.adapters import CouchDBAdapter, MemoryAdapter  # noqa: E402
from nosqlbench.docs import DocFactory  # noqa: E402
from nosqlbench.generators import (AckCounter, ScrambledZipfianChooser, Zipfian,  # noqa: E402
                                   build_key, fnv64, make_chooser)
from nosqlbench.runner import load_phase, run_phase  # noqa: E402
from nosqlbench.workloads import WORKLOADS  # noqa: E402


class TestGenerators(unittest.TestCase):
    def test_fnv_deterministic(self):
        self.assertEqual(fnv64(0), fnv64(0))
        self.assertNotEqual(fnv64(1), fnv64(2))
        self.assertTrue(build_key(5).startswith("user"))

    def test_zipfian_is_skewed_and_in_range(self):
        z = Zipfian(1000)
        rng = random.Random(1)
        c = Counter(z.next(rng) for _ in range(50_000))
        self.assertTrue(all(0 <= k < 1000 for k in c))
        self.assertGreater(c[0], 20 * (50_000 / 1000))  # item teratas >> rata-rata seragam

    def test_scrambled_zipfian_range_and_skew(self):
        ch = ScrambledZipfianChooser(5000)
        rng = random.Random(2)
        c = Counter(ch.next(rng) for _ in range(30_000))
        self.assertTrue(all(0 <= k < 5000 for k in c))
        self.assertGreater(c.most_common(1)[0][1], 10 * (30_000 / 5000))

    def test_latest_prefers_recent(self):
        ctr = AckCounter(1000)
        ch = make_chooser("latest", 1000, ctr)
        rng = random.Random(3)
        xs = [ch.next(rng) for _ in range(5000)]
        self.assertGreater(sum(x >= 900 for x in xs) / len(xs), 0.5)
        self.assertTrue(all(0 <= x <= 999 for x in xs))

    def test_ack_counter_contiguous(self):
        c = AckCounter(10)
        a, b = c.next(), c.next()
        c.acknowledge(b)
        self.assertEqual(c.last(), 9)   # a belum selesai
        c.acknowledge(a)
        self.assertEqual(c.last(), 11)


class TestWorkloads(unittest.TestCase):
    def test_proportions_sum_to_one_and_match_paper(self):
        for w in WORKLOADS.values():
            self.assertAlmostEqual(sum(w.proportions.values()), 1.0)
        self.assertEqual(WORKLOADS["E"].proportions, {"SCAN": 0.95, "INSERT": 0.05})
        self.assertEqual(WORKLOADS["D"].request_distribution, "latest")
        self.assertEqual(set(WORKLOADS), set("ABCDEFGH"))

    def test_chooser_proportions(self):
        pick = WORKLOADS["B"].chooser()
        rng = random.Random(4)
        c = Counter(pick(rng) for _ in range(20_000))
        self.assertAlmostEqual(c["READ"] / 20_000, 0.95, delta=0.01)

    def test_document_size_is_10kb(self):
        d = DocFactory().fields(random.Random(0))
        self.assertEqual(len(d), 20)
        self.assertEqual(sum(len(v) for v in d.values()), 20 * 500)


class TestRunnerMemory(unittest.TestCase):
    def test_all_workloads_run_without_errors(self):
        ad, f = MemoryAdapter(), DocFactory()
        ad.prepare()
        load_phase(ad, 500, f, seed=1, batch_size=100)
        for name, wl in WORKLOADS.items():
            for thr in (1, 3):
                res = run_phase(ad, wl, 500, 600, thr, f, seed=7)
                self.assertEqual(res["errors"], 0, f"workload {name} thr {thr}")
                self.assertEqual(res["ok_ops"], 600)
                self.assertGreater(res["throughput_ops_s"], 0)

    def test_inserts_grow_dataset(self):
        ad, f = MemoryAdapter(), DocFactory()
        ad.prepare()
        load_phase(ad, 200, f, 1)
        run_phase(ad, WORKLOADS["D"], 200, 1000, 3, f, 2)
        self.assertGreater(len(ad._docs), 200)


class TestCouchDBAdapterAgainstFake(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import requests  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("requests tidak terpasang")
        from fake_couchdb import make_server
        cls.srv = make_server()
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_crud_scan_and_workloads(self):
        ad = CouchDBAdapter(url=self.url, user="u", password="p", db="ycsb", threads=4)
        f = DocFactory()
        ad.prepare()
        load_phase(ad, 300, f, 1, batch_size=100)
        self.assertEqual(ad.read(build_key(0))["field0"], ad.read(build_key(0))["field0"])
        self.assertIsNone(ad.read("tidak-ada"))
        ad.update(build_key(1), {"field3": "X"})
        self.assertEqual(ad.read(build_key(1))["field3"], "X")
        rows = ad.scan("user", 10)
        self.assertEqual(len(rows), 10)
        self.assertEqual([r["_id"] for r in rows], sorted(r["_id"] for r in rows))
        for name in ("A", "E", "F"):
            res = run_phase(ad, WORKLOADS[name], 300, 200, 3, f, seed=5)
            self.assertEqual(res["errors"], 0, name)


if __name__ == "__main__":
    unittest.main()