import requests
import datetime
import logging

def send_summary_to_notion(notion_token, database_id, project, file_name, summary):
    url = "https://api.notion.com/v1/pages"

    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    data = {
        "parent": {"database_id": database_id},
        "properties": {
            "Proyecto": {"title": [{"text": {"content": project}}]},
            "Archivo": {"rich_text": [{"text": {"content": file_name}}]},
            "Resumen": {"rich_text": [{"text": {"content": summary}}]},
            "Fecha de creacion": {"date": {"start": datetime.datetime.utcnow().isoformat()}},
        }
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        logging.error(f"❌ Error al guardar en Notion: {response.text}")
    else:
        logging.info("✅ Resumen enviado a Notion correctamente.")
