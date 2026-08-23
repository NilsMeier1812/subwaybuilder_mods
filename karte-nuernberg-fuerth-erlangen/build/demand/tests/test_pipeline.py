#!/usr/bin/env python3
"""
Testsuite für die Nachfrage-Pipeline. Nur Standardbibliothek:

    python3 tests/test_pipeline.py
    python3 -m unittest discover -s tests -v
"""

import gzip
import json
import math
import os
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import build_demand
import make_fixtures
import verify_pois
from nuedemand import buildings, commute, geo, jobs, laea, pendler, routing, zensus


class TestLaea(unittest.TestCase):
    def test_origin(self):
        x, y = laea.forward(10.0, 52.0)
        self.assertAlmostEqual(x, 4321000.0, places=3)
        self.assertAlmostEqual(y, 3210000.0, places=3)

    def test_roundtrip(self):
        for lon, lat in [(11.0823, 49.4455), (10.9887, 49.5967), (6.0, 47.3), (15.0, 55.0)]:
            x, y = laea.forward(lon, lat)
            lo, la = laea.inverse(x, y)
            self.assertAlmostEqual(lo, lon, places=7)
            self.assertAlmostEqual(la, lat, places=7)

    def test_distance_matches_haversine(self):
        """Flächentreue Projektion: über 10 km darf die Länge kaum abweichen."""
        a = (11.0823, 49.4455)
        b = (11.0823, 49.5355)
        x1, y1 = laea.forward(*a)
        x2, y2 = laea.forward(*b)
        projected = math.hypot(x2 - x1, y2 - y1)
        self.assertLess(abs(projected / geo.haversine(a, b) - 1), 0.005)

    def test_grid_id(self):
        x, y, size = laea.parse_grid_id("CRS3035RES100mN2926400E4399400")
        self.assertEqual(size, 100)
        self.assertEqual((x, y), (4399450.0, 2926450.0))  # Zellmittelpunkt
        lon, lat = laea.grid_id_to_lonlat("CRS3035RES100mN2926400E4399400")
        self.assertTrue(10.9 < lon < 11.3 and 49.3 < lat < 49.7)

    def test_bad_grid_id(self):
        with self.assertRaises(ValueError):
            laea.parse_grid_id("kein-gitter")


class TestGeo(unittest.TestCase):
    def setUp(self):
        self.lat, self.lon = 49.44, 11.08
        self.dlat = 1000 / 111320.0
        self.dlon = 1000 / (111320 * math.cos(math.radians(self.lat)))
        self.ring = [
            [self.lon, self.lat],
            [self.lon + self.dlon, self.lat],
            [self.lon + self.dlon, self.lat + self.dlat],
            [self.lon, self.lat + self.dlat],
            [self.lon, self.lat],
        ]

    def test_area(self):
        self.assertAlmostEqual(geo.ring_area_m2(self.ring) / 1e6, 1.0, places=2)

    def test_centroid(self):
        lon, lat = geo.ring_centroid(self.ring)
        self.assertAlmostEqual(lon, self.lon + self.dlon / 2, places=5)
        self.assertAlmostEqual(lat, self.lat + self.dlat / 2, places=5)

    def test_point_in_polygon_with_hole(self):
        hole = [
            [self.lon + self.dlon * f, self.lat + self.dlat * g]
            for f, g in [(0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6), (0.4, 0.4)]
        ]
        poly = [self.ring, hole]
        self.assertTrue(geo.point_in_polygon(self.lon + self.dlon * 0.2, self.lat + self.dlat * 0.2, poly))
        self.assertFalse(geo.point_in_polygon(self.lon + self.dlon * 0.5, self.lat + self.dlat * 0.5, poly))
        self.assertAlmostEqual(geo.polygon_area_m2(poly) / 1e6, 0.96, places=2)

    def test_multipolygon(self):
        geom = {"type": "MultiPolygon", "coordinates": [[self.ring], [self.ring]]}
        self.assertAlmostEqual(geo.geometry_area_m2(geom) / 1e6, 2.0, places=2)


class TestZensus(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def write(self, name, text, encoding="utf-8", compress=False):
        path = os.path.join(self.dir, name)
        if compress:
            with gzip.open(path, "wt", encoding=encoding) as fh:
                fh.write(text)
        else:
            with open(path, "w", encoding=encoding) as fh:
                fh.write(text)
        return path

    def test_id_only(self):
        path = self.write(
            "a.csv",
            "GITTER_ID_100m;werte\nCRS3035RES100mN2926400E4399400;42\n"
            "CRS3035RES100mN2926500E4399400;-1\n",
        )
        cells = zensus.read_population_grid(path)
        self.assertEqual(len(cells), 1)  # gesperrte Zelle (-1) fliegt raus
        self.assertEqual(cells[0]["residents"], 42)

    def test_explicit_coordinates_latin1(self):
        path = self.write(
            "b.csv",
            "GITTER_ID_100m;x_mp_100m;y_mp_100m;Einwohner\n"
            "CRS3035RES100mN2926400E4399400;4399450;2926450;10\n",
            encoding="latin-1",
        )
        cells = zensus.read_population_grid(path)
        self.assertEqual(cells[0]["residents"], 10)

    def test_gzip_and_bbox(self):
        path = self.write(
            "c.csv.gz",
            "GITTER_ID_100m;werte\nCRS3035RES100mN2926400E4399400;5\n"
            "CRS3035RES100mN3200000E4200000;9\n",
            compress=True,
        )
        cells = zensus.read_population_grid(path, bbox=[10.85, 49.32, 11.28, 49.66])
        self.assertEqual(len(cells), 1)

    def test_missing_value_column(self):
        path = self.write("d.csv", "GITTER_ID_100m;irgendwas\nx;1\n")
        with self.assertRaises(zensus.ZensusFormatError):
            zensus.read_population_grid(path)


class TestBuildings(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.feats = [
            self.square(11.08, 49.44, 40, {"building": "office", "building:levels": "6"}),
            self.square(11.09, 49.44, 30, {"building": "apartments"}),
            self.square(11.10, 49.44, 5, {"building": "garage"}),
            self.square(11.11, 49.44, 4, {"building": "yes"}),
            self.square(11.12, 49.44, 25, {"building": "yes", "shop": "supermarket"}),
            self.square(20.00, 49.44, 25, {"building": "office"}),
        ]

    def tearDown(self):
        shutil.rmtree(self.dir)

    @staticmethod
    def square(lon, lat, side_m, props):
        dlat = side_m / 111320.0
        dlon = side_m / (111320 * math.cos(math.radians(lat)))
        ring = [[lon, lat], [lon + dlon, lat], [lon + dlon, lat + dlat], [lon, lat + dlat], [lon, lat]]
        return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": props}

    def test_filters(self):
        path = os.path.join(self.dir, "b.geojson")
        with open(path, "w") as fh:
            json.dump({"type": "FeatureCollection", "features": self.feats}, fh)
        result = buildings.read_buildings(path, bbox=[10.85, 49.32, 11.28, 49.66])
        kinds = sorted(b["kind"] for b in result)
        self.assertEqual(kinds, ["office", "residential", "retail"])

    def test_geojsonl_identical(self):
        a = os.path.join(self.dir, "b.geojson")
        b = os.path.join(self.dir, "b.geojsonl")
        with open(a, "w") as fh:
            json.dump({"type": "FeatureCollection", "features": self.feats}, fh)
        with open(b, "w") as fh:
            for feat in self.feats:
                fh.write(json.dumps(feat) + "\n")
        bbox = [10.85, 49.32, 11.28, 49.66]
        self.assertEqual(buildings.read_buildings(a, bbox=bbox), buildings.read_buildings(b, bbox=bbox))

    def test_office_outweighs_residential(self):
        path = os.path.join(self.dir, "b.geojson")
        with open(path, "w") as fh:
            json.dump({"type": "FeatureCollection", "features": self.feats}, fh)
        by_kind = {b["kind"]: b for b in buildings.read_buildings(path, bbox=[10.85, 49.32, 11.28, 49.66])}
        self.assertGreater(by_kind["office"]["weight"], by_kind["residential"]["weight"] * 10)


class TestJobs(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_parsing_and_totals(self):
        path = os.path.join(self.dir, "j.csv")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('ags;name;beschaeftigte\n09564000;Nürnberg;285.000\n'
                     '09563000;Fürth;48000\n09562000;Erlangen;"75000"\n09999;X;x\n')
        result = jobs.read_jobs_csv(path, non_sv_factor=1.0)
        self.assertEqual(result, {"09564000": 285000, "09563000": 48000, "09562000": 75000})

    def test_distribution_preserves_total(self):
        index = geo.PolygonIndex(
            [{"geometry": {"type": "Polygon", "coordinates": [[[11.0, 49.4], [11.2, 49.4], [11.2, 49.6], [11.0, 49.6], [11.0, 49.4]]]},
              "properties": {"AGS": "09564000"}}],
            "AGS",
        )
        blds = [{"lon": 11.05, "lat": 49.45, "weight": 100.0}, {"lon": 11.1, "lat": 49.5, "weight": 300.0},
                {"lon": 9.0, "lat": 48.0, "weight": 10.0}]
        self.assertEqual(jobs.assign_to_municipality(blds, index), 1)
        jobs.distribute(blds, {"09564000": 4000})
        inside = [b for b in blds if b["ags"] == "09564000"]
        self.assertAlmostEqual(sum(b["jobs"] for b in inside), 4000.0, places=6)
        self.assertAlmostEqual(inside[1]["jobs"] / inside[0]["jobs"], 3.0, places=6)


class TestPendler(unittest.TestCase):
    def test_filter_and_counts(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as fh:
            fh.write("von_ags;nach_ags;anzahl\n09564000;09564000;180.000\n09563000;09564000;22000\n"
                     "09564000;09162000;9000\n09999000;09564000;5000\n")
            path = fh.name
        try:
            matrix, info = pendler.read_matrix(path, keep_ags={"09564000", "09563000"})
            self.assertEqual(matrix[("09564000", "09564000")], 180000)
            self.assertEqual(info["inbound_outside"], 5000)
            self.assertEqual(info["outbound_outside"], 9000)
        finally:
            os.unlink(path)


class TestRounding(unittest.TestCase):
    def test_largest_remainder_exact(self):
        for total in (1, 7, 100, 12345):
            counts = commute._largest_remainder([1.0, 2.0, 3.0, 0.5], total)
            self.assertEqual(sum(counts), total)

    def test_zero_and_empty(self):
        self.assertEqual(commute._largest_remainder([], 10), [])
        self.assertEqual(commute._largest_remainder([1.0, 2.0], 0), [0, 0])
        self.assertEqual(commute._largest_remainder([0.0, 0.0], 5), [0, 0])


class MockOSRMHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if "/table/" in self.path:
            coords = self.path.split("/table/v1/driving/")[1].split("?")[0]
            n_all = len(coords.split(";"))
            query = self.path.split("?", 1)[1] if "?" in self.path else ""
            params = dict(kv.split("=", 1) for kv in query.split("&") if "=" in kv)
            n_src = len(params.get("sources", "").split(";")) if params.get("sources") else n_all
            n_dst = len(params.get("destinations", "").split(";")) if params.get("destinations") else n_all
            body = json.dumps({
                "code": "Ok",
                "durations": [[600.0] * n_dst for _ in range(n_src)],
                "distances": [[7500.0] * n_dst for _ in range(n_src)],
            }).encode()
        else:
            body = json.dumps({"code": "Ok", "routes": [{"duration": 1.0, "distance": 1.0}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class TestRouting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), MockOSRMHandler)
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_estimate_plausible(self):
        seconds, meters = routing.estimate((11.0823, 49.4455), (10.9887, 49.4783))
        self.assertTrue(8000 < meters < 11000, meters)
        self.assertTrue(8 * 60 < seconds < 20 * 60, seconds)

    def test_same_point(self):
        seconds, meters = routing.estimate((11.0, 49.4), (11.0, 49.4))
        self.assertEqual(meters, 0)
        self.assertGreater(seconds, 0)

    def test_osrm_client(self):
        client = routing.OSRMClient(self.url)
        self.assertTrue(client.available())
        pairs = [((11.0, 49.4), (11.1, 49.5)), ((11.1, 49.5), (11.0, 49.4))]
        result = routing.route_pairs(pairs, client=client)
        self.assertEqual(result, [(600, 7500), (600, 7500)])

    def test_osrm_unavailable_falls_back(self):
        client = routing.OSRMClient("http://127.0.0.1:1")
        self.assertFalse(client.available())


class TestRegionConfig(unittest.TestCase):
    """region.json ist von Hand gepflegt — hier wird sie gegengeprüft."""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(HERE, "..", "region.json")
        with open(path, encoding="utf-8") as fh:
            cls.region = json.load(fh)

    def test_bbox_matches_map(self):
        self.assertEqual(self.region["bbox"], make_fixtures.BBOX)

    def test_view_state_inside_bbox(self):
        view = self.region["initial_view_state"]
        self.assertTrue(geo.bbox_contains(self.region["bbox"], view["longitude"], view["latitude"]))

    def test_poi_types_known(self):
        codes, _source = verify_pois.load_codes()
        for poi in self.region["special_demand"]:
            self.assertIn(poi["type"], codes, poi["name"])

    def test_poi_inside_bbox(self):
        for poi in self.region["special_demand"]:
            lon, lat = poi["location"]
            self.assertTrue(geo.bbox_contains(self.region["bbox"], lon, lat), poi["name"])

    def test_poi_codes_unique(self):
        codes = [p["code"] for p in self.region["special_demand"] if p.get("code")]
        self.assertEqual(len(codes), len(set(codes)))

    def test_poi_capacities_positive(self):
        for poi in self.region["special_demand"]:
            self.assertGreater(poi["total_capacity"], 0, poi["name"])
            self.assertGreater(poi.get("pop_size", 100), 0, poi["name"])

    def test_verify_runs_clean(self):
        out = os.path.join(tempfile.mkdtemp(), "pois.geojson")
        rc = verify_pois.main(["--region", os.path.join(HERE, "..", "region.json"), "--out", out])
        self.assertEqual(rc, 0)
        with open(out, encoding="utf-8") as fh:
            collection = json.load(fh)
        self.assertEqual(len(collection["features"]), len(self.region["special_demand"]) + 1)


class TestEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        cls.fx = make_fixtures.build(os.path.join(cls.dir, "fixtures"), scale=0.15)
        cls.out = os.path.join(cls.dir, "out", "demand_data.json")
        cls.argv = [
            "--zensus", cls.fx["zensus"],
            "--buildings", cls.fx["buildings"],
            "--gemeinden", cls.fx["gemeinden"],
            "--jobs", cls.fx["jobs"],
            "--pendler", cls.fx["pendler"],
            "--out", cls.out,
            "--quiet",
        ]
        cls.rc = build_demand.main(cls.argv)
        with open(cls.out, encoding="utf-8") as fh:
            cls.demand = json.load(fh)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir)

    def test_exit_code(self):
        self.assertEqual(self.rc, 0)

    def test_schema(self):
        self.assertEqual(sorted(self.demand.keys()), ["points", "pops"])
        for point in self.demand["points"]:
            self.assertEqual(sorted(point.keys()), ["id", "jobs", "location", "popIds", "residents"])
            self.assertEqual(len(point["location"]), 2)
            self.assertIsInstance(point["jobs"], int)
            self.assertIsInstance(point["residents"], int)
        for pop in self.demand["pops"]:
            self.assertEqual(
                sorted(pop.keys()),
                ["drivingDistance", "drivingSeconds", "id", "jobId", "residenceId", "size"],
            )

    def test_references_resolve(self):
        ids = {p["id"] for p in self.demand["points"]}
        for pop in self.demand["pops"]:
            self.assertIn(pop["residenceId"], ids)
            self.assertIn(pop["jobId"], ids)

    def test_pop_ids_backlink(self):
        by_point = {p["id"]: set(p["popIds"]) for p in self.demand["points"]}
        for pop in self.demand["pops"]:
            self.assertIn(pop["id"], by_point[pop["residenceId"]])
            self.assertIn(pop["id"], by_point[pop["jobId"]])

    def test_values_sane(self):
        for pop in self.demand["pops"]:
            self.assertGreater(pop["size"], 0)
            self.assertLessEqual(pop["size"], 200)
            self.assertGreater(pop["drivingSeconds"], 0)
            self.assertGreaterEqual(pop["drivingDistance"], 0)

    def test_points_inside_bbox(self):
        bbox = make_fixtures.BBOX
        for point in self.demand["points"]:
            lon, lat = point["location"]
            self.assertTrue(geo.bbox_contains(bbox, lon, lat), point["location"])

    def test_deterministic(self):
        second = os.path.join(self.dir, "out2", "demand_data.json")
        build_demand.main(self.argv[:-2] + [second, "--quiet"])
        with open(second, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), self.demand)

    def test_totals_match_matrix(self):
        """Die verteilten Pendler müssen der Summe der Binnenbeziehungen entsprechen."""
        keep = {"09564000", "09563000", "09562000", "09565000"}
        matrix, _info = pendler.read_matrix(self.fx["pendler"], keep_ags=keep)
        self.assertEqual(sum(p["size"] for p in self.demand["pops"]), sum(matrix.values()))

    def test_residents_preserved(self):
        cells = zensus.read_population_grid(self.fx["zensus"], bbox=make_fixtures.BBOX)
        total_in = zensus.total_residents(cells)
        total_out = sum(p["residents"] for p in self.demand["points"])
        self.assertLess(abs(total_out - total_in) / total_in, 0.01)

    def test_without_matrix_and_jobs(self):
        """Auch ohne amtliche Zahlen muss ein brauchbares Ergebnis herauskommen."""
        out = os.path.join(self.dir, "out3", "demand_data.json")
        rc = build_demand.main([
            "--zensus", self.fx["zensus"],
            "--buildings", self.fx["buildings"],
            "--out", out,
            "--quiet",
        ])
        self.assertEqual(rc, 0)
        with open(out, encoding="utf-8") as fh:
            fallback = json.load(fh)
        self.assertGreater(len(fallback["points"]), 100)
        self.assertGreater(len(fallback["pops"]), 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
