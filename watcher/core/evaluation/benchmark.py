"""
Benchmark System - Sistema completo de evaluación de transcripciones
Permite comparar modelos, configuraciones y medir mejoras objetivamente
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import time

from .metrics import calculate_all_metrics, format_metrics_report

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkSample:
    """Muestra individual en el dataset de benchmark"""
    audio_path: str
    reference_text: str
    metadata: Dict[str, Any]
    sample_id: Optional[str] = None

    def __post_init__(self):
        if self.sample_id is None:
            self.sample_id = Path(self.audio_path).stem


@dataclass
class BenchmarkResult:
    """Resultado de evaluación de una muestra"""
    sample_id: str
    audio_path: str
    reference_text: str
    hypothesis_text: str
    wer: float
    cer: float
    mer: float
    metrics: Dict
    metadata: Dict
    transcription_time: float
    timestamp: str

    def to_dict(self):
        return asdict(self)


class TranscriptionBenchmark:
    """
    Sistema de benchmark para evaluar calidad de transcripciones

    Permite:
    - Cargar datasets de prueba (gold standard)
    - Ejecutar transcripciones con diferentes modelos/configuraciones
    - Calcular métricas (WER, CER, MER)
    - Comparar resultados entre modelos
    - Generar reportes detallados
    - Guardar histórico de resultados
    """

    def __init__(self, dataset_path: str, results_dir: str = None):
        """
        Args:
            dataset_path: Path al archivo JSON con el dataset de prueba
            results_dir: Directorio donde guardar resultados (default: ./benchmark_results)
        """
        self.dataset_path = dataset_path
        self.results_dir = results_dir or "./benchmark_results"
        self.samples: List[BenchmarkSample] = []

        # Crear directorio de resultados
        Path(self.results_dir).mkdir(parents=True, exist_ok=True)

        # Cargar dataset
        self._load_dataset()

    def _load_dataset(self):
        """Cargar dataset de prueba desde JSON"""
        try:
            with open(self.dataset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for item in data:
                sample = BenchmarkSample(
                    audio_path=item['audio_path'],
                    reference_text=item['reference_text'],
                    metadata=item.get('metadata', {}),
                    sample_id=item.get('sample_id')
                )
                self.samples.append(sample)

            logger.info(f"✓ Cargadas {len(self.samples)} muestras desde {self.dataset_path}")

        except FileNotFoundError:
            logger.error(f"✗ Dataset no encontrado: {self.dataset_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"✗ Error al parsear JSON: {e}")
            raise
        except KeyError as e:
            logger.error(f"✗ Campo requerido faltante en dataset: {e}")
            raise

    def evaluate_transcriber(
        self,
        transcriber_func,
        model_name: str,
        config: Optional[Dict] = None
    ) -> Dict:
        """
        Evaluar un transcriber en todo el dataset

        Args:
            transcriber_func: Función que recibe audio_path y retorna texto transcrito
            model_name: Nombre del modelo/configuración para identificar
            config: Configuración adicional del transcriber (opcional)

        Returns:
            Dict con resultados agregados y por muestra
        """
        logger.info(f"\n{'='*70}")
        logger.info(f"🚀 INICIANDO BENCHMARK: {model_name}")
        logger.info(f"{'='*70}")
        logger.info(f"  Dataset: {self.dataset_path}")
        logger.info(f"  Muestras: {len(self.samples)}")
        logger.info(f"  Configuración: {config or 'default'}")
        logger.info(f"{'='*70}\n")

        results = []
        total_start_time = time.time()

        for idx, sample in enumerate(self.samples, 1):
            logger.info(f"[{idx}/{len(self.samples)}] Procesando: {sample.sample_id}")

            try:
                # Transcribir
                start_time = time.time()
                hypothesis = transcriber_func(sample.audio_path)
                transcription_time = time.time() - start_time

                # Calcular métricas
                metrics = calculate_all_metrics(
                    sample.reference_text,
                    hypothesis,
                    normalize=True
                )

                # Crear resultado
                result = BenchmarkResult(
                    sample_id=sample.sample_id,
                    audio_path=sample.audio_path,
                    reference_text=sample.reference_text,
                    hypothesis_text=hypothesis,
                    wer=metrics['wer']['wer'],
                    cer=metrics['cer']['cer'],
                    mer=metrics['mer']['mer'],
                    metrics=metrics,
                    metadata=sample.metadata,
                    transcription_time=transcription_time,
                    timestamp=datetime.now().isoformat()
                )
                results.append(result)

                # Log progreso
                logger.info(f"  ✓ WER: {result.wer*100:.2f}% | CER: {result.cer*100:.2f}% | Tiempo: {transcription_time:.2f}s")

            except Exception as e:
                logger.error(f"  ✗ Error procesando {sample.sample_id}: {e}")
                continue

        total_time = time.time() - total_start_time

        # Calcular estadísticas agregadas
        aggregated = self._aggregate_results(results, model_name, config, total_time)

        # Guardar resultados
        self._save_results(model_name, aggregated, results)

        # Mostrar reporte
        self._print_summary(aggregated)

        return aggregated

    def _aggregate_results(
        self,
        results: List[BenchmarkResult],
        model_name: str,
        config: Optional[Dict],
        total_time: float
    ) -> Dict:
        """Calcular estadísticas agregadas"""
        if not results:
            return {
                'model_name': model_name,
                'config': config,
                'error': 'No se pudieron procesar muestras'
            }

        # Promedios generales
        avg_wer = sum(r.wer for r in results) / len(results)
        avg_cer = sum(r.cer for r in results) / len(results)
        avg_mer = sum(r.mer for r in results) / len(results)
        avg_time = sum(r.transcription_time for r in results) / len(results)

        # Promedios por categoría (si hay metadata)
        category_stats = {}
        categories = set()
        for r in results:
            if 'category' in r.metadata:
                categories.add(r.metadata['category'])

        for category in categories:
            cat_results = [r for r in results if r.metadata.get('category') == category]
            if cat_results:
                category_stats[category] = {
                    'count': len(cat_results),
                    'avg_wer': sum(r.wer for r in cat_results) / len(cat_results),
                    'avg_cer': sum(r.cer for r in cat_results) / len(cat_results),
                    'avg_mer': sum(r.mer for r in cat_results) / len(cat_results),
                }

        return {
            'model_name': model_name,
            'config': config,
            'timestamp': datetime.now().isoformat(),
            'dataset': self.dataset_path,
            'total_samples': len(self.samples),
            'processed_samples': len(results),
            'total_time': total_time,
            'avg_transcription_time': avg_time,
            'metrics': {
                'avg_wer': avg_wer,
                'avg_wer_percentage': avg_wer * 100,
                'avg_cer': avg_cer,
                'avg_cer_percentage': avg_cer * 100,
                'avg_mer': avg_mer,
                'avg_mer_percentage': avg_mer * 100,
            },
            'category_stats': category_stats,
            'best_sample': min(results, key=lambda r: r.wer).sample_id,
            'worst_sample': max(results, key=lambda r: r.wer).sample_id,
            'samples_below_5_wer': len([r for r in results if r.wer < 0.05]),
            'samples_below_10_wer': len([r for r in results if r.wer < 0.10]),
            'samples_above_25_wer': len([r for r in results if r.wer > 0.25]),
        }

    def _save_results(self, model_name: str, aggregated: Dict, results: List[BenchmarkResult]):
        """Guardar resultados en disco"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_model_name = model_name.replace('/', '_').replace(' ', '_')

        # Guardar resultados agregados
        aggregated_file = Path(self.results_dir) / f"{safe_model_name}_{timestamp}_summary.json"
        with open(aggregated_file, 'w', encoding='utf-8') as f:
            json.dump(aggregated, f, indent=2, ensure_ascii=False)

        # Guardar resultados detallados por muestra
        detailed_file = Path(self.results_dir) / f"{safe_model_name}_{timestamp}_detailed.json"
        with open(detailed_file, 'w', encoding='utf-8') as f:
            json.dump([r.to_dict() for r in results], f, indent=2, ensure_ascii=False)

        logger.info(f"\n✓ Resultados guardados:")
        logger.info(f"  - Resumen: {aggregated_file}")
        logger.info(f"  - Detallado: {detailed_file}")

    def _print_summary(self, aggregated: Dict):
        """Imprimir reporte resumen"""
        metrics = aggregated['metrics']

        print("\n" + "="*70)
        print(f"📊 REPORTE DE BENCHMARK: {aggregated['model_name']}")
        print("="*70)
        print(f"\n📁 Dataset: {aggregated['dataset']}")
        print(f"📈 Muestras procesadas: {aggregated['processed_samples']}/{aggregated['total_samples']}")
        print(f"⏱️  Tiempo total: {aggregated['total_time']:.2f}s")
        print(f"⚡ Tiempo promedio por muestra: {aggregated['avg_transcription_time']:.2f}s")

        print("\n" + "-"*70)
        print("📊 MÉTRICAS GENERALES")
        print("-"*70)
        print(f"  WER (Word Error Rate):        {metrics['avg_wer_percentage']:6.2f}%")
        print(f"  CER (Character Error Rate):   {metrics['avg_cer_percentage']:6.2f}%")
        print(f"  MER (Match Error Rate):       {metrics['avg_mer_percentage']:6.2f}%")

        print("\n" + "-"*70)
        print("📈 DISTRIBUCIÓN DE CALIDAD")
        print("-"*70)
        print(f"  Muestras con WER < 5%:  {aggregated['samples_below_5_wer']:3d}  ({aggregated['samples_below_5_wer']/aggregated['processed_samples']*100:.1f}%)")
        print(f"  Muestras con WER < 10%: {aggregated['samples_below_10_wer']:3d}  ({aggregated['samples_below_10_wer']/aggregated['processed_samples']*100:.1f}%)")
        print(f"  Muestras con WER > 25%: {aggregated['samples_above_25_wer']:3d}  ({aggregated['samples_above_25_wer']/aggregated['processed_samples']*100:.1f}%)")

        if aggregated.get('category_stats'):
            print("\n" + "-"*70)
            print("🏷️  MÉTRICAS POR CATEGORÍA")
            print("-"*70)
            for category, stats in aggregated['category_stats'].items():
                print(f"\n  {category.upper()} ({stats['count']} muestras):")
                print(f"    WER: {stats['avg_wer']*100:6.2f}%")
                print(f"    CER: {stats['avg_cer']*100:6.2f}%")

        print("\n" + "-"*70)
        print("🏆 EXTREMOS")
        print("-"*70)
        print(f"  Mejor muestra:  {aggregated['best_sample']}")
        print(f"  Peor muestra:   {aggregated['worst_sample']}")

        print("\n" + "="*70 + "\n")

    def compare_models(self, result_files: List[str]) -> Dict:
        """
        Comparar resultados de múltiples modelos

        Args:
            result_files: Lista de paths a archivos de resultados summary.json

        Returns:
            Dict con comparación
        """
        comparisons = []

        for file_path in result_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    comparisons.append(data)
            except Exception as e:
                logger.error(f"Error cargando {file_path}: {e}")
                continue

        if not comparisons:
            logger.error("No se pudieron cargar resultados para comparar")
            return {}

        # Ordenar por WER (mejor primero)
        comparisons.sort(key=lambda x: x['metrics']['avg_wer'])

        # Imprimir comparación
        print("\n" + "="*90)
        print("🔄 COMPARACIÓN DE MODELOS")
        print("="*90)
        print(f"{'Modelo':<30} {'WER':>10} {'CER':>10} {'MER':>10} {'Tiempo':>12}")
        print("-"*90)

        for comp in comparisons:
            model_name = comp['model_name'][:28]
            wer = comp['metrics']['avg_wer_percentage']
            cer = comp['metrics']['avg_cer_percentage']
            mer = comp['metrics']['avg_mer_percentage']
            time_avg = comp['avg_transcription_time']

            print(f"{model_name:<30} {wer:>9.2f}% {cer:>9.2f}% {mer:>9.2f}% {time_avg:>10.2f}s")

        print("="*90 + "\n")

        # Calcular mejora del mejor vs peor
        best = comparisons[0]
        worst = comparisons[-1]
        improvement = ((worst['metrics']['avg_wer'] - best['metrics']['avg_wer'])
                      / worst['metrics']['avg_wer'] * 100)

        print(f"💡 El mejor modelo ({best['model_name']}) es {improvement:.1f}% mejor que el peor")
        print(f"   WER: {best['metrics']['avg_wer_percentage']:.2f}% vs {worst['metrics']['avg_wer_percentage']:.2f}%\n")

        return {
            'comparisons': comparisons,
            'best_model': best['model_name'],
            'worst_model': worst['model_name'],
            'improvement_percentage': improvement
        }


def create_sample_dataset(output_path: str):
    """
    Crear un dataset de ejemplo para empezar a hacer benchmarks

    Args:
        output_path: Path donde guardar el dataset JSON
    """
    sample_dataset = [
        {
            "sample_id": "sample_001",
            "audio_path": "./benchmark_audios/sample_001.wav",
            "reference_text": "Esta es una prueba de transcripción en español con calidad excelente.",
            "metadata": {
                "category": "clean",
                "duration": 5.2,
                "language": "es",
                "accent": "neutral"
            }
        },
        {
            "sample_id": "sample_002",
            "audio_path": "./benchmark_audios/sample_002.wav",
            "reference_text": "El reconocimiento de voz ha mejorado significativamente en los últimos años.",
            "metadata": {
                "category": "clean",
                "duration": 6.8,
                "language": "es",
                "accent": "neutral"
            }
        },
        {
            "sample_id": "sample_003",
            "audio_path": "./benchmark_audios/sample_003.wav",
            "reference_text": "Este audio tiene ruido de fondo moderado para probar robustez.",
            "metadata": {
                "category": "noisy",
                "duration": 5.5,
                "language": "es",
                "accent": "neutral",
                "noise_level": "medium"
            }
        }
    ]

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(sample_dataset, f, indent=2, ensure_ascii=False)

    print(f"✓ Dataset de ejemplo creado en: {output_path}")
    print(f"  Contiene {len(sample_dataset)} muestras")
    print(f"\n⚠️  IMPORTANTE: Debes crear los archivos de audio correspondientes en ./benchmark_audios/")
    print(f"  y actualizar reference_text con transcripciones manuales precisas.\n")
