"""
Test Semantic Score với 50-60 câu tiếng Việt đa dạng
Mục tiêu: Xác định threshold phù hợp cho Qwen3-Embedding-0.6B
"""

import asyncio

from dotenv import load_dotenv

from src.services.llm.embedding_service import LocalEmbeddingService
from src.services.memories.activate_memory.evaluation.rule_engine import RuleEngine
from src.services.memories.activate_memory.evaluation.sematic_enegine import (
    SemanticEngine,
)
from src.services.memories.activate_memory.models import MessageCategory

# Danh sách 60 câu test được phân loại thủ công
TEST_CASES = [
    # === NHÓM 1: CÂU FACT - PHẢI ĐƯỢC NHẬN DIỆN (20 câu) ===
    ("Tôi tên là Nam, năm nay 25 tuổi.", MessageCategory.FACT),
    ("Mình là Minh, sinh năm 1998.", MessageCategory.FACT),
    ("Tớ được gọi là Bình, quê ở Hà Nội.", MessageCategory.FACT),
    ("Anh là dân lập trình, làm ở công ty FPT.", MessageCategory.FACT),
    ("Em đang học trường ĐH Bách Khoa, ngành CNTT.", MessageCategory.FACT),
    ("Tôi rất thích ăn phở bò.", MessageCategory.FACT),
    ("Mình cực kỳ ghét đồ ăn cay.", MessageCategory.FACT),
    ("Tớ đam mê nhiếp ảnh.", MessageCategory.FACT),
    ("Tôi dị ứng với hải sản.", MessageCategory.FACT),
    ("Mình không ăn được hành tây.", MessageCategory.FACT),
    ("Tôi đang sống ở TP.HCM.", MessageCategory.FACT),
    ("Quê mình ở Nghệ An.", MessageCategory.FACT),
    ("Tớ vừa mới tốt nghiệp đại học.", MessageCategory.FACT),
    ("Tôi đã có người yêu rồi.", MessageCategory.FACT),
    ("Mình đang độc thân.", MessageCategory.FACT),
    ("Tôi có nuôi một chú chó tên Lucky.", MessageCategory.FACT),
    ("Bố mẹ tớ đều là giáo viên.", MessageCategory.FACT),
    ("Tớ dự định tháng sau đi Đà Lạt.", MessageCategory.FACT),
    ("Mục tiêu của tôi là trở thành senior developer.", MessageCategory.FACT),
    ("Tôi chuẩn bị đi du lịch ở Nhật Bản.", MessageCategory.FACT),
    # === NHÓM 2: CÂU GENERAL - KHÔNG PHẢI FACT (20 câu) ===
    ("Hôm nay trời đẹp quá.", MessageCategory.GENERAL),
    ("Bạn có biết gì về AI không?", MessageCategory.GENERAL),
    ("Làm ơn giúp tôi với.", MessageCategory.GENERAL),
    ("Cảm ơn bạn rất nhiều.", MessageCategory.GENERAL),
    ("Chào buổi sáng!", MessageCategory.GENERAL),
    ("Hẹn gặp lại sau nhé.", MessageCategory.GENERAL),
    ("Tôi đang làm bài tập về nhà.", MessageCategory.GENERAL),  # Hành động tạm thời
    (
        "Bạn tôi là bác sĩ.",
        MessageCategory.GENERAL,
    ),  # Nói về người khác, không phải bản thân
    ("Con mèo rất dễ thương.", MessageCategory.GENERAL),  # Nói về con vật chung
    ("Hôm nay tôi đi làm.", MessageCategory.GENERAL),  # Hành động nhất thời
    ("Mọi người đều nói quán này ngon.", MessageCategory.GENERAL),
    ("Tôi là người đã hỏi câu này.", MessageCategory.GENERAL),  # Vai trò tạm thời
    ("Bạn có thể giải thích giúp tôi không?", MessageCategory.GENERAL),
    ("Tôi nghĩ là nên làm thế này.", MessageCategory.GENERAL),
    ("Điều đó thật thú vị!", MessageCategory.GENERAL),
    ("Tôi đồng ý với bạn.", MessageCategory.GENERAL),
    ("Đây là một câu hỏi hay.", MessageCategory.GENERAL),
    ("Tôi không hiểu ý bạn.", MessageCategory.GENERAL),
    ("Có thể tôi sẽ thử.", MessageCategory.GENERAL),
    ("Để tôi suy nghĩ thêm.", MessageCategory.GENERAL),
    # === NHÓM 3: CÂU BIÊN (EDGE CASES) - KHÓ PHÂN LOẠI (20 câu) ===
    (
        "Năm 2001 mẹ tớ sinh ra tớ ở Hà Nội.",
        MessageCategory.FACT,
    ),  # Nói lóng nhưng là fact
    ("Mọi người hay gọi tớ là 'trùm code'.", MessageCategory.FACT),  # Biệt danh
    ("Tớ là người mê cà phê.", MessageCategory.FACT),  # Sở thích nhẹ
    ("Tôi không thích sự trễ hẹn.", MessageCategory.FACT),  # Ràng buộc
    ("Mình có thói quen dậy sớm.", MessageCategory.FACT),  # Thói quen
    ("Tôi là người khó tính về đồ ăn.", MessageCategory.FACT),  # Tính cách
    ("Sinh nhật tớ là ngày 15/3.", MessageCategory.FACT),  # Ngày sinh
    ("Tớ hay đi cafe ở Highlands.", MessageCategory.FACT),  # Sở thích
    ("Tôi thích đọc sách vào buổi tối.", MessageCategory.FACT),
    ("Mình là introvert.", MessageCategory.FACT),  # Tính cách
    (
        "Bạn tớ bảo tôi là người nhiệt tình.",
        MessageCategory.GENERAL,
    ),  # Nói về quan điểm
    ("Tôi đang nghĩ sẽ học guitar.", MessageCategory.GENERAL),  # Dự định chưa chắc chắn
    ("Hôm qua tôi ăn pizza.", MessageCategory.GENERAL),  # Hành động quá khứ
    ("Nghe nói quán đó ngon lắm.", MessageCategory.GENERAL),
    ("Tôi là người đã giúp anh ấy.", MessageCategory.GENERAL),  # Vai trò tạm thời
    (
        "Tớ định sẽ đi tàu thay vì máy bay.",
        MessageCategory.GENERAL,
    ),  # Kế hoạch chưa chắc chắn
    (
        "Con chó nhà tôi rất ồn ào.",
        MessageCategory.GENERAL,
    ),  # Nói về con vật, không phải sở hữu
    ("Bạn của tôi ở Huế.", MessageCategory.GENERAL),  # Nói về người khác
    ("Tôi là người hỏi đầu tiên.", MessageCategory.GENERAL),  # Vai trò tạm thời
    ("Ai đó nói là café ngon.", MessageCategory.GENERAL),  # Không xác định
]


async def test_semantic_engine():
    load_dotenv()

    print("=" * 60)
    print("TEST SEMANTIC ENGINE VÀ RULE ENGINE")
    print("=" * 60)

    # Khởi tạo embedding service
    print("\n⏳ Đang tải mô hình embedding...")
    embedding_service = LocalEmbeddingService()

    rule_engine = RuleEngine()
    semantic_engine = SemanticEngine(embedding_service)

    # Initialize embedding
    await semantic_engine.initialize()

    results = {
        "total": len(TEST_CASES),
        "rule_engine": {"correct": 0, "wrong": 0, "skipped": 0},
        "semantic_engine": {"correct": 0, "wrong": 0, "scores": []},
        "combined": {"correct": 0, "wrong": 0},
    }

    print("\n📊 CHI TIẾT TỪNG CÂU TEST:\n")

    for i, (sentence, expected) in enumerate(TEST_CASES, 1):
        # Rule Engine
        rule_result = rule_engine.evaluate(sentence)

        # Semantic Engine
        score, semantic_result = await semantic_engine.evaluate(sentence)

        # Combined logic: Rule ưu tiên (nếu matched FACT), nếu không thì dùng semantic
        if rule_result.matched and rule_result.category == MessageCategory.FACT:
            final_result = rule_result.category
        else:
            final_result = (
                semantic_result if semantic_result else MessageCategory.GENERAL
            )

        # Track results
        results["semantic_engine"]["scores"].append(
            {
                "sentence": sentence,
                "score": score,
                "expected": expected.name,
                "got": semantic_result.name if semantic_result else "None",
            }
        )

        # Count correct for Rule Engine (chỉ tính khi match FACT)
        if rule_result.matched and rule_result.category == MessageCategory.FACT:
            if rule_result.category == expected:
                results["rule_engine"]["correct"] += 1
            else:
                results["rule_engine"]["wrong"] += 1
        else:
            results["rule_engine"]["skipped"] += 1

        if semantic_result == expected:
            results["semantic_engine"]["correct"] += 1
        else:
            results["semantic_engine"]["wrong"] += 1

        if final_result == expected:
            results["combined"]["correct"] += 1
        else:
            results["combined"]["wrong"] += 1

        # Print details
        status = "✅" if final_result == expected else "❌"
        rule_str = rule_result.category.name if rule_result.matched else "—"
        print(
            f"{status} [{i:02d}] Score: {score:.4f} | Rule: {rule_str:8} | Semantic: {semantic_result.name if semantic_result else 'None':8} | Expected: {expected.name}"
        )
        print(f'      → "{sentence}"')
        print()

    # Summary
    print("=" * 60)
    print("📈 TỔNG KẾT:")
    print("=" * 60)
    print(f"{'Metric':<20} {'Correct':<10} {'Wrong':<10} {'Accuracy':<10}")
    print("-" * 60)
    rule_total = results["rule_engine"]["correct"] + results["rule_engine"]["wrong"]
    print(
        f"{'Rule Engine':<20} {results['rule_engine']['correct']:<10} {results['rule_engine']['wrong']:<10} {results['rule_engine']['correct'] / rule_total * 100 if rule_total > 0 else 0:.1f}%"
    )
    print(
        f"{'Semantic Engine':<20} {results['semantic_engine']['correct']:<10} {results['semantic_engine']['wrong']:<10} {results['semantic_engine']['correct'] / results['total'] * 100:.1f}%"
    )
    print(
        f"{'Combined':<20} {results['combined']['correct']:<10} {results['combined']['wrong']:<10} {results['combined']['correct'] / results['total'] * 100:.1f}%"
    )
    print(f"{'Rule Skipped':<20} {results['rule_engine']['skipped']:<10}")

    # Score distribution
    print("\n📊 PHÂN BỔ SCORE THEO LOẠI:")
    fact_scores = [
        s["score"]
        for s in results["semantic_engine"]["scores"]
        if s["expected"] == "FACT"
    ]
    general_scores = [
        s["score"]
        for s in results["semantic_engine"]["scores"]
        if s["expected"] == "GENERAL"
    ]

    if fact_scores:
        print(
            f"FACT scores: min={min(fact_scores):.4f}, max={max(fact_scores):.4f}, avg={sum(fact_scores) / len(fact_scores):.4f}"
        )
    if general_scores:
        print(
            f"GENERAL scores: min={min(general_scores):.4f}, max={max(general_scores):.4f}, avg={sum(general_scores) / len(general_scores):.4f}"
        )

    # Recommended threshold
    if fact_scores and general_scores:
        avg_fact = sum(fact_scores) / len(fact_scores)
        avg_general = sum(general_scores) / len(general_scores)
        recommended_threshold = (avg_fact + avg_general) / 2
        print(f"\n🎯 RECOMMENDED THRESHOLD: {recommended_threshold:.4f}")
        print(f"   - Avg FACT score: {avg_fact:.4f}")
        print(f"   - Avg GENERAL score: {avg_general:.4f}")
        print(f"   - Gap: {avg_fact - avg_general:.4f}")

    await semantic_engine.close()


if __name__ == "__main__":
    asyncio.run(test_semantic_engine())
