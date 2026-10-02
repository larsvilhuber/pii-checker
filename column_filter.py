# column_filter.py
# Determines whether a dataset column is a candidate for PII checking.
#
# Logic:
#   - Missing columns are skipped
#   - Columns whose name/label matches a force-include pattern (age, birth, ethnicity,
#     religion, disability, etc. — see _FORCE_INCLUDE_PATTERNS) or looks like a platform
#     participant ID (Prolific/MTurk/workerid — see is_platform_id_candidate) are always
#     checked, regardless of dtype or value range
#   - Boolean columns are otherwise skipped (never PII)
#   - Datetime columns are always checked (could be birthdays etc.)
#   - Numeric columns are checked if:
#       - large integers (abs value >= 1000 (i.e. have at least 4 digits), no real decimals)
#   - String columns are checked if max length >= 4
#        - exclude clearly categorical data  - each unique value has at least 10 observations AND data have maximum of 20 unique values AND n_unique/n_observations <0.1
#   - All other types are normalized to object and treated as strings
#
# GPS coordinates are detected separately, per dataframe, by find_gps_candidates (they need
# the neighbouring columns, which is_candidate_column never sees):
#   - missing-value codes in GPS_SENTINELS (+-97, +-98, +-99, +-999, +-9999) are treated as missing,
#     and so are rows where both columns of a pair are 0 (null island)
#   - a column passes the pre-check if numeric, abs value <= 180 and >= 3 decimal places
#   - it is paired with every neighbour within GPS_NEIGHBOUR_WINDOW positions that also passes
#   - a pair is rejected if > GPS_MAX_ONE_SIDED of rows have only one of the two values
#   - both orientations are tried (lat=a/lon=b and lat=b/lon=a, wherever |lat| <= 90) on a
#     sample of up to GPS_SAMPLE_SIZE rows; a point counts as on land if it, or any point
#     GPS_LAND_BUFFER degrees around it, is on land (catches coastal cities); points south of
#     GPS_MIN_LAND_LAT (Antarctica) never count as land
#   - the column is a GPS candidate if at least one of its pairs has >= GPS_LAND_THRESHOLD on land
#   Pre-check columns that pair with nothing fall through to is_candidate_column, where small
#   numeric values are skipped.

import re
import numpy as np
import pandas as pd
from pii_patterns import is_platform_id_candidate

# GPS pair-detection settings — see find_gps_candidates
GPS_NEIGHBOUR_WINDOW = 2
GPS_MIN_DECIMALS = 3
GPS_SENTINELS = [-97, 97, -98, 98, -99, 99, -999, 999, -9999, 9999]
GPS_MIN_LAND_LAT = -60  # Antarctic Treaty boundary — land south of it doesn't count (no residents)
GPS_MAX_ONE_SIDED = 0.10
GPS_SAMPLE_SIZE = 2000
GPS_LAND_THRESHOLD = 0.90
GPS_LAND_BUFFER = 0.01  # degrees, ~1 km

# Column names/labels matching these patterns are always checked regardless of data type or value range.
# Covers quasi-identifiers and sensitive categories that numeric/categorical filters would otherwise skip.
# Includes English and Spanish variants. Stubs are intentional to allow for variants like disab > disability,disabled...
# 'age' uses negative lookbehinds to exclude words where 'age' is a suffix unrelated to the demographic
# (average, percentage, storage, message, image, stage, coverage, language, wage). More can be added as needed.
_FORCE_INCLUDE_PATTERNS = re.compile(
    r'(?<!aver)(?<!percent)(?<!stor)(?<!mess)(?<!im)(?<!st)(?<!cover)(?<!langu)(?<!w)age'
    r'|birth|bday|born|dob|yob|mob'
    r'|edad|nacimiento|nacido|fdn'
    r'|ethn|race|relig|faith|disab'
    r'|etnia|etni|raza|discap',
    re.IGNORECASE
)


def _max_decimals(non_null: pd.Series) -> int:
    """Largest number of significant decimal places among the values."""
    return non_null.apply(
        lambda x: len(str(x).split('.')[-1].rstrip('0')) if '.' in str(x) else 0
    ).max()


def _drop_gps_sentinels(series: pd.Series) -> pd.Series:
    """Float copy of the series with GPS_SENTINELS set to NaN."""
    values = series.astype('float64')
    return values.where(~values.isin(GPS_SENTINELS))


def _passes_gps_precheck(series: pd.Series) -> bool:
    """Within +-180 and with enough decimals to be a coordinate."""
    non_null = series.dropna()
    if non_null.empty:
        return False
    return non_null.abs().max() <= 180 and _max_decimals(non_null) >= GPS_MIN_DECIMALS


def _land_share(lat: np.ndarray, lon: np.ndarray) -> float:
    """
    Share of points on land, counting a point as land if any point GPS_LAND_BUFFER around it is.
    Points south of GPS_MIN_LAND_LAT (Antarctica) never count as land.
    """
    from global_land_mask import globe  # lazy: loads a ~1 GB mask into memory

    on_land = globe.is_land(lat, lon)
    missed = ~on_land
    if missed.any():
        m_lat, m_lon = lat[missed], lon[missed]
        near_land = np.zeros(len(m_lat), dtype=bool)
        for d_lat in (-GPS_LAND_BUFFER, 0, GPS_LAND_BUFFER):
            for d_lon in (-GPS_LAND_BUFFER, 0, GPS_LAND_BUFFER):
                if d_lat == 0 and d_lon == 0:
                    continue
                near_land |= globe.is_land(np.clip(m_lat + d_lat, -90, 90),
                                           np.clip(m_lon + d_lon, -180, 180))
        on_land[missed] = near_land
    on_land &= lat >= GPS_MIN_LAND_LAT
    return float(on_land.mean())


def _test_gps_pair(a: pd.Series, b: pd.Series) -> dict | None:
    """
    Tests whether two columns look like a lat/lon pair on land.
    Returns {'share', 'n', 'a_is_lat'} for the best orientation, or None if the pair fails.
    """
    # (0, 0) rows are a missing-value code (null island), not a point
    null_island = (a == 0) & (b == 0)
    a, b = a.where(~null_island), b.where(~null_island)

    a_present, b_present = a.notna(), b.notna()
    n_either = (a_present | b_present).sum()
    n_both = (a_present & b_present).sum()

    # real coordinates come in complete pairs — reject if many rows have only one of them
    if n_both == 0 or (n_either - n_both) / n_either > GPS_MAX_ONE_SIDED:
        return None

    both = pd.DataFrame({'a': a, 'b': b})[a_present & b_present]
    if len(both) > GPS_SAMPLE_SIZE:
        both = both.sample(GPS_SAMPLE_SIZE, random_state=0)
    a_vals = both['a'].to_numpy(dtype=float)
    b_vals = both['b'].to_numpy(dtype=float)

    best = None
    for a_is_lat in (True, False):
        lat, lon = (a_vals, b_vals) if a_is_lat else (b_vals, a_vals)
        if np.abs(lat).max() > 90:
            continue
        share = _land_share(lat, lon)
        if best is None or share > best['share']:
            best = {'share': share, 'n': len(both), 'a_is_lat': a_is_lat}

    if best is None or best['share'] < GPS_LAND_THRESHOLD:
        return None
    return best


def find_gps_candidates(df: pd.DataFrame) -> dict:
    """
    Finds columns that pair with a neighbouring column as plausible lat/lon coordinates on land.
    Returns {col_name: filter_reason}. Every column with at least one valid pair is included,
    so each column of a pair is listed (and later checked) individually.
    """
    columns = list(df.columns)
    cleaned = {}
    for i in range(len(columns)):
        series = df.iloc[:, i]
        if series.dtype == bool or not pd.api.types.is_numeric_dtype(series):
            continue
        series = _drop_gps_sentinels(series)
        if _passes_gps_precheck(series):
            cleaned[i] = series
    prechecked = set(cleaned)

    pair_results = {}
    candidates = {}
    for i in sorted(prechecked):
        best = None
        for j in range(i - GPS_NEIGHBOUR_WINDOW, i + GPS_NEIGHBOUR_WINDOW + 1):
            if j == i or j not in prechecked:
                continue
            key = (min(i, j), max(i, j))
            if key not in pair_results:
                pair_results[key] = _test_gps_pair(cleaned[key[0]], cleaned[key[1]])
            result = pair_results[key]
            if result is None:
                continue
            if best is None or result['share'] > best[1]['share']:
                best = (j, result)

        if best is not None:
            j, result = best
            i_is_lat = result['a_is_lat'] == (i < j)
            role = 'latitude' if i_is_lat else 'longitude'
            partner_role = 'longitude' if i_is_lat else 'latitude'
            candidates[columns[i]] = (
                f"possible GPS {role} — pairs with '{columns[j]}' as {partner_role} "
                f"({result['share']:.0%} of {result['n']} points on land)"
            )
    return candidates


def is_candidate_column(series: pd.Series, label: str = None) -> tuple[bool, str]:
    """
    Determines if a dataset column should be sent to LLM for PII checking.
    Returns (is_candidate, reason)
    """
    try:
        n_nonmissing = series.notna().sum()
    except TypeError:
        n_nonmissing = series.apply(lambda x: x is not None).sum()

    # --- Skip if all values are missing ---
    if n_nonmissing == 0:
        return False, "all values missing"

    # --- Force include by name/label --- age, birth, DOB etc. are always checked - patterns defined above in _FORCE_INCLUDE_PATTERNS
    # even if numeric filters (or the boolean skip below) would normally skip them (e.g. small values like age 0-100)
    col_text = f"{series.name or ''} {label or ''}"
    if _FORCE_INCLUDE_PATTERNS.search(col_text):
        return True, f"name/label matches must include pattern"

    # --- Force include platform participant IDs --- workerid / prolific / mturk columns
    if is_platform_id_candidate(str(series.name or ''), str(label) if label is not None else ''):
        return True, "name/label suggests platform participant ID (Prolific/MTurk)"

    # --- Bool --- considered as never PII (unless name/label matched a force-include pattern above)
    if series.dtype == bool:
        return False, "boolean dtype"

    # --- Datetime --- always check
    if pd.api.types.is_datetime64_any_dtype(series):
        return True, "datetime dtype"

    # normalize non-numeric, non-datetime to object
    if not pd.api.types.is_numeric_dtype(series):
        series = series.astype(object)

    # --- Numeric ---
    if pd.api.types.is_numeric_dtype(series):
        non_null = series.dropna()
        max_val = non_null.abs().max()

        has_real_decimals = (non_null % 1 != 0).any()

        # GPS coordinates are handled by find_gps_candidates (needs neighbouring columns)

        # 1) Small values — likert, counts etc.
        if max_val < 1000:
            return False, f"numeric with small values (max={max_val})"

        # 2) Has real decimals — standardized scores, indices etc. unlikely to be PII
        if has_real_decimals:
            return False, f"large float, unlikely to be ID (max={max_val})"

        # 3) Large integers — phone numbers, IDs, zip codes
        return True, f"large integer, possible ID or phone (max={max_val})"

    # --- String / object ---
    if series.dtype == object:
        non_null = series.dropna().astype(str)
        max_len = non_null.str.len().max()

        if max_len < 4:
            return False, f"strings too short (max length={max_len})"

        # skip if clearly categorical — every unique value appears at least 10 times + number of unique values 20 or less + n unique / n observations <0.1
        n_unique = non_null.nunique()
        min_count = non_null.value_counts().min()
        cardinality = n_unique / len(non_null)
        if n_unique <= 20 and min_count >= 10 and cardinality < 0.1:
            return False, f"likely categorical ({n_unique} unique values, min count={min_count})"

        return True, f"string candidate (max length={max_len})"

    # --- Unknown dtype --- check to be safe
    return True, f"unknown dtype ({series.dtype}), checking to be safe"