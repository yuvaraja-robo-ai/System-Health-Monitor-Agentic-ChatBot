from app.db import duckdb as ldb


def summarize(since_s: int, limit: int = 40) -> list[dict]:
    return ldb.cluster_logs(since_s, limit=limit)


def histogram(window_s: int, bucket: str = "1m") -> list[dict]:
    return ldb.histogram(bucket, window_s)
