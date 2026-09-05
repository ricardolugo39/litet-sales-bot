"""Retire cross-month aggregates after exact month-aligned replacements arrive."""

from datetime import date, timedelta


def _month_end(value):
    next_month = (value.replace(day=28) + timedelta(days=4)).replace(day=1)
    return next_month - timedelta(days=1)


def retire_replaced_cross_month_reports(conn, imports_table, data_table):
    reports = conn.execute(
        f"""SELECT file_hash, period_start, period_end, source_file
            FROM {imports_table}
            WHERE substr(period_start,1,7) <> substr(period_end,1,7)"""
    ).fetchall()
    retired = []
    for file_hash, start_text, end_text, source_file in reports:
        start, end = date.fromisoformat(start_text), date.fromisoformat(end_text)
        segments = []
        cursor = start
        while cursor <= end:
            segment_end = min(_month_end(cursor), end)
            segments.append((cursor.isoformat(), segment_end.isoformat()))
            cursor = segment_end + timedelta(days=1)
        covered = all(conn.execute(
            f"""SELECT 1 FROM {imports_table}
                WHERE period_start=? AND period_end=? AND file_hash<>? LIMIT 1""",
            (segment_start, segment_end, file_hash),
        ).fetchone() for segment_start, segment_end in segments)
        if not covered:
            continue
        conn.execute(f"DELETE FROM {data_table} WHERE source_hash=?", (file_hash,))
        conn.execute(f"DELETE FROM {imports_table} WHERE file_hash=?", (file_hash,))
        retired.append(source_file)
    return retired
