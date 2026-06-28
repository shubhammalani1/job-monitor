import pdfParse from "pdf-parse";
import mammoth from "mammoth";

const MAX_TEXT_LENGTH = 8000;

export async function extractTextFromFile(buffer, filename) {
  const lower = (filename || "").toLowerCase();

  let text;
  if (lower.endsWith(".pdf")) {
    const result = await pdfParse(buffer);
    text = result.text;
  } else if (lower.endsWith(".docx")) {
    const result = await mammoth.extractRawText({ buffer });
    text = result.value;
  } else {
    text = buffer.toString("utf-8");
  }

  text = (text || "").trim();
  if (!text) {
    throw new Error("Could not extract any text from this file");
  }

  return text.slice(0, MAX_TEXT_LENGTH);
}
