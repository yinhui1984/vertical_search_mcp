"""
User-Agent rotation pool.

This module manages a pool of User-Agents and provides rotation strategies
to avoid detection by anti-crawler systems.
"""

import random
from typing import List, Optional, Dict, Any
from core.logger import get_logger

logger = get_logger("vertical_search.user_agent_pool")


class UserAgentPool:
    """
    User-Agent rotation pool.

    This class manages a pool of User-Agents and provides different
    rotation strategies:
    - per_request: New User-Agent for each request
    - per_session: User-Agent changes when BrowserContext is recreated
    - per_platform: Different User-Agent for each platform

    Attributes:
        user_agents: List of User-Agent strings
        rotation_strategy: Current rotation strategy
        platform_agents: Dictionary mapping platform to User-Agent
        current_index: Current index for round-robin selection
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize User-Agent pool.

        Args:
            config: Anti-crawler configuration dictionary
        """
        user_agent_config = config.get("user_agent", {})
        self._enabled = user_agent_config.get("enabled", True)
        self._rotation_strategy = user_agent_config.get("rotation_strategy", "per_session")
        self._user_agents: List[str] = user_agent_config.get("pool", [])

        if not self._user_agents:
            # Default User-Agent if pool is empty
            self._user_agents = [
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ]

        self._platform_agents: Dict[str, str] = {}
        self._current_index = 0

        logger.info(
            f"User-Agent pool initialized with {len(self._user_agents)} agents, "
            f"strategy: {self._rotation_strategy}"
        )

    def get_user_agent(
        self, strategy: Optional[str] = None, platform: Optional[str] = None
    ) -> str:
        """
        Get User-Agent based on rotation strategy.

        Args:
            strategy: Override rotation strategy (optional)
            platform: Platform name (for per_platform strategy)

        Returns:
            User-Agent string
        """
        if not self._enabled:
            return self._user_agents[0]

        effective_strategy = strategy or self._rotation_strategy

        if effective_strategy == "per_platform":
            if platform:
                if platform not in self._platform_agents:
                    # Assign a User-Agent to this platform
                    agent = self._get_next_agent()
                    self._platform_agents[platform] = agent
                    logger.debug(f"Assigned User-Agent to platform '{platform}'")
                return self._platform_agents[platform]
            else:
                # Fall back to round-robin if no platform specified
                return self._get_next_agent()
        elif effective_strategy == "per_request":
            # Random selection for each request
            return random.choice(self._user_agents)
        elif effective_strategy == "per_session":
            # Round-robin for session-based rotation
            return self._get_next_agent()
        else:
            logger.warning(f"Unknown rotation strategy: {effective_strategy}, using default")
            return self._user_agents[0]

    def _get_next_agent(self) -> str:
        """
        Get next User-Agent using round-robin.

        Returns:
            User-Agent string
        """
        agent = self._user_agents[self._current_index]
        self._current_index = (self._current_index + 1) % len(self._user_agents)
        return agent

    def get_all_agents(self) -> List[str]:
        """
        Get all User-Agents in the pool.

        Returns:
            List of User-Agent strings
        """
        return self._user_agents.copy()

    def reset(self) -> None:
        """Reset rotation state (for testing)."""
        self._current_index = 0
        self._platform_agents.clear()

