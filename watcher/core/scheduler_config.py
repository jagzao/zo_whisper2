#!/usr/bin/env python3
"""
Scheduler Configuration - Gestión de horarios para procesamiento
"""

from datetime import time
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURACIÓN DE HORARIOS
# ============================================================================

class SchedulerConfig:
    """Configuración de horarios para procesamiento de transcripciones"""

    # Horario laboral (máquina debe trabajar fluida)
    WORK_START = time(7, 0)   # 7:00 AM
    WORK_END = time(23, 0)     # 11:00 PM

    # Horario nocturno (procesamiento intensivo)
    NIGHT_START = time(23, 0)  # 11:00 PM
    NIGHT_END = time(7, 0)     # 7:00 AM

    # Configuración de workers según horario
    WORK_HOURS_CONFIG = {
        "max_concurrent_jobs": 1,  # Solo 1 archivo a la vez durante el día
        "cpu_priority": "low",      # Prioridad baja para no afectar otras tareas
        "model_size": "large-v2",   # Mejor calidad real que v3 (menos alucinaciones)
        "enable_parallel": False    # Sin procesamiento paralelo
    }

    NIGHT_HOURS_CONFIG = {
        "max_concurrent_jobs": 2,   # 2-3 archivos simultáneos en la madrugada
        "cpu_priority": "normal",   # Prioridad normal
        "model_size": "large-v2",   # Mejor calidad real (v3 alucina 4x más en español)
        "enable_parallel": True     # Procesamiento paralelo activado
    }

    @classmethod
    def is_work_hours(cls, current_time=None) -> bool:
        """
        Verificar si estamos en horario laboral

        Args:
            current_time: time object, default: now()

        Returns:
            True si es horario laboral (7am-11pm)
        """
        if current_time is None:
            from datetime import datetime
            current_time = datetime.now().time()

        # Horario laboral: 7am - 11pm
        if cls.WORK_START <= current_time < cls.WORK_END:
            return True
        return False

    @classmethod
    def is_night_hours(cls, current_time=None) -> bool:
        """
        Verificar si estamos en horario nocturno

        Args:
            current_time: time object, default: now()

        Returns:
            True si es horario nocturno (11pm-7am)
        """
        return not cls.is_work_hours(current_time)

    @classmethod
    def get_current_config(cls, current_time=None) -> dict:
        """
        Obtener configuración actual según la hora

        Args:
            current_time: time object, default: now()

        Returns:
            Diccionario con configuración actual
        """
        if cls.is_work_hours(current_time):
            config = cls.WORK_HOURS_CONFIG.copy()
            config["period"] = "work_hours"
            config["description"] = "Horario laboral (7am-11pm): 1 archivo, baja prioridad"
        else:
            config = cls.NIGHT_HOURS_CONFIG.copy()
            config["period"] = "night_hours"
            config["description"] = "Horario nocturno (11pm-7am): Procesamiento paralelo"

        return config

    @classmethod
    def log_current_schedule(cls):
        """Log de configuración actual"""
        from datetime import datetime
        current_time = datetime.now().time()
        config = cls.get_current_config(current_time)

        logger.info("=" * 60)
        logger.info("⏰ CONFIGURACIÓN DE HORARIO")
        logger.info("=" * 60)
        logger.info(f"Hora actual: {current_time.strftime('%H:%M:%S')}")
        logger.info(f"Período: {config['description']}")
        logger.info(f"Archivos simultáneos: {config['max_concurrent_jobs']}")
        logger.info(f"Prioridad CPU: {config['cpu_priority']}")
        logger.info(f"Procesamiento paralelo: {'✅' if config['enable_parallel'] else '❌'}")
        logger.info("=" * 60)

    @classmethod
    def should_process_parallel(cls, current_time=None) -> bool:
        """
        Determinar si se debe hacer procesamiento paralelo

        Returns:
            True si es horario nocturno y se permite paralelo
        """
        config = cls.get_current_config(current_time)
        return config.get("enable_parallel", False)

    @classmethod
    def get_max_concurrent_jobs(cls, current_time=None) -> int:
        """
        Obtener número máximo de jobs concurrentes según horario

        Returns:
            Número de jobs concurrentes permitidos
        """
        config = cls.get_current_config(current_time)
        return config.get("max_concurrent_jobs", 1)

# ============================================================================
# SCHEDULE MANAGER
# ============================================================================

class ScheduleManager:
    """Gestor de horarios para ajustar configuración dinámicamente"""

    def __init__(self):
        self.current_config = None
        self.last_check_hour = None
        self._update_config()

    def _update_config(self):
        """Actualizar configuración según hora actual"""
        from datetime import datetime
        current_time = datetime.now()
        current_hour = current_time.hour

        # Solo actualizar si cambió la hora
        if self.last_check_hour != current_hour:
            self.current_config = SchedulerConfig.get_current_config()
            self.last_check_hour = current_hour

            logger.info(f"📅 Configuración actualizada: {self.current_config['description']}")

    def get_config(self) -> dict:
        """Obtener configuración actual"""
        self._update_config()
        return self.current_config

    def can_process_parallel(self) -> bool:
        """Verificar si se puede procesar en paralelo"""
        config = self.get_config()
        return config.get("enable_parallel", False)

    def get_max_workers(self) -> int:
        """Obtener número máximo de workers"""
        config = self.get_config()
        return config.get("max_concurrent_jobs", 1)

# Instancia global del scheduler
schedule_manager = ScheduleManager()

if __name__ == "__main__":
    # Test
    import logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("\n=== TEST: Scheduler Configuration ===\n")

    # Test diferentes horas
    test_times = [
        time(6, 30),   # Antes del trabajo
        time(9, 0),    # Durante trabajo
        time(15, 0),   # Durante trabajo
        time(23, 30),  # Noche
        time(3, 0),    # Madrugada
    ]

    for test_time in test_times:
        print(f"\n--- Hora: {test_time.strftime('%H:%M')} ---")
        config = SchedulerConfig.get_current_config(test_time)
        print(f"Período: {config['description']}")
        print(f"Workers: {config['max_concurrent_jobs']}")
        print(f"Paralelo: {config['enable_parallel']}")

    print("\n\n=== Configuración Actual ===")
    SchedulerConfig.log_current_schedule()
