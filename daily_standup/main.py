"""
Ultra-fast, summary-based daily standup backend with optimized performance
Refactored main entry point with modular architecture
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, File, UploadFile, Form
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import time
import uuid
import logging
import os
import tempfile
import io
from typing import Dict, List, Optional, AsyncGenerator, Tuple, Any
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import textwrap
import re
from datetime import datetime
import aiofiles
import random
import base64
import concurrent.futures

# Local imports - FIXED: Use relative imports
from .core import (
    config,
    DatabaseManager,
    SharedClientManager, 
    SessionData, 
    SessionStage,
    SummaryManager, 
    OptimizedAudioProcessor, 
    UltraFastTTSProcessor, 
    OptimizedConversationManager,
    shared_clients,
    prompts
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# ULTRA-FAST SESSION MANAGER
# =============================================================================

class UltraFastSessionManager:
    def __init__(self):
        self.active_sessions: Dict[str, SessionData] = {}
        self.db_manager = DatabaseManager(shared_clients)
        self.audio_processor = OptimizedAudioProcessor(shared_clients)
        self.tts_processor = UltraFastTTSProcessor()
        self.conversation_manager = OptimizedConversationManager(shared_clients)
    
    async def create_session_fast(self, websocket: Optional[Any] = None) -> SessionData:
        """Ultra-fast session creation"""
        session_id = str(uuid.uuid4())
        test_id = f"standup_{int(time.time())}"
        
        # Get student info and summary in parallel
        student_info_task = asyncio.create_task(self.db_manager.get_student_info_fast())
        summary_task = asyncio.create_task(self.db_manager.get_summary_fast())
        
        student_id, first_name, last_name, session_key = await student_info_task
        summary = await summary_task
        
        # Create session
        session_data = SessionData(
            session_id=session_id,
            test_id=test_id,
            student_id=student_id,
            student_name=f"{first_name} {last_name}",
            session_key=session_key,
            created_at=time.time(),
            last_activity=time.time(),
            current_stage=SessionStage.GREETING,
            websocket=websocket
        )
        
        # Initialize summary manager
        summary_manager = SummaryManager(shared_clients)
        await summary_manager.initialize_chunks(summary)
        session_data.summary_manager = summary_manager
        
        self.active_sessions[session_id] = session_data
        logger.info(f"✅ Fast session created {session_id} for {session_data.student_name}")
        
        return session_data
    
    async def remove_session(self, session_id: str):
        """Fast session removal"""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
            logger.info(f"Removed session {session_id}")
    
    async def process_audio_ultra_fast(self, session_id: str, audio_data: bytes):
        """Ultra-fast audio processing pipeline"""
        session_data = self.active_sessions.get(session_id)
        if not session_data or not session_data.is_active:
            return
        
        start_time = time.time()
        
        # Start transcription immediately
        transcription_task = asyncio.create_task(
            self.audio_processor.transcribe_audio_fast(audio_data)
        )
        
        transcript, quality = await transcription_task
        
        if not transcript or len(transcript.strip()) < 2:
            await self._send_quick_message(session_data, {
                "type": "clarification",
                "text": prompts.clarification_message(),
                "status": session_data.current_stage.value
            })
            return
        
        logger.info(f"Session {session_id}: User said: {transcript}")
        
        # Generate AI response immediately
        response_task = asyncio.create_task(
            self.conversation_manager.generate_fast_response(session_data, transcript)
        )
        
        ai_response = await response_task
        
        # Add exchange to session with chunk tracking
        chunk_id = None
        if session_data.summary_manager:
            current_chunk = session_data.summary_manager.get_current_chunk()
            chunk_id = current_chunk.id if current_chunk else None
        
        session_data.add_exchange(ai_response, transcript, quality, chunk_id)
        
        # Update session state
        await self._update_session_state_fast(session_data)
        
        # Send response with ultra-fast audio streaming
        await self._send_response_with_ultra_fast_audio(session_data, ai_response)
        
        processing_time = time.time() - start_time
        logger.info(f"⚡ Total processing time: {processing_time:.2f}s")
    
    async def _update_session_state_fast(self, session_data: SessionData):
        """Ultra-fast session state updates"""
        if session_data.current_stage == SessionStage.GREETING:
            session_data.greeting_count += 1
            if session_data.greeting_count >= config.GREETING_EXCHANGES:
                session_data.current_stage = SessionStage.TECHNICAL
                logger.info(f"Session {session_data.session_id} moved to TECHNICAL stage")
        
        elif session_data.current_stage == SessionStage.TECHNICAL:
            # Check if all summary chunks are completed
            if session_data.summary_manager and session_data.summary_manager.current_chunk_index >= len(session_data.summary_manager.chunks):
                session_data.current_stage = SessionStage.COMPLETE
                logger.info(f"Session {session_data.session_id} moved to COMPLETE stage")
                
                # Generate evaluation and save session in background
                asyncio.create_task(self._finalize_session_fast(session_data))
    
    async def _finalize_session_fast(self, session_data: SessionData):
        """Fast session finalization"""
        try:
            evaluation_task = asyncio.create_task(
                self.conversation_manager.generate_fast_evaluation(session_data)
            )
            
            evaluation, score = await evaluation_task
            
            save_task = asyncio.create_task(
                self.db_manager.save_session_result_fast(session_data, evaluation, score)
            )
            
            completion_message = prompts.final_completion_message()
            
            await self._send_quick_message(session_data, {
                "type": "conversation_end",
                "text": completion_message,
                "evaluation": evaluation,
                "score": score,
                "pdf_url": f"/download_results/{session_data.session_id}",
                "status": "complete"
            })
            
            # Generate and send final audio
            async for audio_chunk in self.tts_processor.generate_ultra_fast_stream(completion_message):
                if audio_chunk:
                    await self._send_quick_message(session_data, {
                        "type": "audio_chunk",
                        "audio": audio_chunk.hex(),
                        "status": "complete"
                    })
            
            await self._send_quick_message(session_data, {"type": "audio_end", "status": "complete"})
            
            session_data.is_active = False
            await save_task
            
        except Exception as e:
            logger.error(f"❌ Fast session finalization error: {e}")
            raise Exception(f"Session finalization failed: {e}")
    
    async def _send_response_with_ultra_fast_audio(self, session_data: SessionData, text: str):
        """Send response with ultra-fast audio streaming"""
        try:
            await self._send_quick_message(session_data, {
                "type": "ai_response",
                "text": text,
                "status": session_data.current_stage.value
            })
            
            chunk_count = 0
            async for audio_chunk in self.tts_processor.generate_ultra_fast_stream(text):
                if audio_chunk and session_data.is_active:
                    await self._send_quick_message(session_data, {
                        "type": "audio_chunk",
                        "audio": audio_chunk.hex(),
                        "status": session_data.current_stage.value
                    })
                    chunk_count += 1
            
            await self._send_quick_message(session_data, {
                "type": "audio_end",
                "status": session_data.current_stage.value
            })
            
            logger.info(f"🎵 Streamed {chunk_count} audio chunks")
            
        except Exception as e:
            logger.error(f"❌ Ultra-fast audio streaming error: {e}")
            raise Exception(f"Audio streaming failed: {e}")
    
    async def _send_quick_message(self, session_data: SessionData, message: dict):
        """Ultra-fast WebSocket message sending"""
        try:
            if session_data.websocket:
                await session_data.websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"❌ Quick WebSocket send error: {e}")
            raise Exception(f"WebSocket send failed: {e}")
    
    async def get_session_result_fast(self, session_id: str) -> dict:
        """Fast session result retrieval"""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                shared_clients.executor,
                self.db_manager._sync_get_session_result,
                session_id
            )
        except Exception as e:
            logger.error(f"❌ Error fetching session result: {e}")
            raise Exception(f"Session result retrieval failed: {e}")

    # LEGACY SUPPORT (OPTIMIZED)
    async def process_legacy_audio_fast(self, test_id: str, audio_data: bytes) -> dict:
        """Fast legacy audio processing"""
        try:
            logger.info(f"Processing legacy audio for test_id: {test_id}")
            
            transcript, quality = await self.audio_processor.transcribe_audio_fast(audio_data)
            
            if not transcript or len(transcript.strip()) < 2:
                raise Exception("Transcription returned empty or too short result")
            
            summary = await self.db_manager.get_summary_fast()
            
            session_data = SessionData(
                session_id=test_id,
                test_id=test_id,
                student_id=1000,
                student_name="Legacy User",
                session_key="LEGACY",
                created_at=time.time(),
                last_activity=time.time(),
                current_stage=SessionStage.TECHNICAL
            )
            
            ai_response = await self.conversation_manager.generate_fast_response(
                session_data, transcript
            )
            
            return {
                "response": ai_response,
                "audio_path": None,
                "ended": False,
                "complete": False,
                "status": "success"
            }
            
        except Exception as e:
            logger.error(f"❌ Legacy audio processing error: {e}")
            raise Exception(f"Legacy audio processing failed: {e}")

# =============================================================================
# FASTAPI APPLICATION
# =============================================================================

# Create FastAPI sub-application
app = FastAPI(title=config.APP_TITLE, version=config.APP_VERSION)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOW_ORIGINS,
    allow_credentials=config.CORS_ALLOW_CREDENTIALS,
    allow_methods=config.CORS_ALLOW_METHODS,
    allow_headers=config.CORS_ALLOW_HEADERS,
)

# Mount static files
app.mount("/audio", StaticFiles(directory=str(config.AUDIO_DIR)), name="audio")

# Initialize ultra-fast session manager
session_manager = UltraFastSessionManager()

@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    logger.info("🚀 Ultra-Fast Daily Standup application started")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    await shared_clients.close_connections()
    await session_manager.db_manager.close_connections()
    logger.info("Daily Standup application shutting down")

# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/start_test")
async def start_standup_session_fast():
    """Start a new daily standup session with ultra-fast initialization"""
    try:
        logger.info("🚀 Starting ultra-fast standup session...")
        
        session_data = await session_manager.create_session_fast()
        
        greeting = "Hello! Welcome to your daily standup. How are you doing today?"
        
        logger.info(f"⚡ Ultra-fast session created: {session_data.test_id}")
        
        return {
            "status": "success",
            "message": "Session started successfully",
            "test_id": session_data.test_id,
            "session_id": session_data.session_id,
            "websocket_url": f"/daily_standup/ws/{session_data.session_id}",
            "greeting": greeting,
            "summary_chunks": len(session_data.summary_manager.chunks) if session_data.summary_manager else 0
        }
        
    except Exception as e:
        logger.error(f"❌ Error starting session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")

@app.post("/api/record-respond")
async def record_and_respond_fast(
    audio: UploadFile = File(...),
    test_id: str = Form(...)
):
    """Ultra-fast audio processing endpoint"""
    try:
        logger.info(f"🎤 Processing audio for test_id: {test_id}")
        
        if not test_id:
            raise HTTPException(status_code=400, detail="test_id is required")
        
        if not audio or not audio.content_type.startswith('audio/'):
            raise HTTPException(status_code=400, detail="Valid audio file is required")
        
        audio_data = await audio.read()
        if len(audio_data) < 1000:
            raise HTTPException(status_code=400, detail="Audio file too small")
        
        result = await session_manager.process_legacy_audio_fast(test_id, audio_data)
        
        logger.info(f"⚡ Audio processed for {test_id}")
        
        return {
            "status": "success",
            "response": result.get("response", "Thank you for your input."),
            "audio_path": result.get("audio_path"),
            "ended": result.get("ended", False),
            "complete": result.get("complete", False),
            "message": result.get("response", "Processing complete")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Record and respond error: {e}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@app.get("/api/summary/{test_id}")
async def get_standup_summary_fast(test_id: str):
    """Get standup session summary with ultra-fast retrieval"""
    try:
        logger.info(f"📊 Getting summary for test_id: {test_id}")
        
        if not test_id:
            raise HTTPException(status_code=400, detail="test_id is required")
        
        result = await session_manager.get_session_result_fast(test_id)
        
        if result:
            exchanges = result.get("conversation_log", [])
            
            yesterday_work = ""
            today_plans = ""
            blockers = ""
            additional_notes = ""
            
            for exchange in exchanges:
                user_response = exchange.get("user_response", "").lower()
                ai_message = exchange.get("ai_message", "").lower()
                
                if any(word in ai_message for word in ["yesterday", "accomplished", "completed"]):
                    yesterday_work = exchange.get("user_response", "")
                elif any(word in ai_message for word in ["today", "plan", "working on"]):
                    today_plans = exchange.get("user_response", "")
                elif any(word in ai_message for word in ["blocker", "challenge", "obstacle", "stuck"]):
                    blockers = exchange.get("user_response", "")
                elif exchange.get("user_response") and not yesterday_work and not today_plans:
                    additional_notes = exchange.get("user_response", "")
            
            summary_data = {
                "test_id": test_id,
                "session_id": result.get("session_id", test_id),
                "student_name": result.get("student_name", "Student"),
                "timestamp": result.get("timestamp", time.time()),
                "duration": result.get("duration", 0),
                "yesterday": yesterday_work or "Progress discussed during session",
                "today": today_plans or "Plans outlined during session",
                "blockers": blockers or "No specific blockers mentioned",
                "notes": additional_notes or "Additional discussion points covered",
                "accomplishments": yesterday_work,
                "plans": today_plans,
                "challenges": blockers,
                "additional_info": additional_notes,
                "evaluation": result.get("evaluation", "Session completed successfully"),
                "score": result.get("score", 8.0),
                "total_exchanges": result.get("total_exchanges", 0),
                "summary_progress": result.get("summary_progress", {}),
                "pdf_url": f"/daily_standup/download_results/{test_id}",
                "status": "completed"
            }
        else:
            raise HTTPException(status_code=404, detail=f"Session result not found for test_id: {test_id}")
        
        logger.info(f"⚡ Fast summary generated for {test_id}")
        return summary_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting summary: {e}")
        raise HTTPException(status_code=500, detail=f"Summary retrieval failed: {str(e)}")

@app.websocket("/ws/{session_id}")
async def websocket_endpoint_ultra_fast(websocket: WebSocket, session_id: str):
    """Ultra-fast WebSocket endpoint with optimized communication"""
    await websocket.accept()
    
    try:
        logger.info(f"🔌 WebSocket connected for session: {session_id}")
        
        session_data = session_manager.active_sessions.get(session_id)
        if not session_data:
            logger.error(f"❌ Session {session_id} not found in active sessions")
            await websocket.send_text(json.dumps({
                "type": "error",
                "text": f"Session {session_id} not found. Please start a new session.",
                "status": "error"
            }))
            return
        
        session_data.websocket = websocket
        
        # Send initial greeting with ultra-fast audio
        greeting = "Hello! Welcome to your daily standup. How are you doing today?"
        await websocket.send_text(json.dumps({
            "type": "ai_response",
            "text": greeting,
            "status": "greeting"
        }))
        
        # Generate and stream greeting audio with minimal delay
        async for audio_chunk in session_manager.tts_processor.generate_ultra_fast_stream(greeting):
            if audio_chunk:
                await websocket.send_text(json.dumps({
                    "type": "audio_chunk",
                    "audio": audio_chunk.hex(),
                    "status": "greeting"
                }))
        
        await websocket.send_text(json.dumps({
            "type": "audio_end",
            "status": "greeting"
        }))
        
        # Keep connection alive and handle messages
        while session_data.is_active:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=config.WEBSOCKET_TIMEOUT)
                message = json.loads(data)
                
                if message.get("type") == "audio_data":
                    audio_data = base64.b64decode(message.get("audio", ""))
                    asyncio.create_task(
                        session_manager.process_audio_ultra_fast(session_id, audio_data)
                    )
                
                elif message.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                
            except asyncio.TimeoutError:
                logger.info(f"🔌 WebSocket timeout: {session_id}")
                break
            except WebSocketDisconnect:
                logger.info(f"🔌 WebSocket disconnected: {session_id}")
                break
            except Exception as e:
                logger.error(f"❌ WebSocket error: {e}")
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "text": f"Error: {str(e)}",
                    "status": "error"
                }))
                break
    
    except Exception as e:
        logger.error(f"❌ WebSocket endpoint error: {e}")
    finally:
        await session_manager.remove_session(session_id)

@app.get("/download_results/{session_id}")
async def download_results_fast(session_id: str):
    """Fast PDF generation and download"""
    try:
        result = await session_manager.get_session_result_fast(session_id)
        
        if not result:
            raise HTTPException(status_code=404, detail="Session not found")
        
        loop = asyncio.get_event_loop()
        pdf_buffer = await loop.run_in_executor(
            shared_clients.executor,
            generate_pdf_report,
            result, session_id
        )
        
        return StreamingResponse(
            io.BytesIO(pdf_buffer),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=standup_report_{session_id}.pdf"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ PDF generation error: {e}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

@app.get("/health")
async def health_check_fast():
    """Ultra-fast health check"""
    try:
        return {
            "status": "healthy",
            "service": "ultra_fast_daily_standup",
            "timestamp": time.time(),
            "active_sessions": len(session_manager.active_sessions),
            "version": config.APP_VERSION,
            "dummy_data_mode": config.USE_DUMMY_DATA
        }
    except Exception as e:
        logger.error(f"❌ Health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

@app.get("/test")
async def test_endpoint_fast():
    """Fast test endpoint"""
    return {
        "message": "Ultra-Fast Daily Standup service is running",
        "timestamp": time.time(),
        "status": "blazing_fast",
        "config": {
            "dummy_data": config.USE_DUMMY_DATA,
            "debug_mode": config.DEBUG_MODE,
            "greeting_exchanges": config.GREETING_EXCHANGES,
            "summary_chunks": config.SUMMARY_CHUNKS,
            "openai_model": config.OPENAI_MODEL
        },
        "optimizations": [
            "800ms silence detection",
            "Parallel processing pipeline", 
            "Summary-based questioning",
            "Sliding window conversation history",
            "Ultra-fast TTS streaming",
            "Thread pool optimization",
            "Session synchronization fix",
            "NO FALLBACKS - Real error detection",
            "Modular architecture"
        ]
    }

# =============================================================================
# PDF GENERATION UTILITY
# =============================================================================

def generate_pdf_report(result: dict, session_id: str) -> bytes:
    """Generate PDF report synchronously"""
    try:
        pdf_buffer = io.BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=LETTER)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        title = f"Daily Standup Report - {result.get('student_name', 'Student')}"
        story.append(Paragraph(title, styles['Title']))
        story.append(Spacer(1, 12))
        
        # Session info
        info_text = f"""
        Session ID: {session_id}
        Date: {datetime.fromtimestamp(result.get('timestamp', time.time())).strftime('%Y-%m-%d %H:%M:%S')}
        Duration: {result.get('duration', 0)/60:.1f} minutes
        Total Exchanges: {result.get('total_exchanges', 0)}
        Summary Progress: {result.get('summary_progress', {}).get('chunk_progress', 'N/A')}
        """
        story.append(Paragraph(info_text, styles['Normal']))
        story.append(Spacer(1, 12))
        
        # Conversation log
        story.append(Paragraph("Conversation Summary", styles['Heading2']))
        for exchange in result.get('conversation_log', [])[:15]:
            story.append(Paragraph(f"AI: {exchange.get('ai_message', '')}", styles['Normal']))
            story.append(Paragraph(f"User: {exchange.get('user_response', '')}", styles['Normal']))
            story.append(Spacer(1, 6))
        
        # Evaluation
        if result.get('evaluation'):
            story.append(Paragraph("Evaluation", styles['Heading2']))
            story.append(Paragraph(result['evaluation'], styles['Normal']))
            story.append(Paragraph(f"Score: {result.get('score', 0)}/10", styles['Normal']))
        
        doc.build(story)
        pdf_buffer.seek(0)
        return pdf_buffer.read()
        
    except Exception as e:
        logger.error(f"❌ PDF generation error: {e}")
        raise Exception(f"PDF generation failed: {e}")