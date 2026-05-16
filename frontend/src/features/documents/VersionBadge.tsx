import { Badge } from "@/components/primitives/Badge";
import { useT } from "@/i18n/index";

interface VersionBadgeProps {
  versionNumber: number;
  isLatest: boolean;
}

export function VersionBadge({ versionNumber, isLatest }: VersionBadgeProps) {
  const t = useT();
  return (
    <Badge variant={isLatest ? "success" : "neutral"}>
      {t.insight.versionLabel(versionNumber)}
      {isLatest ? ` · ${t.insight.versionLatest}` : ""}
    </Badge>
  );
}
