"""
수집 결과 검증 모듈.
날짜 갭 감지, 소스별 분포 출력.
"""

from collections import Counter
from datetime import date, timedelta


def validate_fetch_results(papers: list[dict], days_back: int) -> dict:
    """
    수집된 논문의 날짜 분포 검증.
    날짜 갭(0개인 날짜) 감지 및 경고.
    소스별 수집 비율 출력.
    """
    today      = date.today()
    date_range = [today - timedelta(days=i) for i in range(days_back + 2)]

    # 날짜별 논문 수 집계
    date_counts: Counter = Counter()
    for p in papers:
        raw_date = p.get("date")
        if raw_date:
            day = str(raw_date)[:10]  # YYYY-MM-DD
            date_counts[day] += 1

    # 갭 감지
    gaps = []
    for d in date_range:
        ds = d.isoformat()
        if date_counts[ds] == 0:
            gaps.append(ds)

    # 소스별 분포
    source_counts: Counter = Counter(
        p.get("source", "unknown") for p in papers
    )

    # 출력
    print("[검증] 날짜별 분포:")
    for d in sorted(date_counts.keys(), reverse=True):
        bar   = "█" * min(date_counts[d], 30)
        count = date_counts[d]
        print(f"  {d}: {bar} {count}개")

    if gaps:
        print(f"\n[검증] ⚠️ 갭 감지 ({len(gaps)}일):")
        for g in gaps:
            print(f"  {g}: 수집 0개 (해당일 논문 없거나 누락)")
    else:
        print("\n[검증] ✅ 날짜 갭 없음")

    print("\n[검증] 소스별 수집:")
    for src, cnt in source_counts.most_common():
        pct = round(cnt / len(papers) * 100, 1) if papers else 0
        print(f"  {src}: {cnt}개 ({pct}%)")

    return {
        "total":         len(papers),
        "date_counts":   dict(date_counts),
        "gaps":          gaps,
        "has_gaps":      len(gaps) > 0,
        "source_counts": dict(source_counts),
    }
