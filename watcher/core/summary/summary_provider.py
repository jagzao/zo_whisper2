import os
import openai
import requests

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")  # o http://ollama:11434 en contenedor

def get_content_type(text, video_file_path):
    """Detecta el tipo de contenido basado en el texto y ruta del archivo"""
    text_lower = text.lower()
    file_path_lower = video_file_path.lower()
    
    # Detectar si es una entrevista por carpeta
    if "/entrevista/" in file_path_lower or "\\entrevista\\" in file_path_lower or "entrevista" in text_lower:
        return "entrevista"
    
    # Detectar si es contenido de estudio por carpeta o contenido
    if ("/study/" in file_path_lower or "/linkedin/" in file_path_lower or 
        "\\study\\" in file_path_lower or "\\linkedin\\" in file_path_lower or
        "study" in text_lower or "estudio" in text_lower or "tutorial" in text_lower or "clase" in text_lower):
        return "study"
    
    # Detectar si es un rediseño
    if "rediseño" in text_lower:
        return "redesign"
    
    # Por defecto, asumir que es una reunión
    return "default"

REDESIGN_PROMPT = lambda text, project_name, company_name, video_file: f"""
Analiza la siguiente transcripción sobre el rediseño de un aplicativo y extrae los puntos clave según la siguiente estructura:

1.  **Cliente Ideal:**
    *   **Perfil:** ¿Quién es el cliente ideal? (Demografía, rol, etc.)
    *   **Problemas y Desafíos:** ¿Qué problemas específicos del cliente resuelve el servicio?
    *   **Deseos y Aspiraciones:** ¿Cuáles son las metas que el cliente quiere alcanzar?
    *   **Objeciones y Miedos:** ¿Qué podría impedirle al cliente contratar el servicio?

2.  **Propuesta de Valor:**
    *   **Valor Diferencial:** ¿Qué hace único a este servicio frente a la competencia?
    *   **Beneficios Clave:** ¿Cuáles son los resultados tangibles que ofrece? (Ej: "Duplicar leads en 3 meses").
    *   **Mensaje Principal:** ¿Cuál es la idea central que se debe comunicar en los primeros segundos?

3.  **Contenido y Persuasión:**
    *   **Titulares Sugeridos:** Ideas para titulares que capturen la atención.
    *   **Descripción de Servicios:** ¿Cómo se explican los servicios y cómo benefician al cliente?
    *   **Pruebas y Ejemplos:** ¿Se mencionan casos de estudio o resultados cuantificables?
    *   **Preguntas Frecuentes (FAQ):** ¿Qué dudas se anticipan y cómo se resuelven?

4.  **Prueba Social:**
    *   **Testimonios:** ¿Se mencionan testimonios de clientes? ¿Qué destacan?
    *   **Logos y Reconocimientos:** ¿Hay mención de clientes importantes o premios?

5.  **Diseño y Experiencia de Usuario (UX):**
    *   **Estilo Visual:** ¿Se define un diseño (limpio, moderno, etc.)?
    *   **Navegación:** ¿Cómo debe ser la estructura y facilidad de uso del sitio?
    *   **Móvil y Velocidad:** ¿Se menciona la importancia de la adaptación a móviles y la velocidad de carga?
    *   **Recursos Gráficos:** ¿Se habla del uso de imágenes o videos?

6.  **Llamadas a la Acción (CTAs):**
    *   **CTAs Principales:** ¿Cuáles son las acciones que se quiere que el usuario realice? (Ej: "Solicitar consulta", "Ver portafolio").
    *   **Ubicación:** ¿Dónde deberían colocarse estos CTAs?

7.  **Optimización para Motores de Búsqueda (SEO):**
    *   **Palabras Clave:** ¿Se identifican términos de búsqueda relevantes?
    *   **Estrategia de Contenido:** ¿Se planea crear contenido adicional como blogs para atraer tráfico?

8.  **Facilidad de Contacto:**
    *   **Métodos de Contacto:** ¿Qué canales se mencionan para contactar? (Formularios, email, chat).

9.  **Medición y Mejora:**
    *   **Herramientas:** ¿Se mencionan herramientas como Google Analytics?
    *   **Métricas Clave:** ¿Qué se va a medir (conversiones, leads, etc.)?
    *   **Feedback:** ¿Se planea solicitar retroalimentación de los usuarios?

Contexto:
- Proyecto: {project_name}
- Compañía: {company_name}
- Archivo: {video_file}

Transcripción de la reunión:
{text}
"""

ENTREVISTA_PROMPT = lambda text, project_name, company_name, video_file: f"""
realiza un análisis integral de la entrevista, abordando los siguientes puntos:
Evaluación General del Desempeño:
¿Cuál fue mi desempeño general en la entrevista? (Bueno, regular, sobresaliente, etc.) Justifica tu respuesta.
¿Qué tan bien logré comunicar mis habilidades y experiencia relevantes para el puesto?
¿Mis respuestas se alinearon con lo que un entrevistador probablemente buscaría en este rol específico?

Análisis por Pregunta Clave:
Para cada pregunta importante que proporcioné, evalúa la efectividad de mi respuesta.
¿Hubo alguna pregunta donde mi respuesta pudo haber sido mejorada (en contenido, estructura, o ejemplos)? Sugiere una respuesta alternativa o mejoras específicas.

¿Mis respuestas demostraron habilidades clave relevantes para el puesto (ej. resolución de problemas, liderazgo, trabajo en equipo, etc.)?
Comunicación de Propuesta de Valor:

¿Logré destacar claramente por qué soy el candidato adecuado para este rol y empresa?
¿Hice preguntas pertinentes que demostraron mi interés y mi pensamiento estratégico?

Habilidades No Verbales y Tono:
Basado en mi descripción, ¿cómo influyó mi lenguaje corporal y tono en la percepción de mi confianza, profesionalismo e interés?
¿Hay alguna área de mejora en mi comunicación no verbal?
Fortalezas y Oportunidades de Mejora:

Identifica mis 3 principales fortalezas que se destacaron durante la entrevista.

Identifica 3 áreas clave donde tengo una oportunidad significativa de mejora para futuras entrevistas. Sé específico y proporciona consejos prácticos.

Alineación con el Rol y la Empresa:

¿Qué tan bien parezco encajar con la cultura de la empresa y los requisitos del rol, basándote en mi desempeño en la entrevista?

Próximos Pasos Sugeridos:

¿Qué debería hacer ahora después de esta entrevista? (Ej. Enviar un correo de agradecimiento, seguir el proceso, preparar un portafolio adicional, investigar más).
¿Qué acciones específicas puedo tomar para mejorar en mis próximas entrevistas?
Reflexión Final:
Proporciona una conclusión general sobre el resultado de la entrevista y un mensaje motivador o de enfoque.

Contexto:
- Proyecto: {project_name}
- Compañía: {company_name}
- Archivo: {video_file}

Texto de la entrevista:
{text}
"""

STUDY_PROMPT = lambda text, project_name, company_name, video_file: f"""
realiza un análisis completo y estructurado del video de estudio, abordando los siguientes puntos:

Resumen y Contexto:

Una breve descripción del video y su propósito.

Evaluación de la idoneidad del tema y el nivel para la audiencia objetivo.

Análisis del Contenido:

Evaluación de la claridad, precisión y profundidad de los conceptos explicados.

Crítica sobre la efectividad de los ejemplos y la estructura del contenido.

Análisis de la Presentación:

Comentario sobre la calidad técnica (audio/video) y el impacto del estilo del presentador.

Evaluación del uso de recursos visuales y el ritmo de la explicación en relación con el engagement.

Evaluación de la Efectividad Educativa:

¿Qué tan bien el video cumple su objetivo de enseñanza?

Identifica los momentos donde el video fue más o menos efectivo para tu aprendizaje.

Compara la información del video con tu conocimiento previo del tema.

Fortalezas Clave del Video:

Destaca los elementos que hacen que este video sea valioso para el estudio.

Oportunidades de Mejora y Sugerencias Constructivas:

Proporciona ideas concretas sobre cómo el video podría ser mejorado (ej. añadir más ejercicios, cambiar el ritmo, mejorar los gráficos, etc.).

Aplicación Personal y Lecciones Aprendidas:

¿Cómo puedes aplicar lo aprendido de este análisis a tus propios hábitos de estudio?

Si eres creador de contenido, ¿qué ideas puedes tomar para mejorar tus propios videos educativos?

Conclusión y Recomendación:

Un veredicto final sobre el video y a quién se lo recomendarías.

Contexto:
- Proyecto: {project_name}
- Compañía: {company_name}
- Archivo: {video_file}

Texto del video de estudio:
{text}
"""

DEFAULT_PROMPT = lambda text, project_name, company_name, video_file: f"""
Eres un asistente ejecutivo. Resume esta reunión, identifica tareas y puntos clave.

Contexto:
- Proyecto: {project_name}
- Compañía: {company_name}
- Archivo: {video_file}

Texto de la reunión:
{text}

Formato:
### 📝 Resumen

[Resumen aquí]

---

### ✅ Tareas Detectadas

- [ ] Tarea 1
- [ ] Tarea 2

---

### 📌 Observaciones

- Punto clave 1
- Punto clave 2
"""

def get_prompt_template(text, project_name, company_name, video_file_path):
    """Selecciona el template de prompt apropiado basado en el tipo de contenido"""
    content_type = get_content_type(text, video_file_path)
    
    # Extract just the filename for the prompt display
    import os
    video_file = os.path.basename(video_file_path)
    
    if content_type == "entrevista":
        return ENTREVISTA_PROMPT(text, project_name, company_name, video_file)
    elif content_type == "study":
        return STUDY_PROMPT(text, project_name, company_name, video_file)
    elif content_type == "redesign":
        return REDESIGN_PROMPT(text, project_name, company_name, video_file)
    else:
        return DEFAULT_PROMPT(text, project_name, company_name, video_file)

HTML_TEMPLATE = lambda summary, project_name, company_name, video_file: f"""
<html>
  <body style='font-family: sans-serif;'>
    <h2>📁 Proyecto: {project_name}</h2>
    <h3>🏢 Compañía: {company_name}</h3>
    <h4>🎞️ Archivo: {video_file}</h4>
    <hr>
    <pre style='background:#f9f9f9; padding: 1em; border-radius: 5px;'>{summary}</pre>
  </body>
</html>
"""

def summarize_with_gpt(text, project_name="", company_name="", video_file=""):
    try:
        print("🧠 Usando GPT...")
        client = openai.OpenAI(api_key=OPENAI_API_KEY)

        prompt = get_prompt_template(text, project_name, company_name, video_file)

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Eres un asistente inteligente que analiza contenido según su tipo: entrevistas, videos de estudio, o reuniones."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print("⚠️ GPT falló:", str(e))
        return summarize_with_deepseek(text, project_name, company_name, video_file)

def summarize_with_deepseek(text, project_name="", company_name="", video_file=""):
    try:
        print("🧠 Usando DeepSeek...")
        prompt = get_prompt_template(text, project_name, company_name, video_file)

        payload = {
            "model": "deepseek-coder",
            "messages": [
                {"role": "system", "content": "Eres un asistente inteligente que analiza contenido según su tipo: entrevistas, videos de estudio, o reuniones."},
                {"role": "user", "content": prompt}
            ]
        }
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        response = requests.post("https://api.deepseek.com/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print("⚠️ DeepSeek API falló:", str(e))
        return summarize_with_ollama(text, project_name, company_name, video_file)

def summarize_with_ollama(text, project_name="", company_name="", video_file=""):
    try:
        print("🤖 Usando Ollama...")
        prompt = get_prompt_template(text, project_name, company_name, video_file)
        payload = {
            "model": "mistral",
            "prompt": prompt,
            "stream": False
        }
        response = requests.post(f"{OLLAMA_URL}/api/generate", json=payload)
        response.raise_for_status()
        return response.json().get("response", "")
    except Exception as e:
        print("❌ Ollama también falló:", str(e))
        return "❌ Ollama también falló: " + str(e)

def generate_summary(text, project_name="", company_name="", video_file=""):
    provider = os.getenv("SUMMARY_PROVIDER", "gpt").strip().lower()

    try:
        if provider == "gpt":
            result = summarize_with_gpt(text, project_name, company_name, video_file)
        elif provider == "deepseek":
            result = summarize_with_deepseek(text, project_name, company_name, video_file)
        elif provider == "ollama":
            result = summarize_with_ollama(text, project_name, company_name, video_file)
        else:
            print(f"❌ Proveedor inválido: {provider}, usando fallback...")
            result = summarize_with_ollama(text, project_name, company_name, video_file)

        return result

    except Exception as e:
        print(f"❗ Error general, usando Ollama fallback: {str(e)}")
        return summarize_with_ollama(text, project_name, company_name, video_file)

def render_summary_html(summary_text, project_name, company_name, video_file):
    return HTML_TEMPLATE(summary_text, project_name, company_name, video_file)
