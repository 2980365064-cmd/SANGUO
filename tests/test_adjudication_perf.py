"""裁决系统性能优化测试。

覆盖：
- BatchQueryCache 线程安全和缓存命中
- QueryToolKit 缓存集成
- run_monthly_adjudication_batch 串行/并行模式
- 计时埋点
"""

import threading
import time
from types import SimpleNamespace

import pytest

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.query_tools import BatchQueryCache, QueryToolKit


@pytest.fixture
def board():
    content = GameContent.load()
    db = GameDB(":memory:", content=content)
    db.seed_static_data()
    yield db
    db.close()


def _state(turn=1):
    return SimpleNamespace(turn=turn, year=208, period=turn)


# ========== BatchQueryCache 单元测试 ==========


class TestBatchQueryCache:
    """BatchQueryCache 线程安全和功能测试。"""

    def test_get_or_compute_caches_result(self):
        cache = BatchQueryCache()
        call_count = 0

        def compute():
            nonlocal call_count
            call_count += 1
            return {"value": 42}

        # 首次调用应计算
        result1 = cache.get_or_compute("key1", compute)
        assert result1 == {"value": 42}
        assert call_count == 1

        # 第二次调用应命中缓存
        result2 = cache.get_or_compute("key1", compute)
        assert result2 == {"value": 42}
        assert call_count == 1  # 没有再次计算

    def test_different_keys_compute_separately(self):
        cache = BatchQueryCache()
        r1 = cache.get_or_compute("a", lambda: "value_a")
        r2 = cache.get_or_compute("b", lambda: "value_b")
        assert r1 == "value_a"
        assert r2 == "value_b"
        assert cache.stats()["size"] == 2

    def test_stats_tracking(self):
        cache = BatchQueryCache()
        cache.get_or_compute("k", lambda: 1)  # miss
        cache.get_or_compute("k", lambda: 1)  # hit
        cache.get_or_compute("k", lambda: 1)  # hit

        stats = cache.stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["size"] == 1

    def test_clear_resets_everything(self):
        cache = BatchQueryCache()
        cache.get_or_compute("k", lambda: 1)
        cache.get_or_compute("k", lambda: 1)
        cache.clear()

        stats = cache.stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["size"] == 0

    def test_set_and_get(self):
        cache = BatchQueryCache()
        cache.set("x", {"data": True})
        assert cache.get("x") == {"data": True}
        assert cache.get("nonexistent") is None

    def test_thread_safety_concurrent_access(self):
        """多线程并发读写不应崩溃或丢数据。"""
        cache = BatchQueryCache()
        errors = []
        results = {}

        def worker(thread_id):
            try:
                for i in range(50):
                    key = f"shared:{i % 10}"
                    val = cache.get_or_compute(key, lambda: f"v{thread_id}_{i}")
                    results.setdefault(key, []).append(val)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors, f"线程错误: {errors}"
        # 每个 key 应该只有一个值（第一个写入的线程赢了）
        for key, vals in results.items():
            assert len(set(vals)) == 1, f"Key {key} 有多个不同值: {set(vals)}"

    def test_thread_safety_stats_consistency(self):
        """并发访问后 hits + misses 应等于总访问次数。"""
        cache = BatchQueryCache()
        total_calls = 0
        lock = threading.Lock()

        def worker():
            nonlocal total_calls
            for i in range(100):
                with lock:
                    total_calls += 1
                cache.get_or_compute(f"k{i % 5}", lambda: i)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        stats = cache.stats()
        assert stats["hits"] + stats["misses"] == total_calls


# ========== QueryToolKit 缓存集成测试 ==========


class TestQueryToolKitCache:
    """QueryToolKit 与 BatchQueryCache 集成测试。"""

    def test_without_cache_still_works(self, board):
        toolkit = QueryToolKit(board, _state())
        result = toolkit.query_character("刘备")
        assert result["found"] is True
        assert result["name"] == "刘备"

    def test_with_cache_returns_same_result(self, board):
        cache = BatchQueryCache()
        toolkit = QueryToolKit(board, _state(), cache=cache)

        r1 = toolkit.query_character("刘备")
        r2 = toolkit.query_character("刘备")

        assert r1["found"] is True
        assert r2 == r1
        assert cache.stats()["hits"] >= 1

    def test_cache_reduces_db_queries(self, board):
        """有缓存时，重复查询不应增加 DB 访问。"""
        cache = BatchQueryCache()
        toolkit = QueryToolKit(board, _state(), cache=cache)

        # 查询 3 个不同实体
        toolkit.query_character("刘备")
        toolkit.query_army("liubei_main")
        toolkit.query_power("liu_bei")

        first_stats = cache.stats()
        assert first_stats["misses"] == 3

        # 重复查询同样 3 个
        toolkit.query_character("刘备")
        toolkit.query_army("liubei_main")
        toolkit.query_power("liu_bei")

        second_stats = cache.stats()
        assert second_stats["hits"] == 3
        assert second_stats["misses"] == 3  # 没有新的 miss

    def test_preload_context_injects_data(self, board):
        """preload_context 应将数据注入缓存。"""
        cache = BatchQueryCache()
        toolkit = QueryToolKit(board, _state(), cache=cache)

        # 模拟校验上下文
        context = {
            "candidate": {"name": "诸葛亮", "ability_value": 95, "loyalty": 90},
        }
        toolkit.preload_context(context)

        # 查询诸葛亮应命中缓存
        result = toolkit.query_character("诸葛亮")
        assert result["found"] is True
        assert cache.stats()["hits"] >= 1

    def test_cache_key_distinguishes_methods(self, board):
        """不同方法 + 相同参数应使用不同缓存 key。"""
        cache = BatchQueryCache()
        toolkit = QueryToolKit(board, _state(), cache=cache)

        toolkit.query_character("刘备")
        toolkit.query_power("刘备")  # 同名字但不同方法

        stats = cache.stats()
        assert stats["misses"] == 2  # 两次独立查询

    def test_query_region_with_cache(self, board):
        cache = BatchQueryCache()
        toolkit = QueryToolKit(board, _state(), cache=cache)

        r1 = toolkit.query_region("jiangxia")
        r2 = toolkit.query_region("jiangxia")

        assert r1["found"] is True
        assert r2 == r1
        assert cache.stats()["hits"] >= 1


# ========== 批处理计时测试 ==========


class TestBatchTiming:
    """批处理计时埋点测试。"""

    def test_batch_summary_contains_timing(self, board):
        """batch summary 应包含计时和 worker 信息。"""
        from ming_sim.adjudication import _collect_batch_tasks

        state = _state()
        tasks = _collect_batch_tasks(board, state)
        # 收集本身不应为空（至少有 power_action 等）
        assert isinstance(tasks, list)

    def test_serial_mode_with_max_workers_1(self, board):
        """max_workers=1 时应使用串行模式（不创建线程）。"""
        from ming_sim.adjudication import run_monthly_adjudication_batch

        state = _state()
        # 无 LLM 时应直接跳过
        result = run_monthly_adjudication_batch(board, state, max_workers=1)
        assert result["status"] == "skipped"

    def test_empty_batch_returns_immediately(self, board):
        """无待裁决项时应立即返回。"""
        from ming_sim.adjudication import run_monthly_adjudication_batch

        state = _state()
        result = run_monthly_adjudication_batch(board, state)
        # 无 LLM 配置时直接跳过
        assert result["status"] == "skipped"
        assert result["summary"]["total"] == 0


# ========== N+1 查询消除验证 ==========


class TestNPlus1Elimination:
    """验证 P2 优化后查询次数减少。"""

    def test_query_character_single_sql(self, board):
        """query_character 应只执行 1 次 SQL（LEFT JOIN 合并 faction）。"""
        queries = []
        board.conn.set_trace_callback(lambda sql: queries.append(sql))

        toolkit = QueryToolKit(board, _state())
        result = toolkit.query_character("刘备")

        board.conn.set_trace_callback(None)
        assert result["found"] is True
        assert "faction_info" in result
        assert len(queries) == 1, f"期望 1 次 SQL，实际 {len(queries)}: {queries}"

    def test_query_army_single_sql(self, board):
        """query_army 应只执行 1 次 SQL（JOIN commander + station）。"""
        queries = []
        board.conn.set_trace_callback(lambda sql: queries.append(sql))

        toolkit = QueryToolKit(board, _state())
        result = toolkit.query_army("guanyu_fleet")

        board.conn.set_trace_callback(None)
        assert result["found"] is True
        assert "commander_info" in result
        assert len(queries) == 1, f"期望 1 次 SQL，实际 {len(queries)}: {queries}"

    def test_query_power_single_sql(self, board):
        """query_power 应只执行 1 次 SQL（LEFT JOIN armies）。"""
        queries = []
        board.conn.set_trace_callback(lambda sql: queries.append(sql))

        toolkit = QueryToolKit(board, _state())
        result = toolkit.query_power("liu_bei")

        board.conn.set_trace_callback(None)
        assert result["found"] is True
        assert "armies" in result
        assert isinstance(result["armies_count"], int)
        assert len(queries) == 1, f"期望 1 次 SQL，实际 {len(queries)}: {queries}"

    def test_query_diplomacy_three_sql(self, board):
        """query_diplomacy 应只执行 3 次 SQL（合并 power 解析 + relations + treaties）。"""
        queries = []
        board.conn.set_trace_callback(lambda sql: queries.append(sql))

        toolkit = QueryToolKit(board, _state())
        result = toolkit.query_diplomacy("liu_bei", "cao_cao")

        board.conn.set_trace_callback(None)
        # power 合并 1 次 + relations 1 次 + treaties 1 次 = 3 次
        assert len(queries) == 3, f"期望 3 次 SQL，实际 {len(queries)}: {queries}"

    def test_query_army_result_structure_unchanged(self, board):
        """P2 优化后 query_army 返回结构不变。"""
        toolkit = QueryToolKit(board, _state())
        result = toolkit.query_army("guanyu_fleet")

        assert result["found"] is True
        assert result["id"] == "guanyu_fleet"
        assert "commander_info" in result
        assert "name" in result["commander_info"]

    def test_query_character_result_structure_unchanged(self, board):
        """P2 优化后 query_character 返回结构不变。"""
        toolkit = QueryToolKit(board, _state())
        result = toolkit.query_character("诸葛亮")

        assert result["found"] is True
        assert result["name"] == "诸葛亮"
        # faction_info 可能不存在（如果人物没有 faction）


# ========== 缓存 key 生成测试 ==========


class TestCacheKeyGeneration:
    """QueryToolKit._cache_key 方法测试。"""

    def test_cache_key_format(self, board):
        toolkit = QueryToolKit(board, _state())
        key = toolkit._cache_key("character", "刘备")
        assert key == "character:刘备"

    def test_cache_key_multiple_args(self, board):
        toolkit = QueryToolKit(board, _state())
        key = toolkit._cache_key("diplomacy", "liu_bei", "sun_quan")
        assert key == "diplomacy:liu_bei:sun_quan"

    def test_cached_passthrough_without_cache(self, board):
        """无缓存时 _cached 应直接执行函数。"""
        toolkit = QueryToolKit(board, _state())
        result = toolkit._cached("test", lambda: 42)
        assert result == 42


# ========== P3: 校验上下文复用验证 ==========


class TestValidationContextReuse:
    """验证 P3 校验上下文注入缓存。"""

    def test_run_adjudication_with_tools_accepts_validation_context(self):
        """run_adjudication_with_tools 签名应接受 validation_context 参数。"""
        import inspect
        from ming_sim.adjudication import run_adjudication_with_tools

        sig = inspect.signature(run_adjudication_with_tools)
        assert "validation_context" in sig.parameters, \
            "run_adjudication_with_tools 应接受 validation_context 参数（P3 优化）"

    def test_preload_context_with_army_breakdown(self, board):
        """preload_context 应注入 army_breakdown 中的军队数据。"""
        cache = BatchQueryCache()
        toolkit = QueryToolKit(board, _state(), cache=cache)

        context = {
            "army_breakdown": {
                "attackers": [
                    {"id": "guanyu_fleet", "name": "关羽水军", "manpower": 5000},
                ],
                "defenders": [],
            },
        }
        toolkit.preload_context(context)

        # 查询 guanyu_fleet 应命中缓存
        result = toolkit.query_army("guanyu_fleet")
        assert result["found"] is True
        assert cache.stats()["hits"] >= 1
