"""
Triple-redundant blockchain data ingestion pipeline with WebSocket fallback.
Implements health checks and automatic failover.
"""
import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any
from concurrent.futures import ThreadPoolExecutor
import aiohttp
from web3 import Web3
from web3.middleware import geth_poa_middleware
from web3.exceptions import BlockNotFound, TimeExhausted

from config import config, Network, RPCConfig

logger = logging.getLogger(__name__)

class RPCHealthCheck:
    """Health monitoring for RPC endpoints"""
    
    @staticmethod
    async def check_rpc_health(rpc_url: str, timeout: int = 5) -> Tuple[bool, float]:
        """Check if RPC endpoint is healthy and return latency"""
        try:
            async with aiohttp.ClientSession() as session:
                start_time = asyncio.get_event_loop().time()
                
                payload = {
                    "jsonrpc": "2.0",
                    "method": "eth_blockNumber",
                    "params": [],
                    "id": 1
                }
                
                async with session.post(
                    rpc_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:
                    end_time = asyncio.get_event_loop().time()
                    latency = (end_time - start_time) * 1000  # Convert to ms
                    
                    if response.status == 200:
                        data = await response.json()
                        if 'result' in data:
                            return True, latency
                    
                    return False, latency
                    
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.debug(f"RPC health check failed for {rpc_url}: {e}")
            return False, timeout * 1000
        except Exception as e:
            logger.warning(f"Unexpected error in health check: {e}")
            return False, timeout * 1000

class BlockchainIngestor:
    """Manages blockchain data ingestion with failover"""
    
    def __init__(self):
        self.web3_clients: Dict[Network, Web3] = {}
        self.rpc_configs: Dict[Network, RPCConfig] = {}
        self.current_rpc_index: Dict[Network, int] = {}
        self.executor = ThreadPoolExecutor(max_workers=5)
        self._initialized = False
        
    def initialize(self) -> None:
        """Initialize Web3 connections for all configured networks"""
        try:
            for network, rpc_config in config.networks.items():
                self.rpc_configs[network] = rpc_config
                self.current_rpc_index[network] = 0
                
                # Create initial Web3 connection
                rpc_url = rpc_config.get_next_rpc()
                w3 = self._create_web3_connection(rpc_url, network)
                
                if w3.is_connected():
                    self.web3_clients[network] = w3
                    logger.info(f"Connected to {network.value} via {self._mask_rpc_url(rpc_url)}")
                else:
                    logger.error(f"Failed to connect to {network.value}")
            
            self._initialized = True
            logger.info(f"Initialized ingestor for {len(self.web3_clients)} networks")
            
        except Exception as e:
            logger.error(f"Failed to initialize blockchain ingestor: {e}")
            raise
    
    def _create_web3_connection(self, rpc_url: str, network: Network) -> Web3:
        """Create Web3 connection with appropriate middleware"""
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        
        # Add POA middleware for networks like Polygon, Arbitrum
        if network in [Network.POLYGON, Network.ARBITRUM, Network.BASE, Network.OPTIMISM]:
            w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        
        return w3
    
    def _mask_rpc_url(self, url: str) -> str:
        """Mask R