import { api } from "./client";

export interface ActivityItem {
  doc_id: string;
  title: string | null;
  mime_type: string;
  viewed_at: string | null;
}

export function getActivity(limit = 50, offset = 0): Promise<ActivityItem[]> {
  return api.get<ActivityItem[]>(`/me/activity?skip=${offset}&limit=${limit}`);
}
