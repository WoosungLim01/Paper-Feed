# PaperFeed

자동화된 학술 논문 발견 및 랭킹 시스템.

arXiv / Semantic Scholar / OpenAlex 세 소스에서 논문을 수집하고, TF-IDF 코사인 유사도로 주제 관련성을 스코어링한 뒤, 정적 사이트로 게시합니다.

## 구조

```
paper-discovery/
├── app/
│   ├── run.py              # CLI 진입점
│   ├── config.py           # 설정 파일 읽기 + 환경변수
│   ├── fetcher.py          # arXiv / Semantic Scholar / OpenAlex 크롤러
│   ├── deduplicator.py     # ID 우선순위 기반 중복 제거
│   ├── scorer.py           # TF-IDF 코사인 유사도 스코어링
│   ├── store.py            # ndjson 읽기/쓰기 헬퍼
│   └── publisher.py        # 정적 사이트 데이터 배포
├── data/
│   ├── survey_config.json  # 주제, 질문, 기간, 임계값 설정
│   ├── papers.ndjson       # 수락된 논문 (append-only)
│   ├── rejects.ndjson      # 거절된 논문 + 이유
│   └── run_history.ndjson  # 실행별 메타데이터
├── site/
│   ├── index.html          # 정적 프론트엔드 (서버 불필요)
│   ├── app.js              # React 클라이언트 로직
│   ├── styles.css          # 커스텀 스타일
│   └── data/               # 프론트엔드용 JSON 데이터
└── requirements.txt
```

## 설치

```bash
pip install -r requirements.txt
```

## 사용법

```bash
# 기본 실행 (data/survey_config.json 사용)
python -m app.run

# 주제 일시 override
python -m app.run --topic "robotics"

# 기간 override (14일치 논문 수집)
python -m app.run --days-back 14

# 파일 쓰기 없이 테스트
python -m app.run --dry-run
```

## 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DATA_DIR` | `data` | 데이터 디렉토리 |
| `SITE_DIR` | `site` | 사이트 디렉토리 |
| `DAYS_BACK` | `7` | 며칠치 논문을 수집할지 |
| `MAX_PER_SOURCE` | `50` | 소스별 쿼리당 최대 결과 수 |
| `REQUEST_TIMEOUT` | `15` | HTTP 요청 타임아웃 (초) |

## 사이트 열기

```bash
cd site && python -m http.server 8080
# 브라우저에서 http://localhost:8080 접속
```

## 파이프라인 설명

1. **수집 (Fetch)** — arXiv XML API, Semantic Scholar Graph API, OpenAlex REST API에서 병렬 수집
2. **중복 제거 (Dedup)** — DOI > arXiv ID > OpenAlex ID > S2 ID > 제목 지문 해시 우선순위로 중복 병합
3. **스코어링 (Score)** — TF-IDF (1~2-gram, max 8000 features) + 코사인 유사도, query_text = topic + questions + context + hints
4. **필터링 (Filter)** — min_relevance_score 미달, 기간 외, 메타데이터 누락 → rejects
5. **게시 (Publish)** — ndjson append-only 저장 + site/data/ 미러링

## 참고 프로젝트

- [arxiv-sanity](https://github.com/karpathy/arxiv-sanity-preserver) by Karpathy
- [Dynamic-LR baseline.md](https://github.com/SouravPanda11/Dynamic-LR)
- Scholar Inbox (arXiv:2504.08385)
