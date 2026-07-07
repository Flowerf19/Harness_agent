#!/usr/bin/env python3
"""calibrate_t2.py — P1 measurement for the T2 diary/retrieval plan.

Measures the REAL cosine distribution between labeled queries (query-side,
with Config.EMBEDDING_QUERY_PREFIX applied — the thing P0 fixed) and the
T2 summaries actually stored in Redis, then proposes values for:

  - T2_MIN_COSINE        (search gate — query vs doc)
  - T2_MERGE_MIN_COSINE  (P2 diary same-day merge gate — incoming summary
                          vs stored doc, passage vs passage)

Run MANUALLY on the host (outside the container), read-only against Redis:

    python3 scripts/calibrate_t2.py
    python3 scripts/calibrate_t2.py --embed-url http://localhost:11434/v1 \
        --redis-url redis://localhost:6379

It never writes to Redis (SCAN + HGETALL only) and never touches the
production trace file. Merge probes are embedded in-memory only.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

# Same load the real entrypoints do (twin/march7/__main__.py) — must happen
# BEFORE Config is imported, since settings reads os.getenv at import time.
load_dotenv(ROOT / ".env", override=True)

import redis.asyncio as aioredis  # noqa: E402

from twin.shared.config.settings import Config  # noqa: E402
from twin.shared.llm.embedding import OpenAIEmbeddingService  # noqa: E402
from twin.shared.llm.embedding.embedding_trace_logger import (  # noqa: E402
    cosine_similarity,
    token_overlap,
)
from twin.shared.memory.diary.codec import unpack_embedding  # noqa: E402
from twin.shared.memory.diary import TimelineSummaryStore  # noqa: E402

# --------------------------------------------------------------------------
# Labeled query set (built 2026-07-03 from data/embedding_trace.jsonl real
# queries + casual/pronoun variants + negatives). Scopes match the docs
# present in Redis at calibration time.
# --------------------------------------------------------------------------

PERSONA = "1487427038280421456"  # test persona "Hòa": food/hiking/lifestyle/pet/work
REAL = "726302130318868500"      # real user: habit/psychological/work

# (scope, query, expected_topics) — empty set = negative (nothing relevant).
QUERIES: list[tuple[str, str, set[str]]] = [
    # persona / food
    (PERSONA, "Bảy ơi cuối tuần này tui nên nấu món gì ngon?", {"food"}),
    (PERSONA, "tui mê ăn phở với bún chả lắm", {"food"}),
    (PERSONA, "món bún đậu mắm tôm ăn ở đâu ngon nhỉ", {"food"}),
    # persona / pet
    (PERSONA, "tui mới nhận nuôi một con mèo tên Mun, nó đen thui à", {"pet"}),
    (PERSONA, "con mèo nhà tui dạo này quậy lắm", {"pet"}),
    (PERSONA, "con Mun nó cứ leo trèo khắp nơi", {"pet"}),
    # persona / hiking
    (PERSONA, "cuối tuần tui hay đi leo núi ở Bà Đen cho khỏe", {"hiking"}),
    (PERSONA, "leo Tà Năng có cực không ta", {"hiking"}),
    # persona / work
    (PERSONA, "tui đang làm một dự án web bằng React với TypeScript, hơi khó", {"work"}),
    (PERSONA, "Bảy ơi tui đang debug cái project hoài không xong", {"work"}),
    (PERSONA, "cái app todo list của tui bị lỗi state hoài", {"work"}),
    (PERSONA, "ê mà cái con hàm bữa t với m fix ấy nó sao rồi nhỉ", {"work"}),
    # persona / lifestyle
    (PERSONA, "tối nay coi gì trên Netflix đây ta", {"lifestyle"}),
    (PERSONA, "gợi ý tui mấy bài nhạc indie Việt đi", {"lifestyle"}),
    (PERSONA, "dạo này tui nghiện nghe Ngọt với Chillies", {"lifestyle"}),
    # persona / negatives (no relevant doc in scope)
    (PERSONA, "Bảy ơi thời tiết hôm nay thế nào?", set()),
    (PERSONA, "mai nắng hay mưa thế m. cả Phú Thọ với luôn", set()),
    (PERSONA, "alo bé", set()),
    (PERSONA, "1 cộng 1 bằng mấy", set()),
    (PERSONA, "giá vàng hôm nay bao nhiêu", set()),
    (PERSONA, "trận chung kết tối qua tỉ số bao nhiêu", set()),
    # real user / psychological
    (REAL, "Bảy ơi an ủi tui mệt quá", {"psychological"}),
    (REAL, "tối nay tự nhiên thấy trống trải ghê", {"psychological"}),
    (REAL, "hic hoài", {"psychological"}),
    # real user / work (embedding eval)
    (REAL, "cái vụ embedding model tiếng Việt hôm bữa tới đâu rồi", {"work"}),
    (REAL, "e5-small với qwen3 cái nào ngon hơn cho tiếng Việt", {"work"}),
    # real user / habit
    (REAL, "sao tui cứ nhắn đi nhắn lại một câu vậy trời", {"habit", "psychological"}),
    # real user / negatives (food doc belongs to the OTHER scope)
    (REAL, "công thức nấu phở bò sao cho ngọt nước", set()),
    (REAL, "M search hộ t cái coi", set()),
]

# Merge probes: synthetic "incoming consolidation summary" texts (diary-entry
# style), embedded PASSAGE-side in-memory. same-topic pair = should merge on
# the same day; vs other topics = must never merge.
MERGE_PROBES: list[tuple[str, str, str]] = [
    (PERSONA, "food",
     "Hòa nấu bún bò Huế sáng nay, cay xé lưỡi, sả ớt chanh, thịt bò bắp với "
     "chả cua. Vẫn mê nấu món Việt như mọi khi."),
    (PERSONA, "pet",
     "Mèo Mun hôm nay leo lên mái nhà làm Hòa hết hồn, gọi mãi mới chịu "
     "xuống, xong nhảy vào đùi đòi ăn."),
    (PERSONA, "work",
     "Hòa vẫn vật lộn với bug state trong app todo React/TypeScript, nghi do "
     "Zustand store update mà component không re-render."),
    (PERSONA, "hiking",
     "Cuối tuần này Hòa tính đổi gió leo núi Chứa Chan thay vì Bà Đen, rủ "
     "thêm hai đứa bạn cùng đi."),
    (REAL, "psychological",
     "Đêm nay Hòa lại thấy cô đơn, nhắn liên tiếp mấy tin tâm sự, cần được "
     "lắng nghe hơn là lời khuyên."),
    (REAL, "work",
     "Hòa chốt dùng qwen3-embedding 0.6b thay cho e5-small cho semantic "
     "search tiếng Việt, reindex 1024 chiều đã chạy xong."),
]


def fmt(v: float) -> str:
    return f"{v:.3f}"


async def load_docs(r: aioredis.Redis, store: TimelineSummaryStore) -> list[dict]:
    docs = []
    async for key in r.scan_iter(match=f"{store.prefix}:*".encode(), count=200):
        h = await r.hgetall(key)
        if not h or b"embedding" not in h:
            continue
        docs.append({
            "key": key.decode(),
            "user_id": h[b"user_id"].decode(),
            "topic": h.get(b"topic", b"").decode(),
            "summary": h[b"summary"].decode(),
            "embedding": unpack_embedding(h[b"embedding"]),
        })
    docs.sort(key=lambda d: (d["user_id"], d["topic"]))
    return docs


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--embed-url", default="http://localhost:11434/v1",
                    help="Embedding API from the HOST (container uses host.docker.internal)")
    ap.add_argument("--redis-url", default="redis://localhost:6379")
    ap.add_argument("--limit", type=int, default=8, help="live search() limit")
    args = ap.parse_args()

    print("=" * 78)
    print("T2 calibration — query prefix under test:")
    print(f"  EMBEDDING_QUERY_PREFIX   = {Config.EMBEDDING_QUERY_PREFIX!r}")
    print(f"  EMBEDDING_PASSAGE_PREFIX = {Config.EMBEDDING_PASSAGE_PREFIX!r}")
    print(f"  model={Config.EMBEDDING_MODEL_NAME} dim={Config.EMBEDDING_VECTOR_SIZE}")
    print(f"  current T2_MIN_COSINE={Config.T2_MIN_COSINE} (gate DISABLED for this run)")
    print("=" * 78)

    # Gate off in-process so live search() shows everything it fused.
    Config.T2_MIN_COSINE = 0.0

    r = aioredis.Redis.from_url(args.redis_url, db=Config.TIMELINE_REDIS_DB,
                                password=Config.REDIS_PASSWORD, decode_responses=False)
    store = TimelineSummaryStore(r, embedding_dim=Config.EMBEDDING_VECTOR_SIZE)
    svc = OpenAIEmbeddingService(
        model_name=Config.EMBEDDING_MODEL_NAME,
        api_url=args.embed_url,
        api_key=Config.EMBEDDING_API_KEY or "ollama",
        expected_dim=Config.EMBEDDING_VECTOR_SIZE,
    )

    try:
        docs = await load_docs(r, store)
        print(f"\nT2 docs in Redis (read-only): {len(docs)}")
        for d in docs:
            print(f"  [{d['user_id']}|{d['topic']}] {d['summary'][:72]}")
        if not docs:
            print("No docs — nothing to calibrate against.")
            return

        by_scope: dict[str, list[dict]] = {}
        for d in docs:
            by_scope.setdefault(d["user_id"], []).append(d)

        # ---------------- SEARCH gate: query (prefixed) vs doc ----------------
        pos, irr, neg = [], [], []   # (cosine, label) buckets
        mismatches = 0
        print("\n" + "-" * 78)
        print("SEARCH calibration — cosine per (query, doc), matrix + live search()")
        print("-" * 78)
        for scope, query, expected in QUERIES:
            emb = await svc.get_embedding(Config.EMBEDDING_QUERY_PREFIX + query)
            if not emb:
                print(f"!! embed failed for {query!r}")
                continue
            scored = sorted(
                ((cosine_similarity(emb, d["embedding"]), d) for d in by_scope.get(scope, [])),
                key=lambda x: -x[0],
            )
            kind = "NEG" if not expected else "POS"
            top_line = ", ".join(
                f"{d['topic']}={fmt(c)}{'✓' if d['topic'] in expected else ''}"
                for c, d in scored[:4]
            )
            print(f"[{kind}] {query[:52]!r:<56} {top_line}")
            if expected:
                rel = [c for c, d in scored if d["topic"] in expected]
                oth = [c for c, d in scored if d["topic"] not in expected]
                if rel:
                    pos.append((max(rel), query))
                if oth:
                    irr.append((max(oth), query))
                to = token_overlap(query, scored[0][1]["summary"]) if scored else 0.0
                # live production path (hybrid RRF + fusion), gate disabled
                live = await store.search(scope, emb, limit=args.limit, query_text=query)
                live_top = live[0] if live else None
                live_topic = (live_top or {}).get("topic")
                matrix_topic = scored[0][1]["topic"] if scored else None
                if live_topic != matrix_topic:
                    mismatches += 1
                    print(f"      live search() top1={live_topic} != matrix top1={matrix_topic} "
                          f"(RRF/BM25 reorder — check if expected) tok_overlap={fmt(to)}")
            else:
                if scored:
                    neg.append((scored[0][0], query))

        # ---------------- MERGE gate: incoming summary vs docs ----------------
        same, cross = [], []
        print("\n" + "-" * 78)
        print("MERGE calibration — synthetic incoming summaries (passage-side, in-memory)")
        print("-" * 78)
        for scope, topic, text in MERGE_PROBES:
            emb = await svc.get_embedding(Config.EMBEDDING_PASSAGE_PREFIX + text)
            if not emb:
                print(f"!! embed failed for merge probe {topic}")
                continue
            for d in by_scope.get(scope, []):
                c = cosine_similarity(emb, d["embedding"])
                if d["topic"] == topic:
                    same.append((c, f"{topic}↔{topic}"))
                    print(f"[SAME ] {topic:<13} vs {d['topic']:<13} {fmt(c)}")
                else:
                    cross.append((c, f"{topic}↔{d['topic']}"))
        # stored doc↔doc, same scope, different topic (must never merge)
        for scope, ds in by_scope.items():
            for i in range(len(ds)):
                for j in range(i + 1, len(ds)):
                    if ds[i]["topic"] != ds[j]["topic"]:
                        c = cosine_similarity(ds[i]["embedding"], ds[j]["embedding"])
                        cross.append((c, f"{ds[i]['topic']}↔{ds[j]['topic']}"))
        cross.sort(key=lambda x: -x[0])
        print("[CROSS] top-5 highest cross-topic (must stay BELOW merge gate):")
        for c, label in cross[:5]:
            print(f"        {label:<30} {fmt(c)}")

        # ---------------- Summary & suggestions ----------------
        def dist(name: str, xs: list[tuple[float, str]]) -> None:
            if not xs:
                print(f"{name}: (empty)")
                return
            vs = sorted(v for v, _ in xs)
            lo, hi = xs[min(range(len(xs)), key=lambda i: xs[i][0])], xs[max(range(len(xs)), key=lambda i: xs[i][0])]
            print(f"{name}: n={len(vs)} min={fmt(vs[0])} p25={fmt(vs[len(vs)//4])} "
                  f"med={fmt(vs[len(vs)//2])} max={fmt(vs[-1])}")
            print(f"    min ← {lo[1][:60]!r}")
            print(f"    max ← {hi[1][:60]!r}")

        print("\n" + "=" * 78)
        print("DISTRIBUTIONS")
        dist("POS (query vs its relevant doc)      ", pos)
        dist("IRR (pos query vs best OTHER-topic)  ", irr)
        dist("NEG (negative query vs best doc)     ", neg)
        dist("SAME (merge probe vs same-topic doc) ", same)
        dist("CROSS (probe/doc vs other-topic doc) ", cross)

        noise_hi = max([v for v, _ in irr + neg], default=0.0)
        pos_lo = min([v for v, _ in pos], default=1.0)
        print(f"\nSEARCH gate: highest noise={fmt(noise_hi)}  lowest relevant={fmt(pos_lo)}"
              f"  {'SEPARATED' if pos_lo > noise_hi else '!! OVERLAP — pick by trade-off'}")
        print(f"  suggestion zone: ({fmt(noise_hi)}, {fmt(pos_lo)}) → "
              f"midpoint {fmt((noise_hi + pos_lo) / 2)}")
        cross_hi = max([v for v, _ in cross], default=0.0)
        same_lo = min([v for v, _ in same], default=1.0)
        print(f"MERGE gate: highest cross-topic={fmt(cross_hi)}  lowest same-topic={fmt(same_lo)}"
              f"  {'SEPARATED' if same_lo > cross_hi else '!! OVERLAP — bias HIGH (false merge is worse)'}")
        print(f"  suggestion zone: ({fmt(cross_hi)}, {fmt(same_lo)}) → "
              f"upper-third {fmt(cross_hi + (same_lo - cross_hi) * 2 / 3)}")
        if mismatches:
            print(f"\nNOTE: live search() top1 differed from matrix top1 on {mismatches} "
                  f"queries (RRF/BM25 fusion) — inspect above.")
    finally:
        await svc.close()
        await r.aclose()


if __name__ == "__main__":
    asyncio.run(main())
