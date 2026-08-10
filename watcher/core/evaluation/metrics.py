"""
Metrics Module - Cálculo de métricas de calidad de transcripción
WER (Word Error Rate), CER (Character Error Rate), MER (Match Error Rate)
"""

import re
from typing import List, Tuple, Dict
import logging

logger = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    """
    Normalizar texto para comparación justa
    - Lowercase
    - Remover puntuación
    - Normalizar espacios
    """
    # Convertir a minúsculas
    text = text.lower()

    # Remover puntuación (mantener solo letras, números y espacios)
    text = re.sub(r'[^\w\s]', '', text)

    # Normalizar espacios múltiples
    text = re.sub(r'\s+', ' ', text)

    # Trim
    text = text.strip()

    return text


def levenshtein_distance(ref: List[str], hyp: List[str]) -> Tuple[int, int, int, int]:
    """
    Calcular distancia de Levenshtein entre dos secuencias
    Retorna: (distancia, substituciones, inserciones, eliminaciones)
    """
    m, n = len(ref), len(hyp)

    # Matriz de distancias
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    # Inicializar primera fila y columna
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    # Llenar matriz
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref[i - 1] == hyp[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(
                    dp[i - 1][j],      # Eliminación
                    dp[i][j - 1],      # Inserción
                    dp[i - 1][j - 1]   # Substitución
                )

    # Backtrack para contar operaciones
    i, j = m, n
    subs, ins, dels = 0, 0, 0

    while i > 0 or j > 0:
        if i == 0:
            ins += 1
            j -= 1
        elif j == 0:
            dels += 1
            i -= 1
        elif ref[i - 1] == hyp[j - 1]:
            i -= 1
            j -= 1
        else:
            # Encontrar operación mínima
            min_cost = min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])

            if dp[i - 1][j - 1] == min_cost:
                subs += 1
                i -= 1
                j -= 1
            elif dp[i][j - 1] == min_cost:
                ins += 1
                j -= 1
            else:
                dels += 1
                i -= 1

    distance = dp[m][n]
    return distance, subs, ins, dels


def calculate_wer(reference: str, hypothesis: str, normalize: bool = True) -> Dict:
    """
    Calcular Word Error Rate (WER)

    WER = (S + D + I) / N
    donde:
    - S = substituciones
    - D = eliminaciones
    - I = inserciones
    - N = número de palabras en referencia

    Args:
        reference: Texto de referencia (ground truth)
        hypothesis: Texto transcrito por el modelo
        normalize: Si True, normaliza textos antes de comparar

    Returns:
        Dict con WER y métricas detalladas
    """
    # Normalizar si es necesario
    if normalize:
        reference = normalize_text(reference)
        hypothesis = normalize_text(hypothesis)

    # Dividir en palabras
    ref_words = reference.split()
    hyp_words = hypothesis.split()

    # Calcular distancia de Levenshtein
    distance, subs, ins, dels = levenshtein_distance(ref_words, hyp_words)

    # Calcular WER
    n_ref = len(ref_words)
    if n_ref == 0:
        wer = 0.0 if len(hyp_words) == 0 else float('inf')
    else:
        wer = distance / n_ref

    return {
        'wer': wer,
        'wer_percentage': wer * 100,
        'distance': distance,
        'substitutions': subs,
        'insertions': ins,
        'deletions': dels,
        'ref_words': n_ref,
        'hyp_words': len(hyp_words),
        'correct_words': n_ref - (subs + dels),
    }


def calculate_cer(reference: str, hypothesis: str, normalize: bool = True) -> Dict:
    """
    Calcular Character Error Rate (CER)

    Similar a WER pero a nivel de caracteres
    Útil para evaluar idiomas sin separadores de palabras claros

    Args:
        reference: Texto de referencia (ground truth)
        hypothesis: Texto transcrito por el modelo
        normalize: Si True, normaliza textos antes de comparar

    Returns:
        Dict con CER y métricas detalladas
    """
    # Normalizar si es necesario
    if normalize:
        reference = normalize_text(reference)
        hypothesis = normalize_text(hypothesis)

    # Convertir a listas de caracteres
    ref_chars = list(reference)
    hyp_chars = list(hypothesis)

    # Calcular distancia de Levenshtein
    distance, subs, ins, dels = levenshtein_distance(ref_chars, hyp_chars)

    # Calcular CER
    n_ref = len(ref_chars)
    if n_ref == 0:
        cer = 0.0 if len(hyp_chars) == 0 else float('inf')
    else:
        cer = distance / n_ref

    return {
        'cer': cer,
        'cer_percentage': cer * 100,
        'distance': distance,
        'substitutions': subs,
        'insertions': ins,
        'deletions': dels,
        'ref_chars': n_ref,
        'hyp_chars': len(hyp_chars),
        'correct_chars': n_ref - (subs + dels),
    }


def calculate_mer(reference: str, hypothesis: str, normalize: bool = True) -> Dict:
    """
    Calcular Match Error Rate (MER)

    MER = (S + D + I) / (S + D + C)
    donde C = palabras correctas

    MER es más sensible a errores que WER

    Args:
        reference: Texto de referencia (ground truth)
        hypothesis: Texto transcrito por el modelo
        normalize: Si True, normaliza textos antes de comparar

    Returns:
        Dict con MER y métricas detalladas
    """
    wer_result = calculate_wer(reference, hypothesis, normalize)

    subs = wer_result['substitutions']
    dels = wer_result['deletions']
    ins = wer_result['insertions']
    correct = wer_result['correct_words']

    # Calcular MER
    denominator = subs + dels + correct
    if denominator == 0:
        mer = 0.0
    else:
        mer = (subs + dels + ins) / denominator

    return {
        'mer': mer,
        'mer_percentage': mer * 100,
        'substitutions': subs,
        'insertions': ins,
        'deletions': dels,
        'correct_words': correct,
    }


def calculate_all_metrics(reference: str, hypothesis: str, normalize: bool = True) -> Dict:
    """
    Calcular todas las métricas en una sola llamada

    Args:
        reference: Texto de referencia (ground truth)
        hypothesis: Texto transcrito por el modelo
        normalize: Si True, normaliza textos antes de comparar

    Returns:
        Dict con WER, CER y MER
    """
    wer_result = calculate_wer(reference, hypothesis, normalize)
    cer_result = calculate_cer(reference, hypothesis, normalize)
    mer_result = calculate_mer(reference, hypothesis, normalize)

    return {
        'wer': wer_result,
        'cer': cer_result,
        'mer': mer_result,
        'summary': {
            'wer_percentage': f"{wer_result['wer_percentage']:.2f}%",
            'cer_percentage': f"{cer_result['cer_percentage']:.2f}%",
            'mer_percentage': f"{mer_result['mer_percentage']:.2f}%",
        }
    }


def format_metrics_report(metrics: Dict) -> str:
    """
    Formatear métricas en reporte legible

    Args:
        metrics: Dict retornado por calculate_all_metrics

    Returns:
        String formateado con el reporte
    """
    wer = metrics['wer']
    cer = metrics['cer']
    mer = metrics['mer']

    report = f"""
==================================================================
            REPORTE DE METRICAS DE TRANSCRIPCION
==================================================================

RESUMEN EJECUTIVO
------------------------------------------------------------------
  * WER (Word Error Rate):    {wer['wer_percentage']:6.2f}%
  * CER (Character Error Rate): {cer['cer_percentage']:6.2f}%
  * MER (Match Error Rate):     {mer['mer_percentage']:6.2f}%

ANALISIS DE PALABRAS
------------------------------------------------------------------
  Palabras en referencia:      {wer['ref_words']:5d}
  Palabras en hipotesis:        {wer['hyp_words']:5d}
  Palabras correctas:           {wer['correct_words']:5d}

  Errores:
    - Substituciones:           {wer['substitutions']:5d}
    - Inserciones:              {wer['insertions']:5d}
    - Eliminaciones:            {wer['deletions']:5d}
    ----------------------------------
    Total errores:              {wer['distance']:5d}

ANALISIS DE CARACTERES
------------------------------------------------------------------
  Caracteres en referencia:    {cer['ref_chars']:5d}
  Caracteres en hipotesis:      {cer['hyp_chars']:5d}
  Caracteres correctos:         {cer['correct_chars']:5d}
  Total errores:                {cer['distance']:5d}

INTERPRETACION
------------------------------------------------------------------
"""

    # Interpretación basada en WER
    if wer['wer_percentage'] < 5:
        interpretation = "  ***** Excelente - Calidad profesional"
    elif wer['wer_percentage'] < 10:
        interpretation = "  ****  Muy bueno - Pocas correcciones necesarias"
    elif wer['wer_percentage'] < 15:
        interpretation = "  ***   Bueno - Algunas correcciones necesarias"
    elif wer['wer_percentage'] < 25:
        interpretation = "  **    Regular - Requiere revision"
    else:
        interpretation = "  *     Bajo - Requiere mejoras significativas"

    report += interpretation + "\n"
    report += "==================================================================\n"

    return report
