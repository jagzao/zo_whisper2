#!/usr/bin/env python3
"""
Simple Speaker Diarization System
Identifies different speakers in audio without heavy ML models
Uses WebRTC VAD + spectral features for CPU-friendly diarization
"""

import logging
import numpy as np
from typing import List, Dict, Tuple, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import WebRTC VAD
try:
    import webrtcvad
    WEBRTC_AVAILABLE = True
except ImportError:
    WEBRTC_AVAILABLE = False
    logger.warning("webrtcvad not available, using fallback VAD")

# Try to import librosa for audio processing
try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False
    logger.error("librosa required for diarization")


class SimpleSpeakerDiarizer:
    """
    Lightweight speaker diarization using:
    - VAD (Voice Activity Detection) to find speech segments
    - Spectral features (pitch, energy, MFCCs) to cluster speakers
    - Simple k-means clustering to group similar voices
    """

    def __init__(
        self,
        num_speakers: int = 2,
        vad_aggressiveness: int = 3,
        min_speaker_time: float = 1.0,
        similarity_threshold: float = 0.6
    ):
        """
        Initialize diarizer

        Args:
            num_speakers: Expected number of speakers (or 'auto' for automatic detection)
            vad_aggressiveness: VAD sensitivity (0-3, higher = more aggressive)
            min_speaker_time: Minimum time for a speaker segment (seconds)
            similarity_threshold: Threshold for speaker similarity (0-1)
        """
        self.num_speakers = num_speakers
        self.vad_aggressiveness = vad_aggressiveness
        self.min_speaker_time = min_speaker_time
        self.similarity_threshold = similarity_threshold

        if not LIBROSA_AVAILABLE:
            raise ImportError("librosa is required for speaker diarization")

        logger.info(f"Speaker Diarizer initialized (expected speakers: {num_speakers})")

    def detect_voice_segments(self, audio: np.ndarray, sr: int) -> List[Tuple[float, float]]:
        """
        Detect voice activity segments using WebRTC VAD

        Args:
            audio: Audio signal
            sr: Sample rate

        Returns:
            List of (start_time, end_time) tuples for voice segments
        """
        try:
            if WEBRTC_AVAILABLE:
                return self._webrtc_vad(audio, sr)
            else:
                return self._simple_vad(audio, sr)
        except Exception as e:
            logger.error(f"VAD failed: {e}, using whole audio as single segment")
            duration = len(audio) / sr
            return [(0.0, duration)]

    def _webrtc_vad(self, audio: np.ndarray, sr: int) -> List[Tuple[float, float]]:
        """WebRTC VAD implementation"""
        try:
            # Resample to 16kHz (required by WebRTC VAD)
            if sr != 16000:
                audio_16k = librosa.resample(audio, orig_sr=sr, target_sr=16000)
                sr = 16000
            else:
                audio_16k = audio

            # Convert to int16
            audio_int16 = (audio_16k * 32768).astype(np.int16)

            # Create VAD
            vad = webrtcvad.Vad(self.vad_aggressiveness)

            # Process in 30ms frames
            frame_duration = 30  # ms
            frame_length = int(sr * frame_duration / 1000)

            segments = []
            in_speech = False
            speech_start = 0

            for i in range(0, len(audio_int16) - frame_length, frame_length):
                frame = audio_int16[i:i + frame_length].tobytes()

                try:
                    is_speech = vad.is_speech(frame, sr)

                    if is_speech and not in_speech:
                        # Speech started
                        speech_start = i / sr
                        in_speech = True
                    elif not is_speech and in_speech:
                        # Speech ended
                        speech_end = i / sr
                        if speech_end - speech_start >= self.min_speaker_time:
                            segments.append((speech_start, speech_end))
                        in_speech = False
                except Exception as e:
                    # Frame processing failed, skip
                    continue

            # Close final segment if still in speech
            if in_speech:
                segments.append((speech_start, len(audio_int16) / sr))

            logger.info(f"WebRTC VAD detected {len(segments)} voice segments")
            return segments

        except Exception as e:
            logger.warning(f"WebRTC VAD failed: {e}, using simple VAD")
            return self._simple_vad(audio, sr)

    def _simple_vad(self, audio: np.ndarray, sr: int) -> List[Tuple[float, float]]:
        """Simple energy-based VAD fallback"""
        try:
            # Compute short-time energy
            hop_length = int(sr * 0.01)  # 10ms hops
            energy = librosa.feature.rms(y=audio, hop_length=hop_length)[0]

            # Threshold: mean + 0.5 * std
            threshold = np.mean(energy) + 0.5 * np.std(energy)

            # Find voice segments
            is_voice = energy > threshold
            segments = []
            in_segment = False
            segment_start = 0

            for i, voice in enumerate(is_voice):
                time = i * hop_length / sr

                if voice and not in_segment:
                    segment_start = time
                    in_segment = True
                elif not voice and in_segment:
                    if time - segment_start >= self.min_speaker_time:
                        segments.append((segment_start, time))
                    in_segment = False

            if in_segment:
                segments.append((segment_start, len(audio) / sr))

            logger.info(f"Simple VAD detected {len(segments)} voice segments")
            return segments

        except Exception as e:
            logger.error(f"Simple VAD failed: {e}")
            return [(0.0, len(audio) / sr)]

    def extract_speaker_features(self, audio: np.ndarray, sr: int, start: float, end: float) -> np.ndarray:
        """
        Extract spectral features for a segment to characterize speaker

        Features:
        - Pitch (F0) statistics
        - MFCC coefficients
        - Spectral centroid
        - Zero crossing rate

        Args:
            audio: Full audio signal
            sr: Sample rate
            start: Segment start time
            end: Segment end time

        Returns:
            Feature vector
        """
        try:
            # Extract segment
            start_sample = int(start * sr)
            end_sample = int(end * sr)
            segment = audio[start_sample:end_sample]

            if len(segment) == 0:
                return np.zeros(17)  # Return zero vector for empty segments

            features = []

            # 1. Pitch (F0) features
            try:
                pitches, magnitudes = librosa.piptrack(y=segment, sr=sr)
                pitch_values = pitches[pitches > 0]

                if len(pitch_values) > 0:
                    features.extend([
                        np.mean(pitch_values),     # Mean pitch
                        np.std(pitch_values),      # Pitch variation
                        np.min(pitch_values),      # Min pitch
                        np.max(pitch_values)       # Max pitch
                    ])
                else:
                    features.extend([0, 0, 0, 0])
            except:
                features.extend([0, 0, 0, 0])

            # 2. MFCCs (first 10 coefficients)
            try:
                mfccs = librosa.feature.mfcc(y=segment, sr=sr, n_mfcc=10)
                mfcc_mean = np.mean(mfccs, axis=1)
                features.extend(mfcc_mean.tolist())
            except:
                features.extend([0] * 10)

            # 3. Spectral centroid
            try:
                centroid = librosa.feature.spectral_centroid(y=segment, sr=sr)
                features.append(np.mean(centroid))
            except:
                features.append(0)

            # 4. Zero crossing rate
            try:
                zcr = librosa.feature.zero_crossing_rate(segment)
                features.append(np.mean(zcr))
            except:
                features.append(0)

            # 5. RMS energy
            try:
                rms = librosa.feature.rms(y=segment)
                features.append(np.mean(rms))
            except:
                features.append(0)

            return np.array(features)

        except Exception as e:
            logger.warning(f"Feature extraction failed for segment {start}-{end}: {e}")
            return np.zeros(17)

    def cluster_speakers(self, features: List[np.ndarray]) -> List[int]:
        """
        Cluster feature vectors into speakers using simple k-means

        Args:
            features: List of feature vectors

        Returns:
            List of speaker labels (0, 1, 2, ...)
        """
        try:
            from sklearn.cluster import KMeans
            from sklearn.preprocessing import StandardScaler

            if len(features) == 0:
                return []

            # Standardize features
            scaler = StandardScaler()
            features_scaled = scaler.fit_transform(features)

            # Determine optimal number of clusters if auto
            if self.num_speakers == 'auto':
                # Use elbow method or default to 2
                max_speakers = min(5, len(features))
                # Simple heuristic: use 2 speakers if unsure
                n_clusters = 2
            else:
                n_clusters = min(self.num_speakers, len(features))

            # K-means clustering
            kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            labels = kmeans.fit_predict(features_scaled)

            logger.info(f"Clustered into {len(set(labels))} speaker groups")
            return labels.tolist()

        except ImportError:
            logger.warning("sklearn not available, assigning alternating speakers")
            # Fallback: alternate between speakers
            return [i % self.num_speakers for i in range(len(features))]
        except Exception as e:
            logger.error(f"Clustering failed: {e}, assigning single speaker")
            return [0] * len(features)

    def diarize(self, audio_path: str) -> List[Dict]:
        """
        Perform speaker diarization on audio file

        Args:
            audio_path: Path to audio file

        Returns:
            List of dicts with {speaker_id, start, end, duration}
        """
        try:
            logger.info(f"Starting diarization for {audio_path}")

            # Load audio
            audio, sr = librosa.load(audio_path, sr=16000, mono=True)
            total_duration = len(audio) / sr

            logger.info(f"Audio loaded: {total_duration:.1f}s @ {sr}Hz")

            # Detect voice segments
            voice_segments = self.detect_voice_segments(audio, sr)

            if len(voice_segments) == 0:
                logger.warning("No voice segments detected")
                return [{
                    "speaker_id": 0,
                    "start": 0.0,
                    "end": total_duration,
                    "duration": total_duration
                }]

            logger.info(f"Detected {len(voice_segments)} voice segments")

            # Extract features for each segment
            features = []
            for start, end in voice_segments:
                feature_vec = self.extract_speaker_features(audio, sr, start, end)
                features.append(feature_vec)

            # Cluster into speakers
            speaker_labels = self.cluster_speakers(features)

            # Build result
            diarization_result = []
            for (start, end), speaker_id in zip(voice_segments, speaker_labels):
                diarization_result.append({
                    "speaker_id": int(speaker_id),
                    "start": round(start, 2),
                    "end": round(end, 2),
                    "duration": round(end - start, 2)
                })

            logger.info(f"Diarization completed: {len(set(speaker_labels))} speakers identified")

            return diarization_result

        except Exception as e:
            logger.error(f"Diarization failed: {e}, returning single speaker")
            # Fallback: return whole audio as single speaker
            try:
                audio, sr = librosa.load(audio_path, sr=None, duration=1)
                audio_full, sr = librosa.load(audio_path, sr=None)
                duration = len(audio_full) / sr
            except:
                duration = 0

            return [{
                "speaker_id": 0,
                "start": 0.0,
                "end": duration,
                "duration": duration
            }]


def merge_diarization_with_transcription(
    transcription_segments: List[Dict],
    diarization_segments: List[Dict]
) -> List[Dict]:
    """
    Merge diarization results with transcription segments

    Args:
        transcription_segments: Segments from Whisper transcription
        diarization_segments: Speaker segments from diarization

    Returns:
        Merged segments with speaker_id added to each transcription segment
    """
    try:
        merged = []

        for trans_seg in transcription_segments:
            trans_start = trans_seg.get("start", 0)
            trans_end = trans_seg.get("end", 0)
            trans_mid = (trans_start + trans_end) / 2

            # Find which speaker segment this belongs to
            speaker_id = 0  # Default
            for diar_seg in diarization_segments:
                if diar_seg["start"] <= trans_mid <= diar_seg["end"]:
                    speaker_id = diar_seg["speaker_id"]
                    break

            # Add speaker_id to transcription segment
            merged_seg = trans_seg.copy()
            merged_seg["speaker_id"] = speaker_id
            merged.append(merged_seg)

        return merged

    except Exception as e:
        logger.error(f"Failed to merge diarization with transcription: {e}")
        # Return original segments without speaker info
        return transcription_segments


if __name__ == "__main__":
    # Test diarization
    import sys

    if len(sys.argv) > 1:
        audio_file = sys.argv[1]
        diarizer = SimpleSpeakerDiarizer(num_speakers=2)
        results = diarizer.diarize(audio_file)

        print("\n=== DIARIZATION RESULTS ===")
        for seg in results:
            print(f"Speaker {seg['speaker_id']}: {seg['start']:.2f}s - {seg['end']:.2f}s ({seg['duration']:.2f}s)")
    else:
        print("Usage: python speaker_diarization.py <audio_file>")
