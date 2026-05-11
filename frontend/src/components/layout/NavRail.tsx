import { useState, useEffect } from "react";
import { Link } from "@tanstack/react-router";
import {
  Search,
  MessageSquare,
  Bell,
  History,
  Bookmark,
  Settings,
  Shield,
  Network,
  ChevronRight,
  ChevronLeft,
} from "lucide-react";
import { useT } from "@/i18n/index";
import { LanguageSelector } from "@/components/settings/LanguageSelector";
import { TomorrowlandLogo } from "@/components/brand/TomorrowlandLogo";
import styles from "./NavRail.module.css";

type NavKey = "search" | "qa" | "subscriptions" | "notifications" | "history" | "expertise" | "admin";

interface NavItem {
  to: string;
  key: NavKey;
  icon: React.ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/search", key: "search", icon: <Search size={20} /> },
  { to: "/qa", key: "qa", icon: <MessageSquare size={20} /> },
  { to: "/subscriptions", key: "subscriptions", icon: <Bookmark size={20} /> },
  { to: "/notifications", key: "notifications", icon: <Bell size={20} /> },
  { to: "/history", key: "history", icon: <History size={20} /> },
  { to: "/expertise", key: "expertise", icon: <Network size={20} /> },
];

const ADMIN_ITEM: NavItem = {
  to: "/admin",
  key: "admin",
  icon: <Shield size={20} />,
};

const STORAGE_KEY = "tomorrowland_rail_expanded";

interface NavRailProps {
  isAdmin: boolean;
  unreadCount?: number;
}

export function NavRail({ isAdmin, unreadCount = 0 }: NavRailProps) {
  const t = useT();
  const [expanded, setExpanded] = useState<boolean>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === "1";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, expanded ? "1" : "0");
    } catch {
      // ignore storage errors in sandboxed environments
    }
  }, [expanded]);

  const items = isAdmin ? [...NAV_ITEMS, ADMIN_ITEM] : NAV_ITEMS;

  return (
    <nav
      className={`${styles.rail} ${expanded ? styles.expanded : ""}`}
      aria-label={t.nav.primary}
    >
      <div className={styles.top}>
        <TomorrowlandLogo size={32} className={styles.mark} />
        <button
          className={styles.toggle}
          onClick={() => setExpanded((e) => !e)}
          aria-label={expanded ? t.nav.collapse : t.nav.expand}
          title={expanded ? t.nav.collapse : t.nav.expand}
        >
          {expanded ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
        </button>
      </div>

      <ul className={styles.list} role="list">
        {items.map((item) => {
          const label = t.nav[item.key];
          return (
            <li key={item.to}>
              <Link
                to={item.to}
                className={styles.item}
                activeProps={{ className: `${styles.item} ${styles.active}` }}
                title={!expanded ? label : undefined}
              >
                <span className={styles.icon} aria-hidden>
                  {item.to === "/notifications" && unreadCount > 0 ? (
                    <span className={styles.badgeWrap}>
                      {item.icon}
                      <span className={styles.badge} aria-label={t.nav.unread(unreadCount)}>
                        {unreadCount > 9 ? "9+" : unreadCount}
                      </span>
                    </span>
                  ) : (
                    item.icon
                  )}
                </span>
                <span className={styles.label}>{label}</span>
              </Link>
            </li>
          );
        })}
      </ul>

      <div className={styles.bottom}>
        <Link
          to="/settings/profile"
          className={styles.item}
          title={!expanded ? t.nav.settings : undefined}
        >
          <span className={styles.icon} aria-hidden><Settings size={20} /></span>
          <span className={styles.label}>{t.nav.settings}</span>
        </Link>
        <LanguageSelector />
      </div>
    </nav>
  );
}
