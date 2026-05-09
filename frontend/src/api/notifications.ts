import { api } from "./client";

export interface Notification {
  id: string;
  subscription_id: string;
  subscription_name: string;
  subscription_query: string;
  doc_id: string;
  doc_title: string;
  similarity: number;
  read: boolean;
  created_at: string;
}

export function listNotifications(unreadOnly = true): Promise<Notification[]> {
  return api.get<Notification[]>(`/notifications?unread_only=${String(unreadOnly)}`);
}

export function markRead(notificationId: string): Promise<{ id: string; read: boolean }> {
  return api.put(`/notifications/${notificationId}/read`, {});
}
