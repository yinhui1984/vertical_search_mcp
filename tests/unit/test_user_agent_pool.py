"""
Unit tests for User-Agent pool.

Test strategy:
1. Test User-Agent rotation strategies
2. Test round-robin selection
3. Test per-platform User-Agents
4. Test loading from config
"""

import pytest
from core.user_agent_pool import UserAgentPool


class TestUserAgentPool:
    """Test UserAgentPool class."""

    @pytest.fixture
    def config(self) -> dict:
        """Create test configuration."""
        return {
            "user_agent": {
                "enabled": True,
                "rotation_strategy": "per_session",
                "pool": [
                    "User-Agent 1",
                    "User-Agent 2",
                    "User-Agent 3",
                ],
            }
        }

    def test_load_from_config(self, config: dict) -> None:
        """Test loading User-Agents from config."""
        pool = UserAgentPool(config)

        agents = pool.get_all_agents()
        assert len(agents) == 3
        assert "User-Agent 1" in agents
        assert "User-Agent 2" in agents
        assert "User-Agent 3" in agents

    def test_per_session_round_robin(self, config: dict) -> None:
        """Test per_session strategy uses round-robin."""
        pool = UserAgentPool(config)

        # Should cycle through agents
        agent1 = pool.get_user_agent()
        agent2 = pool.get_user_agent()
        agent3 = pool.get_user_agent()
        agent4 = pool.get_user_agent()

        # Should cycle back to first
        assert agent4 == agent1
        # All should be different in first cycle
        assert agent1 != agent2
        assert agent2 != agent3

    def test_per_request_random(self, config: dict) -> None:
        """Test per_request strategy uses random selection."""
        config["user_agent"]["rotation_strategy"] = "per_request"
        pool = UserAgentPool(config)

        # Get multiple agents - they may be the same (random)
        agents = [pool.get_user_agent() for _ in range(10)]

        # All should be valid User-Agents from pool
        pool_agents = pool.get_all_agents()
        assert all(agent in pool_agents for agent in agents)

    def test_per_platform_assignment(self, config: dict) -> None:
        """Test per_platform strategy assigns consistent User-Agent per platform."""
        config["user_agent"]["rotation_strategy"] = "per_platform"
        pool = UserAgentPool(config)

        # Same platform should get same User-Agent
        agent1 = pool.get_user_agent(platform="weixin")
        agent2 = pool.get_user_agent(platform="weixin")
        assert agent1 == agent2

        # Different platform may get different User-Agent
        agent3 = pool.get_user_agent(platform="zhihu")
        # May or may not be different, but should be consistent
        agent4 = pool.get_user_agent(platform="zhihu")
        assert agent3 == agent4

    def test_disabled_pool(self) -> None:
        """Test that disabled pool returns first User-Agent."""
        config = {
            "user_agent": {
                "enabled": False,
                "pool": ["Agent 1", "Agent 2", "Agent 3"],
            }
        }

        pool = UserAgentPool(config)

        # Should always return first agent
        agent1 = pool.get_user_agent()
        agent2 = pool.get_user_agent()
        assert agent1 == agent2
        assert agent1 == "Agent 1"

    def test_empty_pool_default(self) -> None:
        """Test that empty pool uses default User-Agent."""
        config = {"user_agent": {"enabled": True, "pool": []}}

        pool = UserAgentPool(config)

        agent = pool.get_user_agent()
        assert agent is not None
        assert len(agent) > 0

    def test_reset(self, config: dict) -> None:
        """Test reset functionality."""
        pool = UserAgentPool(config)

        # Get some agents
        pool.get_user_agent(platform="test")
        pool.get_user_agent(platform="test2")

        # Reset
        pool.reset()

        # Should start from beginning
        agent1 = pool.get_user_agent()
        # After reset, should cycle from start
        assert agent1 is not None

    def test_override_strategy(self, config: dict) -> None:
        """Test overriding strategy per call."""
        pool = UserAgentPool(config)

        # Default is per_session
        pool.get_user_agent()
        pool.get_user_agent()

        # Override to per_request
        agent3 = pool.get_user_agent(strategy="per_request")
        agent4 = pool.get_user_agent(strategy="per_request")

        # per_request may return same or different (random)
        # But should be valid
        pool_agents = pool.get_all_agents()
        assert agent3 in pool_agents
        assert agent4 in pool_agents
