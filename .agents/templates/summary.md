# Template: AI-Generated Summary from Transcription

Use this template when generating a Markdown summary from a Whisper transcript.

## Input Variables

- `video_filename` — original video name (used for title and routing hints)
- `language` — detected language (es, en, etc.)
- `duration` — total duration in seconds
- `transcription_text` — full transcript text
- `segments` — array of `{start, end, text}` objects
- `frames` — optional array of `{timestamp, frame_file, caption}` for tutorial videos

## Output Template

```markdown
# Resumen: {{ video_filename }}

**Idioma:** {{ language }} | **Duración:** {{ duration // 60 }} min
**Fecha de generación:** {{ now() }}

## TL;DR (3-5 bullets)
- Bullet 1
- Bullet 2
- Bullet 3

## Temas principales
1. **Tema A** — paragraph
2. **Tema B** — paragraph
3. **Tema C** — paragraph

## Decisiones / Acciones
- [ ] Acción 1
- [ ] Acción 2

{% if frames %}
## Frames clave
| Timestamp | Frame | Descripción |
|-----------|-------|-------------|
{% for f in frames %}
| {{ f.timestamp }} | {{ f.frame_file }} | {{ f.caption or "—" }} |
{% endfor %}
{% endif %}

## Transcripción completa
<details>
<summary>Expandir</summary>

{{ transcription_text }}

</details>
```

## Routing Hints (for the LLM agent)

Based on `video_filename` prefix:
- `northwind_` → save to `NORTHWIND_PATH/docs/transcripts/`
- `zo_` / `interview` / `entrevista` → save to `ZO_INTERVIEWS_PATH/summaries/`
- `jm_` → save to `Videos/py_jm/summaries/`
- `tutorial` → include **Frames clave** table and add `## Pasos del tutorial` section

## Prompt for the Agent

```
You are a transcription analyst. Read the following transcript and generate a structured Markdown summary using the template above.
Be concise but comprehensive. If the filename contains "tutorial", prioritize step-by-step instructions and include timestamps.
Output ONLY the Markdown content.
```
