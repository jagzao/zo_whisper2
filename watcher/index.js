const fs = require("fs");
const path = require("path");
const axios = require("axios");

const folder = process.env.TRANSCRIPTIONS_FOLDER || "CarpetaTranscripciones";
const summaryUrl = process.env.SUMMARY_SERVICE_URL || "http://localhost:7860";

fs.watch(folder, { recursive: true }, async (eventType, filename) => {
  if (filename && filename.endsWith(".txt")) {
    const fullPath = path.join(folder, filename);
    console.log(`Nuevo archivo detectado: ${fullPath}`);

    try {
      const text = fs.readFileSync(fullPath, "utf-8");

      const response = await axios.post(`${summaryUrl}/generate-summary`, {
        text: text,
      });

      const resumenPath = fullPath.replace(folder, "resumen").replace(".txt", ".resumen.txt");
      fs.mkdirSync(path.dirname(resumenPath), { recursive: true });
      fs.writeFileSync(resumenPath, response.data.summary, "utf-8");

      console.log(`✅ Resumen generado en: ${resumenPath}`);
    } catch (err) {
      console.error("❌ Error procesando archivo:", err.message);
    }
  }
});
