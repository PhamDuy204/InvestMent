import { getCache } from "@vercel/functions";
import { NextResponse } from "next/server";

import { sanitizeTelemetry } from "../../../lib/telemetry";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store, max-age=0" };
const TELEMETRY_KEY = "v13-monitoring-latest";

export async function GET() {
  try {
    const stored = await getCache().get(TELEMETRY_KEY);
    if (!stored) {
      return NextResponse.json({ status: "WAITING" }, { status: 404, headers: NO_STORE });
    }
    const telemetry = sanitizeTelemetry(stored);
    if (!telemetry) throw new Error("stored_telemetry_invalid");
    return NextResponse.json(telemetry, { headers: NO_STORE });
  } catch (error) {
    const message = error instanceof Error ? error.message : "telemetry_unavailable";
    return NextResponse.json({ status: "DEGRADED", error: message.slice(0, 120) }, { status: 503, headers: NO_STORE });
  }
}
