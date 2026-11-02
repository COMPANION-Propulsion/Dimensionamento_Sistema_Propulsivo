import math
import unittest
from ventola_designer.polars import PolarGrid, PolarDomainError, coordinate_hash
from ventola_designer.geometry import naca4


class PolarTests(unittest.TestCase):
    def grid(self):
        reynolds, mach, alpha = [10000,100000],[0,.2],[-10,10]
        data = {"profile":"NACA4412","coordinates_sha256":coordinate_hash(naca4("NACA4412")),
                "reynolds":reynolds,"mach":mach,"alpha_deg":alpha,
                "cl":[[[math.log(r)+m+a for a in alpha] for m in mach] for r in reynolds],
                "cd":[[[.01,.03],[.01,.03]],[[.01,.03],[.01,.03]]],
                "confidence":[[[.9,.9],[.9,.9]],[[.9,.9],[.9,.9]]]}
        return PolarGrid(data)

    def test_affine_interpolation_and_endpoints(self):
        grid = self.grid()
        re = math.sqrt(1e9)
        cl,cd,confidence = grid.coefficients(2,re,.1)
        self.assertAlmostEqual(cl, math.log(re)+.1+2)
        self.assertAlmostEqual(cd,.022)
        for re in (10000,100000):
            for m in (0,.2):
                for a in (-10,10):
                    self.assertAlmostEqual(grid.coefficients(a,re,m)[0],math.log(re)+m+a)

    def test_reject_each_out_of_domain(self):
        for args in [(0,9999,.1),(0,100001,.1),(-11,20000,.1),(11,20000,.1),
                     (0,20000,-.01),(0,20000,.21),(0,float("nan"),.1)]:
            with self.subTest(args=args), self.assertRaises(PolarDomainError):
                self.grid().coefficients(*args)

    def test_confidence_and_profile_identity(self):
        grid = self.grid()
        grid.validate_profile("NACA4412")
        with self.assertRaises(PolarDomainError):
            grid.validate_profile("NACA2412")
        grid.data["confidence"][0][0][0] = .1
        with self.assertRaises(PolarDomainError):
            grid.coefficients(0,20000,.1)
        grid.data["coordinates_sha256"] = "different_geometry"
        with self.assertRaises(PolarDomainError):
            grid.validate_profile("NACA4412")
