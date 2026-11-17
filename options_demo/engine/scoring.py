import pandas as pd
from sklearn.ensemble import IsolationForest

from .constants import EMPTY_COLS, FEATURE_COLS
from .quality import add_quality_columns, add_reason_columns
from .utils import robust_apply, robust_params, robust_z_clip


def score_with_training_cache(
    current_df,
    train_df,
    contamination=0.08,
    min_train_rows=100,
    min_current_rows=20,
    n_estimators=300,
):
    if current_df is None or current_df.empty:
        return pd.DataFrame(columns=EMPTY_COLS)

    outputs = []

    for option_type, current_part in current_df.groupby("option_type"):
        current_part = current_part.copy()

        train_part = (
            train_df[train_df["option_type"].eq(option_type)].copy()
            if train_df is not None and not train_df.empty
            else pd.DataFrame()
        )

        if len(train_part) >= min_train_rows:
            for col in FEATURE_COLS:
                train_part[col] = pd.to_numeric(train_part[col], errors="coerce").fillna(0)
                current_part[col] = pd.to_numeric(current_part[col], errors="coerce").fillna(0)

            med, iqr = robust_params(train_part, FEATURE_COLS)
            x_train = robust_apply(train_part, FEATURE_COLS, med, iqr)
            x_current = robust_apply(current_part, FEATURE_COLS, med, iqr)

            model = IsolationForest(
                n_estimators=n_estimators,
                contamination=contamination,
                random_state=42,
            )

            model.fit(x_train)

            pred = model.predict(x_current)
            score = -model.score_samples(x_current)

            current_part["is_anomaly"] = pred == -1
            current_part["anomaly_score"] = score
            current_part["training_source"] = "ticker_cache"

            outputs.append(current_part)

        elif len(current_part) >= min_current_rows:
            x_current = robust_z_clip(current_part, FEATURE_COLS)

            model = IsolationForest(
                n_estimators=n_estimators,
                contamination=contamination,
                random_state=42,
            )

            pred = model.fit_predict(x_current)
            score = -model.score_samples(x_current)

            current_part["is_anomaly"] = pred == -1
            current_part["anomaly_score"] = score
            current_part["training_source"] = "current_snapshot_fallback"

            outputs.append(current_part)

        else:
            print(f"Skipping {option_type}s: only {len(current_part)} rows")
            continue

    if not outputs:
        return pd.DataFrame(columns=EMPTY_COLS)

    scored = pd.concat(outputs, ignore_index=True)
    scored = add_quality_columns(scored)
    scored = add_reason_columns(scored)

    return scored
