export type InsightPaneTab =
  | "summary"       // owned by phase 08d
  | "chat"          // Document Chat with single_document scope (#474)
  | "related"       // owned by phase 08d
  | "annotations"   // owned by phase 08e (unified: comments removed per #487)
  | "subscriptions" // owned by phase 08e
  | "versions"      // owned by phase 08f (#204)
  | "details";      // owned by #445
