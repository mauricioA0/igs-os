"use server";

import { revalidatePath } from "next/cache";
import { ApiError, unwrap } from "@/lib/api";
import { serverApi } from "@/lib/api/server";
import type { ApiProblem, ApprovalDecisionIn, ApprovalDecisionOut, ApprovalDetail, Result } from "./types";

function problemOf(e: unknown): ApiProblem {
  if (e instanceof ApiError) return { status: e.status, code: e.code, title: e.title, detail: e.detail };
  return { status: 0, code: "network-error", title: "No pudimos conectar con la API." };
}

export async function fetchApproval(id: string): Promise<Result<ApprovalDetail>> {
  try {
    const data = await unwrap(serverApi().GET("/v1/approvals/{approval_id}", { params: { path: { approval_id: id } } }));
    return { ok: true, data };
  } catch (e) {
    return { ok: false, problem: problemOf(e) };
  }
}

export async function decideApproval(id: string, body: ApprovalDecisionIn): Promise<Result<ApprovalDecisionOut>> {
  try {
    const data = await unwrap(
      serverApi().POST("/v1/approvals/{approval_id}/decision", { params: { path: { approval_id: id } }, body }),
    );
    revalidatePath("/ops/approvals");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, problem: problemOf(e) };
  }
}
