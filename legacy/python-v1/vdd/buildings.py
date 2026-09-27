"""Voucher-friendliness score per building, from Person 1's HPD/HRA table.

Two modes:
  - No labels (hackathon default): an empirical-Bayes score. Evidence of
    acceptance (past HRA placements) vs. evidence of refusal (our flagged
    listings, CHR complaints), shrunk toward the owner's whole portfolio and
    then toward the borough. A building with 1 placement and 0 flags isn't
    "100% friendly"; it inherits what we know about its owner.
  - Labels present (`accepted_voucher` column, e.g. from a caseworker outcome
    log): a logistic regression over the same features, cross-validated.

Habitability is kept separate on purpose. Landlords who take vouchers are
sometimes the ones with the worst buildings; ranking them as "friendly" without
a warning would steer families into hazardous housing.

Expected input columns (missing ones default to 0):
  bbl, address, borough, lat, lon, units, owner, hra_placements_3yr,
  flagged_listings, clean_listings, chr_complaints, class_c_violations,
  open_violations, rent_stabilized_units
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

FEATURES = ["hra_placements_3yr", "flagged_listings", "clean_listings", "chr_complaints",
            "class_c_violations", "open_violations", "rent_stabilized_units", "units"]

# Pseudo-counts: how many observations' worth of weight each prior level gets.
OWNER_PRIOR_STRENGTH = 3.0
BOROUGH_PRIOR_STRENGTH = 5.0


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in FEATURES:
        if c not in df:
            df[c] = 0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    if "owner" not in df:
        df["owner"] = df.get("bbl", pd.Series(range(len(df)))).astype(str)
    if "borough" not in df:
        df["borough"] = "NYC"
    # Successes: placements. Failures: refusals we observed (flags weigh more than
    # a complaint because a flag is our own verified evidence).
    df["_succ"] = df["hra_placements_3yr"]
    df["_fail"] = df["flagged_listings"] * 1.0 + df["chr_complaints"] * 0.5
    return df


def score_heuristic(df: pd.DataFrame) -> pd.DataFrame:
    return _finish(_bayes(df))


def _bayes(df: pd.DataFrame) -> pd.DataFrame:
    df = _prep(df)
    city_rate = (df["_succ"].sum() + 1) / (df["_succ"].sum() + df["_fail"].sum() + 2)

    boro = df.groupby("borough")[["_succ", "_fail"]].sum()
    boro_rate = (boro["_succ"] + BOROUGH_PRIOR_STRENGTH * city_rate) / (boro["_succ"] + boro["_fail"] + BOROUGH_PRIOR_STRENGTH)
    df["_boro_rate"] = df["borough"].map(boro_rate)

    own = df.groupby("owner")[["_succ", "_fail"]].sum()
    own_prior = df.groupby("owner")["_boro_rate"].mean()
    own_rate = (own["_succ"] + BOROUGH_PRIOR_STRENGTH * own_prior) / (own["_succ"] + own["_fail"] + BOROUGH_PRIOR_STRENGTH)
    df["_owner_rate"] = df["owner"].map(own_rate)
    df["_owner_flags"] = df["owner"].map(df.groupby("owner")["flagged_listings"].sum())
    df["_owner_buildings"] = df["owner"].map(df.groupby("owner").size())

    n = df["_succ"] + df["_fail"]
    df["friendliness"] = ((df["_succ"] + OWNER_PRIOR_STRENGTH * df["_owner_rate"]) / (n + OWNER_PRIOR_STRENGTH)).round(3)
    # How much of the score comes from this building's own history vs. its owner's.
    df["evidence_strength"] = (n / (n + OWNER_PRIOR_STRENGTH)).round(2)
    return df


def fit_supervised(df: pd.DataFrame, label_col: str = "accepted_voucher"):
    """Logistic regression when outcome labels exist. Returns (model, cv_auc)."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    df = _bayes(df)                     # adds owner-level features
    X = _supervised_X(df)
    y = df[label_col].astype(int)
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced"))
    auc = cross_val_score(model, X, y, cv=5, scoring="roc_auc").mean()
    model.fit(X, y)
    return model, float(auc)


def score_supervised(model, df: pd.DataFrame) -> pd.DataFrame:
    df = _bayes(df)
    df["friendliness"] = model.predict_proba(_supervised_X(df))[:, 1].round(3)
    return _finish(df)


def _supervised_X(df: pd.DataFrame) -> np.ndarray:
    cols = FEATURES + ["_owner_rate", "_owner_flags", "_owner_buildings"]
    X = df[cols].to_numpy(dtype=float)
    return np.log1p(np.clip(X, 0, None))


def _finish(df: pd.DataFrame) -> pd.DataFrame:
    units = df["units"].clip(lower=1)
    df["habitability_warning"] = (df["class_c_violations"] >= 3) | (df["open_violations"] / units > 1.5)
    df["repeat_offender_owner"] = (df["_owner_flags"] >= 3) & (df["_owner_buildings"] >= 2)
    df["tier"] = pd.cut(df["friendliness"], [-0.01, 0.35, 0.65, 1.01], labels=["avoid", "unknown", "friendly"]).astype(str)
    df["reasons"] = df.apply(_reasons, axis=1)
    keep = [c for c in df.columns if not c.startswith("_")]
    return df[keep].sort_values("friendliness", ascending=False).reset_index(drop=True)


def _reasons(row) -> list:
    out = []
    if row["hra_placements_3yr"]:
        out.append(f"{int(row['hra_placements_3yr'])} HRA voucher placements in the last 3 years")
    if row["flagged_listings"]:
        out.append(f"{int(row['flagged_listings'])} listings flagged for source-of-income discrimination")
    if row["chr_complaints"]:
        out.append(f"{int(row['chr_complaints'])} prior CHR complaints")
    if row["_owner_buildings"] > 1:
        out.append(f"Owner '{row['owner']}' controls {int(row['_owner_buildings'])} buildings in this data; "
                   f"portfolio acceptance rate ~{row['_owner_rate']:.0%}")
    if row["repeat_offender_owner"]:
        out.append(f"Repeat offender: {int(row['_owner_flags'])} flagged listings across this owner's buildings")
    if row["habitability_warning"]:
        out.append(f"Habitability warning: {int(row['class_c_violations'])} Class C (immediately hazardous) HPD violations")
    if row["evidence_strength"] < 0.3:
        out.append("Little direct history for this building; score mostly reflects owner/borough")
    return out


def score(df: pd.DataFrame, model=None) -> pd.DataFrame:
    return score_supervised(model, df) if model is not None else score_heuristic(df)


def make_mock(n_buildings: int = 240, seed: int = 7) -> pd.DataFrame:
    """Plausible fake HPD/HRA data so the demo runs before Person 1's pipeline lands.
    Includes a few multi-building owners (one bad actor under several LLC names
    would be the entity-resolution follow-up)."""
    rng = np.random.default_rng(seed)
    boros = {"Bronx": (40.845, -73.88), "Brooklyn": (40.66, -73.95), "Manhattan": (40.80, -73.95),
             "Queens": (40.72, -73.83), "Staten Island": (40.60, -74.12)}
    owner_types = ([("friendly", f"Community Housing Partners {i} LLC") for i in range(8)]
                   + [("hostile", f"Parkline Mgmt {i} LLC") for i in range(4)]
                   + [("mixed", f"{s} Realty LLC") for s in ["Atlas", "Borough", "Crown", "Delancey", "Empire",
                                                             "Fulton", "Grand", "Hudson", "Irving", "Jerome"]])
    rows = []
    for i in range(n_buildings):
        kind, owner = owner_types[rng.integers(len(owner_types))] if rng.random() < 0.7 else ("mixed", f"Single Owner {i} LLC")
        boro = rng.choice(list(boros), p=[0.3, 0.3, 0.15, 0.2, 0.05])
        lat, lon = boros[boro]
        units = int(rng.integers(6, 120))
        accept_p = {"friendly": 0.85, "hostile": 0.08, "mixed": 0.4}[kind]
        attempts = rng.poisson(units / 15)
        placements = rng.binomial(attempts, accept_p)
        flags = rng.binomial(max(1, attempts // 2), (1 - accept_p) * 0.6)
        rows.append({
            "bbl": f"{list(boros).index(boro) + 1}{rng.integers(10000, 99999)}{rng.integers(1, 200):04d}",
            "address": f"{rng.integers(1, 3000)} {rng.choice(['Grand Concourse', 'Fulton St', 'Broadway', 'Jamaica Ave', 'Flatbush Ave', 'Richmond Ave', 'Ocean Ave', 'Amsterdam Ave'])}",
            "borough": boro, "lat": lat + rng.normal(0, 0.03), "lon": lon + rng.normal(0, 0.03),
            "units": units, "owner": owner, "hra_placements_3yr": placements, "flagged_listings": flags,
            "clean_listings": int(rng.poisson(2)), "chr_complaints": int(rng.binomial(flags, 0.2)),
            "class_c_violations": int(rng.poisson(0.8 if kind != "hostile" else 1.5)),
            "open_violations": int(rng.poisson(units * 0.4)),
            "rent_stabilized_units": int(units * rng.random()),
            "accepted_voucher": int(rng.random() < accept_p),   # stand-in for a real outcome label
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = make_mock()
    out = score(df)
    cols = ["address", "borough", "owner", "friendliness", "tier", "habitability_warning", "repeat_offender_owner"]
    print(out[cols].head(8).to_string())
    print("...")
    print(out[cols].tail(5).to_string())
    model, auc = fit_supervised(df)
    print(f"\nsupervised mode, 5-fold CV AUC on mock labels: {auc:.3f}")
