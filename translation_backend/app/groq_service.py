from __future__ import annotations

import asyncio
import json
import sys
import os
from datetime import datetime, timezone
from typing import Dict, List, Any, AsyncGenerator, Optional
from dataclasses import dataclass
from pathlib import Path

# Add the root directory to Python path to import from backend
sys.path.append(str(Path(__file__).parent.parent.parent / "backend"))

from groq_client import groq_client, MASTER_AGENT_PROMPT, CREDIT_EXPLANATION_PROMPT, NEGOTIATION_REASONING_PROMPT, REJECTION_EMPATHY_PROMPT, INTENT_CLASSIFICATION_PROMPT
from agents.prompts import SHAP_NARRATION_PROMPT, STAGE_PROMPTS
from app.schemas import ChatRequest, ChatResponse, IntentClassificationRequest, IntentClassificationResponse, HealthResponse

# Import Hinglish detection
from app.hinglish_intent import detect_language_and_style


@dataclass
class ChatMessage:
    role: str
    content: str


class GroqService:
    def __init__(self):
        self.client = groq_client
        self.conversation_histories: Dict[str, List[ChatMessage]] = {}
        self.max_history_length = 6  # Keep last 6 messages (3 turns)
    
    def _get_or_create_history(self, session_id: str) -> List[ChatMessage]:
        """Get or create conversation history for a session"""
        if session_id not in self.conversation_histories:
            self.conversation_histories[session_id] = []
        return self.conversation_histories[session_id]
    
    def _prune_history(self, history: List[ChatMessage], max_messages: int = 6) -> List[ChatMessage]:
        """Prone conversation history to max_messages"""
        if len(history) <= max_messages:
            return history
        
        # Keep the most recent messages
        return history[-max_messages:]
    
    def _create_summary(self, history: List[ChatMessage]) -> str:
        """Create a summary of older conversation context"""
        if len(history) <= 6:
            return ""
        
        older_messages = history[:-6]
        # Simple summary - in production, you'd use Groq for this
        user_requests = [msg.content for msg in older_messages if msg.role == "user"]
        if user_requests:
            return f"Earlier: Applicant requested {', '.join(user_requests[:2])}."
        return ""
    
    async def process_chat_request(self, request: ChatRequest) -> ChatResponse:
        """Process a chat request using Groq with Hinglish detection and stage awareness."""
        try:
            # Detect language and style from user message
            lang_detection = detect_language_and_style(request.message)
            input_style = lang_detection["input_style"]
            detected_language = lang_detection["respond_in"]
            
            # Override request language with detected language if not explicitly set
            effective_language = request.language if request.language else detected_language
            
            # Get or create conversation history
            history = self._get_or_create_history(request.session_id)
            
            # Add user message to history
            user_message = ChatMessage(role="user", content=request.message)
            history.append(user_message)
            
            # Prune history and create summary
            pruned_history = self._prune_history(history)
            summary = self._create_summary(history)
            
            # Determine current stage and completed steps
            current_stage = self._infer_stage_from_history(pruned_history)
            completed_steps = self._get_completed_steps(pruned_history)
            
            # Map inferred stage to STAGE_PROMPTS keys
            stage_prompt_key = self._map_to_stage_prompt_key(current_stage)
            
            # Create system prompt with stage awareness
            system_prompt = MASTER_AGENT_PROMPT.format(
                stage=current_stage,
                language=effective_language,
                completed_steps=", ".join(completed_steps)
            )
            
            # Append stage-specific behavioral instructions
            if stage_prompt_key and stage_prompt_key in STAGE_PROMPTS:
                system_prompt += "\n\n" + STAGE_PROMPTS[stage_prompt_key]
            
            # Prepare messages for Groq
            messages = [
                {"role": "system", "content": system_prompt},
                *[{"role": msg.role, "content": msg.content} for msg in pruned_history]
            ]
            
            # Call Groq with input style hint for Hinglish handling
            response = await self.client.complete(
                messages=messages,
                max_tokens=400,
                temperature=0.3,
                require_json=True,
                input_style=input_style
            )
            
            # Parse response
            try:
                response_data = json.loads(response.content)
            except json.JSONDecodeError:
                # Fallback if JSON parsing fails
                response_data = {
                    "action": "ASK_USER",
                    "user_message": response.content,
                    "reasoning": "Failed to parse structured response",
                    "confidence": 0.5
                }
            
            # Add bot response to history
            bot_message = ChatMessage(role="assistant", content=response_data.get("user_message", ""))
            history.append(bot_message)
            
            return ChatResponse(
                message=response_data.get("user_message", "I'm here to help with your loan application."),
                action=response_data.get("action", "ASK_USER"),
                confidence=response_data.get("confidence", 0.5),
                session_id=request.session_id,
                language=effective_language,
                model_used=response.model_used,
                fallback_used=response.fallback_used,
                response_time_ms=response.response_time_ms
            )
            
        except Exception as e:
            # Error handling
            error_response = ChatResponse(
                message="I'm experiencing technical difficulties. Please try again in a moment.",
                action="ASK_USER",
                confidence=0.1,
                session_id=request.session_id,
                language=request.language or "en",
                model_used="error_fallback",
                fallback_used=True
            )
            
            print(f"Error processing chat request: {e}")
            return error_response
    
    async def stream_chat_response(self, request: ChatRequest) -> AsyncGenerator[str, None]:
        """Stream chat response token by token with Hinglish detection."""
        try:
            # Detect language and style
            lang_detection = detect_language_and_style(request.message)
            input_style = lang_detection["input_style"]
            detected_language = lang_detection["respond_in"]
            effective_language = request.language if request.language else detected_language
            
            # Get or create conversation history
            history = self._get_or_create_history(request.session_id)
            
            # Add user message to history
            user_message = ChatMessage(role="user", content=request.message)
            history.append(user_message)
            
            # Prune history and create summary
            pruned_history = self._prune_history(history)
            summary = self._create_summary(history)
            
            # Determine current stage and completed steps
            current_stage = self._infer_stage_from_history(pruned_history)
            completed_steps = self._get_completed_steps(pruned_history)
            stage_prompt_key = self._map_to_stage_prompt_key(current_stage)
            
            # Create system prompt with stage awareness
            system_prompt = MASTER_AGENT_PROMPT.format(
                stage=current_stage,
                language=effective_language,
                completed_steps=", ".join(completed_steps)
            )
            
            if stage_prompt_key and stage_prompt_key in STAGE_PROMPTS:
                system_prompt += "\n\n" + STAGE_PROMPTS[stage_prompt_key]
            
            # Prepare messages for Groq
            messages = [
                {"role": "system", "content": system_prompt},
                *[{"role": msg.role, "content": msg.content} for msg in pruned_history]
            ]
            
            # For streaming, we'll use a simpler approach with the basic client
            if self.client.client:
                try:
                    # Try to get streaming response
                    loop = asyncio.get_event_loop()
                    
                    def create_stream():
                        return self.client.client.chat.completions.create(
                            model=self.client.primary_model,
                            messages=messages,
                            max_tokens=400,
                            temperature=0.3,
                            stream=True
                        )
                    
                    stream = await loop.run_in_executor(None, create_stream)
                    
                    accumulated_content = ""
                    for chunk in stream:
                        if chunk.choices[0].delta.content:
                            token = chunk.choices[0].delta.content
                            accumulated_content += token
                            yield token
                    
                    # Add final response to history
                    bot_message = ChatMessage(role="assistant", content=accumulated_content)
                    history.append(bot_message)
                    
                    return
                    
                except Exception as e:
                    print(f"Streaming failed, falling back to non-streaming: {e}")
            
            # Fallback to non-streaming with input style
            response = await self.client.complete(
                messages=messages,
                max_tokens=400,
                temperature=0.3,
                input_style=input_style
            )
            
            # Stream the response character by character
            for char in response.content:
                yield char
            
            # Add response to history
            bot_message = ChatMessage(role="assistant", content=response.content)
            history.append(bot_message)
            
        except Exception as e:
            yield f"Error: {str(e)}"
            print(f"Error in stream_chat_response: {e}")
    
    async def classify_intent(self, request: IntentClassificationRequest) -> IntentClassificationResponse:
        """Classify user intent using Groq with Hinglish awareness."""
        try:
            # Detect language/style first
            lang_detection = detect_language_and_style(request.text)
            input_style = lang_detection["input_style"]
            
            # Create prompt for intent classification
            prompt = INTENT_CLASSIFICATION_PROMPT.format(text=request.text)
            
            messages = [
                {"role": "system", "content": "You are an expert at classifying loan application intents."},
                {"role": "user", "content": prompt}
            ]
            
            # Call Groq with input style
            response = await self.client.complete(
                messages=messages,
                max_tokens=150,
                temperature=0.1,
                require_json=True,
                input_style=input_style
            )
            
            # Parse response
            try:
                response_data = json.loads(response.content)
            except json.JSONDecodeError:
                # Fallback parsing
                response_data = {
                    "intent": "GENERAL_QUERY",
                    "confidence": 0.3,
                    "language": "en",
                    "extracted": {"amount": None, "rate": None, "tenure": None}
                }
            
            return IntentClassificationResponse(
                intent=response_data.get("intent", "GENERAL_QUERY"),
                confidence=response_data.get("confidence", 0.3),
                language=response_data.get("language", "en"),
                extracted=response_data.get("extracted", {"amount": None, "rate": None, "tenure": None}),
                model_used=response.model_used,
                fallback_used=response.fallback_used
            )
            
        except Exception as e:
            print(f"Error classifying intent: {e}")
            # Fallback to keyword-based classification
            return self._fallback_intent_classification(request.text)
    
    def _fallback_intent_classification(self, text: str) -> IntentClassificationResponse:
        """Fallback keyword-based intent classification with Hinglish detection."""
        text_lower = text.lower()
        
        # Detect language using enhanced detection
        lang_detection = detect_language_and_style(text)
        language = lang_detection["respond_in"]
        
        # Simple keyword matching
        intent_keywords = {
            "LOAN_REQUEST": ["loan", "need loan", "want loan", "apply loan"],
            "RATE_QUERY": ["rate", "interest", "rate of interest"],
            "EMI_QUERY": ["emi", "monthly payment", "installment"],
            "KYC_READY": ["pan", "aadhaar", "kyc", "upload"],
            "ELIGIBILITY_QUERY": ["eligible", "eligibility", "qualify"],
            "ACCEPTANCE": ["yes", "ok", "agree", "accept"],
            "REJECTION": ["no", "reject", "don't want"],
            "TENURE_CHANGE": ["tenure", "duration", "months", "years"]
        }
        
        # Find matching intent
        matched_intent = "GENERAL_QUERY"
        max_matches = 0
        
        for intent, keywords in intent_keywords.items():
            matches = sum(1 for keyword in keywords if keyword in text_lower)
            if matches > max_matches:
                max_matches = matches
                matched_intent = intent
        
        return IntentClassificationResponse(
            intent=matched_intent,
            confidence=0.6 if max_matches > 0 else 0.3,
            language=language,
            extracted={"amount": None, "rate": None, "tenure": None},
            model_used="keyword_fallback",
            fallback_used=True
        )
    
    async def generate_credit_explanation(self, credit_score: int, risk_score: int, 
                                        decision: str, rate: float, 
                                        shap_factors: List[str], language: str,
                                        structured_shap: Optional[Dict[str, Any]] = None) -> str:
        """Generate credit explanation using Groq with structured SHAP data."""
        try:
            # Format structured SHAP for prompt
            if structured_shap:
                from services.shap_narrator import format_structured_shap_for_groq
                shap_text = format_structured_shap_for_groq(structured_shap)
            else:
                # Fallback to simple factor list
                shap_text = "Top factors: " + ", ".join(shap_factors[:3])
            
            # Use SHAP_NARRATION_PROMPT if structured data available, else fallback
            if structured_shap:
                positive = "\n".join([
                    f"- {f['label']}: {f['actual_value']} (impact: +{f['shap_value']:.3f})"
                    for f in structured_shap.get("positive_factors", [])
                ]) or "None"
                
                negative = "\n".join([
                    f"- {f['label']}: {f['actual_value']} (impact: {f['shap_value']:.3f})"
                    for f in structured_shap.get("negative_factors", [])
                ]) or "None"
                
                prompt = SHAP_NARRATION_PROMPT.format(
                    decision=decision,
                    positive_factors=positive,
                    negative_factors=negative,
                    credit_score=credit_score,
                    risk_score=risk_score,
                    language=language
                )
            else:
                prompt = CREDIT_EXPLANATION_PROMPT.format(
                    credit_score=credit_score,
                    risk_score=risk_score,
                    decision=decision,
                    rate=rate,
                    structured_shap=shap_text,
                    language=language
                )
            
            messages = [
                {"role": "system", "content": "You are a helpful loan officer explaining credit decisions."},
                {"role": "user", "content": prompt}
            ]
            
            # Detect input style for language handling
            lang_detection = detect_language_and_style(" ".join(shap_factors))
            input_style = lang_detection["input_style"]
            
            response = await self.client.complete(
                messages=messages,
                max_tokens=300,
                temperature=0.4,
                input_style=input_style
            )
            
            return response.content
            
        except Exception as e:
            print(f"Error generating credit explanation: {e}")
            # Fallback response
            if decision.lower() == "approved":
                return "Your loan has been approved based on your credit profile. The offered rate reflects your risk assessment."
            else:
                return "Based on your credit profile, we're unable to approve the loan at this time. Please work on improving your credit score."
    
    async def generate_negotiation_explanation(self, starting_rate: float, current_rate: float,
                                              floor_rate: float, round_num: int, max_rounds: int,
                                              risk_tier: str, positive_factor: str, 
                                              language: str) -> str:
        """Generate negotiation explanation using Groq with stage awareness."""
        try:
            prompt = NEGOTIATION_REASONING_PROMPT.format(
                starting_rate=starting_rate,
                current_rate=current_rate,
                floor_rate=floor_rate,
                round=round_num,
                max_rounds=max_rounds,
                risk_tier=risk_tier,
                top_positive_shap_factor=positive_factor,
                language=language
            )
            
            messages = [
                {"role": "system", "content": "You are a loan negotiation agent."},
                {"role": "user", "content": prompt}
            ]
            
            response = await self.client.complete(
                messages=messages,
                max_tokens=150,
                temperature=0.3
            )
            
            return response.content
            
        except Exception as e:
            print(f"Error generating negotiation explanation: {e}")
            return f"Based on your {risk_tier} risk profile, we're offering {current_rate}% interest rate."
    
    async def generate_rejection_message(self, credit_score: int, language: str) -> str:
        """Generate empathetic rejection message using Groq"""
        try:
            prompt = REJECTION_EMPATHY_PROMPT.format(
                score=credit_score,
                language=language
            )
            
            messages = [
                {"role": "system", "content": "You are an empathetic loan officer."},
                {"role": "user", "content": prompt}
            ]
            
            response = await self.client.complete(
                messages=messages,
                max_tokens=200,
                temperature=0.5
            )
            
            return response.content
            
        except Exception as e:
            print(f"Error generating rejection message: {e}")
            return "We understand this is disappointing. Your credit score needs improvement. Please focus on timely payments and reapply after 6 months."
    
    def _infer_stage_from_history(self, history: List[ChatMessage]) -> str:
        """Infer current application stage from conversation history.
        
        Returns stage names that map to STAGE_PROMPTS keys:
        INITIATED, KYC_PENDING, CREDIT_ASSESSED, NEGOTIATING, SANCTIONED
        """
        if not history:
            return "INITIATED"
        
        # Simple heuristic based on conversation content
        recent_messages = " ".join([msg.content.lower() for msg in history[-3:]])
        all_messages = " ".join([msg.content.lower() for msg in history])
        
        # Check for sanction/completion first (highest stage)
        if any(word in all_messages for word in ["sanction", "approved", "disburse", "letter", "blockchain", "accept"]):
            return "SANCTIONED"
        
        # Check for negotiation
        if any(word in recent_messages for word in ["negotiate", "better rate", "counter offer", "concession", "rate kam"]):
            return "NEGOTIATING"
        
        # Check for credit assessment
        if any(word in recent_messages for word in ["credit", "score", "cibil", "risk", "assessment", "approved", "declined"]):
            return "CREDIT_ASSESSED"
        
        # Check for KYC
        if any(word in recent_messages for word in ["pan", "aadhaar", "kyc", "upload", "document", "verify"]):
            return "KYC_PENDING"
        
        # Default to initiated
        return "INITIATED"
    
    def _map_to_stage_prompt_key(self, inferred_stage: str) -> Optional[str]:
        """Map inferred stage to STAGE_PROMPTS keys."""
        stage_mapping = {
            "INITIATED": "INITIATED",
            "KYC_PENDING": "KYC_PENDING",
            "CREDIT_ASSESSED": "CREDIT_ASSESSED",
            "NEGOTIATING": "NEGOTIATING",
            "SANCTIONED": "SANCTIONED",
        }
        return stage_mapping.get(inferred_stage)
    
    def _get_completed_steps(self, history: List[ChatMessage]) -> List[str]:
        """Get list of completed steps from conversation"""
        completed = []
        recent_messages = " ".join([msg.content.lower() for msg in history])
        
        if any(word in recent_messages for word in ["pan verified", "kyc complete", "aadhaar verified"]):
            completed.append("KYC")
        if any(word in recent_messages for word in ["credit score", "risk assessment"]):
            completed.append("Credit Check")
        if any(word in recent_messages for word in ["loan offer", "interest rate"]):
            completed.append("Offer")
        if any(word in recent_messages for word in ["negotiated", "final rate"]):
            completed.append("Negotiation")
        
        return completed
    
    def get_health_status(self) -> HealthResponse:
        """Get health status of the Groq service"""
        groq_health = self.client.get_health_status()
        
        return HealthResponse(
            status="healthy" if groq_health["groq_api_reachable"] else "degraded",
            uptime_seconds=groq_health["uptime_seconds"],
            groq_api_reachable=groq_health["groq_api_reachable"],
            primary_model=groq_health["primary_model"],
            fallback_model=groq_health["fallback_model"],
            requests_today=groq_health["requests_today"],
            fallback_activations=groq_health["fallback_activations"],
            current_mode=groq_health["current_mode"],
            last_error=groq_health["last_error"],
            active_sessions=len(self.conversation_histories)
        )


# Global service instance
groq_service = GroqService()

