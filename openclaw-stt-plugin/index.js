import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const pluginRoot = path.dirname(fileURLToPath(import.meta.url));
const defaultScriptPath = path.join(pluginRoot, "stt_cli.py");

function parseJson(text) {
  const trimmed = String(text ?? "").trim();
  if (!trimmed) return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    const lines = trimmed.split(/\r?\n/).filter(Boolean);
    if (lines.length === 0) return null;
    try {
      return JSON.parse(lines[lines.length - 1]);
    } catch {
      return null;
    }
  }
}

function createSttTool(api) {
  return {
    name: "stt_transcribe",
    label: "STT Transcribe",
    description: "Transcribe local audio to text. If audio_path is missing, record from mic first.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        audio_path: { type: "string", description: "Absolute local audio file path." },
        record_seconds: { type: "number", minimum: 0.3, maximum: 120 },
        model: { type: "string" },
        device: { type: "string" },
        language: { type: "string" },
        use_itn: { type: "boolean" }
      }
    },
    async execute(_id, params) {
      const cfg = api.pluginConfig ?? {};
      const pythonBin = (cfg.pythonBin || process.env.OPENCLAW_STT_PYTHON || "python3").trim();
      const scriptPath = path.resolve((cfg.scriptPath || defaultScriptPath).trim());

      if (!pythonBin) {
        throw new Error("openclaw-stt: pythonBin is empty");
      }
      if (!fs.existsSync(scriptPath)) {
        throw new Error(`openclaw-stt: stt script not found: ${scriptPath}`);
      }

      const args = [scriptPath, "--json"];
      const audioPathRaw = typeof params.audio_path === "string" ? params.audio_path.trim() : "";
      const audioPath = audioPathRaw ? path.resolve(audioPathRaw) : "";
      if (audioPath) {
        args.push("--audio-path", audioPath);
      } else {
        const seconds =
          typeof params.record_seconds === "number" && Number.isFinite(params.record_seconds)
            ? params.record_seconds
            : 5.0;
        args.push("--record-seconds", String(seconds));
      }

      const model =
        (typeof params.model === "string" && params.model.trim()) ||
        (typeof cfg.defaultModel === "string" && cfg.defaultModel.trim()) ||
        "iic/SenseVoiceSmall";
      const device =
        (typeof params.device === "string" && params.device.trim()) ||
        (typeof cfg.defaultDevice === "string" && cfg.defaultDevice.trim()) ||
        "cpu";
      const language =
        (typeof params.language === "string" && params.language.trim()) ||
        (typeof cfg.defaultLanguage === "string" && cfg.defaultLanguage.trim()) ||
        "auto";
      const useItn =
        typeof params.use_itn === "boolean"
          ? params.use_itn
          : typeof cfg.defaultUseItn === "boolean"
            ? cfg.defaultUseItn
            : true;

      args.push("--model", model, "--device", device, "--language", language);
      if (useItn) {
        args.push("--use-itn");
      }

      const timeoutMs =
        typeof cfg.timeoutMs === "number" && Number.isFinite(cfg.timeoutMs)
          ? Math.max(1000, Math.min(300000, Math.floor(cfg.timeoutMs)))
          : 120000;

      const proc = spawnSync(pythonBin, args, {
        encoding: "utf8",
        timeout: timeoutMs,
        maxBuffer: 1024 * 1024 * 8,
      });

      if (proc.error) {
        throw new Error(`openclaw-stt spawn failed: ${proc.error.message}`);
      }

      const payload = parseJson(proc.stdout);
      const stderr = String(proc.stderr ?? "").trim();
      if (proc.status !== 0) {
        const reason = payload?.error || stderr || `exit status ${proc.status}`;
        throw new Error(`openclaw-stt failed: ${reason}`);
      }

      const text = typeof payload?.text === "string" ? payload.text : "";
      if (!text.trim()) {
        return {
          content: [{ type: "text", text: "(STT completed, but no speech recognized)" }],
          details: { text: "", raw: payload ?? null },
        };
      }

      return {
        content: [{ type: "text", text }],
        details: { text, raw: payload ?? null },
      };
    },
  };
}

export default function register(api) {
  api.registerTool(createSttTool(api));
}
