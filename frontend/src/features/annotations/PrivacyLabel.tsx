import { Badge } from "@/components/primitives/Badge";

interface PrivacyLabelProps {
  shared: boolean;
}

export function PrivacyLabel({ shared }: PrivacyLabelProps) {
  return <Badge variant={shared ? "success" : "neutral"}>{shared ? "Shared with readers" : "Private note"}</Badge>;
}
