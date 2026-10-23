"use server";

import { revalidatePath } from "next/cache";
import { apiWrite, type WriteResult } from "@/features/ops-shell/writes";
import type { LeadStage } from "./data";

/** `PATCH /v1/leads/{id}`: stage change (with the reason when a lead is lost). */
export async function updateLeadStatus(
  id: string,
  status: LeadStage,
  lostReason?: string,
): Promise<WriteResult<unknown>> {
  const body = status === "lost" ? { status, lost_reason: lostReason } : { status };
  const result = await apiWrite("PATCH", `/v1/leads/${encodeURIComponent(id)}`, body);
  if (result.ok) revalidatePath("/ops/leads");
  return result;
}
