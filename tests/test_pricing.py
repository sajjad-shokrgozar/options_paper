import math
from src.pricing_bs import bs_price, implied_vol


def test_bs_iv_roundtrip():
    for S in [100, 50000]:
        for K in [90, 100, 110]:
            for T in [0.1, 1.0]:
                for r in [0.03, 0.34]:
                    for sigma in [0.2, 0.8]:
                        for kind in ["call", "put"]:
                            p = bs_price(S, K, T, r, sigma, kind)
                            iv, reason = implied_vol(p, S, K, T, r, kind, min_price=0)
                            assert reason == "ok"
                            assert abs(iv - sigma) < 1e-6


def test_put_call_parity_high_rate():
    S, K, T, r, sigma = 100, 95, 0.7, 0.34, 0.55
    c = bs_price(S, K, T, r, sigma, "call")
    p = bs_price(S, K, T, r, sigma, "put")
    assert abs(c - p - (S - K * math.exp(-r * T))) < 1e-8
