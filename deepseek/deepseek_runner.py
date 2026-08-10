"""
DEPRECATED — use watcher.core.integration.llm_client.generate_summary instead.
Kept for reference. generate_summary() here clashes in name with llm_client.
"""
import os
import openai

PROVIDER = os.getenv("SUMMARY_PROVIDER", "gpt")

# =======================
# PROVIDER: OPENAI GPT
# =======================
def summarize_with_gpt(text):
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Eres un asistente ejecutivo que resume reuniones y lista tareas."},
            {"role": "user", "content": f"Resumen y tareas de la reunión:\n\n{text}"}
        ]
    )
    return response.choices[0].message.content

# =======================
# PROVIDER: OLLAMA
# =======================
def summarize_with_ollama(text):
    import requests
    payload = {
        "model": "mistral",  # o "phi3", etc.
        "prompt": f"""Actúa como asistente ejecutivo. Resume la siguiente reunión y lista tareas:\n\n{text}""",
        "stream": False
    }
    response = requests.post("http://localhost:11434/api/generate", json=payload)
    return response.json().get("response", "")

# =======================
# PROVIDER: DeepSeek-Coder
# =======================
def summarize_with_deepseek(text):
    from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
    model_id = "deepseek-ai/deepseek-llm-7b-chat"  # chat model, not coder
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(model_id, trust_remote_code=True, device_map="auto")

    generator = pipeline("text-generation", model=model, tokenizer=tokenizer)
    prompt = f"""Actúa como asistente ejecutivo. Lee la siguiente transcripción y responde:\n
1. ¿Cuál es el resumen de la reunión?\n2. ¿Qué tareas debo realizar?\nTexto:\n\"\"\"{text}\"\"\""""
    output = generator(prompt, max_new_tokens=500, do_sample=True)[0]["generated_text"]
    return output

# =======================
# FUNCIÓN PRINCIPAL
# =======================
def generate_summary(text):
    if PROVIDER == "gpt":
        return summarize_with_gpt(text)
    elif PROVIDER == "ollama":
        return summarize_with_ollama(text)
    elif PROVIDER == "deepseek":
        return summarize_with_deepseek(text)
    else:
        return "❌ Proveedor inválido."

# =======================
# USO LOCAL (demo)
# =======================
if __name__ == "__main__":
    with open("demo.txt", encoding="utf-8") as f:
        texto = f.read()
    print(generate_summary(texto))
