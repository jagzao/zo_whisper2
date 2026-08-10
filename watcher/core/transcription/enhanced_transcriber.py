#!/usr/bin/env python3
"""
Enhanced Transcription Client - Connects to dedicated transcription service
Includes fallback to local processing with quality improvements
"""

import os
import requests
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import structlog
import whisper
import torch
import numpy as np
import librosa
import noisereduce as nr
from scipy.io import wavfile
import tempfile

logger = structlog.get_logger("enhanced_transcriber")

class EnhancedTranscriptionClient:
    """Client for high-quality transcription with service fallback"""
    
    def __init__(self, 
                 service_url: str = "http://transcription_service:9000",
                 fallback_to_local: bool = True,
                 local_model: str = "large-v3"):
        
        self.service_url = service_url
        self.fallback_to_local = fallback_to_local
        self.local_model = local_model
        self._local_whisper_model = None
        
        # Quality enhancement settings
        self.quality_settings = {
            "use_service": True,
            "preprocessing": True,
            "noise_reduction": True,
            "volume_normalization": True,
            "silence_removal": True,
            "post_processing": True,
            "language_specific_cleaning": True
        }
        
        logger.info("Enhanced Transcription Client initialized",
                   service_url=service_url,
                   fallback_enabled=fallback_to_local,
                   local_model=local_model)
    
    def transcribe_audio(self, 
                        audio_path: str, 
                        language: str = "es",
                        quality_level: str = "high",
                        project_name: str = "General") -> Dict[str, Any]:
        """
        Main transcription method with enhanced quality
        
        Args:
            audio_path: Path to audio file
            language: Language code (es, en, etc.)
            quality_level: fastest, balanced, high
            project_name: Project context for optimization
            
        Returns:
            Enhanced transcription result with quality metrics
        """
        start_time = datetime.now()
        
        try:
            logger.info("Starting enhanced transcription", 
                       audio_path=audio_path,
                       language=language,
                       quality_level=quality_level,
                       project=project_name)
            
            # Step 1: Try dedicated transcription service first
            if self.quality_settings["use_service"]:
                service_result = self._transcribe_via_service(
                    audio_path, language, quality_level, project_name
                )
                
                if service_result and "error" not in service_result:
                    logger.info("Transcription completed via service", 
                               confidence=service_result.get("confidence", 0),
                               quality_score=service_result.get("quality_score", 0))
                    return service_result
                else:
                    logger.warning("Service transcription failed, falling back to local",
                                  error=service_result.get("error") if service_result else "No response")
            
            # Step 2: Fallback to local processing with enhancements
            if self.fallback_to_local:
                local_result = self._transcribe_locally_enhanced(
                    audio_path, language, quality_level, project_name
                )
                
                if local_result and "error" not in local_result:
                    logger.info("Transcription completed locally with enhancements")
                    return local_result
            
            # Step 3: Basic fallback
            logger.warning("All enhanced methods failed, using basic transcription")
            return self._basic_transcription_fallback(audio_path, language)
            
        except Exception as e:
            logger.error("Enhanced transcription failed completely", 
                        audio_path=audio_path, 
                        error=str(e))
            return {
                "error": str(e),
                "text": "",
                "confidence": 0.0,
                "quality_score": 0.0,
                "processing_time_seconds": (datetime.now() - start_time).total_seconds(),
                "method_used": "error"
            }
    
    def _transcribe_via_service(self, 
                               audio_path: str, 
                               language: str, 
                               quality_level: str,
                               project_name: str) -> Optional[Dict[str, Any]]:
        """Transcribe using dedicated transcription service"""
        try:
            # Check if service is available
            health_url = f"{self.service_url}/health"
            health_response = requests.get(health_url, timeout=5)
            
            if health_response.status_code != 200:
                logger.warning("Transcription service health check failed", 
                              status_code=health_response.status_code)
                return None
            
            # Prepare file for upload
            with open(audio_path, 'rb') as audio_file:
                files = {'audio': audio_file}
                data = {
                    'language': language,
                    'quality': quality_level,
                    'model': self._get_optimal_model_for_quality(quality_level)
                }
                
                # Make transcription request
                transcribe_url = f"{self.service_url}/transcribe"
                response = requests.post(
                    transcribe_url, 
                    files=files, 
                    data=data,
                    timeout=600  # 10 minute timeout for long files
                )
                
                if response.status_code == 200:
                    result = response.json()
                    result["method_used"] = "service"
                    return result
                else:
                    logger.error("Service transcription request failed", 
                               status_code=response.status_code,
                               response=response.text[:200])
                    return None
                    
        except requests.exceptions.RequestException as e:
            logger.warning("Failed to connect to transcription service", error=str(e))
            return None
        except Exception as e:
            logger.error("Unexpected error in service transcription", error=str(e))
            return None
    
    def _transcribe_locally_enhanced(self, 
                                   audio_path: str, 
                                   language: str, 
                                   quality_level: str,
                                   project_name: str) -> Dict[str, Any]:
        """Enhanced local transcription with quality improvements"""
        try:
            # Load local Whisper model if needed
            if not self._local_whisper_model:
                model_name = self._get_optimal_model_for_quality(quality_level)
                logger.info("Loading local Whisper model", model=model_name)
                self._local_whisper_model = whisper.load_model(
                    model_name,
                    device="cuda" if torch.cuda.is_available() else "cpu"
                )
            
            # Enhanced audio preprocessing
            preprocessed_path = None
            if self.quality_settings["preprocessing"]:
                preprocessed_path = self._preprocess_audio_locally(audio_path)
            
            # Use preprocessed audio or original
            final_audio_path = preprocessed_path or audio_path
            
            # Enhanced transcription options
            transcribe_options = self._get_enhanced_transcribe_options(
                language, quality_level, final_audio_path
            )
            
            logger.info("Starting local enhanced transcription", 
                       model=self.local_model,
                       options=transcribe_options)
            
            # Perform transcription
            result = self._local_whisper_model.transcribe(
                final_audio_path,
                **transcribe_options
            )
            
            # Enhanced post-processing
            enhanced_result = self._post_process_local_result(
                result, language, project_name
            )
            
            # Cleanup preprocessed file
            if preprocessed_path and preprocessed_path != audio_path:
                try:
                    os.unlink(preprocessed_path)
                except:
                    pass
            
            enhanced_result["method_used"] = "local_enhanced"
            return enhanced_result
            
        except Exception as e:
            logger.error("Enhanced local transcription failed", error=str(e))
            return {"error": str(e)}
    
    def _preprocess_audio_locally(self, audio_path: str) -> str:
        """Local audio preprocessing for quality improvement"""
        try:
            logger.debug("Starting local audio preprocessing", file=audio_path)
            
            # Load audio with librosa
            audio, sr = librosa.load(audio_path, sr=16000)  # Whisper's preferred sample rate
            
            processed_audio = audio.copy()
            
            # Apply noise reduction
            if self.quality_settings["noise_reduction"]:
                processed_audio = nr.reduce_noise(
                    y=processed_audio, 
                    sr=sr,
                    stationary=False,
                    prop_decrease=0.8
                )
                logger.debug("Applied noise reduction")
            
            # Volume normalization
            if self.quality_settings["volume_normalization"]:
                processed_audio = librosa.util.normalize(processed_audio)
                processed_audio = librosa.effects.preemphasis(processed_audio)
                logger.debug("Applied volume normalization")
            
            # Silence removal
            if self.quality_settings["silence_removal"]:
                processed_audio, _ = librosa.effects.trim(
                    processed_audio, 
                    top_db=30,
                    frame_length=2048,
                    hop_length=512
                )
                logger.debug("Applied silence removal")
            
            # Save processed audio
            temp_dir = tempfile.mkdtemp()
            processed_path = os.path.join(temp_dir, "processed_audio.wav")
            
            # Convert to int16 for compatibility
            processed_audio_int16 = (processed_audio * 32767).astype(np.int16)
            wavfile.write(processed_path, sr, processed_audio_int16)
            
            logger.debug("Audio preprocessing completed", output_path=processed_path)
            return processed_path
            
        except Exception as e:
            logger.warning("Local audio preprocessing failed", error=str(e))
            return audio_path  # Return original on failure
    
    def _get_enhanced_transcribe_options(self, 
                                       language: str, 
                                       quality_level: str, 
                                       audio_path: str) -> Dict[str, Any]:
        """Get enhanced transcription options based on quality level and context"""
        
        # Base options optimized for quality
        options = {
            "language": language,
            "task": "transcribe",
            "temperature": 0.0,  # Deterministic
            "best_of": 5,
            "beam_size": 5,
            "patience": 1.0,
            "length_penalty": 1.0,
            "suppress_tokens": [-1],
            "condition_on_previous_text": True,
            "fp16": torch.cuda.is_available(),
            "compression_ratio_threshold": 2.4,
            "logprob_threshold": -1.0,
            "no_speech_threshold": 0.6
        }
        
        # Adjust based on quality level
        if quality_level == "fastest":
            options.update({
                "temperature": 0.2,
                "best_of": 1,
                "beam_size": 1,
                "condition_on_previous_text": False
            })
        elif quality_level == "balanced":
            options.update({
                "temperature": 0.1,
                "best_of": 3,
                "beam_size": 3
            })
        elif quality_level == "high":
            # Use the enhanced options as-is
            options.update({
                "temperature": 0.0,
                "best_of": 5,
                "beam_size": 5
            })
        
        # Language-specific optimizations
        # Use natural conversation starters instead of instructions to avoid hallucinations
        if language == "es":
            options["initial_prompt"] = (
                "Hola, bienvenidos. Muchas gracias por estar aquí. "
                "Vamos a comenzar con la reunión de hoy."
            )
        elif language == "en":
            options["initial_prompt"] = (
                "Hello and welcome. Thank you very much for being here. "
                "Let's get started with today's meeting."
            )
        
        # Audio duration-based optimization
        try:
            audio, sr = librosa.load(audio_path, sr=None)
            duration = len(audio) / sr
            
            if duration > 300:  # Long audio (5+ minutes)
                options.update({
                    "condition_on_previous_text": True,
                    "compression_ratio_threshold": 2.2  # More lenient for long audio
                })
        except:
            pass  # Use defaults if duration calculation fails
        
        return options
    
    def _post_process_local_result(self, 
                                 result: Dict[str, Any], 
                                 language: str, 
                                 project_name: str) -> Dict[str, Any]:
        """Enhanced post-processing for local transcription results"""
        try:
            text = result.get("text", "")
            segments = result.get("segments", [])
            
            # Calculate confidence from segments
            total_confidence = 0
            word_count = 0
            
            for segment in segments:
                # Whisper segments have avg_logprob which we can convert to confidence
                if "avg_logprob" in segment:
                    # Convert log probability to confidence (approximate)
                    confidence = np.exp(segment["avg_logprob"])
                    segment_words = len(segment["text"].split())
                    total_confidence += confidence * segment_words
                    word_count += segment_words
            
            avg_confidence = total_confidence / word_count if word_count > 0 else 0.0
            
            # Enhanced text cleaning
            cleaned_text = text
            if self.quality_settings["language_specific_cleaning"]:
                cleaned_text = self._clean_text_by_language(text, language)
            
            if self.quality_settings["post_processing"]:
                cleaned_text = self._apply_post_processing_rules(cleaned_text, language, project_name)
            
            # Calculate quality score
            quality_score = self._calculate_local_quality_score(result, avg_confidence)
            
            return {
                "text": cleaned_text,
                "original_text": text,
                "segments": segments,
                "language": result.get("language", language),
                "confidence": round(avg_confidence, 3),
                "quality_score": round(quality_score, 3),
                "word_count": len(cleaned_text.split()),
                "duration": segments[-1]["end"] if segments else 0,
                "processing_info": {
                    "model_used": self.local_model,
                    "preprocessing_applied": True,
                    "post_processing_applied": True,
                    "method": "local_enhanced"
                }
            }
            
        except Exception as e:
            logger.error("Local result post-processing failed", error=str(e))
            return result
    
    def _clean_text_by_language(self, text: str, language: str) -> str:
        """Language-specific text cleaning"""
        import re
        
        if language == "es":
            # Spanish-specific corrections
            replacements = {
                r'\bbuen días\b': 'buenos días',
                r'\bbuen tardes\b': 'buenas tardes', 
                r'\bbuen noches\b': 'buenas noches',
                r'\besta bien\b': 'está bien',
                r'\besta es\b': 'esta es',
                r'\basi es\b': 'así es',
                r'\bmuchisimas\b': 'muchísimas',
                r'\bmuchisimos\b': 'muchísimos',
                r'\bperfecto\b': 'perfecto',
                r'\bde nada\b': 'de nada',
                r'\bpor favor\b': 'por favor',
                r'\bgracias\b': 'gracias',
                r'\bdisculpe\b': 'disculpe',
                r'\bdisculpa\b': 'disculpa'
            }
            
            for pattern, replacement in replacements.items():
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        elif language == "en":
            # English-specific corrections
            replacements = {
                r'\bthru\b': 'through',
                r'\bur\b': 'your',
                r'\bu\b': 'you',
                r'\btho\b': 'though',
                r'\bwanna\b': 'want to',
                r'\bgonna\b': 'going to',
                r'\bhave got\b': 'have',
                r'\bkinda\b': 'kind of'
            }
            
            for pattern, replacement in replacements.items():
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        return text
    
    def _apply_post_processing_rules(self, text: str, language: str, project_name: str) -> str:
        """Apply context-aware post-processing rules"""
        import re
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Fix punctuation spacing
        text = re.sub(r'\s+([,.!?;:])', r'\1', text)
        text = re.sub(r'([.!?])\s*([a-záéíóúñüA-ZÁÉÍÓÚÑÜ])', r'\1 \2', text)
        
        # Capitalize after sentence endings
        sentences = re.split(r'([.!?]+)', text)
        processed_sentences = []
        
        for i, sentence in enumerate(sentences):
            if i % 2 == 0 and sentence.strip():  # Text parts (not punctuation)
                sentence = sentence.strip()
                if sentence:
                    sentence = sentence[0].upper() + sentence[1:]
                processed_sentences.append(sentence)
            else:
                processed_sentences.append(sentence)
        
        text = ''.join(processed_sentences)
        
        # Project-specific corrections
        project_lower = project_name.lower()
        if any(word in project_lower for word in ["meeting", "reunión", "junta"]):
            # Meeting-specific corrections
            text = re.sub(r'\baction item\b', 'acción pendiente', text, flags=re.IGNORECASE)
            text = re.sub(r'\bfollow up\b', 'seguimiento', text, flags=re.IGNORECASE)
        
        return text.strip()
    
    def _calculate_local_quality_score(self, result: Dict[str, Any], avg_confidence: float) -> float:
        """Calculate quality score for local transcription"""
        try:
            segments = result.get("segments", [])
            
            if not segments:
                return avg_confidence
            
            # Confidence component
            confidence_score = avg_confidence
            
            # Consistency metrics
            segment_lengths = [s["end"] - s["start"] for s in segments if "end" in s and "start" in s]
            
            # Speech rate consistency
            speech_rates = []
            for segment in segments:
                if "text" in segment and "end" in segment and "start" in segment:
                    duration = segment["end"] - segment["start"]
                    words = len(segment["text"].split())
                    if duration > 0:
                        speech_rates.append(words / duration)
            
            # Calculate consistency scores
            length_consistency = 1.0
            if len(segment_lengths) > 1:
                length_std = np.std(segment_lengths)
                length_consistency = max(0, 1 - length_std / 10)
            
            rate_consistency = 1.0
            if len(speech_rates) > 1:
                rate_std = np.std(speech_rates)
                rate_consistency = max(0, 1 - rate_std / 5)
            
            # Weighted quality score
            quality_score = (
                confidence_score * 0.6 +
                length_consistency * 0.2 +
                rate_consistency * 0.2
            )
            
            return min(1.0, max(0.0, quality_score))
            
        except Exception as e:
            logger.warning("Quality score calculation failed", error=str(e))
            return avg_confidence
    
    def _get_optimal_model_for_quality(self, quality_level: str) -> str:
        """Get optimal Whisper model based on quality requirements"""
        if quality_level == "fastest":
            return "base"
        elif quality_level == "balanced":
            return "small"
        elif quality_level == "high":
            return "large-v3"  # Highest quality
        else:
            return self.local_model
    
    def _basic_transcription_fallback(self, audio_path: str, language: str) -> Dict[str, Any]:
        """Basic transcription fallback when all enhanced methods fail"""
        try:
            logger.warning("Using basic transcription fallback")
            
            # Use the most basic Whisper setup
            if not self._local_whisper_model:
                self._local_whisper_model = whisper.load_model("base")
            
            result = self._local_whisper_model.transcribe(
                audio_path,
                language=language,
                task="transcribe"
            )
            
            return {
                "text": result.get("text", ""),
                "language": result.get("language", language),
                "confidence": 0.5,  # Conservative estimate
                "quality_score": 0.3,  # Low quality indicator
                "word_count": len(result.get("text", "").split()),
                "method_used": "basic_fallback",
                "processing_info": {
                    "model_used": "base",
                    "preprocessing_applied": False,
                    "post_processing_applied": False,
                    "method": "basic_fallback"
                }
            }
            
        except Exception as e:
            logger.error("Even basic transcription fallback failed", error=str(e))
            return {
                "error": str(e),
                "text": "",
                "confidence": 0.0,
                "quality_score": 0.0,
                "method_used": "failed"
            }

# Global enhanced transcription client
enhanced_transcriber = EnhancedTranscriptionClient()