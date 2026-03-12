"""
Firebase integration for Project Sentinel with error handling and state management.
Implements the immutable command ledger and kill switch system.
"""
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import asdict
import firebase_admin
from firebase_admin import firestore, credentials, db
from firebase_admin.exceptions import FirebaseError

from config import config

logger = logging.getLogger(__name__)

class FirebaseManager:
    """Manages all Firebase interactions with error recovery"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FirebaseManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._initialized = True
            self.app = None
            self.db_firestore = None
            self.db_realtime = None
            self._initialize_firebase()
    
    def _initialize_firebase(self) -> None:
        """Initialize Firebase connection with validation"""
        try:
            if not config.firebase:
                logger.warning("Firebase not configured. Running in local mode.")
                return
            
            # Check if Firebase already initialized
            if len(firebase_admin._apps) > 0:
                self.app = firebase_admin.get_app()
            else:
                # Validate service account file exists
                if not config.firebase.validate():
                    raise FileNotFoundError("Firebase configuration invalid")
                
                # Initialize Firebase
                cred = credentials.Certificate(config.firebase.service_account_key_path)
                firebase_config = {
                    'credential': cred,
                    'projectId': config.firebase.project_id
                }
                
                if config.firebase.database_url:
                    firebase_config['databaseURL'] = config.firebase.database_url
                
                self.app = firebase_admin.initialize_app(**firebase_config)
            
            # Initialize clients
            self.db_firestore = firestore.client()
            self.db_realtime = db.reference() if config.firebase.database_url else None
            
            logger.info("Firebase initialized successfully")
            
        except FileNotFoundError as e:
            logger.error(f"Firebase configuration error: {e}")
            raise
        except FirebaseError as e:
            logger.error(f"Firebase initialization error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error initializing Firebase: {e}")
            raise
    
    def log_transaction(self, chain_id: int, block_number: int, tx_hash: str, 
                       data: Dict[str, Any]) -> bool:
        """
        Log transaction to immutable command ledger in Firestore.
        Returns success status.
        """
        if not self.db_firestore:
            logger.warning("Firestore not available. Transaction not logged.")
            return False
        
        try:
            # Construct document path
            doc_path = f"ledger/{chain_id}/{block_number}/{tx_hash}"
            
            # Add metadata
            data.update({
                'timestamp': datetime.utcnow().isoformat(),
                'cell_id': config.cell_id,
                'logged_at': firestore.SERVER_TIMESTAMP
            })
            
            # Write to Firestore
            doc_ref = self.db_firestore.document(doc_path)
            doc_ref.set(data)
            
            logger.debug(f"Logged transaction {tx_hash} to Firestore")
            return True
            
        except FirebaseError as e:
            logger.error(f"Firestore write error for tx {tx_hash}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error logging transaction {tx_hash}: {e}")
            return False
    
    def check_kill_switch(self) -> bool:
        """
        Check if kill switch is activated in Realtime Database.
        Returns True if system should stop.
        """
        if not self.db_realtime:
            logger.debug("Realtime DB not configured. Kill switch check skipped.")
            return False
        
        try:
            kill_switch_ref = self.db_realtime.child('system/kill_switch')
            kill_data = kill_switch_ref.get()
            
            if kill_data and isinstance(kill_data, dict):
                is_active = kill_data.get('active', False)
                if is_active:
                    logger.critical("KILL SWITCH ACTIVATED! Shutting down.")
                    return True
            
            return False
            
        except FirebaseError as e:
            logger.error(f"Error checking kill switch: {e}")
            # Default to continue running on error (failsafe)
            return False
        except Exception as e:
            logger.error(f"Unexpected error checking kill switch: {e}")
            return False
    
    def get_cell_health(self, cell_id: str) -> Optional[Dict[str, Any]]:
        """Get health status of a specific cell"""
        if not self.db_firestore:
            return None
        
        try:
            doc_ref = self.db_firestore.document(f"cells/{cell_id}")
            doc = doc_ref.get()
            return doc.to_dict() if doc.exists else None
        except FirebaseError as e:
            logger.error(f"Error getting cell health for {cell_id}: {e}")
            return None
    
    def update_cell_health(self, status: str, metrics: Dict[str, Any]) -> bool:
        """Update this cell's health status"""
        if not self.db_firestore:
            return False
        
        try:
            health_data = {
                'cell_id': config.cell_id,
                'status': status,
                'last_heartbeat': firestore.SERVER_TIMESTAMP,
                'metrics': metrics,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            doc_ref = self.db_firestore.document(f"cells/{config.cell_id}")
            doc_ref.set(health_data)
            return True
            
        except FirebaseError as e:
            logger.error(f"Error updating cell health: {e}")
            return False
    
    def log_anomaly(self, anomaly_type: str, data: Dict[str, Any], 
                   severity: str = "warning") -> bool:
        """Log anomaly for forensic analysis"""
        if not self.db_firestore:
            return False
        
        try:
            anomaly_id = f"{anomaly_type}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            doc_path = f"anomalies/{anomaly_id}"
            
            anomaly_data = {
                'type': anomaly_type,
                'severity': severity,
                'cell_id': config.cell_id,
                'data': data,
                'timestamp': firestore.SERVER_TIMESTAMP
            }
            
            doc_ref = self.db_firestore.document(doc_path)
            doc_ref.set(anomaly_data)
            
            logger.warning(f"Logged anomaly: {anomaly_type} ({severity})")
            return True
            
        except FirebaseError as e:
            logger.error(f"Error logging anomaly: {e}")
            return False

# Global Firebase manager instance
firebase_manager = FirebaseManager()