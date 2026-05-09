import { api } from "./client";

export interface Subscription {
  id: string;
  user_id: string;
  name: string;
  query: string;
  similarity_threshold: number;
  enabled: boolean;
  unread_count: number;
  last_notified: string | null;
  created_at: string;
  updated_at: string;
}

export interface SubscriptionWrite {
  name: string;
  query: string;
  similarity_threshold: number;
  enabled: boolean;
}

export function listSubscriptions(): Promise<Subscription[]> {
  return api.get<Subscription[]>("/subscriptions");
}

export function createSubscription(data: SubscriptionWrite): Promise<Subscription> {
  return api.post<Subscription>("/subscriptions", data);
}

export function updateSubscription(id: string, data: SubscriptionWrite): Promise<Subscription> {
  return api.put<Subscription>(`/subscriptions/${id}`, data);
}

export function deleteSubscription(id: string): Promise<void> {
  return api.delete(`/subscriptions/${id}`);
}
