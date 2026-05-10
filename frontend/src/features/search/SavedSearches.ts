export interface SavedSearch {
  id: string;
  name: string;
  query: string;
}

export const SavedSearches: SavedSearch[] = [
  { id: "recent-risk", name: "Recent risk research", query: "risk assessment" },
  { id: "policy-updates", name: "Policy updates", query: "policy update" },
];
