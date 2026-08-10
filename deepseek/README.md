


<!-- Elimina contenedores anteriores -->
docker compose down

<!-- Recompila con tus nuevos archivos - solo para cambios en requirements? -->
docker compose build --no-cache

<!-- Si solo editas .py (no requirements.txt), puedes correr: -->
docker compose up --build

<!-- Arranca con el código actualizado -->
docker compose up