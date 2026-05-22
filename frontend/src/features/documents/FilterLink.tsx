import { Search } from "lucide-react";
import { Link } from "@tanstack/react-router";

interface FilterLinkProps {
  field: string;
  value: string;
  children?: React.ReactNode;
}

export function FilterLink({ field, value, children }: FilterLinkProps) {
  const params: Record<string, string> = {};
  if (field === "source") params.source = value;
  else if (field === "tags") params.tags = value;
  else if (field === "file_type") params.file_type = value;
  else if (field === "file_extension") params.file_extension = value;
  else return <>{children || value}</>;

  return (
    <Link
      to="/search"
      search={{ q: "", mode: "hybrid", ...params }}
      aria-label={`Search for documents with ${field}: ${value}`}
      style={{ display: "inline-flex", alignItems: "center", gap: 2, color: "inherit", textDecoration: "none" }}
    >
      {children || value}
      <Search size={12} style={{ opacity: 0.5, marginLeft: 2 }} />
    </Link>
  );
}
