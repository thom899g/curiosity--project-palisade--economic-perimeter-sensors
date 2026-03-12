"""
Configuration management for Project Sentinel with environment validation.
All sensitive credentials are loaded from environment variables.
"""
import os
import json
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

class Network(Enum):
    ETHEREUM = "ethereum"
    POLYGON = "polygon"
    ARBITRUM = "arbitrum"
    BASE = "base"
    OPTIMISM = "optimism"

@dataclass
class RPCConfig:
    """Triple-redundant RPC configuration for each network"""
    primary: str
    secondary: str
    tertiary: str
    ws_primary: str
    ws_secondary: str
    current_index: int = 0
    
    def get_next_rpc(self) -> str:
        """Round-robin RPC selection for load balancing"""
        rpcs = [self.primary, self.secondary, self.tertiary]
        rpc = rpcs[self.current_index % len(rpcs)]
        self.current_index += 1
        return rpc
    
    def get_next_ws(self) -> str:
        """Round-robin WebSocket selection"""
        ws_rpcs = [self.ws_primary, self.ws_secondary]
        return ws_rpcs[self.current_index % len(ws_rpcs)]

@dataclass
class FirebaseConfig:
    """Firebase configuration with validation"""
    project_id: str
    service_account_key_path: str = "firebase-key.json"
    database_url: Optional[str] = None
    
    def validate(self) -> bool:
        """Validate Firebase configuration exists"""
        if not os.path.exists(self.service_account_key_path):
            raise FileNotFoundError(
                f"Firebase service account key not found at {self.service_account_key_path}. "
                "Please download from Firebase Console and place in project root."
            )
        return True

@dataclass
class SentinelConfig:
    """Main configuration for Sentinel system"""
    # Network configurations
    networks: Dict[Network, RPCConfig] = field(default_factory=dict)
    
    # Firebase
    firebase: Optional[FirebaseConfig] = None
    
    # Economic parameters
    max_tx_cost_usd: float = 5.0
    max_treasury_percentage: float = 0.001  # 0.1%
    min_profit_threshold_usd: float = 0.50
    
    # Gas thresholds (in gwei)
    gas_thresholds: Dict[Network, float] = field(default_factory=lambda: {
        Network.ETHEREUM: 15.0,
        Network.POLYGON: 50.0,
        Network.ARBITRUM: 0.1,
        Network.BASE: 0.1,
        Network.OPTIMISM: 0.1
    })
    
    # Cell configuration
    cell_id: str = "cell_alpha"
    max_parallel_executions: int = 3
    health_check_interval: int = 60  # seconds
    
    # Social monitoring
    discord_bot_token: Optional[str] = None
    twitter_enabled: bool = False
    
    def load_from_env(self) -> None:
        """Load configuration from environment variables"""
        self.cell_id = os.getenv("SENTINEL_CELL_ID", "cell_alpha")
        
        # Load RPC URLs from environment
        eth_rpc = os.getenv("ETH_RPC_URL", "")
        if eth_rpc:
            self.networks[Network.ETHEREUM] = RPCConfig(
                primary=os.getenv("ETH_RPC_PRIMARY", eth_rpc),
                secondary=os.getenv("ETH_RPC_SECONDARY", ""),
                tertiary=os.getenv("ETH_RPC_TERTIARY", ""),
                ws_primary=os.getenv("ETH_WS_PRIMARY", ""),
                ws_secondary=os.getenv("ETH_WS_SECONDARY", "")
            )
        
        # Initialize Firebase if config exists
        fb_project = os.getenv("FIREBASE_PROJECT_ID")
        if fb_project:
            self.firebase = FirebaseConfig(
                project_id=fb_project,
                service_account_key_path=os.getenv("FIREBASE_KEY_PATH", "firebase-key.json"),
                database_url=os.getenv("FIREBASE_DATABASE_URL")
            )
        
        # Social tokens
        self.discord_bot_token = os.getenv("DISCORD_BOT_TOKEN")
        self.twitter_enabled = os.getenv("TWITTER_ENABLED", "false").lower() == "true"

# Global configuration instance
config = SentinelConfig()