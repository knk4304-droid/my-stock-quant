import unittest
from adaptive_signal_research import signals, candidate_score
from adaptive_strategy_review import review

class AdaptiveResearchTests(unittest.TestCase):
    def test_uptrend(self):
        c=[100+i for i in range(81)]
        s=signals(c,c,[1000]*81)
        self.assertEqual(s["regime"],"up")
        for h in ("short","swing","medium"):
            self.assertIsNotNone(candidate_score(s,h))
    def test_downtrend_abstains(self):
        c=[200-i for i in range(81)]
        s=signals(c,c,[1000]*81)
        self.assertEqual(s["regime"],"down")
        self.assertIsNone(candidate_score(s,"swing"))
    def test_bad_data(self):
        with self.assertRaises(ValueError):
            signals([1]*60,[1]*60,[1]*60)
        with self.assertRaises(ValueError):
            signals([1]*60+[float("nan")],[1]*61,[1]*61)
    def test_range(self):
        s=signals([100]*61,[100]*61,[1000]*61)
        self.assertEqual(s["regime"],"range")
        self.assertEqual(candidate_score(s,"short"),0)
    def folds(self):
        return [dict(start=2*i,end=2*i+1,baseline_net=.01,challenger_net=.02,baseline_mdd=.1,challenger_mdd=.09) for i in range(12)]
    def test_gate(self):
        f=self.folds()
        self.assertFalse(review(f[:11])["eligible_for_review"])
        self.assertTrue(review(f)["eligible_for_review"])
        f[-1]["challenger_mdd"]=.2
        self.assertFalse(review(f)["eligible_for_review"])
    def test_numeric_string_drawdown(self):
        f=self.folds()
        for row in f:
            row["baseline_mdd"]="0.10"
            row["challenger_mdd"]="0.090"
        self.assertTrue(review(f)["eligible_for_review"])
        f[-1]["challenger_mdd"]="0.2"
        self.assertFalse(review(f)["eligible_for_review"])
    def test_invalid_threshold(self):
        for value in (12.5, True, 11):
            with self.assertRaises(ValueError):
                review(self.folds(), min_folds=value)
    def test_nonfinite_metrics(self):
        f=self.folds()
        f[0]["challenger_net"]=float("inf")
        with self.assertRaises(ValueError):
            review(f)
    def test_invalid_date(self):
        f=self.folds()
        f[0]["start"]="2020-01-01garbage"
        f[0]["end"]="2020-01-02"
        with self.assertRaises(ValueError):
            review(f)
    def test_overlap(self):
        f=self.folds()
        f[1]["start"]=f[0]["end"]
        with self.assertRaises(ValueError): review(f)

if __name__=="__main__": unittest.main()
