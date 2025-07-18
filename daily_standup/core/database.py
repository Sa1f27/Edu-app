"""
Database management module for Daily Standup application
Handles MongoDB and SQL Server connections and operations
"""

import os
import time
import logging
import asyncio
import pyodbc
from typing import Tuple, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient
from urllib.parse import quote_plus
from .config import config

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Optimized database management with connection pooling"""
    
    def __init__(self, client_manager):
        self.client_manager = client_manager
        self._mongo_client = None
        self._mongo_db = None
        
    @property
    def mongo_config(self) -> Dict[str, Any]:
        """Get MongoDB configuration from environment"""
        return {
            "host": os.getenv("MONGODB_HOST"),
            "port": int(os.getenv("MONGODB_PORT", "27017")),
            "username": os.getenv("MONGODB_USERNAME"),
            "password": os.getenv("MONGODB_PASSWORD"),
            "database": os.getenv("MONGODB_DATABASE")
        }
    
    @property
    def sql_config(self) -> Dict[str, Any]:
        """Get SQL Server configuration from environment"""
        return {
            "DRIVER": os.getenv("SQL_DRIVER", "ODBC Driver 17 for SQL Server"),
            "SERVER": os.getenv("SQL_SERVER"),
            "DATABASE": os.getenv("SQL_DATABASE"),
            "UID": os.getenv("SQL_USERNAME"),
            "PWD": os.getenv("SQL_PASSWORD"),
            "timeout": int(os.getenv("SQL_TIMEOUT", "5"))
        }
    
    async def get_mongo_client(self) -> AsyncIOMotorClient:
        """Get MongoDB client with connection pooling"""
        if self._mongo_client is None:
            mongo_cfg = self.mongo_config
            mongo_url = (
                f"mongodb://{quote_plus(mongo_cfg['username'])}:"
                f"{quote_plus(mongo_cfg['password'])}@"
                f"{mongo_cfg['host']}:{mongo_cfg['port']}/"
                f"{mongo_cfg['database']}?authSource=admin"
            )
            
            self._mongo_client = AsyncIOMotorClient(
                mongo_url, 
                maxPoolSize=config.MONGO_MAX_POOL_SIZE,
                serverSelectionTimeoutMS=config.MONGO_SERVER_SELECTION_TIMEOUT
            )
            
            try:
                await self._mongo_client.admin.command('ping')
                logger.info("✅ MongoDB client initialized")
            except Exception as e:
                logger.error(f"❌ MongoDB connection failed: {e}")
                raise Exception(f"MongoDB connection failed: {e}")
                
        return self._mongo_client
    
    async def get_mongo_db(self):
        """Get MongoDB database instance"""
        if self._mongo_db is None:
            client = await self.get_mongo_client()
            self._mongo_db = client[self.mongo_config["database"]]
        return self._mongo_db
    
    def get_sql_connection(self):
        """Get SQL Server connection with optimized configuration"""
        try:
            sql_cfg = self.sql_config
            conn_str = (
                f"DRIVER={{{sql_cfg['DRIVER']}}};"
                f"SERVER={sql_cfg['SERVER']};"
                f"DATABASE={sql_cfg['DATABASE']};"
                f"UID={sql_cfg['UID']};"
                f"PWD={sql_cfg['PWD']};"
            )
            
            conn = pyodbc.connect(conn_str, timeout=sql_cfg['timeout'])
            return conn
        except Exception as e:
            logger.error(f"❌ SQL connection failed: {e}")
            raise Exception(f"SQL Server connection failed: {e}")
    
    async def get_student_info_fast(self) -> Tuple[int, str, str, str]:
        """Fast student info retrieval with dummy data support"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.client_manager.executor,
            self._sync_get_student_info
        )
    
    def _sync_get_student_info(self) -> Tuple[int, str, str, str]:
        """Synchronous student info retrieval for thread pool"""
        if config.USE_DUMMY_DATA:
            logger.warning("⚠️ Using dummy student info (SQL Server is DOWN)")
            student_id = 99999
            first_name = "Dummy"
            last_name = "User"
            session_key = f"SESSION_{int(time.time())}"
            return (student_id, first_name, last_name, session_key)
        
        try:
            conn = self.get_sql_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT TOP 1 ID, First_Name, Last_Name FROM tbl_Student ORDER BY NEWID()")
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if not row:
                raise Exception("No student records found in tbl_Student")
                
            return (row[0], row[1], row[2], f"SESSION_{int(time.time())}")
            
        except Exception as e:
            logger.error(f"❌ Error fetching student info: {e}")
            raise Exception(f"Student info retrieval failed: {e}")
    
    async def get_summary_fast(self) -> str:
        """Fast summary retrieval from MongoDB with dummy data support"""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                self.client_manager.executor,
                self._sync_get_summary
            )
        except Exception as e:
            logger.error(f"❌ Error fetching summary: {e}")
            raise Exception(f"Summary retrieval failed: {e}")
    
    def _sync_get_summary(self) -> str:
        """Synchronous summary retrieval for thread pool"""
        if config.USE_DUMMY_DATA:
            logger.warning("⚠️ Using dummy summary (MongoDB is DOWN)")
            return (
                "MLOps (Machine Learning Operations) is a set of practices that combines Machine Learning, "
                "DevOps, and Data Engineering to deploy and maintain ML models in production reliably. It enables "
                "automation and monitoring of the ML lifecycle, including training, deployment, and retraining. "
                "Key tools include MLflow, Kubeflow, and TFX. MLOps ensures reproducibility, scalability, and model governance, "
                "and addresses challenges like data quality, model drift, and pipeline orchestration."
            )
        
        try:
            import asyncio
            db = asyncio.run(self.get_mongo_db())
            collection = db[config.TRANSCRIPTS_COLLECTION]
            
            doc = asyncio.run(collection.find_one(
                {"summary": {"$exists": True, "$ne": None, "$ne": ""}},
                sort=[("timestamp", -1)]
            ))
            
            if not doc or not doc.get("summary"):
                raise Exception("No valid summary found in MongoDB transcripts collection")
                
            summary = doc["summary"].strip()
            if len(summary) < 100:
                raise Exception(f"Summary too short ({len(summary)} chars): {summary}")
                
            return summary
            
        except Exception as e:
            logger.error(f"❌ Sync summary retrieval error: {e}")
            raise Exception(f"MongoDB summary retrieval failed: {e}")
    
    async def save_session_result_fast(self, session_data, evaluation: str, score: float) -> bool:
        """Fast session result saving"""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                self.client_manager.executor,
                self._sync_save_result,
                session_data, evaluation, score
            )
        except Exception as e:
            logger.error(f"❌ Error saving session result: {e}")
            raise Exception(f"Session save failed: {e}")
    
    def _sync_save_result(self, session_data, evaluation: str, score: float) -> bool:
        """Synchronous save for thread pool"""
        try:
            import asyncio
            db = asyncio.run(self.get_mongo_db())
            collection = db[config.RESULTS_COLLECTION]
            
            document = {
                "test_id": session_data.test_id,
                "session_id": session_data.session_id,
                "student_id": session_data.student_id,
                "student_name": session_data.student_name,
                "session_key": session_data.session_key,
                "timestamp": time.time(),
                "created_at": session_data.created_at,
                "conversation_log": [
                    {
                        "timestamp": exchange.timestamp,
                        "stage": exchange.stage.value,
                        "ai_message": exchange.ai_message,
                        "user_response": exchange.user_response,
                        "transcript_quality": exchange.transcript_quality,
                        "chunk_id": exchange.chunk_id
                    }
                    for exchange in session_data.exchanges
                ],
                "evaluation": evaluation,
                "score": score,
                "total_exchanges": len(session_data.exchanges),
                "greeting_exchanges": session_data.greeting_count,
                "summary_progress": session_data.summary_manager.get_progress() if session_data.summary_manager else {},
                "duration": time.time() - session_data.created_at
            }
            
            result = asyncio.run(collection.insert_one(document))
            logger.info(f"Session {session_data.session_id} saved successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Sync save error: {e}")
            raise Exception(f"MongoDB save failed: {e}")
    
    async def get_session_result_fast(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Fast session result retrieval"""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                self.client_manager.executor,
                self._sync_get_session_result,
                session_id
            )
        except Exception as e:
            logger.error(f"❌ Error fetching session result: {e}")
            raise Exception(f"Session result retrieval failed: {e}")
    
    def _sync_get_session_result(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Synchronous session result retrieval"""
        try:
            import asyncio
            db = asyncio.run(self.get_mongo_db())
            collection = db[config.RESULTS_COLLECTION]
            result = asyncio.run(collection.find_one({"session_id": session_id}))
            
            if result:
                result['_id'] = str(result['_id'])
                return result
            return None
            
        except Exception as e:
            logger.error(f"❌ Sync session result error: {e}")
            raise Exception(f"Session result retrieval failed: {e}")
    
    async def close_connections(self):
        """Cleanup method for graceful shutdown"""
        if self._mongo_client:
            self._mongo_client.close()
        logger.info("🔌 Database connections closed")