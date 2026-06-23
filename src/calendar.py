from __future__ import annotations

import datetime as dt
import jdatetime
import pandas as pd


def yyyymmdd_to_datetime(value) -> pd.Timestamp:
    if pd.isna(value):
        return pd.NaT
    s = str(int(value))
    return pd.to_datetime(s, format="%Y%m%d", errors="coerce")


def jalali_int_to_gregorian(value) -> pd.Timestamp:
    if pd.isna(value):
        return pd.NaT
    s = str(int(value)).zfill(8)
    jy, jm, jd = int(s[:4]), int(s[4:6]), int(s[6:8])
    try:
        g = jdatetime.date(jy, jm, jd).togregorian()
    except ValueError:
        return pd.NaT
    return pd.Timestamp(dt.date(g.year, g.month, g.day))


def gregorian_to_jalali_year_month(ts) -> tuple[int | None, int | None]:
    if pd.isna(ts):
        return None, None
    stamp = pd.Timestamp(ts)
    j = jdatetime.date.fromgregorian(date=stamp.date())
    return j.year, j.month
