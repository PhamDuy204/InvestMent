import { getCache } from "@vercel/functions";
import { NextResponse } from "next/server";

import { isAuthorizedDigest } from "../../../lib/server-telemetry";
import { sanitizeTelemetry, validateTelemetry } from "../../../lib/telemetry";

export const runtime = "nodejs";
const TELEMETRY_KEY = "v13-monitoring-latest";
// ponytail: static digest keeps deploys independent of missing env injection; switch to managed INGEST_TOKEN_SHA256 when connector env writes are available.
const INGEST_TOKEN_SHA256 = process.env.INGEST_TOKEN_SHA256 ?? "10239bd076a7a1cccfcfd6e194d617739b8dcbe88a81432542e4b2b22ca9bd27";

export async function POST(request: Request) {
  if (!isAuthorizedDigest(request.headers.get("authorization"), INGEST_TOKEN_SHA256)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  let body: unknown;
  try { body = await request.json(); }
  catch { return NextResponse.json({ error: "invalid_json" }, { status: 400 }); }
  const validation = validateTelemetry(body);
  if (!validation.ok) return NextResponse.json({ error: "invalid_telemetry" }, { status: 400 });
  const telemetry = sanitizeTelemetry(validation.data);
  if (!telemetry) return NextResponse.json({ error: "invalid_telemetry" }, { status: 400 });
  await getCache().set(TELEMETRY_KEY, telemetry, {
    ttl: 604800,
    tags: ["v13-monitoring"],
    name: "V13 paper telemetry",
  });
  return NextResponse.json({ ok: true, updated_at_utc: telemetry.updated_at_utc });
}
