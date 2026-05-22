import { createRouter, createRoute, createRootRoute, redirect } from "@tanstack/react-router";
import { authStorage } from "@/api/auth";
import { SignUpPage } from "@/features/auth/SignUpPage";
import { LoginPage } from "@/features/auth/LoginPage";
import { SearchPage } from "@/features/search/SearchPage";
import { DocumentPage } from "@/features/documents/DocumentPage";
import { QAPage } from "@/features/qa/QAPage";
import { ChatPage } from "@/features/chat/ChatPage";
import { SubscriptionsPage } from "@/features/subscriptions/SubscriptionsPage";
import { NotificationsPage } from "@/features/notifications/NotificationsPage";
import { HistoryPage } from "@/features/history/HistoryPage";
import { ExpertisePage } from "@/features/expertise/ExpertisePage";
import { AdminHubPage } from "@/features/admin/AdminHubPage";
import { AdminSourcesPage } from "@/features/admin/AdminSourcesPage";
import { AdminSourceDetailPage } from "@/features/admin/AdminSourceDetailPage";
import { AdminAddSourceWizard } from "@/features/admin/AdminAddSourceWizard";
import { AdminGroupsPage } from "@/features/admin/AdminGroupsPage";
import { AdminGroupDetailPage } from "@/features/admin/AdminGroupDetailPage";
import { AdminUsersPage } from "@/features/admin/AdminUsersPage";
import { AdminUserDetailPage } from "@/features/admin/AdminUserDetailPage";
import { AppLayout } from "./AppLayout";

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
  beforeLoad: () => { throw redirect({ to: "/search", search: { q: "", mode: "hybrid" } }); },
});

const searchRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/search",
  component: SearchPage,
  validateSearch: (search: Record<string, unknown>) => ({
    q: typeof search.q === "string" ? search.q : "",
    mode: typeof search.mode === "string" ? search.mode : "hybrid",
    file_type: typeof search.file_type === "string" ? search.file_type : "",
    tags: typeof search.tags === "string" ? search.tags : "",
    source: typeof search.source === "string" ? search.source : "",
    file_extension: typeof search.file_extension === "string" ? search.file_extension : "",
    sort_by: typeof search.sort_by === "string" ? search.sort_by : "",
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
    return { ...(page !== undefined ? { page } : {}), ...(chunk !== undefined ? { chunk } : {}) };
  },
});

const qaRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/qa",
  component: QAPage,
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

const adminSourcesRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/sources",
  component: AdminSourcesPage,
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

const routeTree = rootRoute.addChildren([
  loginRoute,
  signupRoute,
  appRoute.addChildren([
    indexRoute,
    searchRoute,
    docRoute,
    qaRoute,
    chatRoute,
    subscriptionsRoute,
    notificationsRoute,
    historyRoute,
    expertiseRoute,
    adminRoute,
    adminSourcesRoute,
    adminAddSourceRoute,
    adminSourceDetailRoute,
    adminGroupsRoute,
    adminGroupDetailRoute,
    adminUsersRoute,
    adminUserDetailRoute,
  ]),
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
