"use server";

import { revalidatePath } from "next/cache";
import { apiWrite, type WriteResult } from "@/features/ops-shell/writes";
import type { TripItem } from "./api";

export type ItemStatus = TripItem["status"];

/** `PATCH /v1/trips/{id}/items/{item_id}`: the API applies domain transitions, audit and events. */
export async function updateTripItemStatus(
  tripId: string,
  itemId: string,
  status: ItemStatus,
): Promise<WriteResult<TripItem>> {
  const result = await apiWrite<TripItem>(
    "PATCH",
    `/v1/trips/${encodeURIComponent(tripId)}/items/${encodeURIComponent(itemId)}`,
    { status },
  );
  if (result.ok) {
    revalidatePath(`/ops/trips/${tripId}`);
    revalidatePath("/ops");
  }
  return result;
}
