/* eslint-disable react-refresh/only-export-components */
import { lazy, Suspense, type ComponentType } from "react";
import {
  createRouter,
  createRoute,
  createRootRoute,
  redirect,
} from "@tanstack/react-router";
import { ErrorBoundary } from "react-error-boundary";
import { authStorage } from "@/api/auth";
import { RouteErrorFallback } from "@/components/primitives/RouteErrorFallback";
import { AppLayout } from "./AppLayout";

// Wraps a named export from a lazy-loaded module into a React.lazy() component.
function lazyRoute<M extends Record<string, ComponentType>>(
  importFn: () => Promise<M>,
  pick: keyof M,
) {
  return lazy(() => importFn().then((m) => ({ default: m[pick] as ComponentType })));
}

// --- Route-level code splitting ---
// Auth pages sit outside AppLayout so they carry their own Suspense + ErrorBoundary.
// App pages render inside AppLayout whose <Outlet> is already wrapped in both.

const LazyLoginPage = lazyRoute(() => import("@/features/auth/LoginPage"), "LoginPage");
const LazySignUpPage = lazyRoute(() => import("@/features/auth/SignUpPage"), "SignUpPage");
const SearchPage = lazyRoute(() => import("@/features/search/SearchPage"), "SearchPage");
const DocumentPage = lazyRoute(() => import("@/features/documents/DocumentPage"), "DocumentPage");
const ChatPage = lazyRoute(() => import("@/features/chat/ChatPage"), "ChatPage");
const SubscriptionsPage = lazyRoute(() => import("@/features/subscriptions/SubscriptionsPage"), "SubscriptionsPage");
const EvidencePacksPage = lazyRoute(() => import("@/features/evidence/EvidencePacksPage"), "EvidencePacksPage");
const EvidencePackDetailPage = lazyRoute(() => import("@/features/evidence/EvidencePackDetailPage"), "EvidencePackDetailPage");
const NotificationsPage = lazyRoute(() => import("@/features/notifications/NotificationsPage"), "NotificationsPage");
const HistoryPage = lazyRoute(() => import("@/features/history/HistoryPage"), "HistoryPage");
const ExpertisePage = lazyRoute(() => import("@/features/expertise/ExpertisePage"), "ExpertisePage");
const AdminHubPage = lazyRoute(() => import("@/features/admin/AdminHubPage"), "AdminHubPage");
const AdminIngestionPage = lazyRoute(() => import("@/features/admin/AdminIngestionPage"), "AdminIngestionPage");
const AdminSourcesPage = lazyRoute(() => import("@/features/admin/AdminSourcesPage"), "AdminSourcesPage");
const AdminSourceDetailPage = lazyRoute(() => import("@/features/admin/AdminSourceDetailPage"), "AdminSourceDetailPage");
const AdminSourceHealthPage = lazyRoute(() => import("@/features/admin/AdminSourceHealthPage"), "AdminSourceHealthPage");
const AdminAddSourceWizard = lazyRoute(() => import("@/features/admin/AdminAddSourceWizard"), "AdminAddSourceWizard");
const AdminEditSourcePage = lazyRoute(() => import("@/features/admin/AdminEditSourcePage"), "AdminEditSourcePage");
const AdminGroupsPage = lazyRoute(() => import("@/features/admin/AdminGroupsPage"), "AdminGroupsPage");
const AdminGroupDetailPage = lazyRoute(() => import("@/features/admin/AdminGroupDetailPage"), "AdminGroupDetailPage");
const AdminUsersPage = lazyRoute(() => import("@/features/admin/AdminUsersPage"), "AdminUsersPage");
const AdminUserDetailPage = lazyRoute(() => import("@/features/admin/AdminUserDetailPage"), "AdminUserDetailPage");
const AdminModelProvidersPage = lazyRoute(() => import("@/features/admin/AdminModelProvidersPage"), "AdminModelProvidersPage");
const AdminRuntimeConfigPage = lazyRoute(() => import("@/features/admin/AdminRuntimeConfigPage"), "AdminRuntimeConfigPage");
const AdminLdapPage = lazyRoute(() => import("@/features/admin/AdminLdapPage"), "AdminLdapPage");
const QualityLabPage = lazyRoute(() => import("@/features/admin/QualityLabPage"), "QualityLabPage");
const PermissionSimulatorPage = lazyRoute(() => import("@/features/admin/PermissionSimulatorPage"), "PermissionSimulatorPage");

// Auth pages need their own Suspense + ErrorBoundary (no AppLayout shell above them).
function LoginPage() {
  return (
    <ErrorBoundary FallbackComponent={RouteErrorFallback}>
      <Suspense fallback={null}>
        <LazyLoginPage />
      </Suspense>
    </ErrorBoundary>
  );
}
function SignUpPage() {
  return (
    <ErrorBoundary FallbackComponent={RouteErrorFallback}>
      <Suspense fallback={null}>
        <LazySignUpPage />
      </Suspense>
    </ErrorBoundary>
  );
}

function requireAuth() {
  if (!authStorage.hasToken()) {
    throw redirect({ to: "/login" });
  }
}

const rootRoute = createRootRoute();

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  component: LoginPage,
});

const signupRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/signup",
  component: SignUpPage,
});

const appRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "app",
  beforeLoad: requireAuth,
  component: AppLayout,
});

const indexRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/",
  beforeLoad: () => {
    throw redirect({ to: "/search", search: { q: "", mode: "hybrid" } });
  },
});

const searchRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/search",
  component: SearchPage,
  validateSearch: (search: Record<string, unknown>) => ({
    q: typeof search.q === "string" ? search.q : "",
    mode: typeof search.mode === "string" ? search.mode : "hybrid",
  }),
});

function parseNum(v: unknown): number | undefined {
  if (typeof v === "number") return v;
  if (typeof v === "string") {
    const n = Number(v);
    return Number.isFinite(n) ? n : undefined;
  }
  return undefined;
}

const docRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/doc/$docId",
  component: DocumentPage,
  validateSearch: (search: Record<string, unknown>) => {
    const page = parseNum(search.page);
    const chunk = parseNum(search.chunk);
    return {
      ...(page !== undefined ? { page } : {}),
      ...(chunk !== undefined ? { chunk } : {}),
    };
  },
});

const chatRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/chat",
  component: ChatPage,
  validateSearch: (search: Record<string, unknown>) => ({
    scope: typeof search.scope === "string" ? search.scope : undefined,
    ids: typeof search.ids === "string" ? search.ids : undefined,
  }),
});

const subscriptionsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/subscriptions",
  component: SubscriptionsPage,
});

const evidenceRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/evidence",
  component: EvidencePacksPage,
});

const evidenceDetailRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/evidence/$packId",
  component: EvidencePackDetailPage,
});

const notificationsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/notifications",
  component: NotificationsPage,
});

const historyRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/history",
  component: HistoryPage,
});

const expertiseRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/expertise",
  component: ExpertisePage,
});

const adminRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin",
  component: AdminHubPage,
});

const adminIngestionRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/ingestion",
  component: AdminIngestionPage,
});

const adminSourcesRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/sources",
  component: AdminSourcesPage,
});

const adminSourceHealthRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/source-health",
  component: AdminSourceHealthPage,
});

const adminAddSourceRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/sources/new",
  component: AdminAddSourceWizard,
});

const adminSourceDetailRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/sources/$sourceId",
  component: AdminSourceDetailPage,
});

const adminEditSourceRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/sources/$sourceId/edit",
  component: AdminEditSourcePage,
});

const adminGroupsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/groups",
  component: AdminGroupsPage,
});

const adminGroupDetailRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/groups/$groupId",
  component: AdminGroupDetailPage,
});

const adminUsersRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/users",
  component: AdminUsersPage,
});

const adminUserDetailRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/users/$userId",
  component: AdminUserDetailPage,
});

const adminModelProvidersRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/model-providers",
  component: AdminModelProvidersPage,
});

const adminLdapRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/ldap",
  component: AdminLdapPage,
});

const adminRuntimeConfigRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/config",
  component: AdminRuntimeConfigPage,
});

const qualityLabRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/quality-lab",
  component: QualityLabPage,
});

const permissionSimulatorRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/permission-simulator",
  component: PermissionSimulatorPage,
});

const routeTree = rootRoute.addChildren([
  loginRoute,
  signupRoute,
  appRoute.addChildren([
    indexRoute,
    searchRoute,
    docRoute,
    chatRoute,
    subscriptionsRoute,
    evidenceRoute,
    evidenceDetailRoute,
    notificationsRoute,
    historyRoute,
    expertiseRoute,
    adminRoute,
    adminIngestionRoute,
    adminSourcesRoute,
    adminSourceHealthRoute,
    adminAddSourceRoute,
    adminSourceDetailRoute,
    adminEditSourceRoute,
    adminGroupsRoute,
    adminGroupDetailRoute,
    adminUsersRoute,
    adminUserDetailRoute,
    adminModelProvidersRoute,
    adminLdapRoute,
    adminRuntimeConfigRoute,
    qualityLabRoute,
    permissionSimulatorRoute,
  ]),
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
